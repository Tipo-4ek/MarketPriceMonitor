"""Validators for user input."""


def validate_threshold(threshold_str: str) -> int | None:
    """Validate threshold value.

    Returns:
        Threshold value if valid, None otherwise.
    """
    try:
        threshold = int(threshold_str)
        if 1 <= threshold <= 100:
            return threshold
    except ValueError:
        pass
    return None


def validate_product_id(product_id_str: str) -> int | None:
    """Validate product ID.

    Returns:
        Product ID if valid, None otherwise.
    """
    try:
        product_id = int(product_id_str)
        if product_id > 0:
            return product_id
    except ValueError:
        pass
    return None


def validate_locale(locale: str) -> bool:
    """Validate locale code."""
    return locale in ('ru', 'en')


