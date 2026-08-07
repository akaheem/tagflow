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
        # Per-run memo of get_classifications, kept write-coherent in
        # _resolve_one. An entity reachable from several sources (or already
        # seen during source discovery) is then read from DataHub only once.
        self._class_cache: dict = {}

    def run(
        self,
        source_urns: Optional[Iterable[str]] = None,
        limit: Optional[int] = None,
    ) -> RunReport:
        """Execute a full propagation pass.

        Args:
            source_urns: explicit sources to propagate from. If omitted, sources
                are auto-discovered from datasets carrying sensitive tags/terms.
            limit: stop after this many new propagations are recorded. Used for
                scoped test writes and as a safety cap. ``None`` means no limit.
        """
        report = RunReport(dry_run=self.client.config.dry_run)

        if source_urns is None:
            source_urns = self._discover_sources()
        source_urns = list(source_urns)
        report.sources_scanned = len(source_urns)

        for source_urn in source_urns:
            if self._limit_reached(report, limit):
                break
            sensitive = self.reader.filter_sensitive(
                self._classifications(source_urn)
            )
            if not sensitive:
                continue

            downstream = self.lineage.downstream_of(source_urn)
            report.downstream_scanned += len(downstream)

            for entity in downstream:
                if self._limit_reached(report, limit):
                    break
                existing = self._classifications(entity.urn)
                existing_urns = {c.urn for c in existing}
                # Frozen snapshot of the target's *pre-existing* classifications
                # for this pass. Successful writes append to `existing` (the
                # cache) so later hops skip correctly, but conflict detection must
                # compare against this frozen copy — otherwise two sibling labels
                # from the same source (e.g. tags PII and GDPR) would flag each
                # other as conflicts once the first is written.
                conflict_basis = tuple(existing)

                for classification in sensitive:
                    if self._limit_reached(report, limit):
                        break
                    self._resolve_one(
                        report=report,
                        source_urn=source_urn,
                        target_urn=entity.urn,
                        hops=entity.hops,
                        classification=classification,
                        existing=existing,
                        existing_urns=existing_urns,
                        conflict_basis=conflict_basis,
                    )

        return report

    def _classifications(self, urn: str) -> List[Classification]:
        """Read an entity's classifications once per run, then serve from cache.

        Kept coherent with writes by _resolve_one, so the skip-if-present check
        stays correct when the same entity is reached again later in the run.
        """
        cached = self._class_cache.get(urn)
        if cached is None:
            cached = self.reader.get_classifications(urn)
            self._class_cache[urn] = cached
        return cached

    @staticmethod
    def _limit_reached(report: RunReport, limit: Optional[int]) -> bool:
        return limit is not None and len(report.propagations) >= limit

    def _resolve_one(
        self,
        report: RunReport,
        source_urn: str,
        target_urn: str,
        hops: int,
        classification: Classification,
        existing: List[Classification],
        existing_urns: set,
        conflict_basis: tuple,
    ) -> None:
        """Decide what to do with one (target, classification) pair."""
        # Already present downstream — nothing to do. Matched by URN, the true
        # identity of a tag/term, so this aligns with the writer's own
        # URN-level idempotency (a same-named but distinct label won't mask it).
        if classification.urn in existing_urns:
            return

        # Conflict detection: the target already carries a *different* sensitive
        # classification. We flag rather than stack a second one silently, since
        # contradictory sensitivity labels need human review.
        conflicting = self._find_conflict(classification, conflict_basis)
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
            # Keep the per-run cache coherent: this label now lives on the
            # target, so a later hop reaching it again correctly skips it.
            existing.append(classification)
            existing_urns.add(classification.urn)

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
            try:
                sensitive = self.reader.filter_sensitive(
                    self._classifications(urn)
                )
            except Exception:  # noqa: BLE001 - skip an unreadable entity, keep scanning
                continue
            if sensitive:
                sources.append(urn)

        return sources
