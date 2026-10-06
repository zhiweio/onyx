import logging
from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi_users.password import PasswordHelper
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from onyx.db.engine.sql_engine import SqlEngine, get_session_with_current_tenant
from onyx.db.enums import AccountType
from onyx.db.models import (
    ChatSession,
    Connector,
    ConnectorCredentialPair,
    Credential,
    Credential__UserGroup,
    DocPermissionSyncAttempt,
    DocumentSet,
    DocumentSet__ConnectorCredentialPair,
    DocumentSet__User,
    DocumentSet__UserGroup,
    ExternalGroupPermissionSyncAttempt,
    IndexAttempt,
    IndexAttemptError,
    LLMModelFlow,
    LLMProvider,
    LLMProvider__UserGroup,
    MCPServer,
    MCPServer__UserGroup,
    ModelConfiguration,
    OAuthConfig,
    Persona,
    Persona__DocumentSet,
    Persona__User,
    Persona__UserGroup,
    Project__UserFile,
    TokenRateLimit__UserGroup,
    Tool,
    User,
    User__UserGroup,
    UserGroup,
    UserGroup__ConnectorCredentialPair,
    UserProject,
)
from onyx.db.users import assign_user_to_default_groups__no_commit
from onyx.file_store.file_store import get_default_file_store
from shared_configs.configs import POSTGRES_DEFAULT_SCHEMA_STANDARD_VALUE
from shared_configs.contextvars import CURRENT_TENANT_ID_CONTEXTVAR
from tests.external_dependency_unit.full_setup import ensure_full_deployment_setup

# Opt into the shared @pytest.mark.secrets / test_secrets infrastructure.
from tests.utils.pytest_secrets import (
    pytest_collection_modifyitems as pytest_collection_modifyitems,
)
from tests.utils.pytest_secrets import pytest_configure as pytest_configure
from tests.utils.pytest_secrets import test_secrets as test_secrets

# Email signature of users created by create_test_user below: an 8-char hex
# suffix before @example.com. Real signups and the e2e users do not match it,
# so the teardown sweep can key on it.
TEST_USER_EMAIL_PATTERN = r"_[0-9a-f]{8}@example\.com$"

# Name signature of user groups created by the suites here (craft, agent
# sharing, persona upsert tests): a fixed prefix plus a hex suffix.
TEST_GROUP_NAME_PATTERN = r"^(default|craft-group|agent-sharing-group)-[0-9a-f]+$"


@pytest.fixture(autouse=True)
def sweep_test_rows(db_session: Session) -> Generator[None, None, None]:
    """Tests here commit to the shared dev PostgreSQL, so rows persist after the
    run and leak into admin surfaces (tools, agents, MCP servers, OAuth configs,
    LLM providers, user groups, connectors, users). After each test, delete rows
    created through ``create_test_user`` and sweep the remaining reserved
    test-name patterns, then restore the default LLM flows the tests flipped."""
    yield

    # Snapshot the default LLM flows first: update_default_provider calls in
    # these suites overwrite the global default, which the UI then shows as a
    # different model until an admin re-picks it.
    default_flows = db_session.execute(
        select(
            LLMModelFlow.model_configuration_id, LLMModelFlow.llm_model_flow_type
        ).where(LLMModelFlow.is_default == True)  # noqa: E712
    ).all()

    leaked_user_ids = (
        select(User.id)
        .where(User.email.regexp_match(TEST_USER_EMAIL_PATTERN))
        .scalar_subquery()
    )
    owned_document_sets = (
        select(DocumentSet.id)
        .where(DocumentSet.user_id.in_(leaked_user_ids))
        .scalar_subquery()
    )
    owned_projects = (
        select(UserProject.id)
        .where(UserProject.user_id.in_(leaked_user_ids))
        .scalar_subquery()
    )
    db_session.execute(
        delete(DocumentSet__ConnectorCredentialPair).where(
            DocumentSet__ConnectorCredentialPair.document_set_id.in_(
                owned_document_sets
            )
        )
    )
    db_session.execute(
        delete(DocumentSet__User).where(
            DocumentSet__User.document_set_id.in_(owned_document_sets)
        )
    )
    db_session.execute(
        delete(DocumentSet__UserGroup).where(
            DocumentSet__UserGroup.document_set_id.in_(owned_document_sets)
        )
    )
    db_session.execute(
        delete(Persona__DocumentSet).where(
            Persona__DocumentSet.document_set_id.in_(owned_document_sets)
        )
    )
    db_session.execute(
        delete(DocumentSet).where(DocumentSet.id.in_(owned_document_sets))
    )
    db_session.execute(delete(Tool).where(Tool.user_id.in_(leaked_user_ids)))
    # Connector/credential chain: credential rows cascade with their owner, but
    # the join table and its attempt children have no ON DELETE CASCADE.
    leaked_credential_ids = (
        select(Credential.id)
        .where(Credential.user_id.in_(leaked_user_ids))
        .scalar_subquery()
    )
    owned_cc_pairs = (
        select(ConnectorCredentialPair.id)
        .where(ConnectorCredentialPair.credential_id.in_(leaked_credential_ids))
        .scalar_subquery()
    )
    owned_index_attempts = (
        select(IndexAttempt.id)
        .where(IndexAttempt.connector_credential_pair_id.in_(owned_cc_pairs))
        .scalar_subquery()
    )
    db_session.execute(
        delete(DocPermissionSyncAttempt).where(
            DocPermissionSyncAttempt.connector_credential_pair_id.in_(owned_cc_pairs)
        )
    )
    db_session.execute(
        delete(ExternalGroupPermissionSyncAttempt).where(
            ExternalGroupPermissionSyncAttempt.connector_credential_pair_id.in_(
                owned_cc_pairs
            )
        )
    )
    db_session.execute(
        delete(IndexAttemptError).where(
            IndexAttemptError.index_attempt_id.in_(owned_index_attempts)
        )
    )
    db_session.execute(
        delete(IndexAttempt).where(
            IndexAttempt.connector_credential_pair_id.in_(owned_cc_pairs)
        )
    )
    db_session.execute(
        delete(UserGroup__ConnectorCredentialPair).where(
            UserGroup__ConnectorCredentialPair.cc_pair_id.in_(owned_cc_pairs)
        )
    )
    db_session.execute(
        delete(ConnectorCredentialPair).where(
            ConnectorCredentialPair.id.in_(owned_cc_pairs)
        )
    )
    db_session.execute(
        delete(Credential__UserGroup).where(
            Credential__UserGroup.credential_id.in_(leaked_credential_ids)
        )
    )
    db_session.execute(
        delete(ChatSession).where(ChatSession.project_id.in_(owned_projects))
    )
    db_session.execute(
        delete(Project__UserFile).where(
            Project__UserFile.project_id.in_(owned_projects)
        )
    )
    db_session.execute(delete(UserProject).where(UserProject.id.in_(owned_projects)))
    # Soft-delete agents this suite created — by owner first, then by the
    # reserved name patterns that also cover rows orphaned by earlier runs.
    db_session.execute(
        update(Persona)
        .where(
            or_(
                Persona.user_id.in_(leaked_user_ids),
                Persona.name.like("agent-sharing-test-%"),
                Persona.name.like("Test Persona %"),
                Persona.name.like("Test MCP Persona %"),
                Persona.name.like("persona-%"),
                Persona.name.like("gate-%"),
                Persona.name.like("test_eager_load_persona_%"),
                Persona.name.in_(("eager-load-test", "edit-True")),
            )
        )
        .values(deleted=True)
    )
    db_session.execute(
        delete(Persona__User).where(Persona__User.user_id.in_(leaked_user_ids))
    )
    db_session.execute(
        delete(User__UserGroup).where(User__UserGroup.user_id.in_(leaked_user_ids))
    )
    db_session.execute(delete(User).where(User.id.in_(leaked_user_ids)))
    # Rows tests create inline rather than through the helpers, recognised by
    # their reserved name/URL patterns (example.com is never a real server URL
    # in this deployment, and the gateway prefixes test-registered servers).
    db_session.execute(
        delete(Tool).where(
            or_(
                Tool.name.like("editor-visibility-tool-%"),
                Tool.name.like("test_tool%"),
            )
        )
    )
    db_session.execute(
        delete(MCPServer).where(
            or_(
                MCPServer.server_url.like("%example.com%"),
                MCPServer.name.like("gw-%"),
                MCPServer.name.regexp_match(r"^deepwiki-[0-9a-f]+$"),
            )
        )
    )
    db_session.execute(
        delete(OAuthConfig).where(OAuthConfig.name.like("Test OAuth Config %"))
    )
    # Test LLM providers (llm/ suites, answer/craft conftests).
    test_provider_ids = (
        select(LLMProvider.id)
        .where(LLMProvider.name.like("test-provider%"))
        .scalar_subquery()
    )
    db_session.execute(
        delete(LLMProvider__UserGroup).where(
            LLMProvider__UserGroup.llm_provider_id.in_(test_provider_ids)
        )
    )
    db_session.execute(delete(LLMProvider).where(LLMProvider.id.in_(test_provider_ids)))
    # Test user groups and their join rows (no cascade on those).
    test_group_ids = (
        select(UserGroup.id)
        .where(UserGroup.name.regexp_match(TEST_GROUP_NAME_PATTERN))
        .scalar_subquery()
    )
    db_session.execute(
        delete(DocumentSet__UserGroup).where(
            DocumentSet__UserGroup.user_group_id.in_(test_group_ids)
        )
    )
    db_session.execute(
        delete(Credential__UserGroup).where(
            Credential__UserGroup.user_group_id.in_(test_group_ids)
        )
    )
    db_session.execute(
        delete(LLMProvider__UserGroup).where(
            LLMProvider__UserGroup.user_group_id.in_(test_group_ids)
        )
    )
    db_session.execute(
        delete(MCPServer__UserGroup).where(
            MCPServer__UserGroup.user_group_id.in_(test_group_ids)
        )
    )
    db_session.execute(
        delete(Persona__UserGroup).where(
            Persona__UserGroup.user_group_id.in_(test_group_ids)
        )
    )
    db_session.execute(
        delete(TokenRateLimit__UserGroup).where(
            TokenRateLimit__UserGroup.user_group_id.in_(test_group_ids)
        )
    )
    db_session.execute(
        delete(User__UserGroup).where(User__UserGroup.user_group_id.in_(test_group_ids))
    )
    db_session.execute(
        delete(UserGroup__ConnectorCredentialPair).where(
            UserGroup__ConnectorCredentialPair.user_group_id.in_(test_group_ids)
        )
    )
    db_session.execute(delete(UserGroup).where(UserGroup.id.in_(test_group_ids)))
    # Test connectors: the MOCK source ("Not Applicable" in the UI) only exists
    # for integration tests, and the helpers here name connectors "Test ...";
    # drop the whole connector→credential chain for both.
    mock_connectors = (
        select(Connector.id)
        .where(
            or_(
                Connector.source == "MOCK_CONNECTOR",
                Connector.name.ilike("test%"),
            )
        )
        .scalar_subquery()
    )
    mock_cc_pairs = (
        select(ConnectorCredentialPair.id)
        .where(ConnectorCredentialPair.connector_id.in_(mock_connectors))
        .scalar_subquery()
    )
    mock_credentials = (
        select(ConnectorCredentialPair.credential_id)
        .where(ConnectorCredentialPair.id.in_(mock_cc_pairs))
        .scalar_subquery()
    )
    mock_index_attempts = (
        select(IndexAttempt.id)
        .where(IndexAttempt.connector_credential_pair_id.in_(mock_cc_pairs))
        .scalar_subquery()
    )
    db_session.execute(
        delete(DocPermissionSyncAttempt).where(
            DocPermissionSyncAttempt.connector_credential_pair_id.in_(mock_cc_pairs)
        )
    )
    db_session.execute(
        delete(ExternalGroupPermissionSyncAttempt).where(
            ExternalGroupPermissionSyncAttempt.connector_credential_pair_id.in_(
                mock_cc_pairs
            )
        )
    )
    db_session.execute(
        delete(IndexAttemptError).where(
            IndexAttemptError.index_attempt_id.in_(mock_index_attempts)
        )
    )
    db_session.execute(
        delete(IndexAttempt).where(
            IndexAttempt.connector_credential_pair_id.in_(mock_cc_pairs)
        )
    )
    db_session.execute(
        delete(UserGroup__ConnectorCredentialPair).where(
            UserGroup__ConnectorCredentialPair.cc_pair_id.in_(mock_cc_pairs)
        )
    )
    db_session.execute(
        delete(ConnectorCredentialPair).where(
            ConnectorCredentialPair.id.in_(mock_cc_pairs)
        )
    )
    # Only drop credentials no surviving cc pair still references.
    db_session.execute(
        delete(Credential).where(
            Credential.id.in_(mock_credentials)
            & Credential.id.not_in(select(ConnectorCredentialPair.credential_id))
        )
    )
    db_session.execute(delete(Connector).where(Connector.id.in_(mock_connectors)))
    # Restore the defaults captured before the test, best effort — a flow whose
    # model configuration the test deleted cannot be restored.
    for model_configuration_id, flow_type in default_flows:
        model_config = db_session.scalar(
            select(ModelConfiguration).where(
                ModelConfiguration.id == model_configuration_id
            )
        )
        if model_config is None:
            continue
        flow_row = db_session.scalar(
            select(LLMModelFlow).where(
                LLMModelFlow.model_configuration_id == model_configuration_id,
                LLMModelFlow.llm_model_flow_type == flow_type,
            )
        )
        if flow_row is None:
            continue
        db_session.execute(
            update(LLMModelFlow)
            .where(
                LLMModelFlow.llm_model_flow_type == flow_type,
                LLMModelFlow.is_default == True,  # noqa: E712
            )
            .values(is_default=False)
        )
        flow_row.is_default = True
    db_session.commit()


@pytest.fixture
def audit_stream(caplog: pytest.LogCaptureFixture) -> Generator[None, None, None]:
    """``onyx.audit`` sets ``propagate=False``, so caplog's root handler never sees
    its records; hang caplog's handler below that barrier instead. Not autouse — it
    would feed audit records to tests that capture logs for other reasons.
    """
    audit_logger = logging.getLogger("onyx.audit")
    audit_logger.addHandler(caplog.handler)
    try:
        yield
    finally:
        audit_logger.removeHandler(caplog.handler)


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Create a database session for testing using the actual PostgreSQL database"""
    # Make sure that the db engine is initialized before any tests are run
    SqlEngine.init_engine(
        pool_size=10,
        max_overflow=5,
    )
    with get_session_with_current_tenant() as session:
        yield session


@pytest.fixture(scope="session")
def full_deployment_setup() -> Generator[None, None, None]:
    """Optional fixture to perform full deployment-like setup on demand.

    Import and call tests.external_dependency_unit.startup.full_setup.ensure_full_deployment_setup
    to initialize Postgres defaults, Vespa indices, and seed initial docs.
    """
    ensure_full_deployment_setup()
    yield


@pytest.fixture(scope="function")
def tenant_context() -> Generator[None, None, None]:
    """Set up tenant context for testing"""
    # Set the tenant context for the test
    token = CURRENT_TENANT_ID_CONTEXTVAR.set(POSTGRES_DEFAULT_SCHEMA_STANDARD_VALUE)
    try:
        yield
    finally:
        # Reset the tenant context after the test
        CURRENT_TENANT_ID_CONTEXTVAR.reset(token)


def create_test_user(
    db_session: Session,
    email_prefix: str,
    account_type: AccountType = AccountType.STANDARD,
    is_admin: bool = False,
    assign_default_group: bool = True,
) -> User:
    """Create a test user. Assigns the seeded Basic
    (or Admin if is_admin=True) default group and populates
    effective_permissions; skipped for BOT/EXT_PERM_USER/ANONYMOUS.

    Pass assign_default_group=False for the group-less case — a service account
    in no group is what the old LIMITED role described."""
    unique_email = f"{email_prefix}_{uuid4().hex[:8]}@example.com"

    password_helper = PasswordHelper()
    password = password_helper.generate()
    hashed_password = password_helper.hash(password)

    user = User(
        id=uuid4(),
        email=unique_email,
        hashed_password=hashed_password,
        is_active=True,
        is_superuser=False,
        is_verified=True,
        account_type=account_type,
    )
    db_session.add(user)
    db_session.flush()

    if assign_default_group:
        assign_user_to_default_groups__no_commit(db_session, user, is_admin=is_admin)

    db_session.commit()
    db_session.refresh(user)
    return user


def delete_test_user(db_session: Session, *users: User) -> None:
    """Tear down users created by create_test_user. Clears default-group
    membership first — user__user_group.user_id has no ON DELETE CASCADE, so a
    bare delete(user) raises ForeignKeyViolation. Mirrors the production delete
    path in onyx.db.users."""
    user_ids = [user.id for user in users]
    db_session.execute(
        delete(User__UserGroup).where(User__UserGroup.user_id.in_(user_ids))
    )
    db_session.execute(delete(User).where(User.__table__.c.id.in_(user_ids)))


@pytest.fixture(scope="module")
def initialize_file_store() -> Generator[None, None, None]:
    """Initialize the file store for testing.

    Scoped to module level since file store initialization is idempotent
    and doesn't need to be reset between tests.
    """
    get_default_file_store().initialize()
    yield
