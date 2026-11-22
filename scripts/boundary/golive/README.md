# Go-live boundary scripts

Written for OpenSpec change `go-live-boundary` (tasks 1.1 and 1.2). They run once, at the boundary,
after the implementation phase is complete and committed. Contract:
`.kbd-orchestrator/phases/sellbird-go-live/adopted-contract.json` (`boundaryPacket.commands`).
Every script ends with `RESULT <scenario-ids> <status>`; exit 0 = PASS, 1 = FAIL, 3 = BLOCKED,
4 = NOT_EXERCISED. A negative-control script exits 0 (PASS) when its control was REJECTED as the
contract requires. Each appends JSON lines to `results.jsonl` in the evidence folder and keeps its raw
output there. Only counts, digests, statuses, exit codes and timestamps are printed or recorded.
Python is always `.venv/bin/python`; `python3` is never assumed.

## Order (the packet order)

| # | Command | Needs |
|---|---|---|
| 1 | `preflight.sh` | tools, `.venv` extras, `requirements.lock`, a real Trivy checksum in `images.yml`, clean committed tree |
| 2 | `docker build -t sellbird:golive .` | (not a script here) |
| 3 | `standin-up.sh` | image `sellbird:golive`, free ports from preflight |
| 4-5 | `suite.sh`, `neg-reg.sh` | the stand-in (Postgres DSNs), node |
| 6-7 | `fresh-install-order.sh infra/k8s/base`, `neg-fresh.sh` | a kustomize renderer |
| 8-9 | `locked-install.sh`, `neg-lock.sh` | docker, uv at `scripts/ci/uv-version`, network |
| 10-11 | `pipe-graph-check.sh .github/workflows`, `neg-pipe-graph.sh` | `.venv` PyYAML |
| 12-14 | `pipe-control.sh failing-test` / `none` / `vulnerable-image` | gh, pushed branch, **operator approval** |
| 15-17 | `neg-trivy-checksum.sh`, `neg-image-swap.sh`, `neg-lock-stale.sh` | docker (swap), uv + network (stale) |
| 18-19 | `live-rollout.sh`, `live-rollout.sh --expect-previous-digest` | gh, kubectl, merged + deployed |
| 20-21 | `live-restart.sh`, `live-restart.sh --marker-dir /tmp --expect-fail` | **one approved pod delete** |
| 22-23 | `live-heartbeat.sh`, `neg-heartbeat-stale.sh` | trained hosted Sellbird, Claude login |
| 24-25 | `live-nosend.sh`, `neg-approved-send.sh` | live read; stand-in for the control |
| 26 | `redaction-grep.sh` | the whole evidence folder |
| after | `summarize.sh` (extra) | writes `boundary-results.json` and a README skeleton |

Every script takes the scenario id as its last argument (as in the packet); it only labels the run.
The control for SCN-LIVE-002 reuses the primary run's single pod delete (see below).

## Environment

| Variable | Meaning |
|---|---|
| `EVIDENCE_DIR` | Evidence folder to append to. Default: the folder `preflight.sh` created (a new dated folder under `.kbd-orchestrator/phases/sellbird-go-live/evidence/boundary-run/`, found through `evidence/.boundary-run-current`). Existing folders are only appended to. For a repair rerun, export the same folder. |
| `GOLIVE_KUBE_CONTEXT` | kube context for the live scripts. No default: unset means they record BLOCKED. |
| `GOLIVE_REQUIRE_LIVE=1` | preflight fails when the context is unset. |
| `GOLIVE_ALLOW_DISPATCH=1` | lets `pipe-control.sh` dispatch the control runs (approval 5). |
| `GOLIVE_REF` | branch to dispatch on; default the current branch. `main` only if set explicitly. |
| `GOLIVE_ALLOW_POD_DELETE=1` | lets `live-restart.sh` delete the one pod (approval 5). |
| `GOLIVE_BASE_REF` | pre-phase commit `neg-reg.sh` reverts to; default `git merge-base HEAD origin/main`. Set it when HEAD is on main after the merge. |
| `GOLIVE_ALLOW_DIRTY=1` | run with uncommitted changes (dry runs only; the worktrees and CI see commits only). |
| `GOLIVE_PREVIOUS_DIGEST` | override for the previous digest in the rollout control. |
| `GOLIVE_RUN_FIND_SECONDS`, `GOLIVE_RUN_TIMEOUT_SECONDS`, `GOLIVE_RESTART_TIMEOUT_SECONDS`, `GOLIVE_HEARTBEAT_TIMEOUT_SECONDS`, `GOLIVE_NOSEND_TIMEOUT_SECONDS` | wait limits. |
| `SELLBIRD_LOCAL_PG_PORT`, `_GATE_PORT`, `_DIRECT_PORT` | start ports for the free-port search; the chosen ones are in `ports.env`. |

## What each operator approval gates

1. Push of the go-live branch and the pull request: nothing here pushes. `pipe-control.sh` refuses unless
   the branch is on the remote at the local HEAD.
2. Merge of the Sellbird pull request: `live-rollout.sh` needs a successful `images.yml` run on `main`.
3. Platform overlay and provider secrets: `live-rollout.sh` and `live-heartbeat.sh` find nothing to read
   until they exist (BLOCKED).
4. Training and Claude login: `live-restart.sh` and `live-heartbeat.sh` record BLOCKED while
   `/data/sellbird.local.yaml` is absent or the newest cycle is a `brain_paused` one.
5. One pod delete and three control runs: `GOLIVE_ALLOW_POD_DELETE=1` and `GOLIVE_ALLOW_DISPATCH=1`.
   `live-restart.sh` is the only script that changes the cluster (a marker file in `/data` and `/tmp`, one
   pod delete, then removal of the `/data` marker). Everything else in `live-*` is read-only.
6. Sending stays paused: `live-nosend.sh` reports the flag and requires sent/approved/sending/failed
   counts unchanged and approval mode on; `neg-approved-send.sh` runs on the local stand-in only.

Cleanup after the run (from the contract): `docker compose -f infra/local/compose.yaml down -v`,
`docker image rm sellbird:golive sellbird:boundary`. Scratch copies, control images and worktrees are
removed by each script's exit trap.
