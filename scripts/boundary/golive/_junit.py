"""JUnit XML reader for the golive boundary (pytest --junitxml output).

  _junit.py counts   XML
  _junit.py ids      FIXTURE [--task T]...
  _junit.py required XML FIXTURE [--task T]... [--root DIR] [--expect pass|fail]

Why junit and not `--collect-only` plus -rA parsing: one machine-readable file records every
collected test with its outcome (passed, failed, error, skipped), so "collected and passed" is
one lookup. A node ID is rebuilt from each <testcase>: classname (dotted module path, plus a
class if any) is mapped to the longest dotted prefix that is a file under --root, then
"::" + the rest + name. Assumption (pytest xunit2 default, not run here): classname is the
module path with dots and name is the function name including its [param] suffix.

Matching: a required ID equals a node ID, or (when it has no "[") is the part of a node ID
before "[" (so test_f covers every parametrization).

`required --expect pass` (default) exits 0 only if every required ID matched at least one
test and every matched test passed. `--expect fail` exits 0 only if at least one matched test
failed or errored (used for the reverted-edit controls). Output is IDs and counts only.
"""
import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET


def load_cases(xml_path, root):
    tree = ET.parse(xml_path).getroot()
    suites = [tree] if tree.tag == "testsuite" else list(tree)
    cases = []
    for suite in suites:
        for tc in suite.iter("testcase"):
            classname = tc.get("classname", "")
            name = tc.get("name", "")
            parts = classname.split(".") if classname else []
            nodeid = None
            for i in range(len(parts), 0, -1):
                path = "/".join(parts[:i]) + ".py"
                if os.path.isfile(os.path.join(root, path)):
                    rest = "::".join(parts[i:])
                    nodeid = path + "::" + (rest + "::" if rest else "") + name
                    break
            if nodeid is None:
                nodeid = classname + "::" + name
            if tc.find("failure") is not None:
                outcome = "failed"
            elif tc.find("error") is not None:
                outcome = "error"
            elif tc.find("skipped") is not None:
                outcome = "skipped"
            else:
                outcome = "passed"
            cases.append((nodeid, outcome))
    return cases


def counts(cases):
    c = {"tests": len(cases), "passed": 0, "failed": 0, "error": 0, "skipped": 0}
    for _, outcome in cases:
        c[outcome] += 1
    return c


def read_fixture(path, tasks):
    groups = []  # (task, id)
    task = None
    with open(path) as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                if line.startswith("# task:"):
                    task = line.split(":", 1)[1].strip()
                continue
            if tasks and task not in tasks:
                continue
            groups.append((task, line))
    return groups


def matches(required, nodeid):
    if nodeid == required:
        return True
    return "[" not in required and nodeid.split("[", 1)[0] == required


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("counts")
    p.add_argument("xml")
    p = sub.add_parser("ids")
    p.add_argument("fixture")
    p.add_argument("--task", action="append", default=[])
    p = sub.add_parser("required")
    p.add_argument("xml")
    p.add_argument("fixture")
    p.add_argument("--task", action="append", default=[])
    p.add_argument("--root", default=".")
    p.add_argument("--expect", choices=["pass", "fail"], default="pass")
    a = ap.parse_args()

    if a.cmd == "ids":
        for _, rid in read_fixture(a.fixture, a.task):
            print(rid)
        return 0

    cases = load_cases(a.xml, getattr(a, "root", "."))
    if a.cmd == "counts":
        print(json.dumps(counts(cases)))
        return 0

    bad = 0
    any_failed = False
    total = 0
    for task, rid in read_fixture(a.fixture, a.task):
        total += 1
        hit = [o for n, o in cases if matches(rid, n)]
        c = {k: hit.count(k) for k in ("passed", "failed", "error", "skipped")}
        if a.expect == "pass":
            ok = bool(hit) and c["passed"] == len(hit)
            if not ok:
                bad += 1
        else:
            ok = bool(hit) and (c["failed"] + c["error"]) > 0
            any_failed = any_failed or ok
        print("ID %s %s matched=%d passed=%d failed=%d error=%d skipped=%d  task=%s" % (
            "OK" if ok else "NOT-OK", rid, len(hit), c["passed"], c["failed"], c["error"],
            c["skipped"], task))
    if total == 0:
        print("no required IDs selected")
        return 1
    if a.expect == "pass":
        print("required: %d ids, %d not satisfied" % (total, bad))
        return 0 if bad == 0 else 1
    print("required: %d ids, at least one failed/errored: %s" % (total, any_failed))
    return 0 if any_failed else 1


if __name__ == "__main__":
    sys.exit(main())
