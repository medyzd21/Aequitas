"""Append-only event log that mirrors what a smart contract would emit.

This is NOT a blockchain. It is a deliberately tiny, observable, ordered log
so that later work can swap `EventLog.append` for a real Solidity event
without changing any caller. Each record gets a sequence number and a
content hash linking it to the previous record — a Merkle-flavoured audit
chain that can be independently verified from the logged data alone.

Intended use:
    log = EventLog()
    log.append("contribution_recorded", wallet="0xA...", amount=1000)
    log.append("proposal_evaluated", name="cut cohort 1965 by 2%", passes=False)
    log.verify()      # True if untampered
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, asdict, field
from typing import Any, Iterable


def _hash(prev_hash: str, payload: dict[str, Any]) -> str:
    serial = json.dumps(payload, sort_keys=True, default=str).encode()
    h = hashlib.sha256()
    h.update(prev_hash.encode())
    h.update(serial)
    return h.hexdigest()


@dataclass
class Event:
    seq: int
    timestamp: float
    event_type: str
    data: dict[str, Any]
    prev_hash: str
    hash: str


@dataclass
class EventLog:
    """Simple in-memory audit chain."""
    events: list[Event] = field(default_factory=list)

    GENESIS_HASH = "0" * 64

    def append(self, event_type: str, **data: Any) -> Event:
        prev_hash = self.events[-1].hash if self.events else self.GENESIS_HASH
        payload = {
            "seq": len(self.events),
            "event_type": event_type,
            "data": data,
            "prev_hash": prev_hash,
        }
        h = _hash(prev_hash, payload)
        event = Event(
            seq=len(self.events),
            timestamp=time.time(),
            event_type=event_type,
            data=data,
            prev_hash=prev_hash,
            hash=h,
        )
        self.events.append(event)
        return event

    # ----- inspection ------------------------------------------------------
    def __iter__(self) -> Iterable[Event]:
        return iter(self.events)

    def __len__(self) -> int:
        return len(self.events)

    def latest(self, k: int = 10) -> list[Event]:
        return self.events[-k:]

    # ----- verification ----------------------------------------------------
    def verify(self) -> bool:
        prev_hash = self.GENESIS_HASH
        for ev in self.events:
            payload = {
                "seq": ev.seq,
                "event_type": ev.event_type,
                "data": ev.data,
                "prev_hash": prev_hash,
            }
            expected = _hash(prev_hash, payload)
            if expected != ev.hash:
                return False
            prev_hash = ev.hash
        return True

    # ----- serialisation --------------------------------------------------
    def to_list(self) -> list[dict[str, Any]]:
        return [asdict(e) for e in self.events]
