"""No-key DuckDuckGo research provider."""

from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
from urllib import error, parse, request

from .models import ResearchFetchedPage, ResearchSearchResult

_USER_AGENT = "Mozilla/5.0 (compatible; JonResearcher/0.1; +https://example.com/jon)"


def _unwrap_duckduckgo_url(url: str) -> str:
    parsed = parse.urlparse(url)
    is_duckduckgo_redirect = "duckduckgo.com" in parsed.netloc or parsed.path.startswith(
        "/l/"
    )
    if not is_duckduckgo_redirect:
        return url
    values = parse.parse_qs(parsed.query).get("uddg")
    if values:
        return parse.unquote(values[0])
    return url


class _DuckDuckGoHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[ResearchSearchResult] = []
        self._in_result_link = False
        self._in_snippet = False
        self._current_title: list[str] = []
        self._current_url = ""
        self._current_snippet: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        class_name = attr_map.get("class", "")
        if tag == "a" and "result__a" in class_name:
            self._flush()
            self._in_result_link = True
            self._current_url = _unwrap_duckduckgo_url(attr_map.get("href", ""))
            return
        if tag in {"a", "div"} and "result__snippet" in class_name:
            self._in_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_result_link:
            self._in_result_link = False
        if tag in {"a", "div"} and self._in_snippet:
            self._in_snippet = False
            self._flush()

    def handle_data(self, data: str) -> None:
        text = unescape(data).strip()
        if not text:
            return
        if self._in_result_link:
            self._current_title.append(text)
        elif self._in_snippet:
            self._current_snippet.append(text)

    def _flush(self) -> None:
        title = " ".join(self._current_title).strip()
        url = self._current_url.strip()
        if title and url and not any(item.url == url for item in self.results):
            self.results.append(
                ResearchSearchResult(
                    title=title,
                    url=url,
                    snippet=" ".join(self._current_snippet).strip(),
                    source="duckduckgo",
                )
            )
        self._current_title = []
        self._current_url = ""
        self._current_snippet = []

    def close(self) -> None:
        self._flush()
        super().close()


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._in_title = False
        self._skip_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = unescape(data).strip()
        if not text:
            return
        if self._in_title:
            self.title = f"{self.title} {text}".strip()
            return
        if not self._skip_depth:
            self._chunks.append(text)

    @property
    def text(self) -> str:
        normalized: list[str] = []
        previous = ""
        for chunk in self._chunks:
            if chunk != previous:
                normalized.append(chunk)
            previous = chunk
        return "\n".join(normalized)


class DuckDuckGoResearchProvider:
    name = "duckduckgo"
    requires_api_key = False

    def __init__(self, *, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def search(
        self,
        query: str,
        *,
        max_results: int = 5,
    ) -> list[ResearchSearchResult]:
        url = f"https://html.duckduckgo.com/html/?q={parse.quote_plus(query)}"
        response_text = _read_url(url, timeout=self.timeout)
        parser = _DuckDuckGoHTMLParser()
        parser.feed(response_text)
        parser.close()
        return parser.results[: max(1, min(int(max_results or 5), 10))]

    def fetch(
        self,
        url: str,
        *,
        max_chars: int = 6000,
    ) -> ResearchFetchedPage:
        response_text = _read_url(url, timeout=self.timeout)
        parser = _TextExtractor()
        parser.feed(response_text)
        parser.close()
        limit = max(500, min(int(max_chars or 6000), 20000))
        return ResearchFetchedPage(
            url=url,
            title=parser.title,
            text=parser.text[:limit],
            source="http",
        )


def _read_url(url: str, *, timeout: float) -> str:
    req = request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with request.urlopen(req, timeout=timeout) as response:
            content_type = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(content_type, errors="replace")
    except error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} for {url}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Research request failed for {url}: {exc.reason}") from exc
