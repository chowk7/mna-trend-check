import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

from news_fetcher import fetch_articles
from alternative_fetcher import fetch_articles_ddg
from summarizer import search_articles_gemini

logger = logging.getLogger(__name__)

_SOURCE_PRIORITY = {"DuckDuckGo": 0, "Google News RSS": 1, "Google CSE": 2, "Naver News": 3, "Gemini Search": 4}


def search_all_sources(
    after_date: date,
    before_date: date,
    max_results: int = 50,
    keywords: str | None = None,
    api_key: str | None = None,
    use_gemini_fallback: bool = True,
    source_configs: dict | None = None,
    cse_api_key: str = "",
    cse_cx: str = "",
    naver_client_id: str = "",
    naver_client_secret: str = "",
) -> tuple[list[dict], dict[str, int]]:
    """
    DuckDuckGo + Google News RSS + Google CSE + Naver News를 병렬로 검색하고 결과를 합칩니다.
    모든 소스 결과가 없으면 Gemini google_search로 폴백합니다.

    Returns:
        (articles, source_counts)
        - articles: 중복 제거 후 정렬된 기사 리스트
        - source_counts: 각 소스별 수집 건수
    """
    ddg_articles: list[dict] = []
    rss_articles: list[dict] = []
    cse_articles: list[dict] = []
    naver_articles: list[dict] = []

    # 소스 활성화 상태 (source_configs 또는 기존 설정에서 확인)
    cse_enabled = bool(cse_api_key and cse_cx)
    naver_enabled = bool(naver_client_id and naver_client_secret)

    # DuckDuckGo + RSS 병렬 실행
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(fetch_articles_ddg, after_date, before_date, max_results, keywords): "ddg",
            executor.submit(fetch_articles, after_date, before_date, max_results, keywords): "rss",
        }

        # Google CSE 추가 (활성화 시)
        if cse_enabled:
            from cse_fetcher import fetch_articles_cse
            futures[
                executor.submit(
                    fetch_articles_cse,
                    after_date,
                    before_date,
                    max_results,
                    keywords,
                    cse_api_key,
                    cse_cx,
                )
            ] = "cse"

        # Naver News 추가 (활성화 시)
        if naver_enabled:
            from naver_fetcher import fetch_articles_naver
            futures[
                executor.submit(
                    fetch_articles_naver,
                    naver_client_id,
                    naver_client_secret,
                    after_date,
                    before_date,
                    max_results,
                    keywords,
                )
            ] = "naver"

        for future in as_completed(futures):
            source = futures[future]
            try:
                result = future.result()
            except Exception as e:
                logger.warning("%s 검색 실패: %s", source, e)
                result = []

            if source == "ddg":
                ddg_articles = result
            elif source == "rss":
                for a in result:
                    a.setdefault("search_source", "Google News RSS")
                rss_articles = result
            elif source == "cse":
                cse_articles = result
            elif source == "naver":
                naver_articles = result

    # 모든 결과 합치기
    combined = ddg_articles + rss_articles + cse_articles + naver_articles
    combined = _deduplicate(combined)

    # 모든 소스 결과 없음 → Gemini 폴백
    gemini_articles: list[dict] = []
    if not combined and use_gemini_fallback and api_key:
        logger.info("모든 소스 결과 없음 → Gemini 검색 폴백 실행")
        kw = keywords.strip() if keywords and keywords.strip() else '"to acquire" OR "to divest" OR "joint venture"'
        gemini_articles = search_articles_gemini(
            keywords=kw,
            after_date=after_date,
            before_date=before_date,
            api_key=api_key,
            max_results=max_results,
        )
        combined = gemini_articles

    # 날짜 내림차순 정렬 (날짜 없는 기사는 마지막), 비영어 기사는 후순위
    combined.sort(key=lambda a: (
        _is_non_english(a["title"]),
        -(a["published_dt"].timestamp() if a.get("published_dt") else 0),
    ))

    combined = combined[:max_results]

    source_counts = {
        "DuckDuckGo": sum(1 for a in combined if a.get("search_source") == "DuckDuckGo"),
        "Google News RSS": sum(1 for a in combined if a.get("search_source") == "Google News RSS"),
        "Google CSE": sum(1 for a in combined if a.get("search_source") == "Google CSE"),
        "Naver News": sum(1 for a in combined if a.get("search_source") == "Naver News"),
        "Gemini Search": sum(1 for a in combined if a.get("search_source") == "Gemini Search"),
    }

    return combined, source_counts


def _deduplicate(articles: list[dict]) -> list[dict]:
    """
    URL 정규화(Pass 1) 및 제목 fingerprint(Pass 2)로 중복을 제거합니다.
    우선순위: DuckDuckGo > Google News RSS > Google CSE > Naver News > Gemini Search
    """
    # 소스 우선순위 순으로 정렬
    articles = sorted(articles, key=lambda a: _SOURCE_PRIORITY.get(a.get("search_source", ""), 99))

    seen_urls: set[str] = set()
    seen_titles: dict[str, str] = {}  # fingerprint → url
    result: list[dict] = []

    for article in articles:
        # Pass 1: URL 정규화 중복 제거
        norm_url = _normalize_url(article.get("url", ""))
        if norm_url and norm_url in seen_urls:
            continue

        # Pass 2: 제목 fingerprint 중복 제거 (1일 이내 동일 기사)
        fp = _title_fingerprint(article.get("title", ""))
        if fp and fp in seen_titles:
            continue

        if norm_url:
            seen_urls.add(norm_url)
        if fp:
            seen_titles[fp] = norm_url

        result.append(article)

    return result


def _normalize_url(url: str) -> str:
    """URL에서 트래킹 쿼리 파라미터를 제거하고 정규화합니다."""
    if not url:
        return ""
    # 쿼리 파라미터 제거 (utm_*, source, ref 등 트래킹용)
    url = re.sub(r"\?.*$", "", url)
    return url.rstrip("/").lower()


def _title_fingerprint(title: str) -> str:
    """제목을 소문자화하고 기호를 제거한 fingerprint를 반환합니다."""
    if not title:
        return ""
    # 소문자화 후 알파벳/숫자/한글만 남김
    clean = re.sub(r"[^\w\s]", "", title.lower())
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _is_non_english(text: str) -> bool:
    """한글/한자 등 비영어 문자가 포함되면 True (정렬용)."""
    for ch in text:
        cat = unicodedata.category(ch)
        if cat.startswith("L") and ord(ch) > 127:
            return True
    return False
