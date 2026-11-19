# Goals

- Decide and record, before any build work: (1) whether SQLite stays supported for local installs alongside Postgres; (2) where Postgres runs (in-cluster from the flint-forge PG18 image, or an existing flint-forge instance); (3) how the public dashboard is protected (Ory Kratos sign-in enforced by flint-gate, replacing the local token link only in hosted mode); (4) how the AI brain authenticates in a pod (Claude/Codex credentials, provider choice).
- Sellbird's state layer runs on Postgres 18 using the custom flint-forge image, with versioned reversible migrations, least-privilege roles, preserved signal/observation and sending-safety invariants, and a tested tool to move an existing data/sellbird.db.
- A hardened container image is built, scanned and pushed to GHCR by digest on every merge to main (github-argocd-continuous-deployment Phase 1).
- Kustomize production overlay and AppProject-scoped Argo CD Applications deploy Sellbird, Postgres, Ory Kratos and flint-gate to the GKE cluster (gke_knowme-corporate_us-south1_main), with a deploy job that pins image@digest via a GitHub App bot and a protected-main ruleset.
- https://sellbird.know-me.tools resolves, serves TLS, and requires a Kratos session enforced by flint-gate before the dashboard loads; local single-user mode keeps working unchanged.
- A harmless change merged to main reaches the cluster end to end through the real pipeline, verified (VLBV boundary), with an independent security review of Postgres, auth, gateway and Kubernetes changes and docs/CHANGELOG updated.
