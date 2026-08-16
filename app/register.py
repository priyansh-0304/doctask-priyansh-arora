"""Stage 4: Draft Deliverable. Builds the Feature & Deadline Register --
the grounded deliverable Task 1 requires. Every field traces to its
exact source; fields under active dispute (per conflict_detection) are
marked disputed rather than silently resolved to one value -- this is
the concrete implementation of "it never bluffs."
"""

from dataclasses import dataclass, field
from app.extraction import ExtractedFact, FactType
from app.conflict_detection import Conflict


@dataclass
class SourcedValue:
    value: str
    filename: str
    source_quote: str


@dataclass
class RegisterRow:
    feature_name: str
    owners: list[SourcedValue] = field(default_factory=list)
    target_date: list[SourcedValue] = field(default_factory=list)
    date_disputed: bool = False
    statuses: list[SourcedValue] = field(default_factory=list)
    scope_included: list[SourcedValue] = field(default_factory=list)
    scope_cut: list[SourcedValue] = field(default_factory=list)
    scope_disputed: list[tuple[SourcedValue, SourcedValue]] = field(default_factory=list)


def _sourced(filename: str, fact: ExtractedFact) -> SourcedValue:
    return SourcedValue(value=fact.value, filename=filename, source_quote=fact.source_quote)


def _dedupe_owners(owners: list[SourcedValue], resolver) -> list[SourcedValue]:
    """Collapses name variants ('Ananya' vs 'Ananya Rao') using the same
    embedding-similarity logic already used for feature name resolution.
    Keeps the longer/more complete-looking name as the representative."""
    if len(owners) <= 1:
        return owners

    groups: list[list[SourcedValue]] = []
    embeddings: list = []

    for owner in owners:
        emb = resolver.embed_text(owner.value)
        matched = False
        for i, group_emb in enumerate(embeddings):
            if resolver.similarity(emb, group_emb) >= 0.75:
                groups[i].append(owner)
                matched = True
                break
        if not matched:
            groups.append([owner])
            embeddings.append(emb)

    return [max(group, key=lambda o: len(o.value)) for group in groups]


def build_register(all_facts: list[tuple], conflicts: list[Conflict], resolver) -> list[RegisterRow]:
    """all_facts: list of (Document, ExtractedFact), already entity-resolved.
    conflicts: output of detect_conflicts() on the same all_facts.
    resolver: the EntityResolver instance, reused here for owner-name dedup.

    Dispute tracking is keyed by fact.fact_id (a stable UUID) throughout --
    NEVER by id(fact), which is a Python memory address that does not
    survive serialization (e.g. a LangGraph checkpoint round-trip) and
    silently breaks dispute matching once objects are reconstructed."""

    date_conflict_features = {c.feature_name for c in conflicts if c.conflict_type == "date_conflict"}

    scope_conflict_lookup_by_feature: dict[str, dict[str, list[tuple[SourcedValue, SourcedValue]]]] = {}
    disputed_fact_ids_by_feature: dict[str, set[str]] = {}
    for c in conflicts:
        if c.conflict_type == "scope_conflict":
            inc_filename, inc_fact = c.conflicting_facts[0]
            cut_filename, cut_fact = c.conflicting_facts[1]
            scope_conflict_lookup_by_feature.setdefault(c.feature_name, {}).setdefault(inc_fact.fact_id, []).append(
                (_sourced(inc_filename, inc_fact), _sourced(cut_filename, cut_fact))
            )
            disputed_fact_ids_by_feature.setdefault(c.feature_name, set()).update({inc_fact.fact_id, cut_fact.fact_id})

    by_feature: dict[str, list[tuple[str, ExtractedFact]]] = {}
    for doc, fact in all_facts:
        by_feature.setdefault(fact.feature_name, []).append((doc.filename, fact))

    rows = []
    for feature_name, facts in sorted(by_feature.items()):
        row = RegisterRow(feature_name=feature_name)
        scope_conflict_lookup = scope_conflict_lookup_by_feature.get(feature_name, {})
        disputed_fact_ids = disputed_fact_ids_by_feature.get(feature_name, set())

        for filename, fact in facts:
            if fact.fact_type == FactType.OWNER:
                row.owners.append(_sourced(filename, fact))
            elif fact.fact_type == FactType.TARGET_DATE:
                row.target_date.append(_sourced(filename, fact))
            elif fact.fact_type == FactType.STATUS:
                row.statuses.append(_sourced(filename, fact))
            elif fact.fact_type == FactType.SCOPE_INCLUDED:
                if fact.fact_id in scope_conflict_lookup:
                    row.scope_disputed.extend(scope_conflict_lookup[fact.fact_id])
                else:
                    row.scope_included.append(_sourced(filename, fact))
            elif fact.fact_type == FactType.SCOPE_CUT:
                if fact.fact_id not in disputed_fact_ids:
                    row.scope_cut.append(_sourced(filename, fact))

        row.date_disputed = feature_name in date_conflict_features
        row.owners = _dedupe_owners(row.owners, resolver)
        rows.append(row)

    return rows


def render_register_markdown(rows: list[RegisterRow]) -> str:
    lines = ["# Feature & Deadline Register\n"]

    for row in rows:
        lines.append(f"## {row.feature_name}\n")

        distinct_owners = {o.value for o in row.owners}
        if len(distinct_owners) > 1:
            lines.append(f"**Owner:** ⚠️ DISPUTED — {len(distinct_owners)} different values:")
            for o in row.owners:
                lines.append(f'  - {o.value} (*{o.filename}*: "{o.source_quote[:60]}...")')
        elif row.owners:
            o = row.owners[0]
            lines.append(f"**Owner:** {o.value} (*{o.filename}*)")
        else:
            lines.append("**Owner:** _not stated in any source_")
        lines.append("")

        if row.date_disputed:
            lines.append(f"**Target Date:** ⚠️ DISPUTED — {len(row.target_date)} conflicting mentions:")
            for d in row.target_date:
                lines.append(f'  - {d.value} (*{d.filename}*: "{d.source_quote[:60]}...")')
        elif row.target_date:
            d = row.target_date[0]
            lines.append(f"**Target Date:** {d.value} (*{d.filename}*)")
        else:
            lines.append("**Target Date:** _not stated in any source_")
        lines.append("")

        lines.append("**Status:**")
        for s in row.statuses or []:
            lines.append(f"  - {s.value} (*{s.filename}*)")
        if not row.statuses:
            lines.append("  - _no status reported_")
        lines.append("")

        lines.append("**Scope (confirmed included):**")
        for s in row.scope_included or []:
            lines.append(f"  - {s.value} (*{s.filename}*)")
        if not row.scope_included:
            lines.append("  - _none_")

        if row.scope_disputed:
            lines.append("\n**Scope (⚠️ DISPUTED — included in one source, cut in another):**")
            for inc, cut in row.scope_disputed:
                lines.append(f'  - "{inc.value}" — included per *{inc.filename}*, cut per *{cut.filename}*')

        if row.scope_cut:
            lines.append("\n**Scope (confirmed cut, no dispute):**")
            for s in row.scope_cut:
                lines.append(f"  - {s.value} (*{s.filename}*)")

        lines.append("\n---\n")

    return "\n".join(lines)