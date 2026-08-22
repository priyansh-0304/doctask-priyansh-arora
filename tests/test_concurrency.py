"""Requirement #9: 'two runs at the same time stay two runs, whether they
are two piles or the same pile hit twice. Concurrent work does not
corrupt state.' Proves this with real OS threads, not just single-threaded
reasoning -- fully mocked so it runs without a live API key.

Patches at the ingest_documents boundary (extract_facts, EntityResolver)
rather than re-mocking Gemini's internals -- that machinery already has
its own dedicated tests in test_extraction.py; this test only needs to
prove _runs stays correctly isolated under real concurrent access.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest

from app.extraction import ExtractedFact, FactType

FIXTURES_A = Path(__file__).parent / "fixtures_concurrency_a"
FIXTURES_B = Path(__file__).parent / "fixtures_concurrency_b"


class FakeEntityResolver:
    """No Gemini calls, no embedding complexity -- this test is about
    ingest_documents' concurrency safety, not entity resolution."""
    def __init__(self, api_key=None):
        self.pending_review = []

    def resolve(self, feature_name):
        return feature_name, None, "new"


def fake_extract_facts(doc):
    if "Alpha" in doc.raw_content:
        return [ExtractedFact(feature_name="Alpha Feature", fact_type=FactType.STATUS,
                               value="in progress", source_quote="in progress")]
    elif "Beta" in doc.raw_content:
        return [ExtractedFact(feature_name="Beta Feature", fact_type=FactType.STATUS,
                               value="in progress", source_quote="in progress")]
    raise ValueError(f"unexpected document content in concurrency test: {doc.raw_content[:80]}")


@pytest.fixture(autouse=True)
def setup_fixture_dirs():
    FIXTURES_A.mkdir(exist_ok=True)
    FIXTURES_B.mkdir(exist_ok=True)
    (FIXTURES_A / "doc.md").write_text("# PRD: Alpha Feature\nFeature Owner: X\nAcceptance Criteria\n...")
    (FIXTURES_B / "doc.md").write_text("# PRD: Beta Feature\nFeature Owner: Y\nAcceptance Criteria\n...")
    yield


@patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key-for-test"})
@patch("app.mcp_server.EntityResolver", FakeEntityResolver)
@patch("app.mcp_server.extract_facts", side_effect=fake_extract_facts)
def test_two_concurrent_ingests_never_cross_contaminate(mock_extract_facts):
    from app.mcp_server import ingest_documents, _runs

    results = [None, None]

    def run_a():
        results[0] = ingest_documents(str(FIXTURES_A))

    def run_b():
        results[1] = ingest_documents(str(FIXTURES_B))

    t1 = threading.Thread(target=run_a)
    t2 = threading.Thread(target=run_b)
    t1.start(); t2.start()
    t1.join(); t2.join()

    run_id_a, run_id_b = results[0]["run_id"], results[1]["run_id"]

    assert run_id_a != run_id_b, "Two concurrent ingests must never collide on run_id"

    facts_a = _runs[run_id_a]["all_facts"]
    facts_b = _runs[run_id_b]["all_facts"]

    assert all(f.feature_name == "Alpha Feature" for _, f in facts_a), \
        "Run A's facts must never contain Run B's data"
    assert all(f.feature_name == "Beta Feature" for _, f in facts_b), \
        "Run B's facts must never contain Run A's data"


def test_many_concurrent_resolve_item_calls_on_same_run_lose_nothing():
    from app.mcp_server import _runs, resolve_item

    run_id = "stress-test-run"
    _runs[run_id] = {
        "decisions": {"conflict_decisions": {}, "merge_decisions": {}},
    }

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [
            executor.submit(resolve_item, run_id, "conflict", i, i % 2 == 0)
            for i in range(50)
        ]
        for f in futures:
            f.result()

    recorded = _runs[run_id]["decisions"]["conflict_decisions"]
    assert len(recorded) == 50, f"Expected 50 recorded decisions, got {len(recorded)} -- some writes were lost"
    for i in range(50):
        assert recorded[i] == (i % 2 == 0)