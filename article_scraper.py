import logging
import re

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

_MAX_CHARS = 15_000
_TIMEOUT_MS = 20_000  # 20초

# 로딩 속도 향상을 위해 불필요한 리소스 차단
_BLOCKED_RESOURCES = {"image", "stylesheet", "font", "media"}

_CONTENT_CLASSES = [
    "article", "article-body", "article-content", "article_body",
    "article-text", "post-content", "story-body", "entry-content",
    "content", "news-content", "newstext", "article__body",
    "news_view", "article_view", "view_con", "news-article-body",
]

_PAYWALL_PHRASES = [
    "subscribe", "subscription", "login to read", "sign in to read",
    "구독", "로그인", "회원가입", "유료기사", "전용기사",
]


def scrape_articles_batch(urls: list[str]) -> dict[str, str | None]:
    """
    브라우저 1개 인스턴스로 여러 기사를 순차 스크래핑합니다.

    Returns:
        {url: 기사본문 또는 None} 딕셔너리
    """
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",           # Cloud Run(root 실행) 필수
                "--disable-dev-shm-usage",  # /dev/shm 제한 우회
                "--disable-gpu",
            ],
        )
        for url in urls:
            results[url] = _scrape_one(browser, url)
        browser.close()
    return results


def scrape_article(url: str) -> str | None:
    """단건 스크래핑 (하위호환용)."""
    return scrape_articles_batch([url]).get(url)


def _scrape_one(browser, url: str) -> str | None:
    page = None
    try:
        page = browser.new_page()

        # 이미지·폰트·미디어 차단으로 로딩 속도 향상
        page.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in _BLOCKED_RESOURCES
            else route.continue_(),
        )

        page.goto(url, wait_until="domcontentloaded", timeout=_TIMEOUT_MS)

        final_url = page.url
        if "google.com" in final_url:
            logger.warning("Google 리다이렉트/동의 페이지 감지, 스크래핑 불가: %s → %s", url, final_url)
            return None

        text = _extract_text(page.content(), final_url)

        if _is_paywall(text):
            return "[페이월: 전체 기사에 접근할 수 없습니다. 구독이 필요할 수 있습니다.]"

        return text[:_MAX_CHARS] if text else None

    except Exception as e:
        logger.warning("스크래핑 실패 %s: %s", url, e)
        return None
    finally:
        if page:
            page.close()


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
    cleaned = re.sub(r"\n{3,}", "\n\n", raw)
    return cleaned.strip()


def _is_paywall(text: str) -> bool:
    if not text or len(text) < 300:
        snippet = (text or "").lower()
        return any(phrase in snippet for phrase in _PAYWALL_PHRASES)
    return False
