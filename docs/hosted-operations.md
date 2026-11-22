# Running Sellbird hosted

This is for the person who looks after a hosted Sellbird: the one that runs in a
Kubernetes cluster behind flint-gate and Kratos, with its state in Postgres. If you
run Sellbird on your own machine, you don't need this page. How the hosted setup is
put together is in [Hosting Sellbird](hosting.md). What the platform has to provide
is in [the platform interface](platform-interface.md).

Every command below assumes the namespace is `sellbird`. Use `kubectl` however your
platform lets you reach the cluster.

## What is running

One pod, two containers, one shared folder:

- **`sellbird`** is the dashboard. It's the only container with a port, and the one
  `kubectl logs` and `kubectl exec` pick when you don't name a container.
- **`heartbeat`** is the outreach loop (`sellbird run`). It finds prospects, writes
  emails, sends the ones you've approved and reads replies.
- **`/data`** is a small disk (1Gi) both containers share. Training, your offer and
  your dashboard settings live there. Prospects, emails and conversations live in
  Postgres.

## First time: train Sellbird

A new hosted Sellbird doesn't know what it's selling yet. Teach it from your
website:

```bash
kubectl -n sellbird exec deploy/sellbird -c sellbird -- python -m sellbird train https://www.example.com
```

Use your own address in place of `https://www.example.com`. Training reads your site
and writes Sellbird's configuration and sales notes to `/data`. It takes a few
minutes.

Until that is done, the heartbeat waits. It doesn't crash and it doesn't restart. It
checks again every minute, and about every fifteen minutes it says in its log that
it is waiting for training. Once training has finished it notices on its own,
usually within a minute, and starts working. You don't restart anything.

You can watch it:

```bash
kubectl -n sellbird logs deploy/sellbird -c heartbeat --tail=20
```

## Give Sellbird its keys

Keys reach the pod as Secrets. Sellbird can't start without two of them, and the
rest depend on what you use:

| Secret | Holds | Needed |
|---|---|---|
| `sellbird-db-app` | `SELLBIRD_DATABASE_URL` | always |
| `sellbird-claude` | `CLAUDE_CODE_OAUTH_TOKEN` | always |
| `sellbird-mail` | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `IMAP_HOST`, `IMAP_PORT`, `IMAP_USERNAME`, `IMAP_PASSWORD` (and the Instantly key, if you use it) | to send and read replies |
| `sellbird-discovery` | `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD`, `SERPER_API_KEY`, `TINYFISH_API_KEY`, `SCAVIO_API_KEY` | for paid prospecting sources |
| `sellbird-verifiers` | `REOON_API_KEY`, `ZEROBOUNCE_API_KEY`, `HUNTER_API_KEY` | to verify email addresses |
| `sellbird-extras` | `PRECLEARED_API_KEY`, `TRULYINBOX_API_KEY`, `TRULYINBOX_WORKSPACE_ID`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `LINKEDIN_EMAIL`, `LINKEDIN_PASSWORD` | for the cold-email check, warmup status and so on |

Each key goes in under the same name as the variable. Create only the optional
Secrets you need, and only the keys in them you use. A missing Secret or key just
means that feature shows as not configured.

Your platform may have its own way to create Secrets. If it does, use that. The
plain `kubectl` shape is:

```bash
kubectl -n sellbird create secret generic sellbird-mail \
  --from-literal=SMTP_HOST=<your-smtp-host> \
  --from-literal=SMTP_PORT=587 \
  --from-literal=SMTP_USERNAME=<your-smtp-username> \
  --from-literal=SMTP_PASSWORD=<your-smtp-password> \
  --from-literal=IMAP_HOST=<your-imap-host> \
  --from-literal=IMAP_PORT=993 \
  --from-literal=IMAP_USERNAME=<your-imap-username> \
  --from-literal=IMAP_PASSWORD=<your-imap-password>

kubectl -n sellbird create secret generic sellbird-verifiers \
  --from-literal=REOON_API_KEY=<your-reoon-key>
```

Typing a real password on a command line leaves it in your shell history. Prefer
your platform's secret path, or `--from-file` with a file you delete afterwards.

Secret values are read when a container starts, so restart the pod after you add or
change one:

```bash
kubectl -n sellbird rollout restart deploy/sellbird
```

The restart briefly takes Sellbird offline, see below.

**Mail ports.** The pod can only reach the internet on TCP 80, 443, 465, 587 and
993. Use SMTP on 587 or 465 and IMAP on 993. Port 25 and plain IMAP on 143 are
blocked.

## What isn't supported hosted

- **Gmail and Microsoft 365 sign-in.** `sellbird gmail auth` and `sellbird microsoft
  auth` open a browser on the machine they run on, and a pod has none. Use a mailbox
  that offers SMTP and IMAP instead. Whether a token file made elsewhere
  could be copied into `/data` has not been verified, and isn't something to rely
  on.
- **Starting and stopping Sellbird from the dashboard.** The platform runs the
  heartbeat; the buttons are hidden and the requests are refused.
- **Codex.** Hosted Sellbird uses Claude only.

## Nothing sends without you

Like a local Sellbird, a hosted one holds every email in the **Outbox** until you
approve it. Open the dashboard, go to **Outbox**, and approve or reject each
draft. Read each draft before you approve it. [Approval and
sending](approval-and-sending.md) explains the Outbox and what the checks catch.

You can switch to autopilot in **Settings**, then **Sending**. It sends without
asking, still inside your daily limit and quiet hours. Approve a few batches by
hand first.

From a terminal you can use the same Outbox commands, in either container:

```bash
kubectl -n sellbird exec deploy/sellbird -c sellbird -- python -m sellbird outbox
```

## Pause and resume sending

There's a kill switch. Pausing stops everything leaving the Outbox. Sellbird keeps
finding prospects and writing drafts.

```bash
kubectl -n sellbird exec deploy/sellbird -c sellbird -- python -m sellbird sending pause
kubectl -n sellbird exec deploy/sellbird -c sellbird -- python -m sellbird sending resume
kubectl -n sellbird exec deploy/sellbird -c sellbird -- python -m sellbird sending status
```

The setting is stored in Postgres, so it holds across restarts and both containers
see it. Resuming also resets the bounce counter.

## Is it running?

The dashboard's header and Agent card say **Sellbird is running** or **Sellbird is
not running**, with when it last finished a cycle.

The heartbeat is a separate container, so the dashboard can't look at its process.
It reads the action log in Postgres instead. The heartbeat writes a row each cycle,
and also one per interval while it waits (quiet hours, over budget, or the brain
unavailable). **Running** means the newest row is less than three heartbeat
intervals old, 45 minutes at the default 15.

**Not running** means no row for that long. Look in this order:

1. **Not trained yet.** A waiting heartbeat writes no rows. Check the log for the
   "waiting to be trained" line and train, as above.
2. **The container is down.** `kubectl -n sellbird get pods` shows restarts, and
   `kubectl -n sellbird logs deploy/sellbird -c heartbeat --previous` shows why it
   stopped.
3. **A fresh start.** After a deploy or restart the first row can take a moment.

"No cycle recorded yet" means the heartbeat has never written a row.

## What survives a restart

Everything under `/data` survives restarts and deploys: what training learned, your
offer, your dashboard settings. Postgres holds the rest. Nothing here is lost when
the pod is replaced, and the platform never prunes or deletes the `sellbird-data`
disk.

Each deploy replaces the pod rather than updating it in place, so the old pod stops
before the new one starts. Expect Sellbird, and the dashboard, to be gone for a
short while on every deploy. A send in progress is given up to two minutes to
finish.

## Start over

To drop what Sellbird learned and train it again, you delete the `sellbird-data`
disk. Argo CD never does that for you. It's destructive, so it's the platform
operator's call, made by hand and not verified here: stop the pod, delete the
PersistentVolumeClaim `sellbird-data`, and let the next sync create a fresh one.
The next start copies Sellbird's defaults in and the heartbeat waits for training
again.

That doesn't touch Postgres. Prospects, emails and conversations stay. Clearing
those is a database operation and isn't covered here.
