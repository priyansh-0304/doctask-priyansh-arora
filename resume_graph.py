import sqlite3
from dotenv import load_dotenv
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from app.graph import build_graph

load_dotenv()


def _ask_yes_no(prompt: str) -> bool:
    while True:
        answer = input(f"{prompt} [y/n]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("  please answer y or n")


def main():
    conn = sqlite3.connect("checkpoints.db", check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    graph = build_graph().compile(checkpointer=checkpointer)

    config = {"configurable": {"thread_id": "run-1"}}

    # Pull the interrupt payload straight from the current graph state,
    # so what's shown here is exactly what the graph is waiting on.
    state = graph.get_state(config)
    interrupt_payload = state.tasks[0].interrupts[0].value if state.tasks else None

    if interrupt_payload is None:
        print("No pending human review found for this thread.")
        return

    print("--- Conflicts ---")
    conflict_decisions = {}
    for item in interrupt_payload["conflicts"]:
        approved = _ask_yes_no(f"  [{item['index']}] {item['summary']}\n  Accept this as a real conflict?")
        conflict_decisions[item["index"]] = approved

    print("\n--- Proposed entity merges ---")
    merge_decisions = {}
    for item in interrupt_payload["pending_merges"]:
        approved = _ask_yes_no(f"  [{item['index']}] {item['summary']}\n  Approve this merge?")
        merge_decisions[item["index"]] = approved

    decision = {"conflict_decisions": conflict_decisions, "merge_decisions": merge_decisions}

    print("\n--- Resuming pipeline with your decisions ---")
    result = graph.invoke(Command(resume=decision), config)
    print("\n✅ Done.")


if __name__ == "__main__":
    main()