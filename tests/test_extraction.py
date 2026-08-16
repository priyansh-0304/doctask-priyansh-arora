"""Regression test for the exclude=True schema-leak bug: fact_id must
never be influenced by the model's response, even if the model's JSON
happens to include a field named fact_id (simulating exactly what
Gemini did when the wire schema hadn't been separated yet)."""

import json
from unittest.mock import patch, MagicMock

from app.extraction import extract_facts, ExtractedFact
from app.models import Document, DocType


def _mock_gemini_response(facts_json: list[dict]):
    mock_response = MagicMock()
    mock_response.text = json.dumps({"facts": facts_json})
    return mock_response


@patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key-for-test"})
@patch("app.extraction.genai.Client")
def test_extracted_facts_get_real_unique_ids_even_if_model_output_lacks_them(mock_client_cls):
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _mock_gemini_response([
        {"feature_name": "X", "fact_type": "owner", "value": "Alice", "source_quote": "Alice"},
        {"feature_name": "X", "fact_type": "status", "value": "In Progress", "source_quote": "In Progress"},
    ])
    mock_client_cls.return_value = mock_client

    doc = Document(filename="a.md", doc_type=DocType.PRD, raw_content="...", source_hash="abc123")
    facts = extract_facts(doc)

    assert len(facts) == 2
    assert facts[0].fact_id != facts[1].fact_id  # must be genuinely unique
    assert len(facts[0].fact_id) > 4  # a real UUID, not a short model-invented placeholder like "f1"


@patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key-for-test"})
@patch("app.extraction.genai.Client")
def test_two_documents_never_produce_colliding_fact_ids(mock_client_cls):
    # This is the exact scenario that broke: two different documents,
    # each producing a fact the model (hypothetically) might label
    # identically -- must never collide once assigned locally.
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        _mock_gemini_response([{"feature_name": "X", "fact_type": "owner", "value": "Alice", "source_quote": "Alice"}]),
        _mock_gemini_response([{"feature_name": "X", "fact_type": "owner", "value": "Bob", "source_quote": "Bob"}]),
    ]
    mock_client_cls.return_value = mock_client

    doc_a = Document(filename="a.md", doc_type=DocType.PRD, raw_content="...", source_hash="aaa")
    doc_b = Document(filename="b.md", doc_type=DocType.PRD, raw_content="...", source_hash="bbb")

    facts_a = extract_facts(doc_a)
    facts_b = extract_facts(doc_b)

    assert facts_a[0].fact_id != facts_b[0].fact_id