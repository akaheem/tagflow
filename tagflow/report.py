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
class Failure:
    """A propagation that was attempted in apply mode but could not be written."""

    target_urn: str
    classification: str
    classification_urn: str
    source_urn: str
    error: str


@dataclass
class RunReport:
    """Aggregated outcome of a TagFlow propagation run."""

    dry_run: bool
    sources_scanned: int = 0
    downstream_scanned: int = 0
    propagations: List[Propagation] = field(default_factory=list)
    conflicts: List[Conflict] = field(default_factory=list)
    failures: List[Failure] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "summary": {
                "sources_scanned": self.sources_scanned,
                "downstream_scanned": self.downstream_scanned,
                "propagations": len(self.propagations),
                "written": sum(1 for p in self.propagations if p.applied),
                "conflicts": len(self.conflicts),
                "failures": len(self.failures),
            },
            "propagations": [asdict(p) for p in self.propagations],
            "conflicts": [asdict(c) for c in self.conflicts],
            "failures": [asdict(f) for f in self.failures],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def render_console(self) -> str:
        """Human-readable summary for the terminal / demo video."""
        mode = "DRY RUN (no writes)" if self.dry_run else "APPLIED (written to DataHub)"
        written = sum(1 for p in self.propagations if p.applied)
        lines = [
            "",
            "=" * 60,
            f"  TagFlow propagation report — {mode}",
            "=" * 60,
            f"  Sources scanned      : {self.sources_scanned}",
            f"  Downstream scanned   : {self.downstream_scanned}",
            (
                f"  Written to DataHub   : {written}"
                if not self.dry_run
                else f"  Would write          : {len(self.propagations)}"
            ),
            f"  Conflicts flagged    : {len(self.conflicts)}",
            f"  Failures             : {len(self.failures)}",
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

        if self.failures:
            lines.append("-" * 60)
            lines.append("  FAILURES (write did not succeed):")
            for f in self.failures:
                lines.append(
                    f"    x {_short(f.target_urn)} [{f.classification}]: {f.error}"
                )

        lines.append("=" * 60)
        lines.append("")
        return "\n".join(lines)


def _short(urn: str) -> str:
    """Shorten a URN to a readable label for console output.

    Handles the URN shapes TagFlow touches:
      dataset   -> last two dotted name segments (``...analytics.order_details``
                   -> ``analytics.order_details``)
      chart     -> ``tool:id``                  (``looker:dashboard_element_1``)
      dashboard -> ``tool:id``
    Falls back to the last comma-field for anything else.
    """
    if not urn:
        return "?"

    parts = urn.split(":", 3)
    entity_type = parts[2] if len(parts) >= 3 else ""

    if "(" in urn:
        inner = urn[urn.find("(") + 1 : urn.rfind(")")]
    else:
        inner = urn
    fields = inner.split(",")

    if entity_type == "dataset" and len(fields) >= 2:
        name = fields[1]
        segs = name.split(".")
        return ".".join(segs[-2:]) if len(segs) >= 2 else name

    if entity_type in ("chart", "dashboard") and len(fields) >= 2:
        tool = fields[0].split(":")[-1]          # strip any urn:li:dataPlatform: prefix
        ident = fields[-1].split(".")[-1]
        if len(ident) > 24:
            ident = ident[:21] + "..."
        return f"{tool}:{ident}"

    return fields[-1] if fields else urn
