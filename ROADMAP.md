# Roadmap

TagFlow's core loop — read lineage, decide, write back with provenance — is
done and proven (34 classifications written, 0 failures, idempotent re-runs).
These are the natural extensions, ordered by impact:

1. **MCP Server wrapper** — expose `tagflow propagate` (dry-run / `--apply` /
   report) as MCP tools, so any MCP client (e.g. Claude) can invoke governance
   propagation from a conversation instead of a shell.
2. **DataHub Skill** — package the propagation runbook as a DataHub Skill that
   agents can discover and call ("propagate sensitive classifications from this
   source across its lineage").
3. **Agent Context Kit** — feed lineage and pending-propagation context to
   agents so they can reason over what TagFlow found before acting.
4. **Conflict-resolution flow** — a UI/agentic path for triaging flagged
   conflicts instead of leaving them for manual review.
5. **Policy as code** — evolve sensitivity policies (keywords → regex →
   classifier) into reviewable, versioned config.

None of these are required for the current submission — they extend the same
read → decide → write loop.
