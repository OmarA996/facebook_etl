from typing import Optional, List
from sqlalchemy import create_engine, text
from src.config import PostgresConfig
from src.etl.extract.creatives import fetch_preview_url
from src.utils.logger import get_logger

logger = get_logger(__name__)

def run_hydrate_previews(
    limit: int = 100,
    ad_format: str = "DESKTOP_FEED_STANDARD",
    db_config: Optional[PostgresConfig] = None,
):
    """
    Find creatives in dim_meta_creatives that are missing a preview_url,
    fetch them from Meta, and update the DB row.
    """
    if not db_config:
        logger.error("No DB config provided for hydration.")
        return

    engine = create_engine(db_config.conn_string)
    
    # 1. Find candidates
    # We assume dim_meta_creatives has columns: creative_id, account_id, preview_url
    select_sql = """
        SELECT creative_id, account_id
        FROM dim_meta_creatives
        WHERE preview_url IS NULL
        LIMIT :limit
    """
    
    with engine.connect() as conn:
        candidates = conn.execute(text(select_sql), {"limit": limit}).fetchall()
        
    if not candidates:
        logger.info("No creatives found missing preview_url (limit reached or all done).")
        return

    logger.info("Found candidates for hydration", count=len(candidates))
    
    updated_count = 0
    
    # 2. Iterate and fetch
    # We'll update one by one for simplicity (or batch if needed, but fetching is the bottleneck)
    with engine.begin() as conn:
        for row in candidates:
            c_id = row.creative_id
            a_id = row.account_id
            
            if not c_id or not a_id:
                continue
                
            try:
                url = fetch_preview_url(account_id=str(a_id), creative_id=str(c_id), ad_format=ad_format)
            except Exception as e:
                logger.warning("Failed to fetch preview", creative_id=c_id, error=str(e))
                continue
            
            if url:
                update_sql = """
                    UPDATE dim_meta_creatives
                    SET preview_url = :url
                    WHERE creative_id = :c_id
                """
                conn.execute(text(update_sql), {"url": url, "c_id": c_id})
                updated_count += 1
                
    logger.info("Hydration complete", updated=updated_count, attempted=len(candidates))
