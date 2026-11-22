"""Static checks on the rendered Kubernetes base (SCN-FRESH-001) and the fixture mutations.

  _fresh.py check RENDERED.yaml
  _fresh.py mutate-hook SRC_DIR DST_DIR   copy the base, remove the migration ServiceAccount's Argo CD annotations
  _fresh.py mutate-dns  SRC_DIR DST_DIR   copy the base, widen the NodeLocal DNS peer to 169.254.0.0/16

`check` prints "PASS ..." / "FAIL ..." lines and exits 1 on any FAIL. Names the offending
object or peer in every FAIL line. Needs PyYAML (the repo's .venv).
"""
import ipaddress
import json
import shutil
import sys

import yaml

HOOK = "argocd.argoproj.io/hook"
WAVE = "argocd.argoproj.io/sync-wave"
KUBE_DNS = 'sel:ns={"kubernetes.io/metadata.name": "kube-system"} pod={"k8s-app": "kube-dns"}'
NODELOCAL = "ip:169.254.20.10/32"
LINK_LOCAL = ipaddress.ip_network("169.254.0.0/16")


def ann(doc):
    return (doc.get("metadata") or {}).get("annotations") or {}


def name(doc):
    return (doc.get("metadata") or {}).get("name", "?")


def hooks(doc):
    return [h.strip() for h in str(ann(doc).get(HOOK, "")).split(",") if h.strip()]


def wave(doc):
    return int(str(ann(doc).get(WAVE, "0")).strip())


def peer_key(peer):
    if "ipBlock" in peer:
        ib = peer["ipBlock"]
        extra = " except=" + ",".join(ib["except"]) if ib.get("except") else ""
        return "ip:%s%s" % (ib["cidr"], extra)
    ns = (peer.get("namespaceSelector") or {}).get("matchLabels")
    pod = (peer.get("podSelector") or {}).get("matchLabels")
    return "sel:ns=%s pod=%s" % (json.dumps(ns, sort_keys=True), json.dumps(pod, sort_keys=True))


def covers_53(port):
    if not isinstance(port, dict):
        return False
    try:
        lo = int(port.get("port"))
    except (TypeError, ValueError):
        return False
    hi = int(port.get("endPort", lo))
    return lo <= 53 <= hi


def check(path):
    with open(path) as fh:
        docs = [d for d in yaml.safe_load_all(fh) if d]
    fails = []

    # (a) The migration Job's ServiceAccount is itself an earlier PreSync hook.
    jobs = [d for d in docs if d.get("kind") == "Job" and "PreSync" in hooks(d)]
    if not jobs:
        fails.append("FAIL no PreSync migration Job in the render")
    sas = {name(d): d for d in docs if d.get("kind") == "ServiceAccount"}
    for job in jobs:
        sa_name = ((job.get("spec") or {}).get("template") or {}).get("spec", {}).get("serviceAccountName")
        jn = name(job)
        if not sa_name:
            fails.append("FAIL Job/%s has no serviceAccountName (the namespace default account is not a hook)" % jn)
            continue
        sa = sas.get(sa_name)
        if sa is None:
            fails.append("FAIL ServiceAccount/%s used by Job/%s is not in the render: on a fresh install it would not exist at PreSync" % (sa_name, jn))
            continue
        if "PreSync" not in hooks(sa):
            fails.append("FAIL ServiceAccount/%s (used by Job/%s) is not a PreSync hook" % (sa_name, jn))
            continue
        try:
            sw, jw = wave(sa), wave(job)
        except ValueError:
            fails.append("FAIL ServiceAccount/%s or Job/%s has a non-numeric sync-wave" % (sa_name, jn))
            continue
        if sw >= jw:
            fails.append("FAIL ServiceAccount/%s wave %d is not lower than Job/%s wave %d" % (sa_name, sw, jn, jw))
        else:
            print("PASS ServiceAccount/%s is a PreSync hook at wave %d, before Job/%s at wave %d" % (sa_name, sw, jn, jw))

    # (b) Port 53 egress peers across every NetworkPolicy are exactly kube-dns pods and the NodeLocal /32.
    seen = {}  # peer key -> policy names
    for d in docs:
        if d.get("kind") != "NetworkPolicy":
            continue
        pn = name(d)
        for rule in (d.get("spec") or {}).get("egress") or []:
            ports = rule.get("ports")
            hits_53 = (not ports) or any(covers_53(p) for p in ports)
            peers = rule.get("to")
            if hits_53 and not peers:
                fails.append("FAIL NetworkPolicy/%s has an egress rule with no peer restriction that includes port 53" % pn)
            if hits_53:
                for peer in peers or []:
                    seen.setdefault(peer_key(peer), []).append(pn)
            for peer in peers or []:
                ib = peer.get("ipBlock")
                if not ib:
                    continue
                try:
                    net = ipaddress.ip_network(ib["cidr"])
                except ValueError:
                    fails.append("FAIL NetworkPolicy/%s has an unparsable cidr" % pn)
                    continue
                if net.version != 4 or not net.overlaps(LINK_LOCAL):
                    continue
                if net == ipaddress.ip_network("169.254.20.10/32"):
                    continue
                if net.subnet_of(LINK_LOCAL):
                    fails.append("FAIL NetworkPolicy/%s allows link-local peer %s (only 169.254.20.10/32 on port 53 is allowed)" % (pn, ib["cidr"]))
                else:
                    excepts = [ipaddress.ip_network(e) for e in ib.get("except", [])]
                    if not any(e.supernet_of(LINK_LOCAL) for e in excepts):
                        fails.append("FAIL NetworkPolicy/%s peer %s does not except 169.254.0.0/16" % (pn, ib["cidr"]))
    expected = {KUBE_DNS, NODELOCAL}
    for key in sorted(set(seen) - expected):
        fails.append("FAIL unexpected port 53 egress peer %s in NetworkPolicy/%s" % (key, ",".join(sorted(set(seen[key])))))
    for key in sorted(expected - set(seen)):
        fails.append("FAIL expected port 53 egress peer missing: %s" % key)
    if set(seen) == expected:
        print("PASS port 53 egress peers are exactly kube-dns pods and 169.254.20.10/32")

    for line in fails:
        print(line)
    return 1 if fails else 0


def _copy(src, dst):
    shutil.copytree(src, dst)


def _rewrite(path, fn):
    with open(path) as fh:
        docs = [d for d in yaml.safe_load_all(fh) if d]
    changed = fn(docs)
    with open(path, "w") as fh:
        yaml.safe_dump_all(docs, fh, sort_keys=False)
    return changed


def mutate_hook(src, dst):
    _copy(src, dst)
    with open(dst + "/migrate-job.yaml") as fh:
        job = next(d for d in yaml.safe_load_all(fh) if d and d.get("kind") == "Job")
    sa_name = job["spec"]["template"]["spec"]["serviceAccountName"]

    def fn(docs):
        n = 0
        for d in docs:
            if d.get("kind") == "ServiceAccount" and name(d) == sa_name:
                a = (d.get("metadata") or {}).get("annotations") or {}
                for key in [k for k in a if k.startswith("argocd.argoproj.io/")]:
                    del a[key]
                    n += 1
                if not a:
                    d["metadata"].pop("annotations", None)
        return n

    if _rewrite(dst + "/serviceaccount.yaml", fn) == 0:
        raise SystemExit("mutation did not apply: no Argo CD annotation found on ServiceAccount/" + sa_name)
    print("mutated: removed the Argo CD annotations from ServiceAccount/" + sa_name)


def mutate_dns(src, dst):
    _copy(src, dst)

    def fn(docs):
        n = 0
        for d in docs:
            if d.get("kind") != "NetworkPolicy":
                continue
            for rule in (d.get("spec") or {}).get("egress") or []:
                for peer in rule.get("to") or []:
                    if peer.get("ipBlock", {}).get("cidr") == "169.254.20.10/32":
                        peer["ipBlock"]["cidr"] = "169.254.0.0/16"
                        n += 1
        return n

    if _rewrite(dst + "/networkpolicy.yaml", fn) == 0:
        raise SystemExit("mutation did not apply: the NodeLocal DNS peer was not found")
    print("mutated: widened the port 53 NodeLocal peer to 169.254.0.0/16")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "check" and len(sys.argv) == 3:
        sys.exit(check(sys.argv[2]))
    if cmd == "mutate-hook" and len(sys.argv) == 4:
        mutate_hook(sys.argv[2], sys.argv[3])
        sys.exit(0)
    if cmd == "mutate-dns" and len(sys.argv) == 4:
        mutate_dns(sys.argv[2], sys.argv[3])
        sys.exit(0)
    print(__doc__)
    sys.exit(2)
