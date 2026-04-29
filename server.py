import asyncio
import json
import logging
import os
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from news_fetcher import DEFAULT_KEYWORDS
from cse_fetcher import DEFAULT_KEYWORDS_CSE
from naver_fetcher import DEFAULT_KEYWORDS_NAVER
from orchestrator import search_all_sources
from secret_manager import get_gemini_api_key
from settings_manager import load_settings, save_settings, is_gcs_configured
from summarizer import summarize_article, summarize_with_content

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="M&A 뉴스 요약기")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ── 캐시 ──────────────────────────────────────────────────────
_api_key_cache: str | None = None
_settings_cache: dict = {}  # GCS에서 로드한 설정

# ── 환경변수 (폴백) ───────────────────────────────────────────
_ENV_CSE_API_KEY = os.environ.get("GOOGLE_CSE_API_KEY", "AIzaSyDLPbiIhfTeIaFP2JPaC3vEBpowOwKYhVA")
_ENV_CSE_CX = os.environ.get("GOOGLE_CSE_CX", "620f073b5bf414784")
_ENV_NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "_jOicpv_8TEwG0M3VpLK")
_ENV_NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "KmUiTp1kgi")


def _load_api_key() -> str:
    global _api_key_cache
    if _api_key_cache:
        return _api_key_cache
    env_key = os.environ.get("GEMINI_API_KEY")
    if env_key:
        _api_key_cache = env_key
        return _api_key_cache
    _api_key_cache = get_gemini_api_key()
    return _api_key_cache


def _get_cred(key: str, env_val: str) -> str:
    """GCS 설정 우선, 없으면 환경변수 폴백."""
    return _settings_cache.get(key) or env_val


def _effective_cse_api_key() -> str:
    return _get_cred("cse_api_key", _ENV_CSE_API_KEY)


def _effective_cse_cx() -> str:
    return _get_cred("cse_cx", _ENV_CSE_CX)


def _effective_naver_client_id() -> str:
    return _get_cred("naver_client_id", _ENV_NAVER_CLIENT_ID)


def _effective_naver_client_secret() -> str:
    return _get_cred("naver_client_secret", _ENV_NAVER_CLIENT_SECRET)


# ── 시작 시 GCS 설정 로드 ─────────────────────────────────────
@app.on_event("startup")
async def _startup():
    global _settings_cache
    _settings_cache = load_settings()
    logger.info("GCS 설정 로드 완료: %d개 키", len(_settings_cache))


# ── 기본 요약 양식 ────────────────────────────────────────────
DEFAULT_FORMAT = """[예시 1번]
(10/22일, 반도체) 韓세미파이브 IPO 절차 진행 중, 예상 시가총액 0.7~0.8兆 수준
ㅡ 17日 韓 맞춤형 반도체 설계업체 세미파이브(최대주주 美SiFive社 18% 보유)는 코스닥 상장위한 증권신고서 제출 (대표주관사는 삼성/UBS)
ㅡ 세미파이브는 SoC 설계역량으로 韓 리벨리온/퓨리오사AI/하이퍼엑셀 等 AI向 Fabless와 협력 中

[예시 2번]
(10/21일, 보안 S/W) 美Veeam, AI 보안 기업 Securiti社 1.7B$에 인수
ㅡ Veeam : 데이터 백업 및 데이터 보호 S/W社 (KKR 제안 Long-list 기업중 하나)
ㅡ Securiti社 기술 활용해 AI 모델이 데이터에 접근하는 것을 제어할 수 있도록 기존 제품 성능 강화 예정

[예시 3번]
(10/22일, 기타) 韓셀트리온그룹, 중앙일보그룹 산하 영화제작社 SLL중앙 인수 검토
ㅡ SLL중앙은 중앙 계열사 콘텐트리중앙(JTBC, 메가박스 영화관 보유)의 자회사로, 영화 等 컨텐츠 제작 전문 업체
ㅡ K컨텐츠 사업 인수로 非바이오 부문을 강화하여, 장남 서진석은 바이오, 차남 서준석은 非바이오 신사업으로 후계구도 정리 관측

[양식]
(기사날짜, 카테고리) 어떤업체가 어떤 업체를 얼마에 인수/매각하는지 기술
ㅡ 인수업체가 왜 인수하는지, 인수업체는 어떤 회사인지 한 문장으로 기술
ㅡ 상세내용으로 매각업체가 왜 매각하는지, 매각업체는 어떤 회사인지 한 문장으로 기술
ㅡ 기타 주요 내용 한 문장으로 기술

[규칙]
ㅡ 말투는 명사로 끝나는 문어체로 표현
ㅡ 기사 날짜는 예를 들어 10/23日 같이 월/일日로 표현.
ㅡ 한국회사 제외하고는 영어로 회사명을 표기
ㅡ 제목에서 회사이름을 언급하는 경우에 회사 본사가 위치한 국가를 한자로 덧붙여줌 (예를 들어 美 nVidia)"""

MODELS = [
    {"id": "gemini-3-flash-preview", "label": "gemini-3-flash-preview (기본값)"},
    {"id": "gemini-3.1-pro-preview", "label": "gemini-3.1-pro-preview (고성능)"},
    {"id": "gemini-3.1-flash-lite-preview", "label": "gemini-3.1-flash-lite-preview (경량)"},
    {"id": "gemini-2.5-pro", "label": "gemini-2.5-pro (안정)"},
    {"id": "gemini-2.5-flash", "label": "gemini-2.5-flash (안정)"},
    {"id": "gemini-2.5-flash-lite", "label": "gemini-2.5-flash-lite (안정, 경량)"},
    {"id": "gemini-2.0-flash", "label": "gemini-2.0-flash (지원 종료 예정)"},
]

_DEFAULT_DDG_KEYWORDS = "acquire divest merger acquisition"


# ── API ───────────────────────────────────────────────────────

@app.get("/api/config")
async def get_config():
    cse_ok = bool(_effective_cse_api_key() and _effective_cse_cx())
    naver_ok = bool(_effective_naver_client_id() and _effective_naver_client_secret())
    return {
        "default_format": DEFAULT_FORMAT,
        "models": MODELS,
        "sources": {
            "rss": {
                "label": "Google News RSS",
                "available": True,
                "default_keywords": DEFAULT_KEYWORDS,
            },
            "ddg": {
                "label": "DuckDuckGo",
                "available": True,
                "default_keywords": _DEFAULT_DDG_KEYWORDS,
            },
            "cse": {
                "label": "Google CSE",
                "available": cse_ok,
                "default_keywords": DEFAULT_KEYWORDS_CSE,
            },
            "naver": {
                "label": "Naver 뉴스",
                "available": naver_ok,
                "default_keywords": DEFAULT_KEYWORDS_NAVER,
            },
        },
        "gcs_configured": is_gcs_configured(),
    }


@app.get("/api/settings")
async def get_settings():
    """현재 GCS 설정을 반환합니다. 민감 값은 마스킹합니다."""
    # cache가 비어있으면 GCS에서 다시 로드
    global _settings_cache
    if not _settings_cache:
        _settings_cache = load_settings()
        logger.info("Settings cache miss, reloaded from GCS")

    def mask(val: str) -> str:
        if not val:
            return ""
        return val[:4] + "****" if len(val) > 4 else "****"

    return {
        "cse_api_key": _settings_cache.get("cse_api_key", ""),
        "cse_cx": _settings_cache.get("cse_cx", ""),
        "naver_client_id": _settings_cache.get("naver_client_id", ""),
        "naver_client_secret": _settings_cache.get("naver_client_secret", ""),
        # 환경변수 현황 (실제 값 아님)
        "env_cse_api_key_set": bool(_ENV_CSE_API_KEY),
        "env_cse_cx_set": bool(_ENV_CSE_CX),
        "env_naver_client_id_set": bool(_ENV_NAVER_CLIENT_ID),
        "env_naver_client_secret_set": bool(_ENV_NAVER_CLIENT_SECRET),
        "gcs_configured": is_gcs_configured(),
    }


class SettingsUpdateRequest(BaseModel):
    cse_api_key: str = ""
    cse_cx: str = ""
    naver_client_id: str = ""
    naver_client_secret: str = ""


@app.post("/api/settings")
async def update_settings(req: SettingsUpdateRequest):
    global _settings_cache
    new_settings = {
        "cse_api_key": req.cse_api_key.strip(),
        "cse_cx": req.cse_cx.strip(),
        "naver_client_id": req.naver_client_id.strip(),
        "naver_client_secret": req.naver_client_secret.strip(),
    }
    try:
        await asyncio.to_thread(save_settings, new_settings)
    except EnvironmentError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("설정 저장 실패: %s", e)
        raise HTTPException(status_code=500, detail=f"GCS 저장 실패: {e}")

    _settings_cache = new_settings
    cse_ok = bool(_effective_cse_api_key() and _effective_cse_cx())
    naver_ok = bool(_effective_naver_client_id() and _effective_naver_client_secret())
    return {
        "ok": True,
        "cse_available": cse_ok,
        "naver_available": naver_ok,
    }


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(content=(STATIC_DIR / "index.html").read_text(encoding="utf-8"))


# ── Search ────────────────────────────────────────────────────

class SourceConfig(BaseModel):
    enabled: bool = True
    keywords: str | None = None


class SearchRequest(BaseModel):
    start_date: str
    end_date: str
    max_results: int = 30
    use_gemini_fallback: bool = True
    source_configs: dict[str, SourceConfig] = {}


@app.post("/api/search")
async def search(req: SearchRequest):
    try:
        after = date.fromisoformat(req.start_date)
        before = date.fromisoformat(req.end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"날짜 형식 오류: {e}")

    if after > before:
        raise HTTPException(status_code=400, detail="시작 날짜가 종료 날짜보다 늦을 수 없습니다.")

    try:
        api_key = _load_api_key() if req.use_gemini_fallback else None
    except Exception:
        api_key = None

    articles, source_counts = await asyncio.to_thread(
        search_all_sources,
        after_date=after,
        before_date=before,
        max_results=req.max_results,
        source_configs={k: v.model_dump() for k, v in req.source_configs.items()},
        api_key=api_key,
        use_gemini_fallback=req.use_gemini_fallback,
        cse_api_key=_effective_cse_api_key(),
        cse_cx=_effective_cse_cx(),
        naver_client_id=_effective_naver_client_id(),
        naver_client_secret=_effective_naver_client_secret(),
    )

    for a in articles:
        a.pop("published_dt", None)

    return {"articles": articles, "source_counts": source_counts}


# ── Summarize ─────────────────────────────────────────────────

class ArticleRef(BaseModel):
    url: str
    title: str


class SummarizeRequest(BaseModel):
    articles: list[ArticleRef]
    custom_format: str
    model: str = "gemini-3-flash-preview"


@app.post("/api/summarize")
async def summarize(req: SummarizeRequest):
    try:
        api_key = _load_api_key()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"API 키 로딩 실패: {e}")

    async def event_stream():
        total = len(req.articles)
        for idx, article in enumerate(req.articles):
            yield (
                "data: "
                + json.dumps(
                    {"type": "progress", "index": idx, "total": total, "title": article.title},
                    ensure_ascii=False,
                )
                + "\n\n"
            )

            try:
                summary = await asyncio.to_thread(
                    summarize_article,
                    url=article.url,
                    custom_format=req.custom_format,
                    api_key=api_key,
                    model=req.model,
                )
            except Exception as e:
                summary = f"[오류: {e}]"

            yield (
                "data: "
                + json.dumps(
                    {"type": "result", "url": article.url, "title": article.title, "summary": summary},
                    ensure_ascii=False,
                )
                + "\n\n"
            )

        yield "data: " + json.dumps({"type": "done"}) + "\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


class ManualSummarizeRequest(BaseModel):
    title: str = ""
    url: str = ""
    content: str
    custom_format: str
    model: str = "gemini-3-flash-preview"


@app.post("/api/summarize-manual")
async def summarize_manual(req: ManualSummarizeRequest):
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="기사 내용을 입력해 주세요.")

    try:
        api_key = _load_api_key()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"API 키 로딩 실패: {e}")

    try:
        summary = await asyncio.to_thread(
            summarize_with_content,
            content=req.content,
            custom_format=req.custom_format,
            api_key=api_key,
            url=req.url,
            model=req.model,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"summary": summary}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
