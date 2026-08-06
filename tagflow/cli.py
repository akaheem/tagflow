"""Command-line entrypoint for TagFlow.

Usage:
    python -m tagflow.cli propagate --dry-run
    python -m tagflow.cli propagate --apply
    python -m tagflow.cli propagate --apply --source <dataset_urn>
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from tagflow.client import TagFlowClient
from tagflow.config import TagFlowConfig
from tagflow.propagate import PropagationEngine


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tagflow",
        description="Propagate sensitive classifications downstream across "
        "DataHub lineage.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prop = sub.add_parser(
        "propagate",
        help="Propagate sensitive tags/terms from sources to downstream entities.",
    )
    mode = prop.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and report changes without writing (default).",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Write propagated classifications back to DataHub.",
    )
    prop.add_argument(
        "--source",
        action="append",
        default=None,
        metavar="URN",
        help="Explicit source dataset URN. Repeatable. Omit to auto-discover.",
    )
    prop.add_argument(
        "--max-hops",
        type=int,
        default=3,
        help="How many hops downstream to propagate (default: 3).",
    )
    prop.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Stop after N propagations. Use for a scoped test write "
        "(e.g. --apply --limit 1) or as a safety cap.",
    )
    prop.add_argument(
        "--out",
        default=None,
        metavar="PATH",
        help="Write the JSON report to this path.",
    )
    return parser


def _run_propagate(args: argparse.Namespace) -> int:
    config = TagFlowConfig(
        dry_run=not args.apply,
        max_hops=args.max_hops,
    )

    client = TagFlowClient(config)
    try:
        client.check_connection()
    except Exception as exc:  # noqa: BLE001 - surface any connection failure clearly
        print(
            f"ERROR: could not reach DataHub at {config.gms_url}\n  {exc}\n"
            "Is the DataHub Quickstart running? Set DATAHUB_GMS_URL if needed.",
            file=sys.stderr,
        )
        return 2

    engine = PropagationEngine(client)
    sources: Optional[List[str]] = args.source
    report = engine.run(source_urns=sources, limit=args.limit)

    print(report.render_console())

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report.to_json())
        print(f"Report written to {args.out}")

    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "propagate":
        return _run_propagate(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
