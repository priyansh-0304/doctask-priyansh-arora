from app.extraction import ExtractedFact, FactType
from app.conflict_detection import Conflict
from app.register import build_register, render_register_markdown
from tests.fakes import FakeResolver


class FakeDoc:
    def __init__(self, filename):
        self.filename = filename


def _fact(feature, fact_type, value) -> ExtractedFact:
    return ExtractedFact(feature_name=feature, fact_type=fact_type, value=value, source_quote=value)


def test_owner_shows_disputed_when_two_distinct_names_survive_dedup():
    doc_a, doc_b = FakeDoc("a.md"), FakeDoc("b.md")
    f1 = _fact("X", FactType.OWNER, "Alice")
    f2 = _fact("X", FactType.OWNER, "Bob")  # genuinely different person
    all_facts = [(doc_a, f1), (doc_b, f2)]

    resolver = FakeResolver({"Alice": [1.0, 0.0], "Bob": [0.0, 1.0]})  # orthogonal -> not deduped

    rows = build_register(all_facts, [], resolver)
    assert len(rows[0].owners) == 2


def test_owner_dedup_collapses_name_variants():
    doc_a, doc_b = FakeDoc("a.md"), FakeDoc("b.md")
    f1 = _fact("X", FactType.OWNER, "Ananya")
    f2 = _fact("X", FactType.OWNER, "Ananya Rao")
    all_facts = [(doc_a, f1), (doc_b, f2)]

    resolver = FakeResolver({"Ananya": [1.0, 0.0], "Ananya Rao": [0.99, 0.01]})  # near-identical

    rows = build_register(all_facts, [], resolver)
    assert len(rows[0].owners) == 1
    assert rows[0].owners[0].value == "Ananya Rao"  # longer name wins as representative


def test_scope_disputed_retains_multiple_conflicts_against_same_included_fact():
    # Regression test for the dict-overwrite bug: one PRD fact disputed
    # by TWO different sources must show BOTH disputes, not just one.
    doc_prd, doc_a, doc_b = FakeDoc("prd.md"), FakeDoc("a.md"), FakeDoc("b.md")
    included = _fact("X", FactType.SCOPE_INCLUDED, "Email digest")
    cut1 = _fact("X", FactType.SCOPE_CUT, "email digest")
    cut2 = _fact("X", FactType.SCOPE_CUT, "digest fallback")

    all_facts = [(doc_prd, included), (doc_a, cut1), (doc_b, cut2)]
    conflicts = [
        Conflict("X", "scope_conflict", "desc1", [("prd.md", included), ("a.md", cut1)]),
        Conflict("X", "scope_conflict", "desc2", [("prd.md", included), ("b.md", cut2)]),
    ]

    rows = build_register(all_facts, conflicts, FakeResolver({}))
    assert len(rows[0].scope_disputed) == 2


def test_fact_identity_uses_fact_id_not_object_identity():
    # Regression test for the id()-across-checkpoint bug: two SEPARATE
    # ExtractedFact objects with the same fact_id must be treated as
    # the same fact by the dispute lookup.
    doc_prd, doc_a = FakeDoc("prd.md"), FakeDoc("a.md")
    included = _fact("X", FactType.SCOPE_INCLUDED, "Email digest")
    cut = _fact("X", FactType.SCOPE_CUT, "email digest")

    # Simulate a "deserialized" copy sharing the same fact_id but being
    # a genuinely different Python object -- id() would differ, fact_id must not.
    included_copy = ExtractedFact(
        fact_id=included.fact_id, feature_name=included.feature_name,
        fact_type=included.fact_type, value=included.value, source_quote=included.source_quote,
    )
    assert included_copy is not included
    assert included_copy.fact_id == included.fact_id

    all_facts = [(doc_prd, included_copy), (doc_a, cut)]
    conflicts = [Conflict("X", "scope_conflict", "desc", [("prd.md", included), ("a.md", cut)])]

    rows = build_register(all_facts, conflicts, FakeResolver({}))
    assert len(rows[0].scope_disputed) == 1  # matched via fact_id despite being a different object


def test_render_produces_valid_markdown_structure():
    doc = FakeDoc("a.md")
    facts = [(doc, _fact("X", FactType.STATUS, "In Progress"))]
    rows = build_register(facts, [], FakeResolver({}))
    md = render_register_markdown(rows)
    assert "# Feature & Deadline Register" in md
    assert "## X" in md
    assert "In Progress" in md