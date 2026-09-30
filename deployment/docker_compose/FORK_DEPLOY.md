# Fork Deployment Guide (GHCR + docker compose)

This fork builds its own images and publishes them to the GitHub Container
Registry (GHCR). Deploy them on a VPS with the stock docker compose files.
This guide replaces the upstream release flow (Docker Hub, beta tags,
nightly builds).

## What gets built

The `Build and Push Images` workflow (`.github/workflows/images.yml`) builds
three images on every push to `main`, on every `v*` tag, and on manual
dispatch:

| Image | Used by compose services |
| --- | --- |
| `ghcr.io/<owner>/onyx-backend` | `api_server`, `background`, `mcp_gateway`, `sandbox-proxy` |
| `ghcr.io/<owner>/onyx-web-server` | `web_server` |
| `ghcr.io/<owner>/sandbox` | Craft sandbox containers (`sandbox-image-prepull`) |

`<owner>` is the GitHub account or org that owns this fork. Third-party images
(Postgres, Redis, OpenSearch, MinIO, nginx) still come from their registries.

Tags:

- `sha-<short-sha>` — one tag per commit. Use these to pin or roll back.
- `latest` — the build from the tip of `main`.
- `<tag-name>` — a `v*` tag (for example `v1.2.3`).

## One-time VPS setup

1. Create a classic GitHub personal access token with the `read:packages`
   scope. GHCR images are private by default.
2. Log in on the VPS:

   ```bash
   echo <TOKEN> | docker login ghcr.io -u <github-username> --password-stdin
   ```

## Configure the stack

Clone this repo on the VPS (or copy `deployment/docker_compose/`). Copy
`env.template` to `.env`, then point the app images at GHCR:

```bash
cd deployment/docker_compose
cp env.template .env
```

Add these lines to `.env`:

```bash
ONYX_BACKEND_IMAGE=ghcr.io/<owner>/onyx-backend:latest
ONYX_WEB_SERVER_IMAGE=ghcr.io/<owner>/onyx-web-server:latest
SANDBOX_CONTAINER_IMAGE=ghcr.io/<owner>/sandbox:latest
```

Do not include `docker-compose.local-build.yml` in `COMPOSE_FILE`. That
overlay builds images on the VPS itself; the GHCR flow pulls them instead.

If you use the Craft sandbox, keep `docker-compose.craft.yml` in `COMPOSE_FILE`
and set `SANDBOX_IMAGE_PULL_POLICY=IfNotPresent` (the default `Never` is for
local builds only).

## Deploy an update

```bash
git pull
cd deployment/docker_compose
docker compose pull
docker compose up -d
```

Watch the logs while services come up:

```bash
docker compose logs -f api_server background web_server
```

## Roll back

Point `.env` at the `sha-<short-sha>` tag of the last known-good commit,
then pull and restart:

```bash
ONYX_BACKEND_IMAGE=ghcr.io/<owner>/onyx-backend:sha-abc1234
ONYX_WEB_SERVER_IMAGE=ghcr.io/<owner>/onyx-web-server:sha-abc1234
SANDBOX_CONTAINER_IMAGE=ghcr.io/<owner>/sandbox:sha-abc1234
```

Find the short sha in the commit history, or in the image list on the
packages page of the GitHub account.
