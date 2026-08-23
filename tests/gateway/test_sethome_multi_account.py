import yaml
import pytest
from unittest.mock import MagicMock

from gateway.config import GatewayConfig, HomeChannel, Platform, PlatformConfig
from gateway.platforms.base import MessageEvent
from gateway.run import GatewayRunner
from gateway.session import SessionSource


@pytest.mark.asyncio
async def test_sethome_persists_feishu_platform_home_channel(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    runner = GatewayRunner.__new__(GatewayRunner)
    runner.config = GatewayConfig(
        platforms={
            Platform.FEISHU: PlatformConfig(
                enabled=True,
                extra={
                    "accounts": {
                        "corp": {
                            "app_id": "cli_corp",
                            "app_secret": "sec_corp",
                        },
                    },
                },
            ),
        },
    )

    event = MessageEvent(
        text="/sethome",
        source=SessionSource(
            platform=Platform.FEISHU,
            account_id="corp",
            chat_id="oc_c7a439d23a9a824e7c5b4352f802d660",
            chat_name="Team CLAIRE",
            chat_type="group",
            user_id="ou_owner",
            user_name="Ethan",
        ),
    )

    result = await runner._handle_set_home_command(event)

    saved = yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))
    home = saved["platforms"]["feishu"]["home_channel"]

    assert home["account_id"] == "corp"
    assert home["chat_id"] == "oc_c7a439d23a9a824e7c5b4352f802d660"
    assert home["name"] == "Team CLAIRE"
    assert (
        runner.config.get_home_channel(Platform.FEISHU).chat_id
        == "oc_c7a439d23a9a824e7c5b4352f802d660"
    )
    assert runner.config.get_home_channel(Platform.FEISHU).account_id == "corp"
    assert "Home channel set to **Team CLAIRE**" in result


def test_has_home_channel_for_feishu_account_uses_platform_scoped_config():
    runner = GatewayRunner.__new__(GatewayRunner)
    runner.config = GatewayConfig(
        platforms={
            Platform.FEISHU: PlatformConfig(
                enabled=True,
                home_channel=HomeChannel(
                    platform=Platform.FEISHU,
                    chat_id="oc_dm_home",
                    name="Owner DM",
                    account_id="corp",
                ),
                extra={
                    "accounts": {
                        "corp": {
                            "app_id": "cli_corp",
                            "app_secret": "sec_corp",
                        },
                    },
                },
            ),
        },
    )

    source = SessionSource(
        platform=Platform.FEISHU,
        account_id="corp",
        chat_id="oc_group",
        chat_name="Team CLAIRE",
        chat_type="group",
        user_id="ou_owner",
        user_name="Ethan",
    )

    assert runner._has_home_channel_for_source(source) is True


def test_has_home_channel_for_feishu_account_accepts_legacy_account_scoped_fallback():
    runner = GatewayRunner.__new__(GatewayRunner)
    runner.config = GatewayConfig(
        platforms={
            Platform.FEISHU: PlatformConfig(
                enabled=True,
                extra={
                    "accounts": {
                        "corp": {
                            "app_id": "cli_corp",
                            "app_secret": "sec_corp",
                            "home_channel": {
                                "chat_id": "oc_dm_home",
                                "name": "Owner DM",
                            },
                        },
                    },
                },
            ),
        },
    )

    source = SessionSource(
        platform=Platform.FEISHU,
        account_id="corp",
        chat_id="oc_group",
        chat_name="Team CLAIRE",
        chat_type="group",
        user_id="ou_owner",
        user_name="Ethan",
    )

    assert runner._has_home_channel_for_source(source) is True


def test_has_home_channel_for_feishu_account_does_not_fallback_to_global_env(monkeypatch):
    monkeypatch.setenv("FEISHU_HOME_CHANNEL", "oc_global_home")

    runner = GatewayRunner.__new__(GatewayRunner)
    runner.config = GatewayConfig(
        platforms={
            Platform.FEISHU: PlatformConfig(
                enabled=True,
                extra={
                    "accounts": {
                        "corp": {
                            "app_id": "cli_corp",
                            "app_secret": "sec_corp",
                        },
                    },
                },
            ),
        },
    )

    source = SessionSource(
        platform=Platform.FEISHU,
        account_id="corp",
        chat_id="oc_group",
        chat_name="Team CLAIRE",
        chat_type="group",
        user_id="ou_owner",
        user_name="Ethan",
    )

    assert runner._has_home_channel_for_source(source) is False


def test_get_adapter_does_not_fallback_to_platform_default_for_account_bound_source():
    runner = GatewayRunner.__new__(GatewayRunner)
    runner.config = GatewayConfig()
    default_adapter = MagicMock()
    runner.adapters = {Platform.FEISHU: default_adapter}
    runner._adapters_by_binding = {Platform.FEISHU: default_adapter}

    adapter = runner._get_adapter(Platform.FEISHU, account_id="corp")

    assert adapter is None
