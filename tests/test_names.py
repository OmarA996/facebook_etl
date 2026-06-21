from src.utils.names import normalize_column_name


def test_normalize_column_name_replaces_hyphens_and_punctuation():
    assert (
        normalize_column_name("ad_review_feedback_global_non-functional_landing_page")
        == "ad_review_feedback_global_non_functional_landing_page"
    )


def test_normalize_column_name_collapses_repeated_separators():
    assert normalize_column_name("  A.B:C - D  ") == "a_b_c_d"
