from pathlib import Path
from dotenv import load_dotenv

from app.ingest import ingest_pile
from app.extraction import extract_facts
from app.entity_resolution import EntityResolver
from app.conflict_detection import detect_conflicts
from app.register import build_register, render_register_markdown
from app.rules import run_governance_checks
from app.cost_tracker import tracker

load_dotenv()

FIXTURES_DIR = Path("fixtures")


def main():
    documents = ingest_pile(FIXTURES_DIR)
    print(f"Ingested {len(documents)} document(s)\n")

    resolver = EntityResolver()
    all_facts = []

    for doc in documents:
        facts = extract_facts(doc)
        for fact in facts:
            all_facts.append((doc, fact))

    print("--- Entity Resolution ---")
    for doc, fact in all_facts:
        canonical, score, confidence = resolver.resolve(fact.feature_name)
        fact.feature_name = canonical
    print()

    if resolver.pending_review:
        print(f"⚠️  {len(resolver.pending_review)} merge(s) need human confirmation before being trusted:")
        for item in resolver.pending_review:
            print(f"   '{item['mention']}' -> '{item['matched_to']}' (embedding {item['embedding_score']})")
        print()

    conflicts = detect_conflicts(all_facts, resolver)
    print(f"--- Conflicts Detected ({len(conflicts)}) ---")
    for c in conflicts:
        print(f"\n[{c.conflict_type}] {c.feature_name}")
        print(f"  {c.description}")
        for fn, fact in c.conflicting_facts:
            print(f"    - ({fn}) {fact.value}")
    print()

    findings = run_governance_checks(all_facts, conflicts)
    print(f"--- Findings ({len(findings)}) ---")
    for f in findings:
        print(f"\n[{f.rule}] {f.feature_name}: {f.description}")
        for fn, quote in f.source_refs:
            print(f'    - ({fn}) "{quote[:60]}..."')

    register_rows = build_register(all_facts, conflicts, resolver)
    register_md = render_register_markdown(register_rows)

    OUTPUT_DIR = Path("output")
    OUTPUT_DIR.mkdir(exist_ok=True)
    register_path = OUTPUT_DIR / "register.md"
    register_path.write_text(register_md)
    print(f"--- Register written to {register_path} ---\n")

    print("--- Facts grouped by canonical feature ---")
    canonical_names = sorted(set(f.feature_name for _, f in all_facts))
    for name in canonical_names:
        print(f"\n=== {name} ===")
        for doc, fact in all_facts:
            if fact.feature_name == name:
                print(f"  [{doc.filename}] [{fact.fact_type}] {fact.value}")

    print(tracker.report())

if __name__ == "__main__":
    main()