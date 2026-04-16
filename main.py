import argparse
import sys

from src.utils.logger import configure_logger, get_logger

from src.cli.handlers import (
    handle_adsets_info,
    handle_ads_info,
    handle_accounts_info,
    handle_accounts_registry,
    handle_campaigns_info,
    handle_creatives_info,
    handle_insights_daily,
    handle_insights_range,
    handle_prune_columns,
    handle_sync_to_bigquery,
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
    daily.add_argument("--to-bigquery", action="store_true", help="load normalized output into BigQuery")
    daily.add_argument(
        "--bq-write-disposition",
        default="WRITE_APPEND",
        choices=["WRITE_APPEND", "WRITE_TRUNCATE", "WRITE_EMPTY"],
        help="BigQuery write mode (default WRITE_APPEND)",
    )
    daily.add_argument("--bq-table", dest="bq_table", default=None, help="optional BigQuery table override")
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
    range_p.add_argument("--to-bigquery", action="store_true", help="load normalized output into BigQuery")
    range_p.add_argument(
        "--bq-write-disposition",
        default="WRITE_APPEND",
        choices=["WRITE_APPEND", "WRITE_TRUNCATE", "WRITE_EMPTY"],
        help="BigQuery write mode (default WRITE_APPEND)",
    )
    range_p.add_argument("--bq-table", dest="bq_table", default=None, help="optional BigQuery table override")
    range_p.add_argument("--workers", dest="workers", type=int, default=1, help="max threads for parallel account fetch (default 1)")

    # accounts-info
    acc = subparsers.add_parser("accounts-info", help="Fetch accounts info")
    acc.add_argument("csv_path", nargs="?", default=None, help="optional CSV output path")
    acc.add_argument("--no-db", action="store_true", help="skip DB load")
    acc.add_argument("--to-bigquery", action="store_true", help="load normalized output into BigQuery")
    acc.add_argument(
        "--bq-write-disposition",
        default="WRITE_APPEND",
        choices=["WRITE_APPEND", "WRITE_TRUNCATE", "WRITE_EMPTY"],
        help="BigQuery write mode (default WRITE_APPEND)",
    )
    acc.add_argument("--bq-table", dest="bq_table", default=None, help="optional BigQuery table override")

    # accounts-registry
    acc_registry = subparsers.add_parser("accounts-registry", help="Fetch account registry with include flag")
    acc_registry.add_argument("csv_path", nargs="?", default="data/account_registry.csv", help="registry CSV output path")
    acc_registry.add_argument("--no-db", action="store_true", help="skip DB load")
    acc_registry.add_argument("--to-bigquery", action="store_true", help="load registry into BigQuery")
    acc_registry.add_argument(
        "--bq-write-disposition",
        default="WRITE_APPEND",
        choices=["WRITE_APPEND", "WRITE_TRUNCATE", "WRITE_EMPTY"],
        help="BigQuery write mode (default WRITE_APPEND)",
    )
    acc_registry.add_argument("--bq-table", dest="bq_table", default=None, help="optional BigQuery table override")

    # campaigns-info
    campaigns = subparsers.add_parser("campaigns-info", help="Fetch campaign metadata")
    campaigns.add_argument("csv_path", nargs="?", default=None, help="optional CSV output path")
    campaigns.add_argument("--effective-statuses", dest="effective_statuses", default=None, help="comma-separated effective statuses")
    campaigns.add_argument("--workers", dest="workers", type=int, default=1, help="max threads for parallel account fetch (default 1)")
    campaigns.add_argument("--no-db", action="store_true", help="skip DB load")

    # adsets-info
    adsets = subparsers.add_parser("adsets-info", help="Fetch adset metadata")
    adsets.add_argument("csv_path", nargs="?", default=None, help="optional CSV output path")
    adsets.add_argument("--effective-statuses", dest="effective_statuses", default=None, help="comma-separated effective statuses")
    adsets.add_argument("--workers", dest="workers", type=int, default=1, help="max threads for parallel account fetch (default 1)")
    adsets.add_argument("--no-db", action="store_true", help="skip DB load")

    # ads-info
    ads = subparsers.add_parser("ads-info", help="Fetch ad metadata/settings")
    ads.add_argument("csv_path", nargs="?", default=None, help="optional CSV output path")
    ads.add_argument("--effective-statuses", dest="effective_statuses", default=None, help="comma-separated effective statuses")
    ads.add_argument("--workers", dest="workers", type=int, default=1, help="max threads for parallel account fetch (default 1)")
    ads.add_argument("--no-db", action="store_true", help="skip DB load")

    # creatives-info
    creatives = subparsers.add_parser("creatives-info", help="Fetch creative metadata")
    creatives.add_argument("csv_path", nargs="?", default=None, help="optional CSV output path")
    creatives.add_argument("--workers", dest="workers", type=int, default=1, help="max threads for parallel account fetch (default 1)")
    creatives.add_argument("--no-db", action="store_true", help="skip DB load")
    creatives.add_argument("--preview", action="store_true", help="fetch preview URLs for each creative (slow — one API call per creative)")

    # prune-columns
    prune = subparsers.add_parser(
        "prune-columns",
        help="Drop columns marked 'excluded' in api_field_rename_template.csv from Postgres (and BigQuery)",
    )
    prune.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be dropped without making any changes",
    )
    prune.add_argument(
        "--also-bigquery",
        action="store_true",
        help="Also drop excluded columns from BigQuery tables",
    )

    # sync-to-bigquery
    sync_bq = subparsers.add_parser(
        "sync-to-bigquery",
        help="Sync PostgreSQL tables into existing BigQuery tables",
    )
    sync_bq.add_argument(
        "tables",
        nargs="+",
        help="one or more PostgreSQL source tables, or 'all' to sync only tables that already exist in BigQuery",
    )
    sync_bq.add_argument(
        "--mode",
        default="auto",
        choices=["auto", "merge", "truncate", "append"],
        help="sync mode (default auto)",
    )
    sync_bq.add_argument(
        "--chunk-size",
        dest="chunk_size",
        type=int,
        default=50000,
        help="rows per PostgreSQL chunk (default 50000)",
    )
    sync_bq.add_argument(
        "--bq-table",
        dest="bq_table",
        default=None,
        help="optional BigQuery target table override for single-table syncs",
    )

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
        elif cmd == "accounts-info":
            handle_accounts_info(args)
        elif cmd == "accounts-registry":
            handle_accounts_registry(args)
        elif cmd == "campaigns-info":
            handle_campaigns_info(args)
        elif cmd == "adsets-info":
            handle_adsets_info(args)
        elif cmd == "ads-info":
            handle_ads_info(args)
        elif cmd == "creatives-info":
            handle_creatives_info(args)
        elif cmd == "prune-columns":
            handle_prune_columns(args)
        elif cmd == "sync-to-bigquery":
            handle_sync_to_bigquery(args)
        else:
            parser.print_help()
    except Exception:
        logger.exception("Fatal error in CLI")
        sys.exit(1)


if __name__ == "__main__":
    main()
