import logging
import urllib.error
import urllib.parse
from datetime import date, datetime

import feedparser

logger = logging.getLogger(__name__)

# M&A 관련 기본 검색 키워드 (영어)
DEFAULT_KEYWORDS = '"to acquire" OR "to divest" OR "joint venture"'

_RSS_BASE = "https://news.google.com/rss/search"


def fetch_articles(
    after_date: date,
    before_date: date,
    max_results: int = 50,
    keywords: str | None = None,
) -> list[dict]:
    """
    Google News RSS에서 M&A 관련 기사를 가져옵니다.

    Args:
        keywords: 검색 키워드 문자열. None이면 DEFAULT_KEYWORDS 사용.

    Returns:
        list of dicts with keys: title, url, published, published_dt, snippet, source
    """
    after_str = after_date.strftime("%Y-%m-%d")
    before_str = before_date.strftime("%Y-%m-%d")

    search_query = (keywords.strip() if keywords and keywords.strip() else DEFAULT_KEYWORDS)
    query = f"{search_query} after:{after_str} before:{before_str}"
    params = urllib.parse.urlencode({
        "q": query,
        "hl": "en",
        "gl": "US",
        "ceid": "US:en",
    })
    url = f"{_RSS_BASE}?{params}"
    logger.info("Fetching RSS: %s", url)

    try:
        feed = feedparser.parse(url)
    except Exception as e:
        logger.warning("feedparser 오류: %s", e)
        return []

    if feed.bozo and not feed.entries:
        logger.warning("RSS 파싱 경고 (bozo): %s", feed.bozo_exception)
        return []

    articles = []
    for entry in feed.entries:
        try:
            pub_dt = _parse_published(entry)
        except Exception:
            pub_dt = None

        # 날짜 범위 클라이언트 측 필터링
        if pub_dt:
            pub_d = pub_dt.date()
            if pub_d < after_date or pub_d > before_date:
                continue

        articles.append({
            "title": entry.get("title", "제목 없음"),
            "url": entry.get("link", ""),
            "published": pub_dt.strftime("%Y-%m-%d") if pub_dt else "",
            "published_dt": pub_dt,
            "snippet": _clean_snippet(entry.get("summary", "")),
            "source": _get_source(entry),
        })

        if len(articles) >= max_results:
            break

    # 영어 기사(ASCII 위주 제목)를 먼저 정렬
    articles.sort(key=lambda a: _is_non_english(a["title"]))

    logger.info("총 %d개 기사 수집 완료", len(articles))
    return articles


def _is_non_english(text: str) -> bool:
    """한글/한자 등 비영어 문자가 포함되면 True (정렬용)."""
    import unicodedata
    for ch in text:
        cat = unicodedata.category(ch)
        if cat.startswith("L") and ord(ch) > 127:
            return True
    return False


def _parse_published(entry) -> datetime | None:
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime(*entry.published_parsed[:6])
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        return datetime(*entry.updated_parsed[:6])
    return None


def _clean_snippet(raw: str) -> str:
    """HTML 태그 제거 후 스니펫 반환."""
    import re
    clean = re.sub(r"<[^>]+>", "", raw)
    return clean.strip()


def _get_source(entry) -> str:
    if hasattr(entry, "source") and hasattr(entry.source, "title"):
        return entry.source.title
    # Google News RSS: 출처가 title에 ' - 출처명' 형식으로 붙어있는 경우
    title = entry.get("title", "")
    if " - " in title:
        return title.rsplit(" - ", 1)[-1]
    return ""
