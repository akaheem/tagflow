"""Reset the demo graph so the full propagation can be recorded live.

Removes the tags TagFlow added downstream (the propagated PII tag and the
``Confidential`` seed from the conflict demo), restoring the "before" state.
The source's own tag is left intact, so a fresh ``propagate --apply`` re-runs
the entire flow for the camera.

Usage (in the Codespace):

    ~/dhenv/bin/python scripts/reset_demo.py
"""

from __future__ import annotations

import json
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Silence the SDK's per-traversal multi-hop lineage warning.
logging.getLogger("datahub").setLevel(logging.ERROR)

from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.metadata.schema_classes import GlobalTagsClass

from tagflow.client import TagFlowClient
from tagflow.config import TagFlowConfig
from tagflow.lineage import LineageWalker
from tagflow.propagate import PropagationEngine

CONFLICT_TAG = "urn:li:tag:Confidential"
REPORT = os.path.join(
    os.path.dirname(__file__), "..", "examples", "propagation-report.json"
)


def main() -> int:
    client = TagFlowClient(TagFlowConfig(dry_run=False))
    client.check_connection()
    engine = PropagationEngine(client)
    walker = LineageWalker(client)
    graph = client.graph

    # Tags to strip from downstream: the propagated PII tag + the conflict seed.
    remove_urns = {CONFLICT_TAG}
    source = None
    try:
        with open(os.path.normpath(REPORT), encoding="utf-8") as fh:
            props = json.load(fh)["propagations"]
        source = props[0]["source_urn"]
        remove_urns.add(props[0]["classification_urn"])
    except (OSError, KeyError, IndexError):
        pass

    sources = [source] if source else engine._discover_sources()
    if not sources:
        print("No source found — nothing to reset.")
        return 1

    cleaned = 0
    seen = set()
    for src in sources:
        for ent in walker.downstream_of(src):
            if ent.urn in seen or ent.urn == src:
                continue
            seen.add(ent.urn)
            aspect = graph.get_aspect(ent.urn, GlobalTagsClass)
            if not aspect or not aspect.tags:
                continue
            kept = [a for a in aspect.tags if str(a.tag) not in remove_urns]
            if len(kept) != len(aspect.tags):
                graph.emit(
                    MetadataChangeProposalWrapper(
                        entityUrn=ent.urn, aspect=GlobalTagsClass(tags=kept)
                    )
                )
                cleaned += 1

    print(f"Reset complete — removed demo tags from {cleaned} downstream assets.")
    print("Record now:  propagate --dry-run  ->  --apply  ->  check the DataHub UI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
