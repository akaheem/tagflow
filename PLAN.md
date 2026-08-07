# TagFlow — Project Plan & Progress Tracker

> Living document. Updated as we build. Source of truth for scope, approach,
> and status.

---

## 1. What we're building

**TagFlow** — an AI-driven governance agent that makes classifications
*transitive* across a data stack.

**The problem:** Data teams tag sensitive fields at the source (e.g. `PII` on
`users.email`), but those tags rarely follow the data as it is copied, joined,
and aggregated downstream. Derived tables and dashboards end up holding
regulated data with no label, so governance policies can't be enforced.

**The solution:** TagFlow reads lineage + existing tags from DataHub, figures
out which downstream columns *should* inherit an upstream classification but
don't, flags conflicts, and **writes the propagated tags back into DataHub** so
the catalog becomes self-consistent and the next person/agent inherits the
knowledge.

**One-liner for the demo:** *"Governance that follows your data."*

---

## 2. Why this wins (mapping to judging criteria)

| Criterion | How TagFlow scores |
|---|---|
| **Use of DataHub** (highest weight) | Reads lineage + tag/term aspects AND **contributes back** to the graph — the explicitly double-emphasized criterion. |
| **Technical Execution** | End-to-end: read → analyze → detect conflicts → write → report. Runs against real sample data. |
| **Originality** | Not a DataHub built-in. Tag *propagation across lineage* with conflict detection is a genuine gap. |
| **Real-World Usefulness** | Every governed data team fights tag-drift downstream. Immediately relatable to judges from Pinterest/Netflix/Apple. |
| **Submission Quality** | Clean README, sample outputs in `examples/`, tight <3min before/after video. |
| **Bonus: OSS contribution** | Ship one small DataHub PR (doc fix or tiny skill) for bonus points. |

---

## 3. Constraints

- **Solo dev, 2 days hard cap** (another mandatory hackathon starts Aug 10).
- **Low-spec laptop** → DataHub runs in a **GitHub Codespace**, not locally.
- **Language: Python** (DataHub SDK + MCP are Python-first).
- Workflow: code is authored on the local machine (`C:\Ai Factory`), pushed to
  the `akaheem/tagflow` repo, and pulled/run inside the Codespace where DataHub
  lives.

---

## 4. Architecture

```
                +---------------------+
                |   DataHub (GMS)     |   <- runs in Codespace via quickstart
                |  showcase-ecommerce |
                +----------+----------+
                           ^ read lineage + tags/terms
                           | write tags/terms back
                +----------+----------+
                |      TagFlow        |
                |                     |
   cli.py  -->  propagate.py  <-----  config.py (sensitivity policy)
                |   |     |           |
                |   |     +--> tags.py      (read/analyze/write classifications)
                |   +--------> lineage.py   (downstream traversal via SDK)
                +--------+----------------+
                         v
                     report.py  --> console summary + JSON artifact (examples/)
```

**Data flow per run:**
1. Discover source datasets that carry sensitive tags/terms.
2. For each source, walk downstream lineage (`get_lineage`, max_hops=3).
3. For each downstream entity, read its existing tags/terms.
4. If a sensitive classification is missing downstream → queue a propagation.
5. If a downstream entity already has a *conflicting* classification → flag it,
   don't overwrite.
6. In `--apply` mode, emit the queued tags/terms back to DataHub.
7. Print report + write JSON artifact.

---

## 5. Tech approach / key decisions

- **Read lineage** via high-level SDK `client.lineage.get_lineage(..., max_hops=N)`
  — server-side multi-hop traversal, no hand-rolled BFS. *(confirmed by research)*
- **Read tags/terms** via low-level `graph.get_aspect(urn, GlobalTagsClass /
  GlossaryTermsClass)`. *(confirmed by research)*
- **Write-back** via SDK emit of tag/term association aspects. *(pending final
  research agent — the one module we won't guess on)*
- **Sensitivity policy** is keyword-based & configurable (`config.py`) so the
  demo clearly shows *only* PII/sensitive tags flowing, not noise.
- **Dry-run by default** — safe, and produces the "before" state for the video.
- **Provenance** — every written tag is auditable so the change is defensible.
- Core logic on the **Python SDK** for reliability; **MCP tie-in is a stretch
  goal**, not a dependency.

---

## 6. Status board

### DONE
- [x] Project decided, named (TagFlow), repo + Codespace created.
- [x] `LICENSE` — Apache 2.0 (required, visible in About).
- [x] `README.md` — full description, quickstart, layout.
- [x] `requirements.txt`, `.gitignore`.
- [x] `tagflow/__init__.py`.
- [x] `tagflow/config.py` — connection config + sensitivity keyword policy.
- [x] `tagflow/client.py` — DataHub SDK connection wrapper (graph + sdk clients).
- [x] `tagflow/lineage.py` — downstream lineage traversal.
- [x] `tagflow/report.py` — console + JSON run reports.
- [x] `examples/README.md`, `reports/.gitkeep`.

### DONE (build + verification)
- [x] `tagflow/tags.py` — read + analyze + WRITE tags/terms via low-level aspect emit
      (`MetadataChangeProposalWrapper`, idempotent, works uniformly on datasets/charts/dashboards).
- [x] `tagflow/propagate.py` — core engine: source auto-discovery, downstream
      propagation, conflict detection, per-entity fault-tolerance.
- [x] `tagflow/cli.py` — `propagate --dry-run / --apply / --limit N` entrypoint.
- [x] **Write-back proven end-to-end**: 34 tags written across Snowflake datasets, dbt models,
      PowerBI / Tableau / Looker charts & dashboards, **0 write failures**, up to 5 hops.
- [x] **Idempotency verified**: re-run shows 0 new propagations (everything already tagged).
- [x] Sample report committed to `examples/propagation-report.json`.

### DONE (overnight hardening review — behavior-preserving)
- [x] Suppress the DataHub SDK's per-traversal multi-hop lineage warning
      (`logging.getLogger("datahub").setLevel(ERROR)`) in `cli.py` and both demo
      scripts — clean console for the video, real errors still surface.
- [x] URN-based "already present" check in `propagate._resolve_one` (was
      name-based) — aligns with the writer's URN-level idempotency; a same-named
      but distinct label no longer masks a real propagation. Proven counts
      (34 / 0 conflicts on apply, idempotent re-run, 1 seeded conflict) unchanged.
- [x] Per-run read cache in the engine (`_classifications`), kept write-coherent —
      each entity's tags/terms are read from DataHub once per run instead of
      repeatedly across source-discovery + downstream passes.
- [x] Per-entity fault-tolerance in `_discover_sources` — one unreadable dataset
      no longer aborts discovery.

### DONE (test suite + regression fix)
- [x] Caught + fixed a self-introduced regression in `_resolve_one`: the
      write-coherent cache let `_find_conflict` see freshly-written sibling labels,
      so two sensitive tags of the same kind from one source (e.g. PII + GDPR)
      would falsely flag each other. Fix: freeze `conflict_basis = tuple(existing)`
      per target before writes; detect conflicts against that snapshot.
- [x] `tests/` — pytest suite over the real engine/reader/writer/lineage with an
      in-memory DataHub fake (`tests/fakes.py`). Covers: propagate, idempotent
      re-run, sibling-labels-no-false-conflict (the regression guard), genuine
      conflict flagged-not-written, `--limit` cap, write-failure isolation,
      dry-run writes nothing, glossary-term path, discovery fault-tolerance, and
      report JSON/console/`_short()` rendering. Run: `pytest` in the Codespace.

### DONE (submission weak-point hardening)
- [x] `examples/README.md` corrected — the committed report is an APPLIED run
      (`dry_run: false`, 34 written), not a dry-run; the old text implied read-only.
- [x] `report.py` summary now includes `"written": <applied count>`; console shows
      "Written to DataHub: N" (apply) vs "Would write: N" (dry-run) — write-back is
      provable at a glance, in the repo and on the demo video.
- [x] README gained a "Proof of write-back" section (points at the applied report
      + a DataHub UI screenshot slot) and a "Future work" section (MCP wrapper /
      DataHub Skill / Agent Context Kit), backed by a real `ROADMAP.md`.

### IN PROGRESS
- [ ] Pull updated README + commit locally, push to close the loop.

### PENDING (submission)
- [ ] Record <3min demo video. Shot list (no "hi I'm…" intro — open on the problem):
      - 0:00–0:15 — DataHub UI: a downstream asset (`order_history`) with NO PII tag.
      - 0:15–0:30 — one sentence: the tag lives on the source, not where the data went.
      - 0:30–2:00 — `clear`, then `propagate --dry-run` → `--apply`; show "Written to
        DataHub: 34"; refresh the UI on `order_history` → the PII_Data tag is now there.
      - 2:00–2:30 — `demo_conflict.py`: TagFlow FLAGS a conflict, leaves it untouched.
      - 2:30–3:00 — recap + repo link.
      - Clean terminal (`clear` first); use `--limit 5` if a full run is too verbose.
- [ ] Add real DataHub UI screenshot to `examples/writeback-ui.png` (before/after split)
      — referenced by README; or delete that image line before pushing.
- [ ] Paste the demo-video URL into the README hero link (currently `#`).
- [ ] Write Devpost description; opt into feedback survey (free $50 tier).
- [ ] (Optional, ~2 min) Seed a conflicting tag to show conflict detection on camera.

---

## 7. Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Quickstart OOM on free Codespace | High | Rebuild at 4-core; fallback = read from demo instance, write to lightweight GMS. |
| Write-back API differs from expectation | Medium | Dedicated research agent; keep write path isolated in `tags.py`. |
| showcase-ecommerce lacks clean PII lineage | Medium | Configurable keyword policy; can seed our own tag on a source column to demo the flow. |
| Time overrun (2-day cap) | Medium | Dry-run alone is a complete, demoable submission. Everything past it is stretch. |

---

## 8. Definition of "submittable"

Minimum viable winning submission:
1. Public repo, Apache-2.0 visible in About. ✅ (license ready)
2. TagFlow runs end-to-end against showcase-ecommerce (at least dry-run).
3. `--apply` writes at least one tag back, visible in DataHub UI.
4. Sample output committed to `examples/`.
5. <3min video showing before → run → after.
6. Devpost description + feedback survey opt-in.

Stretch: MCP tie-in, OSS PR, richer conflict handling.
