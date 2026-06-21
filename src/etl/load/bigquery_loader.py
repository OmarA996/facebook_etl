from __future__ import annotations

import datetime as _dt
import json
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Sequence

import google.auth
import pandas as pd
from google.api_core.exceptions import NotFound
from google.auth import impersonated_credentials
from google.cloud import bigquery
from google.oauth2 import service_account

from src.config import load_bigquery_config
from src.schema.bigquery import get_declared_bigquery_schema, get_declared_bigquery_type_map
from src.schema.views import BQ_REQUIRED_TABLES, STATIC_FACT_COLUMNS, VIEW_NAME, bigquery_view_sql
from src.utils.names import normalize_column_name
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _normalize_bq_column(col: str) -> str:
    if col is None:
        return col
    col = normalize_column_name(col, max_len=300)
    col = re.sub(r"[^a-z0-9_]", "_", col)
    if not col:
        col = "col"
    if not re.match(r"^[a-z_]", col):
        col = f"_{col}"
    return col


def _collapse_duplicate_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    duplicates: dict[str, list[int]] = {}
    for idx, col in enumerate(df.columns):
        duplicates.setdefault(col, []).append(idx)
    for col, idxs in duplicates.items():
        if len(idxs) <= 1:
            continue
        dup_df = df.iloc[:, idxs]
        merged = dup_df.bfill(axis=1).iloc[:, 0]
        df.drop(columns=dup_df.columns, inplace=True)
        df[col] = merged
    return df


def _serialize_cell_for_bigquery(value: Any) -> Any:
    if isinstance(value, set):
        value = sorted(value)
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def _coerce_to_bool(value: Any) -> Any:
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    lowered = str(value).strip().lower()
    if lowered in {"true", "t", "1", "yes", "y"}:
        return True
    if lowered in {"false", "f", "0", "no", "n"}:
        return False
    return None


def _coerce_series_to_declared_type(series: pd.Series, field_type: str) -> pd.Series:
    field_type = field_type.upper()
    if field_type == "DATE":
        parsed = pd.to_datetime(series, errors="coerce")
        return pd.Series(
            [value.date() if pd.notna(value) else None for value in parsed],
            index=series.index,
            dtype=object,
        )

    if field_type == "TIMESTAMP":
        return pd.to_datetime(series, errors="coerce", utc=True)

    if field_type == "STRING":
        return pd.Series(
            [None if pd.isna(value) else str(value) for value in series],
            index=series.index,
            dtype=object,
        )

    if field_type == "INT64":
        numeric = pd.to_numeric(series, errors="coerce")
        return numeric.astype("Int64")

    if field_type in {"NUMERIC", "BIGNUMERIC"}:
        coerced: list[Any] = []
        for value in series:
            try:
                if pd.isna(value):
                    coerced.append(None)
                    continue
            except Exception:
                pass
            try:
                coerced.append(Decimal(str(value)))
            except (InvalidOperation, ValueError):
                coerced.append(None)
        return pd.Series(coerced, index=series.index, dtype=object)

    if field_type == "BOOL":
        return pd.Series([_coerce_to_bool(value) for value in series], index=series.index, dtype=object)

    return series


def _sanitize_python_date_objects(df: pd.DataFrame) -> pd.DataFrame:
    """Convert object columns holding Python date/datetime values to ISO strings.

    pd.read_sql returns DATE columns as Python datetime.date objects in object-dtype
    Series. pyarrow cannot convert those to STRING bytes, so we stringify them first.
    """
    for col in df.columns:
        if df[col].dtype != object:
            continue
        non_null = df[col].dropna()
        if non_null.empty:
            continue
        sample = non_null.iloc[0]
        if isinstance(sample, _dt.datetime):
            df[col] = df[col].apply(
                lambda x: x.isoformat() if isinstance(x, _dt.datetime) else (None if pd.isna(x) else x)
            )
        elif isinstance(sample, _dt.date):
            df[col] = df[col].apply(
                lambda x: x.isoformat() if isinstance(x, _dt.date) else (None if pd.isna(x) else x)
            )
    return df


def _prepare_df_for_bigquery(
    df: pd.DataFrame,
    *,
    table_name: str,
    normalize_columns: bool,
    serialize_complex_types: bool,
    partition_field: str | None,
) -> pd.DataFrame:
    prepared = df.copy()
    prepared = _sanitize_python_date_objects(prepared)
    if normalize_columns:
        prepared.columns = [_normalize_bq_column(c) for c in prepared.columns]
        prepared = _collapse_duplicate_columns(prepared)

    declared_types = get_declared_bigquery_type_map(table_name)
    if declared_types:
        # For truncated/materialized tables the DataFrame IS the schema — never add phantom
        # NULL columns. For append/merge tables, add missing declared columns so the BQ
        # schema stays stable across batches where optional fields may be absent.
        if table_name != "fact_meta_ads_combined":
            for column_name in declared_types:
                if column_name not in prepared.columns:
                    prepared[column_name] = None

    normalized_partition_field = _normalize_bq_column(partition_field) if partition_field else None
    if serialize_complex_types and not prepared.empty:
        for col in prepared.columns:
            series = prepared[col]
            if not series.apply(lambda x: isinstance(x, (dict, list, tuple, set))).any():
                continue
            prepared[col] = series.apply(_serialize_cell_for_bigquery)

    for column_name, field_type in declared_types.items():
        if column_name not in prepared.columns:
            continue
        prepared[column_name] = _coerce_series_to_declared_type(prepared[column_name], field_type)

    if normalized_partition_field and normalized_partition_field in prepared.columns and normalized_partition_field not in declared_types:
        series = prepared[normalized_partition_field]
        non_null = series.dropna()
        if not non_null.empty and not pd.api.types.is_datetime64_any_dtype(series):
            parsed = pd.to_datetime(non_null, errors="coerce")
            if parsed.notna().all():
                full_parsed = pd.to_datetime(series, errors="coerce")
                prepared[normalized_partition_field] = [
                    value.date() if pd.notna(value) else None
                    for value in full_parsed
                ]

    return prepared


def _infer_bq_type_from_dtype(series: pd.Series) -> str:
    """Infer a BigQuery field type from a pandas Series dtype."""
    dtype = series.dtype
    if pd.api.types.is_bool_dtype(dtype):
        return "BOOL"
    if pd.api.types.is_integer_dtype(dtype):
        return "INT64"
    if pd.api.types.is_float_dtype(dtype):
        return "FLOAT64"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "TIMESTAMP"
    return "STRING"


def _build_full_schema_for_df(df: pd.DataFrame, table_name: str) -> list[bigquery.SchemaField]:
    """Build a BQ schema covering every column in df.

    Uses declared types where known; falls back to dtype inference so numeric/date
    columns are never mislabelled as STRING.
    """
    declared_types = get_declared_bigquery_type_map(table_name)
    return [
        bigquery.SchemaField(col, declared_types.get(col) or _infer_bq_type_from_dtype(df[col]))
        for col in df.columns
    ]


def _normalize_merge_keys(merge_keys: Sequence[str] | None) -> list[str]:
    if not merge_keys:
        return []
    return [_normalize_bq_column(key) for key in merge_keys]


def _validate_incoming_merge_keys(columns: Sequence[str], merge_keys: Sequence[str]) -> None:
    missing = [key for key in merge_keys if key not in columns]
    if missing:
        raise ValueError(f"[bigquery_loader] Missing merge key columns: {missing}")


def _validate_merge_keys(df: pd.DataFrame, merge_keys: Sequence[str]) -> None:
    null_keys = [key for key in merge_keys if df[key].isna().any()]
    if null_keys:
        raise ValueError(f"[bigquery_loader] Merge key columns contain null values: {null_keys}")


def _dedupe_merge_rows(df: pd.DataFrame, merge_keys: Sequence[str]) -> pd.DataFrame:
    dup_mask = df.duplicated(subset=list(merge_keys), keep="last")
    dup_count = int(dup_mask.sum())
    if dup_count:
        logger.info("Dropping duplicate rows before merge load", count=dup_count, merge_keys=list(merge_keys))
        return df.loc[~dup_mask].copy()
    return df


def _build_client(
    project_id: str | None,
    credentials_path: str | None,
    impersonate_service_account: str | None = None,
) -> bigquery.Client:
    if credentials_path:
        creds = service_account.Credentials.from_service_account_file(credentials_path)
        return bigquery.Client(project=project_id, credentials=creds)

    if impersonate_service_account:
        source_credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        impersonated_creds = impersonated_credentials.Credentials(
            source_credentials=source_credentials,
            target_principal=impersonate_service_account,
            target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
            lifetime=3600,
        )
        return bigquery.Client(project=project_id, credentials=impersonated_creds)

    return bigquery.Client(project=project_id)


def _ensure_dataset(
    client: bigquery.Client,
    project_id: str,
    dataset_id: str,
    location: str | None,
) -> None:
    dataset_ref = bigquery.Dataset(f"{project_id}.{dataset_id}")
    try:
        client.get_dataset(dataset_ref)
        return
    except NotFound:
        if not location:
            raise ValueError(
                "[bigquery_loader] Dataset does not exist and no location was provided to create it."
            )
        dataset_ref.location = location
        client.create_dataset(dataset_ref, exists_ok=True)


def _load_table_from_df(
    client: bigquery.Client,
    df: pd.DataFrame,
    table_id: str,
    *,
    table_name: str,
    write_disposition: str,
    create_disposition: str,
    partition_field: str | None = None,
    cluster_fields: Sequence[str] | None = None,
) -> None:
    job_config = bigquery.LoadJobConfig(
        write_disposition=write_disposition,
        create_disposition=create_disposition,
    )

    if partition_field:
        job_config.time_partitioning = bigquery.TimePartitioning(field=partition_field)

    if cluster_fields:
        job_config.clustering_fields = list(cluster_fields)

    job_config.schema = _build_full_schema_for_df(df, table_name)

    load_job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
    load_job.result()


def _table_exists(client: bigquery.Client, table_id: str) -> bool:
    try:
        client.get_table(table_id)
        return True
    except NotFound:
        return False


def _build_staging_table_id(project_id: str, dataset_id: str, table_name: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"{project_id}.{dataset_id}._{table_name}__staging_{timestamp}_{suffix}"


def _create_table_with_schema(
    client: bigquery.Client,
    *,
    table_id: str,
    table_name: str,
    partition_field: str | None = None,
    cluster_fields: Sequence[str] | None = None,
) -> bool:
    declared_schema = get_declared_bigquery_schema(table_name)
    if not declared_schema:
        return False

    table = bigquery.Table(table_id, schema=declared_schema)
    if partition_field:
        table.time_partitioning = bigquery.TimePartitioning(field=partition_field)
    if cluster_fields:
        table.clustering_fields = list(cluster_fields)
    client.create_table(table, exists_ok=True)
    return True


def _warn_if_declared_schema_differs(
    client: bigquery.Client,
    *,
    table_id: str,
    table_name: str,
) -> None:
    declared_types = get_declared_bigquery_type_map(table_name)
    if not declared_types:
        return

    actual_types = {
        field.name: field.field_type.upper()
        for field in client.get_table(table_id).schema
    }
    mismatches = [
        f"{column_name}: expected {declared_types[column_name]}, found {actual_types[column_name]}"
        for column_name in declared_types
        if column_name in actual_types and actual_types[column_name] != declared_types[column_name]
    ]
    if mismatches:
        logger.warning("BigQuery schema differs from declared schema", table=table_name, mismatches=mismatches)


def _sync_missing_columns(
    client: bigquery.Client,
    final_table_id: str,
    staging_table_id: str,
) -> None:
    final_table = client.get_table(final_table_id)
    staging_table = client.get_table(staging_table_id)

    existing = {field.name for field in final_table.schema}
    missing = [field for field in staging_table.schema if field.name not in existing]
    if not missing:
        return

    final_table.schema = list(final_table.schema) + missing
    client.update_table(final_table, ["schema"])


def _source_expr(column: str, field_types: dict[str, str]) -> str:
    field_type = field_types.get(column, "").upper()
    if not field_type:
        return f"S.{column}"

    cast_types = {
        "STRING",
        "INT64",
        "INTEGER",
        "FLOAT64",
        "NUMERIC",
        "BIGNUMERIC",
        "BOOL",
        "BOOLEAN",
        "DATE",
        "DATETIME",
        "TIMESTAMP",
        "TIME",
        "JSON",
    }
    if field_type not in cast_types:
        return f"S.{column}"

    target_type = "INT64" if field_type == "INTEGER" else "BOOL" if field_type == "BOOLEAN" else field_type
    return f"CAST(S.{column} AS {target_type})"


def _build_merge_sql(
    *,
    final_table_id: str,
    staging_table_id: str,
    columns: Sequence[str],
    merge_keys: Sequence[str],
    field_types: dict[str, str],
) -> str:
    on_clause = " AND ".join([f"T.{col} = S.{col}" for col in merge_keys])
    insert_columns = ", ".join(columns)
    insert_values = ", ".join([_source_expr(col, field_types) for col in columns])

    non_key_columns = [col for col in columns if col not in set(merge_keys)]
    statements = [
        f"MERGE `{final_table_id}` T",
        f"USING `{staging_table_id}` S",
        f"ON {on_clause}",
    ]

    if non_key_columns:
        update_clause = ", ".join([f"{col} = {_source_expr(col, field_types)}" for col in non_key_columns])
        statements.append(f"WHEN MATCHED THEN UPDATE SET {update_clause}")

    statements.append(
        f"WHEN NOT MATCHED THEN INSERT ({insert_columns}) VALUES ({insert_values})"
    )
    return "\n".join(statements)


def _merge_df_to_bigquery(
    *,
    client: bigquery.Client,
    df: pd.DataFrame,
    project_id: str,
    dataset_id: str,
    table_name: str,
    merge_keys: Sequence[str],
    create_disposition: str,
    partition_field: str | None,
    cluster_fields: Sequence[str] | None,
    require_existing_table: bool = False,
) -> None:
    final_table_id = f"{project_id}.{dataset_id}.{table_name}"
    if not _table_exists(client, final_table_id):
        if require_existing_table:
            raise ValueError(f"[bigquery_loader] Target BigQuery table does not exist: {final_table_id}")
        if _create_table_with_schema(
            client,
            table_id=final_table_id,
            table_name=table_name,
            partition_field=partition_field,
            cluster_fields=cluster_fields,
        ):
            logger.info("Created BigQuery table from declared schema", table_id=final_table_id)
        else:
            _load_table_from_df(
                client,
                df,
                final_table_id,
                table_name=table_name,
                write_disposition="WRITE_APPEND",
                create_disposition=create_disposition,
                partition_field=partition_field,
                cluster_fields=cluster_fields,
            )
            logger.info("Loaded rows into BigQuery", table_id=final_table_id, rows=len(df))
            return

    _warn_if_declared_schema_differs(client, table_id=final_table_id, table_name=table_name)
    staging_table_id = _build_staging_table_id(project_id, dataset_id, table_name)
    try:
        _load_table_from_df(
            client,
            df,
            staging_table_id,
            table_name=table_name,
            write_disposition="WRITE_TRUNCATE",
            create_disposition="CREATE_IF_NEEDED",
        )
        _sync_missing_columns(client, final_table_id, staging_table_id)
        final_field_types = {
            field.name: field.field_type
            for field in client.get_table(final_table_id).schema
        }
        merge_sql = _build_merge_sql(
            final_table_id=final_table_id,
            staging_table_id=staging_table_id,
            columns=list(df.columns),
            merge_keys=merge_keys,
            field_types=final_field_types,
        )
        client.query(merge_sql).result()
        logger.info("Merged rows into BigQuery", table_id=final_table_id, rows=len(df))
    finally:
        try:
            client.delete_table(staging_table_id, not_found_ok=True)
        except Exception:
            pass


def save_df_to_bigquery(
    df: pd.DataFrame,
    table_name: str,
    profile: str | None = None,
    dataset_id: str | None = None,
    project_id: str | None = None,
    credentials_path: str | None = None,
    impersonate_service_account: str | None = None,
    location: str | None = None,
    write_disposition: str = "WRITE_APPEND",
    create_disposition: str = "CREATE_IF_NEEDED",
    partition_field: str | None = None,
    cluster_fields: Sequence[str] | None = None,
    normalize_columns: bool = True,
    merge_keys: Sequence[str] | None = None,
    serialize_complex_types: bool = True,
    require_existing_table: bool = False,
) -> None:
    """
    Load a DataFrame into a BigQuery table.

    write_disposition: WRITE_APPEND (default), WRITE_TRUNCATE, or WRITE_EMPTY.
    """
    if df.empty:
        logger.info("DataFrame is empty, nothing to load", table=table_name)
        return

    if not project_id or not dataset_id:
        try:
            cfg = load_bigquery_config(profile)
            project_id = project_id or cfg.project_id
            dataset_id = dataset_id or cfg.dataset_id
            if credentials_path is None:
                credentials_path = cfg.credentials_path
            if impersonate_service_account is None:
                impersonate_service_account = cfg.impersonate_service_account
            if location is None:
                location = cfg.location
        except Exception as exc:
            logger.error("No BigQuery config available", error=str(exc))
            return
    else:
        if (
            credentials_path is None
            or impersonate_service_account is None
            or location is None
        ):
            try:
                cfg = load_bigquery_config(profile)
                if credentials_path is None:
                    credentials_path = cfg.credentials_path
                if impersonate_service_account is None:
                    impersonate_service_account = cfg.impersonate_service_account
                if location is None:
                    location = cfg.location
            except Exception:
                pass

    if not project_id or not dataset_id:
        logger.error("Missing BigQuery project_id or dataset_id")
        return

    normalized_merge_keys = _normalize_merge_keys(merge_keys)
    if normalized_merge_keys:
        incoming_columns = [_normalize_bq_column(c) for c in df.columns] if normalize_columns else list(df.columns)
        _validate_incoming_merge_keys(incoming_columns, normalized_merge_keys)

    df = _prepare_df_for_bigquery(
        df,
        table_name=table_name,
        normalize_columns=normalize_columns,
        serialize_complex_types=serialize_complex_types,
        partition_field=partition_field,
    )

    if normalized_merge_keys:
        _validate_merge_keys(df, normalized_merge_keys)
        df = _dedupe_merge_rows(df, normalized_merge_keys)

    client = _build_client(
        project_id,
        credentials_path,
        impersonate_service_account=impersonate_service_account,
    )
    table_id = f"{project_id}.{dataset_id}.{table_name}"
    if require_existing_table:
        if not _table_exists(client, table_id):
            raise ValueError(f"[bigquery_loader] Target BigQuery table does not exist: {table_id}")
    else:
        _ensure_dataset(client, project_id, dataset_id, location)
    if normalized_merge_keys and write_disposition == "WRITE_APPEND":
        _merge_df_to_bigquery(
            client=client,
            df=df,
            project_id=project_id,
            dataset_id=dataset_id,
            table_name=table_name,
            merge_keys=normalized_merge_keys,
            create_disposition=create_disposition,
            partition_field=partition_field,
            cluster_fields=cluster_fields,
            require_existing_table=require_existing_table,
        )
        return

    _load_table_from_df(
        client,
        df,
        table_id,
        table_name=table_name,
        write_disposition=write_disposition,
        create_disposition="CREATE_NEVER" if require_existing_table else create_disposition,
        partition_field=partition_field,
        cluster_fields=cluster_fields,
    )

    logger.info("Loaded rows into BigQuery", table_id=table_id, rows=len(df))


def bigquery_table_exists(
    table_name: str,
    profile: str | None = None,
    dataset_id: str | None = None,
    project_id: str | None = None,
    credentials_path: str | None = None,
    impersonate_service_account: str | None = None,
) -> bool:
    if not project_id or not dataset_id:
        try:
            cfg = load_bigquery_config(profile)
            project_id = project_id or cfg.project_id
            dataset_id = dataset_id or cfg.dataset_id
            if credentials_path is None:
                credentials_path = cfg.credentials_path
            if impersonate_service_account is None:
                impersonate_service_account = cfg.impersonate_service_account
        except Exception as exc:
            logger.error("No BigQuery config available", error=str(exc))
            return False

    if not project_id or not dataset_id:
        logger.error("Missing BigQuery project_id or dataset_id")
        return False

    client = _build_client(
        project_id,
        credentials_path,
        impersonate_service_account=impersonate_service_account,
    )
    table_id = f"{project_id}.{dataset_id}.{table_name}"
    return _table_exists(client, table_id)


def truncate_table(
    table_name: str,
    profile: str | None = None,
    dataset_id: str | None = None,
    project_id: str | None = None,
    credentials_path: str | None = None,
    impersonate_service_account: str | None = None,
) -> None:
    if not project_id or not dataset_id:
        try:
            cfg = load_bigquery_config(profile)
            project_id = project_id or cfg.project_id
            dataset_id = dataset_id or cfg.dataset_id
            if credentials_path is None:
                credentials_path = cfg.credentials_path
            if impersonate_service_account is None:
                impersonate_service_account = cfg.impersonate_service_account
        except Exception as exc:
            logger.error("No BigQuery config available", error=str(exc))
            return

    if not project_id or not dataset_id:
        logger.error("Missing BigQuery project_id or dataset_id")
        return

    client = _build_client(
        project_id,
        credentials_path,
        impersonate_service_account=impersonate_service_account,
    )
    table_id = f"{project_id}.{dataset_id}.{table_name}"
    if not _table_exists(client, table_id):
        raise ValueError(f"[bigquery_loader] Target BigQuery table does not exist: {table_id}")
    client.query(f"TRUNCATE TABLE `{table_id}`").result()
    logger.info("Truncated BigQuery table", table_id=table_id)


def delete_table(
    table_name: str,
    profile: str | None = None,
    dataset_id: str | None = None,
    project_id: str | None = None,
    credentials_path: str | None = None,
    impersonate_service_account: str | None = None,
) -> None:
    if not project_id or not dataset_id:
        try:
            cfg = load_bigquery_config(profile)
            project_id = project_id or cfg.project_id
            dataset_id = dataset_id or cfg.dataset_id
            if credentials_path is None:
                credentials_path = cfg.credentials_path
            if impersonate_service_account is None:
                impersonate_service_account = cfg.impersonate_service_account
        except Exception as exc:
            logger.error("No BigQuery config available", error=str(exc))
            return
    else:
        if credentials_path is None or impersonate_service_account is None:
            try:
                cfg = load_bigquery_config(profile)
                if credentials_path is None:
                    credentials_path = cfg.credentials_path
                if impersonate_service_account is None:
                    impersonate_service_account = cfg.impersonate_service_account
            except Exception:
                pass

    if not project_id or not dataset_id:
        logger.error("Missing BigQuery project_id or dataset_id")
        return

    client = _build_client(
        project_id,
        credentials_path,
        impersonate_service_account=impersonate_service_account,
    )
    table_id = f"{project_id}.{dataset_id}.{table_name}"
    client.delete_table(table_id, not_found_ok=True)
    logger.info("Deleted BigQuery table", table_id=table_id)


def ensure_bigquery_views(
    profile: str | None = None,
    project_id: str | None = None,
    dataset_id: str | None = None,
    credentials_path: str | None = None,
    impersonate_service_account: str | None = None,
) -> None:
    if not project_id or not dataset_id:
        try:
            cfg = load_bigquery_config(profile)
            project_id = project_id or cfg.project_id
            dataset_id = dataset_id or cfg.dataset_id
            if credentials_path is None:
                credentials_path = cfg.credentials_path
            if impersonate_service_account is None:
                impersonate_service_account = cfg.impersonate_service_account
        except Exception as exc:
            logger.error("No BigQuery config available", error=str(exc))
            return

    if not project_id or not dataset_id:
        logger.error("Missing BigQuery project_id or dataset_id")
        return

    client = _build_client(project_id, credentials_path, impersonate_service_account)

    existing = {t.table_id for t in client.list_tables(f"{project_id}.{dataset_id}")}
    missing = BQ_REQUIRED_TABLES - existing
    if missing:
        logger.warning("Skipping view creation: missing required tables", view=VIEW_NAME, missing_tables=sorted(missing))
        return

    fact_table_id = f"{project_id}.{dataset_id}.fact_meta_delivery_ad"
    all_fact_cols = {field.name for field in client.get_table(fact_table_id).schema}
    extra = sorted(all_fact_cols - STATIC_FACT_COLUMNS)

    existing_dim_cols: dict[str, set[str]] = {}
    for tbl in ("dim_meta_accounts", "dim_meta_ads", "dim_meta_creatives"):
        tbl_id = f"{project_id}.{dataset_id}.{tbl}"
        try:
            existing_dim_cols[tbl] = {field.name for field in client.get_table(tbl_id).schema}
        except NotFound:
            pass

    view_id = f"{project_id}.{dataset_id}.{VIEW_NAME}"
    sql = bigquery_view_sql(project_id, dataset_id, extra_fact_columns=extra, existing_dim_cols=existing_dim_cols)
    try:
        existing_view = client.get_table(view_id)
        existing_view.view_query = sql
        client.update_table(existing_view, ["view_query"])
        logger.info("Updated BigQuery view", view_id=view_id)
    except NotFound:
        view = bigquery.Table(view_id)
        view.view_query = sql
        client.create_table(view)
        logger.info("Created BigQuery view", view_id=view_id)


def create_or_update_bq_view(
    view_name: str,
    sql: str,
    project_id: str | None = None,
    dataset_id: str | None = None,
    profile: str | None = None,
    credentials_path: str | None = None,
    impersonate_service_account: str | None = None,
) -> None:
    if not project_id or not dataset_id:
        try:
            cfg = load_bigquery_config(profile)
            project_id = project_id or cfg.project_id
            dataset_id = dataset_id or cfg.dataset_id
            credentials_path = credentials_path or cfg.credentials_path
            impersonate_service_account = impersonate_service_account or cfg.impersonate_service_account
        except Exception as exc:
            logger.error("No BigQuery config for view creation", error=str(exc))
            return

    client = _build_client(project_id, credentials_path, impersonate_service_account)
    view_id = f"{project_id}.{dataset_id}.{view_name}"
    try:
        existing = client.get_table(view_id)
        existing.view_query = sql
        client.update_table(existing, ["view_query"])
        logger.info("Updated BigQuery view", view_id=view_id)
    except NotFound:
        view = bigquery.Table(view_id)
        view.view_query = sql
        client.create_table(view)
        logger.info("Created BigQuery view", view_id=view_id)


def list_tables(
    profile: str | None = None,
    dataset_id: str | None = None,
    project_id: str | None = None,
    credentials_path: str | None = None,
    impersonate_service_account: str | None = None,
) -> list[str]:
    if not project_id or not dataset_id:
        try:
            cfg = load_bigquery_config(profile)
            project_id = project_id or cfg.project_id
            dataset_id = dataset_id or cfg.dataset_id
            if credentials_path is None:
                credentials_path = cfg.credentials_path
            if impersonate_service_account is None:
                impersonate_service_account = cfg.impersonate_service_account
        except Exception as exc:
            logger.error("No BigQuery config available", error=str(exc))
            return []
    else:
        if credentials_path is None or impersonate_service_account is None:
            try:
                cfg = load_bigquery_config(profile)
                if credentials_path is None:
                    credentials_path = cfg.credentials_path
                if impersonate_service_account is None:
                    impersonate_service_account = cfg.impersonate_service_account
            except Exception:
                pass

    if not project_id or not dataset_id:
        logger.error("Missing BigQuery project_id or dataset_id")
        return []

    client = _build_client(
        project_id,
        credentials_path,
        impersonate_service_account=impersonate_service_account,
    )
    dataset_ref = bigquery.Dataset(f"{project_id}.{dataset_id}")
    tables = client.list_tables(dataset_ref)
    return [t.table_id for t in tables]
