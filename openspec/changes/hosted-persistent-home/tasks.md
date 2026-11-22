## 1. Keep the hosted home folder and fix fresh installs

- [x] 1.1 Replace the /data emptyDir with a 1Gi ReadWriteOnce PersistentVolumeClaim `sellbird-data` and set the Deployment strategy to Recreate (role: platform-engineer)
- [x] 1.2 Give the migration Job its own ServiceAccount `sellbird-migrate`, itself a PreSync hook at an earlier wave than the Job (role: platform-engineer)
- [x] 1.3 Add a DNS egress rule for UDP and TCP 53 to 169.254.20.10/32 beside the kube-dns rule; keep the metadata server blocked (role: platform-engineer)
