import argparse
import sys

from src.utils.logger import configure_logger, get_logger
from src.etl.pipelines.clean_raw_dims import RAW_CLEAN_CONFIGS
from src.schema.unique_keys import UNIQUE_KEYS

from src.cli.handlers import (
    handle_insights_daily,
    handle_insights_range,
    handle_insights_clean,
    handle_clean_dim,
    handle_accounts_info,
    handle_creatives_info,
    handle_campaigns_info,
    handle_adsets_info,
    handle_ads_info,
    handle_ads_info,
    handle_db_truncate,
    handle_hydrate_previews
)

logger = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Meta ETL CLI")
    parser.add_argument(
        "--db-profile",
        default=None,
        help="Optional DB profile name (e.g., freelance, agency). Uses DB_CONN_STRING_<PROFILE> from .env",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # insights-daily
    daily = subparsers.add_parser("insights-daily", help="Run daily insights pipeline")
    daily.add_argument("level", nargs="?", default="ad", help="ad|adset|campaign|account (default ad)")
    daily.add_argument("--date-preset", dest="date_preset", default="yesterday", help="date preset (default yesterday)")
    daily.add_argument("--csv", dest="csv_path", default=None, help="optional CSV output path")
    daily.add_argument("--breakdowns", dest="breakdowns", default=None, help="comma-separated breakdowns (e.g., age,gender)")
    daily.add_argument("--no-db", action="store_true", help="skip DB load")
    daily.add_argument("--workers", dest="workers", type=int, default=1, help="max threads for parallel account fetch (default 1)")

    # insights-range
    range_p = subparsers.add_parser("insights-range", help="Run range insights pipeline")
    range_p.add_argument("from_date", help="start date YYYY-MM-DD")
    range_p.add_argument("to_date", help="end date YYYY-MM-DD")
    range_p.add_argument("level", nargs="?", default="ad", help="ad|adset|campaign|account (default ad)")
    range_p.add_argument("chunk_days", nargs="?", type=int, default=7, help="chunk size in days (default 7)")
    range_p.add_argument("--csv", dest="csv_path", default=None, help="optional CSV output path")
    range_p.add_argument("--breakdowns", dest="breakdowns", default=None, help="comma-separated breakdowns (e.g., age,gender)")
    range_p.add_argument("--no-db", action="store_true", help="skip DB load")
    range_p.add_argument("--workers", dest="workers", type=int, default=1, help="max threads for parallel account fetch (default 1)")

    # clean-dim (re-run cleaning for dimension pipelines from their raw tables)
    clean_dim = subparsers.add_parser("clean-dim", help="Clean raw dimension tables into fact/dim tables")
    clean_dim.add_argument(
        "entity",
        choices=list(RAW_CLEAN_CONFIGS.keys()),
        help="Which entity to clean (accounts, creatives, campaigns, adsets, ads, ad-previews)",
    )
    clean_dim.add_argument("--limit", dest="limit", type=int, default=None, help="optional max raw rows to process")
    clean_dim.add_argument("--no-db", action="store_true", help="skip fact/dim upsert (still reads raw from DB)")

    # insights-clean (from raw table to fact table)
    clean = subparsers.add_parser("insights-clean", help="Clean raw insights (meta_insights_raw) into fact tables")
    clean.add_argument("level", nargs="?", default="ad", help="ad|adset|campaign|account (default ad)")
    clean.add_argument("--breakdowns", dest="breakdowns", default=None, help="comma-separated breakdowns to filter raw and pick target table (e.g., age,gender)")
    clean.add_argument("--from-date", dest="from_date", default=None, help="filter raw by date_start >= YYYY-MM-DD")
    clean.add_argument("--to-date", dest="to_date", default=None, help="filter raw by date_start <= YYYY-MM-DD")
    clean.add_argument("--limit", dest="limit", type=int, default=None, help="optional max raw rows to process")
    clean.add_argument("--no-db", action="store_true", help="skip fact table upsert (still reads raw from DB)")

    # accounts-info
    acc = subparsers.add_parser("accounts-info", help="Fetch accounts info")
    acc.add_argument("csv_path", nargs="?", default=None, help="optional CSV output path")
    acc.add_argument("--no-db", action="store_true", help="skip DB load")

    # creatives-info
    creatives = subparsers.add_parser("creatives-info", help="Fetch creatives info")
    creatives.add_argument("csv_path", nargs="?", default=None, help="optional CSV output path")
    creatives.add_argument("--no-db", action="store_true", help="skip DB load")
    creatives.add_argument("--workers", dest="workers", type=int, default=1, help="max threads for parallel account fetch (default 1)")



    # campaigns-info
    campaigns = subparsers.add_parser("campaigns-info", help="Fetch campaigns info")
    campaigns.add_argument("csv_path", nargs="?", default=None, help="optional CSV output path")
    campaigns.add_argument("--no-db", action="store_true", help="skip DB load")
    campaigns.add_argument("--workers", dest="workers", type=int, default=1, help="max threads for parallel account fetch (default 1)")

    # adsets-info
    adsets = subparsers.add_parser("adsets-info", help="Fetch adsets info")
    adsets.add_argument("csv_path", nargs="?", default=None, help="optional CSV output path")
    adsets.add_argument("--no-db", action="store_true", help="skip DB load")
    adsets.add_argument("--workers", dest="workers", type=int, default=1, help="max threads for parallel account fetch (default 1)")

    # ads-info
    ads = subparsers.add_parser("ads-info", help="Fetch ads settings info")
    ads.add_argument("csv_path", nargs="?", default=None, help="optional CSV output path")
    ads.add_argument("--no-db", action="store_true", help="skip DB load")
    ads.add_argument("--workers", dest="workers", type=int, default=1, help="max threads for parallel account fetch (default 1)")

    # db-truncate
    truncate = subparsers.add_parser("db-truncate", help="Truncate all known tables")
    truncate.add_argument("--tables", nargs="*", default=None, help="specific tables to truncate (default: all known)")

    # hydrate-previews
    hydrate = subparsers.add_parser("hydrate-previews", help="Hydrate missing preview URLs in dim_meta_creatives")
    hydrate.add_argument("--limit", type=int, default=100, help="max rows to update per run (default 100)")
    hydrate.add_argument("--ad-format", default="DESKTOP_FEED_STANDARD", help="ad format for preview (default DESKTOP_FEED_STANDARD)")


    return parser


def main():
    configure_logger()
    parser = build_parser()
    args = parser.parse_args()

    cmd = args.command
    logger.info("CLI invoked", command=cmd)

    try:
        if cmd == "insights-daily":
            handle_insights_daily(args)
        elif cmd == "insights-range":
            handle_insights_range(args)
        elif cmd == "clean-dim":
            handle_clean_dim(args)
        elif cmd == "insights-clean":
            handle_insights_clean(args)
        elif cmd == "accounts-info":
            handle_accounts_info(args)
        elif cmd == "creatives-info":
            handle_creatives_info(args)
        elif cmd == "campaigns-info":
            handle_campaigns_info(args)
        elif cmd == "adsets-info":
            handle_adsets_info(args)
        elif cmd == "ads-info":
            handle_ads_info(args)
        elif cmd == "db-truncate":
            handle_db_truncate(args)
        elif cmd == "hydrate-previews":
            handle_hydrate_previews(args)
        else:
            parser.print_help()
    except Exception:
        logger.exception("Fatal error in CLI")
        sys.exit(1)


if __name__ == "__main__":
    main()
