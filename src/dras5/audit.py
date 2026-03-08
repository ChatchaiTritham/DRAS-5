"""
Audit Logging
=============

Comprehensive audit trail for state machine operations.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import json
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["AuditEntry", "AuditLogger", "AuditLog"]


@dataclass(frozen=True)
class AuditEntry:
    """Single audit log entry"""
    timestamp: float
    event_type: str
    from_state: Optional[str]
    to_state: Optional[str]
    risk_score: float
    trigger: str
    approved: bool
    user_id: Optional[str]
    metadata: Dict[str, Any]
    entry_id: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2)


class AuditLogger:
    """
    Audit logger for state machine operations.

    Provides immutable audit trail with multiple output formats.
    """

    def __init__(
        self,
        log_file: Optional[str] = None,
        enable_file_logging: bool = True
    ):
        """
        Initialize audit logger.

        Args:
            log_file: Path to audit log file
            enable_file_logging: Enable writing to file
        """
        self._entries: List[AuditEntry] = []
        self.log_file = Path(log_file) if log_file else None
        self.enable_file_logging = enable_file_logging

        if self.enable_file_logging and self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"AuditLogger initialized (file: {log_file})")

    def log(
        self,
        event_type: str,
        from_state: Optional[str] = None,
        to_state: Optional[str] = None,
        risk_score: float = 0.0,
        trigger: str = "",
        approved: bool = False,
        user_id: Optional[str] = None,
        **metadata
    ):
        """
        Log audit entry.

        Args:
            event_type: Type of event (transition, update, etc.)
            from_state: Source state
            to_state: Target state
            risk_score: Associated risk score
            trigger: What triggered the event
            approved: Whether event was approved
            user_id: User who initiated event
            **metadata: Additional metadata
        """
        entry = AuditEntry(
            timestamp=time.time(),
            event_type=event_type,
            from_state=from_state,
            to_state=to_state,
            risk_score=risk_score,
            trigger=trigger,
            approved=approved,
            user_id=user_id,
            metadata=metadata
        )

        self._entries.append(entry)

        if self.enable_file_logging and self.log_file:
            self._write_to_file(entry)

        logger.debug(f"Audit entry logged: {event_type}")

    def _write_to_file(self, entry: AuditEntry):
        """Write entry to log file"""
        try:
            with open(self.log_file, 'a') as f:
                f.write(entry.to_json() + '\n')
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")

    def get_entries(
        self,
        event_type: Optional[str] = None,
        from_state: Optional[str] = None,
        to_state: Optional[str] = None,
        min_timestamp: Optional[float] = None,
        max_timestamp: Optional[float] = None
    ) -> List[AuditEntry]:
        """
        Query audit entries with filters.

        Args:
            event_type: Filter by event type
            from_state: Filter by source state
            to_state: Filter by target state
            min_timestamp: Minimum timestamp
            max_timestamp: Maximum timestamp

        Returns:
            List of matching entries
        """
        results = self._entries

        if event_type:
            results = [e for e in results if e.event_type == event_type]

        if from_state:
            results = [e for e in results if e.from_state == from_state]

        if to_state:
            results = [e for e in results if e.to_state == to_state]

        if min_timestamp:
            results = [e for e in results if e.timestamp >= min_timestamp]

        if max_timestamp:
            results = [e for e in results if e.timestamp <= max_timestamp]

        return results

    def export_json(self, filepath: str):
        """Export all entries to JSON file"""
        data = [entry.to_dict() for entry in self._entries]

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Audit log exported to {filepath}")

    def export_csv(self, filepath: str):
        """Export all entries to CSV file"""
        import csv

        if not self._entries:
            logger.warning("No entries to export")
            return

        fieldnames = list(self._entries[0].to_dict().keys())

        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for entry in self._entries:
                row = entry.to_dict()
                # Convert metadata dict to JSON string for CSV
                row['metadata'] = json.dumps(row['metadata'])
                writer.writerow(row)

        logger.info(f"Audit log exported to CSV: {filepath}")

    def get_statistics(self) -> Dict[str, Any]:
        """Get audit statistics"""
        if not self._entries:
            return {}

        event_counts = {}
        for entry in self._entries:
            event_counts[entry.event_type] = event_counts.get(entry.event_type, 0) + 1

        transition_counts = {}
        for entry in self._entries:
            if entry.from_state and entry.to_state:
                key = f"{entry.from_state}→{entry.to_state}"
                transition_counts[key] = transition_counts.get(key, 0) + 1

        return {
            "total_entries": len(self._entries),
            "event_type_counts": event_counts,
            "transition_counts": transition_counts,
            "first_timestamp": min(e.timestamp for e in self._entries),
            "last_timestamp": max(e.timestamp for e in self._entries),
            "approval_rate": sum(1 for e in self._entries if e.approved) / len(self._entries),
        }

    def verify_completeness(self) -> bool:
        """Verify audit trail completeness"""
        # Check for gaps in timestamps
        timestamps = sorted(e.timestamp for e in self._entries)

        for i in range(1, len(timestamps)):
            # Flag if gap > 1 hour (configurable)
            if timestamps[i] - timestamps[i-1] > 3600:
                logger.warning(
                    f"Audit trail gap detected: "
                    f"{timestamps[i] - timestamps[i-1]:.1f}s"
                )
                return False

        return True

    def clear(self):
        """Clear all entries (use with caution!)"""
        logger.warning("Clearing audit log!")
        self._entries = []

    def append(
        self,
        timestamp: float,
        from_state: Any,
        to_state: Any,
        risk_score: float,
        rho_eff: float = 0.0,
        trigger: str = "",
        approved: bool = False,
        user_id: Optional[str] = None,
    ) -> AuditEntry:
        """Append an audit entry.

        Args:
            from_state: Source state (RiskState enum or string). Converted to
                string via .name for enums, str() otherwise.
            to_state: Target state (RiskState enum or string). Same conversion.
        """
        entry = AuditEntry(
            timestamp=timestamp,
            event_type="transition",
            from_state=from_state.name if hasattr(from_state, 'name') else str(from_state),
            to_state=to_state.name if hasattr(to_state, 'name') else str(to_state),
            risk_score=risk_score,
            trigger=trigger,
            approved=approved,
            user_id=user_id,
            metadata={"rho_eff": rho_eff},
            entry_id=len(self._entries) + 1,
        )
        self._entries.append(entry)
        return entry

    def __len__(self) -> int:
        """Return number of entries."""
        return len(self._entries)

    @property
    def entries(self) -> List[AuditEntry]:
        """Get entries (returns a copy for immutability)."""
        return list(self._entries)

    @entries.setter
    def entries(self, value: List[AuditEntry]):
        """Set entries (compatibility property)."""
        self._entries = list(value)

    def to_json(self) -> str:
        """Export to JSON string (compatibility method)."""
        return json.dumps([entry.to_dict() for entry in self._entries], indent=2)

    def filter_by_trigger(self, trigger: str) -> List[AuditEntry]:
        """Filter entries by trigger (compatibility method)."""
        return [e for e in self._entries if e.trigger == trigger]

    def to_csv(self) -> str:
        """Export to CSV string (compatibility method)."""
        if not self._entries:
            return ""
        import io
        import csv
        output = io.StringIO()
        fieldnames = ['entry_id', 'timestamp', 'event_type', 'from_state', 'to_state', 
                      'risk_score', 'trigger', 'approved', 'user_id']
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for entry in self._entries:
            writer.writerow({
                'entry_id': getattr(entry, 'entry_id', 0),
                'timestamp': entry.timestamp,
                'event_type': entry.event_type,
                'from_state': entry.from_state,
                'to_state': entry.to_state,
                'risk_score': entry.risk_score,
                'trigger': entry.trigger,
                'approved': entry.approved,
                'user_id': entry.user_id,
            })
        return output.getvalue()


AuditLog = AuditLogger
