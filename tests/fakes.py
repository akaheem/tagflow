"""In-memory fakes for the DataHub SDK boundary.

TagFlow reaches DataHub through exactly two objects: the low-level ``graph``
(aspect read/write + URN filtering) and the high-level ``sdk`` (lineage). These
fakes stand in for both, so the *real* ``TagReader``, ``TagWriter``,
``LineageWalker`` and ``PropagationEngine`` run unchanged against deterministic
in-memory metadata — no DataHub, no network. Emitted writes are reflected on
subsequent reads, so idempotency and write-coherence are exercised for real
rather than mocked away.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from datahub.metadata.schema_classes import (
    AuditStampClass,
    GlobalTagsClass,
    GlossaryTermAssociationClass,
    GlossaryTermsClass,
    TagAssociationClass,
)

from tagflow.config import TagFlowConfig


class FakeGraph:
    """Stands in for ``DataHubGraph``: aspect store + emit + URN filter."""

    def __init__(
        self,
        tags: Optional[Dict[str, List[str]]] = None,
        terms: Optional[Dict[str, List[str]]] = None,
        dataset_urns: Optional[List[str]] = None,
        fail_urns: Optional[List[str]] = None,
        read_fail_urns: Optional[List[str]] = None,
    ):
        self._tags = {u: list(v) for u, v in (tags or {}).items()}
        self._terms = {u: list(v) for u, v in (terms or {}).items()}
        self._dataset_urns = list(dataset_urns or [])
        self._fail_urns = set(fail_urns or [])
        self._read_fail_urns = set(read_fail_urns or [])
        self.emit_calls: List[str] = []

    # --- reads -------------------------------------------------------------
    def get_aspect(self, urn: str, aspect_class):
        if urn in self._read_fail_urns:
            raise RuntimeError(f"simulated read failure for {urn}")
        if aspect_class is GlobalTagsClass:
            urns = self._tags.get(urn)
            if not urns:
                return None
            return GlobalTagsClass(tags=[TagAssociationClass(tag=u) for u in urns])
        if aspect_class is GlossaryTermsClass:
            urns = self._terms.get(urn)
            if not urns:
                return None
            return GlossaryTermsClass(
                terms=[GlossaryTermAssociationClass(urn=u) for u in urns],
                auditStamp=AuditStampClass(time=0, actor="urn:li:corpuser:test"),
            )
        return None

    def get_urns_by_filter(self, entity_types=None) -> List[str]:
        return list(self._dataset_urns)

    def get_config(self) -> dict:
        return {}

    # --- writes ------------------------------------------------------------
    def emit(self, mcp) -> None:
        urn = mcp.entityUrn
        if urn in self._fail_urns:
            raise RuntimeError(f"simulated GMS write failure for {urn}")
        aspect = mcp.aspect
        if isinstance(aspect, GlobalTagsClass):
            self._tags[urn] = [str(a.tag) for a in aspect.tags]
        elif isinstance(aspect, GlossaryTermsClass):
            self._terms[urn] = [str(a.urn) for a in aspect.terms]
        self.emit_calls.append(urn)

    # --- assertions helpers ------------------------------------------------
    def tags_on(self, urn: str) -> List[str]:
        return list(self._tags.get(urn, []))

    def terms_on(self, urn: str) -> List[str]:
        return list(self._terms.get(urn, []))


class _LineageRec:
    """One downstream hit, shaped like the SDK's lineage result rows."""

    def __init__(self, urn: str, hops: int):
        self.urn = urn
        self.hops = hops
        self.platform = ""
        self.name = ""


class _FakeLineage:
    def __init__(self, mapping: Dict[str, List[Tuple[str, int]]]):
        self._mapping = mapping

    def get_lineage(self, source_urn, direction, max_hops):
        recs = self._mapping.get(source_urn, [])
        return [_LineageRec(u, h) for (u, h) in recs if h <= max_hops]


class _FakeSdk:
    def __init__(self, lineage: _FakeLineage):
        self.lineage = lineage


class FakeClient:
    """Duck-typed stand-in for ``TagFlowClient``: config + graph + sdk."""

    def __init__(self, config: TagFlowConfig, graph: FakeGraph, sdk: _FakeSdk):
        self.config = config
        self.graph = graph
        self.sdk = sdk


def build_client(
    *,
    tags=None,
    terms=None,
    lineage=None,
    dataset_urns=None,
    fail_urns=None,
    read_fail_urns=None,
    dry_run=False,
    max_hops=3,
    sensitive_keywords=None,
) -> FakeClient:
    """Assemble a ``FakeClient`` seeded with in-memory metadata.

    tags/terms   -- {entity_urn: [classification_urn, ...]} initial state.
    lineage      -- {source_urn: [(downstream_urn, hops), ...]}.
    dataset_urns -- what ``get_urns_by_filter`` returns (source auto-discovery).
    fail_urns    -- entities whose write ``emit`` raises.
    read_fail_urns -- entities whose ``get_aspect`` raises.
    """
    config = TagFlowConfig(dry_run=dry_run, max_hops=max_hops)
    if sensitive_keywords is not None:
        config.sensitive_keywords = list(sensitive_keywords)
    graph = FakeGraph(
        tags=tags,
        terms=terms,
        dataset_urns=dataset_urns,
        fail_urns=fail_urns,
        read_fail_urns=read_fail_urns,
    )
    sdk = _FakeSdk(_FakeLineage(lineage or {}))
    return FakeClient(config, graph, sdk)
