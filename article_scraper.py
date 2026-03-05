import logging
import re

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_MAX_CHARS = 15_000
_TIMEOUT = 10

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    # Google 동의 페이지 우회 쿠키
    "Cookie": "CONSENT=YES+cb; SOCS=CAISHAgBEhJnd3NfMjAyMzA4MDktMF9SQzEaAmVuIAEaBgiAo_SnBg",
}

_PAYWALL_PHRASES = [
    "subscribe", "subscription", "login to read", "sign in to read",
    "구독", "로그인", "회원가입", "유료기사", "전용기사",
]

_CONTENT_CLASSES = [
    "article", "article-body", "article-content", "article_body",
    "article-text", "post-content", "story-body", "entry-content",
    "content", "news-content", "newstext", "article__body",
    "news_view", "article_view", "view_con", "news-article-body",
]


def scrape_article(url: str, timeout: int = _TIMEOUT) -> str | None:
    """
    URL의 기사 본문을 추출합니다.

    Returns:
        기사 본문 텍스트, 페이월/오류 시 메시지 문자열, 접근 불가 시 None.
    """
    try:
        session = requests.Session()
        resp = session.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        logger.warning("타임아웃: %s", url)
        return None
    except requests.exceptions.TooManyRedirects:
        logger.warning("리다이렉트 초과: %s", url)
        return None
    except requests.exceptions.ConnectionError:
        logger.warning("연결 오류: %s", url)
        return None
    except requests.exceptions.HTTPError as e:
        logger.warning("HTTP 오류 %s: %s", e.response.status_code, url)
        return None

    if _is_google_page(resp.url, resp.text):
        logger.warning("Google 동의/개인정보 페이지 감지, 스크래핑 불가: %s → %s", url, resp.url)
        return None

    text = _extract_text(resp.text, resp.url)

    if _is_paywall(text):
        return "[페이월: 전체 기사에 접근할 수 없습니다. 구독이 필요할 수 있습니다.]"

    return text[:_MAX_CHARS] if text else None


def _is_google_page(final_url: str, html: str) -> bool:
    """Google 동의/개인정보 페이지 여부 감지."""
    if "google.com" not in final_url:
        return False
    lower = html.lower()
    return "consent" in lower or ("privacy" in lower and "cookie" in lower)


def _extract_text(html: str, url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # 불필요한 태그 제거
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside", "form", "iframe"]):
        tag.decompose()

    # 1순위: <article> 태그
    candidate = soup.find("article")

    # 2순위: 알려진 콘텐츠 클래스
    if not candidate:
        for cls in _CONTENT_CLASSES:
            candidate = soup.find(class_=re.compile(cls, re.I))
            if candidate:
                break

    # 3순위: id에 article/content/body 포함
    if not candidate:
        candidate = soup.find(id=re.compile(r"article|content|body|story", re.I))

    # 폴백: body 전체
    if not candidate:
        candidate = soup.body

    if not candidate:
        return ""

    raw = candidate.get_text(separator="\n", strip=True)
    # 연속 빈 줄 정리
    cleaned = re.sub(r"\n{3,}", "\n\n", raw)
    return cleaned.strip()


def _is_paywall(text: str) -> bool:
    if not text or len(text) < 300:
        snippet = (text or "").lower()
        return any(phrase in snippet for phrase in _PAYWALL_PHRASES)
    return False
