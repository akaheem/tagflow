"""Tag and glossary-term read/write operations for TagFlow.

Wraps the DataHub SDK so the propagation engine doesn't touch URNs or aspect
classes directly. Exposes three operations: read classifications on an entity,
decide which ones are sensitive, and write new classifications back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from datahub.metadata.schema_classes import GlobalTagsClass, GlossaryTermsClass
from datahub.sdk import TagUrn, GlossaryTermUrn

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
    """Writes tags and glossary terms back to DataHub."""

    def __init__(self, client: TagFlowClient):
        self.client = client

    def apply_classification(
        self, target_urn: str, classification: Classification
    ) -> None:
        """Write a tag or term to ``target_urn``. Raises on failure."""
        if self.client.config.dry_run:
            return

        sdk = self.client.sdk
        dataset = sdk.entities.get(target_urn)

        if classification.kind == "tag":
            dataset.add_tag(TagUrn(classification.urn))
        elif classification.kind == "term":
            dataset.add_term(GlossaryTermUrn(classification.urn))
        else:
            raise ValueError(f"Unknown classification kind: {classification.kind}")

        sdk.entities.update(dataset)


def _urn_tail(urn: str) -> str:
    """Extract the human-readable tail from a DataHub URN.

    Example: urn:li:tag:PII -> PII
             urn:li:glossaryTerm:Classification.Sensitive -> Classification.Sensitive
    """
    if not urn:
        return ""
    return urn.split(":")[-1].rstrip(")")
