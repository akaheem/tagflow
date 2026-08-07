"""Behavioral tests for the propagation engine.

These run the real engine, reader, writer, and lineage walker against the
in-memory fakes in ``tests.fakes`` — the only thing standing in for DataHub is
its SDK boundary, so the decision logic (skip / conflict / write / limit /
fault-isolation) is exercised end to end.
"""

from tagflow.propagate import PropagationEngine
from tests.fakes import build_client

SRC = "urn:li:dataset:(urn:li:dataPlatform:snowflake,shop.public.users,PROD)"
D1 = "urn:li:dataset:(urn:li:dataPlatform:snowflake,shop.public.orders,PROD)"
D2 = "urn:li:dataset:(urn:li:dataPlatform:snowflake,shop.public.order_items,PROD)"
BROKEN = "urn:li:dataset:(urn:li:dataPlatform:snowflake,shop.public.broken,PROD)"

PII = "urn:li:tag:PII"
GDPR = "urn:li:tag:GDPR"
CONF = "urn:li:tag:Confidential"
PII_TERM = "urn:li:glossaryTerm:Classification.PII"


def test_propagates_missing_tag_downstream():
    client = build_client(tags={SRC: [PII]}, lineage={SRC: [(D1, 1)]})
    report = PropagationEngine(client).run(source_urns=[SRC])
    assert len(report.propagations) == 1
    assert report.propagations[0].applied is True
    assert PII in client.graph.tags_on(D1)
    assert report.conflicts == []
    assert report.failures == []


def test_rerun_is_idempotent():
    client = build_client(tags={SRC: [PII]}, lineage={SRC: [(D1, 1)]})
    PropagationEngine(client).run(source_urns=[SRC])
    # Fresh engine = cold per-run cache; it must read the now-tagged D1 and skip.
    report = PropagationEngine(client).run(source_urns=[SRC])
    assert report.propagations == []
    assert client.graph.tags_on(D1).count(PII) == 1


def test_sibling_labels_do_not_false_conflict():
    # Regression guard: two sensitive tags of the SAME kind from ONE source must
    # both propagate. Writing the first must not make the second look like a
    # conflict — conflict detection compares against a frozen pre-write snapshot.
    client = build_client(tags={SRC: [PII, GDPR]}, lineage={SRC: [(D1, 1)]})
    report = PropagationEngine(client).run(source_urns=[SRC])
    assert len(report.propagations) == 2
    assert report.conflicts == []
    assert set(client.graph.tags_on(D1)) == {PII, GDPR}


def test_genuine_conflict_is_flagged_not_written():
    client = build_client(tags={SRC: [PII], D1: [CONF]}, lineage={SRC: [(D1, 1)]})
    report = PropagationEngine(client).run(source_urns=[SRC])
    assert report.propagations == []
    assert len(report.conflicts) == 1
    conflict = report.conflicts[0]
    assert conflict.incoming_classification == "PII"
    assert conflict.existing_classification == "Confidential"
    # Left untouched: the pre-existing label stays, PII is not stacked on.
    assert client.graph.tags_on(D1) == [CONF]


def test_limit_caps_propagations():
    client = build_client(tags={SRC: [PII]}, lineage={SRC: [(D1, 1), (D2, 2)]})
    report = PropagationEngine(client).run(source_urns=[SRC], limit=1)
    assert len(report.propagations) == 1


def test_write_failure_is_isolated():
    client = build_client(
        tags={SRC: [PII]},
        lineage={SRC: [(D1, 1), (D2, 2)]},  # D1 first (nearest), then D2
        fail_urns=[D1],
    )
    report = PropagationEngine(client).run(source_urns=[SRC])
    assert len(report.failures) == 1
    assert report.failures[0].target_urn == D1
    # The run continued past the failure and tagged the healthy entity.
    assert len(report.propagations) == 1
    assert report.propagations[0].target_urn == D2


def test_dry_run_writes_nothing():
    client = build_client(tags={SRC: [PII]}, lineage={SRC: [(D1, 1)]}, dry_run=True)
    report = PropagationEngine(client).run(source_urns=[SRC])
    assert len(report.propagations) == 1
    assert report.propagations[0].applied is False
    assert client.graph.emit_calls == []
    assert client.graph.tags_on(D1) == []


def test_glossary_term_propagates():
    client = build_client(terms={SRC: [PII_TERM]}, lineage={SRC: [(D1, 1)]})
    report = PropagationEngine(client).run(source_urns=[SRC])
    assert len(report.propagations) == 1
    assert report.propagations[0].kind == "term"
    assert PII_TERM in client.graph.terms_on(D1)


def test_discovery_skips_unreadable_dataset():
    # An unreadable dataset during auto-discovery must not abort the scan.
    client = build_client(
        tags={SRC: [PII]},
        dataset_urns=[BROKEN, SRC],
        read_fail_urns=[BROKEN],
        lineage={SRC: [(D1, 1)]},
    )
    report = PropagationEngine(client).run()  # source_urns=None -> auto-discover
    assert report.sources_scanned == 1  # BROKEN skipped, SRC found
    assert len(report.propagations) == 1
