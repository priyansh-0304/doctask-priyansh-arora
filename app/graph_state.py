from typing import TypedDict, Optional


class PipelineState(TypedDict, total=False):
    fixtures_dir: str
    documents: list
    all_facts: list
    original_feature_names: dict[str, str]  # fact_id -> pre-merge name, NOT a position-indexed list
    canonical_names: list[str]
    canonical_embeddings: list[list[float]]
    pending_review: list[dict]
    conflicts: list
    register_rows: list
    register_markdown: str
    human_decisions: Optional[dict]