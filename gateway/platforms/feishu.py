"""Compatibility wrapper for the Feishu/Lark plugin adapter.

The implementation moved to ``plugins.platforms.feishu.adapter`` upstream, but
older tests, tools, and user code still import ``gateway.platforms.feishu``.
Keep this module as a thin re-export so the plugin architecture can move
without breaking those call sites.
"""

from plugins.platforms.feishu import adapter as _adapter
from plugins.platforms.feishu.adapter import *  # noqa: F401,F403


def __getattr__(name):
    return getattr(_adapter, name)
