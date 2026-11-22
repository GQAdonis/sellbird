"""Static job-graph checks on the committed workflows (SCN-PIPE-001 and SCN-PIPE-002).

  _graph.py graph        WORKFLOWS_DIR
  _graph.py trivy-order  WORKFLOWS_DIR
  _graph.py mutate KIND  SRC_DIR DST_DIR     KIND: if-always | drop-tests-need

Output lines: "PASS|FAIL|WARN <scenario-id> <job or step>: <reason>"; exit 1 on any FAIL.
Only JOB-level `if` is judged (a step-level `if: always()`, such as the registry logout step,
is not a violation). Needs PyYAML (the repo's .venv).

Job ids in images.yml (see its header): tests = the call of tests.yml, build = build and scan,
images = publish to GHCR, deploy = pin production overlay.
"""
import os
import re
import shutil
import sys

import yaml

TESTS, SCAN, PUBLISH, DEPLOY = "tests", "build", "images", "deploy"
IMAGES = "images.yml"
BAD_STATUS = (("always", re.compile(r"\balways\s*\(")),
              ("cancelled", re.compile(r"\bcancelled\s*\(")),
              ("failure", re.compile(r"\bfailure\s*\(")))
RISKY = [re.compile(p) for p in (
    r"packages:\s*write", r"docker\s+push", r"pin_overlay", r"create-github-app-token",
    r"environment:\s*production", r"build-push-action[\s\S]{0,400}?push:\s*true")]
EVENTS_THAT_SHIP = {"push", "workflow_run", "schedule", "release", "workflow_dispatch"}

lines = []
failed = False


def emit(level, scn, where, msg):
    global failed
    if level == "FAIL":
        failed = True
    lines.append("%s %s %s: %s" % (level, scn, where, msg))
    print(lines[-1])


def load(path):
    with open(path) as fh:
        text = fh.read()
    return yaml.safe_load(text), text


def triggers(wf):
    on = wf.get("on", wf.get(True))  # YAML 1.1 reads the bare key `on` as True
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {k: None for k in on}
    return on or {}


def needs(job):
    n = job.get("needs") or []
    return [n] if isinstance(n, str) else list(n)


def norm_if(job):
    v = job.get("if")
    if v is None:
        return None
    s = str(v).strip()
    s = re.sub(r"^\$\{\{|\}\}$", "", s).replace('"', "'")
    return re.sub(r"\s+", "", s)


def run_text(step):
    return str(step.get("run", ""))


def scan_steps(steps):
    out = []
    for i, s in enumerate(steps):
        if str(s.get("uses", "")).startswith("aquasecurity/trivy-action") or re.search(
                r"\btrivy\s+(image|fs|rootfs|repo|config|sbom|k8s)\b", run_text(s)):
            out.append(i)
    return out


def idx(steps, pred):
    return [i for i, s in enumerate(steps) if pred(s)]


def graph(directory):
    files = sorted(f for f in os.listdir(directory) if f.endswith((".yml", ".yaml")))
    if IMAGES not in files:
        emit("FAIL", "SCN-PIPE-001", IMAGES, "workflow file not found in " + directory)
        return
    wf, _ = load(os.path.join(directory, IMAGES))
    jobs = wf.get("jobs") or {}
    for j in (TESTS, SCAN, PUBLISH, DEPLOY):
        if j not in jobs:
            emit("FAIL", "SCN-PIPE-001", j, "job is missing from " + IMAGES)
    if failed:
        return

    # tests job calls tests.yml, which is callable.
    uses = str(jobs[TESTS].get("uses", ""))
    if uses != "./.github/workflows/tests.yml":
        emit("FAIL", "SCN-PIPE-001", TESTS, "does not call ./.github/workflows/tests.yml (uses=%r)" % uses)
    else:
        called = os.path.join(directory, "tests.yml")
        if os.path.isfile(called) and "workflow_call" in triggers(load(called)[0]):
            emit("PASS", "SCN-PIPE-001", TESTS, "calls tests.yml, which has a workflow_call trigger")
        else:
            emit("FAIL", "SCN-PIPE-001", TESTS, "tests.yml has no workflow_call trigger")

    for scn, shippers in (("SCN-PIPE-001", (PUBLISH, DEPLOY)), ("SCN-PIPE-002", (PUBLISH,))):
        for j in shippers:
            n = needs(jobs[j])
            missing = [x for x in (TESTS, SCAN) if x not in n]
            if missing:
                emit("FAIL", scn, j, "needs %s but not %s" % (n, missing))
            else:
                emit("PASS", scn, j, "needs the tests job and the scan job")
            expr = norm_if(jobs[j])
            bad = [label for label, rx in BAD_STATUS if expr and rx.search(expr)]
            if bad:
                emit("FAIL", scn, j, "job-level if contains %s(): it could run after a failed need" % ", ".join(bad))
            else:
                emit("PASS", scn, j, "no job-level if that survives a failed need")
            ok = (expr is not None and "github.event_name=='push'" in expr
                  and "github.ref=='refs/heads/main'" in expr and "||" not in expr)
            if ok:
                emit("PASS", scn, j, "gated on a push to main")
            else:
                emit("FAIL", scn, j, "job-level if does not restrict it to a push to main (if=%r)" % expr)
    for j in (TESTS, SCAN):
        expr = norm_if(jobs[j])
        bad = [label for label, rx in BAD_STATUS if expr and rx.search(expr)]
        if bad:
            emit("FAIL", "SCN-PIPE-001", j, "job-level if contains %s()" % ", ".join(bad))

    # The push trigger is main only; only publish has packages: write; only deploy uses production.
    push = triggers(wf).get("push")
    if not (isinstance(push, dict) and push.get("branches") == ["main"]):
        emit("FAIL", "SCN-PIPE-001", IMAGES, "push trigger is not restricted to branches [main]")
    for j, job in jobs.items():
        perms = job.get("permissions") or {}
        if j != PUBLISH and isinstance(perms, dict) and perms.get("packages") == "write":
            emit("FAIL", "SCN-PIPE-001", j, "has packages: write but is not the publish job")
        if j != DEPLOY and job.get("environment"):
            emit("FAIL", "SCN-PIPE-001", j, "uses an environment but is not the deploy job")

    # No other workflow deploys or publishes on push.
    for f in files:
        if f == IMAGES:
            continue
        other, text = load(os.path.join(directory, f))
        risky = [rx.pattern for rx in RISKY if rx.search(text)]
        trig = set(triggers(other))
        if risky and trig & EVENTS_THAT_SHIP:
            emit("FAIL", "SCN-PIPE-001", f, "can publish or deploy and triggers on %s" % sorted(trig & EVENTS_THAT_SHIP))
        elif risky:
            emit("WARN", "SCN-PIPE-001", f, "contains publish or deploy tokens but triggers only on %s" % sorted(trig))
        else:
            emit("PASS", "SCN-PIPE-001", f, "no publish or deploy step")

    # SCN-PIPE-002: ordering inside the scan job, and publish loads the scanned archive.
    steps = jobs[SCAN].get("steps") or []
    scans = scan_steps(steps)
    save = idx(steps, lambda s: "docker image inspect" in run_text(s) and "docker save" in run_text(s))
    build = idx(steps, lambda s: str(s.get("uses", "")).startswith("docker/build-push-action"))
    verify = idx(steps, lambda s: "verify-trivy.sh" in run_text(s))
    recheck = idx(steps, lambda s: "recheck-image.sh" in run_text(s))
    upload = idx(steps, lambda s: str(s.get("uses", "")).startswith("actions/upload-artifact"))
    if not scans:
        emit("FAIL", "SCN-PIPE-002", SCAN, "no scan step found")
        return
    first, last = min(scans), max(scans)
    if not save:
        emit("FAIL", "SCN-PIPE-002", SCAN, "no step records the image ID and saves the image")
    elif max(save) < first and build and max(build) < min(save):
        emit("PASS", "SCN-PIPE-002", SCAN, "build (step %d) then image-ID/save (step %d) precede the first scan (step %d)" % (max(build) + 1, max(save) + 1, first + 1))
    else:
        emit("FAIL", "SCN-PIPE-002", SCAN, "the build and the image-ID/save step must both precede every scan step (save=%s first-scan=%d)" % ([i + 1 for i in save], first + 1))
    if not verify or max(verify) > first:
        emit("FAIL", "SCN-PIPE-002", SCAN, "the Trivy checksum step does not precede the first scan")
    else:
        emit("PASS", "SCN-PIPE-002", SCAN, "the Trivy checksum is verified before the first scan")
    if recheck and min(recheck) > last:
        emit("PASS", "SCN-PIPE-002", SCAN, "a recheck step (step %d) follows the last scan (step %d)" % (min(recheck) + 1, last + 1))
    else:
        emit("FAIL", "SCN-PIPE-002", SCAN, "no recheck step after the last scan")
    if upload and recheck and min(upload) > max(recheck):
        emit("PASS", "SCN-PIPE-002", SCAN, "the archive is uploaded only after the recheck")
    else:
        emit("FAIL", "SCN-PIPE-002", SCAN, "the archive upload does not come after the recheck")
    for kind in ("vuln", "secret"):
        real = [i for i in scans
                if str((steps[i].get("with") or {}).get("scanners")) == kind
                and str((steps[i].get("with") or {}).get("exit-code")) == "1"
                and not steps[i].get("continue-on-error")]
        if real:
            emit("PASS", "SCN-PIPE-002", SCAN, "a blocking %s scan exists (exit-code 1, no continue-on-error)" % kind)
        else:
            emit("FAIL", "SCN-PIPE-002", SCAN, "no blocking %s scan step" % kind)
    psteps = jobs[PUBLISH].get("steps") or []
    rebuild = idx(psteps, lambda s: str(s.get("uses", "")).startswith("docker/build-push-action")
                  or re.search(r"\bdocker\s+(buildx\s+)?build\b", run_text(s)))
    load_ok = idx(psteps, lambda s: "docker load" in run_text(s) and "IMAGE_ID" in run_text(s))
    if rebuild:
        emit("FAIL", "SCN-PIPE-002", PUBLISH, "the publish job builds an image instead of loading the scanned archive")
    elif not load_ok:
        emit("FAIL", "SCN-PIPE-002", PUBLISH, "no step loads the archive and compares the image ID")
    else:
        emit("PASS", "SCN-PIPE-002", PUBLISH, "publishes the loaded, ID-checked archive and never rebuilds")


def trivy_order(directory):
    wf, _ = load(os.path.join(directory, IMAGES))
    steps = wf["jobs"][SCAN].get("steps") or []
    scans = scan_steps(steps)
    verify = idx(steps, lambda s: "verify-trivy.sh" in run_text(s))
    if scans and verify and max(verify) < min(scans):
        emit("PASS", "SCN-PIPE-002", SCAN, "verify-trivy.sh runs before the first scan")
    else:
        emit("FAIL", "SCN-PIPE-002", SCAN, "verify-trivy.sh does not run before the first scan")


def mutate(kind, src, dst):
    shutil.copytree(src, dst)
    path = os.path.join(dst, IMAGES)
    with open(path) as fh:
        rows = fh.read().split("\n")
    start = None
    if kind == "if-always":
        job, key, new = DEPLOY, "    if:", "    if: always()"
    elif kind == "drop-tests-need":
        job, key, new = PUBLISH, "    needs:", "    needs: [build]"
    else:
        raise SystemExit("unknown mutation " + kind)
    for i, row in enumerate(rows):
        if row == "  %s:" % job:
            start = i
        elif start is not None and row.startswith(key):
            rows[i] = new
            break
    else:
        raise SystemExit("mutation did not apply to job " + job)
    with open(path, "w") as fh:
        fh.write("\n".join(rows))
    print("mutated: job %s now has%s" % (job, new[3:]))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "graph" and len(sys.argv) == 3:
        graph(sys.argv[2])
    elif cmd == "trivy-order" and len(sys.argv) == 3:
        trivy_order(sys.argv[2])
    elif cmd == "mutate" and len(sys.argv) == 5:
        mutate(sys.argv[2], sys.argv[3], sys.argv[4])
        sys.exit(0)
    else:
        print(__doc__)
        sys.exit(2)
    sys.exit(1 if failed else 0)
