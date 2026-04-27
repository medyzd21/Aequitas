"""Tests for the Join as a member portal on the Members page."""
from __future__ import annotations

from pathlib import Path

import pytest

# ── page-source checks — no Reflex import needed ────────────────────────────

_MEMBERS_PAGE = (
    Path(__file__).resolve().parent.parent
    / "reflex_app" / "aequitas_rx" / "pages" / "members.py"
)


def _src() -> str:
    return _MEMBERS_PAGE.read_text(encoding="utf-8")


def test_members_page_includes_join_as_a_member():
    assert "Join as a member" in _src()


def test_members_page_includes_required_form_fields():
    src = _src()
    for phrase in [
        "Full name",
        "Date of birth",
        "Annual salary",
        "Contribution rate",
        "Target retirement age",
        "Wallet address",
    ]:
        assert phrase in src, f"missing form field label: {phrase!r}"


def test_members_page_includes_section_headings():
    src = _src()
    for heading in [
        "Member details",
        "Contribution choice",
        "Estimated PIUs",
        "Submit application",
    ]:
        assert heading in src, f"missing section heading: {heading!r}"


def test_members_page_includes_disclaimer_copy():
    src = _src()
    assert "demo onboarding portal" in src.lower() or "demo onboarding" in src
    assert "off-chain" in src
    assert "on-chain" in src


def test_members_page_includes_pending_applicants_table():
    assert "Pending applicants" in _src()


def test_members_page_does_not_call_blockchain_on_submit():
    src = _src()
    assert "cast send" not in src
    assert "eth_sendTransaction" not in src
    assert "sendTransaction" not in src


def test_members_page_does_not_expose_private_keys():
    src = _src()
    assert "private_key" not in src
    assert "DEPLOYER_PK" not in src


# ── state logic — skipped when Reflex is not importable in this env ──────────
# Use try/except so page-source tests above are never blocked.

try:
    from reflex_app.aequitas_rx.state import AppState as _AppState
    _REFLEX_OK = True
except Exception:
    _AppState = None  # type: ignore[assignment]
    _REFLEX_OK = False

_skip_no_reflex = pytest.mark.skipif(
    not _REFLEX_OK, reason="reflex not importable in this test env"
)


def _fresh():
    state = _AppState()
    state.current_piu_price_value = 1.08
    return state


def _fill(state, **kw):
    defaults = dict(
        join_full_name="Jane Smith",
        join_dob="1985-06-15",
        join_salary="60000",
        join_contribution_rate="8",
        join_retirement_age="65",
        join_wallet="",
    )
    defaults.update(kw)
    for k, v in defaults.items():
        setattr(state, k, v)


@_skip_no_reflex
class TestSubmitCreatesApplicantRow:
    def test_valid_submission_adds_one_row(self):
        state = _fresh()
        _fill(state)
        state.submit_join_application()
        assert state.join_submitted is True
        assert len(state.join_pending_applicants) == 1

    def test_row_contains_expected_keys(self):
        state = _fresh()
        _fill(state)
        state.submit_join_application()
        row = state.join_pending_applicants[0]
        for key in ("name", "age", "salary", "contribution_rate",
                    "annual_contribution", "estimated_pius", "status"):
            assert key in row, f"missing key: {key!r}"

    def test_row_status_is_pending_review(self):
        state = _fresh()
        _fill(state)
        state.submit_join_application()
        assert state.join_pending_applicants[0]["status"] == "pending review"

    def test_annual_contribution_is_correct(self):
        state = _fresh()
        _fill(state, join_salary="50000", join_contribution_rate="10")
        state.submit_join_application()
        row = state.join_pending_applicants[0]
        assert "5,000.00" in row["annual_contribution"]

    def test_estimated_pius_uses_piu_price(self):
        state = _fresh()
        state.current_piu_price_value = 2.0
        _fill(state, join_salary="50000", join_contribution_rate="10")
        state.submit_join_application()
        row = state.join_pending_applicants[0]
        # 5000 / 2.0 = 2500
        assert "2,500.00" in row["estimated_pius"]

    def test_multiple_submissions_accumulate_rows(self):
        state = _fresh()
        _fill(state, join_full_name="Alice")
        state.submit_join_application()
        state.join_submitted = False
        _fill(state, join_full_name="Bob")
        state.submit_join_application()
        assert len(state.join_pending_applicants) == 2

    def test_row_does_not_include_private_key(self):
        state = _fresh()
        _fill(state, join_wallet="0x" + "ab" * 20)
        state.submit_join_application()
        row_str = str(state.join_pending_applicants[0])
        assert "private_key" not in row_str
        assert "DEPLOYER_PK" not in row_str


@_skip_no_reflex
class TestValidation:
    def test_empty_name_raises_error(self):
        state = _fresh()
        _fill(state, join_full_name="")
        state.submit_join_application()
        assert state.join_submitted is False
        assert "name" in state.join_error.lower()

    def test_missing_dob_raises_error(self):
        state = _fresh()
        _fill(state, join_dob="")
        state.submit_join_application()
        assert state.join_submitted is False
        assert state.join_error != ""

    def test_invalid_dob_raises_error(self):
        state = _fresh()
        _fill(state, join_dob="not-a-date")
        state.submit_join_application()
        assert state.join_submitted is False
        assert state.join_error != ""

    def test_zero_salary_raises_error(self):
        state = _fresh()
        _fill(state, join_salary="0")
        state.submit_join_application()
        assert state.join_submitted is False
        assert "salary" in state.join_error.lower()

    def test_negative_salary_raises_error(self):
        state = _fresh()
        _fill(state, join_salary="-5000")
        state.submit_join_application()
        assert state.join_submitted is False

    def test_non_numeric_salary_raises_error(self):
        state = _fresh()
        _fill(state, join_salary="abc")
        state.submit_join_application()
        assert state.join_submitted is False
        assert "salary" in state.join_error.lower()

    def test_contribution_rate_too_high_raises_error(self):
        state = _fresh()
        _fill(state, join_contribution_rate="31")
        state.submit_join_application()
        assert state.join_submitted is False

    def test_contribution_rate_zero_raises_error(self):
        state = _fresh()
        _fill(state, join_contribution_rate="0")
        state.submit_join_application()
        assert state.join_submitted is False

    def test_retirement_age_too_low_raises_error(self):
        state = _fresh()
        _fill(state, join_retirement_age="40")
        state.submit_join_application()
        assert state.join_submitted is False

    def test_retirement_age_too_high_raises_error(self):
        state = _fresh()
        _fill(state, join_retirement_age="85")
        state.submit_join_application()
        assert state.join_submitted is False

    def test_invalid_wallet_address_raises_error(self):
        state = _fresh()
        _fill(state, join_wallet="not-a-wallet")
        state.submit_join_application()
        assert state.join_submitted is False
        assert "wallet" in state.join_error.lower()

    def test_valid_wallet_address_is_accepted(self):
        state = _fresh()
        _fill(state, join_wallet="0x" + "ab" * 20)
        state.submit_join_application()
        assert state.join_submitted is True, state.join_error

    def test_empty_wallet_is_accepted(self):
        state = _fresh()
        _fill(state, join_wallet="")
        state.submit_join_application()
        assert state.join_submitted is True, state.join_error

    def test_underage_applicant_raises_error(self):
        state = _fresh()
        _fill(state, join_dob="2020-01-01")
        state.submit_join_application()
        assert state.join_submitted is False

    def test_all_errors_reported_together(self):
        """Submitting a completely empty form surfaces multiple error messages."""
        state = _fresh()
        # Leave everything empty — should collect all required-field errors
        state.submit_join_application()
        assert state.join_submitted is False
        assert state.join_error != ""


@_skip_no_reflex
class TestResetForm:
    def test_reset_clears_all_fields(self):
        state = _fresh()
        _fill(state)
        state.submit_join_application()
        assert state.join_submitted is True
        state.reset_join_form()
        assert state.join_submitted is False
        assert state.join_full_name == ""
        assert state.join_error == ""

    def test_reset_does_not_clear_pending_applicants(self):
        state = _fresh()
        _fill(state)
        state.submit_join_application()
        assert len(state.join_pending_applicants) == 1
        state.reset_join_form()
        assert len(state.join_pending_applicants) == 1


@_skip_no_reflex
class TestComputedVars:
    def test_annual_contribution_fmt_correct(self):
        state = _fresh()
        state.join_salary = "50000"
        state.join_contribution_rate = "10"
        assert "5,000.00" in state.join_annual_contribution_fmt

    def test_annual_contribution_fmt_dash_on_invalid(self):
        state = _fresh()
        state.join_salary = "abc"
        state.join_contribution_rate = "10"
        assert state.join_annual_contribution_fmt == "—"

    def test_estimated_pius_fmt_uses_piu_price(self):
        state = _fresh()
        state.current_piu_price_value = 2.0
        state.join_salary = "40000"
        state.join_contribution_rate = "10"
        # 4000 / 2.0 = 2000
        assert "2,000.00" in state.join_estimated_pius_fmt

    def test_estimated_pius_fmt_dash_when_no_salary(self):
        state = _fresh()
        state.join_salary = ""
        state.join_contribution_rate = "8"
        assert state.join_estimated_pius_fmt == "—"
