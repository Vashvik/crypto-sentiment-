from app.services.text_processing import (
    clean_text, content_hash, is_probably_english, parse_utc, quality_issue, source_type_for, tag_assets, template_hash,
)


def test_clean_text_strips_html_urls_and_whitespace():
    assert clean_text("<b>Bitcoin</b>  hits &amp; holds https://x.co/abc  $100k") == "Bitcoin hits & holds $100k"


def test_content_hash_ignores_case_and_punctuation():
    assert content_hash("Bitcoin rises!") == content_hash("bitcoin   RISES")
    assert content_hash("Bitcoin rises") != content_hash("Bitcoin falls")


def test_template_hash_collapses_numbers_only():
    a = template_hash("1,200 #BTC transferred from unknown wallet")
    b = template_hash("85 #BTC transferred from unknown wallet")
    assert a == b
    assert content_hash("1,200 #BTC transferred") != content_hash("85 #BTC transferred")


def test_asset_tagging_is_whole_word_and_avoids_ambiguous_sol():
    assert tag_assets("Ethereum and Bitcoin rally") == {"ETH", "BTC"}
    assert tag_assets("The solution was simple") == set()
    assert tag_assets("Solana network outage") == {"SOL"}
    assert tag_assets("Buying $SOL today") == {"SOL"}
    assert tag_assets("Together we stand") == set()  # 'eth' inside a word must not match


def test_quality_filters():
    assert quality_issue("BTC up") == "too_short"
    assert quality_issue("Биткоин растет на новостях сегодня утром") == "non_english"
    assert quality_issue("Join our telegram for free crypto signals now") == "promotional"
    assert quality_issue("Bitcoin price climbs after ETF inflows") is None
    assert is_probably_english("Ethereum upgrade goes live on mainnet")


def test_source_type_and_timestamps():
    assert source_type_for("twitter.com") == "social"
    assert source_type_for("old.reddit.com") == "social"
    assert source_type_for("coindesk.com") == "news"
    dt = parse_utc("2024-01-10T20:42:04")
    assert dt.tzinfo is not None and dt.hour == 20
    assert parse_utc("2024-01-10T22:42:04+02:00").hour == 20
    assert parse_utc("not a date") is None
