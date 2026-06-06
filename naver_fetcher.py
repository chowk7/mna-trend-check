"""
Naver 뉴스 검색 API 파서
"""
import logging
import urllib.parse
from datetime import date, datetime

import requests

logger = logging.getLogger(__name__)

_SEARCH_SOURCE = "Naver News"

DEFAULT_KEYWORDS_NAVER = "인수 합병 M&A"


def fetch_articles_naver(
    client_id: str,
    client_secret: str,
    after_date: date,
    before_date: date,
    max_results: int = 50,
    keywords: str | None = None,
) -> list[dict]:
    """
    Naver 뉴스 검색 API에서 기사를 가져옵니다.

    Args:
        client_id: Naver API Client ID
        client_secret: Naver API Client Secret
        keywords: 검색 키워드

    Returns:
        list of dicts with keys: title, url, published, published_dt, snippet, source, search_source
    """
    if not client_id or not client_secret:
        logger.warning("Naver API credentials not provided")
        return []

    query = keywords.strip() if keywords and keywords.strip() else "인수 합병 M&A"
    display = min(max_results * 2, 100)

    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }

    params = {
        "query": query,
        "display": display,
        "start": 1,
        "sort": "date",
    }

    articles = []

    try:
        response = requests.get(
            "https://openapi.naver.com/v1/search/news.json",
            headers=headers,
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        for item in data.get("items", []):
            # HTML 태그 제거
            title = _clean_html(item.get("title", ""))
            description = _clean_html(item.get("description", ""))

            # 날짜 파싱 (Naver: Wed, 29 Apr 2026 13:00:00 +0900)
            pub_str = item.get("pubDate", "")
            pub_dt = _parse_naver_date(pub_str)

            # 날짜 범위 필터링
            if pub_dt:
                pub_d = pub_dt.date()
                if pub_d < after_date or pub_d > before_date:
                    continue

            articles.append({
                "title": title,
                "url": item.get("link", ""),
                "published": pub_dt.strftime("%Y-%m-%d") if pub_dt else "",
                "published_dt": pub_dt,
                "snippet": description,
                "source": item.get("source", "Naver"),
                "search_source": _SEARCH_SOURCE,
            })

            if len(articles) >= max_results:
                break

        logger.info("Naver News: %d개 기사 수집 완료", len(articles))

    except requests.exceptions.RequestException as e:
        logger.warning(f"Naver API 요청 실패: {e}")
    except Exception as e:
        logger.warning(f"Naver 뉴스 파싱 실패: {e}")

    return articles


def _clean_html(text: str) -> str:
    """HTML 엔티티 및 태그 제거"""
    import re
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&apos;", "'")
    return text.strip()


def _parse_naver_date(date_str: str) -> datetime | None:
    """Naver 뉴스 날짜 파싱 (RFC 2822 스타일)"""
    if not date_str:
        return None

    try:
        # "Wed, 29 Apr 2026 13:00:00 +0900"
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str).replace(tzinfo=None)
    except Exception:
        pass

    return None


def fetch_articles_google_cse(
    api_key: str,
    search_engine_id: str,
    after_date: date,
    before_date: date,
    max_results: int = 50,
    keywords: str | None = None,
) -> list[dict]:
    """
    Google Custom Search Engine API에서 기사를 가져옵니다.

    Args:
        api_key: Google API Key
        search_engine_id: Search Engine ID (cx)
        keywords: 검색 키워드

    Returns:
        list of dicts with keys: title, url, published, published_dt, snippet, source, search_source
    """
    if not api_key or not search_engine_id:
        logger.warning("Google CSE credentials not provided")
        return []

    query = keywords.strip() if keywords and keywords.strip() else "M&A acquisition merger"
    start = 1

    articles = []

    try:
        while len(articles) < max_results:
            params = {
                "key": api_key,
                "cx": search_engine_id,
                "q": query,
                "num": min(10, max_results),
                "start": start,
                "dateRestrict": f"d{(before_date - after_date).days}",
            }

            response = requests.get(
                "https://www.googleapis.com/customsearch/v1",
                params=params,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            items = data.get("items", [])
            if not items:
                break

            for item in items:
                # 날짜 파싱
                pub_str = item.get("pagemap", {}).get("newsarticle", [{}])[0].get("datepublished", "")
                pub_dt = _parse_cse_date(pub_str)

                # 날짜 범위 필터링
                if pub_dt:
                    pub_d = pub_dt.date()
                    if pub_d < after_date or pub_d > before_date:
                        continue

                articles.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "published": pub_dt.strftime("%Y-%m-%d") if pub_dt else "",
                    "published_dt": pub_dt,
                    "snippet": item.get("snippet", ""),
                    "source": item.get("displayLink", ""),
                    "search_source": "Google CSE",
                })

                if len(articles) >= max_results:
                    break

            start += 10

            # 다음 페이지 없으면 종료
            if "nextPage" not in data.get("queries", {}):
                break

        logger.info("Google CSE: %d개 기사 수집 완료", len(articles))

    except requests.exceptions.RequestException as e:
        logger.warning(f"Google CSE API 요청 실패: {e}")
    except Exception as e:
        logger.warning(f"Google CSE 파싱 실패: {e}")

    return articles


def _parse_cse_date(date_str: str) -> datetime | None:
    """Google CSE 날짜 파싱 (ISO 8601)"""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        pass
    return None
