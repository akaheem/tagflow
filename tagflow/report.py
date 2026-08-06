"""Run reporting for TagFlow.

Turns the structured result of a propagation run into (a) a readable console
summary and (b) a JSON artifact suitable for committing to ``examples/`` so
hackathon judges can evaluate output quality without running the tool.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import List


@dataclass
class Propagation:
    """A single classification propagated from a source to a target."""

    classification: str          # tag/term name, e.g. "PII"
    classification_urn: str
    source_urn: str
    target_urn: str
    hops: int
    kind: str                    # "tag" or "term"
    applied: bool                # False in dry-run mode


@dataclass
class Conflict:
    """A downstream entity that already carries a differing classification."""

    target_urn: str
    incoming_classification: str
    existing_classification: str
    source_urn: str
    note: str = ""


@dataclass
class RunReport:
    """Aggregated outcome of a TagFlow propagation run."""

    dry_run: bool
    sources_scanned: int = 0
    downstream_scanned: int = 0
    propagations: List[Propagation] = field(default_factory=list)
    conflicts: List[Conflict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "summary": {
                "sources_scanned": self.sources_scanned,
                "downstream_scanned": self.downstream_scanned,
                "propagations": len(self.propagations),
                "conflicts": len(self.conflicts),
            },
            "propagations": [asdict(p) for p in self.propagations],
            "conflicts": [asdict(c) for c in self.conflicts],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def render_console(self) -> str:
        """Human-readable summary for the terminal / demo video."""
        mode = "DRY RUN (no writes)" if self.dry_run else "APPLIED (written to DataHub)"
        lines = [
            "",
            "=" * 60,
            f"  TagFlow propagation report — {mode}",
            "=" * 60,
            f"  Sources scanned      : {self.sources_scanned}",
            f"  Downstream scanned   : {self.downstream_scanned}",
            f"  Classifications flowed: {len(self.propagations)}",
            f"  Conflicts flagged    : {len(self.conflicts)}",
            "-" * 60,
        ]

        if self.propagations:
            lines.append("  PROPAGATIONS:")
            for p in self.propagations:
                arrow = "->" if p.applied else "..(dry)..>"
                lines.append(
                    f"    [{p.kind}] {p.classification} {arrow} "
                    f"{_short(p.target_urn)} (+{p.hops} hop)"
                )
        else:
            lines.append("  No new classifications to propagate.")

        if self.conflicts:
            lines.append("-" * 60)
            lines.append("  CONFLICTS (left untouched, needs human review):")
            for c in self.conflicts:
                lines.append(
                    f"    ! {_short(c.target_urn)}: incoming "
                    f"'{c.incoming_classification}' vs existing "
                    f"'{c.existing_classification}'"
                )

        lines.append("=" * 60)
        lines.append("")
        return "\n".join(lines)


def _short(urn: str) -> str:
    """Shorten a URN to its readable tail for console output."""
    if not urn:
        return "?"
    tail = urn.rstrip(")").split(",")
    return tail[-2] if len(tail) >= 2 else urn
