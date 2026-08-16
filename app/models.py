"""Core data structures for the pipeline."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class DocType(str, Enum):
    PRD = "prd"
    STATUS_REPORT = "status_report"
    MEETING_NOTES = "meeting_notes"
    UNKNOWN = "unknown"


@dataclass
class Document:
    filename: str
    doc_type: DocType
    raw_content: str
    source_hash: str
    ingested_at: datetime = field(default_factory=datetime.utcnow)