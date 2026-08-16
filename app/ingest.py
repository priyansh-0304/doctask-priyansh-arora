"""Stage 1: Ingest. Reads the document pile, detects type per file.
Heuristic-based for now — no LLM call needed at this stage. If a file's
type can't be confidently detected, it's flagged UNKNOWN rather than
guessed, per the 'never bluffs' requirement — an escalation candidate,
not a silent misclassification.
"""

import hashlib
from pathlib import Path

from app.models import Document, DocType

# Simple, explicit signal per doc type — real content, not just filename,
# so this still works even if files get renamed.
TYPE_SIGNALS = {
    DocType.PRD: ["# PRD:", "Feature Owner:", "Acceptance Criteria"],
    DocType.STATUS_REPORT: ["Weekly Status Report", "Prepared by:"],
    DocType.MEETING_NOTES: ["Meeting Notes", "Attendees:"],
}


def classify_doc_type(content: str) -> DocType:
    """Returns the doc type with the most matching signals. If nothing
    matches clearly, returns UNKNOWN rather than guessing."""
    scores = {doc_type: 0 for doc_type in TYPE_SIGNALS}

    for doc_type, signals in TYPE_SIGNALS.items():
        for signal in signals:
            if signal.lower() in content.lower():
                scores[doc_type] += 1

    best_type = max(scores, key=scores.get)
    if scores[best_type] == 0:
        return DocType.UNKNOWN
    return best_type


def load_document(path: Path) -> Document:
    content = path.read_text(encoding="utf-8")
    source_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]

    return Document(
        filename=path.name,
        doc_type=classify_doc_type(content),
        raw_content=content,
        source_hash=source_hash,
    )


def ingest_pile(directory: Path) -> list[Document]:
    """Loads every .md file in the given directory as a Document."""
    documents = []
    for path in sorted(directory.glob("*.md")):
        documents.append(load_document(path))
    return documents