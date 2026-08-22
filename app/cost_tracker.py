"""Requirement #10: 'it knows what it cost. A run can report what it
spent and where the time went, stage by stage.' Wraps every Gemini call
site to record token usage and latency per stage.

Module-level singleton, protected by a lock -- multiple concurrent runs
writing to the same tracker is a genuine possibility (see requirement #9),
and dict/list mutation is not guaranteed atomic across Python builds,
including free-threaded (no-GIL) CPython 3.13+.
"""

import threading
from dataclasses import dataclass


@dataclass
class CallRecord:
    stage: str
    model: str
    prompt_tokens: int
    output_tokens: int
    duration_seconds: float


class CostTracker:
    def __init__(self):
        self.records: list[CallRecord] = []
        self._lock = threading.Lock()

    def record(self, stage: str, model: str, prompt_tokens: int, output_tokens: int, duration_seconds: float):
        with self._lock:
            self.records.append(CallRecord(stage, model, prompt_tokens, output_tokens, duration_seconds))

    def report(self) -> str:
        with self._lock:
            records_snapshot = list(self.records)  # copy under lock, format outside it

        if not records_snapshot:
            return "--- Cost Report ---\nNo tracked calls."

        lines = ["--- Cost Report (stage by stage) ---"]
        by_stage: dict[str, list[CallRecord]] = {}
        for r in records_snapshot:
            by_stage.setdefault(r.stage, []).append(r)

        total_calls = total_prompt = total_output = 0
        total_time = 0.0

        for stage, records in by_stage.items():
            calls = len(records)
            prompt = sum(r.prompt_tokens for r in records)
            output = sum(r.output_tokens for r in records)
            duration = sum(r.duration_seconds for r in records)
            lines.append(f"  {stage}: {calls} call(s), {prompt} prompt tokens, "
                         f"{output} output tokens, {duration:.2f}s")
            total_calls += calls
            total_prompt += prompt
            total_output += output
            total_time += duration

        lines.append(f"  TOTAL: {total_calls} call(s), {total_prompt} prompt tokens, "
                     f"{total_output} output tokens, {total_time:.2f}s")
        return "\n".join(lines)


tracker = CostTracker()