"""Stage 2: Fact extraction. Uses Gemini to pull structured facts out of
each document's raw text, with each fact required to carry the exact
source quote it's grounded in.

fact_id is intentionally NOT part of the schema shown to Gemini (see
ExtractedFactWire below) -- an earlier version used exclude=True on the
field, which only affects local serialization, not the JSON schema sent
to the model. Gemini filled the visible field with its own short,
per-call, non-unique placeholder IDs ("f1", "f2"...), silently
overriding the real UUID generator and breaking fact identity across
documents. Fix: a separate wire schema with no fact_id field at all;
the real ID is assigned locally, after parsing, where the model can't
touch it.
"""

import os
import time
from app.cost_tracker import tracker

from enum import StrEnum
from uuid import uuid4
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from app.models import Document

CHAT_MODEL = "gemini-3.5-flash-lite"


class FactType(StrEnum):
    OWNER = "owner"
    TARGET_DATE = "target_date"
    STATUS = "status"
    SCOPE_INCLUDED = "scope_included"
    SCOPE_CUT = "scope_cut"
    DECISION = "decision"


class ExtractedFactWire(BaseModel):
    """Schema exposed to Gemini's structured output. No fact_id -- the
    model never sees this field and can't invent a value for it."""
    feature_name: str
    fact_type: FactType
    value: str
    source_quote: str


class ExtractionResultWire(BaseModel):
    facts: list[ExtractedFactWire]


class ExtractedFact(BaseModel):
    """Internal representation used everywhere else in the pipeline.
    fact_id is generated locally, always, after the model's response is
    parsed -- guaranteed real, guaranteed unique."""
    fact_id: str = Field(default_factory=lambda: str(uuid4()))
    feature_name: str
    fact_type: FactType
    value: str
    source_quote: str


EXTRACTION_PROMPT = """You are extracting structured facts from a single project document.
Extract every distinct fact about features being built: who owns it, target dates,
current status, scope items included, scope items explicitly cut/removed, and any
explicit decisions made.

Rules:
- Every fact MUST include a "source_quote" field containing the EXACT verbatim text
  from the document that supports the fact. Do not paraphrase the quote.
- If a date is mentioned more than once or changes, extract EACH mention as a
  separate fact — do not silently pick the "latest" one; a later conflict-detection
  stage needs to see every mention to compare them.
- Do not infer or invent facts not explicitly stated in the text.
- feature_name should be consistent across facts about the same feature (e.g. always
  "Notifications", not sometimes "In-App Notifications" and sometimes "Notification Feature").
- fact_type MUST be exactly one of: owner, target_date, status, scope_included, scope_cut, decision

Document:
---
{content}
---

Return the extracted facts as JSON matching the required schema."""


def extract_facts(document: Document) -> list[ExtractedFact]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in environment / .env")

    client = genai.Client(api_key=api_key)
    prompt = EXTRACTION_PROMPT.format(content=document.raw_content)

    start = time.time()
    response = client.models.generate_content(
        model=CHAT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ExtractionResultWire,
        ),
    )
    duration = time.time() - start

    usage = getattr(response, "usage_metadata", None)
    prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
    output_tokens = getattr(usage, "candidates_token_count", 0) or 0
    tracker.record("extract", CHAT_MODEL, prompt_tokens, output_tokens, duration)

    wire_result = ExtractionResultWire.model_validate_json(response.text)

    # Convert to internal model -- fact_id assigned fresh here, locally,
    # never influenced by the model's output.
    return [
        ExtractedFact(
            feature_name=f.feature_name,
            fact_type=f.fact_type,
            value=f.value,
            source_quote=f.source_quote,
        )
        for f in wire_result.facts
    ]