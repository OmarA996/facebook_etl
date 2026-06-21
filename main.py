import argparse
import sys

from src.etl.load.run_logger import record_run
from src.utils.logger import configure_logger, get_logger

from src.cli.handlers import (
    handle_adsets_info,
    handle_ads_info,
    handle_accounts_info,
    handle_accounts_registry,
    handle_backup_db,
    handle_campaigns_info,
    handle_clean_db,
    handle_creatives_info,
    handle_delete_account_data,
    handle_drop_backup,
    handle_full_refresh,
    handle_insights_daily,
    handle_insights_range,
    handle_list_backups,
    handle_migrate_renames,
    handle_prune_columns,
    handle_restore_backup,
    handle_run_daily,
    handle_sync_to_bigquery,
    handle_health_check,
    handle_materialize_combined,
    handle_reset_bigquery,
    handle_accounts_insights,
    handle_dims_refresh,
    handle_load_goals,
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
    range_p.add_argument("--force", action="store_true", help="re-process chunks already marked complete in etl_insights_checkpoint")

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

    # backup-db
    backup = subparsers.add_parser("backup-db", help="Copy all ETL tables into a timestamped backup schema")
    backup.add_argument("schema_name", nargs="?", default=None, help="Optional backup schema name (default: backup_YYYYMMDD_HHMMSS)")

    # list-backups
    subparsers.add_parser("list-backups", help="List all backup schemas in the database")

    # restore-backup
    restore = subparsers.add_parser("restore-backup", help="Restore ETL tables from a backup schema")
    restore.add_argument("schema_name", help="Backup schema name to restore from (e.g. backup_20260422_143000)")
    restore.add_argument("--dry-run", action="store_true", help="Print what would be restored without making changes")

    # drop-backup
    drop_bk = subparsers.add_parser("drop-backup", help="Delete a backup schema to free space")
    drop_bk.add_argument("schema_name", help="Backup schema name to delete")

    # migrate-renames
    migrate = subparsers.add_parser(
        "migrate-renames",
        help="Rename DB columns to match rename_to values in api_field_rename_template.csv",
    )
    migrate.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be renamed without making any changes",
    )
    migrate.add_argument(
        "--backup",
        action="store_true",
        help="Create a backup schema before renaming (recommended)",
    )
    migrate.add_argument(
        "--also-bigquery",
        action="store_true",
        help="Also rename columns in BigQuery tables",
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
    sync_bq.add_argument(
        "--create-if-missing",
        dest="create_if_missing",
        action="store_true",
        help="create BigQuery tables that do not exist yet (use for first-time setup)",
    )

    # delete-account-data
    del_acc = subparsers.add_parser(
        "delete-account-data",
        help="Delete all rows for accounts marked delete=TRUE in the template CSV (Postgres + optionally BigQuery)",
    )
    del_acc.add_argument(
        "csv_path",
        nargs="?",
        default="data/delete_accounts_template.csv",
        help="Path to the delete template CSV (default: data/delete_accounts_template.csv)",
    )
    del_acc.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview how many rows would be deleted without making any changes",
    )
    del_acc.add_argument(
        "--yes",
        action="store_true",
        help="Actually execute the deletions (required to make changes)",
    )
    del_acc.add_argument(
        "--also-bigquery",
        action="store_true",
        help="Also delete from BigQuery tables",
    )

    # clean-db
    clean = subparsers.add_parser(
        "clean-db",
        help="Drop tables/views in the public schema that are not part of the ETL model (safe for Power BI)",
    )
    clean.add_argument("--dry-run", action="store_true", help="List what would be dropped without making changes")

    # health-check
    subparsers.add_parser(
        "health-check",
        help="Test all connections (Meta API, Postgres, BigQuery) and report status",
    )

    # run-daily
    daily_auto = subparsers.add_parser(
        "run-daily",
        help="Run the full daily workflow: dims refresh + insights-daily + optional BQ sync",
    )
    daily_auto.add_argument("--days-back", dest="days_back", type=int, default=7, help="how many days back to pull insights (default 7)")
    daily_auto.add_argument("--level", default="ad", help="ad|adset|campaign|account (default ad)")
    daily_auto.add_argument("--breakdowns", dest="breakdowns", default=None, help="comma-separated breakdowns")
    daily_auto.add_argument("--skip-dims", dest="skip_dims", action="store_true", help="skip dimension refreshes")
    daily_auto.add_argument("--no-db", action="store_true", help="skip DB load")
    daily_auto.add_argument("--to-bigquery", action="store_true", help="sync to BigQuery after loading")
    daily_auto.add_argument(
        "--bq-write-disposition",
        default="WRITE_APPEND",
        choices=["WRITE_APPEND", "WRITE_TRUNCATE", "WRITE_EMPTY"],
        help="BigQuery write mode (default WRITE_APPEND)",
    )
    daily_auto.add_argument("--workers", dest="workers", type=int, default=1, help="parallel workers (default 1)")

    # full-refresh
    full = subparsers.add_parser(
        "full-refresh",
        help="Run the full historical workflow: dims + insights-range + optional BQ sync",
    )
    full.add_argument("from_date", help="start date YYYY-MM-DD")
    full.add_argument("to_date", help="end date YYYY-MM-DD")
    full.add_argument("--level", default="ad", help="ad|adset|campaign|account (default ad)")
    full.add_argument("--chunk-days", dest="chunk_days", type=int, default=7, help="chunk size in days (default 7)")
    full.add_argument("--breakdowns", dest="breakdowns", default=None, help="comma-separated breakdowns")
    full.add_argument("--skip-dims", dest="skip_dims", action="store_true", help="skip dimension refreshes")
    full.add_argument("--no-db", action="store_true", help="skip DB load")
    full.add_argument("--to-bigquery", action="store_true", help="sync to BigQuery after loading")
    full.add_argument(
        "--bq-write-disposition",
        default="WRITE_APPEND",
        choices=["WRITE_APPEND", "WRITE_TRUNCATE", "WRITE_EMPTY"],
        help="BigQuery write mode (default WRITE_APPEND)",
    )
    full.add_argument("--workers", dest="workers", type=int, default=1, help="parallel workers (default 1)")
    full.add_argument("--backup", action="store_true", help="take a DB backup before starting")

    mc = subparsers.add_parser(
        "materialize-combined",
        help="Create fact_meta_ads_combined in Postgres from the full view, optionally sync to BigQuery",
    )
    mc.add_argument("--to-bigquery", action="store_true", help="sync to BigQuery after materializing")

    subparsers.add_parser(
        "reset-bigquery",
        help="Drop all BigQuery tables, re-sync all Postgres ETL tables, and rebuild fact_meta_ads_combined",
    )

    ai = subparsers.add_parser(
        "accounts-insights",
        help="2-hour refresh: accounts metadata + rolling 7-day insights + BigQuery sync",
    )
    ai.add_argument("--days-back", dest="days_back", type=int, default=7)
    ai.add_argument("--to-bigquery", action="store_true")
    ai.add_argument("--workers", type=int, default=1)

    dr = subparsers.add_parser(
        "dims-refresh",
        help="Daily refresh: campaigns, adsets, ads, creatives + BigQuery sync",
    )
    dr.add_argument("--to-bigquery", action="store_true")
    dr.add_argument("--workers", type=int, default=1)

    # load-goals
    lg = subparsers.add_parser(
        "load-goals",
        help="Load goals from a CSV into dim_goals (Postgres + BigQuery) and create vw_goals_vs_actual",
    )
    lg.add_argument(
        "csv_path",
        nargs="?",
        default="data/goals.csv",
        help="Path to goals CSV (default: data/goals.csv)",
    )
    lg.add_argument("--no-db", action="store_true", help="skip Postgres upsert")
    lg.add_argument("--to-bigquery", action="store_true", help="sync to BigQuery and create vw_goals_vs_actual")

    return parser


def main():
    configure_logger()
    parser = build_parser()
    args = parser.parse_args()

    cmd = args.command
    profile = getattr(args, "db_profile", None)
    logger.info("CLI invoked", command=cmd, profile=profile)

    try:
        with record_run(command=cmd, profile=profile):
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
            elif cmd == "backup-db":
                handle_backup_db(args)
            elif cmd == "list-backups":
                handle_list_backups(args)
            elif cmd == "restore-backup":
                handle_restore_backup(args)
            elif cmd == "drop-backup":
                handle_drop_backup(args)
            elif cmd == "migrate-renames":
                handle_migrate_renames(args)
            elif cmd == "prune-columns":
                handle_prune_columns(args)
            elif cmd == "sync-to-bigquery":
                handle_sync_to_bigquery(args)
            elif cmd == "delete-account-data":
                handle_delete_account_data(args)
            elif cmd == "clean-db":
                handle_clean_db(args)
            elif cmd == "health-check":
                handle_health_check(args)
            elif cmd == "run-daily":
                handle_run_daily(args)
            elif cmd == "full-refresh":
                handle_full_refresh(args)
            elif cmd == "materialize-combined":
                handle_materialize_combined(args)
            elif cmd == "reset-bigquery":
                handle_reset_bigquery(args)
            elif cmd == "accounts-insights":
                handle_accounts_insights(args)
            elif cmd == "dims-refresh":
                handle_dims_refresh(args)
            elif cmd == "load-goals":
                handle_load_goals(args)
            else:
                parser.print_help()
    except Exception:
        logger.exception("Fatal error in CLI")
        sys.exit(1)


if __name__ == "__main__":
    main()
