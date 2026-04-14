# TASK-02 Public API — SQLite Data Ledger

## Module path: `src.data.ledger`

---

## `LedgerError(RuntimeError)`

Raised when the database is locked for longer than 500 ms or is otherwise unavailable.

---

## `class Ledger`

Persistent storage for file hashes, skeletons, and symbol references.
Initialises `ledger.db` in WAL mode on first connection.

**Key invariants:**
- WAL mode is always active — readers are never blocked by a concurrent write.
- `PRAGMA busy_timeout=500` enforces the 500 ms lock deadline; exceeding it raises `LedgerError`.
- Foreign-key enforcement is on; deleting a `ledger` row cascades to `context_cache`.

### Constructor

```python
Ledger(db_path: Path = _DB_PATH) -> None
```

Opens (or creates) the SQLite database at `db_path` and creates the three tables if they do not exist.

Can be used as a context manager (`with Ledger() as ledger:`).

---

### `ledger` table methods

```python
upsert_file(path: str, mtime: float, ast_hash: str, is_ignored: bool = False) -> None
```
Insert or replace a file record.

```python
get_file(path: str) -> Optional[sqlite3.Row]
```
Return the row for `path`, or `None`.

```python
delete_file(path: str) -> None
```
Remove a file record (cascades to `context_cache`).

---

### `context_cache` table methods

```python
upsert_cache(file_id: str, skeleton: Optional[str] = None, summary: Optional[str] = None) -> None
```
Store or update the extracted skeleton and/or LLM summary for a file.

```python
get_cache(file_id: str) -> Optional[sqlite3.Row]
```
Return the cache row for `file_id`, or `None`.

---

### `symbol_index` table methods

```python
upsert_symbol(symbol_name: str, source_file: str, references: list[str]) -> None
```
Store or update a symbol definition and the list of files that call/import it.
`references` is serialised as a JSON array.

```python
get_symbol(symbol_name: str, source_file: str) -> Optional[sqlite3.Row]
```
Return the raw row, or `None`.

```python
get_references(symbol_name: str, source_file: str) -> list[str]
```
Return the deserialised references list (empty list if symbol not found).

---

## Config keys read

None — the storage path (`ledger.db` in the repo root) and lock timeout (500 ms) are module-level constants, not driven by `load_config()`.

---

## DB tables owned

| Table | Primary key | Notes |
|---|---|---|
| `ledger` | `path` | One row per tracked file |
| `context_cache` | `file_id` | FK → `ledger.path`, cascade delete |
| `symbol_index` | `(symbol_name, source_file)` | `references` column is JSON array |
