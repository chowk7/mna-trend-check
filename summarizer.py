import logging
import time

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-2.0-flash"
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


def _build_prompt(url: str, custom_format: str) -> str:
    return f"""다음 URL의 기사를 읽고, 제공된 예시 양식에 맞춰 요약해 주세요.

[기사 URL]
{url}

[예시 양식 및 규칙]
{custom_format}"""
