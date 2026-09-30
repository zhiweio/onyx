"""Platform tool registry: catalog assembly, dispatch, journaling.

The registry owns the cross-cutting behavior QM applies inside
``createAgentTools``: every call and result is journaled, result text is
capped, and unknown tools fail with a helpful message instead of crashing
the runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from onyx.server.features.build.tools import implementations as impl
from onyx.server.features.build.tools.base import (
    PlatformTool,
    ToolContext,
    ToolInvocation,
    ToolResult,
    cap_result_text,
    text_result,
)
from onyx.utils.logger import setup_logger

logger = setup_logger()


@dataclass
class ToolJournalEntry:
    tool: str
    session_id: str | None
    user_id: str
    arguments: dict[str, Any]
    ok: bool
    result_text: str
    terminated: bool = False


JournalFn = Callable[[ToolJournalEntry], None]


@dataclass
class ToolBindings:
    """Service bindings the executor/bridge provides at build time."""

    search_fn: impl.SearchFn | None = None
    question_hook: impl.QuestionHook | None = None
    background_hook: impl.BackgroundHook | None = None
    journal: JournalFn | None = None


@dataclass
class PlatformToolRegistry:
    tools: dict[str, PlatformTool] = field(default_factory=dict)
    journal: JournalFn | None = None

    # ── assembly ─────────────────────────────────────────────────────────

    @classmethod
    def build(cls, bindings: ToolBindings) -> PlatformToolRegistry:
        catalog: list[PlatformTool] = [
            impl.RagSearchTool(bindings.search_fn),
            impl.QuestionTool(bindings.question_hook),
            impl.BackgroundTool(bindings.background_hook),
            impl.mcp_call_tool(),
            impl.web_search_tool(),
            impl.crawl_tool(),
            impl.connector_query_tool(),
        ]
        return cls(
            tools={tool.name: tool for tool in catalog},
            journal=bindings.journal,
        )

    # ── introspection ────────────────────────────────────────────────────

    def definitions(self) -> list[dict[str, Any]]:
        """MCP ``tools/list`` shaped definitions."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.parameters,
            }
            for tool in self.tools.values()
        ]

    def __contains__(self, name: str) -> bool:
        return name in self.tools

    def __len__(self) -> int:
        return len(self.tools)

    # ── dispatch ─────────────────────────────────────────────────────────

    def call(
        self,
        invocation: ToolInvocation,
        ctx: ToolContext,
    ) -> ToolResult:
        tool = self.tools.get(invocation.tool)
        if tool is None:
            known = ", ".join(sorted(self.tools))
            return text_result(
                f"[{invocation.tool}] unknown tool. Known tools: {known}"
            )
        try:
            result = tool.execute(invocation, ctx)
        except Exception as exc:
            logger.exception("Platform tool %s failed", invocation.tool)
            result = text_result(
                f"[{invocation.tool}] internal error: {exc}"
            )
        # Cap before journaling or returning so transcripts stay bounded.
        for block in result.content:
            if block.get("type") == "text":
                block["text"] = cap_result_text(block["text"])
        self._journal(invocation, ctx, result)
        return result

    def _journal(
        self, invocation: ToolInvocation, ctx: ToolContext, result: ToolResult
    ) -> None:
        if self.journal is None:
            return
        try:
            self.journal(
                ToolJournalEntry(
                    tool=invocation.tool,
                    session_id=invocation.session_id,
                    user_id=ctx.user_id,
                    arguments=invocation.arguments,
                    ok=not result.text().startswith(
                        f"[{invocation.tool}] internal error"
                    ),
                    result_text=result.text()[:2000],
                    terminated=result.terminate,
                )
            )
        except Exception:
            logger.exception("Tool journal write failed")
