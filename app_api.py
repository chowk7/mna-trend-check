"""
FastAPI 서버 - M&A 뉴스 요약기
"""
import logging
from datetime import date
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from news_fetcher import fetch_articles
from alternative_fetcher import fetch_articles_ddg
from naver_fetcher import fetch_articles_google_cse, fetch_articles_naver
from orchestrator import search_all_sources
from secret_manager import get_gemini_api_key
from summarizer import summarize_article
from settings_manager import (
    get_cse_settings,
    get_naver_settings,
    load_settings,
    save_settings,
    update_cse_settings,
    update_naver_settings,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="M&A 뉴스 요약기 API")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 및 템플릿
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ── 요청/응답 모델 ─────────────────────────────────────────────────────────────

class SummarizeRequest(BaseModel):
    url: str | None = None
    text: str | None = None
    custom_format: str | None = None
    model: str = "gemini-2.5-flash"


class SearchRequest(BaseModel):
    after_date: str  # YYYY-MM-DD
    before_date: str  # YYYY-MM-DD
    max_results: int = 30
    keywords: str | None = None
    use_gemini_fallback: bool = True


class SettingsUpdateRequest(BaseModel):
    google_cse: dict[str, Any] | None = None
    naver_news: dict[str, Any] | None = None


# ── 헬스체크 ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    return {"status": "ok"}


# ── UI 렌더링 ─────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return templates.TemplateResponse("index.html", {"request": {}})


# ── 요약 API ─────────────────────────────────────────────────────────────────

@app.post("/api/summarize")
def api_summarize(req: SummarizeRequest):
    """URL 또는 직접 텍스트를 요약합니다."""
    try:
        api_key = get_gemini_api_key()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"API 키 로드 실패: {e}")

    try:
        if req.url:
            summary = summarize_article(
                url=req.url,
                custom_format=req.custom_format,
                api_key=api_key,
                model=req.model,
            )
        elif req.text:
            summary = summarize_article(
                url=None,
                custom_format=req.custom_format,
                api_key=api_key,
                model=req.model,
                direct_text=req.text,
            )
        else:
            raise HTTPException(status_code=400, detail="url 또는 text 중 하나 필요")

        return {"success": True, "summary": summary}

    except Exception as e:
        logger.error(f"요약 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── 검색 API ─────────────────────────────────────────────────────────────────

@app.post("/api/search")
def api_search(req: SearchRequest):
    """뉴스를 검색합니다."""
    try:
        after_date = date.fromisoformat(req.after_date)
        before_date = date.fromisoformat(req.before_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식 오류 (YYYY-MM-DD)")

    try:
        api_key = get_gemini_api_key() if req.use_gemini_fallback else None
    except Exception:
        api_key = None

    try:
        articles, source_counts = search_all_sources(
            after_date=after_date,
            before_date=before_date,
            max_results=req.max_results,
            keywords=req.keywords,
            api_key=api_key,
            use_gemini_fallback=req.use_gemini_fallback,
        )

        return {
            "success": True,
            "articles": articles,
            "source_counts": source_counts,
        }

    except Exception as e:
        logger.error(f"검색 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── 설정 API ─────────────────────────────────────────────────────────────────

@app.get("/api/settings")
def api_get_settings():
    """설정을 조회합니다."""
    try:
        settings = load_settings()
        return {"success": True, "settings": settings}
    except Exception as e:
        logger.error(f"설정 로드 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings")
def api_update_settings(req: SettingsUpdateRequest):
    """설정을 저장합니다."""
    try:
        if req.google_cse is not None:
            update_cse_settings(
                api_key=req.google_cse.get("api_key"),
                search_engine_id=req.google_cse.get("search_engine_id"),
                enabled=req.google_cse.get("enabled"),
            )

        if req.naver_news is not None:
            update_naver_settings(
                client_id=req.naver_news.get("client_id"),
                client_secret=req.naver_news.get("client_secret"),
                enabled=req.naver_news.get("enabled"),
            )

        return {"success": True}

    except Exception as e:
        logger.error(f"설정 저장 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
