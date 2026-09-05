from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from onyx.db.enums import BuildSessionStatus, CraftProjectFileSource
from onyx.db.models import BuildSession, CraftProject, CraftProjectFile


class CraftProjectUpsertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    instructions: str | None = None


class CraftProjectPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    instructions: str | None = None


class CraftProjectFileResponse(BaseModel):
    id: UUID
    project_id: UUID
    path: str
    name: str
    mime_type: str | None
    size_bytes: int | None
    content_hash: str | None
    source: CraftProjectFileSource
    produced_by_session_id: UUID | None
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, row: CraftProjectFile) -> "CraftProjectFileResponse":
        return cls(
            id=row.id,
            project_id=row.project_id,
            path=row.path,
            name=row.path.rsplit("/", 1)[-1],
            mime_type=row.mime_type,
            size_bytes=row.size_bytes,
            content_hash=row.content_hash,
            source=row.source,
            produced_by_session_id=row.produced_by_session_id,
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class CraftProjectSessionResponse(BaseModel):
    id: UUID
    name: str | None
    status: BuildSessionStatus
    created_at: datetime
    last_activity_at: datetime

    @classmethod
    def from_model(cls, session: BuildSession) -> "CraftProjectSessionResponse":
        return cls(
            id=session.id,
            name=session.name,
            status=session.status,
            created_at=session.created_at,
            last_activity_at=session.last_activity_at,
        )


class CraftProjectResponse(BaseModel):
    id: UUID
    name: str
    description: str
    instructions: str | None
    file_count: int
    session_count: int
    created_at: datetime
    updated_at: datetime
    files: list[CraftProjectFileResponse] | None = None
    sessions: list[CraftProjectSessionResponse] | None = None

    @classmethod
    def from_model(
        cls,
        project: CraftProject,
        *,
        file_count: int,
        session_count: int,
        files: list[CraftProjectFile] | None = None,
        sessions: list[BuildSession] | None = None,
    ) -> "CraftProjectResponse":
        return cls(
            id=project.id,
            name=project.name,
            description=project.description,
            instructions=project.instructions,
            file_count=file_count,
            session_count=session_count,
            created_at=project.created_at,
            updated_at=project.updated_at,
            files=(
                [CraftProjectFileResponse.from_model(row) for row in files]
                if files is not None
                else None
            ),
            sessions=(
                [CraftProjectSessionResponse.from_model(row) for row in sessions]
                if sessions is not None
                else None
            ),
        )


class CraftProjectListResponse(BaseModel):
    projects: list[CraftProjectResponse]


class CraftProjectCreateSessionRequest(BaseModel):
    name: str | None = None
    headless: bool = False
