import argparse
import json as json_lib
import os
import re
from datetime import date, datetime
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from common.state import RetrievedDocument


try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()


DEFAULT_SEARCH_PROVIDER = "tavily"
DEFAULT_TAVILY_SEARCH_URL = "https://api.tavily.com/search"
DEFAULT_DUCKDUCKGO_SEARCH_URL = "https://duckduckgo.com/html/"
DEFAULT_USER_AGENT = "SKN27-MapleStory-WebRAG/0.1"
DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_MAX_RESULTS = 5
DEFAULT_MAX_CONTEXTS = 5
DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 150
FRESHNESS_HIGH_DAYS = 90
FRESHNESS_MEDIUM_DAYS = 365
DEFAULT_OFFICIAL_DOMAINS = (
    "maplestory.nexon.com",
    "openapi.nexon.com",
    "notice.nexon.com",
)
DEFAULT_COMMUNITY_DOMAINS = (
    "maple.inven.co.kr",
    "www.inven.co.kr",
)
NEXON_OFFICIAL_PATH_PREFIXES = (
    "/news",
    "/promotion/event",
    "/guide",
)
NEXON_COMMUNITY_PATH_PREFIXES = (
    "/community",
)
CONTENT_SELECTORS_TO_DROP = (
    "script",
    "style",
    "noscript",
    "header",
    "footer",
    "nav",
    "aside",
    "form",
    ".global_gnb",
    ".login_popup_wrap",
    ".event_bg",
    ".event_view_roll",
    ".sub_ev_dot",
    ".right_aside_new",
    ".con_title",
    ".qs_info",
    ".shortcut",
    ".side_board_info",
    ".side_board_wrap",
    ".side_banner_wrap",
    ".reply_wrap",
    ".bottom_txar_wrap",
    ".fix_toon_control",
    "#ajaxRefresh",
)
CONTENT_TAGS_TO_DROP = tuple(selector for selector in CONTENT_SELECTORS_TO_DROP if not selector.startswith((".", "#")))
CONTENT_CLASSES_TO_DROP = tuple(selector[1:] for selector in CONTENT_SELECTORS_TO_DROP if selector.startswith("."))
CONTENT_IDS_TO_DROP = tuple(selector[1:] for selector in CONTENT_SELECTORS_TO_DROP if selector.startswith("#"))
DOCUMENT_MAIN_SELECTORS = (
    ".contents_wrap",
    ".new_board_con",
    "main",
    "article",
    "#content",
    "#contents",
    ".content",
    ".contents",
)
OFFICIAL_DETAIL_PATH_PATTERNS = (
    r"^/News/Event/Ongoing/\d+$",
    r"^/News/Event/\d+$",
    r"^/News/Notice/\d+$",
    r"^/News/Update/\d+$",
    r"^/News/CashShop/\d+$",
    r"^/News/NoticeMapleBoard/\d+$",
    r"^/promotion/event/\d+/\d+/event\d+$",
)


class SimpleResponse:
    def __init__(self, text: str, status_code: int) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP request failed with status {self.status_code}")


class UrllibSession:
    def __init__(self, user_agent: str) -> None:
        self.headers = {"User-Agent": user_agent}

    def get(self, url: str, params: dict[str, Any] | None = None, timeout: int | None = None) -> SimpleResponse:
        query = urlencode(params or {})
        request_url = f"{url}?{query}" if query else url
        request = Request(request_url, headers=self.headers)
        try:
            with urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return SimpleResponse(response.read().decode(charset, errors="replace"), response.status)
        except HTTPError as exc:
            return SimpleResponse(exc.read().decode("utf-8", errors="replace"), exc.code)
        except URLError as exc:
            raise RuntimeError(f"HTTP request failed: {exc}") from exc

    def post(self, url: str, json: dict[str, Any] | None = None, timeout: int | None = None) -> SimpleResponse:
        request_body = json_lib.dumps(json or {}).encode("utf-8")
        headers = {**self.headers, "Content-Type": "application/json"}
        request = Request(url, data=request_body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return SimpleResponse(response.read().decode(charset, errors="replace"), response.status)
        except HTTPError as exc:
            return SimpleResponse(exc.read().decode("utf-8", errors="replace"), exc.code)
        except URLError as exc:
            raise RuntimeError(f"HTTP request failed: {exc}") from exc


class SearchResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self.current_href = ""
        self.current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr_map = {key: value or "" for key, value in attrs}
        classes = attr_map.get("class", "")
        if "result__a" in classes:
            self.current_href = attr_map.get("href", "")
            self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.current_href:
            self.current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.current_href:
            self.results.append({"url": self.current_href, "title": clean_text(" ".join(self.current_text))})
            self.current_href = ""
            self.current_text = []


class DocumentTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text_parts: list[str] = []
        self.title_parts: list[str] = []
        self.skip_depth = 0
        self.in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.skip_depth:
            self.skip_depth += 1
            return

        attr_map = {key: value or "" for key, value in attrs}
        class_names = set(attr_map.get("class", "").split())
        should_skip = (
            tag in CONTENT_TAGS_TO_DROP
            or attr_map.get("id") in CONTENT_IDS_TO_DROP
            or bool(class_names.intersection(CONTENT_CLASSES_TO_DROP))
        )
        if should_skip:
            self.skip_depth += 1
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag: str) -> None:
        if self.skip_depth:
            self.skip_depth -= 1
            return
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if not self.skip_depth and not self.in_title:
            self.text_parts.append(data)


def load_optional_beautiful_soup() -> Any | None:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None
    return BeautifulSoup


def create_http_session(user_agent: str) -> tuple[Any, Any]:
    try:
        import requests
    except ImportError:
        return UrllibSession(user_agent), Exception

    session = requests.Session()
    session.headers.update({"User-Agent": user_agent})
    return session, requests.RequestException


def get_env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def get_env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def get_official_domains() -> tuple[str, ...]:
    raw = os.environ.get("WEB_RAG_OFFICIAL_DOMAINS")
    if not raw:
        return DEFAULT_OFFICIAL_DOMAINS
    return tuple(domain.strip().lower() for domain in raw.split(",") if domain.strip())


def get_community_domains() -> tuple[str, ...]:
    raw = os.environ.get("WEB_RAG_COMMUNITY_DOMAINS")
    if not raw:
        return DEFAULT_COMMUNITY_DOMAINS
    return tuple(domain.strip().lower() for domain in raw.split(",") if domain.strip())


def as_domain_context(character_context: Any | None) -> dict[str, Any]:
    """Accepts a ProcessedCharacter-like object or mapping without importing domain.py."""
    if character_context is None:
        return {}
    if isinstance(character_context, dict):
        return character_context
    return {
        "character_name": getattr(character_context, "character_name", ""),
        "job_name": getattr(character_context, "job_name", ""),
        "level": getattr(character_context, "level", ""),
        "world_name": getattr(character_context, "world_name", ""),
    }


def build_search_query(
    question: str,
    character_context: Any | None = None,
    official_only: bool = True,
    official_domains: tuple[str, ...] | None = None,
    community_domains: tuple[str, ...] | None = None,
    include_site_filter: bool = True,
) -> str:
    domain_context = as_domain_context(character_context)
    query_parts = [question.strip(), "메이플스토리"]

    job_name = str(domain_context.get("job_name") or "").strip()
    level = str(domain_context.get("level") or "").strip()
    if job_name:
        query_parts.append(job_name)
    if level:
        query_parts.append(f"{level}레벨")

    if include_site_filter:
        domains = official_domains or get_official_domains()
        if not official_only:
            domains = domains + (community_domains or get_community_domains())

        site_filter = " OR ".join(f"site:{domain}" for domain in domains)
        query_parts.append(f"({site_filter})")

    return " ".join(part for part in query_parts if part)


def normalize_provider(provider: str | None) -> str:
    resolved = (provider or DEFAULT_SEARCH_PROVIDER).strip().lower()
    if resolved not in {"tavily", "duckduckgo"}:
        raise ValueError("WEB_RAG_SEARCH_PROVIDER must be 'tavily' or 'duckduckgo'")
    return resolved


def default_search_url(provider: str) -> str:
    if provider == "tavily":
        return DEFAULT_TAVILY_SEARCH_URL
    return DEFAULT_DUCKDUCKGO_SEARCH_URL


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            parsed = urlparse(target)

    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/") or parsed.path
    return parsed._replace(scheme=scheme, netloc=hostname, path=path, query="", fragment="").geturl()


def is_http_url(url: str) -> bool:
    return urlparse(url).scheme in {"http", "https"}


def domain_matches(url: str, allowed_domains: tuple[str, ...]) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in allowed_domains)


def path_starts_with(url: str, prefixes: tuple[str, ...]) -> bool:
    path = urlparse(url).path.lower()
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in prefixes)


def is_nexon_community_url(url: str) -> bool:
    parsed = urlparse(url)
    return (parsed.hostname or "").lower() == "maplestory.nexon.com" and path_starts_with(
        url,
        NEXON_COMMUNITY_PATH_PREFIXES,
    )


def is_nexon_official_content_url(url: str) -> bool:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if hostname != "maplestory.nexon.com":
        return domain_matches(url, DEFAULT_OFFICIAL_DOMAINS)
    return path_starts_with(url, NEXON_OFFICIAL_PATH_PREFIXES)


def is_allowed_result_url(url: str, allowed_domains: tuple[str, ...], official_only: bool) -> bool:
    if not domain_matches(url, allowed_domains):
        return False
    if official_only and is_nexon_community_url(url):
        return False
    return True


def source_reliability(url: str, official_domains: tuple[str, ...]) -> str:
    if domain_matches(url, official_domains) and is_nexon_official_content_url(url):
        return "HIGH"
    return "MEDIUM"


def parse_date_value(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None

    normalized = text.replace(".", "-").replace("/", "-")
    patterns = (
        r"(?P<year>20\d{2})-(?P<month>\d{1,2})-(?P<day>\d{1,2})",
        r"(?P<year>20\d{2})\s*년\s*(?P<month>\d{1,2})\s*월\s*(?P<day>\d{1,2})\s*일",
        r"(?P<year>20\d{2})(?P<month>\d{2})(?P<day>\d{2})",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        try:
            return date(
                int(match.group("year")),
                int(match.group("month")),
                int(match.group("day")),
            )
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def extract_published_at(*values: Any) -> str | None:
    for value in values:
        parsed = parse_date_value(value)
        if parsed:
            return parsed.isoformat()
    return None


def source_freshness(published_at: str | None, today: date | None = None) -> str:
    parsed = parse_date_value(published_at)
    if not parsed:
        return "UNKNOWN"
    current_date = today or date.today()
    age_days = (current_date - parsed).days
    if age_days < 0:
        return "HIGH"
    if age_days <= FRESHNESS_HIGH_DAYS:
        return "HIGH"
    if age_days <= FRESHNESS_MEDIUM_DAYS:
        return "MEDIUM"
    return "LOW"


def tokenize(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z0-9가-힣]+", text) if len(token) > 1}


def merge_search_results(
    search_results: list[dict[str, Any]],
    max_results: int,
) -> list[dict[str, Any]]:
    merged = []
    seen_urls = set()
    index_by_url = {}
    for result in sorted(search_results, key=search_result_rank, reverse=True):
        url = normalize_url(result.get("url", ""))
        if not url:
            continue
        if url in seen_urls:
            existing = merged[index_by_url[url]]
            if result.get("content") and not existing.get("content"):
                existing["content"] = result["content"]
            if result.get("tavily_score") and not existing.get("tavily_score"):
                existing["tavily_score"] = result["tavily_score"]
            if result.get("published_at") and not existing.get("published_at"):
                existing["published_at"] = result["published_at"]
                existing["freshness"] = result.get("freshness", source_freshness(result["published_at"]))
            continue
        seen_urls.add(url)
        result = {**result, "url": url}
        index_by_url[url] = len(merged)
        merged.append(result)
        if len(merged) >= max_results:
            break
    return merged


def search_result_rank(result: dict[str, Any]) -> tuple[bool, bool, float]:
    url = normalize_url(str(result.get("url", "")))
    return (
        source_reliability(url, DEFAULT_OFFICIAL_DOMAINS) == "HIGH",
        is_official_detail_url(url),
        float(result.get("tavily_score") or 0),
    )


def is_official_detail_url(url: str) -> bool:
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() != "maplestory.nexon.com":
        return False
    return any(re.match(pattern, parsed.path, flags=re.IGNORECASE) for pattern in OFFICIAL_DETAIL_PATH_PATTERNS)


def clean_text(text: str) -> str:
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_search_results(html: str, beautiful_soup: Any | None) -> list[dict[str, str]]:
    if beautiful_soup:
        soup = beautiful_soup(html, "html.parser")
        return [
            {"url": anchor.get("href", ""), "title": clean_text(anchor.get_text(" "))}
            for anchor in soup.select("a.result__a")
        ]

    parser = SearchResultParser()
    parser.feed(html)
    return parser.results


def parse_document(html: str, fallback_title: str, beautiful_soup: Any | None) -> dict[str, str]:
    if beautiful_soup:
        soup = beautiful_soup(html, "html.parser")
        for selector in CONTENT_SELECTORS_TO_DROP:
            for tag in soup.select(selector):
                tag.decompose()
        title = extract_document_title(soup, fallback_title)
        text = extract_document_text(soup)
        return {"title": title, "text": text}

    parser = DocumentTextParser()
    parser.feed(extract_fallback_main_html(html))
    title = (
        extract_fallback_document_title(html)
        or clean_text(" ".join(parser.title_parts))
        or fallback_title
    )
    text = clean_text(" ".join(parser.text_parts))
    return {"title": title, "text": text}


def extract_document_title(soup: Any, fallback_title: str) -> str:
    for selector in (".qs_title span", "h1", "title"):
        tag = soup.select_one(selector)
        if tag:
            title = clean_text(tag.get_text(" "))
            if title:
                return title
    return fallback_title


def extract_document_text(soup: Any) -> str:
    for selector in DOCUMENT_MAIN_SELECTORS:
        tag = soup.select_one(selector)
        if not tag:
            continue
        text = clean_text(" ".join(collect_content_text(tag)))
        if text:
            return text
    return clean_text(" ".join(collect_content_text(soup)))


def collect_content_text(tag: Any) -> list[str]:
    text_parts = [tag.get_text(" ")]
    for image in tag.select("img[alt]"):
        alt_text = clean_text(image.get("alt", ""))
        if alt_text:
            text_parts.append(alt_text)
    return text_parts


def extract_fallback_main_html(html: str) -> str:
    match = re.search(
        r"<[^>]+class=[\"'][^\"']*(?:contents_wrap|new_board_con)[^\"']*[\"'][^>]*>",
        html,
        flags=re.IGNORECASE,
    )
    if not match:
        return html

    start = match.start()
    lower_html = html.lower()
    end_markers = (
        '<div class="event_view_roll"',
        '<div class="right_aside_new"',
        '<div class="event_bg"',
        '<div id="footer"',
    )
    end_positions = [
        lower_html.find(marker, start + 1)
        for marker in end_markers
        if lower_html.find(marker, start + 1) != -1
    ]
    end = min(end_positions) if end_positions else len(html)
    return html[start:end]


def extract_fallback_document_title(html: str) -> str:
    match = re.search(
        r"<p[^>]+class=[\"'][^\"']*qs_title[^\"']*[\"'][^>]*>.*?<span[^>]*>(.*?)</span>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ""
    return clean_text(re.sub(r"<[^>]+>", " ", match.group(1)))


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    if not text:
        return []
    chunks = []
    start = 0
    text_length = len(text)
    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == text_length:
            break
        start = max(end - chunk_overlap, start + 1)
    return chunks


def score_text(query: str, text: str) -> float:
    query_tokens = tokenize(query)
    if not query_tokens:
        return 0.0
    text_tokens = tokenize(text)
    overlap = query_tokens.intersection(text_tokens)
    return len(overlap) / len(query_tokens)


class WebSearchRAG:
    """First-pass Web Search RAG retriever for MapleStory project sources."""

    def __init__(
        self,
        search_provider: str | None = None,
        search_url: str | None = None,
        user_agent: str | None = None,
        timeout_seconds: int | None = None,
        official_domains: tuple[str, ...] | None = None,
        community_domains: tuple[str, ...] | None = None,
    ) -> None:
        requested_provider = normalize_provider(search_provider or os.environ.get("WEB_RAG_SEARCH_PROVIDER"))
        self.tavily_api_key = os.environ.get("TAVILY_API_KEY", "").strip()
        self.search_provider = (
            "duckduckgo"
            if requested_provider == "tavily" and not self.tavily_api_key
            else requested_provider
        )
        configured_search_url = search_url or os.environ.get("WEB_RAG_SEARCH_URL", "").strip()
        self.search_url = configured_search_url if configured_search_url and self.search_provider == requested_provider else default_search_url(self.search_provider)
        self.timeout_seconds = timeout_seconds or get_env_int("WEB_RAG_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
        self.official_domains = official_domains or get_official_domains()
        self.community_domains = community_domains or get_community_domains()
        self.tavily_search_depth = os.environ.get("TAVILY_SEARCH_DEPTH", "basic").strip().lower()
        self.tavily_include_raw_content = get_env_bool("TAVILY_INCLUDE_RAW_CONTENT", False)
        resolved_user_agent = user_agent or os.environ.get("WEB_RAG_USER_AGENT", DEFAULT_USER_AGENT)
        self.beautiful_soup = load_optional_beautiful_soup()
        self.session, self.request_exception = create_http_session(resolved_user_agent)
        if self.search_provider == "tavily" and self.tavily_api_key and hasattr(self.session, "headers"):
            self.session.headers.update({"Authorization": f"Bearer {self.tavily_api_key}"})

    def get_allowed_domains(self, official_only: bool) -> tuple[str, ...]:
        if official_only:
            return self.official_domains
        return self.official_domains + self.community_domains

    def search(
        self,
        question: str,
        character_context: Any | None = None,
        official_only: bool = True,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        max_results = max_results or get_env_int("WEB_RAG_MAX_RESULTS", DEFAULT_MAX_RESULTS)
        if self.search_provider == "tavily":
            search_results = self.search_tavily(question, character_context, official_only, max_results)
        else:
            search_results = self.search_duckduckgo(question, character_context, official_only, max_results)
        return merge_search_results(search_results, max_results)

    def search_tavily(
        self,
        question: str,
        character_context: Any | None,
        official_only: bool,
        max_results: int,
    ) -> list[dict[str, Any]]:
        if not self.tavily_api_key:
            raise RuntimeError("TAVILY_API_KEY is required when WEB_RAG_SEARCH_PROVIDER=tavily")

        query = build_search_query(
            question,
            character_context,
            official_only,
            self.official_domains,
            self.community_domains,
            include_site_filter=False,
        )
        allowed_domains = self.get_allowed_domains(official_only)
        payload = {
            "query": query,
            "search_depth": self.tavily_search_depth,
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": self.tavily_include_raw_content,
            "include_domains": list(allowed_domains),
        }
        response = self.session.post(self.search_url, json=payload, timeout=self.timeout_seconds)
        response.raise_for_status()

        try:
            body = json_lib.loads(response.text)
        except json_lib.JSONDecodeError as exc:
            raise RuntimeError("Tavily search response was not valid JSON") from exc

        results = []
        seen_urls = set()
        for row in body.get("results", []):
            url = normalize_url(str(row.get("url", "")))
            title = clean_text(str(row.get("title", "")))
            content = clean_text(str(row.get("content") or ""))
            raw_content = clean_text(str(row.get("raw_content") or ""))
            published_at = extract_published_at(
                row.get("published_date"),
                row.get("published_at"),
                row.get("date"),
                row.get("url"),
                content,
                raw_content,
            )
            if not url or not title or not is_http_url(url) or url in seen_urls:
                continue
            if not is_allowed_result_url(url, allowed_domains, official_only):
                continue
            seen_urls.add(url)
            results.append(
                {
                    "title": title,
                    "url": url,
                    "query": query,
                    "content": raw_content or content,
                    "tavily_score": row.get("score"),
                    "reliability": source_reliability(url, self.official_domains),
                    "published_at": published_at,
                    "freshness": source_freshness(published_at),
                }
            )
            if len(results) >= max_results:
                break
        return results

    def search_duckduckgo(
        self,
        question: str,
        character_context: Any | None,
        official_only: bool,
        max_results: int,
    ) -> list[dict[str, Any]]:
        query = build_search_query(
            question,
            character_context,
            official_only,
            self.official_domains,
            self.community_domains,
        )
        response = self.session.get(self.search_url, params={"q": query}, timeout=self.timeout_seconds)
        response.raise_for_status()

        results = []
        seen_urls = set()
        allowed_domains = self.get_allowed_domains(official_only)
        for parsed_result in parse_search_results(response.text, self.beautiful_soup):
            url = normalize_url(parsed_result.get("url", ""))
            title = parsed_result.get("title", "")
            if not url or not title or not is_http_url(url) or url in seen_urls:
                continue
            if not is_allowed_result_url(url, allowed_domains, official_only):
                continue
            published_at = extract_published_at(url, title)
            seen_urls.add(url)
            results.append(
                {
                    "title": title,
                    "url": url,
                    "query": query,
                    "reliability": source_reliability(url, self.official_domains),
                    "published_at": published_at,
                    "freshness": source_freshness(published_at),
                }
            )
            if len(results) >= max_results:
                break
        return results

    def fetch_document(self, result: dict[str, Any]) -> dict[str, Any]:
        if result.get("content"):
            return {
                "title": result.get("title", ""),
                "url": result["url"],
                "text": result["content"],
                "query": result.get("query", ""),
                "reliability": result.get("reliability", source_reliability(result["url"], self.official_domains)),
                "published_at": result.get("published_at"),
                "freshness": result.get("freshness", source_freshness(result.get("published_at"))),
            }

        response = self.session.get(result["url"], timeout=self.timeout_seconds)
        response.raise_for_status()

        parsed_document = parse_document(response.text, result.get("title", ""), self.beautiful_soup)
        published_at = extract_published_at(result.get("published_at"), result["url"], parsed_document["text"])
        return {
            "title": parsed_document["title"] or result.get("title", ""),
            "url": result["url"],
            "text": parsed_document["text"],
            "query": result.get("query", ""),
            "reliability": result.get("reliability", source_reliability(result["url"], self.official_domains)),
            "published_at": published_at,
            "freshness": result.get("freshness", source_freshness(published_at)),
        }

    def retrieve(
        self,
        question: str,
        character_context: Any | None = None,
        official_only: bool = True,
        max_results: int | None = None,
        max_contexts: int | None = None,
    ) -> dict[str, Any]:
        max_contexts = max_contexts or get_env_int("WEB_RAG_MAX_CONTEXTS", DEFAULT_MAX_CONTEXTS)
        search_results = self.search(question, character_context, official_only, max_results)
        contexts = []
        documents = []

        for result in search_results:
            try:
                document = self.fetch_document(result)
            except self.request_exception:
                continue
            documents.append({key: document.get(key) for key in ("title", "url", "reliability", "freshness", "published_at")})
            for index, chunk in enumerate(chunk_text(document["text"])):
                contexts.append(
                    {
                        "title": document["title"],
                        "url": document["url"],
                        "chunk_index": index,
                        "content": chunk,
                        "score": score_text(question, chunk),
                        "reliability": document["reliability"],
                        "freshness": document.get("freshness", "UNKNOWN"),
                        "published_at": document.get("published_at"),
                    }
                )

        freshness_rank = {"HIGH": 3, "MEDIUM": 2, "UNKNOWN": 1, "LOW": 0}
        contexts.sort(
            key=lambda row: (
                row["score"],
                row["reliability"] == "HIGH",
                freshness_rank.get(row.get("freshness", "UNKNOWN"), 1),
            ),
            reverse=True,
        )
        return {
            "question": question,
            "search_provider": self.search_provider,
            "search_query": build_search_query(
                question,
                character_context,
                official_only,
                self.official_domains,
                self.community_domains,
                include_site_filter=self.search_provider != "tavily",
            ),
            "documents": documents,
            "contexts": contexts[:max_contexts],
        }


def format_contexts_for_prompt(retrieval_result: dict[str, Any]) -> str:
    lines = []
    for index, context in enumerate(retrieval_result.get("contexts", []), start=1):
        lines.append(
            "\n".join(
                [
                    f"[{index}] {context['title']}",
                    f"URL: {context['url']}",
                    f"Reliability: {context['reliability']}",
                    f"Freshness: {context.get('freshness', 'UNKNOWN')}",
                    f"Published At: {context.get('published_at') or 'UNKNOWN'}",
                    f"Content: {context['content']}",
                ]
            )
        )
    return "\n\n".join(lines)


def to_retrieved_documents(retrieval_result: dict[str, Any]) -> list[RetrievedDocument]:
    documents: list[RetrievedDocument] = []
    for context in retrieval_result.get("contexts", []):
        documents.append(
            {
                "page_content": context.get("content", ""),
                "metadata": {
                    "title": context.get("title", ""),
                    "url": context.get("url", ""),
                    "chunk_index": context.get("chunk_index", 0),
                    "reliability": context.get("reliability", "MEDIUM"),
                    "freshness": context.get("freshness", "UNKNOWN"),
                    "published_at": context.get("published_at"),
                },
                "score": float(context.get("score") or 0.0),
                "source": context.get("url", ""),
            }
        )
    return documents


def retrieve_for_agent_state(
    question: str,
    character_context: Any | None = None,
    official_only: bool = True,
    max_results: int | None = None,
    max_contexts: int | None = None,
) -> dict[str, Any]:
    rag = WebSearchRAG()
    retrieval_result = rag.retrieve(
        question=question,
        character_context=character_context,
        official_only=official_only,
        max_results=max_results,
        max_contexts=max_contexts,
    )
    return {
        "retrieved_docs": to_retrieved_documents(retrieval_result),
        "context": format_contexts_for_prompt(retrieval_result),
        "tool_results": {"web_search_rag": retrieval_result},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run first-pass MapleStory Web Search RAG retrieval.")
    parser.add_argument("question")
    parser.add_argument("--max-results", type=int, default=DEFAULT_MAX_RESULTS)
    parser.add_argument("--max-contexts", type=int, default=DEFAULT_MAX_CONTEXTS)
    parser.add_argument("--include-community", action="store_true")
    parser.add_argument("--prompt-format", action="store_true")
    args = parser.parse_args()

    rag = WebSearchRAG()
    result = rag.retrieve(
        question=args.question,
        official_only=not args.include_community,
        max_results=args.max_results,
        max_contexts=args.max_contexts,
    )
    if args.prompt_format:
        print(format_contexts_for_prompt(result))
        return
    print(json_lib.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
