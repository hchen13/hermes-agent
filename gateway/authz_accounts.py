"""Account-local Feishu admission; chat admission is not approval authority."""


def _ids(raw) -> set[str]:
    if raw is None:
        return set()
    values = raw.split(",") if isinstance(raw, str) else raw if isinstance(raw, (list, tuple, set, frozenset)) else [raw]
    return {str(value).strip() for value in values if str(value).strip()}


def _matches(source, allowed: set[str]) -> bool:
    identities = {str(value).strip() for value in (source.user_id, source.user_id_alt, source.user_name) if value is not None}
    return "*" in allowed or bool(identities & allowed)


def authorize_feishu_account(source, extra: dict) -> bool | None:
    is_group = source.chat_type in {"group", "forum", "channel"}
    if not is_group:
        policy = str(extra.get("dm_policy") or "").strip().lower()
        if policy in {"open", "allow_all"}:
            return True
        if policy in {"disabled", "closed", "deny"}:
            return False
        allowed = _ids(extra.get("allowed_users") or extra.get("allow_from"))
        return _matches(source, allowed) if allowed else None
    if _matches(source, _ids(extra.get("admins"))):
        return True
    groups = extra.get("groups") or extra.get("group_rules")
    rule = None
    if isinstance(groups, dict):
        chat_id = str(source.chat_id or "").lower()
        rule = next((v for k, v in groups.items() if str(k).lower() == chat_id and isinstance(v, dict)), groups.get("*"))
    if isinstance(rule, dict):
        allowed, blocked = _ids(rule.get("allowlist")), _ids(rule.get("blacklist"))
        policy = rule.get("policy") or extra.get("default_group_policy") or extra.get("group_policy")
    else:
        allowed = _ids(extra.get("allowed_group_users") or extra.get("group_allowed_users")
                       or extra.get("allowed_users") or extra.get("allow_from"))
        blocked = set()
        policy = extra.get("default_group_policy") or extra.get("group_policy")
    if _matches(source, blocked):
        return False
    policy = str(policy or "").strip().lower()
    if policy in {"open", "allow_all"}:
        return True
    if policy in {"closed", "deny", "disabled"} or allowed:
        return _matches(source, allowed)
    return None
