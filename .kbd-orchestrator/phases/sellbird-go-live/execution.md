# Execution — sellbird-go-live

Started 2026-11-22 on branch `kbd/sellbird-go-live`, cut from `origin/main` at `a661932`.

## Backend

`openspec`, driven through KBD task transitions. Six changes under `openspec/changes/`, 22 tasks.

## Dispatch contract

- Contract: `adopted-contract.json`, digest `f045388b…`, plan revision 1, readiness READY on 2026-11-22.
- Workers: Claude Code project subagents per role, as `plan.md` TASK MODEL ASSIGNMENTS routes them. The model each runs on is the one its role definition sets; no per-task override is passed.
- Rounds: 1 `hosted-persistent-home`, `hosted-small-fixes`, `pipeline-hardening`; 2 `hosted-heartbeat`; 3 `go-live-docs`, `go-live-boundary`.
- Each worker edits only its task's files, in this one checkout. Workers do not commit; the lead commits per round.
- VLBV: no test, build, lint, type check, import or container run during the rounds. Everything runs once at the boundary.
- Reviewer and security-reviewer roles stay dormant until round 3 is complete.

## Lessons the workers are given

- No real person's or business's name, address, phone number or domain anywhere; `example.com`-style data only.
- Evidence and logs carry counts, digests and timestamps only.
- A scenario script must discover its environment (ports, tools, logins) and fail in preflight with a clear message.

## Operator authorizations recorded

- 2026-11-22, in this session: "Start execution" in answer to "Start building the 22 go-live tasks now?". This covers writing the code. It does not cover pushing, opening a pull request, merging, cluster changes or control runs; those are asked at the boundary.
