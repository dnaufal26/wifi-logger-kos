"""Bentuk riwayat downtime dari sampel yang sudah diurutkan menurut waktu."""
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from diagnostics import DOWN_STATES, UP_STATES

MIN_DOWNTIME_SECONDS = 60
GAP_SECONDS = 15


@dataclass
class Incident:
    started_at: datetime
    last_failed_at: datetime
    recovered_at: datetime | None
    state: str
    patterns: dict[str, int]

    @property
    def observed_seconds(self):
        end = self.recovered_at or self.last_failed_at
        return int((end - self.started_at).total_seconds())

    @property
    def diagnosis_code(self):
        if len(self.patterns) > 1:
            return "MIXED"
        return next(iter(self.patterns))


@dataclass
class History:
    incidents: list[Incident] = field(default_factory=list)
    gaps: list[tuple[datetime, datetime]] = field(default_factory=list)
    short_failures: int = 0
    pending_seconds: int | None = None


def analyze_samples(samples, now):
    """samples berisi pasangan (datetime, kode diagnosis)."""
    history = History()
    failures = []
    first_recovery = None
    previous = None

    def confirmed():
        return bool(failures) and (
            failures[-1][0] - failures[0][0]
        ).total_seconds() >= MIN_DOWNTIME_SECONDS

    def finish(state, recovered_at=None):
        nonlocal first_recovery
        if confirmed():
            history.incidents.append(Incident(
                failures[0][0], failures[-1][0], recovered_at, state,
                dict(Counter(code for _, code in failures)),
            ))
        elif failures and state == "Pulih":
            history.short_failures += 1
        failures.clear()
        first_recovery = None

    for timestamp, code in samples:
        if previous is not None and (timestamp - previous).total_seconds() > GAP_SECONDS:
            history.gaps.append((previous, timestamp))
            finish("Pemulihan belum diketahui")

        if code in DOWN_STATES:
            failures.append((timestamp, code))
            first_recovery = None
        elif code in UP_STATES:
            if confirmed():
                if first_recovery is None:
                    first_recovery = timestamp
                else:
                    finish("Pulih", first_recovery)
            else:
                finish("Pulih", timestamp)
        else:
            finish("Pemulihan belum diketahui")
        previous = timestamp

    if previous is not None and (now - previous).total_seconds() > GAP_SECONDS:
        history.gaps.append((previous, now))
        finish("Pemulihan belum diketahui")
    elif confirmed():
        finish("Menunggu konfirmasi pulih" if first_recovery else "Berlangsung")
    elif failures:
        history.pending_seconds = int((failures[-1][0] - failures[0][0]).total_seconds())

    return history
