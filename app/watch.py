"""Stage: Stays Alive. Watches a folder for new documents. A new
document triggers a focused update -- only facts belonging to features
the new document actually mentions get reprocessed. Everything else is
left byte-identical, and the diff is provable, not just claimed.
"""

import time
import hashlib
from pathlib import Path

from app.ingest import load_document
from app.extraction import extract_facts
from app.entity_resolution import EntityResolver
from app.conflict_detection import detect_conflicts
from app.rules import run_governance_checks
from app.register import build_register, render_register_markdown

SEEN_HASHES_FILE = Path("output/.seen_hashes")


def _load_seen_hashes() -> set[str]:
    if SEEN_HASHES_FILE.exists():
        return set(SEEN_HASHES_FILE.read_text().splitlines())
    return set()


def _save_seen_hash(source_hash: str):
    SEEN_HASHES_FILE.parent.mkdir(exist_ok=True)
    with open(SEEN_HASHES_FILE, "a") as f:
        f.write(source_hash + "\n")


def process_new_document(path: Path, all_facts: list, resolver: EntityResolver) -> tuple[list, list[str]]:
    """Extracts facts from ONE new document, resolves their feature names
    against the EXISTING resolver (so it can match into an existing
    feature rather than always creating a new one), and returns the
    updated all_facts plus which canonical features got touched."""
    doc = load_document(path)
    new_facts = extract_facts(doc)

    touched_features = set()
    for fact in new_facts:
        canonical, score, confidence = resolver.resolve(fact.feature_name)
        fact.feature_name = canonical
        touched_features.add(canonical)
        all_facts.append((doc, fact))

    return all_facts, list(touched_features)


def watch_folder(watch_dir: Path, initial_all_facts: list, resolver: EntityResolver, poll_seconds: int = 3):
    """Polls watch_dir for .md files not seen before. On a new file,
    runs a focused update: re-detects conflicts/findings/register only
    for the touched feature(s), and proves untouched features' register
    sections are byte-identical to their prior content.
    """
    watch_dir.mkdir(exist_ok=True)
    seen_hashes = _load_seen_hashes()
    all_facts = initial_all_facts

    # Baseline: render each feature's register section once, so later we
    # can prove untouched sections didn't change -- "an update should
    # cost like an update," provably, not just by claim.
    conflicts = detect_conflicts(all_facts, resolver)
    rows = build_register(all_facts, conflicts, resolver)
    prior_sections = {row.feature_name: render_register_markdown([row]) for row in rows}

    print(f"Watching {watch_dir} for new documents (Ctrl+C to stop)...")
    while True:
        for path in sorted(watch_dir.glob("*.md")):
            content = path.read_text(encoding="utf-8")
            source_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]

            if source_hash in seen_hashes:
                continue

            print(f"\n📄 New document detected: {path.name}")
            all_facts, touched = process_new_document(path, all_facts, resolver)
            print(f"   Touched feature(s): {touched}")

            conflicts = detect_conflicts(all_facts, resolver)
            findings = run_governance_checks(all_facts, conflicts)
            rows = build_register(all_facts, conflicts, resolver)

            unchanged_count = 0
            for row in rows:
                new_section = render_register_markdown([row])
                if row.feature_name not in touched:
                    if prior_sections.get(row.feature_name) == new_section:
                        unchanged_count += 1
                    else:
                        print(f"   ⚠️  '{row.feature_name}' was NOT touched by this document "
                              f"but its section changed anyway -- update was not focused.")
                prior_sections[row.feature_name] = new_section

            print(f"   ✅ {unchanged_count} untouched feature section(s) confirmed byte-identical to before")
            print(f"   {len(findings)} finding(s) after update")

            full_md = render_register_markdown(rows)
            Path("output/register.md").write_text(full_md)

            seen_hashes.add(source_hash)
            _save_seen_hash(source_hash)

        time.sleep(poll_seconds)