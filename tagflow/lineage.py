"""Lineage traversal for TagFlow.

Wraps the DataHub high-level SDK's ``get_lineage`` so the propagation engine can
ask a simple question: *given a source dataset, what is downstream of it, and
how many hops away?*
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from tagflow.client import TagFlowClient


@dataclass
class DownstreamEntity:
    """A single downstream entity discovered during lineage traversal."""

    urn: str
    hops: int
    platform: str = ""
    name: str = ""


class LineageWalker:
    """Discovers downstream entities for a given source using DataHub lineage."""

    def __init__(self, client: TagFlowClient):
        self.client = client
        self.max_hops = client.config.max_hops

    def downstream_of(self, source_urn: str) -> List[DownstreamEntity]:
        """Return all datasets downstream of ``source_urn`` within max_hops.

        Uses the SDK's server-side multi-hop traversal so we don't hand-roll a
        BFS. Results are returned nearest-first so propagation can prefer the
        closest classification when resolving conflicts.
        """
        results = self.client.sdk.lineage.get_lineage(
            source_urn=source_urn,
            direction="downstream",
            max_hops=self.max_hops,
        )

        downstream: List[DownstreamEntity] = []
        for r in results:
            downstream.append(
                DownstreamEntity(
                    urn=str(getattr(r, "urn", "")),
                    hops=int(getattr(r, "hops", 0) or 0),
                    platform=str(getattr(r, "platform", "") or ""),
                    name=str(getattr(r, "name", "") or ""),
                )
            )

        downstream.sort(key=lambda d: d.hops)
        return downstream
