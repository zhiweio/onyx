from onyx.configs.app_configs import TAX_DISABLED_SOURCES
from onyx.tax.plugin import LiveSourcePlugin
from onyx.tax.sources.html_plugin import (
    StaPolicyPlugin,
    StaViolationPlugin,
    TaxIntelPlugin,
)
from onyx.tax.sources.mcp_plugin import PatsnapMcpPlugin, QixinbaoMcpPlugin
from onyx.tax.sources.reference_plugin import TaxReferencePlugin

_OVERRIDE: list[LiveSourcePlugin] | None = None


def default_plugins() -> list[LiveSourcePlugin]:
    return [
        StaPolicyPlugin(),
        StaViolationPlugin(),
        TaxIntelPlugin(),
        TaxReferencePlugin(),
        QixinbaoMcpPlugin(),
        PatsnapMcpPlugin(),
    ]


def set_plugins_for_tests(plugins: list[LiveSourcePlugin] | None) -> None:
    global _OVERRIDE
    _OVERRIDE = plugins


def get_plugins() -> list[LiveSourcePlugin]:
    plugins = _OVERRIDE if _OVERRIDE is not None else default_plugins()
    disabled = set(TAX_DISABLED_SOURCES)
    return [plugin for plugin in plugins if plugin.source_id not in disabled]


def get_plugin(source_id: str) -> LiveSourcePlugin | None:
    for plugin in get_plugins():
        if plugin.source_id == source_id:
            return plugin
    return None
