import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from news_fetcher import fetch_articles
from alternative_fetcher import fetch_articles_ddg
from cse_fetcher import fetch_articles_cse
from naver_fetcher import fetch_articles_naver
from summarizer import search_articles_gemini

logger = logging.getLogger(__name__)

_SOURCE_PRIORITY = {
    "DuckDuckGo": 0,
    "Google News RSS": 1,
    "Google CSE": 2,
    "Naver News": 3,
    "Gemini Search": 4,
}

_SOURCE_DEFAULTS = {
    "rss":   {"enabled": True,  "keywords": None},
    "ddg":   {"enabled": True,  "keywords": None},
    "cse":   {"enabled": True,  "keywords": None},
    "naver": {"enabled": True,  "keywords": None},
}


def search_all_sources(
    after_date: date,
    before_date: date,
    max_results: int = 50,
    source_configs: dict | None = None,
    api_key: str | None = None,
    use_gemini_fallback: bool = True,
    cse_api_key: str = "",
    cse_cx: str = "",
    naver_client_id: str = "",
    naver_client_secret: str = "",
) -> tuple[list[dict], dict[str, int]]:
    """
    RSS, DuckDuckGo, Google CSE, Naver News를 병렬로 검색하고 결과를 합칩니다.
    모든 소스가 빈 결과이면 Gemini google_search로 폴백합니다.

    Args:
        source_configs: 소스별 설정 dict.
            예: {"rss": {"enabled": True, "keywords": "..."}, "cse": {"enabled": False}}
            None이면 전체 기본값 사용.

    Returns:
        (articles, source_counts)
    """
    cfg = {k: dict(v) for k, v in _SOURCE_DEFAULTS.items()}
    if source_configs:
        for key, val in source_configs.items():
            if key in cfg:
                cfg[key].update(val)

    futures: dict = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        if cfg["rss"]["enabled"]:
            futures[executor.submit(
                fetch_articles, after_date, before_date, max_results, cfg["rss"]["keywords"]
            )] = "rss"

        if cfg["ddg"]["enabled"]:
            futures[executor.submit(
                fetch_articles_ddg, after_date, before_date, max_results, cfg["ddg"]["keywords"]
            )] = "ddg"

        if cfg["cse"]["enabled"] and cse_api_key and cse_cx:
            futures[executor.submit(
                fetch_articles_cse,
                after_date, before_date, max_results,
                cfg["cse"]["keywords"], cse_api_key, cse_cx,
            )] = "cse"

        if cfg["naver"]["enabled"] and naver_client_id and naver_client_secret:
            futures[executor.submit(
                fetch_articles_naver,
                after_date, before_date, max_results,
                cfg["naver"]["keywords"], naver_client_id, naver_client_secret,
            )] = "naver"

        source_results: dict[str, list] = {"rss": [], "ddg": [], "cse": [], "naver": []}
        for future in as_completed(futures):
            src = futures[future]
            try:
                result = future.result()
            except Exception as e:
                logger.warning("%s 검색 실패: %s", src, e)
                result = []

            if src == "rss":
                for a in result:
                    a.setdefault("search_source", "Google News RSS")
            source_results[src] = result

    combined = (
        source_results["ddg"]
        + source_results["rss"]
        + source_results["cse"]
        + source_results["naver"]
    )
    combined = _deduplicate(combined)

    # 모든 소스 빈 결과 → Gemini 폴백
    gemini_articles: list[dict] = []
    if not combined and use_gemini_fallback and api_key:
        logger.info("기본 소스 결과 없음 → Gemini 검색 폴백 실행")
        # 활성화된 소스 중 키워드가 있는 첫 번째 것을 사용
        kw = next(
            (cfg[k]["keywords"] for k in ("rss", "ddg", "cse", "naver")
             if cfg[k].get("keywords")),
            '"to acquire" OR "to divest" OR "joint venture"',
        )
        gemini_articles = search_articles_gemini(
            keywords=kw,
            after_date=after_date,
            before_date=before_date,
            api_key=api_key,
            max_results=max_results,
        )
        combined = gemini_articles

    # 날짜 내림차순 정렬, 비영어 기사는 후순위
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
    """URL 정규화(Pass 1) 및 제목 fingerprint(Pass 2)로 중복을 제거합니다."""
    articles = sorted(articles, key=lambda a: _SOURCE_PRIORITY.get(a.get("search_source", ""), 99))

    seen_urls: set[str] = set()
    seen_titles: dict[str, str] = {}
    result: list[dict] = []

    for article in articles:
        norm_url = _normalize_url(article.get("url", ""))
        if norm_url and norm_url in seen_urls:
            continue

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
    if not url:
        return ""
    url = re.sub(r"\?.*$", "", url)
    return url.rstrip("/").lower()


def _title_fingerprint(title: str) -> str:
    if not title:
        return ""
    clean = re.sub(r"[^\w\s]", "", title.lower())
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _is_non_english(text: str) -> bool:
    for ch in text:
        cat = unicodedata.category(ch)
        if cat.startswith("L") and ord(ch) > 127:
            return True
    return False
