"""Tests for engine.chain_stub."""
from engine.chain_stub import EventLog


def test_event_log_chains_and_verifies():
    log = EventLog()
    log.append("member_registered", wallet="0xA", birth_year=1980)
    log.append("contribution_recorded", wallet="0xA", amount=500.0)
    log.append("proposal_evaluated", name="demo", passes=True)
    assert len(log) == 3
    assert log.verify() is True


def test_event_log_detects_tampering():
    log = EventLog()
    log.append("member_registered", wallet="0xA", birth_year=1980)
    log.append("contribution_recorded", wallet="0xA", amount=500.0)
    # tamper with data
    log.events[1].data["amount"] = 9_999_999.0
    assert log.verify() is False
