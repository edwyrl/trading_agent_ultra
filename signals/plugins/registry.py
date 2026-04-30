from __future__ import annotations

from typing import Iterable

from signals.plugins.base import BaseSignalPlugin


class SignalRegistry:
    def __init__(self, plugins: Iterable[BaseSignalPlugin] | None = None):
        self._plugins: dict[str, BaseSignalPlugin] = {}
        for plugin in plugins or []:
            self.register(plugin)

    def register(self, plugin: BaseSignalPlugin) -> None:
        self._plugins[plugin.signal_key] = plugin

    def get(self, signal_key: str) -> BaseSignalPlugin:
        plugin = self._plugins.get(signal_key)
        if plugin is None:
            raise KeyError(f"Unknown signal plugin: {signal_key}")
        return plugin

    def list_plugins(self) -> list[BaseSignalPlugin]:
        return [self._plugins[key] for key in sorted(self._plugins.keys())]
