## Why

The hosted pod's home folder is temporary storage, so training and settings vanish on every restart; a fresh install deadlocks on the migration Job's service account; DNS breaks under NodeLocal DNSCache.

## What Changes

- Replace the /data emptyDir with a 1Gi ReadWriteOnce PersistentVolumeClaim `sellbird-data` and set the Deployment strategy to Recreate.
- Give the migration Job its own ServiceAccount `sellbird-migrate`, itself a PreSync hook at an earlier wave than the Job.
- Add a DNS egress rule for UDP and TCP 53 to 169.254.20.10/32 beside the kube-dns rule; keep the metadata server blocked.

## Impact

- Affected capability: `hosted-home`
- Files: infra/k8s/base/**; infra/k8s/base/networkpolicy.yaml
- Phase: `sellbird-go-live`; verified once at the phase boundary, not per task.
