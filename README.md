# TagFlow

**Governance that follows your data.** TagFlow is a governance agent that reads
lineage from [DataHub](https://datahub.com), finds sensitive and glossary
classifications on upstream columns, and **propagates them downstream** to
untagged columns — then writes the results back to the catalog so the next
person or agent inherits the knowledge.

> Governance usually stops at the source table. A `PII` tag lives on
> `users.email`, but the ten downstream tables and dashboards built from it are
> unlabeled. TagFlow closes that gap by walking DataHub lineage and flowing tags
> to where the data actually went.

**[Watch the 3-minute demo](#)** &nbsp;·&nbsp; before → `--apply` → after in the DataHub UI. *(link added on submission)*

---

## Why it matters

Data teams tag sensitive fields at the source, but those tags rarely follow the
data as it's copied, joined, and aggregated downstream. The result: PII hiding
in plain sight in derived tables, dashboards no one knows contain regulated
data, and governance policies that can't be enforced because the metadata isn't
there. TagFlow makes governance **transitive** across the lineage graph.

## What it does

1. **Reads** the lineage graph and existing tags/glossary terms from DataHub.
2. **Analyzes** which downstream columns *should* inherit an upstream
   classification but don't.
3. **Detects conflicts** — cases where a downstream column already carries a
   different or contradictory classification.
4. **Writes back** the proposed tags/terms to DataHub via the SDK, with full
   provenance so every change is auditable.
5. **Reports** a human-readable summary of everything it propagated and flagged.

## How it uses DataHub

- Reads multi-hop lineage via the DataHub Python SDK (`client.lineage.get_lineage`).
- Reads `GlobalTags` and `GlossaryTerms` aspects per entity/column.
- **Contributes back to the graph** by emitting tag/term associations — the
  most heavily weighted judging criterion.

---

## What makes this different

DataHub *can* propagate tags along lineage — it's a per-tag setting, and
column-level propagation ships in Core. TagFlow isn't a reimplementation of that;
it's the **governance safety layer and agent** on top of it:

- **Conflict detection with safe refusal.** When a downstream asset already
  carries a *different* sensitive label, TagFlow flags it and refuses to
  overwrite — built-in propagation just stacks labels. Contradictory
  classifications are precisely what a human should review, not silently merge.
- **An agent, not a background toggle.** TagFlow runs as a standalone agent
  against the SDK on open-source DataHub Core (glossary-term propagation is
  open-beta / Cloud-gated), with an explicit, safe **dry-run → apply** workflow.
- **Auditable by construction.** Every write carries provenance (the `tagflow`
  actor) and lands in a JSON run report — a reviewable batch you can diff, not an
  always-on process you can't inspect.
- **Idempotent and entity-uniform.** Low-level aspect emits label datasets,
  charts, and dashboards the same way; a re-run writes nothing new.

## Proven results

Run against a live DataHub loaded with the `showcase-ecommerce` datapack, from a
**single** `PII_Data` tag on one order-entry source:

| Metric | Result |
|---|---|
| Downstream assets scanned | 69 |
| Classifications **written** to DataHub in one pass | **34** |
| Write failures | **0** |
| Entity types written | Snowflake datasets, dbt models, PowerBI / Tableau / Looker charts & dashboards |
| Deepest propagation | **5 hops** from source |
| Re-run (idempotency) | **0** new writes — everything already classified |

> These numbers are deterministic **for the `showcase-ecommerce` datapack** —
> they reflect that graph's lineage shape, not random sampling. A different
> catalog will produce different counts; the behavior (propagate, skip, flag,
> refuse) is the same.

Because the propagated tags persist, the classified surface compounds: a second
run auto-discovers **21** PII-bearing sources (up from 2) and correctly writes
nothing new. The writer uses low-level aspect emits
(`MetadataChangeProposalWrapper`), so it labels dashboards and charts as reliably
as it does tables. A full sample report is in
[`examples/propagation-report.json`](examples/propagation-report.json).

### Proof of write-back

This is a real, applied run — the report opens with `"dry_run": false`, and all
**34** propagated classifications carry `"applied": true` next to the exact URN
they were written to. Re-running was idempotent: **0** new writes. Glossary-term
writes are stamped with the `tagflow` actor, and every write — tag or term — is
emitted under TagFlow's identity, so DataHub's own audit log attributes each
change and the JSON report doubles as a provenance trail.

![Before and after: a downstream order_history dataset in the DataHub UI — untagged on the left, carrying the PII_Data tag TagFlow wrote on the right](examples/writeback-ui.png)

---

## Safety features

Writing governance metadata back automatically is powerful, so TagFlow is
conservative by design:

- **Dry-run by default.** `--apply` is required to write anything; the default
  run computes and reports changes without touching DataHub.
- **Conflict refusal.** If a downstream asset already carries a *different*
  sensitive label, TagFlow flags it for human review and does **not** overwrite.
- **Idempotent.** Every write checks for the existing association first, so
  re-runs (and concurrent runs) write nothing new — no duplicates, no clobbering.
- **Partial success, never a hard abort.** If one entity can't be written, that
  failure is recorded (`33 succeeded, 1 failed`) and the run continues.
- **Scoping controls.** `--source` and `--limit N` bound exactly what a run
  touches, so a first apply can be as small as one write.

## Why now

As organizations lean on AI agents and automated pipelines, governance metadata
has to stay correct across data that is constantly copied, joined, and reshaped.
Manual tagging doesn't keep up — so lineage-aware propagation, applied safely and
auditable after the fact, becomes the practical way to keep classifications where
the data actually is.

## Quickstart

> TagFlow talks to a running DataHub instance. The commands below assume the
> [DataHub Quickstart](https://docs.datahub.com/docs/quickstart) is up and the
> `showcase-ecommerce` datapack is loaded.

```bash
# 0. Load a sample datapack so there's lineage + tags to propagate
datahub datapack load showcase-ecommerce

# 1. Install
pip install -r requirements.txt

# 2. Point TagFlow at your DataHub (defaults to local quickstart)
export DATAHUB_GMS_URL=http://localhost:8080
export DATAHUB_GMS_TOKEN=            # optional; required on secured instances

# 3. Dry run — see what WOULD change, write nothing
python -m tagflow.cli propagate --dry-run

# 4. Apply — write the propagated tags back to DataHub
python -m tagflow.cli propagate --apply

# Safety: cap the number of writes (also handy for a scoped first test)
python -m tagflow.cli propagate --apply --limit 1
```

## Tests

The decision logic (propagate / skip / conflict / limit / failure isolation) is
covered by an in-memory suite that needs no DataHub connection:

```bash
pip install -r requirements-dev.txt
pytest
```

## Project layout

```
tagflow/
  cli.py            # command-line entrypoint
  config.py         # connection + policy configuration
  client.py         # DataHub connection wrapper
  lineage.py        # lineage traversal
  tags.py           # read/analyze/write tags & glossary terms
  propagate.py      # core propagation engine + conflict detection
  report.py         # human-readable run reports
examples/           # sample outputs (propagation reports)
```

## Future work

TagFlow deliberately uses the DataHub Python SDK for direct, auditable graph
access — the write path works uniformly on datasets, charts, and dashboards. The
natural extensions, tracked in [ROADMAP.md](ROADMAP.md):

- **MCP Server wrapper** — expose `propagate` (dry-run / `--apply` / report) as
  MCP tools so any MCP client can invoke governance propagation from a
  conversation.
- **DataHub Skill** — package the propagation runbook as a Skill that agents can
  discover and call.
- **Agent Context Kit** — surface lineage and pending-propagation context to
  agent-driven catalog workflows.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
