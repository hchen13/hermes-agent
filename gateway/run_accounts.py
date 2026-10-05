"""Concrete bot bindings alongside the legacy one-adapter-per-platform maps."""

from typing import Optional

from gateway.config import Platform


class AccountAdapterMap(dict):
    """Platform lookup remains compatible; cron also carries concrete account bindings."""

    def __init__(self, adapters, account_adapters):
        super().__init__(adapters)
        self.account_adapters = account_adapters


class GatewayAccountBindingsMixin:
    @staticmethod
    def _adapter_binding_key(platform: Platform, account_id: Optional[str] = None):
        account_id = str(account_id or "").strip()
        return (platform, account_id) if account_id else platform

    @staticmethod
    def _normalize_binding_key(key):
        return (key[0], key[1]) if isinstance(key, tuple) else (key, None)

    @staticmethod
    def _binding_label(platform: Platform, account_id: Optional[str] = None) -> str:
        account_id = account_id.strip() if isinstance(account_id, str) else None
        return f"{platform.value}[{account_id}]" if account_id else platform.value

    @staticmethod
    def _account_id_for_adapter(adapter) -> Optional[str]:
        value = getattr(adapter, "account_id", None)
        return value.strip() or None if isinstance(value, str) else None

    def _ensure_adapter_registry(self) -> None:
        if getattr(self, "_adapters_by_binding", None) is None:
            self._adapters_by_binding = {}
        if getattr(self, "_profile_account_adapters", None) is None:
            self._profile_account_adapters = {}
        if getattr(self, "adapters", None) is None:
            self.adapters = {}
        if not isinstance(self.adapters, AccountAdapterMap):
            self.adapters = AccountAdapterMap(self.adapters, self._adapters_by_binding)
        for platform, adapter in self.adapters.items():
            self._adapters_by_binding.setdefault(self._adapter_binding_key(platform, self._account_id_for_adapter(adapter)), adapter)
        router = getattr(self, "delivery_router", None)
        if router is not None:
            router.account_adapters = self._adapters_by_binding

    def _account_adapters_for_profile(self, profile: Optional[str] = None) -> dict:
        self._ensure_adapter_registry()
        primary = getattr(self, "_primary_profile_name", None)
        if not profile or profile == "default" or profile == primary:
            return self._adapters_by_binding
        return self._profile_account_adapters.get(profile, {})

    def _register_adapter(self, platform: Platform, adapter, profile: Optional[str] = None) -> None:
        self._ensure_adapter_registry()
        if profile:
            bindings = self._profile_account_adapters.setdefault(profile, {})
            legacy = self._profile_adapters.setdefault(profile, {})
            if not isinstance(legacy, AccountAdapterMap):
                legacy = self._profile_adapters[profile] = AccountAdapterMap(legacy, bindings)
            config = self._profile_configs[profile]
        else:
            bindings, legacy, config = self._adapters_by_binding, self.adapters, self.config
        account_id = self._account_id_for_adapter(adapter)
        bindings[self._adapter_binding_key(platform, account_id)] = adapter
        if platform not in legacy or not account_id or account_id == config.get_default_account_id(platform):
            legacy[platform] = adapter
        if getattr(self, "delivery_router", None) is not None:
            self.delivery_router.adapters = self.adapters

    def _unregister_adapter(self, adapter, profile: Optional[str] = None) -> None:
        bindings = self._account_adapters_for_profile(profile)
        platform = adapter.platform
        key = self._adapter_binding_key(platform, self._account_id_for_adapter(adapter))
        if bindings.get(key) is not adapter:
            return
        bindings.pop(key)
        legacy = self._adapters_for_profile(profile)
        if legacy.get(platform) is adapter:
            replacement = next((a for k, a in bindings.items() if self._normalize_binding_key(k)[0] == platform), None)
            if replacement is None:
                legacy.pop(platform, None)
            else:
                legacy[platform] = replacement

    def _get_adapter(self, platform: Platform, account_id: Optional[str] = None, profile: Optional[str] = None):
        if account_id:
            return self._account_adapters_for_profile(profile).get(self._adapter_binding_key(platform, account_id))
        return self._adapters_for_profile(profile).get(platform)

    def _get_adapter_for_source(self, source):
        return self._delivery_adapter_for(source) if source is not None else None

    def _iter_adapter_bindings(self, profile: Optional[str] = None):
        bindings = self._account_adapters_for_profile(profile)
        seen = set()
        for key, adapter in list(bindings.items()) + list(self._adapters_for_profile(profile).items()):
            if id(adapter) not in seen:
                seen.add(id(adapter))
                yield self._normalize_binding_key(key)[0], adapter

    def _all_adapter_instances(self):
        self._ensure_adapter_registry()
        return list(self._adapters_by_binding.items())

    def _has_home_channel_for_source(self, source) -> bool:
        if source is None:
            return False
        config = (getattr(self, "_profile_configs", None) or {}).get(source.profile, self.config)
        return bool(config.get_home_channel(source.platform, getattr(source, "account_id", None)))
