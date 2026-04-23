"""Pure-Python helpers for shaping Reflex-safe UI payloads."""
from __future__ import annotations

from typing import Any

import numpy as np


def is_nan_like(value: Any) -> bool:
    try:
        return bool(np.isnan(value))
    except TypeError:
        return False


def typed_record(
    row: dict[str, Any],
    *,
    int_fields: set[str] | None = None,
    float_fields: set[str] | None = None,
    str_fields: set[str] | None = None,
) -> dict[str, Any]:
    """Coerce a row into a UI-safe payload with an explicit type contract."""
    int_fields = int_fields or set()
    float_fields = float_fields or set()
    str_fields = str_fields or set()
    typed: dict[str, Any] = {}
    for key, value in row.items():
        if key in int_fields:
            typed[key] = None if value is None or is_nan_like(value) else int(value)
        elif key in float_fields:
            typed[key] = None if value is None or is_nan_like(value) else float(value)
        elif key in str_fields:
            typed[key] = "" if value is None else str(value)
        else:
            typed[key] = value
    return typed


def typed_records(
    rows: list[dict[str, Any]],
    *,
    int_fields: set[str] | None = None,
    float_fields: set[str] | None = None,
    str_fields: set[str] | None = None,
) -> list[dict[str, Any]]:
    return [
        typed_record(
            row,
            int_fields=int_fields,
            float_fields=float_fields,
            str_fields=str_fields,
        )
        for row in rows
    ]
