# Derived method context

Method: VLBV (project-pin); phase: sellbird-go-live; revision: 315; status: RESOLVED_REFERENCES.

This is a recovery index, not execution permission. Resolve current canonical decisions and contract before dependent action.

```json
{
  "schemaVersion": 1,
  "kind": "kbd.derived-method-context",
  "generatedAt": "2026-11-22T01:22:15.074Z",
  "authority": "derived-read-only-index; canonical signed decisions, phase binding, contract and governing host policy remain authority",
  "projectId": "09d97122-c2c7-452a-a0a1-48a80e6cfef5",
  "runId": "postgres-gke-deployment-20261118T052720Z",
  "phaseId": "sellbird-go-live",
  "sourceRevision": 315,
  "phaseDirectory": ".kbd-orchestrator/phases/sellbird-go-live",
  "contract": {
    "path": ".kbd-orchestrator/phases/sellbird-go-live/adopted-contract.json",
    "observation": "observed",
    "sha256": "9859e381dbd19b60b2722007aab8acb894b7064b0f85ae383c2fcd0042a66d1f",
    "contractDigest": "f045388b6650c28fb70a4e69531cfc02628bb88c1c74a3eadfc2afc0f6e9006c",
    "binding": {
      "contractPath": ".kbd-orchestrator/phases/sellbird-go-live/adopted-contract.json",
      "contractDigest": "f045388b6650c28fb70a4e69531cfc02628bb88c1c74a3eadfc2afc0f6e9006c",
      "scenarioDigests": {
        "SCN-FRESH-001": "b7a51c81390e300cfce161442934a4e50dd0c50c6c6d323a152508540607bc36",
        "SCN-LIVE-001": "f50def651dad9fa40449f7efed94283fab66f66af62377bdf12f6d7dc80890c9",
        "SCN-LIVE-002": "1c438325b5ed834933bc6d886361816241e09f717c4c2dd148bb2820ac8714c1",
        "SCN-LIVE-003": "b46fe3e706c9de546d604c36a4c8fd4e69661eb5e6fcff27d19a03f532042787",
        "SCN-LOCK-001": "fb4d8294b9d9e7d59af41f53780a96b0c1455628279c222d1570f9a17a879285",
        "SCN-PIPE-001": "5214d18030f267b3f5e1cce1ea29a10eff2300378ff7ff3af1f1caf9e4355f97",
        "SCN-PIPE-002": "e39ba3d452306816e2c9e4bb97393496e894b04ff0d559de3f5904c22b63680c",
        "SCN-REG-001": "1622b4a0aa8c56ad1c63a90dae52119ff8151752642fd62edb59be6d4055ec05",
        "SCN-SHIP-002": "b788d879071c7f23ac307eab0e569577bbcf454e8a73c0aefe259685ebf51f50"
      },
      "planRevision": 1,
      "adoptionDecisionId": "contract-adoption-sellbird-go-live-f045388b",
      "bindingRevision": 2,
      "authority": {
        "manifestRaw": "{\"action\":\"amend-contract\",\"approver\":\"travis@tribehealthsolutions.com\",\"contractPath\":\".kbd-orchestrator/phases/sellbird-go-live/adopted-contract.json\",\"kind\":\"kbd.scope-authority\",\"namespace\":\"prometheus-kbd-scope-amendment\",\"newContractDigest\":\"f045388b6650c28fb70a4e69531cfc02628bb88c1c74a3eadfc2afc0f6e9006c\",\"nonce\":\"e243554d201c2d4b100614e916aae8b8\",\"phaseId\":\"sellbird-go-live\",\"previousContractDigest\":\"c47f7a031561f0e4722cf538eb3b10cc6b450a37754bc33f13c2aa94d3addd85\",\"projectId\":\"09d97122-c2c7-452a-a0a1-48a80e6cfef5\",\"reason\":\"Correct method.specDeltaDigest to the value the KBD digest tool computes; the adopted value was computed with a different formula. No scenario, scope or budget changes.\",\"runId\":\"postgres-gke-deployment-20261118T052720Z\",\"scenarioChanges\":{\"added\":[],\"modified\":[],\"removed\":[]},\"schemaVersion\":\"1\",\"timestamp\":\"2026-11-22T01:19:03Z\"}",
        "manifestSha256": "6f9f2b691d94f906656eb448c40538925e8c6879860055b11bb854bbce296346",
        "signature": "-----BEGIN SSH SIGNATURE-----\nU1NIU0lHAAAAAQAAADMAAAALc3NoLWVkMjU1MTkAAAAgsgqOvzJMpDfEY0CKRyfxixLl97\nUxT+bg/r6Jl4BBHFcAAAAecHJvbWV0aGV1cy1rYmQtc2NvcGUtYW1lbmRtZW50AAAAAAAA\nAAZzaGE1MTIAAABTAAAAC3NzaC1lZDI1NTE5AAAAQP1/fqMfSCkpiSUbxbqecR7h2FvKEw\nfMlGoFypPvj8spesypQGRsQ6eHQ1hEA+Ci+HZ+UjdRPZpUKM05P5b/HAA=\n-----END SSH SIGNATURE-----\n",
        "approver": "travis@tribehealthsolutions.com",
        "namespace": "prometheus-kbd-scope-amendment",
        "allowedSignersSha256": "4c32adefb70e281e6c78f3ecb562088ef82209c54a9a01b1ed630ba3ed78a573"
      }
    },
    "identity": {
      "projectId": "09d97122-c2c7-452a-a0a1-48a80e6cfef5",
      "runId": "postgres-gke-deployment-20261118T052720Z",
      "phaseId": "sellbird-go-live",
      "planRevision": 1,
      "contractDigest": "f045388b6650c28fb70a4e69531cfc02628bb88c1c74a3eadfc2afc0f6e9006c"
    }
  },
  "selectedMethod": "VLBV",
  "methodSource": "project-pin",
  "deviation": null,
  "methodDecision": null,
  "retiredMethods": [],
  "references": [],
  "includedValue": [
    "Hosted configuration persists across restarts",
    "Fresh install does not deadlock on the migration Job",
    "DNS egress works with NodeLocal DNSCache",
    "Heartbeat runs in the cluster without operator action",
    "Hosted dashboard reports heartbeat status truthfully",
    "No email sent in hosted mode without approval",
    "Deploys gated on passing tests",
    "Published image is the scanned image and a failing scan stops publication",
    "Hash-locked dependency install",
    "JWKS https rule, exists() contract and local gate port",
    "Local single-user mode unchanged",
    "A merge reaches the cluster with both containers ready"
  ],
  "exclusions": [
    "platform-repository changes (requested, not made here): SEC-02 cookie stripping, deploy App push scope, overlay pin",
    "login redirect for signed-out browsers (flint-gate)",
    "choosing or configuring the mail provider, verifier and product (operator)",
    "sending any email",
    "SEC-06 and SEC-07",
    "Tailscale",
    "a real empty-namespace Argo CD sync"
  ],
  "stage": "plan",
  "stageAuthority": {
    "operations": [
      "discover/define/plan within governing policy"
    ],
    "implementationComplete": false,
    "verificationAuthority": "separately authorized whole-value-phase boundary required; this index grants none",
    "executableTestAuthoring": "governed by host policy; where that policy is production-first, defer until the complete agreed production work"
  },
  "governingInstructions": [
    {
      "path": "AGENTS.md",
      "observation": "observed",
      "sha256": "83e154477039c64be95440ae4038734f851eeba18858bef16ae831674b55d9aa"
    },
    {
      "path": "CLAUDE.md",
      "observation": "observed",
      "sha256": "5cb4d00f5ba5b7a4ee030ca20445ab2417d701e6f9e73ec5fe2622a235c9d22b"
    },
    {
      "path": ".kbd-orchestrator/constraints.md",
      "observation": "observed",
      "sha256": "904cb600a099162ae6b98d29246ac80eb4d4401162f542ce0b8bc8d3cc6c7b9c"
    }
  ],
  "effectiveRules": {
    "harness": null,
    "profile": "not-found",
    "files": [
      "AGENTS.md",
      "CLAUDE.md",
      ".kbd-orchestrator/constraints.md"
    ],
    "shadowing": null
  },
  "policyConflicts": [],
  "candidateAndEvidence": {
    "freshness": "Per-scenario invalidation keys (source globs, fixture digests, image digest, contract digest); a change invalidates only the scenarios whose keys it touches; prior evidence and history are preserved; no blanket re-review.",
    "paths": [
      "evidence/boundary-run/boundary-results.json",
      "evidence/boundary-run/README.md"
    ]
  },
  "budgets": {
    "adopted": {
      "timeMinutes": 720,
      "toolCalls": 2000,
      "repairAttempts": 3,
      "noProgressLimit": 3,
      "tokenBudget": "UNKNOWN",
      "tokenFallback": "tool-call ceiling",
      "exhaustion": "checkpoint and BLOCKED; never a silent PASS; documentation and state may be saved without running product tests"
    },
    "consumption": "UNKNOWN; recover original canonical/evidence receipts before execution"
  },
  "unresolved": {
    "boundaryObligations": {
      "phase:sellbird-go-live": {
        "key": "phase:sellbird-go-live",
        "receiptId": "a519f977d7af35a238228209810319eaf56a57179b9183388addfb58037bc1c8",
        "boundary": "phase",
        "subject": "sellbird-go-live",
        "sourceRevision": 276,
        "exactSignal": "Starting phase 2 out of 2: Sellbird go-live at sellbird.know-me.tools"
      }
    },
    "blockers": [],
    "instruction": "Unknown side effects require reconciliation before retry, not a fresh attempt assumption."
  },
  "preserve": [
    "latest non-superseded method decision and retiredMethods; old commands/memory are context only",
    "original contract snapshots, evidence and source/build/configuration/fixture/assertion identity",
    "all budget consumption/high-water marks, including UNKNOWN prior usage; never reset on recovery",
    "unresolved effects and cleanup/receipt obligations; reconcile uncertain effects before retry"
  ],
  "hostCapabilities": {
    "platform": "darwin",
    "nodeVersion": "v24.11.1",
    "observedInterfaces": [
      "canonical status",
      "typed phase disposition",
      "project-owned file identity"
    ],
    "executionInterception": "not provided by this helper",
    "commandInventoryIsPermission": false
  },
  "control": {
    "mode": "instruction-only",
    "observed": [
      "canonical references and file identities"
    ],
    "enforced": [
      "only named existing signed runtime mutations; no generic shell/tool interception claimed"
    ],
    "unsupported": [
      "universal model obedience or arbitrary tool interception"
    ]
  },
  "status": "RESOLVED_REFERENCES",
  "blockers": []
}
```
