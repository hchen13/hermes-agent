"""Account overlays for platforms hosting several independent bot credentials."""

from gateway.config import HomeChannel, Platform, PlatformConfig


def merge_account_config(platform: Platform, base: PlatformConfig, account_id: str, block: dict) -> PlatformConfig:
    payload = base.to_dict()
    extra = dict(payload.pop("extra"))
    extra.pop("accounts", None)
    extra.pop("default_account", None)
    payload.pop("home_channel", None)
    payload.update({key: value for key, value in block.items() if key != "extra"})
    # Account-local settings win over inherited extras, regardless of spelling.
    account_extra = {key: value for key, value in block.items() if key not in PlatformConfig._TYPED_KEYS}
    if isinstance(block.get("extra"), dict):
        account_extra.update(block["extra"])
    payload["extra"] = {**extra, **account_extra, "account_id": account_id}
    payload["enabled"] = block.get("enabled", True)
    if isinstance(block.get("home_channel"), dict):
        home = dict(block["home_channel"])
        home.setdefault("platform", platform.value)
        home.setdefault("account_id", account_id)
        payload["home_channel"] = HomeChannel.from_dict(home).to_dict()
    return PlatformConfig.from_dict(payload)
