from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Optional

from src.config import PostgresConfig, load_ad_account_ids
from src.utils.logger import get_logger

logger = get_logger(__name__)

_Result = tuple[str, bool, float]  # (step_name, success, elapsed_seconds)


def _step(name: str, fn, *args, **kwargs) -> _Result:
    """Run one pipeline step. Returns (name, success, elapsed_seconds). Never raises."""
    start = time.time()
    try:
        fn(*args, **kwargs)
        elapsed = time.time() - start
        logger.info("Step completed", step=name, elapsed_s=round(elapsed, 1), status="OK")
        return name, True, elapsed
    except Exception as exc:
        elapsed = time.time() - start
        logger.error("Step failed", step=name, elapsed_s=round(elapsed, 1), error=str(exc), exc_info=True)
        return name, False, elapsed


def _log_summary(results: list[_Result]) -> None:
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    total_time = sum(t for _, _, t in results)
    logger.info(
        "Pipeline summary",
        passed=passed,
        total=total,
        total_s=round(total_time, 1),
        all_ok=(passed == total),
        steps=[
            {"step": name, "status": "OK" if ok else "FAIL", "elapsed_s": round(t, 1)}
            for name, ok, t in results
        ],
    )


def run_daily(
    days_back: int = 7,
    level: str = "ad",
    breakdowns: list[str] | None = None,
    skip_dims: bool = False,
    to_db: bool = True,
    to_bigquery: bool = False,
    bq_write_disposition: str = "WRITE_APPEND",
    max_workers: int = 1,
    db_config: Optional[PostgresConfig] = None,
    profile: Optional[str] = None,
) -> None:
    from src.etl.pipelines.accounts_info import run_accounts_info
    from src.etl.pipelines.campaigns_info import run_campaigns_info
    from src.etl.pipelines.adsets_info import run_adsets_info
    from src.etl.pipelines.ads_info import run_ads_info
    from src.etl.pipelines.creatives_info import run_creatives_info
    from src.etl.pipelines.meta_insights_range import run_meta_insights_range
    from src.etl.pipelines.sync_to_bigquery import run_sync_to_bigquery

    today = date.today()
    to_date = (today - timedelta(days=1)).isoformat()
    from_date = (today - timedelta(days=days_back)).isoformat()

    ad_account_ids = load_ad_account_ids(profile)
    results: list[_Result] = []

    logger.info(
        "Daily run started",
        from_date=from_date,
        to_date=to_date,
        level=level,
        workers=max_workers,
    )

    if not skip_dims:
        results.append(_step(
            "accounts-info", run_accounts_info,
            profile=profile, to_db=to_db,
            to_bigquery=to_bigquery, bq_write_disposition=bq_write_disposition,
            db_config=db_config,
        ))
        for name, fn in [
            ("campaigns-info", run_campaigns_info),
            ("adsets-info",    run_adsets_info),
            ("ads-info",       run_ads_info),
        ]:
            results.append(_step(
                name, fn,
                to_db=to_db, db_config=db_config,
                ad_account_ids=ad_account_ids, max_workers=max_workers,
            ))
        results.append(_step(
            "creatives-info", run_creatives_info,
            to_db=to_db, db_config=db_config,
            ad_account_ids=ad_account_ids, max_workers=max_workers,
        ))

    results.append(_step(
        f"insights-range ({from_date} to {to_date})", run_meta_insights_range,
        level=level, from_date=from_date, to_date=to_date,
        chunk_size_days=days_back, breakdowns=breakdowns,
        profile=profile, to_db=to_db,
        to_bigquery=to_bigquery, bq_write_disposition=bq_write_disposition,
        csv_path=None, db_config=db_config,
        ad_account_ids=ad_account_ids, max_workers=max_workers,
    ))

    if to_bigquery and to_db and db_config:
        results.append(_step(
            "sync-to-bigquery all", run_sync_to_bigquery,
            table_names=["all"], db_config=db_config, profile=profile,
        ))
        from src.etl.pipelines.materialize_combined import run_materialize_combined
        results.append(_step(
            "materialize-combined", run_materialize_combined,
            db_config=db_config, to_bigquery=True, profile=profile,
        ))

    _log_summary(results)


def run_accounts_insights(
    days_back: int = 7,
    level: str = "ad",
    breakdowns: list[str] | None = None,
    to_db: bool = True,
    to_bigquery: bool = False,
    max_workers: int = 1,
    db_config: Optional[PostgresConfig] = None,
    profile: Optional[str] = None,
) -> None:
    """Lightweight 2-hour refresh: accounts metadata + rolling insights window."""
    from src.etl.pipelines.accounts_info import run_accounts_info
    from src.etl.pipelines.meta_insights_range import run_meta_insights_range
    from src.etl.pipelines.sync_to_bigquery import run_sync_to_bigquery

    today = date.today()
    to_date   = today.isoformat()
    from_date = (today - timedelta(days=days_back)).isoformat()

    ad_account_ids = load_ad_account_ids(profile)
    results: list[_Result] = []

    logger.info("Accounts + insights run started", from_date=from_date, to_date=to_date, level=level)

    results.append(_step(
        "accounts-info", run_accounts_info,
        profile=profile, to_db=to_db, db_config=db_config,
    ))

    results.append(_step(
        f"insights-range ({from_date} to {to_date})", run_meta_insights_range,
        level=level, from_date=from_date, to_date=to_date,
        chunk_size_days=days_back, breakdowns=breakdowns,
        profile=profile, to_db=to_db, csv_path=None,
        db_config=db_config, ad_account_ids=ad_account_ids,
        max_workers=max_workers,
    ))

    if to_bigquery and to_db and db_config:
        results.append(_step(
            "sync-to-bigquery dim_meta_accounts", run_sync_to_bigquery,
            table_names=["dim_meta_accounts"], db_config=db_config, profile=profile,
        ))
        results.append(_step(
            "sync-to-bigquery fact_meta_delivery_ad", run_sync_to_bigquery,
            table_names=["fact_meta_delivery_ad"], db_config=db_config, profile=profile,
        ))
        from src.etl.pipelines.materialize_combined import run_materialize_combined
        results.append(_step(
            "materialize-combined", run_materialize_combined,
            db_config=db_config, to_bigquery=True, profile=profile,
        ))

    _log_summary(results)


def run_dims_refresh(
    to_db: bool = True,
    to_bigquery: bool = False,
    max_workers: int = 1,
    db_config: Optional[PostgresConfig] = None,
    profile: Optional[str] = None,
) -> None:
    """Daily dim refresh: campaigns, adsets, ads, creatives."""
    from src.etl.pipelines.campaigns_info import run_campaigns_info
    from src.etl.pipelines.adsets_info import run_adsets_info
    from src.etl.pipelines.ads_info import run_ads_info
    from src.etl.pipelines.creatives_info import run_creatives_info
    from src.etl.pipelines.sync_to_bigquery import run_sync_to_bigquery

    ad_account_ids = load_ad_account_ids(profile)
    results: list[_Result] = []

    logger.info("Dims refresh started")

    for name, fn in [
        ("campaigns-info", run_campaigns_info),
        ("adsets-info",    run_adsets_info),
        ("ads-info",       run_ads_info),
    ]:
        results.append(_step(
            name, fn,
            to_db=to_db, db_config=db_config,
            ad_account_ids=ad_account_ids, max_workers=max_workers,
        ))

    results.append(_step(
        "creatives-info", run_creatives_info,
        to_db=to_db, db_config=db_config,
        ad_account_ids=ad_account_ids, max_workers=max_workers,
    ))

    if to_bigquery and to_db and db_config:
        for tbl in ["dim_meta_campaigns", "dim_meta_adsets", "dim_meta_ads", "dim_meta_creatives"]:
            results.append(_step(
                f"sync-to-bigquery {tbl}", run_sync_to_bigquery,
                table_names=[tbl], db_config=db_config, profile=profile,
            ))
        from src.etl.pipelines.materialize_combined import run_materialize_combined
        results.append(_step(
            "materialize-combined", run_materialize_combined,
            db_config=db_config, to_bigquery=True, profile=profile,
        ))

    _log_summary(results)


def run_full_refresh(
    from_date: str,
    to_date: str,
    level: str = "ad",
    chunk_size_days: int = 7,
    breakdowns: list[str] | None = None,
    skip_dims: bool = False,
    to_db: bool = True,
    to_bigquery: bool = False,
    bq_write_disposition: str = "WRITE_APPEND",
    max_workers: int = 1,
    backup: bool = False,
    db_config: Optional[PostgresConfig] = None,
    profile: Optional[str] = None,
) -> None:
    from src.etl.pipelines.accounts_info import run_accounts_info
    from src.etl.pipelines.campaigns_info import run_campaigns_info
    from src.etl.pipelines.adsets_info import run_adsets_info
    from src.etl.pipelines.ads_info import run_ads_info
    from src.etl.pipelines.creatives_info import run_creatives_info
    from src.etl.pipelines.meta_insights_range import run_meta_insights_range
    from src.etl.pipelines.sync_to_bigquery import run_sync_to_bigquery
    from src.etl.pipelines.backup_restore import run_backup

    ad_account_ids = load_ad_account_ids(profile)
    results: list[_Result] = []

    logger.info(
        "Full refresh started",
        from_date=from_date,
        to_date=to_date,
        level=level,
        chunk_days=chunk_size_days,
        workers=max_workers,
    )

    if backup and to_db and db_config:
        results.append(_step(
            "backup-db", run_backup,
            db_config=db_config, profile=profile,
        ))

    if not skip_dims:
        results.append(_step(
            "accounts-info", run_accounts_info,
            profile=profile, to_db=to_db,
            to_bigquery=to_bigquery, bq_write_disposition=bq_write_disposition,
            db_config=db_config,
        ))
        for name, fn in [
            ("campaigns-info", run_campaigns_info),
            ("adsets-info",    run_adsets_info),
            ("ads-info",       run_ads_info),
        ]:
            results.append(_step(
                name, fn,
                to_db=to_db, db_config=db_config,
                ad_account_ids=ad_account_ids, max_workers=max_workers,
            ))
        results.append(_step(
            "creatives-info", run_creatives_info,
            to_db=to_db, db_config=db_config,
            ad_account_ids=ad_account_ids, max_workers=max_workers,
        ))

    results.append(_step(
        f"insights-range ({from_date} to {to_date})", run_meta_insights_range,
        level=level, from_date=from_date, to_date=to_date,
        chunk_size_days=chunk_size_days, breakdowns=breakdowns,
        profile=profile, to_db=to_db,
        to_bigquery=to_bigquery, bq_write_disposition=bq_write_disposition,
        csv_path=None, db_config=db_config,
        ad_account_ids=ad_account_ids, max_workers=max_workers,
    ))

    if to_bigquery and to_db and db_config:
        results.append(_step(
            "sync-to-bigquery all", run_sync_to_bigquery,
            table_names=["all"], db_config=db_config, profile=profile,
        ))
        from src.etl.pipelines.materialize_combined import run_materialize_combined
        results.append(_step(
            "materialize-combined", run_materialize_combined,
            db_config=db_config, to_bigquery=True, profile=profile,
        ))

    _log_summary(results)
