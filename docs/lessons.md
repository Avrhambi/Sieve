# Lessons

Read this before any debugging session — first hypotheses should be grounded in
what has already bitten us.

---

## 2026-09-06 — git commit detection attached snapshots to the wrong commit

**What broke.** `cs diff --since <hash>` sometimes returned "snapshot not found",
or diffed against the parent commit. In ~1 of 3 runs a commit made while the
daemon was running produced no `structural_snapshots` row at all.

**Root cause.** The watcher triggered commit detection on a filesystem event for
`.git/COMMIT_EDITMSG`, then resolved the hash by following `.git/HEAD` →
`.git/refs/heads/<branch>`. Git writes `COMMIT_EDITMSG` *before* it moves the
ref, so the resolve read the **parent** commit. On a fast commit the ref could
also be mid-update, yielding nothing. The README disclosed this only for
`git commit --amend`; it happened on every commit.

**The fix.** Trigger on `.git/logs/HEAD` (the reflog) instead. Git appends a line
there *after* the ref moves: `<old> <new> <ident> <ts> <tz>\t<message>`. Take
field 2 of the last line. Filter on the message starting with `commit` so
`checkout` / `reset` / `merge` reflog entries don't snapshot the current
`symbol_index` against an unrelated historical hash. Fall back to the old
HEAD-follow only when the reflog is unreadable (`core.logAllRefUpdates=false`).

**Gotcha to remember.** Anything under `.git/` that git writes as part of a
multi-step operation is not safe to read on the first filesystem event —
`COMMIT_EDITMSG`, `MERGE_MSG`, `ORIG_HEAD` all move relative to `HEAD` at
different times. The reflog and `.git/logs/refs/heads/<branch>` are the
after-the-fact record; prefer them for "what is the current commit".

---

## 2026-09-06 — the `cs` CLI could not see the daemon's ledger

**What broke.** `cd <project> && cs repo-map --json` returned `{"files": []}` and
silently created an empty `ledger.db` inside the Sieve checkout.

**Root cause.** `json_api.py` calls `Ledger()` with no argument, which resolves
to the `src/data/ledger.py` module-global `_DB_PATH` = `<sieve-repo>/ledger.db`.
The daemon writes the ledger to `<watched-project>/ledger.db`. The MCP server
took a path via `argv[1]`; the CLI had no equivalent, so it read (and created)
the wrong file.

**The fix.** `cli.py` resolves the ledger at startup — `--db` flag, then
`$SIEVE_DB`, then walk up from cwd for a `ledger.db` **stopping at the git repo
root** (a stray `ledger.db` in a parent dir must never bind an unrelated
project) — and calls `set_db_path()` before dispatch. A missing ledger exits
non-zero with a "run the daemon first" message and creates nothing (`Ledger()`
would auto-create the file on connect, so the `path.is_file()` guard must run
before any connect).

**Gotcha to remember.** `Ledger()` / `sqlite3.connect` creates the db file. Any
"the ledger is missing" error path must check `path.exists()` *before*
constructing a `Ledger`.
