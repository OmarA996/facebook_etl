from typing import List, Optional

from src.config import load_postgres_config, load_ad_account_ids
from src.schema.unique_keys import UNIQUE_KEYS
from src.etl.load.postgres_loader import truncate_all_tables

from src.etl.pipelines.meta_insights_daily import run_meta_insights_daily
from src.etl.pipelines.meta_insights_range import run_meta_insights_range
from src.etl.pipelines.insights_clean_from_raw import run_insights_clean_from_raw
from src.etl.pipelines.clean_raw_dims import run_clean_dim_from_raw, RAW_CLEAN_CONFIGS
from src.etl.pipelines.accounts_info import run_accounts_info
from src.etl.pipelines.creatives_info import run_creatives_info
from src.etl.pipelines.campaigns_info import run_campaigns_info
from src.etl.pipelines.adsets_info import run_adsets_info
from src.etl.pipelines.ads_info import run_ads_info
from src.etl.pipelines.hydrate_previews import run_hydrate_previews

from src.utils.logger import get_logger

logger = get_logger(__name__)


def parse_breakdowns(val: str | None) -> list[str] | None:
    if val is None:
        return None
    val = val.strip()
    if not val:
        return None
    return [b.strip() for b in val.split(",") if b.strip()]


def handle_insights_daily(args):
    logger.info("Starting daily insights pipeline", level=args.level, date_preset=args.date_preset)
    try:
        db_cfg = None if args.no_db else load_postgres_config(args.db_profile)
        breakdowns = parse_breakdowns(args.breakdowns)
        ad_accounts = load_ad_account_ids(args.db_profile)
        run_meta_insights_daily(
            level=args.level,
            date_preset=args.date_preset,
            breakdowns=breakdowns,
            to_db=not args.no_db,
            csv_path=args.csv_path if args.csv_path else None,
            db_config=db_cfg,
            ad_account_ids=ad_accounts,
            max_workers=args.workers if args.workers and args.workers > 0 else 1,
        )
        logger.info("Daily insights pipeline completed")
    except Exception as e:
        logger.exception("Failed to run daily insights pipeline", error=str(e))
        raise


def handle_insights_range(args):
    logger.info("Starting range insights pipeline", from_date=args.from_date, to_date=args.to_date)
    try:
        db_cfg = None if args.no_db else load_postgres_config(args.db_profile)
        breakdowns = parse_breakdowns(args.breakdowns)
        ad_accounts = load_ad_account_ids(args.db_profile)
        run_meta_insights_range(
            level=args.level,
            from_date=args.from_date,
            to_date=args.to_date,
            chunk_size_days=args.chunk_days,
            breakdowns=breakdowns,
            to_db=not args.no_db,
            csv_path=args.csv_path if args.csv_path else None,
            db_config=db_cfg,
            ad_account_ids=ad_accounts,
            max_workers=args.workers if args.workers and args.workers > 0 else 1,
        )
        logger.info("Range insights pipeline completed")
    except Exception as e:
        logger.exception("Failed to run range insights pipeline", error=str(e))
        raise


def handle_insights_clean(args):
    logger.info("Starting insights clean pipeline")
    try:
        db_cfg = load_postgres_config(args.db_profile)
        breakdowns = parse_breakdowns(args.breakdowns)
        run_insights_clean_from_raw(
            level=args.level,
            breakdowns=breakdowns,
            from_date=args.from_date,
            to_date=args.to_date,
            limit=args.limit,
            to_db=not args.no_db,
            db_config=db_cfg,
        )
        logger.info("Insights clean pipeline completed")
    except Exception as e:
        logger.exception("Failed to run insights clean pipeline", error=str(e))
        raise


def handle_clean_dim(args):
    logger.info("Starting clean dim pipeline", entity=args.entity)
    try:
        db_cfg = load_postgres_config(args.db_profile)
        run_clean_dim_from_raw(
            entity=args.entity,
            limit=args.limit,
            to_db=not args.no_db,
            db_config=db_cfg,
        )
        logger.info("Clean dim pipeline completed")
    except Exception as e:
        logger.exception("Failed to run clean dim pipeline", error=str(e))
        raise


def handle_accounts_info(args):
    logger.info("Starting accounts info pipeline")
    try:
        db_cfg = None if args.no_db else load_postgres_config(args.db_profile)
        run_accounts_info(
            csv_path=args.csv_path if args.csv_path else None,
            to_db=not args.no_db,
            db_config=db_cfg,
        )
        logger.info("Accounts info pipeline completed")
    except Exception as e:
        logger.exception("Failed to run accounts info pipeline", error=str(e))
        raise


def handle_creatives_info(args):
    logger.info("Starting creatives info pipeline")
    try:
        db_cfg = None if args.no_db else load_postgres_config(args.db_profile)
        ad_accounts = load_ad_account_ids(args.db_profile)
        run_creatives_info(
            csv_path=args.csv_path if args.csv_path else None,
            to_db=not args.no_db,
            db_config=db_cfg,
            ad_account_ids=ad_accounts,
            max_workers=args.workers if args.workers and args.workers > 0 else 1,
        )
        logger.info("Creatives info pipeline completed")
    except Exception as e:
        logger.exception("Failed to run creatives info pipeline", error=str(e))
        raise





def handle_campaigns_info(args):
    logger.info("Starting campaigns info pipeline")
    try:
        db_cfg = None if args.no_db else load_postgres_config(args.db_profile)
        ad_accounts = load_ad_account_ids(args.db_profile)
        run_campaigns_info(
            csv_path=args.csv_path if args.csv_path else None,
            to_db=not args.no_db,
            db_config=db_cfg,
            ad_account_ids=ad_accounts,
            max_workers=args.workers if args.workers and args.workers > 0 else 1,
        )
        logger.info("Campaigns info pipeline completed")
    except Exception as e:
        logger.exception("Failed to run campaigns info pipeline", error=str(e))
        raise


def handle_adsets_info(args):
    logger.info("Starting adsets info pipeline")
    try:
        db_cfg = None if args.no_db else load_postgres_config(args.db_profile)
        ad_accounts = load_ad_account_ids(args.db_profile)
        run_adsets_info(
            csv_path=args.csv_path if args.csv_path else None,
            to_db=not args.no_db,
            db_config=db_cfg,
            ad_account_ids=ad_accounts,
            max_workers=args.workers if args.workers and args.workers > 0 else 1,
        )
        logger.info("Adsets info pipeline completed")
    except Exception as e:
        logger.exception("Failed to run adsets info pipeline", error=str(e))
        raise


def handle_ads_info(args):
    logger.info("Starting ads info pipeline")
    try:
        db_cfg = None if args.no_db else load_postgres_config(args.db_profile)
        ad_accounts = load_ad_account_ids(args.db_profile)
        run_ads_info(
            csv_path=args.csv_path if args.csv_path else None,
            to_db=not args.no_db,
            db_config=db_cfg,
            ad_account_ids=ad_accounts,
            max_workers=args.workers if args.workers and args.workers > 0 else 1,
        )
        logger.info("Ads info pipeline completed")
    except Exception as e:
        logger.exception("Failed to run ads info pipeline", error=str(e))
        raise


def handle_db_truncate(args):
    logger.info("Starting DB truncate")
    try:
        db_cfg = load_postgres_config(args.db_profile)
        if args.tables:
            table_names = args.tables
        else:
            table_names = list(UNIQUE_KEYS.keys())
        truncate_all_tables(table_names, conn_string=db_cfg.conn_string)
        logger.info("DB truncate completed", tables=table_names)
    except Exception as e:
        logger.exception("Failed to run DB truncate", error=str(e))
        raise


def handle_hydrate_previews(args):
    logger.info("Starting hydrate previews pipeline")
    try:
        db_cfg = load_postgres_config(args.db_profile)
        run_hydrate_previews(
            limit=args.limit,
            ad_format=args.ad_format,
            db_config=db_cfg,
        )
        logger.info("Hydrate previews pipeline completed")
    except Exception as e:
        logger.exception("Failed to run hydrate previews pipeline", error=str(e))
        raise
