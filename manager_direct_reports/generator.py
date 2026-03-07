"""
generator.py — Test case generator for: Manager with at Least Five Direct Reports

Outputs a JSON array of Employee rows to stdout.
The orchestrator pipes this to Judge0 as stdin.

Usage:
    python3 generator.py <rule_type> --args '{}' --rng-seed 42

rule_types:
    edge_cases  —  boundary conditions (no managers / exactly 4 reports, etc.)
    small       —  small org, 6–15 employees
    medium      —  medium org, 20–80 employees
    large       —  large org, 100–500 employees
    stress      —  stress test, 1000–5000 employees
"""

import argparse
import json
import random
import sys

# ---------------------------------------------------------------------------
# Name pools for realistic-looking data
# ---------------------------------------------------------------------------

_FIRST_NAMES = [
    "Alice", "Bob", "Carol", "Dan", "Eve", "Frank", "Grace", "Heidi",
    "Ivan", "Judy", "Karl", "Laura", "Mallory", "Nick", "Olivia", "Paul",
    "Quinn", "Rachel", "Sam", "Tina", "Uma", "Victor", "Wendy", "Xena",
    "Yolanda", "Zach", "Aaron", "Beth", "Chris", "Diana", "Evan", "Fiona",
    "George", "Hannah", "Ian", "Julia", "Kevin", "Lisa", "Mike", "Nancy",
    "Oscar", "Pam", "Ron", "Susan", "Tim", "Uma", "Vince", "Wanda",
]

_DEPARTMENTS = ["Engineering", "Sales", "HR", "Finance", "Marketing", "Legal", "Ops"]


def _unique_names(n: int, rng: random.Random) -> list:
    """Return a list of n unique names, extending with numeric suffixes if needed."""
    pool = rng.sample(_FIRST_NAMES, min(len(_FIRST_NAMES), n))
    while len(pool) < n:
        pool.append(f"Emp{len(pool) + 1}")
    return pool[:n]


# ---------------------------------------------------------------------------
# Case generators
# ---------------------------------------------------------------------------

def _make_employees(n: int, rng: random.Random, min_reports: int = 0) -> list:
    """
    Generate a list of n Employee row dicts.

    min_reports: if > 0, guarantee exactly one manager has >= min_reports direct reports.
                 Remaining employees are distributed randomly among managers.
    """
    names = _unique_names(n, rng)
    ids = list(range(101, 101 + n))
    rng.shuffle(ids)  # randomise id assignment

    employees = []

    if n == 1:
        # Single employee — no manager
        emp = {"id": ids[0], "name": names[0], "department": rng.choice(_DEPARTMENTS), "managerId": None}
        return [emp]

    # First employee is always a top-level manager (managerId = null)
    top_manager_id = ids[0]
    top_manager_name = names[0]
    employees.append({
        "id": top_manager_id,
        "name": top_manager_name,
        "department": rng.choice(_DEPARTMENTS),
        "managerId": None,
    })

    # Remaining employees
    for i in range(1, n):
        # Pick a manager from already-placed employees
        possible_managers = [e["id"] for e in employees]
        manager_id = rng.choice(possible_managers)
        employees.append({
            "id": ids[i],
            "name": names[i],
            "department": rng.choice(_DEPARTMENTS),
            "managerId": manager_id,
        })

    # If min_reports required, ensure top_manager_id gets at least min_reports direct reports
    if min_reports > 0:
        top_manager_reports = [e for e in employees if e["managerId"] == top_manager_id]
        while len(top_manager_reports) < min_reports and len(employees) < n:
            # Reassign some employees to report to top_manager
            candidates = [e for e in employees if e["managerId"] != top_manager_id and e["id"] != top_manager_id]
            if not candidates:
                break
            pick = rng.choice(candidates)
            pick["managerId"] = top_manager_id
            top_manager_reports = [e for e in employees if e["managerId"] == top_manager_id]

    rng.shuffle(employees)  # shuffle row order (doesn't affect results)
    return employees


# ---------------------------------------------------------------------------
# Rule-type dispatch
# ---------------------------------------------------------------------------

def generate_case(rule_type: str, args: dict) -> str:
    seed = args.get("seed")
    rng = random.Random(seed)

    if rule_type == "edge_cases":
        variant = rng.choice([
            "single_employee",
            "no_manager_qualifies",
            "exactly_five",
            "one_employee_only",
        ])

        if variant == "single_employee":
            rows = [{"id": 101, "name": "John", "department": "A", "managerId": None}]

        elif variant == "one_employee_only":
            rows = [{"id": 200, "name": "Solo", "department": "A", "managerId": None}]

        elif variant == "exactly_five":
            # Manager with exactly 5 reports (should appear in output)
            rows = [
                {"id": 1, "name": "Boss",  "department": "A", "managerId": None},
                {"id": 2, "name": "Alpha", "department": "A", "managerId": 1},
                {"id": 3, "name": "Beta",  "department": "A", "managerId": 1},
                {"id": 4, "name": "Gamma", "department": "A", "managerId": 1},
                {"id": 5, "name": "Delta", "department": "A", "managerId": 1},
                {"id": 6, "name": "Epsilon","department": "A", "managerId": 1},
            ]

        else:  # no_manager_qualifies — 4 reports
            rows = [
                {"id": 1, "name": "Boss",  "department": "A", "managerId": None},
                {"id": 2, "name": "Alpha", "department": "A", "managerId": 1},
                {"id": 3, "name": "Beta",  "department": "A", "managerId": 1},
                {"id": 4, "name": "Gamma", "department": "A", "managerId": 1},
                {"id": 5, "name": "Delta", "department": "A", "managerId": 1},
            ]

    elif rule_type == "small":
        n = rng.randint(6, 15)
        rows = _make_employees(n, rng, min_reports=5)

    elif rule_type == "medium":
        n = rng.randint(20, 80)
        rows = _make_employees(n, rng, min_reports=5)

    elif rule_type == "large":
        n = rng.randint(100, 500)
        rows = _make_employees(n, rng)

    elif rule_type == "stress":
        n = rng.randint(1000, 5000)
        rows = _make_employees(n, rng)

    else:
        raise ValueError(f"Unknown rule_type: '{rule_type}'")

    return json.dumps(rows)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate test data (JSON Employee rows) for manager_direct_reports"
    )
    parser.add_argument("rule_type", help="edge_cases | small | medium | large | stress")
    parser.add_argument("--args", type=json.loads, default={},
                        help="JSON dict of additional args (e.g. '{\"seed\": 42}')")
    parser.add_argument("--rng-seed", type=int, default=None,
                        help="Random seed override")
    ns = parser.parse_args()

    args = ns.args if ns.args else {}
    if ns.rng_seed is not None:
        args["seed"] = ns.rng_seed

    output = generate_case(ns.rule_type, args)
    print(output)
