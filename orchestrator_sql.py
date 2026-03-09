#!/usr/bin/env python3
"""
orchestrator_sql.py — SQL Problem Test Suite Generator

Extends the standard orchestrator with SQL-specific injection:
  1. Reads wrapper.py (the execution template)
  2. Reads solution.sql (the reference SQL)
  3. Injects the SQL into wrapper.py by replacing the USER_SQL placeholder
  4. Submits the combined Python to Judge0 (language_id: 71) with JSON stdin
  5. Writes <problem_name>_sql_testcases.json

Usage:
    cd Platform_questions/sql_problems/<problem_name>/
    python3 ../../orchestrator_sql.py -p .

The same injection step is performed by the platform at contest time when
a contestant submits their SQL answer.

Injection contract:
    wrapper.py contains:
        USER_SQL = ""
    After injection it becomes:
        USER_SQL = \"\"\"
        <contestant SQL>
        \"\"\"
"""

import argparse
import json
import os
import random
import sys
import subprocess
import time

import requests


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

JUDGE0_URL = "http://localhost:3000"
PYTHON_LANGUAGE_ID = 71
INJECTION_PLACEHOLDER = 'USER_SQL = ""'


# ---------------------------------------------------------------------------
# SQL Injection
# ---------------------------------------------------------------------------

def inject_sql_into_wrapper(wrapper_code: str, sql_query: str) -> str:
    """
    Replace the USER_SQL placeholder in wrapper.py with the actual SQL query.

    wrapper.py has:
        USER_SQL = ""

    After injection:
        USER_SQL = \"\"\"
        <sql_query>
        \"\"\"
    """
    if INJECTION_PLACEHOLDER not in wrapper_code:
        raise ValueError(
            f"Injection placeholder not found in wrapper.py.\n"
            f"Expected to find: {INJECTION_PLACEHOLDER}"
        )

    injected_assignment = f'USER_SQL = """\n{sql_query.strip()}\n"""'
    return wrapper_code.replace(INJECTION_PLACEHOLDER, injected_assignment, 1)


# ---------------------------------------------------------------------------
# Judge0 execution
# ---------------------------------------------------------------------------

def submit_to_judge0(source_code: str, stdin_data: str) -> dict:
    """Submit to Judge0 and return the result dict."""
    resp = requests.post(
        f"{JUDGE0_URL}/submissions?base64_encoded=false&wait=true"
        "&fields=stdout,stderr,status,time,memory",
        json={
            "source_code": source_code,
            "language_id": PYTHON_LANGUAGE_ID,
            "stdin": stdin_data,
            "enable_network": True,  # SQL wrappers need to reach mysql-eval-server
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Generator runner
# ---------------------------------------------------------------------------

def run_generator(generator_path: str, rule_type: str, args: dict) -> str:
    """Run generator.py and return the generated stdin (JSON string)."""
    seed = args.get("seed", random.randint(0, 999999))
    cmd = [
        sys.executable, generator_path,
        rule_type,
        "--args", json.dumps(args),
        "--rng-seed", str(seed),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def generate_test_suite(problem_dir: str):
    problem_dir = os.path.abspath(problem_dir)
    problem_name = os.path.basename(problem_dir)

    # Load required files
    def load(filename):
        path = os.path.join(problem_dir, filename)
        if not os.path.exists(path):
            print(f"❌ Missing required file: {filename}", file=sys.stderr)
            sys.exit(1)
        with open(path) as f:
            return f.read()

    wrapper_code  = load("wrapper.py")
    solution_sql  = load("solution.sql")
    config_data   = json.loads(load("config.json"))
    examples_data = json.loads(load("examples.json"))
    generator_path = os.path.join(problem_dir, "generator.py")

    # Build master source: inject solution SQL into wrapper
    print("🔧 Injecting solution.sql into wrapper.py...")
    master_source = inject_sql_into_wrapper(wrapper_code, solution_sql)

    # Test Judge0 health
    print("🏥 Checking Judge0 health...")
    try:
        ping = requests.get(JUDGE0_URL, timeout=5)
        print(f"   ✅ Judge0 is up at {JUDGE0_URL}")
    except Exception as e:
        print(f"   ❌ Cannot reach Judge0: {e}", file=sys.stderr)
        sys.exit(1)

    all_test_cases = []
    case_counter = 1

    # ── Visible examples ────────────────────────────────────────────────────
    print(f"\n📋 Processing {len(examples_data)} visible examples...")
    for i, ex in enumerate(examples_data):
        result = submit_to_judge0(master_source, ex["stdin"])
        status_id = result.get("status", {}).get("id")

        if status_id == 3:  # Accepted
            stdout = (result.get("stdout") or "").strip()
            expected = ex.get("expected_output", "").strip()
            match = "✅" if stdout == expected else "⚠️ "
            print(f"  {match} Example {i+1}: got '{stdout}' | expected '{expected}'")
            tc = {
                "test_case_no": case_counter,
                "stdin":           ex["stdin"],
                "expected_output": stdout,
                "is_visible":      True,
                "raw_time":        float(result.get("time") or 0),
                "raw_memory":      int(result.get("memory") or 0),
            }
        else:
            stderr = result.get("stderr") or result.get("status", {}).get("description", "")
            print(f"  ❌ Example {i+1} failed: {stderr}")
            tc = {
                "test_case_no": case_counter,
                "stdin":           ex["stdin"],
                "expected_output": ex.get("expected_output", ""),
                "is_visible":      True,
                "error":           str(stderr),
            }

        all_test_cases.append(tc)
        case_counter += 1

    # ── Generated test cases ─────────────────────────────────────────────────
    for rule in config_data["generation_logic"]:
        rule_type = rule["type"]
        target    = rule["count"]
        rule_args = rule.get("args", {})
        successes = 0

        print(f"\n--- Rule: {rule_type} (target: {target}) ---")

        attempts = 0
        while successes < target and attempts < target * 4:
            attempts += 1
            try:
                stdin_data = run_generator(generator_path, rule_type, rule_args)
                result     = submit_to_judge0(master_source, stdin_data)
                status_id  = result.get("status", {}).get("id")

                if status_id != 3:
                    stderr = result.get("stderr") or result.get("status", {})
                    print(f"  ⚠️ Attempt {attempts}: Judge0 status != 3 — {stderr}")
                    continue

                stdout = (result.get("stdout") or "").strip()
                tc = {
                    "test_case_no":   case_counter,
                    "stdin":          stdin_data,
                    "expected_output": stdout,
                    "is_visible":     False,
                    "raw_time":       float(result.get("time") or 0),
                    "raw_memory":     int(result.get("memory") or 0),
                }
                all_test_cases.append(tc)
                case_counter += 1
                successes += 1
                print(f"  ✅ Case #{tc['test_case_no']}: {tc['raw_time']}s, {tc['raw_memory']}KB")

            except subprocess.CalledProcessError as e:
                print(f"  ⚠️ Generator error: {e.stderr}")
            except Exception as e:
                print(f"  ⚠️ Unexpected error: {e}")

        print(f"  Generated {successes}/{target} cases for '{rule_type}'")

    # ── Write output ─────────────────────────────────────────────────────────
    output_file = os.path.join(problem_dir, f"{problem_name}_sql_testcases.json")
    with open(output_file, "w") as f:
        json.dump(all_test_cases, f, indent=2)

    total    = len(all_test_cases)
    visible  = sum(1 for tc in all_test_cases if tc.get("is_visible"))
    hidden   = total - visible
    errored  = sum(1 for tc in all_test_cases if "error" in tc)

    print(f"\n{'='*60}")
    print(f"✅ Test suite written → {output_file}")
    print(f"   Total: {total}  |  Visible: {visible}  |  Hidden: {hidden}  |  Errors: {errored}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SQL Problem Test Suite Generator"
    )
    parser.add_argument(
        "-p", "--problem-dir",
        required=True,
        help="Path to the SQL problem directory (containing wrapper.py, solution.sql, etc.)"
    )
    args = parser.parse_args()

    generate_test_suite(args.problem_dir)
