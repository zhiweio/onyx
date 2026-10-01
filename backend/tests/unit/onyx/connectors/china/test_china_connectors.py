"""Unit tests for the China workplace connectors (mocked HTTP)."""

from typing import Any

from requests_mock import Mocker as RequestsMocker

from onyx.configs.constants import DocumentSource
from onyx.connectors.china_common import AppTokenManager, paginated
from onyx.connectors.dingtalk.connector import DingTalkConnector
from onyx.connectors.feishu.connector import FeishuConnector
from onyx.connectors.models import Document
from onyx.connectors.sap_odata.connector import SapODataConnector
from onyx.connectors.wecom.connector import WeComConnector

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
    def forever(
        _token: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        return [{"i": 1}], "same"

    assert len(list(paginated(forever, max_pages=5))) == 5


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
        "https://qyapi.weixin.qq.com/cgi-bin/wedrive/list",
        json={
            "errcode": 0,
            "file_list": {
                "file_list": [
                    {
                        "file_id": "f1",
                        "file_name": "制度.md",
                        "update_time": 1750000000,
                    },
                    {"file_id": "f2", "file_name": "logo.png"},
                ]
            },
        },
    )
    requests_mock.post(
        "https://qyapi.weixin.qq.com/cgi-bin/wedrive/download",
        json=None,
        status_code=200,
        text="# 员工手册\n第一条",
    )

    connector = WeComConnector()
    connector.load_credentials(WECOM_CREDS)
    docs = [
        d for b in connector.load_from_state() for d in b if isinstance(d, Document)
    ]
    assert len(docs) == 1
    assert docs[0].id == "wecom-wedrive-f1"
    assert "员工手册" in docs[0].get_text_content()
    assert docs[0].source is DocumentSource.WECOM


def test_dingtalk_connector_indexes_knowledge_base(
    requests_mock: RequestsMocker,
) -> None:
    requests_mock.post(
        "https://api.dingtalk.com/v1.0/oauth2/accessToken",
        json={"accessToken": "dt", "expireIn": 7200},
    )
    requests_mock.get(
        "https://api.dingtalk.com/v1.0/kb/orgs/knowledgeBases",
        json={
            "result": {
                "knowledgeBases": [{"knowledgeBaseId": "kb1", "name": "研发知识库"}]
            }
        },
    )
    requests_mock.get(
        "https://api.dingtalk.com/v1.0/kb/knowledgeBases/kb1/nodes",
        json={
            "nodes": [
                {"nodeId": "n1", "title": "发布流程", "editTime": 1750000000},
            ],
            "nextToken": -1,
        },
    )
    requests_mock.get(
        "https://api.dingtalk.com/v1.0/kb/nodes/n1/content",
        json={"content": "1. 提交 MR\n2. 评审"},
    )

    connector = DingTalkConnector()
    connector.load_credentials(DING_CREDS)
    docs = [
        d for b in connector.load_from_state() for d in b if isinstance(d, Document)
    ]
    assert len(docs) == 1
    assert docs[0].id == "dingtalk-kb-n1"
    assert docs[0].semantic_identifier == "研发知识库/发布流程"


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
