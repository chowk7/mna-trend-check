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
from orchestrator import search_all_sources
from secret_manager import get_gemini_api_key
from summarizer import summarize_article, summarize_with_content

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="M&A 뉴스 요약기")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_api_key_cache: str | None = None


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
    {"id": "gemini-3.1-pro-preview", "label": "gemini-3.1-pro-preview (최신, 추천)"},
    {"id": "gemini-3.1-flash-lite-preview", "label": "gemini-3.1-flash-lite-preview (빠름)"},
    {"id": "gemini-2.5-pro", "label": "gemini-2.5-pro (안정)"},
    {"id": "gemini-2.5-flash", "label": "gemini-2.5-flash (안정)"},
    {"id": "gemini-2.5-flash-lite", "label": "gemini-2.5-flash-lite (안정, 경량)"},
    {"id": "gemini-2.0-flash", "label": "gemini-2.0-flash (지원 종료 예정)"},
]


@app.get("/api/config")
async def get_config():
    return {
        "default_format": DEFAULT_FORMAT,
        "default_keywords": DEFAULT_KEYWORDS,
        "models": MODELS,
    }


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(content=(STATIC_DIR / "index.html").read_text(encoding="utf-8"))


class SearchRequest(BaseModel):
    start_date: str
    end_date: str
    max_results: int = 30
    keywords: str | None = None
    use_gemini_fallback: bool = True


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
        keywords=req.keywords or None,
        api_key=api_key,
        use_gemini_fallback=req.use_gemini_fallback,
    )

    for a in articles:
        a.pop("published_dt", None)

    return {"articles": articles, "source_counts": source_counts}


class ArticleRef(BaseModel):
    url: str
    title: str


class SummarizeRequest(BaseModel):
    articles: list[ArticleRef]
    custom_format: str
    model: str = "gemini-3.1-pro-preview"


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
    model: str = "gemini-3.1-pro-preview"


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
