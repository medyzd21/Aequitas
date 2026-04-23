"""Regression tests for Twin V2 state serialization."""
from __future__ import annotations

from reflex_app.aequitas_rx.serialization import typed_records


def test_typed_records_preserves_phase_as_string():
    rows = [
        {
            "year": 2026,
            "age": 44,
            "salary": 62000.0,
            "contribution": 6200.0,
            "phase": "accumulation",
            "piu_price": 1.08,
        }
    ]
    typed = typed_records(
        rows,
        int_fields={"year", "age"},
        float_fields={"salary", "contribution", "piu_price"},
        str_fields={"phase"},
    )
    assert typed[0]["year"] == 2026
    assert typed[0]["salary"] == 62000.0
    assert typed[0]["phase"] == "accumulation"
    assert isinstance(typed[0]["phase"], str)


def test_typed_records_does_not_guess_categorical_fields_as_numeric():
    rows = [
        {"year": 2027, "phase": "retired", "status": "deceased", "fund_value": 0.0}
    ]
    typed = typed_records(
        rows,
        int_fields={"year"},
        float_fields={"fund_value"},
        str_fields={"phase", "status"},
    )
    assert typed[0]["phase"] == "retired"
    assert typed[0]["status"] == "deceased"
    assert typed[0]["fund_value"] == 0.0
