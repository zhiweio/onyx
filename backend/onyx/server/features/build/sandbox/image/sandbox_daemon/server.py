import asyncio
import base64
import binascii
import hashlib
import json
import os
import secrets
import tarfile
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import uvicorn
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from sandbox_daemon import processes
from sandbox_daemon.contract import (  # ty: ignore[unresolved-import]
    PROCESS_ROOT,
    PUSH_DAEMON_PORT,
    SIDECAR_CODEX_EVENTS_PATH,
    SIDECAR_CODEX_HEALTH_PATH,
    SIDECAR_CODEX_RPC_PATH,
    SIDECAR_FILESYSTEM_LIST_PATH,
    SIDECAR_HEALTH_PATH,
    SIDECAR_OPENCODE_HISTORY_CREATE_PATH,
    SIDECAR_OPENCODE_HISTORY_MARK_RESTORED_PATH,
    SIDECAR_OPENCODE_HISTORY_RESTORE_PATH,
    SIDECAR_OUTPUTS_MANIFEST_PATH,
    SIDECAR_PROCESS_INPUT_SUFFIX,
    SIDECAR_PROCESS_ITEM_PREFIX,
    SIDECAR_PROCESS_LIST_PATH,
    SIDECAR_PROCESS_POLL_SUFFIX,
    SIDECAR_PROCESS_START_PATH,
    SIDECAR_PROCESS_STOP_SUFFIX,
    SIDECAR_PUSH_PATH,
    SIDECAR_PUSH_PUBLIC_KEY_ENV_VAR,
    SIDECAR_READY_PATH,
    SIDECAR_SNAPSHOT_CREATE_PATH,
    SIDECAR_SNAPSHOT_RESTORE_ROUTE,
    FilesystemListRequest,
    OutputsManifestRequest,
    ProcessInputRequest,
    ProcessPollRequest,
    ProcessStartRequest,
    ProcessStopRequest,
    SnapshotCreateRequest,
    sidecar_snapshot_restore_path,
)
from sandbox_daemon.extract import MAX_BUNDLE_BYTES, safe_extract_then_atomic_swap
from sandbox_daemon.filesystem import FilesystemPathError, list_session_directory
from sandbox_daemon.manifest import build_outputs_manifest
from sandbox_daemon.opencode_history import (
    create_opencode_history_archive_file,
    mark_opencode_history_restored,
    opencode_history_restored,
    restore_opencode_history_archive,
)
from sandbox_daemon.snapshot import (
    SnapshotError,
    has_snapshot_content,
    iter_snapshot_archive,
    restore_snapshot,
)

app = FastAPI(title="sandbox-sidecar", docs_url=None, redoc_url=None)

_MAX_TIMESTAMP_DRIFT_SECONDS = 60

_public_key: Ed25519PublicKey | None = None


def _get_public_key() -> Ed25519PublicKey:
    global _public_key
    if _public_key is not None:
        return _public_key

    raw_b64 = os.environ.get(SIDECAR_PUSH_PUBLIC_KEY_ENV_VAR, "")
    if not raw_b64:
        raise HTTPException(status_code=500, detail="Push public key not configured")
    try:
        pub_bytes = base64.b64decode(raw_b64)
        _public_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(
            status_code=500,
            detail=f"Push public key is not a valid base64-encoded Ed25519 key: {e}",
        )
    return _public_key


def _verify_signature(
    path: str,
    sha256_hex: str,
    signature_b64: str,
    timestamp: str,
) -> None:
    """Verify timestamp drift and Ed25519 signature over {timestamp}|{path}|{sha256_hex}."""
    try:
        ts_int = int(timestamp)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid timestamp")
    if abs(time.time() - ts_int) > _MAX_TIMESTAMP_DRIFT_SECONDS:
        raise HTTPException(status_code=401, detail="Timestamp out of range")

    try:
        sig = base64.b64decode(signature_b64)
    except binascii.Error:
        raise HTTPException(status_code=401, detail="Invalid signature encoding")

    message = f"{timestamp}|{path}|{sha256_hex}".encode()
    try:
        _get_public_key().verify(sig, message)
    except InvalidSignature:
        raise HTTPException(status_code=401, detail="Invalid signature")


def _iter_file_then_unlink(path: Path) -> Iterator[bytes]:
    try:
        with path.open("rb") as archive_file:
            while True:
                chunk = archive_file.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk
    finally:
        path.unlink(missing_ok=True)


async def _spool_verified_archive(
    request: Request,
    expected_sha256: str,
) -> Path:
    archive_path: Path | None = None
    sha256_hash = hashlib.sha256()
    try:
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp_file:
            archive_path = Path(tmp_file.name)
            async for chunk in request.stream():
                sha256_hash.update(chunk)
                tmp_file.write(chunk)

        actual_sha = sha256_hash.hexdigest()
        if actual_sha != expected_sha256.lower():
            raise HTTPException(
                status_code=400,
                detail=f"SHA-256 mismatch: expected {expected_sha256}, got {actual_sha}",
            )
        return archive_path
    except Exception:
        if archive_path is not None:
            archive_path.unlink(missing_ok=True)
        raise


def _process_token() -> str:
    """Lazily generate the in-pod shared token for process management. The
    opencode plugin reads the same file (same container filesystem)."""
    token_path = PROCESS_ROOT / "token"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    if not token_path.exists():
        token_path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        token_path.chmod(0o600)
    return token_path.read_text(encoding="utf-8").strip()


def _verify_process_auth(
    request: Request,
    x_push_signature: str | None = Header(default=None, alias="X-Push-Signature"),
    x_push_timestamp: str | None = Header(default=None, alias="X-Push-Timestamp"),
) -> None:
    """Bearer token (in-pod agent) OR Ed25519 signature (host watcher)."""
    auth = request.headers.get("Authorization", "")
    try:
        if auth.startswith("Bearer ") and auth[7:] == _process_token():
            return
    except OSError:
        pass
    if x_push_signature and x_push_timestamp:
        body_hash = hashlib.sha256(b"").hexdigest()
        try:
            _verify_signature(
                request.scope["path"], body_hash, x_push_signature, x_push_timestamp
            )
            return
        except InvalidSignature:
            pass
        except HTTPException:
            pass
    raise HTTPException(status_code=401, detail="process endpoint auth failed")


@app.post(SIDECAR_PROCESS_START_PATH)
async def process_start(
    request: Request,
    x_push_signature: str | None = Header(default=None, alias="X-Push-Signature"),
    x_push_timestamp: str | None = Header(default=None, alias="X-Push-Timestamp"),
) -> dict[str, object]:
    _verify_process_auth(request, x_push_signature, x_push_timestamp)
    body = await request.body()
    try:
        payload = ProcessStartRequest.model_validate_json(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid request body: {e}")

    def _start() -> dict:
        return processes.start_process(
            PROCESS_ROOT, command=payload.command, kind=payload.kind
        )

    try:
        meta = await asyncio.to_thread(_start)
    except processes.ProcessError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"process_id": meta["process_id"], "pid": meta["pid"]}


@app.post(SIDECAR_PROCESS_ITEM_PREFIX + SIDECAR_PROCESS_POLL_SUFFIX)
async def process_poll(
    process_id: str,
    request: Request,
    x_push_signature: str | None = Header(default=None, alias="X-Push-Signature"),
    x_push_timestamp: str | None = Header(default=None, alias="X-Push-Timestamp"),
) -> dict[str, object]:
    _verify_process_auth(request, x_push_signature, x_push_timestamp)
    body = await request.body()
    try:
        payload = ProcessPollRequest.model_validate_json(body or b"{}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid request body: {e}")
    try:
        return await asyncio.to_thread(
            processes.read_output,
            PROCESS_ROOT,
            process_id,
            cursor=payload.cursor,
            max_bytes=payload.max_bytes,
        )
    except processes.ProcessError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post(SIDECAR_PROCESS_ITEM_PREFIX + SIDECAR_PROCESS_INPUT_SUFFIX)
async def process_input(
    process_id: str,
    request: Request,
    x_push_signature: str | None = Header(default=None, alias="X-Push-Signature"),
    x_push_timestamp: str | None = Header(default=None, alias="X-Push-Timestamp"),
) -> dict[str, str]:
    _verify_process_auth(request, x_push_signature, x_push_timestamp)
    body = await request.body()
    try:
        payload = ProcessInputRequest.model_validate_json(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid request body: {e}")
    try:
        await asyncio.to_thread(
            processes.write_input, PROCESS_ROOT, process_id, payload.data
        )
    except processes.ProcessGoneError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except processes.ProcessError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "written"}


@app.post(SIDECAR_PROCESS_ITEM_PREFIX + SIDECAR_PROCESS_STOP_SUFFIX)
async def process_stop(
    process_id: str,
    request: Request,
    x_push_signature: str | None = Header(default=None, alias="X-Push-Signature"),
    x_push_timestamp: str | None = Header(default=None, alias="X-Push-Timestamp"),
) -> dict[str, object]:
    _verify_process_auth(request, x_push_signature, x_push_timestamp)
    body = await request.body()
    try:
        payload = ProcessStopRequest.model_validate_json(body or b"{}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid request body: {e}")
    try:
        return await asyncio.to_thread(
            processes.stop_process, PROCESS_ROOT, process_id, signal_name=payload.signal
        )
    except processes.ProcessError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get(SIDECAR_PROCESS_LIST_PATH)
async def process_list(
    request: Request,
    x_push_signature: str | None = Header(default=None, alias="X-Push-Signature"),
    x_push_timestamp: str | None = Header(default=None, alias="X-Push-Timestamp"),
) -> list[dict[str, object]]:
    _verify_process_auth(request, x_push_signature, x_push_timestamp)
    return await asyncio.to_thread(processes.list_processes, PROCESS_ROOT)


# ── codex app-server bridge ─────────────────────────────────────────────
# 501 (not 500) when the image shipped without the codex binary: callers
# treat that as "runtime unavailable for this deployment", not an error.


def _codex_bridge():
    from sandbox_daemon.codex_bridge import CodexBridge  # ty: ignore[unresolved-import]

    return CodexBridge.instance()


@app.post(SIDECAR_CODEX_RPC_PATH)
async def codex_rpc(
    request: Request,
    x_push_signature: str | None = Header(default=None, alias="X-Push-Signature"),
    x_push_timestamp: str | None = Header(default=None, alias="X-Push-Timestamp"),
) -> dict[str, object]:
    _verify_process_auth(request, x_push_signature, x_push_timestamp)
    from sandbox_daemon.codex_bridge import (
        CodexBridgeError,  # ty: ignore[unresolved-import]
    )

    body = await request.body()
    try:
        payload = json.loads(body or b"{}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid request body: {e}")
    method = payload.get("method")
    params = payload.get("params") or {}
    initialize = bool(payload.get("initialize"))
    timeout_ms = float(payload.get("timeout_ms") or 30_000)
    if not isinstance(method, str) or not isinstance(params, dict):
        raise HTTPException(status_code=400, detail="method/params required")

    def _call() -> dict[str, object]:
        bridge = _codex_bridge()
        if initialize:
            bridge.initialize()
        return {
            "ok": True,
            "result": bridge.rpc(method, params, timeout=timeout_ms / 1000.0),
        }

    try:
        return await asyncio.to_thread(_call)
    except CodexBridgeError as e:
        return {"ok": False, "error": str(e)}


@app.get(SIDECAR_CODEX_EVENTS_PATH)
def codex_events(
    request: Request,
    x_push_signature: str | None = Header(default=None, alias="X-Push-Signature"),
    x_push_timestamp: str | None = Header(default=None, alias="X-Push-Timestamp"),
) -> StreamingResponse:
    _verify_process_auth(request, x_push_signature, x_push_timestamp)
    from sandbox_daemon.codex_bridge import (
        CodexBridgeError,  # ty: ignore[unresolved-import]
    )

    try:
        _codex_bridge().initialize()
    except CodexBridgeError as e:
        raise HTTPException(status_code=501, detail=str(e))

    import queue as _queue

    bridge = _codex_bridge()
    sub = bridge.subscribe()

    def _stream() -> Iterator[bytes]:
        try:
            while True:
                # Client disconnect surfaces as GeneratorExit on the next
                # yield; the finally below unsubscribes.
                try:
                    message = sub.get(timeout=15.0)
                except _queue.Empty:
                    yield b": keepalive\n\n"
                    continue
                yield b"data: " + json.dumps(message).encode("utf-8") + b"\n\n"
        finally:
            bridge.unsubscribe(sub)

    return StreamingResponse(
        _stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


@app.get(SIDECAR_CODEX_HEALTH_PATH)
def codex_health(
    request: Request,
    x_push_signature: str | None = Header(default=None, alias="X-Push-Signature"),
    x_push_timestamp: str | None = Header(default=None, alias="X-Push-Timestamp"),
) -> dict[str, object]:
    _verify_process_auth(request, x_push_signature, x_push_timestamp)
    return _codex_bridge().status()


@app.get(SIDECAR_HEALTH_PATH)
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(SIDECAR_READY_PATH)
def ready() -> dict[str, str]:
    if not opencode_history_restored():
        raise HTTPException(status_code=503, detail="opencode history not restored")
    return {"status": "ok"}


@app.post(SIDECAR_FILESYSTEM_LIST_PATH)
async def filesystem_list(
    request: Request,
    x_push_signature: str = Header(..., alias="X-Push-Signature"),
    x_push_timestamp: str = Header(..., alias="X-Push-Timestamp"),
) -> dict[str, object]:
    body = await request.body()
    _verify_signature(
        SIDECAR_FILESYSTEM_LIST_PATH,
        hashlib.sha256(body).hexdigest(),
        x_push_signature,
        x_push_timestamp,
    )

    try:
        payload = FilesystemListRequest.model_validate_json(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid request body: {e}")

    try:
        listing = await asyncio.to_thread(
            list_session_directory,
            session_id=payload.session_id,
            path=payload.path,
        )
    except FilesystemPathError as e:
        detail = str(e)
        status_code = 400 if "traversal" in detail else 404
        raise HTTPException(status_code=status_code, detail=detail)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"filesystem list OS error: {e}")

    return listing.model_dump()


@app.post(SIDECAR_OUTPUTS_MANIFEST_PATH)
async def outputs_manifest(
    request: Request,
    x_push_signature: str = Header(..., alias="X-Push-Signature"),
    x_push_timestamp: str = Header(..., alias="X-Push-Timestamp"),
) -> dict[str, object]:
    body = await request.body()
    _verify_signature(
        SIDECAR_OUTPUTS_MANIFEST_PATH,
        hashlib.sha256(body).hexdigest(),
        x_push_signature,
        x_push_timestamp,
    )

    try:
        payload = OutputsManifestRequest.model_validate_json(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid request body: {e}")

    try:
        manifest = await asyncio.to_thread(build_outputs_manifest, payload.session_id)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"outputs manifest OS error: {e}")

    return manifest.model_dump()


@app.post(SIDECAR_PUSH_PATH)
async def push(
    request: Request,
    mount_path: str = Query(...),
    x_bundle_sha256: str = Header(..., alias="X-Bundle-Sha256"),
    x_push_signature: str = Header(..., alias="X-Push-Signature"),
    x_push_timestamp: str = Header(..., alias="X-Push-Timestamp"),
) -> dict[str, str]:
    _verify_signature(
        mount_path, x_bundle_sha256.lower(), x_push_signature, x_push_timestamp
    )

    if not mount_path.startswith("/"):
        raise HTTPException(status_code=400, detail="mount_path must be absolute")

    content_length = request.headers.get("content-length")
    if content_length is not None and int(content_length) > MAX_BUNDLE_BYTES:
        raise HTTPException(
            status_code=413, detail=f"Bundle exceeds {MAX_BUNDLE_BYTES} byte limit"
        )

    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BUNDLE_BYTES:
            raise HTTPException(
                status_code=413, detail=f"Bundle exceeds {MAX_BUNDLE_BYTES} byte limit"
            )
        chunks.append(chunk)
    body = b"".join(chunks)

    actual_sha = hashlib.sha256(body).hexdigest()
    if actual_sha != x_bundle_sha256.lower():
        raise HTTPException(
            status_code=400,
            detail=f"SHA-256 mismatch: expected {x_bundle_sha256}, got {actual_sha}",
        )

    try:
        safe_extract_then_atomic_swap(body, mount_path)
    except (ValueError, tarfile.ReadError, tarfile.CompressionError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "ok"}


@app.post(SIDECAR_SNAPSHOT_CREATE_PATH)
async def snapshot_create(
    request: Request,
    x_push_signature: str = Header(..., alias="X-Push-Signature"),
    x_push_timestamp: str = Header(..., alias="X-Push-Timestamp"),
) -> Response:
    body = await request.body()
    _verify_signature(
        SIDECAR_SNAPSHOT_CREATE_PATH,
        hashlib.sha256(body).hexdigest(),
        x_push_signature,
        x_push_timestamp,
    )

    try:
        payload = SnapshotCreateRequest.model_validate_json(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid request body: {e}")

    try:
        has_content = await asyncio.to_thread(has_snapshot_content, payload.session_id)
    except SnapshotError as e:
        raise HTTPException(status_code=500, detail=f"Snapshot create failed: {e}")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Snapshot create OS error: {e}")

    if not has_content:
        return Response(status_code=204)

    return StreamingResponse(
        iter_snapshot_archive(payload.session_id),
        media_type="application/gzip",
    )


@app.post(SIDECAR_SNAPSHOT_RESTORE_ROUTE, status_code=204)
async def snapshot_restore(
    session_id: UUID,
    request: Request,
    x_bundle_sha256: str = Header(..., alias="X-Bundle-Sha256"),
    x_push_signature: str = Header(..., alias="X-Push-Signature"),
    x_push_timestamp: str = Header(..., alias="X-Push-Timestamp"),
) -> None:
    _verify_signature(
        sidecar_snapshot_restore_path(session_id),
        x_bundle_sha256.lower(),
        x_push_signature,
        x_push_timestamp,
    )

    archive_path: Path | None = None
    try:
        archive_path = await _spool_verified_archive(
            request,
            x_bundle_sha256,
        )
        await asyncio.to_thread(
            restore_snapshot,
            session_id=session_id,
            archive_path=archive_path,
        )
    except SnapshotError as e:
        raise HTTPException(status_code=500, detail=f"Snapshot restore failed: {e}")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Snapshot restore OS error: {e}")
    finally:
        if archive_path is not None:
            archive_path.unlink(missing_ok=True)


@app.post(SIDECAR_OPENCODE_HISTORY_CREATE_PATH)
async def opencode_history_create(
    x_push_signature: str = Header(..., alias="X-Push-Signature"),
    x_push_timestamp: str = Header(..., alias="X-Push-Timestamp"),
) -> Response:
    empty_sha256 = hashlib.sha256(b"").hexdigest()
    _verify_signature(
        SIDECAR_OPENCODE_HISTORY_CREATE_PATH,
        empty_sha256,
        x_push_signature,
        x_push_timestamp,
    )

    archive_path: Path | None = None
    try:
        archive_path = await asyncio.to_thread(create_opencode_history_archive_file)
    except SnapshotError as e:
        raise HTTPException(
            status_code=500, detail=f"opencode history create failed: {e}"
        )
    except OSError as e:
        raise HTTPException(
            status_code=500, detail=f"opencode history create OS error: {e}"
        )

    if archive_path is None:
        return Response(status_code=204)

    return StreamingResponse(
        _iter_file_then_unlink(archive_path),
        media_type="application/gzip",
    )


@app.post(SIDECAR_OPENCODE_HISTORY_RESTORE_PATH, status_code=204)
async def opencode_history_restore(
    request: Request,
    x_bundle_sha256: str = Header(..., alias="X-Bundle-Sha256"),
    x_push_signature: str = Header(..., alias="X-Push-Signature"),
    x_push_timestamp: str = Header(..., alias="X-Push-Timestamp"),
) -> None:
    _verify_signature(
        SIDECAR_OPENCODE_HISTORY_RESTORE_PATH,
        x_bundle_sha256.lower(),
        x_push_signature,
        x_push_timestamp,
    )

    archive_path: Path | None = None
    try:
        archive_path = await _spool_verified_archive(
            request,
            x_bundle_sha256,
        )
        await asyncio.to_thread(restore_opencode_history_archive, archive_path)
    except SnapshotError as e:
        raise HTTPException(
            status_code=500, detail=f"opencode history restore failed: {e}"
        )
    except OSError as e:
        raise HTTPException(
            status_code=500, detail=f"opencode history restore OS error: {e}"
        )
    finally:
        if archive_path is not None:
            archive_path.unlink(missing_ok=True)


@app.post(SIDECAR_OPENCODE_HISTORY_MARK_RESTORED_PATH, status_code=204)
async def opencode_history_mark_restored(
    x_push_signature: str = Header(..., alias="X-Push-Signature"),
    x_push_timestamp: str = Header(..., alias="X-Push-Timestamp"),
) -> None:
    empty_sha256 = hashlib.sha256(b"").hexdigest()
    _verify_signature(
        SIDECAR_OPENCODE_HISTORY_MARK_RESTORED_PATH,
        empty_sha256,
        x_push_signature,
        x_push_timestamp,
    )

    try:
        await asyncio.to_thread(mark_opencode_history_restored)
    except OSError as e:
        raise HTTPException(
            status_code=500, detail=f"opencode history mark-restored OS error: {e}"
        )


if __name__ == "__main__":
    # TODO(security): bind to 127.0.0.1 and front with an in-pod proxy, or
    # restrict the listener to the sandbox network namespace.
    uvicorn.run(app, host="0.0.0.0", port=PUSH_DAEMON_PORT)  # noqa: S104
