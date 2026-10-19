"""Evidence layer (E1): append-only journal + derived verdict.

Public surface frozen by ``docs/dev/EVIDENCE.md`` (ADR-008):

- :class:`EvidenceRecord` — one content-free evidence fact.
- :func:`record_evidence` — append + fail-open trace emission.
- :func:`verdict` — pure read of the latest record for a ``spec_id``.
- :func:`reset_journal` — tests only.
"""

from .journal import EvidenceRecord, record_evidence, reset_journal, verdict

__all__ = ["EvidenceRecord", "record_evidence", "reset_journal", "verdict"]
