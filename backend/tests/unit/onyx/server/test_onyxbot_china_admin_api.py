from types import SimpleNamespace
from unittest.mock import patch

import pytest

from onyx.db.enums import SSOProviderType
from onyx.server.onyxbot_china_admin_api import (
    _bot_fields_set,
    _identifier_for,
    _mask,
    verify_china_bot,
)


def _wecom_config(**overrides: object) -> SimpleNamespace:
    config = SimpleNamespace(
        corp_id="ww1234567890abcd",
        corp_secret="secret",
        agent_id="1000002",
        bot_token="token",
        bot_encoding_aes_key="aes",
        client_id=None,
        client_secret=None,
        app_id=None,
        app_secret=None,
        robot_code=None,
        bot_aes_key=None,
        bot_verification_token=None,
        bot_encrypt_key=None,
    )
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def _feishu_config(**overrides: object) -> SimpleNamespace:
    config = SimpleNamespace(
        corp_id=None,
        corp_secret=None,
        agent_id=None,
        bot_token=None,
        bot_encoding_aes_key=None,
        client_id=None,
        client_secret=None,
        app_id="cliabcdef123456",
        app_secret="secret",
        robot_code=None,
        bot_aes_key=None,
        bot_verification_token="vt",
        bot_encrypt_key="ek",
    )
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def test_mask_keeps_short_prefix() -> None:
    assert _mask("ww12") == "****"
    assert _mask("ww1234567890") == "ww12********"
    assert _mask("") == ""


def test_identifier_per_platform() -> None:
    assert _identifier_for("wecom", _wecom_config()) == "ww1234567890abcd"
    assert _identifier_for("feishu", _feishu_config()) == "cliabcdef123456"


def test_bot_fields_set_per_platform() -> None:
    assert _bot_fields_set("wecom", _wecom_config())
    assert not _bot_fields_set("wecom", _wecom_config(bot_token=None))
    assert _bot_fields_set("feishu", _feishu_config())
    # Feishu's Encrypt Key is optional — verification only needs the token.
    assert _bot_fields_set("feishu", _feishu_config(bot_encrypt_key=None))
    assert not _bot_fields_set("feishu", _feishu_config(bot_verification_token=None))


def _provider(provider_type: SSOProviderType, config: object) -> SimpleNamespace:
    return SimpleNamespace(provider_type=provider_type, config=config)


@pytest.mark.parametrize(
    "platform",
    ["wecom", "dingtalk", "feishu"],
)
def test_verify_reports_missing_credentials(platform: str) -> None:
    provider = _provider(
        SSOProviderType(platform.upper())  # type: ignore[arg-type]
        if platform != "wecom"
        else SSOProviderType.WECOM,
        {},
    )
    with (
        patch(
            "onyx.server.onyxbot_china_admin_api.fetch_sso_providers",
            return_value=[provider],
        ) as fetch_providers,
        patch("onyx.server.onyxbot_china_admin_api._config_for") as config_for,
    ):
        config_for.side_effect = lambda _provider, _cfg: _wecom_config(
            bot_token=None, bot_encoding_aes_key=None
        )
        result = verify_china_bot(platform)

    assert fetch_providers.called
    assert result.ok is False
    assert result.detail == "bot credentials missing"


def test_verify_success_calls_token_fetch() -> None:
    provider = _provider(SSOProviderType.FEISHU, {})
    with (
        patch(
            "onyx.server.onyxbot_china_admin_api.fetch_sso_providers",
            return_value=[provider],
        ),
        patch(
            "onyx.server.onyxbot_china_admin_api._config_for",
            return_value=_feishu_config(),
        ),
        patch(
            "onyx.server.onyxbot_china_admin_api._fetch_token",
            return_value="tenant-token",
        ) as fetch_token,
    ):
        result = verify_china_bot("feishu")

    fetch_token.assert_called_once()
    assert result.ok is True
