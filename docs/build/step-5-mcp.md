# Step 5 — MCP Server

## What We're Building

A local read-only MCP server that exposes platform data to Claude Code. No writes. No AI embedded in the platform — Claude Code connects to this externally.

## Prerequisites

- Steps 1–4 complete and verified
- Platform has real data (at least one program, some assets, findings)

## Files to Create

```
src/
  mcp/
    __init__.py
    server.py          MCP server entry point
    resources/
      __init__.py
      programs.py      list programs, get by id
      assets.py        list by program, filter
      findings.py      list by program/status
      alerts.py        unseen count, list
      notes.py         session notes by program/asset
      recon_runs.py    latest per program, history
      scores.py        ranked list, get by program
    tools/
      __init__.py
      search.py        search_assets, summarize_program
```

## MCP Resources (Read-Only)

Each resource maps to a DB query. All read-only — no mutations.

```python
# programs
@server.list_resources()  →  all programs with status
@server.read_resource("programs/{id}")  →  full program detail + scope

# assets
@server.read_resource("assets/program/{program_id}")  →  asset list
@server.read_resource("assets/new/{program_id}")  →  is_new = true only

# findings
@server.read_resource("findings/program/{program_id}")  →  all findings
@server.read_resource("findings/status/{status}")  →  filter by status

# alerts
@server.read_resource("alerts/unseen")  →  count + list of unseen alerts

# session_notes
@server.read_resource("notes/program/{program_id}")  →  all notes
@server.read_resource("notes/asset/{asset_id}")  →  notes for one asset

# recon_runs
@server.read_resource("recon/latest/{program_id}")  →  most recent run
@server.read_resource("recon/history/{program_id}")  →  last 10 runs

# scores
@server.read_resource("scores/ranked")  →  all programs ranked by score
@server.read_resource("scores/program/{program_id}")  →  score detail
```

## MCP Tools (Read-Only Queries)

```python
@server.call_tool("search_assets")
# params: program_id, type?, status?, technology?, is_new?
# returns: filtered asset list

@server.call_tool("summarize_program")
# params: program_id
# returns: full context — program info, latest recon, unseen alerts,
#          finding counts by status, top assets, recent notes
```

## Registering with Claude Code

Add to `.claude/settings.local.json` in this project:

```json
{
  "mcpServers": {
    "bug-bounty": {
      "command": "python",
      "args": ["-m", "src.mcp.server"],
      "env": {
        "DATABASE_URL": "postgresql://bounty:changeme@localhost:5432/bountydb"
      }
    }
  }
}
```

## Verification Gate

```bash
# 1. MCP server starts without errors
python -m src.mcp.server
# Expected: "MCP server running on stdio"

# 2. Claude Code recognises the server
# In Claude Code: ask "what MCP tools do you have available?"
# Expected: bug-bounty server and its resources listed

# 3. Resources return correct data
# In Claude Code: "list my programs"
# Expected: programs from DB returned with correct data

# 4. summarize_program works
# In Claude Code: "summarize the Anthropic program"
# Expected: full context including assets, alerts, scores

# 5. No write operations possible
# Attempt: ask Claude to "add a new program" or "update a finding"
# Expected: no mutation tools available — Claude confirms it's read-only
```

## Notes

- MCP server runs as a subprocess managed by Claude Code — not a persistent service
- Starts when Claude Code needs it, stops when not in use
- No authentication needed — it only reads data and runs locally
- Keep all DB queries in `resources/` files, not inlined in server.py
