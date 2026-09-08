from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class LongTermMemoryItem(BaseModel):
    id: int
    text: str
    kind: str
    source: str
    source_surface: str
    project_id: UUID | None = None
    created_at: datetime
    last_used_at: datetime


class LongTermMemoryListResponse(BaseModel):
    items: list[LongTermMemoryItem]


class LongTermMemoryPatchRequest(BaseModel):
    text: str = Field(min_length=12, max_length=2000)


class LongTermMemoryCreateRequest(BaseModel):
    text: str = Field(min_length=12, max_length=2000)
    kind: str = "semantic"
