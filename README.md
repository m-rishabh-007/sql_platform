# sql_platform

SQL problem execution engine for a LeetCode-style competitive programming platform.

Users write MySQL-style SQL queries in the browser. The platform wraps their SQL in
Python, spins up an in-memory SQLite database seeded from JSON test data, executes
the query, and grades the output — all via a self-hosted Judge0 instance (Python ID 71).

No extra database server. No special Judge0 language support. Just Python + SQLite.

---

## Repository structure

```
sql_platform/
├── orchestrator_sql.py          ← generates test suites for any problem
├── sql_engine/
│   ├── sql_executor.py          ← local dev / smoke-test helper
│   └── __init__.py
├── manager_direct_reports/      ← first problem (9 files)
│   ├── description.txt
│   ├── schema.sql
│   ├── solution.sql             ← reference SQL
│   ├── template.sql             ← contestant starter
│   ├── wrapper.py               ← platform injection template
│   ├── solution.py              ← self-contained (for orchestrator)
│   ├── generator.py             ← generates random JSON test data
│   ├── examples.json            ← visible examples (JSON stdin)
│   └── config.json              ← test generation buckets
└── .github/
    └── copilot-instructions.md  ← AI agent guide
```

---

## Execution flow

```
Contestant writes SQL in editor (template.sql is the starter)
         │
         ▼
Platform injects SQL into wrapper.py:
   USER_SQL = ""   →   USER_SQL = """SELECT name FROM Employee..."""
         │
         ▼
Combined Python file submitted to Judge0 (language_id: 71)
stdin = JSON array of table rows (from generator.py)
         │
         ▼
SQLite in-memory DB created → query executed → stdout printed
(rows sorted deterministically for grading)
         │
         ▼
Grader compares stdout to expected_output from testcases.json
```

---

## Judge0 setup

The platform expects Judge0 at `http://localhost:3000`.

```bash
# In your judge0-submission-system/ directory:
docker compose up -d

# Health check:
curl -s http://localhost:3000/system_info | head -c 80
```

---

## stdin / stdout contract

### stdin
JSON array of row objects matching the problem's table schema:
```json
[
  {"id": 101, "name": "John", "department": "A", "managerId": null},
  {"id": 102, "name": "Dan",  "department": "A", "managerId": 101}
]
```

### stdout
- One result row per line
- Multiple columns separated by `|`
- `NULL` for SQL NULL values
- Rows **sorted lexicographically** (case-insensitive) — so "any order" problems grade deterministically

---

## Generating test suites

```bash
# From the project root:
python3 orchestrator_sql.py -p manager_direct_reports/

# Output: manager_direct_reports/manager_direct_reports_sql_testcases.json
# Contains visible + hidden test cases with expected_output from Judge0
```

---

## Smoke-testing a problem locally

```bash
cd manager_direct_reports/

# Test with the example input
echo '[{"id":101,"name":"John","department":"A","managerId":null},
       {"id":102,"name":"Dan","department":"A","managerId":101},
       {"id":103,"name":"James","department":"A","managerId":101},
       {"id":104,"name":"Amy","department":"A","managerId":101},
       {"id":105,"name":"Anne","department":"A","managerId":101},
       {"id":106,"name":"Ron","department":"B","managerId":101}]' \
  | python3 solution.py
# Expected: John

# Run generator
python3 generator.py small --rng-seed 42

# Full rule types: edge_cases | small | medium | large | stress
```

---

## Adding a new SQL problem

1. Copy an existing problem as a starter:
   ```bash
   cp -r manager_direct_reports/ my_new_problem/
   cd my_new_problem/
   ```

2. Edit all 9 files — see [PLATFORM_CONTEXT.md](PLATFORM_CONTEXT.md) for full conventions.

3. Run smoke test:
   ```bash
   python3 generator.py small --rng-seed 42 | python3 solution.py
   ```

4. Generate test suite:
   ```bash
   python3 ../orchestrator_sql.py -p .
   ```

---

## SQL dialect

Problems use **SQLite SQL** which is compatible with ~95% of MySQL syntax used in
LeetCode-style problems:

| Feature | Supported |
|---------|-----------|
| SELECT, WHERE, GROUP BY, HAVING | ✅ |
| JOIN (INNER, LEFT, RIGHT\*) | ✅ (\*RIGHT via LEFT) |
| Subqueries, IN, EXISTS | ✅ |
| CTEs (WITH ... AS) | ✅ |
| Window functions (ROW_NUMBER, RANK, etc.) | ✅ SQLite 3.25+ |
| LIMIT / OFFSET | ✅ |
| IFNULL / COALESCE / CASE | ✅ |
| ILIKE | ❌ use `LOWER(col) LIKE ...` |

---

## Files per problem (9 total)

| File | Role |
|------|------|
| `description.txt` | Competition-style problem statement |
| `schema.sql` | CREATE TABLE DDL (reference only) |
| `solution.sql` | Reference SQL — correct answer |
| `template.sql` | Contestant starter (blank SELECT stub) |
| `wrapper.py` | Platform injection template — `USER_SQL = ""` |
| `solution.py` | Standalone Python = wrapper + solution SQL (used by orchestrator) |
| `generator.py` | Emits random JSON rows for edge/small/medium/large/stress cases |
| `examples.json` | 2–3 visible examples with JSON stdin |
| `config.json` | Test generation bucket counts |
