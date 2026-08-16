import sqlite3
from dotenv import load_dotenv
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from app.graph import build_graph

load_dotenv()


def main():
    ALLOWED_TYPES = [
        ("app.models", "DocType"),
        ("app.models", "Document"),
        ("app.extraction", "FactType"),
        ("app.extraction", "ExtractedFact"),
        ("app.conflict_detection", "Conflict"),
        ("app.register", "SourcedValue"),
        ("app.register", "RegisterRow"),
    ]

    conn = sqlite3.connect("checkpoints.db", check_same_thread=False)
    checkpointer = SqliteSaver(conn, serde=JsonPlusSerializer(allowed_json_modules=ALLOWED_TYPES))
    graph = build_graph().compile(checkpointer=checkpointer)

    config = {"configurable": {"thread_id": "run-1"}}
    initial_state = {"fixtures_dir": "fixtures"}

    print("--- Running pipeline ---")
    result = graph.invoke(initial_state, config)

    if "__interrupt__" in result:
        print("\n⏸  Paused for human review. Run resume_graph.py to continue.")
    else:
        print("\n✅ Done:", result.get("human_decisions"))


if __name__ == "__main__":
    main()