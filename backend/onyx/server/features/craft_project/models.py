from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from onyx.db.enums import (
    BuildSessionStatus,
    CraftJobStatus,
    CraftProjectFileSource,
    SandboxStatus,
    SessionOrigin,
)
from onyx.db.models import BuildSession, CraftProject, CraftProjectFile, Sandbox
from onyx.server.features.craft_project.session_status import (
    project_session_activity_status,
)


class CraftProjectUpsertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    instructions: str | None = None
    user_group_id: int | None = None


class CraftProjectPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    instructions: str | None = None
    user_group_id: int | None = None


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
    origin: SessionOrigin
    job_status: CraftJobStatus | None = None
    has_active_turn: bool = False
    created_at: datetime
    last_activity_at: datetime

    @classmethod
    def from_model(
        cls,
        session: BuildSession,
        *,
        job_status: CraftJobStatus | None = None,
        has_active_turn: bool = False,
    ) -> "CraftProjectSessionResponse":
        return cls(
            id=session.id,
            name=session.name,
            status=project_session_activity_status(
                session.status,
                job_status=job_status,
                has_active_turn=has_active_turn,
            ),
            origin=session.origin,
            job_status=job_status,
            has_active_turn=has_active_turn,
            created_at=session.created_at,
            last_activity_at=session.last_activity_at,
        )


class CraftProjectSandboxResponse(BaseModel):
    id: UUID
    status: SandboxStatus
    last_heartbeat: datetime | None
    created_at: datetime

    @classmethod
    def from_model(cls, sandbox: Sandbox) -> "CraftProjectSandboxResponse":
        return cls(
            id=sandbox.id,
            status=sandbox.status,
            last_heartbeat=sandbox.last_heartbeat,
            created_at=sandbox.created_at,
        )


class CraftProjectResponse(BaseModel):
    id: UUID
    name: str
    description: str
    instructions: str | None
    user_group_id: int | None = None
    file_count: int
    session_count: int
    created_at: datetime
    updated_at: datetime
    files: list[CraftProjectFileResponse] | None = None
    sessions: list[CraftProjectSessionResponse] | None = None
    sandbox: CraftProjectSandboxResponse | None = None

    @classmethod
    def from_model(
        cls,
        project: CraftProject,
        *,
        file_count: int,
        session_count: int,
        files: list[CraftProjectFile] | None = None,
        sessions: list[BuildSession] | None = None,
        job_statuses: dict[UUID, CraftJobStatus] | None = None,
        active_turns: set[UUID] | None = None,
        sandbox: Sandbox | None = None,
    ) -> "CraftProjectResponse":
        statuses = job_statuses or {}
        turns = active_turns or set()
        return cls(
            id=project.id,
            name=project.name,
            description=project.description,
            instructions=project.instructions,
            user_group_id=project.user_group_id,
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
                [
                    CraftProjectSessionResponse.from_model(
                        row,
                        job_status=statuses.get(row.id),
                        has_active_turn=row.id in turns,
                    )
                    for row in sessions
                ]
                if sessions is not None
                else None
            ),
            sandbox=(
                CraftProjectSandboxResponse.from_model(sandbox)
                if sandbox is not None
                else None
            ),
        )


class CraftProjectListResponse(BaseModel):
    projects: list[CraftProjectResponse]


class CraftProjectCreateSessionRequest(BaseModel):
    name: str | None = None
    headless: bool = False


class CraftProjectSandboxResetRequest(BaseModel):
    migrate_outputs: bool = False
