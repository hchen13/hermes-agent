"""Fork contract: a concrete Feishu account must never fall back to another bot."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import GatewayConfig, HomeChannel, Platform, PlatformConfig
from gateway.delivery import DeliveryTarget, resolve_delivery_transport
from gateway.run import GatewayRunner
from gateway.run_accounts import AccountAdapterMap
from gateway.session import SessionSource, build_session_key


def _config():
    return GatewayConfig(platforms={Platform.FEISHU: PlatformConfig(enabled=True, extra={
        "default_account": "personal",
        "accounts": {
            "personal": {"app_id": "cli_personal", "app_secret": "test", "dm_policy": "open"},
            "work": {"app_id": "cli_work", "app_secret": "test", "dm_policy": "allowlist", "allowed_users": ["owner"]},
        },
    })})


def _bot(account):
    return SimpleNamespace(platform=Platform.FEISHU, account_id=account,
                           send=AsyncMock(), fatal_error_retryable=True)


def _runner():
    runner = GatewayRunner.__new__(GatewayRunner)
    runner.config = _config()
    runner.adapters = {}
    runner._profile_adapters = {}
    runner._profile_configs = {"vera": _config()}
    runner.delivery_router = SimpleNamespace(adapters={}, account_adapters={})
    runner._failed_platforms = {}
    runner._ensure_reconnect_watcher_running = MagicMock()
    return runner


def test_both_bots_registered_and_cron_map_carries_bindings():
    runner = _runner()
    personal, work = _bot("personal"), _bot("work")
    runner._register_adapter(Platform.FEISHU, work)
    runner._register_adapter(Platform.FEISHU, personal)
    assert runner.adapters[Platform.FEISHU] is personal
    assert isinstance(runner.adapters, AccountAdapterMap)
    assert resolve_delivery_transport(Platform.FEISHU, runner.config, runner.adapters, account_id="work").adapter is work
    assert resolve_delivery_transport(Platform.FEISHU, runner.config, runner.adapters, account_id="missing") is None
    assert len(list(runner._iter_adapter_bindings())) == 2


def test_secondary_profile_never_borrows_primary_account():
    runner = _runner()
    primary, secondary = _bot("work"), _bot("work")
    runner._register_adapter(Platform.FEISHU, primary)
    runner._register_adapter(Platform.FEISHU, secondary, "vera")
    assert runner._get_adapter(Platform.FEISHU, "work", "vera") is secondary
    assert runner._get_adapter(Platform.FEISHU, "personal", "vera") is None
    assert runner._profile_adapters["vera"].account_adapters[(Platform.FEISHU, "work")] is secondary


def test_unregister_and_stale_fatal_do_not_remove_sibling_or_replacement():
    runner = _runner()
    personal, work, replacement = _bot("personal"), _bot("work"), _bot("work")
    runner._register_adapter(Platform.FEISHU, personal)
    runner._register_adapter(Platform.FEISHU, work)
    runner._register_adapter(Platform.FEISHU, replacement)
    runner._unregister_adapter(work)
    assert runner._get_adapter(Platform.FEISHU, "work") is replacement
    runner._unregister_adapter(personal)
    assert runner.adapters[Platform.FEISHU] is replacement
    assert runner._get_adapter(Platform.FEISHU, "personal") is None


def test_reconnect_queues_each_account_independently():
    runner = _runner()
    personal, work = _bot("personal"), _bot("work")
    assert runner._queue_retryable_fatal_platform(personal)
    assert runner._queue_retryable_fatal_platform(work)
    assert not runner._queue_retryable_fatal_platform(work)
    assert set(runner._failed_platforms) == {(Platform.FEISHU, "personal"), (Platform.FEISHU, "work")}
    assert runner._failed_platforms[(Platform.FEISHU, "work")]["config"].extra["app_id"] == "cli_work"


@pytest.mark.asyncio
async def test_reconnect_rebuilds_only_the_failed_account():
    runner = _runner()
    personal, work = _bot("personal"), _bot("work")
    runner._register_adapter(Platform.FEISHU, personal)
    runner._queue_retryable_fatal_platform(work)
    replacement = _bot("work")
    runner._flag_reconnect_needs_attention = MagicMock()
    runner._create_adapter = MagicMock(return_value=replacement)
    runner._wire_adapter_handlers = MagicMock()
    runner._connect_adapter_with_timeout = AsyncMock(return_value=True)

    async def install(platform, adapter):
        runner._register_adapter(platform, adapter)
        runner._failed_platforms.pop((platform, adapter.account_id))

    runner._install_reconnected_adapter = install
    await runner._reconnect_failed_platform((Platform.FEISHU, "work"), float("inf"))
    assert runner._create_adapter.call_args.args[1].extra["app_id"] == "cli_work"
    assert runner._get_adapter(Platform.FEISHU, "work") is replacement
    assert runner._get_adapter(Platform.FEISHU, "personal") is personal
    assert not runner._failed_platforms


def test_session_and_delivery_target_preserve_account_identity():
    a = SessionSource(platform=Platform.FEISHU, chat_id="same_chat", account_id="personal", chat_type="dm")
    b = SessionSource(platform=Platform.FEISHU, chat_id="same_chat", account_id="work", chat_type="dm")
    assert build_session_key(a) != build_session_key(b)
    assert SessionSource.from_dict(b.to_dict()).account_id == "work"
    assert DeliveryTarget.parse("origin", b).account_id == "work"
    target = DeliveryTarget.parse("feishu[work]:oc_chat")
    assert target.account_id == "work" and target.to_string() == "feishu[work]:oc_chat"


def test_cron_explicit_target_keeps_origin_account():
    from cron.scheduler_delivery import _resolve_single_delivery_target
    job = {"origin": {"platform": "feishu", "chat_id": "oc_origin", "account_id": "work"}}
    target = _resolve_single_delivery_target(job, "feishu:oc_other")
    assert target["account_id"] == "work"


def test_home_channel_does_not_cross_account_boundary():
    config = _config()
    config.platforms[Platform.FEISHU].home_channel = HomeChannel(Platform.FEISHU, "oc_work", "Work", account_id="work")
    assert config.get_home_channel(Platform.FEISHU).account_id == "work"
    assert config.get_home_channel(Platform.FEISHU, "personal") is None
    assert config.get_home_channel(Platform.FEISHU, "work").chat_id == "oc_work"


def test_plugin_rewire_visits_every_account_once():
    runner = _runner()
    personal, work = _bot("personal"), _bot("work")
    personal.rewire_plugin_handlers = MagicMock()
    work.rewire_plugin_handlers = MagicMock()
    runner._register_adapter(Platform.FEISHU, personal)
    runner._register_adapter(Platform.FEISHU, work)
    assert runner._rewire_plugin_handlers() == 2
    personal.rewire_plugin_handlers.assert_called_once_with()
    work.rewire_plugin_handlers.assert_called_once_with()
