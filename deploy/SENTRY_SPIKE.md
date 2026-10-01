# Bug reporting: buy the capture, build the conversation

**Spike, 22 August 2026.** Question asked: use Sentry's SDK for capture, replay
and error grouping, and build only the customer-facing layer ourselves?

**Short answer: yes on the engineering, but there is one decision to make first,
and it is not an engineering decision.**

---

## What Sentry actually gives us

Measured against the current release rather than taken from marketing.

| | |
|---|---|
| Error capture, breadcrumbs, network timings | included |
| Session Replay | included |
| Error grouping / fingerprinting | included — this is the "one bad deploy floods the queue" problem, solved |
| Release tracking | included |
| Queue with assignment, status, search, comments | included |

Building capture and grouping ourselves is genuinely months. Grouping in
particular looks easy and is not: normalising stack traces so that the same
fault from twelve browsers becomes one ticket is the whole product.

**Bundle cost.** `bundle.tracing.replay.min.js` is **225 KB**. Our entire front
end is 239 KB of JavaScript. So the SDK is roughly the size of the application
it would be watching.

## The masking defaults are better than expected

Read out of the shipped bundle, not the documentation:

```
maskAllText            = true
maskAllInputs          = true
blockAllMedia          = true
networkDetailAllowUrls = []      <- empty, so no bodies or headers
```

A replay therefore shows layout, timing and where someone clicked — not the
words on screen. That is the right default and it removes most of the objection
to recording a session in a product operating under an NDA.

## Three things it does not mask, and one of them bites us today

**Exception messages.** Not masked, sent verbatim. Ours quote agency names,
answers and file names — `"No SCDES corpus loaded"` is a mild example.

**Breadcrumbs and URLs.** Also verbatim. This application currently puts
`?email=…` on **every** API call. Adopting Sentry without a `beforeSend` scrubber
would ship a government employee's address to a third party on every request,
which is a worse leak than the bug we are trying to catch.

**Where the data goes.** Sentry SaaS holds it, US or EU region. Everything above
is fixable in a day of `beforeSend` work; this one is not an engineering
question.

## The residency decision

Three options, and only the third is ours to make alone.

**1 — Sentry SaaS.** Fastest, cheapest, best tooling. Agency data leaves our
infrastructure and lands with a third party. Needs a data-processing agreement
and a decision from IIA, because the NDA a user signs two screens into this
product says these materials are confidential. State agencies will ask; some
will require an answer in writing before they will register.

**2 — Self-hosted Sentry.** Open source, keeps everything on our own boxes,
solves the residency question outright. It is not light. Sentry's own minimum is
4 CPU and 16 GB RAM, running Postgres, Kafka, ClickHouse, Redis, Relay and
Snuba under Docker Compose.

The staging server today:

```
2 vCPU · 7.8 GB RAM · 16 GB free disk
the application itself idles at ~660 MB
```

Self-hosted Sentry would not fit, and on a box that could hold it, the bug
tracker would be several times the size of the product it watches. That is a
separate instance and a standing ops commitment, not a library.

**3 — Build the light layer only.** Widget, short form, technical capture
(console errors, network status codes, view, browser, version), and an admin
queue. No replay, no third party, nothing leaves. Perhaps a week. It does not
give us grouping or replay, which are the two things that make a bug tracker
scale.

## Recommendation

**Do 3 now and decide 1 versus 2 separately.**

The light layer is a week, ships under the NDA without anyone signing anything,
and covers Phase 1 as specified — widget, short form, automatic technical
capture, admin queue. Every report it produces is still a report we would have
lost otherwise.

Sentry is the right answer for Phase 2 (replay and grouping) **if** the
residency question resolves in favour of SaaS. Self-hosting is the wrong answer
at this size: the operational weight is out of proportion to a product with one
staging box and no production users yet.

What that avoids is the failure mode where we spend a fortnight wiring Sentry in
and then discover the first real agency will not accept a third-party processor
— at which point the work is thrown away *and* we still have no bug reporting.

## What to settle before committing anyone

1. **Will IIA accept a third-party processor for telemetry?** Brett's call, and
   it needs to survive a procurement conversation, not just an internal one.
2. **US or EU region?** SC agencies will expect US, and it cannot be changed
   later without recreating the project.
3. **Retention.** Sentry's default is 90 days for replays. What do we want, and
   what will we tell users?
4. **Who may watch a replay?** Restricted access has to be set up on day one,
   not after the first recording of someone's screen.

The `?email=` scrubbing is worth doing whichever way this goes — it is a leak
into our own logs today, not only into Sentry's.
