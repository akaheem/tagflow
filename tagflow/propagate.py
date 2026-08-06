"""Core propagation engine for TagFlow.

Ties lineage, tag reads, and tag writes together into the central workflow:

    1. Discover source entities that carry sensitive classifications.
    2. Walk downstream lineage from each source.
    3. For each downstream entity, decide: propagate, skip (already present),
       or flag (conflicting classification already present).
    4. In apply mode, write the propagated classifications back to DataHub.
    5. Return a structured RunReport.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from tagflow.client import TagFlowClient
from tagflow.lineage import LineageWalker
from tagflow.report import Conflict, Failure, Propagation, RunReport
from tagflow.tags import Classification, TagReader, TagWriter


class PropagationEngine:
    """Orchestrates sensitive-classification propagation across lineage."""

    def __init__(self, client: TagFlowClient):
        self.client = client
        self.lineage = LineageWalker(client)
        self.reader = TagReader(client)
        self.writer = TagWriter(client)

    def run(self, source_urns: Optional[Iterable[str]] = None) -> RunReport:
        """Execute a full propagation pass.

        Args:
            source_urns: explicit sources to propagate from. If omitted, sources
                are auto-discovered from datasets carrying sensitive tags/terms.
        """
        report = RunReport(dry_run=self.client.config.dry_run)

        if source_urns is None:
            source_urns = self._discover_sources()
        source_urns = list(source_urns)
        report.sources_scanned = len(source_urns)

        for source_urn in source_urns:
            sensitive = self.reader.filter_sensitive(
                self.reader.get_classifications(source_urn)
            )
            if not sensitive:
                continue

            downstream = self.lineage.downstream_of(source_urn)
            report.downstream_scanned += len(downstream)

            for entity in downstream:
                existing = self.reader.get_classifications(entity.urn)
                existing_names = {c.name.lower() for c in existing}

                for classification in sensitive:
                    self._resolve_one(
                        report=report,
                        source_urn=source_urn,
                        target_urn=entity.urn,
                        hops=entity.hops,
                        classification=classification,
                        existing=existing,
                        existing_names=existing_names,
                    )

        return report

    def _resolve_one(
        self,
        report: RunReport,
        source_urn: str,
        target_urn: str,
        hops: int,
        classification: Classification,
        existing: List[Classification],
        existing_names: set,
    ) -> None:
        """Decide what to do with one (target, classification) pair."""
        # Already present downstream — nothing to do.
        if classification.name.lower() in existing_names:
            return

        # Conflict detection: the target already carries a *different* sensitive
        # classification. We flag rather than stack a second one silently, since
        # contradictory sensitivity labels need human review.
        conflicting = self._find_conflict(classification, existing)
        if conflicting is not None:
            report.conflicts.append(
                Conflict(
                    target_urn=target_urn,
                    incoming_classification=classification.name,
                    existing_classification=conflicting.name,
                    source_urn=source_urn,
                    note="Downstream entity already carries a different "
                    "sensitive classification; left untouched for review.",
                )
            )
            return

        # Clear to propagate.
        applied = False
        if not self.client.config.dry_run:
            try:
                wrote = self.writer.apply_classification(target_urn, classification)
            except Exception as exc:  # noqa: BLE001 - isolate one entity's failure
                report.failures.append(
                    Failure(
                        target_urn=target_urn,
                        classification=classification.name,
                        classification_urn=classification.urn,
                        source_urn=source_urn,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
                return
            # Already present at the URN level (idempotent no-op) — nothing
            # actually changed, so don't record it as a propagation.
            if not wrote:
                return
            applied = True

        report.propagations.append(
            Propagation(
                classification=classification.name,
                classification_urn=classification.urn,
                source_urn=source_urn,
                target_urn=target_urn,
                hops=hops,
                kind=classification.kind,
                applied=applied,
            )
        )

    def _find_conflict(
        self, incoming: Classification, existing: List[Classification]
    ) -> Optional[Classification]:
        """Return an existing sensitive classification that conflicts.

        A conflict is any *other* sensitive classification of the same kind
        already on the target — e.g. a column tagged `Public` receiving `PII`.
        """
        for c in existing:
            if not self.client.config.is_sensitive(c.name):
                continue
            if c.name.lower() == incoming.name.lower():
                continue
            if c.kind == incoming.kind:
                return c
        return None

    def _discover_sources(self) -> List[str]:
        """Find datasets that carry at least one sensitive classification.

        These become the roots from which classifications flow downstream.
        """
        graph = self.client.graph
        sources: List[str] = []

        for urn in graph.get_urns_by_filter(entity_types=["dataset"]):
            sensitive = self.reader.filter_sensitive(
                self.reader.get_classifications(urn)
            )
            if sensitive:
                sources.append(urn)

        return sources
