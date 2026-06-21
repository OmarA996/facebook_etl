import os
from pathlib import Path
import pytest
from src.config.settings import settings
from src.config.settings import Settings
from src.config import load_account_registry, load_ad_account_ids, load_bigquery_config

def test_defaults(monkeypatch):
    # Ensure no env var interferes
    monkeypatch.delenv("META_API_VERSION", raising=False)
    
    # Pass explicit values to avoid reading from actual .env during test
    s = Settings(META_ACCESS_TOKEN="token", META_AD_ACCOUNT_IDS="123,456", _env_file=None)
    assert s.META_ACCESS_TOKEN == "token"
    assert s.meta_ad_account_ids_list == ["123", "456"]
    assert s.META_API_VERSION == "v21.0" # default

def test_profiles(monkeypatch):
    monkeypatch.setenv("META_AD_ACCOUNT_IDS_AGENCY", "777,888")
    monkeypatch.setenv("DB_CONN_STRING_AGENCY", "postgresql://agency_db")
    
    s = Settings(META_ACCESS_TOKEN="dummy", _env_file=None) 
    
    profiles = s.meta_ad_account_ids_profiles
    assert "agency" in profiles
    assert profiles["agency"] == ["777", "888"]
    
    db_profiles = s.db_conn_profiles
    assert "agency" in db_profiles
    assert db_profiles["agency"] == "postgresql://agency_db"

def test_get_ad_account_ids(monkeypatch):
    monkeypatch.setenv("META_AD_ACCOUNT_IDS", "default_1")
    monkeypatch.setenv("META_AD_ACCOUNT_IDS_TEST", "profile_1")
    
    s = Settings(META_ACCESS_TOKEN="dummy", _env_file=None)
    
    ids = s.get_ad_account_ids(profile=None)
    assert ids == ["default_1"]
    
    ids_profile = s.get_ad_account_ids(profile="test")
    assert ids_profile == ["profile_1"]


def test_load_account_registry_filters_by_profile_and_include_flag(monkeypatch):
    registry_path = Path("tests_account_registry.csv").resolve()
    registry_path.write_text(
        "\n".join(
            [
                "account_id,account_name,account_status,profile_name,include_in_etl,notes",
                "act_1,Agency A,1,agency,True,",
                "act_2,Agency B,1,agency,False,",
                "3,Freelance A,2,freelance,True,",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "ACCOUNT_REGISTRY_PATH", str(registry_path))

    try:
        agency_rows = load_account_registry(profile="agency")
        freelance_rows = load_account_registry(profile="freelance")

        assert [row["account_id"] for row in agency_rows] == ["act_1"]
        assert [row["account_id"] for row in freelance_rows] == ["act_3"]
    finally:
        registry_path.unlink(missing_ok=True)


def test_load_ad_account_ids_falls_back_to_env_when_registry_missing(monkeypatch):
    monkeypatch.setattr(settings, "ACCOUNT_REGISTRY_PATH", str(Path("missing_registry.csv").resolve()))
    monkeypatch.setattr(settings, "META_AD_ACCOUNT_IDS", "123,456")

    assert load_ad_account_ids() == ["act_123", "act_456"]


def test_load_bigquery_config_uses_profile_specific_dataset(monkeypatch):
    monkeypatch.setenv("BQ_PROJECT_ID_AGENCY", "project-agency")
    monkeypatch.setenv("BQ_DATASET_AGENCY", "dataset_agency")
    monkeypatch.setenv("BQ_LOCATION_AGENCY", "EU")

    cfg = load_bigquery_config("agency")

    assert cfg.project_id == "project-agency"
    assert cfg.dataset_id == "dataset_agency"
    assert cfg.location == "EU"
