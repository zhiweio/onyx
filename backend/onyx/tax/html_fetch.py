from html.parser import HTMLParser
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from onyx.utils.logger import setup_logger

logger = setup_logger()

DEFAULT_TIMEOUT_S = 12
USER_AGENT = (
    "OnyxTaxLiveQuery/1.0 (+https://github.com/onyx-dot-app/onyx; research client)"
)


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._href: str | None = None
        self._buf: list[str] = []
        self.anchors: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._href = href
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            title = " ".join("".join(self._buf).split())
            if title:
                self.anchors.append((self._href, title))
            self._href = None
            self._buf = []


def fetch_html(url: str, timeout_s: int = DEFAULT_TIMEOUT_S) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urlopen(request, timeout=timeout_s) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def extract_anchors(html: str, base_url: str) -> list[tuple[str, str]]:
    parser = _AnchorParser()
    parser.feed(html)
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for href, title in parser.anchors:
        if href.startswith("#") or href.startswith("javascript:"):
            continue
        absolute = urljoin(base_url, href)
        if absolute in seen:
            continue
        seen.add(absolute)
        out.append((absolute, title))
    return out


def fetch_title_and_text(url: str) -> tuple[str, str]:
    html = fetch_html(url)
    title = url
    lower = html.lower()
    start = lower.find("<title>")
    end = lower.find("</title>")
    if start != -1 and end > start:
        title = html[start + 7 : end].strip() or url
    text = " ".join(_strip_tags(html).split())
    return title, text[:8000]


def _strip_tags(html: str) -> str:
    class _Text(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.parts: list[str] = []

        def handle_data(self, data: str) -> None:
            self.parts.append(data)

    parser = _Text()
    parser.feed(html)
    return " ".join(parser.parts)
