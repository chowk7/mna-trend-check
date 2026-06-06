import json
import logging
import urllib.parse
import urllib.request
from datetime import date, datetime

logger = logging.getLogger(__name__)

DEFAULT_KEYWORDS_CSE = '"to acquire" OR "to divest" OR "merger" OR "acquisition"'

_CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"


def fetch_articles_cse(
    after_date: date,
    before_date: date,
    max_results: int = 30,
    keywords: str | None = None,
    api_key: str = "",
    cx: str = "",
) -> list[dict]:
    """
    Google Custom Search JSON API로 M&A 뉴스를 검색합니다.

    Returns:
        list of dicts with keys: title, url, published, published_dt, snippet, source, search_source
    """
    if not api_key or not cx:
        logger.warning("Google CSE 자격증명 없음 (GOOGLE_CSE_API_KEY, GOOGLE_CSE_CX 필요)")
        return []

    query = keywords.strip() if keywords and keywords.strip() else DEFAULT_KEYWORDS_CSE
    date_filter = f"after:{after_date} before:{before_date}"
    full_query = f"{query} {date_filter}"

    articles: list[dict] = []
    start = 1

    while len(articles) < max_results:
        batch = _fetch_page(full_query, api_key, cx, start)
        if not batch:
            break

        for item in batch:
            pub_dt = _parse_cse_date(item)
            if pub_dt:
                pub_d = pub_dt.date()
                if pub_d < after_date or pub_d > before_date:
                    continue

            articles.append({
                "title": item.get("title", "제목 없음"),
                "url": item.get("link", ""),
                "published": pub_dt.strftime("%Y-%m-%d") if pub_dt else "",
                "published_dt": pub_dt,
                "snippet": item.get("snippet", "").replace("\n", " "),
                "source": _extract_display_link(item),
                "search_source": "Google CSE",
            })

            if len(articles) >= max_results:
                break

        start += 10
        if start > 91:  # CSE 최대 100건 (start 1~91)
            break

    logger.info("Google CSE: %d개 기사 수집 완료", len(articles))
    return articles


def _fetch_page(query: str, api_key: str, cx: str, start: int) -> list:
    params = urllib.parse.urlencode({
        "key": api_key,
        "cx": cx,
        "q": query,
        "num": 10,
        "start": start,
        "sort": "date",
    })
    url = f"{_CSE_ENDPOINT}?{params}"

    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("items", [])
    except urllib.error.HTTPError as e:
        logger.warning("CSE HTTP 오류 %d: %s", e.code, e.reason)
        return []
    except Exception as e:
        logger.warning("CSE 요청 실패: %s", e)
        return []


def _parse_cse_date(item: dict) -> datetime | None:
    """CSE 응답 item에서 날짜를 파싱합니다."""
    # pagemap.metatags 경로 시도
    pagemap = item.get("pagemap", {})
    metatags = pagemap.get("metatags", [])
    if metatags and isinstance(metatags, list):
        tag = metatags[0]
        for key in ("article:published_time", "og:updated_time", "og:published_time",
                    "date", "datePublished"):
            val = tag.get(key, "")
            if val:
                dt = _parse_iso(val)
                if dt:
                    return dt

    # newsarticle 경로 시도
    for article in pagemap.get("newsarticle", []):
        for key in ("datepublished", "datemodified"):
            val = article.get(key, "")
            if val:
                dt = _parse_iso(val)
                if dt:
                    return dt

    return None


def _parse_iso(date_str: str) -> datetime | None:
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str[:19])
    except (ValueError, TypeError):
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str[:10], fmt)
        except (ValueError, TypeError):
            continue
    return None


def _extract_display_link(item: dict) -> str:
    return item.get("displayLink", item.get("link", "").split("/")[2] if item.get("link") else "")
