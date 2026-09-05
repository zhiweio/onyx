from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SourceDomain(str, Enum):
    POLICY = "policy"
    ENFORCEMENT = "enforcement"
    NEWS = "news"
    REFERENCE = "reference"
    COMMERCIAL = "commercial"
    IP = "ip"


class TrustTier(str, Enum):
    OFFICIAL = "official"
    PROFESSIONAL = "professional"
    NEWS = "news"
    COMMUNITY = "community"
    COMMERCIAL = "commercial"


class AccessMode(str, Enum):
    HTML_SEARCH = "html_search"
    HTML_FETCH = "html_fetch"
    OFFICIAL_API = "official_api"
    LICENSED_API = "licensed_api"
    MCP = "mcp"
    LOCAL_FILE = "local_file"


class PluginStatus(BaseModel):
    ok: bool
    message: str = ""
    configured: bool = True


class LiveQuery(BaseModel):
    intent: str = ""
    query: str
    company: str | None = None
    uscc: str | None = None
    industry: str | None = None
    region: str | None = None
    policy_number: str | None = None
    patent_keyword: str | None = None
    domains: list[SourceDomain] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    since_days: int = 365
    limit: int = 8


class SourceHit(BaseModel):
    source_id: str
    hit_id: str
    title: str
    url: str
    snippet: str = ""
    published_at: datetime | None = None
    score: float = 0.0


class CompanyEntity(BaseModel):
    name: str | None = None
    uscc: str | None = None


class PatentEntity(BaseModel):
    application_no: str | None = None
    assignee: str | None = None


class NormalizedRecord(BaseModel):
    source_id: str
    record_id: str
    url: str
    title: str
    published_at: datetime | None = None
    trust_tier: TrustTier
    domain: SourceDomain
    tax_type: str | None = None
    region_code: str | None = None
    industry_code: str | None = None
    doc_number: str | None = None
    issuing_body: str | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    company: CompanyEntity | None = None
    patent: PatentEntity | None = None
    relations: dict[str, str] = Field(default_factory=dict)
    snippet: str = ""
    full_text: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class OrchestratorResult(BaseModel):
    records: list[NormalizedRecord]
    plugin_notes: list[str] = Field(default_factory=list)
