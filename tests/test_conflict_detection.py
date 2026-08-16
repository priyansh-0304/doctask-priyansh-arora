from app.extraction import ExtractedFact, FactType
from app.conflict_detection import detect_date_conflicts, detect_scope_conflicts, detect_conflicts
from tests.fakes import FakeResolver


def _fact(feature, fact_type, value) -> ExtractedFact:
    return ExtractedFact(feature_name=feature, fact_type=fact_type, value=value, source_quote=value)


def test_date_conflict_fires_on_multiple_distinct_dates():
    facts = [
        ("a.md", _fact("X", FactType.TARGET_DATE, "Sept 15")),
        ("b.md", _fact("X", FactType.TARGET_DATE, "Sept 29")),
    ]
    conflicts = detect_date_conflicts("X", facts)
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "date_conflict"


def test_no_date_conflict_when_all_sources_agree():
    facts = [
        ("a.md", _fact("X", FactType.TARGET_DATE, "Sept 15")),
        ("b.md", _fact("X", FactType.TARGET_DATE, "Sept 15")),
    ]
    assert detect_date_conflicts("X", facts) == []


def test_no_date_conflict_with_only_one_mention():
    facts = [("a.md", _fact("X", FactType.TARGET_DATE, "Sept 15"))]
    assert detect_date_conflicts("X", facts) == []


def test_scope_conflict_fires_when_included_and_cut_are_similar():
    included = _fact("X", FactType.SCOPE_INCLUDED, "Email digest")
    cut = _fact("X", FactType.SCOPE_CUT, "email digest fallback")
    facts = [("prd.md", included), ("notes.md", cut)]

    resolver = FakeResolver({
        "Email digest": [1.0, 0.0],
        "email digest fallback": [0.95, 0.05],  # deliberately close -> high cosine similarity
    })

    conflicts = detect_scope_conflicts("X", facts, resolver)
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "scope_conflict"


def test_no_scope_conflict_when_items_are_dissimilar():
    included = _fact("X", FactType.SCOPE_INCLUDED, "Push notifications")
    cut = _fact("X", FactType.SCOPE_CUT, "Email digest fallback")
    facts = [("prd.md", included), ("notes.md", cut)]

    resolver = FakeResolver({
        "Push notifications": [1.0, 0.0],
        "Email digest fallback": [0.0, 1.0],  # orthogonal -> similarity 0
    })

    assert detect_scope_conflicts("X", facts, resolver) == []


def test_detect_conflicts_groups_by_feature_correctly():
    # Two features, only one has a real conflict -- the other must not
    # leak a false conflict just because it's processed in the same batch.
    class FakeDoc:
        def __init__(self, filename):
            self.filename = filename

    facts = [
        (FakeDoc("a.md"), _fact("X", FactType.TARGET_DATE, "Sept 15")),
        (FakeDoc("b.md"), _fact("X", FactType.TARGET_DATE, "Sept 29")),
        (FakeDoc("a.md"), _fact("Y", FactType.TARGET_DATE, "Oct 1")),
        (FakeDoc("b.md"), _fact("Y", FactType.TARGET_DATE, "Oct 1")),
    ]
    resolver = FakeResolver({})  # no scope facts here, never called

    conflicts = detect_conflicts(facts, resolver)
    assert len(conflicts) == 1
    assert conflicts[0].feature_name == "X"