from src.config import load_ad_account_ids, load_postgres_config, load_graph_config, load_bigquery_config
from src.etl.pipelines.adsets_info import run_adsets_info
from src.etl.pipelines.ads_info import run_ads_info
from src.etl.pipelines.accounts_info import run_accounts_info
from src.etl.pipelines.accounts_registry import run_accounts_registry
from src.etl.pipelines.campaigns_info import run_campaigns_info
from src.etl.pipelines.creatives_info import run_creatives_info
from src.etl.pipelines.meta_insights_daily import run_meta_insights_daily
from src.etl.pipelines.meta_insights_range import run_meta_insights_range
from src.etl.pipelines.prune_columns import run_prune_columns
from src.etl.pipelines.sync_to_bigquery import run_sync_to_bigquery
from src.utils.logger import get_logger

logger = get_logger(__name__)


def parse_breakdowns(val: str | None) -> list[str] | None:
    if val is None:
        return None
    cleaned = val.strip()
    if not cleaned:
        return None
    return [item.strip() for item in cleaned.split(",") if item.strip()]


def handle_insights_daily(args):
    logger.info("Starting daily insights pipeline", level=args.level, date_preset=args.date_preset)
    try:
        db_cfg = None if args.no_db else load_postgres_config(args.db_profile)
        run_meta_insights_daily(
            level=args.level,
            date_preset=args.date_preset,
            breakdowns=parse_breakdowns(args.breakdowns),
            profile=args.db_profile,
            to_db=not args.no_db,
            to_bigquery=args.to_bigquery,
            bq_write_disposition=args.bq_write_disposition,
            bq_table_name=args.bq_table,
            csv_path=args.csv_path or None,
            db_config=db_cfg,
            ad_account_ids=load_ad_account_ids(args.db_profile),
            max_workers=args.workers if args.workers and args.workers > 0 else 1,
        )
        logger.info("Daily insights pipeline completed")
    except Exception as exc:
        logger.exception("Failed to run daily insights pipeline", error=str(exc))
        raise


def handle_insights_range(args):
    logger.info("Starting range insights pipeline", from_date=args.from_date, to_date=args.to_date)
    try:
        db_cfg = None if args.no_db else load_postgres_config(args.db_profile)
        run_meta_insights_range(
            level=args.level,
            from_date=args.from_date,
            to_date=args.to_date,
            chunk_size_days=args.chunk_days,
            breakdowns=parse_breakdowns(args.breakdowns),
            profile=args.db_profile,
            to_db=not args.no_db,
            to_bigquery=args.to_bigquery,
            bq_write_disposition=args.bq_write_disposition,
            bq_table_name=args.bq_table,
            csv_path=args.csv_path or None,
            db_config=db_cfg,
            ad_account_ids=load_ad_account_ids(args.db_profile),
            max_workers=args.workers if args.workers and args.workers > 0 else 1,
        )
        logger.info("Range insights pipeline completed")
    except Exception as exc:
        logger.exception("Failed to run range insights pipeline", error=str(exc))
        raise


def handle_accounts_info(args):
    logger.info("Starting accounts info pipeline")
    try:
        db_cfg = None if args.no_db else load_postgres_config(args.db_profile)
        run_accounts_info(
            csv_path=args.csv_path or None,
            profile=args.db_profile,
            to_db=not args.no_db,
            to_bigquery=args.to_bigquery,
            bq_write_disposition=args.bq_write_disposition,
            bq_table_name=args.bq_table,
            db_config=db_cfg,
        )
        logger.info("Accounts info pipeline completed")
    except Exception as exc:
        logger.exception("Failed to run accounts info pipeline", error=str(exc))
        raise


def handle_accounts_registry(args):
    logger.info("Starting accounts registry pipeline")
    try:
        db_cfg = None if args.no_db else load_postgres_config(args.db_profile)
        run_accounts_registry(
            csv_path=args.csv_path or "data/account_registry.csv",
            profile=args.db_profile,
            to_db=not args.no_db,
            to_bigquery=args.to_bigquery,
            bq_write_disposition=args.bq_write_disposition,
            bq_table_name=args.bq_table,
            db_config=db_cfg,
        )
        logger.info("Accounts registry pipeline completed")
    except Exception as exc:
        logger.exception("Failed to run accounts registry pipeline", error=str(exc))
        raise


def handle_campaigns_info(args):
    logger.info("Starting campaigns info pipeline")
    try:
        db_cfg = None if args.no_db else load_postgres_config(args.db_profile)
        run_campaigns_info(
            csv_path=args.csv_path or None,
            to_db=not args.no_db,
            effective_statuses=parse_breakdowns(args.effective_statuses),
            db_config=db_cfg,
            ad_account_ids=load_ad_account_ids(args.db_profile),
            max_workers=args.workers if args.workers and args.workers > 0 else 1,
        )
        logger.info("Campaigns info pipeline completed")
    except Exception as exc:
        logger.exception("Failed to run campaigns info pipeline", error=str(exc))
        raise


def handle_adsets_info(args):
    logger.info("Starting adsets info pipeline")
    try:
        db_cfg = None if args.no_db else load_postgres_config(args.db_profile)
        run_adsets_info(
            csv_path=args.csv_path or None,
            to_db=not args.no_db,
            effective_statuses=parse_breakdowns(args.effective_statuses),
            db_config=db_cfg,
            ad_account_ids=load_ad_account_ids(args.db_profile),
            max_workers=args.workers if args.workers and args.workers > 0 else 1,
        )
        logger.info("Adsets info pipeline completed")
    except Exception as exc:
        logger.exception("Failed to run adsets info pipeline", error=str(exc))
        raise


def handle_ads_info(args):
    logger.info("Starting ads info pipeline")
    try:
        db_cfg = None if args.no_db else load_postgres_config(args.db_profile)
        run_ads_info(
            csv_path=args.csv_path or None,
            to_db=not args.no_db,
            effective_statuses=parse_breakdowns(args.effective_statuses),
            db_config=db_cfg,
            ad_account_ids=load_ad_account_ids(args.db_profile),
            max_workers=args.workers if args.workers and args.workers > 0 else 1,
        )
        logger.info("Ads info pipeline completed")
    except Exception as exc:
        logger.exception("Failed to run ads info pipeline", error=str(exc))
        raise


def handle_creatives_info(args):
    logger.info("Starting creatives info pipeline")
    try:
        db_cfg = None if args.no_db else load_postgres_config(args.db_profile)
        run_creatives_info(
            csv_path=args.csv_path or None,
            to_db=not args.no_db,
            include_preview=getattr(args, "preview", False),
            db_config=db_cfg,
            ad_account_ids=load_ad_account_ids(args.db_profile),
            max_workers=args.workers if args.workers and args.workers > 0 else 1,
        )
        logger.info("Creatives info pipeline completed")
    except Exception as exc:
        logger.exception("Failed to run creatives info pipeline", error=str(exc))
        raise


def handle_prune_columns(args):
    logger.info("Starting prune-columns", dry_run=args.dry_run, also_bigquery=args.also_bigquery)
    try:
        db_cfg = load_postgres_config(args.db_profile)
        run_prune_columns(
            dry_run=args.dry_run,
            also_bigquery=args.also_bigquery,
            db_config=db_cfg,
            profile=args.db_profile,
        )
        logger.info("prune-columns completed")
    except Exception as exc:
        logger.exception("Failed prune-columns", error=str(exc))
        raise


def handle_sync_to_bigquery(args):
    logger.info("Starting PostgreSQL to BigQuery sync", tables=args.tables, mode=args.mode)
    try:
        db_cfg = load_postgres_config(args.db_profile)
        run_sync_to_bigquery(
            table_names=args.tables,
            db_config=db_cfg,
            profile=args.db_profile,
            mode=args.mode,
            chunk_size=args.chunk_size,
            bq_table_name=args.bq_table,
        )
        logger.info("PostgreSQL to BigQuery sync completed", tables=args.tables)
    except Exception as exc:
        logger.exception("Failed PostgreSQL to BigQuery sync", error=str(exc))
        raise


def handle_health_check(args):
    """
    Test each configured connection and report pass/fail.
    Exits with code 1 if any check fails.
    """
    import sys
    from src.clients.graph_client import GraphAPIClient, GraphAPIError
    from sqlalchemy import create_engine, text

    results = {}

    # ── 1. Meta API ──────────────────────────────────────────────────────────
    try:
        graph_cfg = load_graph_config()
        client = GraphAPIClient(
            access_token=graph_cfg.access_token,
            version=graph_cfg.version,
            base_url=graph_cfg.base_url,
        )
        client.get("me", params={"fields": "id"})
        results["Meta API"] = ("OK", f"token valid (version {graph_cfg.version})")
    except Exception as exc:
        results["Meta API"] = ("FAIL", str(exc))

    # ── 2. PostgreSQL ─────────────────────────────────────────────────────────
    try:
        db_cfg = load_postgres_config(getattr(args, "db_profile", None))
        engine = create_engine(db_cfg.conn_string)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        results["PostgreSQL"] = ("OK", db_cfg.conn_string.split("@")[-1])  # host/db only, no password
    except Exception as exc:
        results["PostgreSQL"] = ("FAIL", str(exc))

    # ── 3. BigQuery (only if configured) ─────────────────────────────────────
    try:
        bq_cfg = load_bigquery_config(getattr(args, "db_profile", None))
        from google.cloud import bigquery as bq
        import google.auth

        if bq_cfg.credentials_path:
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_file(bq_cfg.credentials_path)
        else:
            creds, _ = google.auth.default()

        bq_client = bq.Client(project=bq_cfg.project_id, credentials=creds)
        list(bq_client.list_datasets(max_results=1))
        results["BigQuery"] = ("OK", f"{bq_cfg.project_id}.{bq_cfg.dataset_id}")
    except ValueError:
        results["BigQuery"] = ("SKIP", "BQ_PROJECT_ID / BQ_DATASET not configured")
    except Exception as exc:
        results["BigQuery"] = ("FAIL", str(exc))

    # ── Report ────────────────────────────────────────────────────────────────
    print("\n-- Health Check ---------------------------------------------")
    any_fail = False
    for name, (status, detail) in results.items():
        icon = "OK  " if status == "OK" else ("SKIP" if status == "SKIP" else "FAIL")
        print(f"  [{icon}]  {name:<12}  {detail}")
        if status == "FAIL":
            any_fail = True
    print("-------------------------------------------------------------\n")

    if any_fail:
        sys.exit(1)
