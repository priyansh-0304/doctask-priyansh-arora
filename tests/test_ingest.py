from app.ingest import classify_doc_type
from app.models import DocType


def test_classifies_prd():
    content = "# PRD: Something\nFeature Owner: X\nAcceptance Criteria\n..."
    assert classify_doc_type(content) == DocType.PRD


def test_classifies_status_report():
    content = "Weekly Status Report\nPrepared by: X\n..."
    assert classify_doc_type(content) == DocType.STATUS_REPORT


def test_classifies_meeting_notes():
    content = "Meeting Notes\nAttendees: X, Y\n..."
    assert classify_doc_type(content) == DocType.MEETING_NOTES


def test_unrecognized_content_is_unknown_not_guessed():
    # Deliberately generic text matching none of the signal phrases --
    # must come back UNKNOWN, never a guessed type.
    content = "Just some random notes with no structure at all."
    assert classify_doc_type(content) == DocType.UNKNOWN