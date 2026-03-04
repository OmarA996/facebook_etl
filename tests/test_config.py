import os
import pytest
from src.config.settings import Settings

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
