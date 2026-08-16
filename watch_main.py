from pathlib import Path
from dotenv import load_dotenv

from app.ingest import ingest_pile
from app.extraction import extract_facts
from app.entity_resolution import EntityResolver
from app.watch import watch_folder

load_dotenv()


def main():
    print("--- Initial pile ---")
    resolver = EntityResolver()
    documents = ingest_pile(Path("fixtures"))
    all_facts = []
    for doc in documents:
        for fact in extract_facts(doc):
            canonical, score, confidence = resolver.resolve(fact.feature_name)
            fact.feature_name = canonical
            all_facts.append((doc, fact))
    print(f"Processed {len(all_facts)} fact(s) from {len(documents)} initial document(s)\n")

    watch_folder(Path("incoming"), all_facts, resolver)


if __name__ == "__main__":
    main()