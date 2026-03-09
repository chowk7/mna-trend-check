import json
import logging
import re
import time
from datetime import date, datetime

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-3.1-pro-preview"
_MAX_RETRIES = 3


def summarize_article(
    url: str,
    custom_format: str,
    api_key: str,
    model: str = _DEFAULT_MODEL,
) -> str:
    """
    url_context 도구를 이용해 Gemini가 URL을 직접 fetch하고 요약합니다.

    Returns:
        요약 텍스트 또는 오류 메시지 문자열.
    """
    client = genai.Client(api_key=api_key)
    prompt = _build_prompt(url, custom_format)

    for attempt in range(_MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(url_context=types.UrlContext())],
                ),
            )

            # 안전 필터 차단 여부 확인
            if response.candidates and response.candidates[0].finish_reason.name == "SAFETY":
                return "[안전 필터에 의해 차단된 콘텐츠입니다.]"

            return response.text

        except Exception as e:
            err_str = str(e).lower()
            if "resource_exhausted" in err_str or "429" in err_str:
                wait = 2 ** (attempt + 1)
                logger.warning("API 한도 초과, %d초 후 재시도 (%d/%d)", wait, attempt + 1, _MAX_RETRIES)
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(wait)
                else:
                    return "[오류: API 한도 초과. 잠시 후 다시 시도하세요.]"
            elif "invalid_argument" in err_str or "400" in err_str:
                logger.error("잘못된 요청: %s", e)
                return f"[오류: 잘못된 요청입니다. ({e})]"
            else:
                logger.error("Gemini 오류: %s", e)
                return f"[오류: {e}]"

    return "[오류: 요약에 실패했습니다.]"


def search_articles_gemini(
    keywords: str,
    after_date: date,
    before_date: date,
    api_key: str,
    max_results: int = 20,
    model: str = _DEFAULT_MODEL,
) -> list[dict]:
    """
    Gemini google_search grounding을 사용해 M&A 뉴스 기사를 검색합니다.
    DDG + RSS 검색이 모두 빈 결과일 때 폴백으로 호출됩니다.

    Returns:
        list of dicts with keys: title, url, published, published_dt, snippet, source, search_source
    """
    client = genai.Client(api_key=api_key)

    prompt = (
        f"You are a news research assistant. Search for M&A news articles about the following topics "
        f"published between {after_date} and {before_date}:\n\n"
        f"Topics: {keywords}\n\n"
        f"Return ONLY a JSON array (no markdown, no explanation) of up to {max_results} articles, "
        f'each with these exact keys: "title", "url", "published" (YYYY-MM-DD format), "snippet", "source".'
    )

    for attempt in range(_MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
            )

            raw = response.text or ""
            articles = _parse_gemini_search_response(raw, after_date, before_date)
            logger.info("Gemini 검색: %d개 기사 수집 완료", len(articles))
            return articles

        except Exception as e:
            err_str = str(e).lower()
            if "resource_exhausted" in err_str or "429" in err_str:
                wait = 2 ** (attempt + 1)
                logger.warning("Gemini 검색 API 한도 초과, %d초 후 재시도 (%d/%d)", wait, attempt + 1, _MAX_RETRIES)
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(wait)
                else:
                    logger.error("Gemini 검색 API 한도 초과로 실패")
                    return []
            else:
                logger.error("Gemini 검색 오류: %s", e)
                return []

    return []


def _parse_gemini_search_response(raw: str, after_date: date, before_date: date) -> list[dict]:
    """Gemini 응답 텍스트에서 JSON 배열을 파싱해 article dict 리스트로 변환합니다."""
    # 마크다운 코드 블록 제거
    text = re.sub(r"```(?:json)?\s*", "", raw).strip()

    # JSON 배열 추출
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        logger.warning("Gemini 응답에서 JSON 배열을 찾지 못했습니다. raw=%s", raw[:200])
        return []

    try:
        items = json.loads(match.group())
    except json.JSONDecodeError as e:
        logger.warning("Gemini 검색 결과 JSON 파싱 실패: %s", e)
        return []

    articles = []
    for item in items:
        if not isinstance(item, dict):
            continue

        pub_dt = _parse_date_str(item.get("published", ""))

        # 날짜 범위 필터링 (published 정보가 있는 경우만)
        if pub_dt:
            pub_d = pub_dt.date()
            if pub_d < after_date or pub_d > before_date:
                continue

        articles.append({
            "title": item.get("title", "제목 없음"),
            "url": item.get("url", ""),
            "published": pub_dt.strftime("%Y-%m-%d") if pub_dt else item.get("published", ""),
            "published_dt": pub_dt,
            "snippet": item.get("snippet", ""),
            "source": item.get("source", ""),
            "search_source": "Gemini Search",
        })

    return articles


def _parse_date_str(date_str: str) -> datetime | None:
    """YYYY-MM-DD 형식 날짜 문자열을 datetime으로 변환합니다."""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%B %d, %Y"):
        try:
            return datetime.strptime(date_str[:len(fmt)], fmt)
        except (ValueError, TypeError):
            continue
    return None


def summarize_with_content(
    content: str,
    custom_format: str,
    api_key: str,
    url: str = "",
    model: str = _DEFAULT_MODEL,
) -> str:
    """
    직접 입력된 기사 내용을 Gemini로 요약합니다 (URL fetch 없음).

    Returns:
        요약 텍스트 또는 오류 메시지 문자열.
    """
    client = genai.Client(api_key=api_key)
    prompt = _build_content_prompt(content, custom_format, url)

    for attempt in range(_MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
            )

            if response.candidates and response.candidates[0].finish_reason.name == "SAFETY":
                return "[안전 필터에 의해 차단된 콘텐츠입니다.]"

            return response.text

        except Exception as e:
            err_str = str(e).lower()
            if "resource_exhausted" in err_str or "429" in err_str:
                wait = 2 ** (attempt + 1)
                logger.warning("API 한도 초과, %d초 후 재시도 (%d/%d)", wait, attempt + 1, _MAX_RETRIES)
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(wait)
                else:
                    return "[오류: API 한도 초과. 잠시 후 다시 시도하세요.]"
            elif "invalid_argument" in err_str or "400" in err_str:
                logger.error("잘못된 요청: %s", e)
                return f"[오류: 잘못된 요청입니다. ({e})]"
            else:
                logger.error("Gemini 오류: %s", e)
                return f"[오류: {e}]"

    return "[오류: 요약에 실패했습니다.]"


def _build_prompt(url: str, custom_format: str) -> str:
    return f"""다음 URL의 기사를 읽고, 제공된 예시 양식에 맞춰 요약해 주세요.

[기사 URL]
{url}

[예시 양식 및 규칙]
{custom_format}"""


def _build_content_prompt(content: str, custom_format: str, url: str = "") -> str:
    url_section = f"\n[기사 URL]\n{url}\n" if url.strip() else ""
    return f"""다음 기사 내용을 읽고, 제공된 예시 양식에 맞춰 요약해 주세요.
{url_section}
[기사 내용]
{content}

[예시 양식 및 규칙]
{custom_format}"""
