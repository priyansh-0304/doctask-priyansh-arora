from langgraph.graph import StateGraph, END
from app.graph_state import PipelineState
from app.graph_nodes import (
    ingest_node, extract_node, resolve_node,
    conflict_node, register_node, human_review_node, commit_node,
)


def build_graph():
    graph = StateGraph(PipelineState)
    graph.add_node("ingest", ingest_node)
    graph.add_node("extract", extract_node)
    graph.add_node("resolve", resolve_node)
    graph.add_node("detect_conflicts", conflict_node)
    graph.add_node("build_register", register_node)
    graph.add_node("human_review", human_review_node)
    graph.add_node("commit", commit_node)

    graph.set_entry_point("ingest")
    graph.add_edge("ingest", "extract")
    graph.add_edge("extract", "resolve")
    graph.add_edge("resolve", "detect_conflicts")
    graph.add_edge("detect_conflicts", "build_register")
    graph.add_edge("build_register", "human_review")
    graph.add_edge("human_review", "commit")
    graph.add_edge("commit", END)
    return graph