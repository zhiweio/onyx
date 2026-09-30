# Sandbox runtime decision: keep containers, do not move to microVMs

Status: decided. Re-read this before proposing a runtime swap again.

Question: should Craft replace its sandbox runtime (Docker containers, or
Kubernetes pods) with E2B, with a self-hosted Firecracker fleet, or with
another microVM runtime?

Answer: **no.** The current runtimes stay. This document records why, what
would change the answer, and how a deployment that needs kernel-level
isolation can get it today without a rewrite.

## The runtime does not set the footprint

A sandbox costs memory in two states, and only one of them is a runtime
question.

**Idle but RUNNING.** The resident set is `opencode serve` (one process per
sandbox, supervised by a restart loop), one `bun run dev` Next.js server per
session that ever built a webapp, and — if a browser task ran — a live
Chromium. Hibernation (`hibernation-lifecycle.md`, Docker lane) already drops
this to zero after `SANDBOX_IDLE_TIMEOUT_SECONDS`. A microVM would not beat
zero.

**Actively used.** 1–2 GiB, and almost all of it is the workload: the agent
server, the dev servers, the browser. A microVM pays that same cost inside the
guest, plus guest-kernel and VMM overhead. It does not shrink the process set.

E2B's density advantage comes from `userfaultfd` page faults served lazily out
of a template `memfile`, so a resumed sandbox loads only the pages it touches.
That pays off when a product needs many sandboxes that resume *with their
in-memory process state*. Craft does not need that state: `opencode` rebuilds
from disk, and a dev server restarts lazily on first request. The mechanism
solves a problem this workload does not have.

The real footprint levers live elsewhere:

- **Idle time** — done, via hibernation (`hibernation-lifecycle.md`).
- **Kubernetes has no sleep lane.** `supports_hibernation` is Docker-only, so a
  K8s sandbox is destroyed on sleep and rebuilt from a snapshot on wake. Moving
  the workspace from `emptyDir` to a PVC would give the K8s lane the same
  cheap wake Docker has. See "Next levers" below.
- **Per-session dev servers** are the largest resident cost for an active user.
  Reaping them on idle, with a lazy restart on preview, is a workload change,
  not a runtime change.

## What E2B self-hosting would require

Researched against `e2b-dev/infra` (see "Sources" below).

| Requirement | Cost for Onyx |
| --- | --- |
| Terraform + **Nomad + Consul**; Kubernetes is not a supported target | A second orchestrator to operate. Onyx ships Compose and Helm only. Self-hosters would have to run it. |
| `/dev/kvm` on every sandbox node | Rules out Docker Desktop and macOS, which is where the Compose lane runs. |
| NBD kernel module, hugepages `vm.nr_hugepages >= 2048` | ~4 GiB reserved per sandbox node, before any sandbox runs. |
| API, Orchestrator, Client Proxy, Envd, Dashboard API, PostgreSQL, Redis, **ClickHouse**, object storage | A control plane larger than Onyx's own. |
| Templates built from a Docker image into `memfile` + `rootfs.ext4` + `snapfile` + `metadata.json` | Replaces the `onyxdotapp/sandbox:<tag>` image pipeline. The 3.3 GiB extracted image also becomes a per-sandbox copy-on-write disk. |
| Sandbox URLs are public (opt-out exists) | See the two architectural blockers below. |

### Blocker 1: the egress proxy identifies sandboxes by source IP

`sandbox_proxy/identity.py` resolves a request to a sandbox by TCP peer IP:
`identity_docker.py` streams Docker events for container IPs, `identity_k8s.py`
watches pods for pod IPs. This is not an implementation detail — Chromium's
traffic carries no session tag at all (`browser-cli.sh`: "proxy authorizes by
source IP"), and the gate fails closed when it cannot attribute a request.

E2B sandboxes leave through E2B's own NAT, so the proxy would see E2B's
addresses, not per-sandbox ones. The identity layer would have to move to a
per-sandbox token. That is a rewrite of a security-critical component, and it
sits outside `SandboxManager` entirely — nothing in the backend interface
signals that the cost exists.

### Blocker 2: the control plane would move to the public internet

`opencode` on `:4096` and the Next.js dev servers on `3010-3100` are
cluster-internal today: container-name DNS on the sandbox bridge, or a
ClusterIP Service with a NetworkPolicy backstop. With a hosted sandbox runtime
they become public URLs, with HTTP Basic as the only guard on `:4096`. E2B can
require a traffic access token, so this is mitigable — but the threat model
inverts, and the webapp proxy's careful header handling exists precisely
because that endpoint is not trusted.

### What a VM would *not* fix

Two acknowledged risks do not move:

- **The host Docker socket.** `api_server`, `background`, and `sandbox-proxy`
  bind-mount `/var/run/docker.sock`; anything that reaches it is root on the
  host. That is control-plane side, unaffected by the guest's isolation.
- **The proxy as an alternate path to IMDS.** The runbook already records that
  node-level IMDSv2 `hop_limit=1` does not cover the proxy's own egress.

## The middle path: a RuntimeClass, not a rewrite

If the driver is kernel-level isolation, Kata Containers gets it without
touching the backend. Verified properties:

- `kubectl exec` keeps working (the guest Kata Agent serves it), so the 14 K8s
  exec call sites are unaffected.
- `emptyDir` and `configMap` volumes keep working through `virtio-fs`.
- The pod keeps a **normal CNI pod IP**, so `identity_k8s.py` and the whole
  egress identity model stay as they are.
- The guest runs a full Linux kernel, so `firewall-init.sh`'s
  iptables/ip6tables/conntrack rules work and its self-verification passes.
- `runtimeClassName` is a pod-spec field, and the Python overlay
  (`_overlay_dynamic_fields`) only rewrites `hostAliases` and the secret-backed
  env — every other field passes through. So this is a Helm value, not code.

Costs and checks:

- Needs `/dev/kvm` (bare metal or nested virtualization), so it applies to the
  Kubernetes lane on a capable node pool only.
- A RuntimeClass declares per-pod overhead (`podFixed`; Kata's own
  documentation uses 320 MiB as the example). That is a real density cost,
  charged to the pod cgroup — measure it on the target node type.
- Block-backed `emptyDir` ignores `sizeLimit` under Kata, and `subPath` is not
  supported. The 50 GiB workspace volume needs a measured check.

**gVisor is ruled out for this workload.** It needs no KVM, which is
attractive, but it supports iptables only partially and has limited `nftables`.
`firewall-init.sh` fails closed: `step_self_verify` aborts provisioning when
the OUTPUT policy does not stick. A gVisor pod would not provision at all
without redesigning egress control.

### Using it

Set one value, on a node pool that can run the runtime:

```yaml
sandboxPod:
  runtimeClassName: kata-qemu   # empty (default) = cluster runtime
```

Before enabling it on a real deployment, confirm on one sandbox pod:

1. `firewall-init.sh` completes and egress is proxy-only (provisioning succeeds;
   check the init logs for the self-verify step).
2. `exec`-driven paths work: session workspace setup, file upload, and a turn.
3. The webapp preview loads (dev server on the reserved port, HMR websocket).
4. The egress proxy still attributes traffic — e.g. an MCP or connect-app
   request reaches the right user's credentials.
5. Snapshot create and restore work (50 GiB workspace on the chosen volume mode).
6. Measure per-pod overhead against `podFixed` on the target node type.

## When to revisit

Re-open this decision if any of these becomes true:

- Craft is offered as a multi-tenant service running code from untrusted third
  parties, and the dedicated-node-pool plus RuntimeClass mitigations are not
  enough for the threat model.
- A compliance or customer requirement names kernel-level isolation
  explicitly.
- A product requirement emerges for sub-second wake **with in-flight process
  state** (that is the one thing only memory snapshots give you).
- The host prerequisites stop being a problem: for example, if every supported
  deployment target has KVM and Onyx is willing to operate a sandbox fleet.

If it is revisited, budget these two prerequisites first. They are the real
cost of any new backend, and neither is visible from `SandboxManager`:

- Extract transport-agnostic primitives from the 21-method interface. Today 31
  Docker exec and 14 Kubernetes exec call sites implement policy through
  transport verbs. `sandbox-exec-sidecar.md` sketches this refactor.
- Add a third identity provider to the egress proxy
  (`sandbox_proxy/backend.py`).

## Evaluated and rejected

| Option | Why not |
| --- | --- |
| E2B self-hosted | Prerequisites and operator burden above; breakers 1 and 2. |
| E2B Cloud (hosted) | Same architecture blockers, plus user files and sandbox egress leave the deployment boundary. Every exec and file operation would also cross the public internet. |
| Firecracker built in-house | Rebuilds E2B's core with less maturity: kernel/rootfs pipeline, snapshot store, networking slots, and a new control plane. Highest cost, lowest leverage. |
| Microsandbox (`libkrun`) | Same class of change as Firecracker, and no answer for the identity, exec, and volume work. |
| gVisor | Netfilter support is too limited for `firewall-init.sh`; provisioning fails closed. |
| CRIU checkpoint/restore on Docker | Checkpointing a container needs privileges and a matching CRIU/kernel; the workload does not need in-memory resume. Docker hibernation (stop/start) already covers the wake cost. |
| Kata Containers | Kept, but as an opt-in RuntimeClass rather than a backend. See above. |

## Next levers (not runtime work)

1. **K8s hibernation parity via PVC.** Give each sandbox a persistent volume for
   the workspace so pod deletion preserves it, and wake stops paying the
   snapshot restore. Decisions to make first: storage class and zone affinity
   (a PVC pins the pod to a zone), cost per idle user, and lifecycle on archive.
2. **Workload footprint.** Reap idle per-session dev servers and restart them on
   preview. This is the largest resident cost per active user.
3. **Primitive refactor.** Do this before any future backend, not during.

## Sources

- E2B infrastructure: `e2b-dev/infra` (deepwiki) — self-hosting services, host
  prerequisites, template/snapshot artifacts, network slots, `userfaultfd`
  overcommit.
- Kata Containers: `kata-containers/kata-containers` (deepwiki) — KVM and
  `vhost` requirements, `podFixed` overhead, CNI pod IP, guest kernel netfilter,
  `emptyDir` limitations.
- gVisor: `google/gvisor` (deepwiki) — platforms, partial iptables support,
  compatibility notes.
- Onyx code: `sandbox/base.py`, `sandbox/docker/docker_sandbox_manager.py`,
  `sandbox/image/firewall-init.sh`, `sandbox_proxy/identity.py`,
  `sandbox_proxy/backend.py`, `sandbox/nextjs_dev.py`,
  `deployment/helm/charts/onyx/templates/sandbox-podtemplate.yaml`.
