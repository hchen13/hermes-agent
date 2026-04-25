import asyncio
import sys
import threading
from types import ModuleType, SimpleNamespace

from gateway.platforms.feishu import (
    _FEISHU_WS_THREAD_STATE,
    _FeishuWSLoopProxy,
    _feishu_ws_connect_proxy,
    _install_feishu_ws_runtime_proxies,
    _run_official_feishu_ws_client,
)


def test_feishu_ws_loop_proxy_uses_thread_local_loops():
    proxy = _FeishuWSLoopProxy()
    results = {}

    def worker(name: str) -> None:
        loop = asyncio.new_event_loop()
        _FEISHU_WS_THREAD_STATE.loop = loop
        try:

            async def current_loop_id() -> int:
                return id(asyncio.get_running_loop())

            results[name] = proxy.run_until_complete(current_loop_id())
        finally:
            delattr(_FEISHU_WS_THREAD_STATE, "loop")
            loop.close()

    threads = [
        threading.Thread(target=worker, args=("a",)),
        threading.Thread(target=worker, args=("b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results["a"] != results["b"]


def test_install_feishu_ws_runtime_proxies_patches_once():
    original_connect = object()
    original_loop = asyncio.new_event_loop()
    module = SimpleNamespace(
        websockets=SimpleNamespace(connect=original_connect),
        loop=original_loop,
    )

    try:
        _install_feishu_ws_runtime_proxies(module)
        first_loop = module.loop
        first_connect = module.websockets.connect

        _install_feishu_ws_runtime_proxies(module)

        assert module.loop is first_loop
        assert module.websockets.connect is first_connect
        assert module._hermes_ws_original_connect is original_connect
    finally:
        original_loop.close()


def test_feishu_ws_connect_proxy_applies_thread_local_ping_overrides():
    seen = {}

    async def fake_connect(*args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return "ok"

    loop = asyncio.new_event_loop()
    _FEISHU_WS_THREAD_STATE.loop = loop
    _FEISHU_WS_THREAD_STATE.original_connect = fake_connect
    _FEISHU_WS_THREAD_STATE.ping_interval = 7
    _FEISHU_WS_THREAD_STATE.ping_timeout = 3
    try:
        result = loop.run_until_complete(_feishu_ws_connect_proxy("wss://example.invalid/ws"))
    finally:
        for attr in ("loop", "original_connect", "ping_interval", "ping_timeout"):
            delattr(_FEISHU_WS_THREAD_STATE, attr)
        loop.close()

    assert result == "ok"
    assert seen["args"] == ("wss://example.invalid/ws",)
    assert seen["kwargs"]["ping_interval"] == 7
    assert seen["kwargs"]["ping_timeout"] == 3


def test_official_feishu_ws_runtime_applies_ping_overrides_without_global_loop_race():
    seen = {}

    async def fake_connect(*args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return "ok"

    fake_client_module = ModuleType("lark_oapi.ws.client")
    fake_client_module.loop = None
    fake_client_module.websockets = SimpleNamespace(connect=fake_connect)
    fake_ws_module = ModuleType("lark_oapi.ws")
    fake_ws_module.client = fake_client_module
    fake_root_module = ModuleType("lark_oapi")
    fake_root_module.ws = fake_ws_module

    fake_adapter = SimpleNamespace(
        _ws_thread_loop=None,
        _ws_reconnect_nonce=2,
        _ws_reconnect_interval=3,
        _ws_ping_interval=7,
        _ws_ping_timeout=4,
    )

    class _FakeWSClient:
        def start(self):
            import lark_oapi.ws.client as ws_client_module

            loop = ws_client_module.loop
            seen["loop_during_start"] = loop
            seen["adapter_loop_during_start"] = fake_adapter._ws_thread_loop
            seen["result"] = loop.run_until_complete(
                ws_client_module.websockets.connect("wss://example.invalid/ws")
            )

    original_modules = sys.modules.copy()
    sys.modules["lark_oapi"] = fake_root_module
    sys.modules["lark_oapi.ws"] = fake_ws_module
    sys.modules["lark_oapi.ws.client"] = fake_client_module
    try:
        _run_official_feishu_ws_client(_FakeWSClient(), fake_adapter)
    finally:
        sys.modules.clear()
        sys.modules.update(original_modules)

    assert seen["result"] == "ok"
    assert seen["args"] == ("wss://example.invalid/ws",)
    assert seen["kwargs"]["ping_interval"] == 7
    assert seen["kwargs"]["ping_timeout"] == 4
    assert isinstance(seen["loop_during_start"], _FeishuWSLoopProxy)
    assert seen["adapter_loop_during_start"].is_closed()
    assert fake_client_module.websockets.connect is _feishu_ws_connect_proxy
    assert fake_client_module._hermes_ws_original_connect is fake_connect
    assert fake_adapter._ws_thread_loop is None


def test_official_feishu_ws_runtime_reapplies_overrides_after_sdk_configure():
    class _FakeWSClient:
        def __init__(self):
            self._reconnect_nonce = 30
            self._reconnect_interval = 120
            self._ping_interval = 120
            self.configure_calls = []

        def _configure(self, conf):
            self.configure_calls.append(conf)
            self._reconnect_nonce = conf.ReconnectNonce
            self._reconnect_interval = conf.ReconnectInterval
            self._ping_interval = conf.PingInterval

        def start(self):
            conf = SimpleNamespace(ReconnectNonce=99, ReconnectInterval=88, PingInterval=77)
            self._configure(conf)

    fake_client = _FakeWSClient()
    fake_adapter = SimpleNamespace(
        _ws_thread_loop=None,
        _ws_reconnect_nonce=2,
        _ws_reconnect_interval=3,
        _ws_ping_interval=4,
        _ws_ping_timeout=5,
    )
    fake_client_module = ModuleType("lark_oapi.ws.client")
    fake_client_module.loop = None

    async def fake_connect(*args, **kwargs):
        return "ok"

    fake_client_module.websockets = SimpleNamespace(connect=fake_connect)
    fake_ws_module = ModuleType("lark_oapi.ws")
    fake_ws_module.client = fake_client_module
    fake_root_module = ModuleType("lark_oapi")
    fake_root_module.ws = fake_ws_module

    original_modules = sys.modules.copy()
    sys.modules["lark_oapi"] = fake_root_module
    sys.modules["lark_oapi.ws"] = fake_ws_module
    sys.modules["lark_oapi.ws.client"] = fake_client_module
    try:
        _run_official_feishu_ws_client(fake_client, fake_adapter)
    finally:
        sys.modules.clear()
        sys.modules.update(original_modules)

    assert len(fake_client.configure_calls) == 1
    assert fake_client._reconnect_nonce == 2
    assert fake_client._reconnect_interval == 3
    assert fake_client._ping_interval == 4
    assert fake_adapter._ws_thread_loop is None
