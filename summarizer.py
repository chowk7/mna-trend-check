import logging
import time

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, InvalidArgument

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-1.5-flash"
_MAX_RETRIES = 3


def summarize_article(
    article_text: str,
    custom_format: str,
    api_key: str,
    model: str = _DEFAULT_MODEL,
) -> str:
    """
    Gemini API를 이용해 기사를 요약합니다.

    Returns:
        요약 텍스트 또는 오류 메시지 문자열.
    """
    genai.configure(api_key=api_key)
    model_client = genai.GenerativeModel(model_name=model)
    prompt = _build_prompt(article_text, custom_format)

    for attempt in range(_MAX_RETRIES):
        try:
            response = model_client.generate_content(prompt)

            # 안전 필터 차단 여부 확인
            if response.candidates and response.candidates[0].finish_reason.name == "SAFETY":
                return "[안전 필터에 의해 차단된 콘텐츠입니다.]"

            return response.text

        except ResourceExhausted:
            wait = 2 ** (attempt + 1)
            logger.warning("API 한도 초과, %d초 후 재시도 (%d/%d)", wait, attempt + 1, _MAX_RETRIES)
            if attempt < _MAX_RETRIES - 1:
                time.sleep(wait)
            else:
                return "[오류: API 한도 초과. 잠시 후 다시 시도하세요.]"

        except InvalidArgument as e:
            logger.error("잘못된 요청: %s", e)
            return f"[오류: 잘못된 요청입니다. ({e})]"

        except Exception as e:
            logger.error("Gemini 오류: %s", e)
            return f"[오류: {e}]"

    return "[오류: 요약에 실패했습니다.]"


def _build_prompt(article_text: str, custom_format_example: str) -> str:
    return f"""아래 웹페이지 기사 내용을 제공된 예시 양식에 맞춰서 요약해 주세요.

[기사 내용]
{article_text}

[예시 양식 및 규칙]
{custom_format_example}"""
