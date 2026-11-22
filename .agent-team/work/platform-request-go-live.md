# Request to the platform team: Sellbird go-live

From: the Sellbird repository (documentation-specialist, for the `sellbird-go-live` phase).
To: the shared platform repository's owners.

Sellbird's base manifests (`infra/k8s/base`) and its platform interface
(`docs/platform-interface.md`) are now at contract version 3. This request lists what
the platform repository has to do. Version 3 needs its own operator agreement
decision in the platform phase's decision log; nothing here applies before that.
Nothing below needs a real hostname, owner or address, and none belongs in this
repository.

## (a) Take the new base

**What**

1. Add `PersistentVolumeClaim` to the Argo CD AppProject `sellbird`'s
   `namespaceResourceWhitelist`. The list becomes Deployment, Service,
   ServiceAccount, ConfigMap, NetworkPolicy, Job, PersistentVolumeClaim. Secrets stay
   out of it.
2. Create the optional Secrets Sellbird will use, in namespace `sellbird`, by the
   platform's usual secret path: `sellbird-mail`, `sellbird-discovery`,
   `sellbird-verifiers`, `sellbird-extras`. One key per variable, key name equal to
   the variable name. The key lists are in the Secrets table of
   `docs/platform-interface.md`. The required ones are unchanged: `sellbird-db-app`,
   `sellbird-db-migrate`, `sellbird-claude`. Any optional Secret may be left out;
   the feature then shows as not configured.
3. Move the overlay's base `ref` to a Sellbird commit that carries the new base, by
   reviewed pull request. Check every patch in the overlay: none may address the
   pod's containers by list index or replace the container list. The pod now has two
   containers, `sellbird` (dashboard, first) and `heartbeat`. The one `images` entry
   for the logical name `sellbird` still pins both.
4. Expect brief downtime on every deploy. The Deployment now uses `Recreate`
   (ReadWriteOnce volume, one writer), so the old pod stops, up to 120 seconds, then
   the new one starts. flint-gate has no Sellbird endpoint for that time. Do not
   alert on it.
5. Argo CD must not prune or delete the new claim `sellbird-data`; the manifest
   already carries `Prune=false,Delete=false`. Do not override that in the overlay.

**Why**

The claim keeps Sellbird's training and settings across restarts. Without the
whitelist entry the whole sync fails. The second container runs the outreach loop
that previously had no place to run.

**How to verify**

- `kubectl -n argocd get appproject sellbird -o jsonpath='{.spec.namespaceResourceWhitelist}'`
  lists PersistentVolumeClaim.
- After the sync: the Application is Synced and Healthy;
  `kubectl -n sellbird get pvc sellbird-data` shows Bound; the pod shows 2/2 ready;
  `kubectl -n sellbird get deploy sellbird -o jsonpath='{.spec.strategy.type}'`
  prints `Recreate`.
- `kubectl -n sellbird get pod -l app.kubernetes.io/component=app -o jsonpath='{.items[0].spec.containers[*].name}'`
  prints `sellbird heartbeat`.
- Rendering the overlay shows the digest-pinned image on both containers.

## (b) SEC-02: strip the Cookie header upstream

**What**

On Sellbird's flint-gate site, remove the `Cookie` header from the request before
it is forwarded to Sellbird (or use host-scoped sessions instead of a parent-domain
cookie).

**Why**

The Kratos session cookie is set on the parent domain, so every application host
under it receives it, and flint-gate forwards it upstream. A co-hosted application
could replay a user's cookie through the gateway and get a token for audience
`sellbird`. Sellbird ignores cookies, but the safe place to stop it is before the
request leaves the gateway.

**How to verify**

Send a request through the gateway with a valid session and print the headers
Sellbird's upstream receives (a throwaway echo upstream in a test namespace, or
flint-gate's own request log with values masked): no `Cookie` header arrives, while
`Authorization: Bearer` does. Signed-in dashboard pages still load.

## (c) SEC-03: narrow the deploy App's push scope

**What**

1. Narrow what the deploy GitHub App may push in the platform repository to the
   Sellbird overlay path only (`apps/sellbird/overlays/production`), for example a
   path-restricted push ruleset, or a pull request with auto-merge for that path.
2. Remove the rule bypass the App has today, including force-push.
3. Open item for the platform repository's owners: the deploy job's checkout of the
   platform repository (in Sellbird's `images.yml`) still persists its token in the
   checked-out repository's git config. Sellbird's side can set
   `persist-credentials: false` only if the pin push is changed to pass the token
   explicitly; agree which side does it.

**Why**

The App currently has Contents write on the whole platform repository with always-on
bypass. A leaked App key, or a compromised build step, could then change anything
there, not only the image pin. The deploy is also now gated on passing tests, but
that does not limit what the App can write once it runs.

**How to verify**

- With the App's identity, a push that changes a file outside
  `apps/sellbird/overlays/production` is rejected; a force-push to `main` is
  rejected; a pin commit that changes only `newTag` and `digest` in that
  directory's `kustomization.yaml` succeeds.
- The ruleset lists no bypass actor for the App.

## (d) Optional: NodeLocal DNSCache

**What**

Say whether the cluster runs NodeLocal DNSCache (GKE add-on that listens on
`169.254.20.10`).

**Why**

Sellbird's NetworkPolicy now allows DNS to `169.254.20.10/32` on port 53 as well as
to kube-dns. With the add-on it is needed; without it the rule matches nothing and
harms nothing. Knowing which lets us keep or drop the rule.

**How to verify**

`kubectl -n kube-system get daemonset node-local-dns` exists (or does not).
