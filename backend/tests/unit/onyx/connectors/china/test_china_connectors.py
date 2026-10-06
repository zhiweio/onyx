"""Unit tests for the China workplace connectors (mocked HTTP)."""

from typing import Any

import pytest
from requests_mock import Mocker as RequestsMocker

from onyx.configs.constants import DocumentSource
from onyx.connectors.china_common import AppTokenManager, paginated
from onyx.connectors.dingtalk.connector import DingTalkConnector
from onyx.connectors.dingtalk_drive.connector import DingTalkDriveConnector
from onyx.connectors.dingtalk_todo.connector import DingTalkTodoConnector
from onyx.connectors.exceptions import (
    CredentialInvalidError,
    InsufficientPermissionsError,
)
from onyx.connectors.feishu.connector import FeishuConnector
from onyx.connectors.feishu_drive.connector import FeishuDriveConnector
from onyx.connectors.feishu_im.connector import FeishuImConnector
from onyx.connectors.feishu_task.connector import FeishuTaskConnector
from onyx.connectors.models import (
    ConnectorMissingCredentialError,
    Document,
    SlimDocument,
)
from onyx.connectors.sap_odata.connector import SapODataConnector
from onyx.connectors.wecom.connector import WeComConnector
from onyx.connectors.wecom_approval.connector import WeComApprovalConnector
from onyx.connectors.wps365.connector import WPS365Connector

FEISHU_CREDS = {"feishu_app_id": "cli_x", "feishu_app_secret": "fs-secret"}
WECOM_CREDS = {"wecom_corp_id": "ww1", "wecom_corp_secret": "wm-secret"}
DING_CREDS = {"dingtalk_client_id": "dk", "dingtalk_client_secret": "ds"}
SAP_CREDS = {
    "sap_odata_base_url": "https://sap.example.com/sap/opu/odata/sap/API_SRV",
    "sap_odata_user": "sapuser",
    "sap_odata_password": "sappass",
    "sap_odata_entity_sets": "A_Suppliers,A_Invoices",
}


def test_token_manager_caches_until_expiry() -> None:
    calls: list[int] = []

    def fetch() -> tuple[str, int]:
        calls.append(1)
        return f"tok{len(calls)}", 3600

    mgr = AppTokenManager(fetch)
    assert mgr.get() == "tok1"
    assert mgr.get() == "tok1"  # cached
    mgr.invalidate()
    assert mgr.get() == "tok2"
    assert len(calls) == 2


def test_pagination_stops_without_token() -> None:
    pages: dict[str | None, tuple[list[dict[str, Any]], str | None]] = {
        None: ([{"k": "a"}, {"k": "b"}], "t1"),
        "t1": ([{"k": "c"}], None),
    }

    def fetch_page(
        token: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        return pages[token]

    assert list(paginated(fetch_page)) == [{"k": "a"}, {"k": "b"}, {"k": "c"}]


def test_pagination_caps_at_max_pages() -> None:
    def distinct_tokens(
        token: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        return [{"i": 1}], f"page-{(token or 'start')}"

    assert len(list(paginated(distinct_tokens, max_pages=5))) == 5


def test_pagination_stops_on_repeated_cursor() -> None:
    # Feishu keeps returning a page_token on the last page; a repeated
    # cursor must end iteration instead of looping until the API rejects it.
    def always_same(
        _token: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        return [{"i": 1}], "same"

    # page 1 yields items, the repeat is detected after serving page 2
    assert len(list(paginated(always_same))) == 2


def test_feishu_connector_indexes_wiki(requests_mock: RequestsMocker) -> None:
    requests_mock.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"code": 0, "tenant_access_token": "tt", "expire": 7200},
    )
    requests_mock.get(
        "https://open.feishu.cn/open-apis/wiki/v2/spaces",
        json={
            "code": 0,
            "data": {
                "items": [{"space_id": "sp1", "name": "财务知识库"}],
                "page_token": None,
            },
        },
    )
    requests_mock.get(
        "https://open.feishu.cn/open-apis/wiki/v2/spaces/sp1/nodes",
        json={
            "code": 0,
            "data": {
                "items": [
                    {
                        "obj_token": "doccn1",
                        "obj_type": "docx",
                        "title": "报销制度",
                        "node_edit_time": 1750000000,
                        "url": "https://feishu.cn/wiki/doccn1",
                    },
                    # non-docx node skipped
                    {"obj_token": "m1", "obj_type": "mindnote", "title": "x"},
                ]
            },
        },
    )
    requests_mock.get(
        "https://open.feishu.cn/open-apis/docx/v1/documents/doccn1/raw_content",
        json={"code": 0, "data": {"content": "<p>单笔报销上限 5000 元</p>"}},
    )

    connector = FeishuConnector()
    connector.load_credentials(FEISHU_CREDS)
    batches = list(connector.load_from_state())
    docs = [doc for batch in batches for doc in batch if isinstance(doc, Document)]
    assert len(docs) == 1
    doc = docs[0]
    assert doc.source is DocumentSource.FEISHU
    assert doc.id == "feishu-wiki-doccn1"
    assert "财务知识库/报销制度" in doc.semantic_identifier
    assert "5000" in doc.get_text_content()
    assert "<p>" not in doc.get_text_content()  # html stripped


def test_feishu_poll_window_filters(requests_mock: RequestsMocker) -> None:
    requests_mock.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"code": 0, "tenant_access_token": "tt", "expire": 7200},
    )
    requests_mock.get(
        "https://open.feishu.cn/open-apis/wiki/v2/spaces",
        json={"code": 0, "data": {"items": [{"space_id": "sp1", "name": "s"}]}},
    )
    requests_mock.get(
        "https://open.feishu.cn/open-apis/wiki/v2/spaces/sp1/nodes",
        json={
            "code": 0,
            "data": {
                "items": [
                    {
                        "obj_token": "old",
                        "obj_type": "docx",
                        "title": "旧",
                        "node_edit_time": 1000,
                    },
                    {
                        "obj_token": "new",
                        "obj_type": "docx",
                        "title": "新",
                        "node_edit_time": 2000,
                    },
                ]
            },
        },
    )
    requests_mock.get(
        "https://open.feishu.cn/open-apis/docx/v1/documents/new/raw_content",
        json={"code": 0, "data": {"content": "updated"}},
    )

    connector = FeishuConnector()
    connector.load_credentials(FEISHU_CREDS)
    docs = [
        d
        for b in connector.poll_source(start=1500, end=3000)
        for d in b
        if isinstance(d, Document)
    ]
    assert [d.id for d in docs] == ["feishu-wiki-new"]


def test_wecom_connector_indexes_text_files(requests_mock: RequestsMocker) -> None:
    requests_mock.get(
        "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
        json={"errcode": 0, "access_token": "ct", "expires_in": 7200},
    )
    requests_mock.post(
        "https://qyapi.weixin.qq.com/cgi-bin/wedrive/space_list",
        json={
            "errcode": 0,
            "space_list": [{"spaceid": "sp1", "space_name": "团队空间"}],
        },
    )

    def file_list_callback(request: Any, _context: Any) -> dict[str, Any]:
        if (request.json() or {}).get("fatherid") == "fold1":
            return {
                "errcode": 0,
                "file_list": [
                    {"fileid": "f2", "file_name": "附录.txt", "file_type": "3"}
                ],
            }
        return {
            "errcode": 0,
            "file_list": [
                {"fileid": "f1", "file_name": "制度.md", "file_type": "3"},
                {"fileid": "fold1", "file_name": "子目录", "file_type": "2"},
            ],
        }

    requests_mock.post(
        "https://qyapi.weixin.qq.com/cgi-bin/wedrive/file_list",
        json=file_list_callback,
    )

    def download_callback(request: Any, _context: Any) -> bytes:
        fileid = (request.json() or {}).get("fileid")
        return ("# 员工手册\n第一条" if fileid == "f1" else "附录内容").encode("utf-8")

    requests_mock.post(
        "https://qyapi.weixin.qq.com/cgi-bin/wedrive/file_download",
        content=download_callback,
    )

    connector = WeComConnector()
    connector.load_credentials(WECOM_CREDS)
    docs = [
        d for b in connector.load_from_state() for d in b if isinstance(d, Document)
    ]
    by_id = {d.id: d for d in docs}
    assert set(by_id) == {"wecom-wedrive-f1", "wecom-wedrive-f2"}
    assert "员工手册" in by_id["wecom-wedrive-f1"].get_text_content()
    assert by_id["wecom-wedrive-f1"].source is DocumentSource.WECOM
    assert by_id["wecom-wedrive-f1"].semantic_identifier == "团队空间/制度.md"
    assert by_id["wecom-wedrive-f2"].semantic_identifier == "团队空间/子目录/附录.txt"


def test_dingtalk_connector_indexes_knowledge_base(
    requests_mock: RequestsMocker,
) -> None:
    requests_mock.post(
        "https://api.dingtalk.com/v1.0/oauth2/accessToken",
        json={"accessToken": "dt", "expireIn": 7200},
    )
    requests_mock.get(
        "https://api.dingtalk.com/v2.0/wiki/workspaces",
        json={
            "workspaces": [
                {
                    "workspaceId": "kb1",
                    "name": "研发知识库",
                    "rootNodeId": "root1",
                }
            ]
        },
    )

    def nodes_callback(request: Any, _context: Any) -> dict[str, Any]:
        parent = request.qs.get("parentNodeId", [""])[0]
        if parent == "root1":
            return {
                "nodes": [{"nodeId": "fold1", "type": "FOLDER", "name": "指南"}],
                "nextToken": -1,
            }
        return {
            "nodes": [
                {
                    "nodeId": "n1",
                    "type": "FILE",
                    "name": "发布流程",
                    "modifiedTimestamp": 1750000000000,
                }
            ],
            "nextToken": -1,
        }

    requests_mock.get("https://api.dingtalk.com/v2.0/wiki/nodes", json=nodes_callback)
    requests_mock.get(
        "https://api.dingtalk.com/v1.0/doc/suites/documents/n1/blocks",
        json={
            "result": {
                "data": [
                    {
                        "blockType": "heading",
                        "heading": {"level": "heading-1", "text": "发布流程"},
                        "index": 0,
                    },
                    {
                        "blockType": "paragraph",
                        "paragraph": {"text": "1. 提交 MR"},
                        "index": 1,
                    },
                ]
            },
            "success": True,
        },
    )

    connector = DingTalkConnector(operator_union_id="op1")
    connector.load_credentials(DING_CREDS)
    docs = [
        d for b in connector.load_from_state() for d in b if isinstance(d, Document)
    ]
    assert len(docs) == 1
    assert docs[0].id == "dingtalk-kb-n1"
    assert docs[0].semantic_identifier == "研发知识库/发布流程"
    assert "# 发布流程" in docs[0].get_text_content()
    assert "1. 提交 MR" in docs[0].get_text_content()


def test_sap_odata_parses_v2_wrapper(requests_mock: RequestsMocker) -> None:
    requests_mock.get(
        "https://sap.example.com/sap/opu/odata/sap/API_SRV/A_Suppliers",
        json={
            "d": {
                "results": [
                    {"SupplierID": "S001", "CompanyName": "华信", "__metadata": {}},
                    {"SupplierID": "S002", "CompanyName": "国泰"},
                ]
            }
        },
    )
    requests_mock.get(
        "https://sap.example.com/sap/opu/odata/sap/API_SRV/A_Invoices",
        json={"d": {"results": [{"InvoiceID": "I1", "Amount": 1200.0}]}},
    )

    connector = SapODataConnector()
    connector.load_credentials(SAP_CREDS)
    docs = [
        d for b in connector.load_from_state() for d in b if isinstance(d, Document)
    ]
    by_id = {d.id: d for d in docs}
    assert set(by_id) == {"sap-odata-A_Suppliers", "sap-odata-A_Invoices"}
    assert "S001" in by_id["sap-odata-A_Suppliers"].get_text_content()
    assert "华信" in by_id["sap-odata-A_Suppliers"].get_text_content()
    assert "__metadata" not in by_id["sap-odata-A_Suppliers"].get_text_content()
    assert "1200" in by_id["sap-odata-A_Invoices"].get_text_content()


def test_sap_odata_entity_set_config_forms() -> None:
    connector = SapODataConnector()
    connector.load_credentials(
        {
            "sap_odata_base_url": "https://sap.example.com/srv",
            "sap_odata_apikey": "k",
            "sap_odata_entity_sets": '["A", "B"]',
        }
    )
    assert connector._entity_sets == ["A", "B"]
    connector2 = SapODataConnector()
    connector2.load_credentials(
        {
            "sap_odata_base_url": "https://sap.example.com/srv",
            "sap_odata_apikey": "k",
            "sap_odata_entity_sets": "A, B",
        }
    )
    assert connector2._entity_sets == ["A", "B"]


def _mock_feishu_wiki_tree(requests_mock: RequestsMocker) -> None:
    requests_mock.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"code": 0, "tenant_access_token": "tt", "expire": 7200},
    )
    requests_mock.get(
        "https://open.feishu.cn/open-apis/wiki/v2/spaces",
        json={
            "code": 0,
            "data": {"items": [{"space_id": "sp1", "name": "财务知识库"}]},
        },
    )
    requests_mock.get(
        "https://open.feishu.cn/open-apis/wiki/v2/spaces/sp1/nodes",
        json={
            "code": 0,
            "data": {
                "items": [
                    {
                        "obj_token": "doccn1",
                        "obj_type": "docx",
                        "title": "报销制度",
                        "node_edit_time": 1750000000,
                    },
                    {"obj_token": "m1", "obj_type": "mindnote", "title": "x"},
                ]
            },
        },
    )


def test_feishu_perm_sync_maps_members_to_access(
    requests_mock: RequestsMocker,
) -> None:
    _mock_feishu_wiki_tree(requests_mock)
    requests_mock.get(
        "https://open.feishu.cn/open-apis/drive/v1/permissions/doccn1/members",
        json={
            "code": 0,
            "data": {
                "members": [
                    {"member_type": "user", "member_id": "ou_zhang"},
                    {"member_type": "group", "member_id": "g_finance"},
                ]
            },
        },
    )
    requests_mock.get(
        "https://open.feishu.cn/open-apis/contact/v3/users/ou_zhang",
        json={
            "code": 0,
            "data": {"user": {"open_id": "ou_zhang", "email": "zhang@corp.cn"}},
        },
    )

    connector = FeishuConnector()
    connector.load_credentials(FEISHU_CREDS)
    batches = list(connector.retrieve_all_slim_docs_perm_sync())
    slims = [s for batch in batches for s in batch if isinstance(s, SlimDocument)]
    assert [s.id for s in slims] == ["feishu-wiki-doccn1"]
    access = slims[0].external_access
    assert access is not None
    assert access.external_user_emails == {"zhang@corp.cn"}
    assert access.external_user_group_ids == {"feishu:g_finance"}
    assert access.is_public is False


def test_feishu_perm_sync_unreadable_members_fall_back_private(
    requests_mock: RequestsMocker,
) -> None:
    _mock_feishu_wiki_tree(requests_mock)
    requests_mock.get(
        "https://open.feishu.cn/open-apis/drive/v1/permissions/doccn1/members",
        json={"code": 1770043, "msg": "no permission"},
    )

    connector = FeishuConnector()
    connector.load_credentials(FEISHU_CREDS)
    slims = [
        s
        for batch in connector.retrieve_all_slim_docs_perm_sync()
        for s in batch
        if isinstance(s, SlimDocument)
    ]
    access = slims[0].external_access
    assert access is not None
    assert access.external_user_emails == set()
    assert access.external_user_group_ids == set()
    assert access.is_public is False


def test_feishu_validate_requires_credentials() -> None:
    connector = FeishuConnector()
    with pytest.raises(ConnectorMissingCredentialError):
        connector.validate_connector_settings()


def test_feishu_validate_rejects_bad_credentials(
    requests_mock: RequestsMocker,
) -> None:
    requests_mock.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"code": 10003, "msg": "invalid app_id"},
        status_code=200,
    )
    connector = FeishuConnector()
    connector.load_credentials(FEISHU_CREDS)
    with pytest.raises(CredentialInvalidError):
        connector.validate_connector_settings()


def test_feishu_validate_requires_wiki_scope(
    requests_mock: RequestsMocker,
) -> None:
    requests_mock.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"code": 0, "tenant_access_token": "tt", "expire": 7200},
    )
    requests_mock.get(
        "https://open.feishu.cn/open-apis/wiki/v2/spaces",
        json={"code": 99991672, "msg": "permission denied"},
    )
    connector = FeishuConnector()
    connector.load_credentials(FEISHU_CREDS)
    with pytest.raises(InsufficientPermissionsError):
        connector.validate_connector_settings()


# ── feishu_drive ──────────────────────────────────────────────────────────

FEISHU_ROOT_META_URL = (
    "https://open.feishu.cn/open-apis/drive/explorer/v2/root_folder/meta"
)
FEISHU_FILES_URL = "https://open.feishu.cn/open-apis/drive/v1/files"


def _mock_feishu_drive_tree(requests_mock: RequestsMocker) -> None:
    requests_mock.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"code": 0, "tenant_access_token": "tt", "expire": 7200},
    )
    requests_mock.get(
        FEISHU_ROOT_META_URL,
        json={"code": 0, "data": {"root_folder_token": "fldroot"}},
    )

    def files_callback(request: Any, _context: Any) -> dict[str, Any]:
        folder = request.qs.get("folder_token", [""])[0]
        if folder == "fldroot":
            return {
                "code": 0,
                "data": {
                    "files": [
                        {
                            "type": "folder",
                            "token": "fldsub",
                            "name": "团队文档",
                            "url": "https://feishu.cn/drive/fldsub",
                        },
                        {
                            "type": "docx",
                            "token": "docdocx",
                            "name": "入职指南.docx",
                            "url": "https://feishu.cn/docx/docdocx",
                            "modified_time": 1750000000,
                        },
                        {
                            "type": "shortcut",
                            "token": "sc1",
                            "name": "快捷方式",
                            "modified_time": 1750000000,
                        },
                    ]
                },
            }
        if folder == "fldsub":
            return {
                "code": 0,
                "data": {
                    "files": [
                        {
                            "type": "sheet",
                            "token": "shsheet",
                            "name": "预算",
                            "url": "https://feishu.cn/sheet/shsheet",
                            "modified_time": 1750000100,
                        },
                        {
                            "type": "file",
                            "token": "medfile",
                            "name": "笔记.md",
                            "url": "https://feishu.cn/file/medfile",
                            "modified_time": 1750000200,
                        },
                    ]
                },
            }
        return {"code": 0, "data": {"files": []}}

    requests_mock.get(FEISHU_FILES_URL, json=files_callback)
    requests_mock.get(
        "https://open.feishu.cn/open-apis/docx/v1/documents/docdocx/raw_content",
        json={"code": 0, "data": {"content": "<p>入职第一天做什么</p>"}},
    )
    # sheet export: create task -> poll success -> download csv
    requests_mock.post(
        "https://open.feishu.cn/open-apis/drive/v1/export_tasks",
        json={"code": 0, "data": {"ticket": "tk1"}},
    )
    requests_mock.get(
        "https://open.feishu.cn/open-apis/drive/v1/export_tasks/tk1",
        json={
            "code": 0,
            "data": {"result": {"job_status": 0, "file_token": "expfile"}},
        },
    )
    requests_mock.get(
        "https://open.feishu.cn/open-apis/drive/v1/export_tasks/file/expfile/download",
        content="项目,金额\n服务器,100\n".encode("utf-8"),
    )
    requests_mock.get(
        "https://open.feishu.cn/open-apis/drive/v1/medias/medfile/download",
        content="# 笔记内容".encode("utf-8"),
    )


def test_feishu_drive_indexes_folders_and_exports(
    requests_mock: RequestsMocker,
) -> None:
    _mock_feishu_drive_tree(requests_mock)
    connector = FeishuDriveConnector()
    connector.load_credentials(FEISHU_CREDS)
    docs = [
        d for b in connector.load_from_state() for d in b if isinstance(d, Document)
    ]
    by_id = {d.id: d for d in docs}
    assert set(by_id) == {
        "feishu-drive-docdocx",
        "feishu-drive-shsheet",
        "feishu-drive-medfile",
    }
    docx_doc = by_id["feishu-drive-docdocx"]
    assert docx_doc.source is DocumentSource.FEISHU_DRIVE
    assert docx_doc.semantic_identifier == "入职指南.docx"
    assert by_id["feishu-drive-shsheet"].semantic_identifier == "团队文档/预算"
    assert by_id["feishu-drive-medfile"].semantic_identifier == "团队文档/笔记.md"
    assert "入职第一天做什么" in docx_doc.get_text_content()
    assert "<p>" not in docx_doc.get_text_content()
    assert "服务器" in by_id["feishu-drive-shsheet"].get_text_content()
    assert "笔记内容" in by_id["feishu-drive-medfile"].get_text_content()


def test_feishu_drive_perm_sync_and_fallback(requests_mock: RequestsMocker) -> None:
    _mock_feishu_drive_tree(requests_mock)
    # docx members readable, sheet members denied
    requests_mock.get(
        "https://open.feishu.cn/open-apis/drive/v1/permissions/docdocx/members",
        json={
            "code": 0,
            "data": {"members": [{"member_type": "user", "member_id": "ou_zhang"}]},
        },
    )
    requests_mock.get(
        "https://open.feishu.cn/open-apis/drive/v1/permissions/shsheet/members",
        json={"code": 1770043, "msg": "no permission"},
    )
    requests_mock.get(
        "https://open.feishu.cn/open-apis/contact/v3/users/ou_zhang",
        json={"code": 0, "data": {"user": {"email": "zhang@corp.cn"}}},
    )

    connector = FeishuDriveConnector()
    connector.load_credentials(FEISHU_CREDS)
    slims = [
        s
        for batch in connector.retrieve_all_slim_docs_perm_sync()
        for s in batch
        if isinstance(s, SlimDocument)
    ]
    by_id = {s.id: s for s in slims}
    access = by_id["feishu-drive-docdocx"].external_access
    assert access is not None
    assert access.external_user_emails == {"zhang@corp.cn"}
    fallback = by_id["feishu-drive-shsheet"].external_access
    assert fallback is not None
    assert fallback.external_user_emails == set()
    assert fallback.is_public is False


# ── feishu_im ─────────────────────────────────────────────────────────────

FEISHU_IM_CHATS_URL = "https://open.feishu.cn/open-apis/im/v1/chats"
FEISHU_IM_MESSAGES_URL = "https://open.feishu.cn/open-apis/im/v1/messages"


def _mock_feishu_im(requests_mock: RequestsMocker, create_time_ms: int) -> None:
    requests_mock.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"code": 0, "tenant_access_token": "tt", "expire": 7200},
    )
    requests_mock.get(
        FEISHU_IM_CHATS_URL,
        json={
            "code": 0,
            "data": {"items": [{"chat_id": "oc_chat1", "name": "研发大群"}]},
        },
    )

    def messages_callback(request: Any, _context: Any) -> dict[str, Any]:
        chat_id = request.qs.get("container_id", [""])[0]
        if chat_id != "oc_chat1":
            return {"code": 230001, "msg": "forbidden chat"}
        return {
            "code": 0,
            "data": {
                "items": [
                    {
                        "message_id": "om_1",
                        "msg_type": "text",
                        "create_time": str(create_time_ms),
                        "sender": {"id": "ou_li", "id_type": "open_id"},
                        "body": {"content": '{"text":"上线时间定了：周五"}'},
                    },
                    {
                        "message_id": "om_2",
                        "msg_type": "image",
                        "create_time": str(create_time_ms + 1000),
                        "sender": {"id": "ou_wang", "id_type": "open_id"},
                        "body": {"content": '{"image_key":"img_v2_x"}'},
                    },
                ]
            },
        }

    requests_mock.get(FEISHU_IM_MESSAGES_URL, json=messages_callback)
    requests_mock.get(
        "https://open.feishu.cn/open-apis/im/v1/chats/oc_chat1/members",
        json={
            "code": 0,
            "data": {"items": [{"member_id": "ou_li"}, {"member_id": "ou_wang"}]},
        },
    )
    requests_mock.get(
        "https://open.feishu.cn/open-apis/contact/v3/users/ou_li",
        json={"code": 0, "data": {"user": {"email": "li@corp.cn"}}},
    )
    requests_mock.get(
        "https://open.feishu.cn/open-apis/contact/v3/users/ou_wang",
        json={"code": 0, "data": {"user": {"email": ""}}},
    )


def test_feishu_im_indexes_chat_day_documents(requests_mock: RequestsMocker) -> None:
    from datetime import datetime, timedelta, timezone

    cst = timezone(timedelta(hours=8))
    now_ms = int(datetime.now(tz=cst).timestamp() * 1000)
    _mock_feishu_im(requests_mock, now_ms)
    connector = FeishuImConnector()
    connector.load_credentials(FEISHU_CREDS)
    docs = [
        d for b in connector.load_from_state() for d in b if isinstance(d, Document)
    ]
    assert len(docs) == 1
    doc = docs[0]
    day_key = datetime.now(tz=cst).strftime("%Y%m%d")
    assert doc.id == f"feishu-im-oc_chat1-{day_key}"
    assert doc.source is DocumentSource.FEISHU_IM
    assert doc.semantic_identifier.startswith("研发大群 2")
    text = doc.get_text_content()
    assert "li@corp.cn: 上线时间定了：周五" in text
    assert "[image]" in text  # attachment-only message keeps the flow readable


def test_feishu_im_perm_sync_private_fallback(requests_mock: RequestsMocker) -> None:
    from datetime import datetime, timedelta, timezone

    cst = timezone(timedelta(hours=8))
    now_ms = int(datetime.now(tz=cst).timestamp() * 1000)
    _mock_feishu_im(requests_mock, now_ms)
    # member list denied -> restrictive ACL for every emitted slim doc
    requests_mock.get(
        "https://open.feishu.cn/open-apis/im/v1/chats/oc_chat1/members",
        json={"code": 230002, "msg": "no member permission"},
    )
    connector = FeishuImConnector(history_days=2)
    connector.load_credentials(FEISHU_CREDS)
    slims = [
        s
        for batch in connector.retrieve_all_slim_docs_perm_sync()
        for s in batch
        if isinstance(s, SlimDocument)
    ]
    assert len(slims) == 3  # history_days + 1 date buckets
    access = slims[0].external_access
    assert access is not None
    assert access.external_user_emails == set()
    assert access.is_public is False


# ── feishu_task ───────────────────────────────────────────────────────────

FEISHU_TASKLISTS_URL = "https://open.feishu.cn/open-apis/task/v2/tasklists"
FEISHU_TASKLIST_TASKS_URL = (
    "https://open.feishu.cn/open-apis/task/v2/tasklists/tl1/tasks"
)


def _mock_feishu_tasks(requests_mock: RequestsMocker) -> None:
    requests_mock.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"code": 0, "tenant_access_token": "tt", "expire": 7200},
    )
    requests_mock.get(
        FEISHU_TASKLISTS_URL,
        json={"code": 0, "data": {"items": [{"guid": "tl1", "name": "发布排期"}]}},
    )
    requests_mock.get(
        FEISHU_TASKLIST_TASKS_URL,
        json={
            "code": 0,
            "data": {
                "items": [
                    {
                        "guid": "task1",
                        "summary": "发布 2.0",
                        "description": "完成回归测试",
                        "updated_at": 1750000000000,
                        "status": {"is_completed": False},
                        "members": [
                            {"id": "ou_li", "role": "executor"},
                            {"id": "ou_wang", "role": "follower"},
                        ],
                        "url": "https://feishu.cn/task/task1",
                    }
                ]
            },
        },
    )
    requests_mock.get(
        "https://open.feishu.cn/open-apis/contact/v3/users/ou_li",
        json={"code": 0, "data": {"user": {"email": "li@corp.cn"}}},
    )
    requests_mock.get(
        "https://open.feishu.cn/open-apis/contact/v3/users/ou_wang",
        json={"code": 0, "data": {"user": {"email": ""}}},
    )


def test_feishu_task_indexes_tasks_with_participant_acl(
    requests_mock: RequestsMocker,
) -> None:
    _mock_feishu_tasks(requests_mock)
    connector = FeishuTaskConnector()
    connector.load_credentials(FEISHU_CREDS)
    docs = [
        d for b in connector.load_from_state() for d in b if isinstance(d, Document)
    ]
    assert len(docs) == 1
    doc = docs[0]
    assert doc.id == "feishu-task-task1"
    assert doc.source is DocumentSource.FEISHU_TASK
    assert doc.semantic_identifier == "发布排期/发布 2.0"
    text = doc.get_text_content()
    assert "完成回归测试" in text
    assert "li@corp.cn" in text

    slims = [
        s
        for batch in connector.retrieve_all_slim_docs_perm_sync()
        for s in batch
        if isinstance(s, SlimDocument)
    ]
    assert [s.id for s in slims] == ["feishu-task-task1"]
    access = slims[0].external_access
    assert access is not None
    # ou_wang has no email on record; only resolvable emails enter the ACL
    assert access.external_user_emails == {"li@corp.cn"}
    assert access.is_public is False


# ── dingtalk_drive ────────────────────────────────────────────────────────

DING_SPACES_URL = "https://api.dingtalk.com/v1.0/drive/spaces"
DING_SPACE_FILES_URL = "https://api.dingtalk.com/v1.0/drive/spaces/org1/files"
DING_DOWNLOAD_URL_URL = (
    "https://api.dingtalk.com/v1.0/drive/spaces/org1/files/file1/downloadUrl"
)
DING_TODO_URL = "https://api.dingtalk.com/v1.0/todo/users/op1/tasks"


def _mock_dingtalk_token(requests_mock: RequestsMocker) -> None:
    requests_mock.post(
        "https://api.dingtalk.com/v1.0/oauth2/accessToken",
        json={"accessToken": "dt", "expireIn": 7200},
    )


def test_dingtalk_drive_indexes_org_space_files(
    requests_mock: RequestsMocker,
) -> None:
    _mock_dingtalk_token(requests_mock)
    requests_mock.get(
        DING_SPACES_URL,
        json={
            "spaces": [
                {"spaceId": "org1", "spaceName": "企业盘", "spaceType": "org"},
                {"spaceId": "per1", "spaceName": "个人盘", "spaceType": "personal"},
            ]
        },
    )

    def files_callback(request: Any, _context: Any) -> dict[str, Any]:
        if request.qs.get("parentid", ["0"])[0] == "fold1":
            return {"files": [{"id": "file2", "name": "规范.pdf", "type": "file"}]}
        return {
            "files": [
                {"id": "file1", "name": "说明.md", "type": "file"},
                {"id": "fold1", "name": "子目录", "type": "folder"},
            ]
        }

    requests_mock.get(DING_SPACE_FILES_URL, json=files_callback)
    requests_mock.get(
        DING_DOWNLOAD_URL_URL, json={"downloadUrl": "https://cdn.example.com/file1"}
    )
    requests_mock.get(
        "https://cdn.example.com/file1", content="# 钉盘说明".encode("utf-8")
    )
    # file2's download url resolves to a different CDN object
    requests_mock.get(
        "https://api.dingtalk.com/v1.0/drive/spaces/org1/files/file2/downloadUrl",
        json={"downloadUrl": "https://cdn.example.com/file2"},
    )
    requests_mock.get(
        "https://cdn.example.com/file2", content=b"%PDF-1.4\n\x00\x01\x02bin"
    )

    connector = DingTalkDriveConnector(operator_union_id="op1")
    connector.load_credentials(DING_CREDS)
    docs = [
        d for b in connector.load_from_state() for d in b if isinstance(d, Document)
    ]
    # personal space skipped; file2's bytes are a broken pdf -> no text -> skipped
    assert [d.id for d in docs] == ["dingtalk-drive-file1"]
    assert docs[0].source is DocumentSource.DINGTALK_DRIVE
    assert docs[0].semantic_identifier == "企业盘/说明.md"
    assert "钉盘说明" in docs[0].get_text_content()


def test_dingtalk_todo_indexes_operator_tasks(requests_mock: RequestsMocker) -> None:
    _mock_dingtalk_token(requests_mock)
    requests_mock.get(
        DING_TODO_URL,
        json={
            "taskList": [
                {
                    "taskId": "todo1",
                    "subject": "季度汇报",
                    "description": "准备 Q3 数据",
                    "detailUrl": {"url": "https://todo.dingtalk.com/todo1"},
                    "modifyTime": 1750000000,
                }
            ],
            "nextToken": -1,
        },
    )
    connector = DingTalkTodoConnector(operator_union_id="op1")
    connector.load_credentials(DING_CREDS)
    docs = [
        d for b in connector.load_from_state() for d in b if isinstance(d, Document)
    ]
    assert len(docs) == 1
    assert docs[0].id == "dingtalk-todo-todo1"
    assert docs[0].source is DocumentSource.DINGTALK_TODO
    assert "季度汇报" in docs[0].get_text_content()
    assert "准备 Q3 数据" in docs[0].get_text_content()


# ── wecom_approval ────────────────────────────────────────────────────────

WECOM_APPROVAL_INFO_URL = "https://qyapi.weixin.qq.com/cgi-bin/oa/getapprovalinfo"
WECOM_APPROVAL_DETAIL_URL = "https://qyapi.weixin.qq.com/cgi-bin/oa/getapprovaldetail"


def test_wecom_approval_indexes_requests(requests_mock: RequestsMocker) -> None:
    requests_mock.get(
        "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
        json={"errcode": 0, "access_token": "ct", "expires_in": 7200},
    )
    requests_mock.post(
        WECOM_APPROVAL_INFO_URL,
        json={"errcode": 0, "sp_no_list": ["202401010001"]},
    )
    requests_mock.post(
        WECOM_APPROVAL_DETAIL_URL,
        json={
            "errcode": 0,
            "info": {
                "sp_no": "202401010001",
                "sp_name": "报销申请",
                "template_id": "tpl1",
                "sp_status": 2,
                "apply_time": 1750000000,
                "applyader": {"userid": "zhangsan"},
                "apply_data": {
                    "controls": [
                        {
                            "control": "Money",
                            "title": "报销金额",
                            "value": {"text": "5000"},
                        }
                    ]
                },
            },
        },
    )
    connector = WeComApprovalConnector(history_days=30)
    connector.load_credentials(WECOM_CREDS)
    docs = [
        d for b in connector.load_from_state() for d in b if isinstance(d, Document)
    ]
    assert len(docs) == 1
    doc = docs[0]
    assert doc.id == "wecom-approval-202401010001"
    assert doc.source is DocumentSource.WECOM_APPROVAL
    text = doc.get_text_content()
    assert "报销申请" in text
    assert "已通过" in text
    assert "报销金额: 5000" in text


# ── wps365 ────────────────────────────────────────────────────────────────

WPS_FILES_URL = "https://open.wps.cn/openapi/file/wpscloud/v1/files"
WPS_DOWNLOAD_URL = "https://open.wps.cn/openapi/file/wpscloud/v1/files/wf1/download"


def test_wps365_parses_binary_downloads(requests_mock: RequestsMocker) -> None:
    requests_mock.post(
        "https://open.wps.cn/oauthapi/v3/inner/company/token",
        json={"company_access_token": "wt", "expires_in": 3600},
    )
    requests_mock.get(
        WPS_FILES_URL,
        json={
            "files": [{"file_id": "wf1", "name": "计划.md", "modify_time": 1750000000}]
        },
    )
    requests_mock.get(WPS_DOWNLOAD_URL, content="# WPS 计划正文".encode("utf-8"))

    connector = WPS365Connector()
    connector.load_credentials(
        {"wps365_client_id": "cid", "wps365_client_secret": "csec"}
    )
    docs = [
        d for b in connector.load_from_state() for d in b if isinstance(d, Document)
    ]
    assert len(docs) == 1
    doc = docs[0]
    assert doc.id == "wps365-wf1"
    assert doc.source is DocumentSource.WPS365
    assert "WPS 计划正文" in doc.get_text_content()
