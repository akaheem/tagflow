"""Conflict-detection demo for TagFlow (one command, for the video).

Sets up a realistic clash and shows TagFlow handle it safely:

  1. Picks the source + a downstream dataset from the committed sample report.
  2. Seeds that downstream dataset with a DIFFERENT sensitive tag
     (``Confidential``) in place of the propagated one.
  3. Runs propagation. TagFlow sees the downstream asset already carries a
     conflicting sensitive label, FLAGS it for human review, and does NOT
     overwrite it.

Usage (in the Codespace):

    ~/dhenv/bin/python scripts/demo_conflict.py
"""

from __future__ import annotations

import json
import os

from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.metadata.schema_classes import GlobalTagsClass, TagAssociationClass

from tagflow.client import TagFlowClient
from tagflow.config import TagFlowConfig
from tagflow.lineage import LineageWalker
from tagflow.propagate import PropagationEngine
from tagflow.tags import TagReader

CONFLICT_TAG = "urn:li:tag:Confidential"
REPORT = os.path.join(
    os.path.dirname(__file__), "..", "examples", "propagation-report.json"
)


def _pick_source_and_target(engine, walker):
    """Return (source_urn, downstream_dataset_urn) for the demo.

    Prefers the canonical pair from the committed sample report so the demo is
    deterministic; falls back to live discovery if the report isn't present.
    """
    try:
        with open(os.path.normpath(REPORT), encoding="utf-8") as fh:
            props = json.load(fh)["propagations"]
        source = props[0]["source_urn"]
        target = next(
            p["target_urn"]
            for p in props
            if p["target_urn"].startswith("urn:li:dataset:")
        )
        return source, target
    except (OSError, KeyError, StopIteration, IndexError):
        pass

    sources = engine._discover_sources()
    if not sources:
        return None, None
    source = sources[0]
    for ent in walker.downstream_of(source):
        if ent.urn.startswith("urn:li:dataset:"):
            return source, ent.urn
    return source, None


def main() -> int:
    client = TagFlowClient(TagFlowConfig(dry_run=False))
    client.check_connection()

    engine = PropagationEngine(client)
    reader = TagReader(client)
    walker = LineageWalker(client)

    source, target = _pick_source_and_target(engine, walker)
    if not source or not target:
        print("Could not find a source + downstream dataset to demo. "
              "Run `propagate --apply` first.")
        return 1

    incoming = reader.filter_sensitive(reader.get_classifications(source))
    incoming_names = {c.name.lower() for c in incoming}
    incoming_label = ", ".join(sorted(c.name for c in incoming)) or "(none)"

    # Seed the target with a DIFFERENT sensitive tag. We drop the propagated
    # sensitive tag(s) here so the run exercises the CONFLICT path rather than
    # the "already present, skip" path.
    graph = client.graph
    existing = graph.get_aspect(target, GlobalTagsClass)
    kept = [
        assoc
        for assoc in (existing.tags if existing and existing.tags else [])
        if str(assoc.tag).split(":")[-1].lower() not in incoming_names
    ]
    kept.append(TagAssociationClass(tag=CONFLICT_TAG))
    graph.emit(
        MetadataChangeProposalWrapper(
            entityUrn=target, aspect=GlobalTagsClass(tags=kept)
        )
    )

    print("=" * 60)
    print("  Conflict demo — setup")
    print("=" * 60)
    print(f"  Source classification : {incoming_label}")
    print(f"  Seeded on downstream  : Confidential")
    print(f"  Target                : {target}")
    print("  Now running TagFlow — it should FLAG this, not overwrite it.\n")

    report = engine.run(source_urns=[source])
    print(report.render_console())

    if report.conflicts:
        print("RESULT: conflict correctly detected and left untouched. PASS")
        return 0
    print("RESULT: expected a conflict but none was flagged. CHECK")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
