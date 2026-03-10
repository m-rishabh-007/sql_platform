"""
test_e2e.py -- End-to-end smoke test for the SQL platform.

Simulates what the production platform does when a user submits SQL:
  1. Read wrapper.py (the execution template)
  2. Inject SQL into it (solution.sql for the correct answer, a wrong SQL for WA test)
  3. POST to Judge0 at localhost:3000 with enable_network=true
  4. Compare stdout vs expected_output
  5. Report PASS / WRONG ANSWER / RUNTIME ERROR / etc.

Run from the repo root:
    python3 test_e2e.py
"""

import json
import os
import urllib.request
import urllib.error

JUDGE0_URL = "http://localhost:3000/submissions"
PROBLEM_DIR = os.path.join(os.path.dirname(__file__), "manager_direct_reports")

# ------------------------------------------------------------------ helpers --

def inject_sql(wrapper_code: str, sql: str) -> str:
    """Replicates the production injection the platform performs."""
    return wrapper_code.replace(
        'USER_SQL = ""',
        f'USER_SQL = """\n{sql.strip()}\n"""'
    )


def submit_to_judge0(source_code: str, stdin: str) -> dict:
    payload = json.dumps({
        "source_code": source_code,
        "language_id": 71,          # Python 3
        "stdin": stdin,
        "enable_network": True,     # MUST be true -- sandbox needs MySQL DNS
    }).encode()

    req = urllib.request.Request(
        JUDGE0_URL + "?base64_encoded=false&wait=true"
                   + "&fields=stdout,stderr,status,compile_output",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def verdict(result: dict, expected_output: str) -> tuple[str, str]:
    """Return (verdict_label, detail_string)."""
    status_desc = result["status"]["description"]
    status_id   = result["status"]["id"]
    stdout      = (result.get("stdout") or "").rstrip("\n")
    stderr      = (result.get("stderr") or "").strip()[:300]
    compile_out = (result.get("compile_output") or "").strip()[:300]

    if status_id != 3:          # 3 = Accepted (execution succeeded)
        detail = stderr or compile_out or "(no detail)"
        return f"RUNTIME/COMPILE ERROR ({status_desc})", detail

    if stdout == expected_output:
        return "ACCEPTED", stdout
    else:
        return "WRONG ANSWER", (
            f"  Expected : {repr(expected_output)}\n"
            f"  Got      : {repr(stdout)}"
        )


# -------------------------------------------------------------------- main --

def run_tests(sql_label: str, sql: str, cases: list[dict]):
    print(f"\n{'='*60}")
    print(f" SQL under test: {sql_label}")
    print(f"{'='*60}")

    with open(os.path.join(PROBLEM_DIR, "wrapper.py")) as f:
        wrapper_code = f.read()

    injected = inject_sql(wrapper_code, sql)

    # quick sanity -- injection must have changed the file.
    # Note: 'USER_SQL = ""' is a substring of 'USER_SQL = """', so we check
    # for the original single-line form (with newline) being gone.
    assert 'USER_SQL = ""\n' not in injected, \
        "Injection failed: anchor string not found in wrapper.py"
    assert sql.strip()[:20] in injected, \
        "Injection failed: SQL not found in injected code"

    passed = 0
    for i, case in enumerate(cases, 1):
        stdin           = case["stdin"]
        expected_output = case["expected_output"]
        visibility      = case.get("visibility", "hidden")

        print(f"\n  Test {i} [{visibility}]")
        print(f"  stdin snippet: {stdin[:80]}{'...' if len(stdin)>80 else ''}")

        try:
            result = submit_to_judge0(injected, stdin)
        except Exception as exc:
            print(f"  !! HTTP ERROR: {exc}")
            continue

        label, detail = verdict(result, expected_output)
        print(f"  Verdict : {label}")
        if label == "ACCEPTED":
            print(f"  Output  : {repr(detail)}")
            passed += 1
        else:
            print(detail)

    total = len(cases)
    print(f"\n  Result: {passed}/{total} test cases passed")
    return passed, total


def main():
    # ------------------------------------------------------------------
    # Load test cases (examples + a couple generated ones if available)
    # ------------------------------------------------------------------
    with open(os.path.join(PROBLEM_DIR, "examples.json")) as f:
        cases = json.load(f)

    testcases_path = os.path.join(
        PROBLEM_DIR, "manager_direct_reports_sql_testcases.json"
    )
    generated_cases = []
    if os.path.exists(testcases_path):
        with open(testcases_path) as f:
            all_cases = json.load(f)
        # Take a couple of small generated cases for speed
        generated_cases = [c for c in all_cases if c.get("visibility") == "hidden"][:2]

    all_test_cases = cases + generated_cases
    print(f"Running {len(all_test_cases)} test cases "
          f"({len(cases)} examples + {len(generated_cases)} generated)")

    # ------------------------------------------------------------------
    # Test 1: Correct solution (should all PASS)
    # ------------------------------------------------------------------
    with open(os.path.join(PROBLEM_DIR, "solution.sql")) as f:
        correct_sql = f.read()
    # Strip comments for injection clarity
    sql_lines = [l for l in correct_sql.splitlines() if not l.strip().startswith("--") and l.strip()]
    correct_sql_clean = "\n".join(sql_lines)

    p1, t1 = run_tests("CORRECT SOLUTION (solution.sql)", correct_sql_clean, all_test_cases)

    # ------------------------------------------------------------------
    # Test 2: A deliberately wrong SQL (should produce WRONG ANSWER on
    # example 1 which expects 'John', this returns everyone)
    # ------------------------------------------------------------------
    wrong_sql = "SELECT name FROM Employee"
    p2, t2 = run_tests("WRONG SQL  (SELECT name FROM Employee -- no filter)", wrong_sql, cases[:1])

    # ------------------------------------------------------------------
    # Test 3: A completely broken SQL (should produce RUNTIME ERROR)
    # ------------------------------------------------------------------
    broken_sql = "SELECT nonexistent_column FROM Employee"
    p3, t3 = run_tests("BROKEN SQL (bad column name)", broken_sql, cases[:1])

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print(" SUMMARY")
    print(f"{'='*60}")
    print(f"  Correct solution  : {p1}/{t1} passed  {'[OK]' if p1==t1 else '[!!]'}")
    print(f"  Wrong SQL         : {p2}/{t2} passed  {'[OK - expected 0/1]' if p2==0 else '[!!]'}")
    print(f"  Broken SQL        : {p3}/{t3} passed  {'[OK - expected 0/1]' if p3==0 else '[!!]'}")

    all_ok = (p1 == t1) and (p2 == 0) and (p3 == 0)
    print(f"\n  Overall: {'ALL CHECKS PASSED -- platform logic is correct' if all_ok else 'SOME CHECKS FAILED'}")


if __name__ == "__main__":
    main()
