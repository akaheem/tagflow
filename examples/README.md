# Sample outputs

This folder holds example artifacts produced by TagFlow runs against the
`showcase-ecommerce` sample datapack, so judges can evaluate output quality
without running the tool.

- `propagation-report.json` — a full **applied** run against the DataHub graph:
  `"dry_run": false`, **34 classifications written** (`"applied": true` on every
  entry), **0 conflicts**, **0 failures**. It doubles as the audit trail — each
  written classification names its source, target, and hop distance.
