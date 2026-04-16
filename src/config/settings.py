import os
from dotenv import load_dotenv
from typing import List, Dict, Optional, Any
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env into os.environ so we can scan for dynamic keys
load_dotenv()

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Attributes:
        meta_access_token: The Facebook Graph API access token.
        meta_app_id: The Facebook App ID.
        meta_app_secret: The Facebook App Secret.
        meta_api_version: The API version to use (e.g., 'v17.0').
        meta_ad_account_ids_list: Default list of ad account IDs.
        db_conn_string_default: Default database connection string.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
        case_sensitive=True
    )

    META_ACCESS_TOKEN: str = ""
    META_API_VERSION: str = "v25.0"
    # We use a string field for the raw list to keep parsing simple
    META_AD_ACCOUNT_IDS: str = "" 
    
    DB_CONN_STRING: str = ""
    DB_CONN_STRING_DEFAULT: str = ""

    BQ_PROJECT_ID: str = ""
    BQ_DATASET: str = ""
    BQ_LOCATION: str = ""
    BQ_CREDENTIALS_PATH: str = ""
    BQ_IMPERSONATE_SERVICE_ACCOUNT: str = ""
    ACCOUNT_REGISTRY_PATH: str = Field(default_factory=lambda: os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data",
        "account_registry.csv",
    ))
    
    # Compute default DATA_DIR relative to project root
    DATA_DIR: str = Field(default_factory=lambda: os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
        "data"
    ))

    @property
    def meta_ad_account_ids_list(self) -> List[str]:
         return self._parse_list(self.META_AD_ACCOUNT_IDS)

    @property
    def meta_ad_account_ids_profiles(self) -> Dict[str, List[str]]:
        """
        Dynamically loads ad account lists for specific profiles (e.g., AGENCY, FREELANCE).
        
        Scans environment variables matching pattern META_AD_ACCOUNT_IDS_<PROFILE>.
        """
        profiles = {}
        # Scan os.environ for dynamic keys (populated by load_dotenv or system env)
        for key, value in os.environ.items():
            if key.startswith("META_AD_ACCOUNT_IDS_") and key != "META_AD_ACCOUNT_IDS":
                 profile = key.replace("META_AD_ACCOUNT_IDS_", "").lower()
                 if value:
                     profiles[profile] = self._parse_list(value)
        return profiles

    @property
    def db_conn_profiles(self) -> Dict[str, str]:
        profiles = {}
        for key, value in os.environ.items():
            if key.startswith("DB_CONN_STRING_") and key not in ("DB_CONN_STRING", "DB_CONN_STRING_DEFAULT"):
                profile = key.replace("DB_CONN_STRING_", "").lower()
                if value:
                    profiles[profile] = value
        return profiles

    @property
    def bq_project_profiles(self) -> Dict[str, str]:
        profiles = {}
        for key, value in os.environ.items():
            if key.startswith("BQ_PROJECT_ID_") and key != "BQ_PROJECT_ID":
                profile = key.replace("BQ_PROJECT_ID_", "").lower()
                if value:
                    profiles[profile] = value
        return profiles

    @property
    def bq_dataset_profiles(self) -> Dict[str, str]:
        profiles = {}
        for key, value in os.environ.items():
            if key.startswith("BQ_DATASET_") and key != "BQ_DATASET":
                profile = key.replace("BQ_DATASET_", "").lower()
                if value:
                    profiles[profile] = value
        return profiles

    @property
    def bq_location_profiles(self) -> Dict[str, str]:
        profiles = {}
        for key, value in os.environ.items():
            if key.startswith("BQ_LOCATION_") and key != "BQ_LOCATION":
                profile = key.replace("BQ_LOCATION_", "").lower()
                if value:
                    profiles[profile] = value
        return profiles

    @property
    def bq_credentials_profiles(self) -> Dict[str, str]:
        profiles = {}
        for key, value in os.environ.items():
            if key.startswith("BQ_CREDENTIALS_PATH_") and key != "BQ_CREDENTIALS_PATH":
                profile = key.replace("BQ_CREDENTIALS_PATH_", "").lower()
                if value:
                    profiles[profile] = value
        return profiles

    @property
    def bq_impersonate_service_account_profiles(self) -> Dict[str, str]:
        profiles = {}
        for key, value in os.environ.items():
            if key.startswith("BQ_IMPERSONATE_SERVICE_ACCOUNT_") and key != "BQ_IMPERSONATE_SERVICE_ACCOUNT":
                profile = key.replace("BQ_IMPERSONATE_SERVICE_ACCOUNT_", "").lower()
                if value:
                    profiles[profile] = value
        return profiles

    def get_ad_account_ids(self, profile: Optional[str] = None) -> List[str]:
        if profile:
            ids = self.meta_ad_account_ids_profiles.get(profile.lower())
            if ids:
                return ids
        return self.meta_ad_account_ids_list

    @staticmethod
    def _parse_list(raw: str) -> List[str]:
        if not raw:
            return []
        return [acc.strip() for acc in raw.split(",") if acc.strip()]

# Global instance
settings = Settings()
