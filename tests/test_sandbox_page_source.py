"""Static checks that the Sandbox page wires the Sepolia proof demo copy."""
from __future__ import annotations

from pathlib import Path


_SANDBOX_PAGE = (
    Path(__file__).resolve().parent.parent
    / "reflex_app" / "aequitas_rx" / "pages" / "sandbox.py"
)


def _src() -> str:
    return _SANDBOX_PAGE.read_text(encoding="utf-8")


def test_sandbox_page_includes_required_copy():
    src = _src()
    expected = [
        "Sepolia proof demo",
        "Digital Twin members are simulated at scale",
        "Sandbox members are a small deterministic Sepolia demo set",
        "Etherscan",
        "PIUs minted",
        "fairness proposal",
        "investment votes",
        "Publish ballot voting weights",
        "Publish actuarial proof bundle",
    ]
    for phrase in expected:
        assert phrase in src, f"missing required copy: {phrase!r}"


def test_sandbox_page_includes_live_broadcast_copy():
    src = _src()
    expected = [
        "Live Sepolia broadcast",
        "Dry run",
        "Fund sandbox wallets",
        "Member wallet ETH pays for gas",
        "Protocol pool funding pays for pension benefits",
        "Repeated demo runs may skip steps already recorded on-chain",
    ]
    for phrase in expected:
        assert phrase in src, f"missing required copy: {phrase!r}"


def test_sandbox_page_does_not_render_private_keys():
    src = _src()
    # The page must never reference a private-key field on a UI row.
    assert "private_key" not in src
