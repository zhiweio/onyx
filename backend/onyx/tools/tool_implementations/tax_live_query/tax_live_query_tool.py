import json
from typing import Any

from sqlalchemy.orm import Session
from typing_extensions import override

from onyx.chat.emitter import Emitter
from onyx.configs.app_configs import TAX_VERTICAL_ENABLED
from onyx.server.query_and_chat.placement import Placement
from onyx.server.query_and_chat.streaming_models import (
    CustomToolDelta,
    CustomToolStart,
    Packet,
)
from onyx.tax.models import LiveQuery, SourceDomain
from onyx.tax.orchestrator import run_live_query
from onyx.tools.interface import Tool
from onyx.tools.models import CustomToolCallSummary, ToolResponse


class TaxLiveQueryTool(Tool[None]):
    NAME = "tax_live_query"
    DISPLAY_NAME = "Tax live query"
    DESCRIPTION = (
        "Query China tax policy, enforcement, news, local reference entries, "
        "and configured commercial MCP sources (Qixinbao, PatSnap) at analysis "
        "time. Returns cited records. Use for tax risk, policy, company credit, "
        "or patent questions."
    )

    def __init__(self, tool_id: int, emitter: Emitter) -> None:
        super().__init__(emitter=emitter)
        self._id = tool_id

    @property
    def id(self) -> int:
        return self._id

    @property
    def name(self) -> str:
        return self.NAME

    @property
    def description(self) -> str:
        return self.DESCRIPTION

    @property
    def display_name(self) -> str:
        return self.DISPLAY_NAME

    @classmethod
    def is_available(cls, db_session: Session) -> bool:  # noqa: ARG003
        return TAX_VERTICAL_ENABLED

    @override
    def tool_definition(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query in Chinese or English.",
                        },
                        "intent": {
                            "type": "string",
                            "description": "Optional intent such as policy, enforcement, news, company, patent.",
                        },
                        "company": {"type": "string"},
                        "uscc": {
                            "type": "string",
                            "description": "Unified social credit code.",
                        },
                        "region": {"type": "string"},
                        "patent_keyword": {"type": "string"},
                        "source_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Optional plugin ids: sta_policy, sta_violation, "
                                "tax_intel, tax_reference, qixinbao_mcp, patsnap_mcp."
                            ),
                        },
                        "limit": {"type": "integer"},
                    },
                    "required": ["query"],
                },
            },
        }

    def emit_start(self, placement: Placement) -> None:
        self.emitter.emit(
            Packet(placement=placement, obj=CustomToolStart(tool_name=self.display_name))
        )

    def run(
        self,
        placement: Placement,
        override_kwargs: None = None,  # noqa: ARG002
        **llm_kwargs: Any,
    ) -> ToolResponse:
        raw_sources = llm_kwargs.get("source_ids") or []
        source_ids = [str(item) for item in raw_sources] if raw_sources else []
        domains: list[SourceDomain] = []
        intent = str(llm_kwargs.get("intent") or "")
        try:
            limit = int(llm_kwargs.get("limit") or 8)
        except (TypeError, ValueError):
            limit = 8
        result = run_live_query(
            LiveQuery(
                intent=intent,
                query=str(llm_kwargs.get("query") or ""),
                company=llm_kwargs.get("company"),
                uscc=llm_kwargs.get("uscc"),
                region=llm_kwargs.get("region"),
                patent_keyword=llm_kwargs.get("patent_keyword"),
                domains=domains,
                source_ids=source_ids,
                limit=max(1, min(limit, 20)),
            )
        )
        payload = {
            "records": [record.model_dump(mode="json") for record in result.records],
            "plugin_notes": result.plugin_notes,
        }
        self.emitter.emit(
            Packet(
                placement=placement,
                obj=CustomToolDelta(
                    tool_name=self.display_name,
                    response_type="json",
                    data=payload,
                ),
            )
        )
        return ToolResponse(
            rich_response=CustomToolCallSummary(
                tool_name=self.NAME,
                response_type="json",
                tool_result=payload,
            ),
            llm_facing_response=json.dumps(payload, ensure_ascii=False),
        )
