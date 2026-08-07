"""Tests for run reporting: summary counts, JSON round-trip, URN shortening."""

import json

from tagflow.report import Conflict, Failure, Propagation, RunReport, _short


def _report_with_one_of_each() -> RunReport:
    report = RunReport(dry_run=False)
    report.propagations.append(
        Propagation("PII", "urn:li:tag:PII", "s", "t", 2, "tag", True)
    )
    report.conflicts.append(Conflict("t", "PII", "Confidential", "s"))
    report.failures.append(Failure("t2", "PII", "urn:li:tag:PII", "s", "boom"))
    return report


def test_to_dict_summary_counts():
    report = _report_with_one_of_each()
    assert report.to_dict()["summary"] == {
        "sources_scanned": 0,
        "downstream_scanned": 0,
        "propagations": 1,
        "written": 1,
        "conflicts": 1,
        "failures": 1,
    }


def test_to_json_round_trips():
    report = _report_with_one_of_each()
    parsed = json.loads(report.to_json())
    assert parsed["dry_run"] is False
    assert parsed["propagations"][0]["classification"] == "PII"
    assert parsed["failures"][0]["error"] == "boom"


def test_render_console_mentions_each_section():
    out = _report_with_one_of_each().render_console()
    assert "APPLIED" in out
    assert "Written to DataHub" in out
    assert "PROPAGATIONS" in out
    assert "CONFLICTS" in out
    assert "FAILURES" in out


def test_render_console_dry_run_says_would_write():
    report = RunReport(dry_run=True)
    report.propagations.append(
        Propagation("PII", "urn:li:tag:PII", "s", "t", 1, "tag", False)
    )
    out = report.render_console()
    assert "Would write" in out
    assert "Written to DataHub" not in out


def test_short_renders_dataset_and_chart():
    dataset = (
        "urn:li:dataset:(urn:li:dataPlatform:snowflake,"
        "shop.public.order_details,PROD)"
    )
    assert _short(dataset) == "public.order_details"

    chart = "urn:li:chart:(powerbi,report.sales_overview)"
    assert _short(chart) == "powerbi:sales_overview"
