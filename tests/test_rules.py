from app.extraction import ExtractedFact, FactType
from app.conflict_detection import Conflict
from app.rules import run_governance_checks


class FakeDoc:
    def __init__(self, filename):
        self.filename = filename


def _fact(feature, fact_type, value) -> ExtractedFact:
    return ExtractedFact(feature_name=feature, fact_type=fact_type, value=value, source_quote=value)


def test_no_owner_finding_fires_when_owner_missing():
    doc = FakeDoc("a.md")
    facts = [(doc, _fact("X", FactType.STATUS, "In Progress"))]
    findings = run_governance_checks(facts, [])
    assert any(f.rule == "no-owner" for f in findings)


def test_no_owner_finding_absent_when_owner_present():
    doc = FakeDoc("a.md")
    facts = [(doc, _fact("X", FactType.OWNER, "Alice")), (doc, _fact("X", FactType.STATUS, "In Progress"))]
    findings = run_governance_checks(facts, [])
    assert not any(f.rule == "no-owner" for f in findings)


def test_ambiguous_date_finding_mirrors_a_real_date_conflict():
    doc = FakeDoc("a.md")
    facts = [(doc, _fact("X", FactType.OWNER, "Alice"))]  # avoid triggering no-owner too
    conflicts = [Conflict("X", "date_conflict", "2 dates found", [])]
    findings = run_governance_checks(facts, conflicts)
    assert any(f.rule == "ambiguous-date" for f in findings)


def test_unconfirmed_done_fires_on_single_source_done_claim():
    doc = FakeDoc("a.md")
    facts = [
        (doc, _fact("X", FactType.OWNER, "Alice")),
        (doc, _fact("X", FactType.STATUS, "Done")),
    ]
    findings = run_governance_checks(facts, [])
    assert any(f.rule == "unconfirmed-done" for f in findings)


def test_unconfirmed_done_absent_with_corroborating_second_source():
    doc_a, doc_b = FakeDoc("a.md"), FakeDoc("b.md")
    facts = [
        (doc_a, _fact("X", FactType.OWNER, "Alice")),
        (doc_a, _fact("X", FactType.STATUS, "Done")),
        (doc_b, _fact("X", FactType.STATUS, "confirmed shipped")),
    ]
    findings = run_governance_checks(facts, [])
    assert not any(f.rule == "unconfirmed-done" for f in findings)