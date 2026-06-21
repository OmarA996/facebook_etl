"""Delete all ETL data for accounts marked delete=TRUE in the template CSV.

Usage:
    python main.py delete-account-data                          # dry-run preview
    python main.py delete-account-data --yes                    # execute in Postgres only
    python main.py delete-account-data --yes --also-bigquery    # execute in both
    python main.py delete-account-data data/my_custom.csv --yes
"""

from __future__ import annotations

import csv
from pathlib import Path

from sqlalchemy import create_engine, text

from src.config import load_postgres_config
from src.schema.tables import TABLE_SCHEMAS
from src.schema.unique_keys import UNIQUE_KEYS
from src.utils.logger import get_logger

logger = get_logger(__name__)

# dim_meta_accounts uses 'id' as the account identifier, not 'account_id'
_ACCOUNT_COL_OVERRIDES: dict[str, str] = {
    "dim_meta_accounts": "id",
}

# Tables that exist dynamically (breakdowns, raw) - not declared in TABLE_SCHEMAS
_EXTRA_TABLES: list[str] = [
    "meta_insights_raw",
    "fact_meta_ads_combined",
    *[t for t in UNIQUE_KEYS if t not in TABLE_SCHEMAS],
]

_ALL_TABLES: list[str] = list(TABLE_SCHEMAS.keys()) + _EXTRA_TABLES

# For tables that lack account_id, try deleting via these entity columns,
# resolved through the corresponding dim table.
_ENTITY_JOIN: list[tuple[str, str, str]] = [
    # (entity_col_in_fact, dim_table, entity_col_in_dim)
    ("ad_id",       "dim_meta_ads",       "ad_id"),
    ("adset_id",    "dim_meta_adsets",    "adset_id"),
    ("campaign_id", "dim_meta_campaigns", "campaign_id"),
]


def _load_delete_targets(csv_path: str) -> list[tuple[str, str]]:
    """Return [(account_id, account_name), ...] where delete=TRUE."""
    targets: list[tuple[str, str]] = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("delete", "").strip().upper() in ("TRUE", "1", "YES"):
                account_id = row.get("account_id", "").strip()
                account_name = row.get("account_name", "").strip()
                if account_id:
                    targets.append((account_id, account_name))
    return targets


def _both_id_forms(account_ids: list[str]) -> list[str]:
    """Return IDs in both 'act_XXXXX' and 'XXXXX' forms.

    Fact tables store account_id without the 'act_' prefix while dim tables
    store it with the prefix.  Passing both forms covers all tables without
    needing to know which format each table uses.
    """
    forms: list[str] = []
    for aid in account_ids:
        forms.append(aid)
        if aid.startswith("act_"):
            forms.append(aid[4:])
        else:
            forms.append(f"act_{aid}")
    return list(dict.fromkeys(forms))  # deduplicate, preserve order


def _pg_col_exists(conn, table: str, column: str) -> bool:
    result = conn.execute(
        text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.columns"
            "  WHERE table_schema = 'public'"
            "    AND table_name = :tbl AND column_name = :col"
            ")"
        ),
        {"tbl": table, "col": column},
    )
    return bool(result.scalar())


def _pg_table_exists(conn, table: str) -> bool:
    result = conn.execute(
        text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.tables"
            "  WHERE table_schema = 'public' AND table_name = :tbl"
            ")"
        ),
        {"tbl": table},
    )
    return bool(result.scalar())


def _resolve_pg_where(conn, table: str, account_ids: list[str]) -> tuple[str, dict] | None:
    """
    Return (where_clause, params) for deleting account data from a Postgres table,
    or None if the table has no resolvable account link.
    """
    account_col = _ACCOUNT_COL_OVERRIDES.get(table, "account_id")
    # Tables with the 'id' override (dim_meta_accounts) always store the 'act_' form.
    # All other tables may store with or without 'act_', so pass both forms.
    is_override = table in _ACCOUNT_COL_OVERRIDES
    ids = account_ids if is_override else _both_id_forms(account_ids)

    # Direct account column
    if _pg_col_exists(conn, table, account_col):
        return f"{account_col} = ANY(:ids)", {"ids": ids}

    # Fallback: maybe it has account_id even though we expected a different col
    if account_col != "account_id" and _pg_col_exists(conn, table, "account_id"):
        return "account_id = ANY(:ids)", {"ids": ids}

    # Indirect join via entity column (adset_id / campaign_id / ad_id)
    both = _both_id_forms(account_ids)
    for entity_col, dim_table, dim_entity_col in _ENTITY_JOIN:
        if not _pg_col_exists(conn, table, entity_col):
            continue
        if not _pg_table_exists(conn, dim_table):
            continue
        if not _pg_col_exists(conn, dim_table, "account_id"):
            continue
        where = (
            f'"{entity_col}" IN ('
            f'  SELECT "{dim_entity_col}" FROM "{dim_table}"'
            f'  WHERE account_id = ANY(:ids)'
            f')'
        )
        return where, {"ids": both}

    return None


def _delete_from_postgres(
    account_ids: list[str],
    db_config,
    dry_run: bool,
) -> dict[str, int]:
    engine = create_engine(db_config.conn_string)
    results: dict[str, int] = {}

    with engine.begin() as conn:
        for table in _ALL_TABLES:
            if not _pg_table_exists(conn, table):
                continue

            resolution = _resolve_pg_where(conn, table, account_ids)
            if resolution is None:
                logger.debug("Skipping table: no account link found", table=table)
                continue

            where_clause, params = resolution
            quoted = f'"{table}"'

            if dry_run:
                row = conn.execute(
                    text(f"SELECT COUNT(*) FROM {quoted} WHERE {where_clause}"),
                    params,
                ).scalar()
                count = int(row or 0)
                results[table] = count
                if count:
                    logger.info("DRY RUN: would delete rows", target="postgres", table=table, row_count=count)
            else:
                result = conn.execute(
                    text(f"DELETE FROM {quoted} WHERE {where_clause}"),
                    params,
                )
                count = result.rowcount
                results[table] = count
                if count:
                    logger.info("Deleted rows", target="postgres", table=table, row_count=count)

    return results


def _bq_col_exists(bq_table, column: str) -> bool:
    return any(field.name == column for field in bq_table.schema)


def _resolve_bq_where(
    client,
    table_id: str,
    table_name: str,
    project_id: str,
    dataset_id: str,
    ids_literal: str,
    ids_literal_both: str = "",
) -> str | None:
    """
    Return a WHERE clause string for BigQuery deletion, or None if not resolvable.
    ids_literal is already formatted as a SQL IN-list: "'id1', 'id2', ..."
    """
    from src.etl.load.bigquery_loader import _table_exists

    bq_table = client.get_table(table_id)
    col_names = {field.name for field in bq_table.schema}

    account_col = _ACCOUNT_COL_OVERRIDES.get(table_name, "account_id")

    # Direct account column
    if account_col in col_names:
        return f"{account_col} IN ({ids_literal})"

    if account_col != "account_id" and "account_id" in col_names:
        return f"account_id IN ({ids_literal})"

    # Indirect join via entity column
    for entity_col, dim_table, dim_entity_col in _ENTITY_JOIN:
        if entity_col not in col_names:
            continue
        dim_table_id = f"{project_id}.{dataset_id}.{dim_table}"
        if not _table_exists(client, dim_table_id):
            continue
        bq_dim = client.get_table(dim_table_id)
        dim_col_names = {field.name for field in bq_dim.schema}
        if "account_id" not in dim_col_names:
            continue
        join_ids = ids_literal_both if ids_literal_both else ids_literal
        return (
            f"`{entity_col}` IN ("
            f"  SELECT `{dim_entity_col}` FROM `{dim_table_id}`"
            f"  WHERE account_id IN ({join_ids})"
            f")"
        )

    return None


def _delete_from_bigquery(
    account_ids: list[str],
    profile: str | None,
    dry_run: bool,
) -> dict[str, int]:
    from src.config import load_bigquery_config
    from src.etl.load.bigquery_loader import _build_client, _table_exists

    cfg = load_bigquery_config(profile)
    client = _build_client(
        cfg.project_id,
        cfg.credentials_path,
        cfg.impersonate_service_account,
    )

    ids_literal = ", ".join(f"'{aid}'" for aid in account_ids)
    ids_literal_both = ", ".join(f"'{aid}'" for aid in _both_id_forms(account_ids))
    results: dict[str, int] = {}

    for table in _ALL_TABLES:
        table_id = f"{cfg.project_id}.{cfg.dataset_id}.{table}"
        if not _table_exists(client, table_id):
            continue

        # dim_meta_accounts.id always uses the 'act_' form; other tables may not.
        is_override = table in _ACCOUNT_COL_OVERRIDES
        effective_ids_literal = ids_literal if is_override else ids_literal_both

        where_clause = _resolve_bq_where(
            client, table_id, table, cfg.project_id, cfg.dataset_id,
            effective_ids_literal, ids_literal_both,
        )
        if where_clause is None:
            logger.debug("Skipping BQ table: no account link found", table=table)
            continue

        if dry_run:
            job = client.query(
                f"SELECT COUNT(*) FROM `{table_id}` WHERE {where_clause}"
            )
            count = int(list(job.result())[0][0])
            results[table] = count
            if count:
                logger.info("DRY RUN: would delete rows", target="bigquery", table=table, row_count=count)
        else:
            job = client.query(
                f"DELETE FROM `{table_id}` WHERE {where_clause}"
            )
            job.result()
            count = job.num_dml_affected_rows or 0
            results[table] = count
            if count:
                logger.info("Deleted rows", target="bigquery", table=table, row_count=count)

    return results


def run_delete_account_data(
    csv_path: str = "data/delete_accounts_template.csv",
    dry_run: bool = False,
    yes: bool = False,
    also_bigquery: bool = False,
    db_config=None,
    profile: str | None = None,
) -> None:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Template CSV not found: {csv_path}")

    targets = _load_delete_targets(str(path))
    if not targets:
        logger.info("No accounts marked for deletion (delete=TRUE), nothing to do")
        return

    account_ids = [aid for aid, _ in targets]

    logger.info(
        "Accounts selected for deletion",
        dry_run=dry_run,
        count=len(targets),
        accounts=[{"id": aid, "name": name} for aid, name in targets],
    )

    if not dry_run and not yes:
        logger.info(
            "Preview only, no changes made; re-run with --yes to execute"
            " or --dry-run to see exact row counts first"
        )
        return

    if db_config is None:
        db_config = load_postgres_config(profile)

    pg_results = _delete_from_postgres(account_ids, db_config, dry_run)
    pg_total = sum(v for v in pg_results.values() if v > 0)
    logger.info(
        "PostgreSQL deletion complete",
        dry_run=dry_run,
        total_rows=pg_total,
    )

    if also_bigquery:
        try:
            bq_results = _delete_from_bigquery(account_ids, profile, dry_run)
            bq_total = sum(v for v in bq_results.values() if v > 0)
            logger.info(
                "BigQuery deletion complete",
                dry_run=dry_run,
                total_rows=bq_total,
            )
        except Exception as exc:
            logger.exception("BigQuery deletion failed", error=str(exc))
            raise

    logger.info("Delete-account-data done")
