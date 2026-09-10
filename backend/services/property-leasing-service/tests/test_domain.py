from app.services.leasing_service import LeasingService


def test_terms_digest_is_stable_for_key_order() -> None:
    assert LeasingService._terms_digest({"b": 2, "a": 1}) == LeasingService._terms_digest(
        {"a": 1, "b": 2}
    )


def test_terms_digest_changes_with_terms() -> None:
    assert LeasingService._terms_digest({"rent": 10}) != LeasingService._terms_digest({"rent": 11})
