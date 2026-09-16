# Sandbox hibernation lifecycle

How a sandbox's memory footprint scales with users, and the lifecycle that
keeps it bounded. Read `image-and-spinup.md` first for the container model
(one sandbox per user, one image, one volume).

## The scaling problem

A running sandbox holds real memory: opencode-serve, per-session Next.js dev
servers, and the document/browser toolchain. With a sandbox resident per user
for the whole idle window, host memory grows linearly with *recently active*
users — not with *concurrent* ones. The original lifecycle compounded this:
the only reclamation was sleep (snapshot to FileStore, then destroy the
container and volume), so every wake paid a full re-provision plus a snapshot
restore, which pushed the idle timeout to an hour.

## Three runtime tiers

The lifecycle now has three tiers, modelled on the mature open-source
sandbox platforms (E2B's filesystem-only pause, Daytona's auto-stop /
auto-archive tiers):

| Tier | Status | Runtime | Memory/CPU | Disk | Wake cost |
| --- | --- | --- | --- | --- | --- |
| running | `RUNNING` | container/pod running | full | full | none (hot path) |
| hibernated | `SLEEPING` + `hibernated_at` set | container stopped, kept | none | full | `docker start` + opencode boot (seconds) |
| archived | `SLEEPING`, `hibernated_at` NULL | destroyed; FileStore snapshots only | none | reclaimed | full provision + snapshot restore |

`Sandbox.hibernated_at` is the discriminator between the two `SLEEPING`
flavors. It is written only together with the `RUNNING -> SLEEPING`
transition of a hibernate, and cleared by any provisioning attempt that
finalizes (RUNNING or FAILED), so it can never claim a runtime that a newer
attempt owns.

**Hibernation is the Docker backend's lane** (`supports_hibernation` on the
manager). Kubernetes pods have no stopped state, so the K8s backend keeps the
classic sleep path — snapshot, then destroy — and relies on the cluster
scheduler plus Burstable requests (defaults 500m/1Gi against 2000m/10Gi
limits) for node density.

## Transitions

```
                create / wake
                     v
   +----------- RUNNING -----------+
   |                |              | idle > SANDBOX_IDLE_TIMEOUT_SECONDS
   | heartbeat      | wake         | (default 900s, no open craft job)
   |                |              v
   | recover   +-- hibernated --+  hibernate: history snapshot (best-effort),
   |           |  (stopped but  |  docker stop, mark SLEEPING+hibernated_at
   +---------->+   kept)        |  fail-open: workspace survives the stop,
               |                |  so a failed snapshot never blocks the stop
               |                |  asleep > SANDBOX_HIBERNATE_MAX_AGE_SECONDS
               |                v  (default 24h)
               |           archive: start briefly, snapshot sessions
               |           fail-closed, terminate, clear hibernated_at
               +<--------------+
                     wake = provision() reuses the exited container
```

Both hibernate and archive run under the user's session-creation lock and
re-check idleness (or the `hibernated_at` token) right before touching the
runtime, mirroring `sleep_sandbox`'s race guards; status writes are the same
attempt-numbered CAS updates.

## Hibernation safety properties

- **Data survives the stop.** Session workspaces live in the per-sandbox
  volume and opencode history in the container's writable layer; a `docker
  stop` keeps both. Wake therefore skips snapshot restore entirely
  (`ensure_session_ready` finds `session_workspace_exists` true).
- **Snapshot cadence bounds data loss from host loss.** Background snapshots
  (`SANDBOX_SNAPSHOT_INTERVAL_SECONDS`, default 900s) keep FileStore copies
  fresh while running; the pre-stop history snapshot narrows the unclean-stop
  window to seconds. The interval is deliberately independent of the idle
  timeout — a short idle timeout must not multiply snapshot load.
- **Drift is detected at wake.** A stopped container pinned to an old image
  (version upgrade) or, outside the proxy lane, a stale `ONYX_PAT` env, is
  retired: started briefly, history captured, then removed. The volume keeps
  the workspaces; the fresh container rehydrates from FileStore.
- **`restart_policy: unless-stopped`** keeps a hibernated container stopped
  across daemon restarts and host reboots.

## Concurrency cap (Evictor)

`SANDBOX_MAX_CONCURRENT` (default 0 = unlimited) bounds *running* sandboxes.
Every provision — create or wake — passes `enforce_sandbox_concurrency`
first: when the cap has no headroom, idle running sandboxes are hibernated
least-recently-active-first until it does. With nothing evictable, the
provision fails with `SandboxCapacityError`; surface that as "at capacity".
Only hibernation-capable backends enforce the cap — a cluster scheduler owns
capacity there.

## Configuration

| Env var | Default | Meaning |
| --- | --- | --- |
| `SANDBOX_IDLE_TIMEOUT_SECONDS` | 900 | no-heartbeat window before hibernate (K8s: sleep) |
| `SANDBOX_HIBERNATE_MAX_AGE_SECONDS` | 86400 | asleep window before archive |
| `SANDBOX_SNAPSHOT_INTERVAL_SECONDS` | 900 | background snapshot cadence while running |
| `SANDBOX_MAX_CONCURRENT` | 0 | cap on running sandboxes; 0 disables |

Metrics: `onyx_craft_sandbox_hibernate_duration_seconds`,
`onyx_craft_sandbox_evictions_total`, and
`onyx_craft_sandbox_hibernated_count` (all in `server/metrics/craft_sandbox.py`).

## Sizing

With the defaults, a 64 GiB host sustains roughly `64 / 2 GiB ≈ 30`
*concurrently active* users (set `SANDBOX_MAX_CONCURRENT` to that bound), plus
hundreds of hibernated users limited only by disk (a few GiB each before the
24h archive reclaims them). The pre-hibernation lifecycle supported about as
many *users active within the last hour* — not per moment — before saturating.
