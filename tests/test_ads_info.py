import pandas as pd

from src.etl.pipelines.ads_info import _build_creatives_dimension_df, _save_ads_dimensions


def test_save_ads_dimensions_upserts_settings_and_compat_tables(monkeypatch):
    saved = []

    def fake_save_df_to_postgres_upsert(df, table_name, unique_cols, conn_string=None):
        saved.append(
            {
                "table_name": table_name,
                "unique_cols": unique_cols,
                "conn_string": conn_string,
                "columns": list(df.columns),
                "rows": df.to_dict(orient="records"),
            }
        )

    monkeypatch.setattr(
        "src.etl.pipelines.ads_info.save_df_to_postgres_upsert",
        fake_save_df_to_postgres_upsert,
    )

    df = pd.DataFrame(
        [
            {
                "ad_id": "1",
                "account_id": "act_1",
                "ad_name": "Ad One",
                "adset_id": "10",
                "campaign_id": "100",
                "creative_id": "500",
                "creative.name": "Creative One",
                "effective_status": "ACTIVE",
            }
        ]
    )

    _save_ads_dimensions(df, conn_string="postgresql://example")

    assert [item["table_name"] for item in saved] == [
        "dim_meta_ads_settings",
        "dim_meta_ads",
        "dim_meta_creatives",
    ]
    assert saved[0]["columns"] == [
        "ad_id",
        "account_id",
        "ad_name",
        "adset_id",
        "campaign_id",
        "creative_id",
        "creative.name",
        "effective_status",
    ]
    assert saved[1]["columns"] == [
        "ad_id",
        "account_id",
        "ad_name",
        "adset_id",
        "campaign_id",
        "creative_id",
    ]
    assert saved[1]["rows"] == [
        {
            "ad_id": "1",
            "account_id": "act_1",
            "ad_name": "Ad One",
            "adset_id": "10",
            "campaign_id": "100",
            "creative_id": "500",
        }
    ]
    assert saved[2]["table_name"] == "dim_meta_creatives"
    assert saved[2]["unique_cols"] == ["creative_id"]


def test_save_ads_dimensions_fills_missing_compat_columns(monkeypatch):
    saved = []

    def fake_save_df_to_postgres_upsert(df, table_name, unique_cols, conn_string=None):
        saved.append((table_name, df.to_dict(orient="records")))

    monkeypatch.setattr(
        "src.etl.pipelines.ads_info.save_df_to_postgres_upsert",
        fake_save_df_to_postgres_upsert,
    )

    df = pd.DataFrame([{"ad_id": "1", "ad_name": "Ad One"}])

    _save_ads_dimensions(df)

    assert saved[1] == (
        "dim_meta_ads",
        [
            {
                "ad_id": "1",
                "account_id": None,
                "ad_name": "Ad One",
                "adset_id": None,
                "campaign_id": None,
                "creative_id": None,
            }
        ],
    )


def test_build_creatives_dimension_df_uses_nested_creative_fields():
    df = pd.DataFrame(
        [
            {
                "account_id": "act_1",
                "creative.id": "9001",
                "creative.name": "Creative One",
                "creative.title": "Fallback title",
                "creative.body": "Fallback body",
                "creative.image_url": "https://cdn.example/image.jpg",
                "creative.thumbnail_url": "https://cdn.example/thumb.jpg",
                "creative.image_hash": "hash123",
                "creative.object_story_spec.link_data.message": "Primary text",
                "creative.object_story_spec.link_data.description": "Description text",
                "creative.object_story_spec.link_data.link": "https://example.com",
                "creative.object_story_spec.link_data.caption": "example.com",
                "creative.object_story_spec.link_data.call_to_action.type": "SHOP_NOW",
                "creative.object_story_spec.link_data.picture": "https://cdn.example/picture.jpg",
                "creative.object_story_spec.link_data.image_hash": "hash999",
                "creative.object_story_id": "123_456",
            }
        ]
    )

    creatives_df = _build_creatives_dimension_df(df)

    assert creatives_df.to_dict(orient="records") == [
        {
            "creative_id": "9001",
            "account_id": "act_1",
            "creative_name": "Creative One",
            "title": "Fallback title",
            "body": "Primary text",
            "description": "Description text",
            "call_to_action_type": "SHOP_NOW",
            "image_url": "https://cdn.example/picture.jpg",
            "thumbnail_url": "https://cdn.example/thumb.jpg",
            "image_hash": "hash999",
            "video_id": None,
            "object_url": None,
            "link_url": "https://example.com",
            "display_url": "example.com",
            "effective_object_story_id": "123_456",
            "status": None,
        }
    ]
