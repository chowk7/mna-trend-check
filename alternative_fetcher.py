import logging
import re
from datetime import date, datetime

logger = logging.getLogger(__name__)

_SEARCH_SOURCE = "DuckDuckGo"


def fetch_articles_ddg(
    after_date: date,
    before_date: date,
    max_results: int = 50,
    keywords: str | None = None,
) -> list[dict]:
    """
    DuckDuckGo News에서 M&A 관련 기사를 가져옵니다.

    Args:
        keywords: 검색 키워드 문자열. None이면 기본 M&A 키워드 사용.

    Returns:
        list of dicts with keys: title, url, published, published_dt, snippet, source, search_source
    """
    from duckduckgo_search import DDGS
    from duckduckgo_search.exceptions import DuckDuckGoSearchException

    query = _build_ddg_query(keywords) if keywords and keywords.strip() else "acquire divest merger acquisition"
    # 넉넉하게 가져온 뒤 클라이언트 날짜 필터 적용
    fetch_count = max(max_results * 3, 60)

    logger.info("DuckDuckGo News 검색: %s (최대 %d건 fetch)", query, fetch_count)

    try:
        with DDGS() as ddgs:
            raw_results = list(ddgs.news(query, max_results=fetch_count))
    except DuckDuckGoSearchException as e:
        logger.warning("DuckDuckGo 검색 오류 (rate limit 등): %s", e)
        return []
    except Exception as e:
        logger.warning("DuckDuckGo 검색 실패: %s", e)
        return []

    articles = []
    for item in raw_results:
        pub_dt = _parse_date(item.get("date", ""))

        # 날짜 범위 필터링
        if pub_dt:
            pub_d = pub_dt.date()
            if pub_d < after_date or pub_d > before_date:
                continue

        articles.append({
            "title": item.get("title", "제목 없음"),
            "url": item.get("url", ""),
            "published": pub_dt.strftime("%Y-%m-%d") if pub_dt else "",
            "published_dt": pub_dt,
            "snippet": item.get("body", ""),
            "source": item.get("source", ""),
            "search_source": _SEARCH_SOURCE,
        })

        if len(articles) >= max_results:
            break

    logger.info("DuckDuckGo: %d개 기사 수집 완료", len(articles))
    return articles


def _build_ddg_query(keywords: str) -> str:
    """
    'to acquire" OR "to divest"' 같은 Google News 스타일 키워드를
    DuckDuckGo에서 사용할 수 있는 자연어 쿼리로 변환합니다.
    """
    # 큰따옴표로 묶인 구문과 일반 단어를 추출, OR 토큰은 제거
    terms = re.findall(r'"[^"]+"|\S+', keywords)
    cleaned = [t for t in terms if t.upper() != "OR"]
    return " ".join(cleaned)


def _parse_date(date_str: str) -> datetime | None:
    """DDG가 반환하는 날짜 문자열을 datetime으로 변환합니다."""
    if not date_str:
        return None
    try:
        # ISO 형식: "2024-01-15T10:30:00+00:00" 또는 "2024-01-15"
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        pass
    # 추가 형식 시도
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str[:len(fmt)], fmt)
        except (ValueError, TypeError):
            continue
    logger.debug("날짜 파싱 실패: %s", date_str)
    return None
