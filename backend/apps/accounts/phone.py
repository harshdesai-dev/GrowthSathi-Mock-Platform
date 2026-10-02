import re

from django.core.exceptions import ValidationError


def normalize_indian_mobile(value: str) -> str:
    compact = re.sub(r"[\s\-()]", "", value.strip())
    if compact.startswith("+91"):
        compact = compact[3:]
    elif compact.startswith("91") and len(compact) == 12:
        compact = compact[2:]
    elif compact.startswith("0") and len(compact) == 11:
        compact = compact[1:]

    if not re.fullmatch(r"[6-9]\d{9}", compact):
        raise ValidationError("Enter a valid 10-digit Indian mobile number.")
    return f"+91{compact}"
