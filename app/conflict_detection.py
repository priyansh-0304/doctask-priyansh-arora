"""Stage 3: Conflict detection. Cross-references facts within each
canonical feature to find genuine disagreements between documents.
Both conflict types here are detected mechanically -- no extra LLM
call needed, since this only compares facts already extracted.
"""

from dataclasses import dataclass
from app.extraction import ExtractedFact, FactType
from app.entity_resolution import EntityResolver

SCOPE_ITEM_MATCH_THRESHOLD = 0.75


@dataclass
class Conflict:
    feature_name: str
    conflict_type: str  # "date_conflict" | "scope_conflict"
    description: str
    conflicting_facts: list[tuple[str, ExtractedFact]]  # (filename, fact)


def detect_date_conflicts(feature_name: str, facts: list[tuple[str, ExtractedFact]]) -> list[Conflict]:
    date_facts = [(fn, f) for fn, f in facts if f.fact_type == FactType.TARGET_DATE]
    distinct_values = {f.value for _, f in date_facts}

    if len(distinct_values) <= 1:
        return []

    return [Conflict(
        feature_name=feature_name,
        conflict_type="date_conflict",
        description=f"{len(distinct_values)} different target dates found: {', '.join(sorted(distinct_values))}",
        conflicting_facts=date_facts,
    )]


def detect_scope_conflicts(feature_name: str, facts: list[tuple[str, ExtractedFact]], resolver: EntityResolver) -> list[Conflict]:
    included = [(fn, f) for fn, f in facts if f.fact_type == FactType.SCOPE_INCLUDED]
    cut = [(fn, f) for fn, f in facts if f.fact_type == FactType.SCOPE_CUT]

    conflicts = []
    for inc_fn, inc_fact in included:
        inc_embedding = resolver.embed_text(inc_fact.value)
        for cut_fn, cut_fact in cut:
            cut_embedding = resolver.embed_text(cut_fact.value)
            sim = resolver.similarity(inc_embedding, cut_embedding)
            if sim >= SCOPE_ITEM_MATCH_THRESHOLD:
                conflicts.append(Conflict(
                    feature_name=feature_name,
                    conflict_type="scope_conflict",
                    description=f"'{inc_fact.value}' is listed as included ({inc_fn}) but cut ({cut_fn}) [similarity {sim:.3f}]",
                    conflicting_facts=[(inc_fn, inc_fact), (cut_fn, cut_fact)],
                ))
    return conflicts


def detect_conflicts(all_facts: list[tuple], resolver: EntityResolver) -> list[Conflict]:
    """all_facts: list of (Document, ExtractedFact) tuples, already entity-resolved."""
    by_feature: dict[str, list[tuple[str, ExtractedFact]]] = {}
    for doc, fact in all_facts:
        by_feature.setdefault(fact.feature_name, []).append((doc.filename, fact))

    conflicts = []
    for feature_name, facts in by_feature.items():
        conflicts.extend(detect_date_conflicts(feature_name, facts))
        conflicts.extend(detect_scope_conflicts(feature_name, facts, resolver))

    return conflicts