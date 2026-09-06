from __future__ import annotations

import json

import httpx

from onyx.server.features.build.sandbox.opencode.serve_client import (
    OpencodeServeClient,
)


def test_post_summarize_sends_provider_model_and_auto_false() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    client = OpencodeServeClient(
        base_url="http://test.invalid:4096",
        password="pw",
        transport=httpx.MockTransport(handler),
    )
    client._post_summarize(
        "ses_1",
        "openai",
        "gpt-5",
        directory="/workspace/sessions/x",
    )
    assert len(seen) == 1
    assert seen[0].url.path == "/session/ses_1/summarize"
    body = json.loads(seen[0].content)
    assert body == {
        "providerID": "openai",
        "modelID": "gpt-5",
        "auto": False,
    }
    client.close()
