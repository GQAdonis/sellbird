# Tasks

Model routes for these tasks: see **TASK MODEL ASSIGNMENTS** in `.kbd-orchestrator/phases/postgres-gke-deployment/plan.md`, rows for change `hosted-gateway-mode`.

## 4. Hosted gateway mode: trust a flint-gate JWT, keep local token mode unchanged

- [x] 4.1 Add gateway-mode configuration and the guarded non-loopback bind in dashboard startup (verify at the phase boundary per the plan's coverage table)
- [x] 4.2 Implement JWT verification against a pinned JWKS with iss/aud/kid/alg/exp and sub allowlist (verify at the phase boundary per the plan's coverage table)
- [x] 4.3 Apply gateway-mode request rules: Host/Origin, cookie and header distrust, agent token off (verify at the phase boundary per the plan's coverage table)
- [x] 4.4 Suppress token output in containers and keep local token mode byte-for-byte unchanged (verify at the phase boundary per the plan's coverage table)
- [x] 4.5 Write gateway-mode and local-mode auth tests asserting the resolved principal, forged-header, wrong-aud, expired and non-loopback negatives (verify at the phase boundary per the plan's coverage table)
