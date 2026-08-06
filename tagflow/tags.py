"""Tag and glossary-term read/write operations for TagFlow.

Wraps the DataHub SDK so the propagation engine doesn't touch URNs or aspect
classes directly. Exposes three operations: read classifications on an entity,
decide which ones are sensitive, and write new classifications back.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List

from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.metadata.schema_classes import (
    AuditStampClass,
    GlobalTagsClass,
    GlossaryTermAssociationClass,
    GlossaryTermsClass,
    TagAssociationClass,
)

from tagflow.client import TagFlowClient


@dataclass
class Classification:
    """A single tag or glossary term attached to an entity."""

    name: str          # human-readable tail (e.g. "PII")
    urn: str
    kind: str          # "tag" or "term"


class TagReader:
    """Reads tags and glossary terms from DataHub entities."""

    def __init__(self, client: TagFlowClient):
        self.client = client

    def get_classifications(self, entity_urn: str) -> List[Classification]:
        """Return all tags + glossary terms on ``entity_urn``."""
        graph = self.client.graph
        classifications: List[Classification] = []

        # Tags
        tags_aspect = graph.get_aspect(entity_urn, GlobalTagsClass)
        if tags_aspect and tags_aspect.tags:
            for tag_assoc in tags_aspect.tags:
                tag_urn = str(tag_assoc.tag)
                classifications.append(
                    Classification(
                        name=_urn_tail(tag_urn),
                        urn=tag_urn,
                        kind="tag",
                    )
                )

        # Glossary terms
        terms_aspect = graph.get_aspect(entity_urn, GlossaryTermsClass)
        if terms_aspect and terms_aspect.terms:
            for term_assoc in terms_aspect.terms:
                term_urn = str(term_assoc.urn)
                classifications.append(
                    Classification(
                        name=_urn_tail(term_urn),
                        urn=term_urn,
                        kind="term",
                    )
                )

        return classifications

    def filter_sensitive(
        self, classifications: List[Classification]
    ) -> List[Classification]:
        """Return only the classifications matching the sensitivity policy."""
        return [
            c
            for c in classifications
            if self.client.config.is_sensitive(c.name)
        ]


class TagWriter:
    """Writes tags and glossary terms back to DataHub via low-level aspect emit.

    Uses ``MetadataChangeProposalWrapper`` against the raw ``globalTags`` /
    ``glossaryTerms`` aspects so it writes uniformly to *any* entity type —
    datasets, charts, dashboards — unlike the high-level SDK helpers, which are
    dataset-oriented. Writes are idempotent: a classification already present on
    the target is left untouched.
    """

    # Attribution actor stamped on term changes, so the provenance of every
    # classification TagFlow propagates is visible in the DataHub UI.
    ACTOR_URN = "urn:li:corpuser:tagflow"

    def __init__(self, client: TagFlowClient):
        self.client = client

    def apply_classification(
        self, target_urn: str, classification: Classification
    ) -> bool:
        """Write a tag or term to ``target_urn``.

        Returns True if a new association was written, False if it was already
        present (idempotent no-op). Raises on write failure so the caller can
        record it per-entity.
        """
        if self.client.config.dry_run:
            return False

        if classification.kind == "tag":
            return self._apply_tag(target_urn, classification.urn)
        if classification.kind == "term":
            return self._apply_term(target_urn, classification.urn)
        raise ValueError(f"Unknown classification kind: {classification.kind}")

    def _apply_tag(self, target_urn: str, tag_urn: str) -> bool:
        graph = self.client.graph
        aspect = graph.get_aspect(target_urn, GlobalTagsClass)
        if aspect is None:
            aspect = GlobalTagsClass(tags=[])

        if any(str(assoc.tag) == tag_urn for assoc in aspect.tags):
            return False  # already present — idempotent no-op

        aspect.tags.append(TagAssociationClass(tag=tag_urn))
        graph.emit(
            MetadataChangeProposalWrapper(entityUrn=target_urn, aspect=aspect)
        )
        return True

    def _apply_term(self, target_urn: str, term_urn: str) -> bool:
        graph = self.client.graph
        aspect = graph.get_aspect(target_urn, GlossaryTermsClass)
        if aspect is None:
            aspect = GlossaryTermsClass(terms=[], auditStamp=self._audit_stamp())

        if any(str(assoc.urn) == term_urn for assoc in aspect.terms):
            return False  # already present — idempotent no-op

        aspect.terms.append(GlossaryTermAssociationClass(urn=term_urn))
        graph.emit(
            MetadataChangeProposalWrapper(entityUrn=target_urn, aspect=aspect)
        )
        return True

    def _audit_stamp(self) -> AuditStampClass:
        return AuditStampClass(time=int(time.time() * 1000), actor=self.ACTOR_URN)


def _urn_tail(urn: str) -> str:
    """Extract the human-readable tail from a DataHub URN.

    Example: urn:li:tag:PII -> PII
             urn:li:glossaryTerm:Classification.Sensitive -> Classification.Sensitive
    """
    if not urn:
        return ""
    return urn.split(":")[-1].rstrip(")")
