import email.utils
import html
import json
import logging
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

DEFAULT_KEYWORDS_NAVER = '인수 OR 합병 OR 매각 OR M&A OR 지분취득'

_NAVER_ENDPOINT = "https://openapi.naver.com/v1/search/news.json"
_DISPLAY = 100  # 1회 최대 건수


def fetch_articles_naver(
    after_date: date,
    before_date: date,
    max_results: int = 50,
    keywords: str | None = None,
    client_id: str = "",
    client_secret: str = "",
) -> list[dict]:
    """
    Naver 뉴스 OpenAPI로 M&A 관련 뉴스를 검색합니다.

    Returns:
        list of dicts with keys: title, url, published, published_dt, snippet, source, search_source
    """
    if not client_id or not client_secret:
        logger.warning("Naver 자격증명 없음 (NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 필요)")
        return []

    query = keywords.strip() if keywords and keywords.strip() else DEFAULT_KEYWORDS_NAVER
    early_cutoff = after_date - timedelta(days=30)

    articles: list[dict] = []
    start = 1

    while len(articles) < max_results:
        items = _fetch_page(query, client_id, client_secret, start)
        if not items:
            break

        all_old = True
        for item in items:
            pub_dt = _parse_rfc2822(item.get("pubDate", ""))

            if pub_dt:
                pub_d = pub_dt.date()
                # 너무 오래된 기사면 조기 종료 신호
                if pub_d < early_cutoff:
                    all_old = True
                    break
                all_old = False

                if pub_d < after_date or pub_d > before_date:
                    continue
            else:
                all_old = False

            # originallink 우선 사용 (Naver 리다이렉트 회피)
            url = item.get("originallink") or item.get("link", "")

            articles.append({
                "title": _strip_html(item.get("title", "제목 없음")),
                "url": url,
                "published": pub_dt.strftime("%Y-%m-%d") if pub_dt else "",
                "published_dt": pub_dt,
                "snippet": _strip_html(item.get("description", "")),
                "source": _extract_source(url),
                "search_source": "Naver News",
            })

            if len(articles) >= max_results:
                break

        if all_old:
            break

        start += _DISPLAY
        if start > 1000:  # Naver 최대 1000건
            break

    logger.info("Naver News: %d개 기사 수집 완료", len(articles))
    return articles


def _fetch_page(query: str, client_id: str, client_secret: str, start: int) -> list:
    params = urllib.parse.urlencode({
        "query": query,
        "display": _DISPLAY,
        "start": start,
        "sort": "date",
    })
    url = f"{_NAVER_ENDPOINT}?{params}"

    try:
        req = urllib.request.Request(url, headers={
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("items", [])
    except urllib.error.HTTPError as e:
        logger.warning("Naver API HTTP 오류 %d: %s", e.code, e.reason)
        return []
    except Exception as e:
        logger.warning("Naver API 요청 실패: %s", e)
        return []


def _parse_rfc2822(date_str: str) -> datetime | None:
    """RFC 2822 날짜 문자열(Naver pubDate)을 timezone-naive datetime으로 변환합니다."""
    if not date_str:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        return dt.replace(tzinfo=None)
    except Exception:
        return None


def _strip_html(text: str) -> str:
    """<b>, </b> 등 HTML 태그와 엔티티를 제거합니다."""
    cleaned = re.sub(r"<[^>]+>", "", text)
    return html.unescape(cleaned).strip()


def _extract_source(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc
    except Exception:
        return ""
