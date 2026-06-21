from dataclasses import dataclass
from pathlib import Path
from typing import List

import pandas as pd

from src.config.settings import settings


@dataclass
class GraphConfig:
    access_token: str
    version: str
    base_url: str


@dataclass
class PostgresConfig:
    conn_string: str


@dataclass
class BigQueryConfig:
    project_id: str
    dataset_id: str
    credentials_path: str | None
    impersonate_service_account: str | None
    location: str | None


def _normalize_account_id(account_id: str) -> str:
    if not account_id:
        return account_id
    return account_id if str(account_id).startswith("act_") else f"act_{account_id}"


def load_account_registry(profile: str | None = None) -> list[dict]:
    path = Path(settings.ACCOUNT_REGISTRY_PATH)
    if not path.exists():
        return []

    df = pd.read_csv(path, dtype={"account_id": "string", "profile_name": "string"})
    if df.empty or "account_id" not in df.columns:
        return []

    if "include_in_etl" not in df.columns:
        df["include_in_etl"] = True
    if "profile_name" not in df.columns:
        df["profile_name"] = None

    include_series = df["include_in_etl"].fillna(True).astype(str).str.strip().str.lower()
    df = df[include_series.isin({"true", "1", "yes", "y"})].copy()

    if profile:
        normalized_profile = profile.strip().lower()
        profile_series = df["profile_name"].fillna("").astype(str).str.strip().str.lower()
        df = df[profile_series == normalized_profile].copy()

    if df.empty:
        return []

    if "account_name" not in df.columns:
        df["account_name"] = None
    if "account_status" not in df.columns:
        df["account_status"] = None
    if "notes" not in df.columns:
        df["notes"] = None

    df["account_id"] = df["account_id"].apply(lambda value: _normalize_account_id(str(value).strip()) if pd.notna(value) else None)
    df = df.dropna(subset=["account_id"]).drop_duplicates(subset=["account_id"], keep="last")

    return df[["account_id", "account_name", "account_status", "profile_name", "include_in_etl", "notes"]].to_dict(
        orient="records"
    )


def load_ad_account_ids(profile: str | None = None) -> List[str]:
    """
    Return ad account ids for a given profile, falling back to default list.
    """
    settings.validate_profile(profile)
    registry_rows = load_account_registry(profile=profile)
    if registry_rows:
        return [row["account_id"] for row in registry_rows if row.get("account_id")]

    raw_ids = settings.get_ad_account_ids(profile)
    return [_normalize_account_id(acc) for acc in raw_ids]


def load_graph_config() -> GraphConfig:
    """
    Build a Graph API config object from environment-backed settings.

    Note: GraphAPIClient expects `base_url` without the version suffix
    because it appends `/{version}/{endpoint}` internally.
    """
    token = settings.META_ACCESS_TOKEN
    if not token:
        raise ValueError(
            "META_ACCESS_TOKEN is not set. "
            "Add it to your .env file (copy .env.example to get started)."
        )

    base_url = "https://graph.facebook.com"

    return GraphConfig(
        access_token=token,
        version=settings.META_API_VERSION,
        base_url=base_url,
    )


def load_postgres_config(profile: str | None = None) -> PostgresConfig:
    """
    Build a Postgres config object based on profile.

    - profile is lowercased and mapped to env var DB_CONN_STRING_<PROFILE>
    - profile=None falls back to DB_CONN_STRING_DEFAULT or DB_CONN_STRING
    - unknown profiles raise ValueError so typos can't silently fall back
      to the default and route data into the wrong tenant
    """
    settings.validate_profile(profile)
    if profile:
        key = profile.lower()
        conn = settings.db_conn_profiles.get(key)
        if not conn:
            raise ValueError(
                f"No DB connection string found for profile '{profile}'. "
                "Set DB_CONN_STRING_<PROFILE> in your environment."
            )
        return PostgresConfig(conn_string=conn)

    # default path
    conn = settings.DB_CONN_STRING_DEFAULT or settings.DB_CONN_STRING
    if not conn:
        raise ValueError(
            "DB_CONN_STRING is not set. "
            "Add it to your .env file. Format: postgresql://user:password@host:5432/dbname"
        )
    if not conn.startswith(("postgresql://", "postgresql+psycopg2://", "postgresql+psycopg://")):
        raise ValueError(
            f"DB_CONN_STRING does not look like a valid Postgres URL. "
            "Expected format: postgresql://user:password@host:5432/dbname"
        )
    return PostgresConfig(conn_string=conn)


def load_bigquery_config(profile: str | None = None) -> BigQueryConfig:
    """
    Build a BigQuery config object from environment-backed settings.
    """
    settings.validate_profile(profile)
    normalized_profile = profile.lower() if profile else None

    if normalized_profile:
        project_id = settings.bq_project_profiles.get(normalized_profile, settings.BQ_PROJECT_ID)
        dataset_id = settings.bq_dataset_profiles.get(normalized_profile, settings.BQ_DATASET)
        credentials_path = settings.bq_credentials_profiles.get(normalized_profile, settings.BQ_CREDENTIALS_PATH) or None
        impersonate_service_account = (
            settings.bq_impersonate_service_account_profiles.get(
                normalized_profile,
                settings.BQ_IMPERSONATE_SERVICE_ACCOUNT,
            )
            or None
        )
        location = settings.bq_location_profiles.get(normalized_profile, settings.BQ_LOCATION) or None
    else:
        project_id = settings.BQ_PROJECT_ID
        dataset_id = settings.BQ_DATASET
        credentials_path = settings.BQ_CREDENTIALS_PATH or None
        impersonate_service_account = settings.BQ_IMPERSONATE_SERVICE_ACCOUNT or None
        location = settings.BQ_LOCATION or None

    if not project_id or not dataset_id:
        if normalized_profile:
            raise ValueError(
                f"Missing BigQuery config for profile '{profile}'. "
                "Set BQ_PROJECT_ID/BQ_DATASET or profile-specific BQ_PROJECT_ID_<PROFILE>/BQ_DATASET_<PROFILE>."
            )
        raise ValueError("Missing BigQuery config. Set BQ_PROJECT_ID and BQ_DATASET.")

    return BigQueryConfig(
        project_id=project_id,
        dataset_id=dataset_id,
        credentials_path=credentials_path,
        impersonate_service_account=impersonate_service_account,
        location=location,
    )
