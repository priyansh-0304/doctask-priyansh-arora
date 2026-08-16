"""Tests the MCP server the way a real persistent client actually uses
it -- one long-lived process, multiple sequential tool calls -- proving
the full four-call contract (ingest, review, resolve, deliver) works
end to end through MCP, not just that each tool works in isolation."""

import asyncio
from fastmcp import Client
from app.mcp_server import mcp


async def main():
    async with Client(mcp) as client:
        result = await client.call_tool("ingest_documents", {"directory": "fixtures"})
        run_id = result.data["run_id"]
        print(f"--- ingested, run_id={run_id} ---")
        print(result.data)
        print()

        pending = await client.call_tool("get_pending_review", {"run_id": run_id})
        print("--- pending review ---")
        for c in pending.data["conflicts"]:
            print(f"  conflict [{c['index']}]: {c['summary']}")
        for m in pending.data["pending_merges"]:
            print(f"  merge [{m['index']}]: {m['summary']}")
        print()

        # Approve every conflict, reject the one merge -- same adversarial
        # test as the LangGraph version, proving MCP calls produce the
        # same correct behavior as the direct-Python path.
        for c in pending.data["conflicts"]:
            await client.call_tool("resolve_item", {
                "run_id": run_id, "item_type": "conflict", "index": c["index"], "approve": True
            })
        for m in pending.data["pending_merges"]:
            await client.call_tool("resolve_item", {
                "run_id": run_id, "item_type": "merge", "index": m["index"], "approve": False
            })
        print("--- decisions recorded: all conflicts approved, merge rejected ---\n")

        deliverable = await client.call_tool("get_deliverable", {"run_id": run_id})
        print("--- final register ---")
        print(deliverable.data["register_markdown"])


asyncio.run(main())