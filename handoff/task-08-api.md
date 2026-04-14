# API Handoff: TASK-08 MCP Server

## Public Symbols

### MCP Tool: `get_multi_hop_dependencies(path: str) -> str`
**Module:** `src/mcp/server.py` (registered via FastMCP), logic in `src/layers/logic_tracing.py`
**Purpose:** Traces the full multi-hop import/call graph for a source file using the symbol_index table.
**Returns:** JSON string with nested dependency tree.
**Key invariants:**
- Circular references appear as `{"path": "...", "circular": "[Circular: a.py ↔ b.py]"}` — never recursed.
- Already-expanded nodes in other branches appear as `{"path": "...", "cached": True, "dependencies": []}`.
- Always terminates — visited-set (cross-edges) + stack-set (back-edges) together prevent infinite recursion.

### MCP Tool: `match_api_route(path_literal: str) -> str`
**Module:** `src/mcp/server.py` (registered via FastMCP), logic in `src/layers/logic_tracing.py`
**Purpose:** Maps a frontend URL string (e.g. `"/api/user"`) to a backend route handler by scanning symbol_index.
**Returns:** JSON string with `symbol_name` and `source_file` of first match, or `{"result": "not found"}`.
**Key invariants:**
- Searches both `symbol_name LIKE %literal%` and `source_file LIKE %literal%`.
- Returns first match only.

### `trace_dependencies(path: str, *, db_path: Path = _DB_PATH) -> dict`
**Module:** `src/layers/logic_tracing.py`
**Purpose:** Recursive dependency traversal used by the MCP tool. Returns nested dict structure.
**Raises:** Nothing — sqlite errors propagate, but MCP layer handles them.

### `match_route(path_literal: str, *, db_path: Path = _DB_PATH) -> Optional[dict]`
**Module:** `src/layers/logic_tracing.py`
**Purpose:** Raw DB lookup used by the MCP tool. Returns `{"symbol_name": ..., "source_file": ...}` or `None`.

## Configuration Dependencies
None — DB path is a module-level constant (`ledger.db` at repo root).

## Database Tables Accessed
| Table | Access |
|---|---|
| `symbol_index` | READ — `symbol_name`, `source_file`, `references` columns |

## How to Start the Server
```bash
python -m src.mcp.server    # stdio transport (MCP default)
```
