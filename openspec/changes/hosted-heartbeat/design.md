## Context

The hosted pod runs two containers: `dashboard` (the internet-facing gateway-mode app) and `heartbeat` (`sellbird run`). Both share `/data` and the Postgres database and both get `SELLBIRD_DASHBOARD_MODE=gateway`. Secrets arrive as environment variables only; there is no `.env` file.

## Decisions

### D1. Setup check (task 1.1)

`sellbird/main.py` `_needs_setup` ignores the missing `.env` when `SELLBIRD_DASHBOARD_MODE` is `gateway` and judges only the trained configuration (`persona.company`). Local mode is unchanged.

### D2. Every cycle leaves a row (task 1.1)

The loop wrote its `agent="main"` action row only at the end of a cycle that ran. Four paths slept without writing one, so a quiet, paused or over-budget loop would have looked dead to the hosted dashboard. Now each writes one row per heartbeat interval, with a distinct `action_type`:

| Path | action_type | Rows while waiting |
|---|---|---|
| Quiet hours (no sending allowed) | `quiet_hours` | one on entry, then one per heartbeat interval inside the 5-minute polling loop |
| Quiet hours, nothing cold due | `quiet_hours` | one, then sleeps one interval |
| Brain not usable (`brain.preflight`) | `brain_paused` | one, then sleeps one interval |
| Over budget | `over_budget` | the 1 h wait is cut into interval-sized sleeps with one row each (four at the default 15 minutes) |
| A cycle that ran (including `idle`) | the decided action | one, as before |

A cycle that raises an exception writes no row (the loop backs off and retries); a loop failing for more than three intervals correctly shows as not running.

### Waiting for training (task 1.1)

On a fresh install the heartbeat container starts before anyone has run `sellbird train`. Exiting would crash-loop the container and make the whole pod NotReady, taking the dashboard with it. So in gateway mode only, when setup is needed `main()` does not exit: it logs "Sellbird is waiting to be trained. Run `python -m sellbird train <website>` inside this pod; the heartbeat starts by itself once training is done.", re-checks `_needs_setup()` every `SETUP_RECHECK_SECONDS` (60), repeats the line at most every 15 minutes, logs "Training detected" once, and then continues into the normal loop with no restart. The wait is a signal-aware sleep on the same stop event SIGTERM/SIGINT set (shared `_install_signal_handlers`), so it ends promptly inside the 120 s grace period. It runs before the loop lock is taken and writes no action-log rows, so the dashboard keeps saying the heartbeat is not running and `sellbird train` (which never takes the lock) is not blocked. Local mode is unchanged: no TTY exits 1 with the existing message, a TTY runs the setup wizard.

### D3. Hosted status (task 1.2)

In gateway mode `/api/sellbird/status` reads the newest `actions` row with `agent = 'main'` (`StateManager.last_heartbeat_at`, which normalizes SQLite naive-UTC text and Postgres datetimes to aware UTC). `running` is true only when that row is younger than 3 x `usage.heartbeat_interval_minutes`; `stale_after_seconds` carries that threshold. `POST /api/sellbird/start` and `/stop` return a refusal and never spawn or signal. Local mode adds only `"mode": "local"`.

### D4. Does any dashboard action use a provider directly? (task 1.4)

Finding, from reading `sellbird/dashboard.py`, `sellbird/inbox_routes.py` and what they import: yes, three things, none of them sends cold email or reads replies.

1. **Claude brain in the dashboard process.** `POST /api/offer/suggest` and `POST /api/offer/preview` call `_offer_brain()` (`dashboard.py`), which builds `Brain` and runs a real model call. The dashboard therefore needs `CLAUDE_CODE_OAUTH_TOKEN`. This changes design call A5, which assumed the token was heartbeat-only.
2. **Discovery providers in the dashboard process.** `POST /api/discover/run` (`start_discovery`) runs `pipeline.run_prospecting` in a background task, which calls `collectors/discover.py` (`load_env()` there) and spends money on DataForSEO, Serper, TinyFish or Scavio keys. `GET /api/discover/providers` reports which are configured from the same environment. Site reading (`/api/discover/profile`, `run_profile_stage`) needs no key.
3. **Mailbox settings, read for status and gating only.** `get_mail_provider(config, env)` followed by `is_configured()` (no network) runs in `dashboard._sellbird_can_send` and `inbox_routes.list_inboxes`. `_sellbird_can_send` decides whether the dashboard offers "mark as sent by hand"; its docstring says hand sends are offered only when Sellbird cannot send itself, to avoid emailing someone twice. If the dashboard lacks the mailbox variables it answers "cannot send" while the heartbeat is sending, which wrongly offers hand sends. So the mailbox variables go to both.

Not found: no dashboard endpoint sends mail, reads a mailbox for replies, or calls a verifier. Outbox approve (`/api/outbox/{id}/approve`) only changes a status; the heartbeat's Sender sends. `POST /api/settings/test-instantly` and `/api/inboxes/connect/smtp` make a network call but with a key or password the operator types into the request, not one from the environment. `/api/trulyinbox/connect` and `/api/settings` write a `.env` file, which does not fit a pod and is not a hosted path. Gmail and Microsoft sign-in need a browser on the host and are not available in a pod; use SMTP and IMAP.

## Per-container secret split

Variable names are exactly what `sellbird/config.py` (`load_env`), `sellbird/auth/config.py`, `sellbird/state.py` and the other modules named read.

| Family | Environment variables | dashboard | heartbeat | Evidence |
|---|---|---|---|---|
| Hosted-mode switch | `SELLBIRD_DASHBOARD_MODE=gateway` | yes | yes | `auth/config.py` `dashboard_mode`; `main.py` `_needs_setup` |
| Home folder | `SELLBIRD_HOME` | yes | yes | `paths.py` `HOME_ENV` (not a secret) |
| Database | `SELLBIRD_DATABASE_URL` | yes | yes | `state.py` `DATABASE_URL_ENV`; both open `StateManager` |
| Gateway settings | `SELLBIRD_PUBLIC_HOST`, `SELLBIRD_GATE_ISSUER`, `SELLBIRD_GATE_AUDIENCE`, `SELLBIRD_GATE_JWKS_URL`, `SELLBIRD_GATE_ALLOWED_SUBS` | yes | no | `auth/config.py` `load_gateway_config`; only `dashboard._start_gateway_dashboard` builds the gateway guard. The heartbeat does not read them |
| Claude login | `CLAUDE_CODE_OAUTH_TOKEN` | **yes** | yes | dashboard: `_offer_brain` (offer suggest and preview); heartbeat: `Brain` in `main.heartbeat`. Also optional `CLAUDE_CONFIG_DIR` (not a secret) |
| Mailbox, SMTP/IMAP | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `IMAP_HOST`, `IMAP_PORT`, `IMAP_USERNAME`, `IMAP_PASSWORD` | yes (status and hand-send gate only) | yes (sends and reads replies) | `config.load_env`; `smtp_mail.is_configured`; dashboard `_sellbird_can_send`, `inbox_routes.list_inboxes`; heartbeat `Sender`, `Handler` |
| Mailbox, Gmail | `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET` | yes | yes | same; also needs a token file made by a browser sign-in, so not workable in a pod |
| Mailbox, Microsoft | `M365_CLIENT_ID`, `M365_TENANT_ID` | yes | yes | same; same browser sign-in limit |
| Instantly (legacy) | `INSTANTLY_API_KEY` | yes (gate) | yes | `_sellbird_can_send` reads `env.instantly_api_key`; Sender deploys campaigns |
| Verifiers | `REOON_API_KEY`, `ZEROBOUNCE_API_KEY`, `HUNTER_API_KEY` (and optional `HUNTER_MONTHLY_SEARCHES`) | no (setup checklist display only) | yes | no dashboard endpoint verifies an address; Scout resolves and verifies in the heartbeat |
| Discovery | `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD`, `DATAFORSEO_SANDBOX`, `SERPER_API_KEY`, `TINYFISH_API_KEY`, `SCAVIO_API_KEY` | **yes** | yes | dashboard: `start_discovery` and `get_discovery_providers`; heartbeat: Scout prospecting |
| Cold-email check | `PRECLEARED_API_KEY` | no | yes | used when staging and sending mail; not read by any dashboard route |
| Warmup | `TRULYINBOX_API_KEY`, `TRULYINBOX_WORKSPACE_ID` | no (setup checklist display only) | yes (via `sellbird warmup` in `kubectl exec`) | `integrations/trulyinbox.py` `key_from_env` |
| Training crawl (optional) | `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` | no | yes | `trainer.py`, run by `kubectl exec` in the heartbeat container |
| LinkedIn (optional) | `LINKEDIN_EMAIL`, `LINKEDIN_PASSWORD` | no | yes | Scout LinkedIn strategy |

Summary for the Deployment: both containers get the database URL, the mode switch, the home folder, the Claude token, the mailbox variables, the Instantly key and the discovery keys; only `dashboard` gets the gateway settings; only `heartbeat` gets the verifier, Precleared, TrulyInbox, Cloudflare and LinkedIn keys. All provider entries are `optional: true`.

### If a key is given only to the heartbeat

- Claude token missing from the dashboard: "Suggest offers" and "Preview email" on the Your company tab fail with "couldn't come up with offers" or "the preview failed".
- Discovery keys missing from the dashboard: the Discover tab shows each keyed source as "needs setup" and `Run` refuses; the free OpenStreetMap source still runs. Discovery run from the heartbeat side only through the CLI.
- Mailbox variables missing from the dashboard: the Inboxes tab shows the main mailbox as not connected, and the dashboard offers "mark as sent by hand" while the heartbeat is already sending, which can email a person twice. Nothing is sent or read incorrectly.
- Verifier, Precleared, TrulyInbox, Cloudflare and LinkedIn keys missing from the dashboard: only the Today setup checklist shows those items as not done; no action stops working.

## Follow-ups noted, not done here

- Making `_sellbird_can_send` return true in gateway mode would let the mailbox variables stay heartbeat-only; left out because it changes hand-send behavior.
- Postgres coverage of `last_heartbeat_at` runs through the existing storage contract suite; no Postgres-specific test was added here.
