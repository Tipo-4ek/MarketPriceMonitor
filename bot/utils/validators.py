"""Validators for user input."""

# Product ids are a 32-bit INTEGER primary key. A value past that is not just
# "not found" — passed to Postgres it raises a NumericValueOutOfRange rather
# than returning nothing, so it is rejected here as invalid input.
_MAX_PRODUCT_ID = 2_147_483_647


def validate_threshold(threshold_str: str) -> int | None:
    """Validate a percentage threshold. Returns the value, or None if invalid."""
    try:
        threshold = int(threshold_str)
    except ValueError:
        return None
    return threshold if 1 <= threshold <= 100 else None


def validate_product_id(product_id_str: str) -> int | None:
    """Validate a product id. Returns the value, or None if invalid or out of range."""
    try:
        product_id = int(product_id_str)
    except ValueError:
        return None
    return product_id if 1 <= product_id <= _MAX_PRODUCT_ID else None


def validate_locale(locale: str) -> bool:
    """Validate locale code."""
    return locale in ('ru', 'en')
