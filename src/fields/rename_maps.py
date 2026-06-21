# src/fields/rename_maps.py
#
# Single source of truth for API field → database column name mapping.
#
# HOW TO USE
# ----------
# Edit data/api_field_rename_template.csv to add or change mappings.
#
# COLUMNS
# -------
#   group_name              — visual grouping only (e.g. "01_accounts")
#   endpoint_or_pipeline    — must match the pipeline name used in code
#   api_field               — raw field name as returned by pd.json_normalize
#                             (uses dots for nested paths, e.g. "funding_source_details.id")
#   current_database_table  — destination table name
#   current_database_column — default DB column name (used if rename_to is blank)
#   rename_to               — override DB column name (takes precedence over current_database_column)
#   status                  — controls whether the field is loaded:
#                               approved  → rename and load (default for all known fields)
#                               pending   → new field detected by ETL, awaiting your decision;
#                                           fill rename_to and change to 'approved' to load it,
#                                           or set 'excluded' to permanently drop it
#                               excluded  → silently dropped from all loads
#   notes                   — free-text notes
#
# PIPELINE NAMES (must match the `endpoint_or_pipeline` column in the CSV)
# -------------------------------------------------------------------------
#   "accounts-info"          → dim_meta_accounts
#   "campaigns-info"         → dim_meta_campaigns
#   "adsets-info"            → dim_meta_adsets
#   "ads-info"               → dim_meta_ads
#   "creatives-info"         → dim_meta_creatives
#   "insights-daily ad"      → fact_meta_delivery_ad
#   "insights-daily adset"   → fact_meta_delivery_adset
#   "insights-daily campaign"→ fact_meta_delivery_campaign
#   "insights-daily account" → fact_meta_delivery_account

import csv
import os
from typing import Dict, List, Set, Tuple

_TEMPLATE_PATH = os.path.join(
    os.path.dirname(   # src/fields/
    os.path.dirname(   # src/
    os.path.dirname(   # project root
    os.path.abspath(__file__)))),
    "data",
    "api_field_rename_template.csv",
)

# Valid status values
STATUS_APPROVED = "approved"
STATUS_PENDING  = "pending"
STATUS_EXCLUDED = "excluded"


def _load_all_rows() -> List[dict]:
    """Return every row from the CSV as a list of dicts (raw, no filtering)."""
    if not os.path.exists(_TEMPLATE_PATH):
        return []
    with open(_TEMPLATE_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _load_rename_maps() -> Tuple[
    Dict[str, Dict[str, str]],   # rename_maps:  {pipeline: {api_field -> db_col}}
    Dict[str, Set[str]],         # excluded_map: {pipeline: {api_field, ...}}
    Dict[str, Set[str]],         # pending_map:  {pipeline: {api_field, ...}}
    Dict[str, Set[str]],         # known_map:    {pipeline: {api_field, ...}} (all statuses)
]:
    """
    Parse the CSV and build lookup structures.

    Returns:
        rename_maps  — {pipeline: {api_field -> target_db_col}} for approved rows only
        excluded_map — {pipeline: {api_fields}} to silently drop
        pending_map  — {pipeline: {api_fields}} that are new/unreviewed
        known_map    — {pipeline: {api_fields}} for all rows regardless of status
    """
    rename_maps:  Dict[str, Dict[str, str]] = {}
    excluded_map: Dict[str, Set[str]]       = {}
    pending_map:  Dict[str, Set[str]]       = {}
    known_map:    Dict[str, Set[str]]       = {}

    for row in _load_all_rows():
        pipeline  = (row.get("endpoint_or_pipeline") or "").strip()
        api_field = (row.get("api_field")             or "").strip()
        db_col    = (row.get("current_database_column") or "").strip()
        rename_to = (row.get("rename_to")             or "").strip()
        status    = (row.get("status")                or STATUS_APPROVED).strip().lower()

        if not pipeline or not api_field:
            continue

        # Track every declared field regardless of status
        known_map.setdefault(pipeline, set()).add(api_field)

        if status == STATUS_EXCLUDED:
            excluded_map.setdefault(pipeline, set()).add(api_field)
            continue

        if status == STATUS_PENDING:
            pending_map.setdefault(pipeline, set()).add(api_field)
            continue

        # status == approved (or anything unrecognised → treat as approved)
        if not db_col:
            continue

        target = rename_to if rename_to else db_col

        # Skip no-op entries (field already has the right name)
        if api_field == target:
            rename_maps.setdefault(pipeline, {})  # ensure key exists
            continue

        rename_maps.setdefault(pipeline, {})[api_field] = target

    return rename_maps, excluded_map, pending_map, known_map


# Loaded once at import time.
_RENAME_MAPS, _EXCLUDED_MAP, _PENDING_MAP, _KNOWN_MAP = _load_rename_maps()

# Public aliases kept for backward compatibility
RENAME_MAPS = _RENAME_MAPS


def get_rename_map(pipeline: str) -> Dict[str, str]:
    """Return {api_field -> db_column} for approved fields in this pipeline."""
    return _RENAME_MAPS.get(pipeline, {})


def get_excluded_fields(pipeline: str) -> Set[str]:
    """Return the set of api_fields marked 'excluded' for this pipeline."""
    return _EXCLUDED_MAP.get(pipeline, set())


def get_pending_fields(pipeline: str) -> Set[str]:
    """Return the set of api_fields marked 'pending' for this pipeline."""
    return _PENDING_MAP.get(pipeline, set())


def get_known_fields(pipeline: str) -> Set[str]:
    """Return ALL api_fields declared for this pipeline (any status)."""
    return _KNOWN_MAP.get(pipeline, set())


def register_new_fields(
    pipeline: str,
    table_name: str,
    new_api_fields: List[str],
    group_name: str = "",
) -> int:
    """
    Append previously-unseen API fields to the CSV as 'pending'.

    These fields appeared in an API response but have no entry in the
    rename template.  They will be skipped from DB loads until the user
    opens the CSV, fills in rename_to, and changes status to 'approved'.

    Returns the number of rows actually appended (0 if all already known).
    """
    if not new_api_fields or not os.path.exists(_TEMPLATE_PATH):
        return 0

    # Re-read known fields fresh from disk to avoid stale in-memory state
    existing_rows = _load_all_rows()
    declared: Set[str] = set()
    for row in existing_rows:
        if (row.get("endpoint_or_pipeline") or "").strip() == pipeline:
            f = (row.get("api_field") or "").strip()
            if f:
                declared.add(f)

    truly_new = [f for f in new_api_fields if f not in declared]
    if not truly_new:
        return 0

    fieldnames = [
        "group_name", "endpoint_or_pipeline", "api_field",
        "current_database_table", "current_database_column",
        "rename_to", "status", "notes",
    ]

    with open(_TEMPLATE_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        for field in sorted(truly_new):
            # Derive a default db column name from the api field
            default_col = field.replace(".", "_").replace("-", "_").lower()[:63]
            writer.writerow({
                "group_name":              group_name or f"pending_{pipeline}",
                "endpoint_or_pipeline":    pipeline,
                "api_field":               field,
                "current_database_table":  table_name,
                "current_database_column": default_col,
                "rename_to":               "",
                "status":                  STATUS_PENDING,
                "notes":                   "Auto-detected: set rename_to and change status to approved to load",
            })

    return len(truly_new)


def reload() -> None:
    """Force reload from disk (useful after register_new_fields in same process)."""
    global _RENAME_MAPS, _EXCLUDED_MAP, _PENDING_MAP, _KNOWN_MAP, RENAME_MAPS
    _RENAME_MAPS, _EXCLUDED_MAP, _PENDING_MAP, _KNOWN_MAP = _load_rename_maps()
    RENAME_MAPS = _RENAME_MAPS
