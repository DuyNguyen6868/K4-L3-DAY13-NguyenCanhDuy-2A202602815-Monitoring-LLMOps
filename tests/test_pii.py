from app.pii import hash_user_id, scrub_text


def test_scrub_email() -> None:
    out = scrub_text("Email me at student@vinuni.edu.vn")
    assert "student@" not in out
    assert "REDACTED_EMAIL" in out


def test_scrub_common_vietnamese_phone_formats() -> None:
    phone_numbers = (
        "0901234567",
        "090 123 4567",
        "090.123.4567",
        "090-123-4567",
        "+84 90 123 4567",
    )

    for phone_number in phone_numbers:
        out = scrub_text(f"Contact: {phone_number}")
        assert phone_number not in out
        assert "REDACTED_PHONE_VN" in out


def test_scrub_cccd() -> None:
    out = scrub_text("CCCD 012345678901, please verify")
    assert "012345678901" not in out
    assert "REDACTED_CCCD" in out


def test_scrub_credit_card_formats() -> None:
    for card in ("4111 1111 1111 1111", "4111-1111-1111-1111", "4111111111111111"):
        out = scrub_text(f"Card {card} was charged")
        assert card not in out
        assert "REDACTED_CREDIT_CARD" in out


def test_scrub_passport() -> None:
    for passport in ("B1234567", "C12345678"):
        out = scrub_text(f"Passport {passport}")
        assert passport not in out
        assert "REDACTED_PASSPORT" in out


def test_email_is_scrubbed_before_phone() -> None:
    assert scrub_text("Mail an.nguyen.0987654321@vinuni.edu.vn") == "Mail [REDACTED_EMAIL]"


def test_scrub_keeps_log_identifiers_and_metrics() -> None:
    safe_values = (
        "req-0000abcd",
        hash_user_id("u01"),
        "2026-09-29T08:59:40.904214Z",
        "claude-sonnet-4-5",
        "cost 0.001923 USD, latency 532 ms",
    )
    for value in safe_values:
        assert scrub_text(value) == value
