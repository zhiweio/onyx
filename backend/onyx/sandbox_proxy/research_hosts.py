"""Public research hosts the sandbox may fetch, and the User-Agent they get.

Public APIs often reject anonymous browser User-Agents from datacenter IPs
(HTTP 403). The egress proxy replaces a missing or Mozilla User-Agent on these
hosts with an identifying research agent string.

Known research hostnames also skip the fail-closed DNS deny in
``destination_is_blocked``: a transient resolver error must not look like
an internal-network block. If DNS returns a real internal IP, the destination
check still denies.

Add a host here when a built-in skill documents it — not for one test prompt.
Package registries (PyPI, npm) are off-catalog and do not need this list.
"""

from __future__ import annotations

from typing import Any

RESEARCH_USER_AGENT = "Onyx-Craft/1.0 (scientific-research; +https://onyx.app)"

# Suffixes are suffix-anchored (host == suffix[1:] or host.endswith(suffix)).
_RESEARCH_SUFFIXES = (
    ".fda.gov",
    ".nih.gov",
    ".clinicaltrials.gov",
    ".who.int",
    ".nmpa.gov.cn",
    ".cde.org.cn",
    ".cnki.net",
    ".wanfangdata.com.cn",
    ".wipo.int",
    ".cochrane.org",
)

_RESEARCH_HOSTS = frozenset(
    {
        "api.crossref.org",
        "api.openalex.org",
        "api.semanticscholar.org",
        "arxiv.org",
        "clinicaltrials.gov",
        "clinicaltrialsregister.eu",
        "doi.org",
        "europepmc.org",
        "export.arxiv.org",
        "patents.google.com",
        "pubmed.ncbi.nlm.nih.gov",
        "rest.uniprot.org",
        "worldwide.espacenet.com",
        "www.clinicaltrials.gov",
        "www.clinicaltrialsregister.eu",
        "www.ebi.ac.uk",
        "www.ema.europa.eu",
        "www.europepmc.org",
        "www.uniprot.org",
        "www.uspto.gov",
        "developer.uspto.gov",
        "api.biorxiv.org",
        "api.medrxiv.org",
        "chinadrugtrials.org.cn",
        "www.chinadrugtrials.org.cn",
        "www.nmpa.gov.cn",
        "www.cde.org.cn",
        "kns.cnki.net",
        "www.cnki.net",
        "www.wanfangdata.com.cn",
        "patentscope.wipo.int",
        "www.wipo.int",
        "www.cochranelibrary.com",
        "trialsearch.who.int",
    }
)


def is_public_research_host(host: str) -> bool:
    """True if ``host`` is a known public scientific / regulatory API."""
    normalized = (host or "").strip().lower().rstrip(".")
    if not normalized:
        return False
    if normalized in _RESEARCH_HOSTS:
        return True
    for suffix in _RESEARCH_SUFFIXES:
        bare = suffix[1:]
        if normalized == bare or normalized.endswith(suffix):
            return True
    return False


def apply_research_user_agent(headers: Any, host: str) -> bool:
    """Set an identifying User-Agent on research hosts. Returns True if set."""
    if not is_public_research_host(host):
        return False
    current = str(headers.get("User-Agent") or "")
    if current and not current.startswith("Mozilla/"):
        return False
    headers["User-Agent"] = RESEARCH_USER_AGENT
    return True
