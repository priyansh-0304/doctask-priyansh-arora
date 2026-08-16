"""Stage: Examine. Checks facts + register against a fixed governance
checklist, producing findings that trace to source. Reuses conflicts
already detected rather than re-deriving disagreement logic."""

from dataclasses import dataclass
from app.extraction import ExtractedFact, FactType
from app.conflict_detection import Conflict


@dataclass
class Finding:
    feature_name: str
    rule: str
    description: str
    source_refs: list[tuple[str, str]]  # (filename, source_quote)


def check_missing_owner(feature_name, facts) -> Finding | None:
    if not any(f.fact_type == FactType.OWNER for _, f in facts):
        return Finding(feature_name, "no-owner", f"'{feature_name}' has no owner stated in any source.", [])
    return None


def check_date_disputed(feature_name, conflicts_for_feature) -> Finding | None:
    date_conflicts = [c for c in conflicts_for_feature if c.conflict_type == "date_conflict"]
    if date_conflicts:
        c = date_conflicts[0]
        refs = [(fn, f.source_quote) for fn, f in c.conflicting_facts]
        return Finding(feature_name, "ambiguous-date", c.description, refs)
    return None


def check_scope_disputed(feature_name, conflicts_for_feature) -> list[Finding]:
    findings = []
    for c in conflicts_for_feature:
        if c.conflict_type == "scope_conflict":
            refs = [(fn, f.source_quote) for fn, f in c.conflicting_facts]
            findings.append(Finding(feature_name, "unresolved-scope-change", c.description, refs))
    return findings


def check_unconfirmed_done(feature_name, facts) -> Finding | None:
    """No feature marked Done without corroboration from more than one source."""
    done_facts = [(fn, f) for fn, f in facts
                  if f.fact_type == FactType.STATUS and f.value.strip().lower() in ("done", "completed", "complete")]
    if not done_facts:
        return None
    other_status_files = {fn for fn, f in facts if f.fact_type == FactType.STATUS} - {fn for fn, _ in done_facts}
    if not other_status_files:
        fn, f = done_facts[0]
        return Finding(feature_name, "unconfirmed-done",
                        f"'{feature_name}' marked done, but only confirmed by a single source ({fn}).",
                        [(fn, f.source_quote)])
    return None


def run_governance_checks(all_facts: list[tuple], conflicts: list[Conflict]) -> list[Finding]:
    by_feature: dict[str, list[tuple[str, ExtractedFact]]] = {}
    for doc, fact in all_facts:
        by_feature.setdefault(fact.feature_name, []).append((doc.filename, fact))

    findings = []
    for feature_name, facts in by_feature.items():
        conflicts_for_feature = [c for c in conflicts if c.feature_name == feature_name]

        owner_finding = check_missing_owner(feature_name, facts)
        if owner_finding:
            findings.append(owner_finding)

        date_finding = check_date_disputed(feature_name, conflicts_for_feature)
        if date_finding:
            findings.append(date_finding)

        done_finding = check_unconfirmed_done(feature_name, facts)
        if done_finding:
            findings.append(done_finding)

        findings.extend(check_scope_disputed(feature_name, conflicts_for_feature))

    return findings