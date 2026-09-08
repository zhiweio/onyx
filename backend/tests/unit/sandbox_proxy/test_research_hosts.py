from onyx.sandbox_proxy.research_hosts import (
    RESEARCH_USER_AGENT,
    apply_research_user_agent,
    is_public_research_host,
)


def test_known_scientific_hosts() -> None:
    assert is_public_research_host("api.fda.gov")
    assert is_public_research_host("API.FDA.GOV.")
    assert is_public_research_host("eutils.ncbi.nlm.nih.gov")
    assert is_public_research_host("clinicaltrials.gov")
    assert is_public_research_host("www.ebi.ac.uk")
    assert is_public_research_host("www.nmpa.gov.cn")
    assert is_public_research_host("kns.cnki.net")
    assert is_public_research_host("patentscope.wipo.int")
    assert is_public_research_host("www.cochranelibrary.com")
    assert not is_public_research_host("evil.fda.gov.attacker.example")
    assert not is_public_research_host("evil.cnki.net.attacker.example")
    assert not is_public_research_host("10.0.0.8")
    assert not is_public_research_host("example.com")


def test_apply_research_user_agent_replaces_browser_ua() -> None:
    headers: dict[str, str] = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/143.0.0.0"
    }
    assert apply_research_user_agent(headers, "api.fda.gov") is True
    assert headers["User-Agent"] == RESEARCH_USER_AGENT


def test_apply_research_user_agent_skips_unrelated_hosts() -> None:
    headers: dict[str, str] = {"User-Agent": "Mozilla/5.0"}
    assert apply_research_user_agent(headers, "example.com") is False
    assert headers["User-Agent"] == "Mozilla/5.0"


def test_apply_research_user_agent_keeps_identifying_ua() -> None:
    headers: dict[str, str] = {"User-Agent": "MyResearchBot/2.0"}
    assert apply_research_user_agent(headers, "api.fda.gov") is False
    assert headers["User-Agent"] == "MyResearchBot/2.0"
