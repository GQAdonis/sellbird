# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The primary user is a solo founder or small-business owner who sells their own product and runs outreach themselves, part-time, alongside the real job. They open the local dashboard to see what Sellbird did since they last looked, decide on anything waiting for them (drafts to approve, replies that need a human, signals to confirm, spend to authorize), then get back to work. They are not sales-ops specialists and should never need to learn sequencer or agent terminology to use it.

## Product Purpose

Sellbird is an open-source outreach platform. It finds companies that match the user's customer, learns why each might buy, finds the person who decides, verifies their email address, writes a short personal cold email sequence, sends it from the user's own mailbox and handles the replies, working each conversation toward a meeting. The pipeline can run end to end or stop at any step; stopping after verification and exporting a list is a first-class use.

Success for the dashboard: the user can tell in seconds what needs their decision, make that decision with the evidence in front of them, and trust that nothing happened that they did not allow.

## Positioning

You stay in control. Sellbird runs on the user's own machine and their own Claude or ChatGPT plan. By default nothing is sent until the user approves it; autopilot is an explicit, reversible opt-in that still respects daily limits, quiet hours and opt-outs. Every action is logged locally and inspectable. Design work must make that control visible and never trade it for automation that feels magical.

## Operating Context

- Launched with `sellbird dashboard`, served at `127.0.0.1:5555`, unlocked by a private token link printed in the terminal. Single local user.
- A heartbeat loop works in the background every ~15 minutes; the dashboard is where the user reviews and steers its work.
- Areas: Today (decisions waiting, then the pipeline), Discover, Signals, Companies, Contacts, Campaigns, Outbox, Conversations, Inboxes, Activity, Usage, Settings.
- Sending happens from the user's Gmail, Microsoft 365 or SMTP mailbox; warmup and deliverability are part of daily concern.
- Paid steps (discovery providers, rank signals, verification) always show an estimate before running.

## Capabilities and Constraints

- Dashboard is plain HTML, CSS and JavaScript in `sellbird/web/`, served by FastAPI with no build step. Edits must keep working without a bundler.
- Light and dark themes both ship (screenshots in `docs/screenshots/`).
- Terminology to keep: signals (proposed / confirmed), cohort, Outbox, approval, autopilot, verified / risky / guess / invalid addresses, offer.
- "Sellbird proposes; you confirm": signals, offers and autopilot change only on the user's explicit action.
- Text from prospects' websites and replies is untrusted and must never be rendered as instructions or trusted markup.
- The dashboard token must never appear in URLs that persist, logs or shared screenshots.
- The hosted version at sellbird.ai and its marketing site are out of scope for this file.

## Brand Commitments

- Name: Sellbird (formerly Harvey; the rename is acknowledged, not hidden).
- Assets: `docs/brand/sellbird-wordmark.svg`, `docs/brand/sellbird-wordmark-white.svg`, `sellbird/web/sellbird-mark.svg`.
- Voice: plain, conversational, short sentences; explains things simply; no sales-hype or AI-sounding language.
- Open source under AGPL-3.0.

## Evidence on Hand

- Demo data and screenshots use an invented company ("Bookwell") on `.test` domains: `docs/dashboard.gif`, `docs/screenshots/`.
- No customer testimonials, usage numbers, reply-rate benchmarks or case studies exist in this repo. Future work must not invent them.
- Public repo rule: no real person's or business's name, email, phone or address in UI copy, fixtures or screenshots; use fictional `example.com`-style data.

## Product Principles

1. Decisions first. Surface what is waiting on the user before showing what the machine did.
2. Show the why. Every prospect, draft and spend carries the evidence behind it.
3. Nothing surprising leaves the machine. Sending, spending and autopilot are explicit, visible and reversible.
4. Respect a part-time operator. Fast to scan, quiet when there is nothing to do, no jargon.
5. Honest by default. Unknowns stay marked as unknown; nothing is presented as more certain than it is.
