"""
DRAS-5 Audit Trail (C3)

Implements the immutable, append-only transition log required by
constraint C3 (Audit Completeness).  Every state transition produces
a structured log entry that captures the full context of the decision.

Reference
---------
Tritham C, Snae Namahoot C (2026). DRAS-5, Definition 4.3 / Theorem 3.
"""

from __future__ import annotations

import json
import csv
import io
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple

from .states import RiskState

__all__ = ["AuditEntry", "AuditLog"]


@dataclass(frozen=True)
class AuditEntry:
    """A single, immutable audit record (C3).

    Matches the log tuple:
        l = <t, s_prev, s, rho, rho_eff, trigger, alpha, alpha2, valid>
    """

    entry_id: int
    timestamp: float
    from_state: RiskState
    to_state: RiskState
    risk_score: float
    rho_eff: float
    trigger: str                # "escalation", "timeout", "c5_deescalation", "human_gate"
    approval_1: bool = False
    approval_2: bool = False
    constraints_valid: Tuple[bool, ...] = (True, True, True, True, True)
    session_id: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["from_state"] = self.from_state.name
        d["to_state"] = self.to_state.name
        return d


class AuditLog:
    """Immutable, append-only transition log.

    Once an entry is appended it cannot be modified or removed.
    This guarantees C3: every transition has a corresponding log entry.
    """

    def __init__(self) -> None:
        self._entries: List[AuditEntry] = []
        self._next_id: int = 1

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def append(self, *,
               timestamp: float,
               from_state: RiskState,
               to_state: RiskState,
               risk_score: float,
               rho_eff: float,
               trigger: str,
               approval_1: bool = False,
               approval_2: bool = False,
               constraints_valid: Tuple[bool, ...] = (True,) * 5,
               session_id: str = "",
               note: str = "") -> AuditEntry:
        """Create and append a new audit entry.  Returns the entry."""
        entry = AuditEntry(
            entry_id=self._next_id,
            timestamp=timestamp,
            from_state=from_state,
            to_state=to_state,
            risk_score=risk_score,
            rho_eff=rho_eff,
            trigger=trigger,
            approval_1=approval_1,
            approval_2=approval_2,
            constraints_valid=constraints_valid,
            session_id=session_id,
            note=note,
        )
        self._entries.append(entry)
        self._next_id += 1
        return entry

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self):
        return iter(self._entries)

    def __getitem__(self, idx):
        return self._entries[idx]

    @property
    def entries(self) -> List[AuditEntry]:
        """Return a shallow copy so callers cannot mutate the log."""
        return list(self._entries)

    def filter_by_trigger(self, trigger: str) -> List[AuditEntry]:
        return [e for e in self._entries if e.trigger == trigger]

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def to_json(self, indent: int = 2) -> str:
        return json.dumps([e.to_dict() for e in self._entries], indent=indent)

    def to_csv(self) -> str:
        if not self._entries:
            return ""
        buf = io.StringIO()
        fields = list(self._entries[0].to_dict().keys())
        writer = csv.DictWriter(buf, fieldnames=fields)
        writer.writeheader()
        for e in self._entries:
            writer.writerow(e.to_dict())
        return buf.getvalue()
