import hashlib
import logging
from datetime import date, timedelta

import streamlit as st

from news_fetcher import DEFAULT_KEYWORDS
from orchestrator import search_all_sources
from secret_manager import get_gemini_api_key
from summarizer import summarize_article
from settings_manager import (
    get_cse_settings,
    get_naver_settings,
    update_cse_settings,
    update_naver_settings,
    save_settings,
    load_settings,
)

logging.basicConfig(level=logging.INFO)

# ── 기본 요약 양식 ────────────────────────────────────────────────────────────

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


# ── Gemini API 키 로딩 (앱 시작 시 한 번만) ───────────────────────────────────

@st.cache_resource(show_spinner="Gemini API 키 로딩 중...")
def load_api_key() -> str:
    return get_gemini_api_key()


# ── 유틸리티 ──────────────────────────────────────────────────────────────────

def _url_key(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:8]


def _checkbox_key(url: str) -> str:
    return f"select_{_url_key(url)}"


# ── 설정 패널 렌더링 ─────────────────────────────────────────────────────────

def render_settings_panel():
    """사이드바: 검색 소스 설정 패널"""
    with st.sidebar:
        st.divider()
        with st.expander("⚙️ 검색 소스 설정", expanded=False):
            # ── Google CSE 설정 ──────────────────────────────────────────
            st.markdown("**Google CSE**")
            cse = get_cse_settings()

            cse_enabled = st.checkbox(
                "Google CSE 사용",
                value=cse.get("enabled", False),
                key="cse_enabled",
            )

            cse_api_key = st.text_input(
                "API Key",
                value=cse.get("api_key", ""),
                type="password",
                key="cse_api_key",
                help="Google Cloud Console에서 발급받은 API Key",
            )

            cse_engine_id = st.text_input(
                "Search Engine ID (cx)",
                value=cse.get("search_engine_id", ""),
                key="cse_engine_id",
                help="Custom Search Engine ID (검색엔진 ID)",
            )

            if st.button("💾 CSE 설정 저장", key="save_cse"):
                success = update_cse_settings(
                    api_key=cse_api_key,
                    search_engine_id=cse_engine_id,
                    enabled=cse_enabled,
                )
                if success:
                    st.success("CSE 설정 저장 완료!")
                else:
                    st.error("CSE 설정 저장 실패")

            st.divider()

            # ── Naver News 설정 ──────────────────────────────────────────
            st.markdown("**Naver 뉴스**")
            naver = get_naver_settings()

            naver_enabled = st.checkbox(
                "Naver 뉴스 사용",
                value=naver.get("enabled", False),
                key="naver_enabled",
            )

            naver_client_id = st.text_input(
                "Client ID",
                value=naver.get("client_id", ""),
                key="naver_client_id",
                help="Naver Developers에서 발급받은 Client ID",
            )

            naver_client_secret = st.text_input(
                "Client Secret",
                value=naver.get("client_secret", ""),
                type="password",
                key="naver_client_secret",
                help="Naver Developers에서 발급받은 Client Secret",
            )

            if st.button("💾 Naver 설정 저장", key="save_naver"):
                success = update_naver_settings(
                    client_id=naver_client_id,
                    client_secret=naver_client_secret,
                    enabled=naver_enabled,
                )
                if success:
                    st.success("Naver 설정 저장 완료!")
                else:
                    st.error("Naver 설정 저장 실패")


# ── 메인 앱 ───────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="M&A 뉴스 요약기",
        page_icon="📰",
        layout="wide",
    )
    st.title("📰 M&A 뉴스 요약기")

    # Session state 초기화
    if "articles" not in st.session_state:
        st.session_state.articles = []
    if "summaries" not in st.session_state:
        st.session_state.summaries = {}
    if "source_counts" not in st.session_state:
        st.session_state.source_counts = {}

    # ── 사이드바: 검색 설정 ─────────────────────────────────────────────────
    with st.sidebar:
        st.header("검색 설정")

        today = date.today()
        default_start = today - timedelta(days=7)

        start_date = st.date_input(
            "시작 날짜",
            value=default_start,
            max_value=today,
        )
        end_date = st.date_input(
            "종료 날짜",
            value=today,
            max_value=today,
        )

        max_results = st.slider("최대 기사 수", min_value=10, max_value=100, value=30, step=10)

        st.divider()
        st.markdown("**검색 키워드**")
        custom_keywords = st.text_area(
            "검색 키워드 (OR로 연결)",
            value=DEFAULT_KEYWORDS,
            height=120,
            help=(
                "Google News 검색에 사용할 키워드를 입력하세요.\n"
                "OR로 여러 키워드를 연결할 수 있습니다.\n"
                '예: merger OR acquisition OR "joint venture"'
            ),
            label_visibility="collapsed",
        )

        st.divider()
        st.markdown("**검색 소스 설정**")
        use_gemini_fallback = st.checkbox(
            "Gemini 검색 폴백 사용",
            value=True,
            help="DuckDuckGo + Google News RSS 검색에서 기사를 찾지 못할 경우 Gemini를 사용해 추가 검색합니다.",
        )

        # ── 검색 소스 설정 패널 ───────────────────────────────────────────
        render_settings_panel()

        search_clicked = st.button("🔍 뉴스 검색", use_container_width=True, type="primary")

    # ── 날짜 유효성 검사 ────────────────────────────────────────────────────
    if start_date > end_date:
        st.error("시작 날짜가 종료 날짜보다 늦을 수 없습니다.")
        return

    # ── 뉴스 검색 ───────────────────────────────────────────────────────────
    if search_clicked:
        st.session_state.summaries = {}  # 이전 요약 초기화
        st.session_state.source_counts = {}
        with st.spinner(f"{start_date} ~ {end_date} M&A 뉴스 검색 중..."):
            try:
                api_key_for_search = load_api_key() if use_gemini_fallback else None
            except Exception:
                api_key_for_search = None

            articles, source_counts = search_all_sources(
                after_date=start_date,
                before_date=end_date,
                max_results=max_results,
                keywords=custom_keywords,
                api_key=api_key_for_search,
                use_gemini_fallback=use_gemini_fallback,
            )
        st.session_state.articles = articles
        st.session_state.source_counts = source_counts

        if not articles:
            st.warning("해당 기간에 검색된 M&A 뉴스가 없습니다. 날짜 범위를 넓혀보세요.")

    # ── 기사 목록 표시 ──────────────────────────────────────────────────────
    articles = st.session_state.articles
    if articles:
        # 소스별 건수 표시
        source_counts = st.session_state.get("source_counts", {})
        if source_counts:
            parts = [f"**{src}**: {n}건" for src, n in source_counts.items() if n > 0]
            st.caption("검색 소스 | " + " · ".join(parts))

        st.subheader(f"검색된 기사 목록 ({len(articles)}건)")

        # 전체 선택/해제
        col_all, col_none, _ = st.columns([1, 1, 8])
        with col_all:
            if st.button("전체 선택"):
                for a in articles:
                    st.session_state[_checkbox_key(a["url"])] = True
        with col_none:
            if st.button("전체 해제"):
                for a in articles:
                    st.session_state[_checkbox_key(a["url"])] = False

        st.divider()

        for i, article in enumerate(articles):
            col_cb, col_info = st.columns([0.04, 0.96])
            with col_cb:
                st.checkbox(
                    label="",
                    key=_checkbox_key(article["url"]),
                    label_visibility="collapsed",
                )
            with col_info:
                search_src = article.get("search_source", "")
                source_tag = f"`{search_src}` " if search_src else ""
                source_info = f"**{article['source']}**  |  " if article["source"] else ""
                date_info = f"`{article['published']}`  " if article["published"] else ""
                st.markdown(
                    f"{source_tag}{source_info}{date_info}[{article['title']}]({article['url']})"
                )
                if article["snippet"]:
                    st.caption(article["snippet"])

        st.divider()

        # ── 요약 양식 설정 ─────────────────────────────────────────────────
        st.subheader("요약 양식 설정")
        custom_format = st.text_area(
            "예시 양식 및 규칙",
            value=DEFAULT_FORMAT,
            height=350,
            help="Gemini에게 전달될 요약 양식입니다. 자유롭게 수정 가능합니다.",
        )

        # Gemini 모델 선택
        model_choice = st.selectbox(
            "Gemini 모델",
            options=[
                "gemini-3.1-pro-preview",
                "gemini-3.1-flash-lite-preview",
                "gemini-2.5-pro",
                "gemini-2.5-flash",
                "gemini-2.5-flash-lite",
                "gemini-2.0-flash",
            ],
            index=0,
            help=(
                "사용할 Gemini 모델을 선택하세요.\n"
                "- gemini-3.1-pro-preview: 최신 고성능 모델 (추천)\n"
                "- gemini-3.1-flash-lite-preview: 빠르고 저렴한 최신 모델\n"
                "- gemini-2.5-pro / flash / flash-lite: 안정화 모델\n"
                "- gemini-2.0-flash: 구버전 (2026년 6월 지원 종료 예정)"
            ),
        )

        summarize_clicked = st.button("✨ 선택된 기사 요약", type="primary", use_container_width=True)

        # ── 요약 실행 ───────────────────────────────────────────────────────
        if summarize_clicked:
            selected = [a for a in articles if st.session_state.get(_checkbox_key(a["url"]), False)]

            if not selected:
                st.warning("요약할 기사를 하나 이상 선택해 주세요.")
            else:
                try:
                    api_key = load_api_key()
                except Exception as e:
                    st.error(f"API 키 로딩 실패: {e}")
                    return

                progress = st.progress(0, text="요약 준비 중...")

                for idx, article in enumerate(selected):
                    progress.progress(
                        idx / len(selected),
                        text=f"요약 중... ({idx + 1}/{len(selected)}): {article['title'][:40]}..."
                    )
                    summary = summarize_article(
                        url=article["url"],
                        custom_format=custom_format,
                        api_key=api_key,
                        model=model_choice,
                    )
                    st.session_state.summaries[article["url"]] = summary

                progress.progress(1.0, text="완료!")

        # ── 요약 결과 표시 ─────────────────────────────────────────────────
        if st.session_state.summaries:
            st.divider()
            st.subheader("요약 결과")

            all_summaries_text = ""
            for article in articles:
                url = article["url"]
                if url not in st.session_state.summaries:
                    continue
                summary = st.session_state.summaries[url]

                date_label = f"[{article['published']}] " if article["published"] else ""
                with st.expander(f"📄 {date_label}{article['title']}", expanded=True):
                    st.markdown(summary)
                    col_copy, col_link = st.columns([1, 1])
                    with col_link:
                        st.markdown(f"[기사 원문 보기]({url})")

                all_summaries_text += f"## {article['title']}\n{summary}\n\n---\n\n"

            st.download_button(
                label="📥 전체 요약 다운로드 (txt)",
                data=all_summaries_text,
                file_name=f"mna_summary_{start_date}_{end_date}.txt",
                mime="text/plain",
                use_container_width=True,
            )


if __name__ == "__main__":
    main()
