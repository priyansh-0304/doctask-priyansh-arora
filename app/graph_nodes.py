"""Graph nodes -- each wraps an already-built, already-tested pipeline
stage. A node returning {} when its output already exists in state is
what makes a resumed run skip completed work instead of redoing it."""

from pathlib import Path
import numpy as np

from app.ingest import ingest_pile
from app.extraction import extract_facts
from app.entity_resolution import EntityResolver
from app.conflict_detection import detect_conflicts
from app.register import build_register, render_register_markdown
from langgraph.types import interrupt


def _fresh_resolver_from_state(state) -> EntityResolver:
    resolver = EntityResolver()
    if state.get("canonical_names"):
        resolver.canonical_names = list(state["canonical_names"])
        resolver.canonical_embeddings = [np.array(e) for e in state["canonical_embeddings"]]
    return resolver


def ingest_node(state):
    if state.get("documents"):
        print("  [ingest] already done, skipping")
        return {}
    documents = ingest_pile(Path(state["fixtures_dir"]))
    print(f"  [ingest] loaded {len(documents)} document(s)")
    return {"documents": documents}


def extract_node(state):
    if state.get("all_facts"):
        print("  [extract] already done, skipping")
        return {}
    all_facts = []
    for doc in state["documents"]:
        facts = extract_facts(doc)
        for fact in facts:
            all_facts.append((doc, fact))
    print(f"  [extract] extracted {len(all_facts)} fact(s)")
    return {"all_facts": all_facts}


def resolve_node(state):
    if state.get("pending_review") is not None:
        print("  [resolve] already done, skipping")
        return {}
    resolver = _fresh_resolver_from_state(state)
    all_facts = state["all_facts"]

    # Keyed by fact_id (stable UUID) -- NOT list position (fragile) and
    # NOT id(fact) (breaks across the checkpoint's serialize/deserialize
    # boundary, exactly as found earlier in register.py today).
    original_names = {fact.fact_id: fact.feature_name for _, fact in all_facts}

    for doc, fact in all_facts:
        canonical, score, confidence = resolver.resolve(fact.feature_name)
        fact.feature_name = canonical

    print(f"  [resolve] {len(resolver.pending_review)} merge(s) flagged for human review")
    return {
        "all_facts": all_facts,
        "original_feature_names": original_names,
        "canonical_names": resolver.canonical_names,
        "canonical_embeddings": [e.tolist() for e in resolver.canonical_embeddings],
        "pending_review": resolver.pending_review,
    }


def conflict_node(state):
    if state.get("conflicts") is not None:
        print("  [detect_conflicts] already done, skipping")
        return {}
    resolver = _fresh_resolver_from_state(state)
    conflicts = detect_conflicts(state["all_facts"], resolver)
    print(f"  [detect_conflicts] found {len(conflicts)} conflict(s)")
    return {"conflicts": conflicts}


def register_node(state):
    if state.get("register_markdown"):
        print("  [build_register] already done, skipping")
        return {}
    resolver = _fresh_resolver_from_state(state)
    rows = build_register(state["all_facts"], state["conflicts"], resolver)
    md = render_register_markdown(rows)
    Path("output").mkdir(exist_ok=True)
    Path("output/register.md").write_text(md)
    print("  [build_register] wrote output/register.md")
    return {"register_rows": rows, "register_markdown": md}


def human_review_node(state):
    payload = {
        "conflicts": [
            {"index": i, "summary": f"[{c.conflict_type}] {c.feature_name}: {c.description}"}
            for i, c in enumerate(state["conflicts"])
        ],
        "pending_merges": [
            {"index": i, "summary": f"'{m['mention']}' -> '{m['matched_to']}' (embedding {m['embedding_score']})"}
            for i, m in enumerate(state["pending_review"])
        ],
        "message": "Approve or reject each conflict and each proposed merge.",
    }
    decision = interrupt(payload)
    print(f"  [human_review] resumed with decision: {decision}")
    return {"human_decisions": decision}


def commit_node(state):
    """Applies the human's item-by-item decisions. Rejected merges are
    reverted via fact_id lookup -- consistent with register.py and
    mcp_server.py, not the position-based approach this used to use."""
    decisions = state.get("human_decisions") or {}
    conflict_decisions = decisions.get("conflict_decisions", {})
    merge_decisions = decisions.get("merge_decisions", {})

    all_facts = state["all_facts"]
    original_names = state["original_feature_names"]  # dict: fact_id -> original name
    pending_review = state["pending_review"]

    for i, merge in enumerate(pending_review):
        if merge_decisions.get(i, True) is False:
            mention, matched_to = merge["mention"], merge["matched_to"]
            reverted_count = 0
            for doc, fact in all_facts:
                if fact.feature_name == matched_to and original_names.get(fact.fact_id) == mention:
                    fact.feature_name = mention
                    reverted_count += 1
            print(f"  [commit] rejected merge '{mention}' -> '{matched_to}': reverted {reverted_count} fact(s)")

    conflicts = state["conflicts"]
    kept_conflicts = []
    for i, c in enumerate(conflicts):
        if conflict_decisions.get(i, True) is False:
            print(f"  [commit] dismissed conflict #{i}: [{c.conflict_type}] {c.feature_name}")
        else:
            kept_conflicts.append(c)

    resolver = _fresh_resolver_from_state(state)
    rows = build_register(all_facts, kept_conflicts, resolver)
    md = render_register_markdown(rows)
    Path("output").mkdir(exist_ok=True)
    Path("output/register.md").write_text(md)

    print(f"  [commit] final register written to output/register.md "
          f"({len(kept_conflicts)}/{len(conflicts)} conflicts retained after human review)")
    return {"conflicts": kept_conflicts, "all_facts": all_facts, "register_markdown": md}