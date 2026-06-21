from __future__ import annotations

from typing import Optional

from sqlalchemy import create_engine, inspect, text

from src.config import PostgresConfig, load_postgres_config
from src.schema.tables import TABLE_SCHEMAS
from src.schema.views import VIEW_NAME
from src.utils.logger import get_logger

logger = get_logger(__name__)

_SAFE = frozenset(TABLE_SCHEMAS.keys()) | {VIEW_NAME}


def run_clean_db(
    dry_run: bool = False,
    db_config: Optional[PostgresConfig] = None,
    profile: Optional[str] = None,
) -> None:
    cfg = db_config or load_postgres_config(profile)
    engine = create_engine(cfg.conn_string)
    insp = inspect(engine)

    all_tables = set(insp.get_table_names(schema="public"))
    all_views = set(insp.get_view_names(schema="public"))
    all_objects = all_tables | all_views

    unknown = sorted(all_objects - _SAFE)

    if not unknown:
        logger.info("Nothing to clean, all public tables/views are recognised ETL objects")
        return

    logger.info("Found unrecognised objects in public schema", count=len(unknown), objects=unknown)

    if dry_run:
        logger.info("DRY RUN, no changes made; re-run without --dry-run to drop them")
        return

    with engine.begin() as conn:
        for name in unknown:
            if name in all_views:
                conn.execute(text(f'DROP VIEW IF EXISTS "{name}" CASCADE'))
                logger.info("Dropped view", name=name)
            else:
                conn.execute(text(f'DROP TABLE IF EXISTS "{name}" CASCADE'))
                logger.info("Dropped table", name=name)

    logger.info("Clean complete", dropped=len(unknown))
