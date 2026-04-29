/**
 * M&A 뉴스 요약기 - 프론트엔드 로직
 */

// 상태 관리
const state = {
    articles: [],
    summaries: {},
    settings: null,
};

// DOM 요소
const elements = {
    // 사이드바
    startDate: () => document.getElementById('start-date'),
    endDate: () => document.getElementById('end-date'),
    maxResults: () => document.getElementById('max-results'),
    maxResultsLabel: () => document.getElementById('max-results-label'),
    keywords: () => document.getElementById('keywords'),
    useGeminiFallback: () => document.getElementById('use-gemini-fallback'),
    searchBtn: () => document.getElementById('search-btn'),
    
    // 검색 소스 설정
    cseEnabled: () => document.getElementById('cse-enabled'),
    cseApiKey: () => document.getElementById('cse-api-key'),
    cseEngineId: () => document.getElementById('cse-engine-id'),
    naverEnabled: () => document.getElementById('naver-enabled'),
    naverClientId: () => document.getElementById('naver-client-id'),
    naverClientSecret: () => document.getElementById('naver-client-secret'),
    
    // 직접 입력
    directUrl: () => document.getElementById('direct-url'),
    directText: () => document.getElementById('direct-text'),
    
    // 메인 콘텐츠
    loading: () => document.getElementById('loading'),
    sourceCounts: () => document.getElementById('source-counts'),
    articlesSection: () => document.getElementById('articles-section'),
    articlesList: () => document.getElementById('articles-list'),
    articleCount: () => document.getElementById('article-count'),
    summaryFormatSection: () => document.getElementById('summary-format-section'),
    summaryFormat: () => document.getElementById('summary-format'),
    modelChoice: () => document.getElementById('model-choice'),
    summarizeBtn: () => document.getElementById('summarize-btn'),
    summarySection: () => document.getElementById('summary-section'),
    summaryList: () => document.getElementById('summary-list'),
};

// 초기화
document.addEventListener('DOMContentLoaded', () => {
    initDateInputs();
    initMaxResultsSlider();
    loadSettings();
    initEventListeners();
});

// 날짜 입력 초기화
function initDateInputs() {
    const today = new Date();
    const weekAgo = new Date(today);
    weekAgo.setDate(weekAgo.getDate() - 7);
    
    elements.endDate().value = formatDate(today);
    elements.startDate().value = formatDate(weekAgo);
}

// 날짜 포맷 (YYYY-MM-DD)
function formatDate(date) {
    return date.toISOString().split('T')[0];
}

// 최대 결과 수 슬라이더
function initMaxResultsSlider() {
    const slider = elements.maxResults();
    const label = elements.maxResultsLabel();
    
    slider.addEventListener('input', () => {
        label.textContent = slider.value;
    });
}

// 설정 로드
async function loadSettings() {
    try {
        const response = await fetch('/api/settings');
        const data = await response.json();
        
        if (data.success) {
            state.settings = data.settings;
            applySettingsToUI(data.settings);
        }
    } catch (error) {
        console.error('설정 로드 실패:', error);
    }
}

// 설정 UI에 적용
function applySettingsToUI(settings) {
    // Google CSE
    if (settings.google_cse) {
        elements.cseEnabled().checked = settings.google_cse.enabled || false;
        elements.cseApiKey().value = settings.google_cse.api_key || '';
        elements.cseEngineId().value = settings.google_cse.search_engine_id || '';
    }
    
    // Naver News
    if (settings.naver_news) {
        elements.naverEnabled().checked = settings.naver_news.enabled || false;
        elements.naverClientId().value = settings.naver_news.client_id || '';
        elements.naverClientSecret().value = settings.naver_news.client_secret || '';
    }
}

// 이벤트 리스너
function initEventListeners() {
    elements.searchBtn().addEventListener('click', searchNews);
}

// 뉴스 검색
async function searchNews() {
    showLoading(true);
    
    const request = {
        after_date: elements.startDate().value,
        before_date: elements.endDate().value,
        max_results: parseInt(elements.maxResults().value),
        keywords: elements.keywords().value || null,
        use_gemini_fallback: elements.useGeminiFallback().checked,
    };
    
    try {
        const response = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(request),
        });
        
        const data = await response.json();
        
        if (data.success) {
            state.articles = data.articles;
            renderSourceCounts(data.source_counts);
            renderArticles(data.articles);
            showSection('articles');
        } else {
            showNotification('검색 실패: ' + data.detail, 'error');
        }
    } catch (error) {
        console.error('검색 오류:', error);
        showNotification('검색 중 오류가 발생했습니다.', 'error');
    } finally {
        showLoading(false);
    }
}

// 소스별 건수 표시
function renderSourceCounts(sourceCounts) {
    const container = elements.sourceCounts();
    const parts = [];
    
    for (const [source, count] of Object.entries(sourceCounts)) {
        if (count > 0) {
            parts.push(`<strong>${source}</strong>: ${count}건`);
        }
    }
    
    if (parts.length > 0) {
        container.innerHTML = '검색 소스 | ' + parts.join(' · ');
        container.classList.remove('hidden');
    } else {
        container.classList.add('hidden');
    }
}

// 기사 목록 렌더링
function renderArticles(articles) {
    const container = elements.articlesList();
    container.innerHTML = '';
    
    articles.forEach((article, index) => {
        const div = document.createElement('div');
        div.className = 'article-item';
        div.innerHTML = `
            <input type="checkbox" data-index="${index}" checked>
            <div class="article-info">
                <div class="article-meta">
                    ${article.search_source ? `<span class="source">${article.search_source}</span> | ` : ''}
                    ${article.source ? `<span>${article.source}</span> | ` : ''}
                    ${article.published ? `<span>${article.published}</span>` : ''}
                </div>
                <div class="article-title">
                    <a href="${article.url}" target="_blank">${article.title}</a>
                </div>
                ${article.snippet ? `<div class="article-snippet">${article.snippet}</div>` : ''}
            </div>
        `;
        container.appendChild(div);
    });
    
    elements.articleCount().textContent = articles.length;
}

// 전체 선택
function selectAll() {
    document.querySelectorAll('.article-item input[type="checkbox"]').forEach(cb => {
        cb.checked = true;
    });
}

// 전체 해제
function deselectAll() {
    document.querySelectorAll('.article-item input[type="checkbox"]').forEach(cb => {
        cb.checked = false;
    });
}

// 요약 양식 기본값
const DEFAULT_FORMAT = `[예시 1번]
(10/22일, 반도체) 韓세미파이브 IPO 절차 진행 중, 예상 시가총액 0.7~0.8兆 수준
ㅡ 17日 韓 맞춤형 반도체 설계업체 세미파이브(최대주주 美SiFive社 18% 보유)는 코스닥 상장위한 증권신고서 제출

[양식]
(기사날짜, 카테고리) 어떤업체가 어떤 업체를 얼마에 인수/매각하는지 기술
ㅡ 인수업체가 왜 인수하는지 한 문장으로 기술
ㅡ 상세내용으로 매각업체가 왜 매각하는지 한 문장으로 기술

[규칙]
ㅡ 말투는 명사로 끝나는 문어체
ㅡ 기사 날짜는 예를 들어 10/23日 같이 월/일日로 표현
ㅡ 한국회사 제외 영어로 회사명 표기`;

// 선택된 기사 요약
async function summarizeSelected() {
    const checkboxes = document.querySelectorAll('.article-item input[type="checkbox"]:checked');
    const indices = Array.from(checkboxes).map(cb => parseInt(cb.dataset.index));
    
    if (indices.length === 0) {
        showNotification('요약할 기사를 하나 이상 선택해 주세요.', 'error');
        return;
    }
    
    const selectedArticles = indices.map(i => state.articles[i]);
    const customFormat = elements.summaryFormat().value || DEFAULT_FORMAT;
    const model = elements.modelChoice().value;
    
    showLoading(true);
    elements.summarizeBtn().disabled = true;
    
    state.summaries = {};
    
    for (let i = 0; i < selectedArticles.length; i++) {
        const article = selectedArticles[i];
        showNotification(`요약 중... (${i + 1}/${selectedArticles.length})`, 'success');
        
        try {
            const response = await fetch('/api/summarize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    url: article.url,
                    custom_format: customFormat,
                    model: model,
                }),
            });
            
            const data = await response.json();
            
            if (data.success) {
                state.summaries[article.url] = data.summary;
            } else {
                console.error('요약 실패:', data.detail);
            }
        } catch (error) {
            console.error('요약 오류:', error);
        }
    }
    
    renderSummaries(selectedArticles);
    showLoading(false);
    elements.summarizeBtn().disabled = false;
    showNotification('요약 완료!', 'success');
}

// 직접 URL/텍스트 요약
async function summarizeDirect() {
    const url = elements.directUrl().value.trim();
    const text = elements.directText().value.trim();
    
    if (!url && !text) {
        showNotification('URL 또는 기사 내용을 입력해 주세요.', 'error');
        return;
    }
    
    const customFormat = elements.summaryFormat().value || DEFAULT_FORMAT;
    const model = elements.modelChoice().value;
    
    showLoading(true);
    
    try {
        const response = await fetch('/api/summarize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: url || null,
                text: text || null,
                custom_format: customFormat,
                model: model,
            }),
        });
        
        const data = await response.json();
        
        if (data.success) {
            // 입력 필드 클리어
            elements.directUrl().value = '';
            elements.directText().value = '';
            
            // 결과 표시
            const tempArticle = {
                url: url || '직접 입력',
                title: url || '직접 입력 내용',
                published: new Date().toISOString().split('T')[0],
            };
            
            state.summaries[tempArticle.url] = data.summary;
            renderSummaries([tempArticle]);
            showNotification('요약 완료!', 'success');
        } else {
            showNotification('요약 실패: ' + data.detail, 'error');
        }
    } catch (error) {
        console.error('요약 오류:', error);
        showNotification('요약 중 오류가 발생했습니다.', 'error');
    } finally {
        showLoading(false);
    }
}

// 요약 결과 렌더링
function renderSummaries(articles) {
    const container = elements.summaryList();
    container.innerHTML = '';
    
    elements.summarySection().classList.remove('hidden');
    
    articles.forEach(article => {
        const url = article.url;
        const summary = state.summaries[url];
        
        if (!summary) return;
        
        const details = document.createElement('details');
        details.className = 'summary-item';
        details.innerHTML = `
            <summary>📄 ${article.published ? '[' + article.published + '] ' : ''}${article.title}</summary>
            <div class="summary-content">${summary}</div>
        `;
        container.appendChild(details);
    });
    
    // 스크롤 이동
    elements.summarySection().scrollIntoView({ behavior: 'smooth' });
}

// 전체 요약 다운로드
function downloadAll() {
    let content = '';
    
    state.articles.forEach(article => {
        const summary = state.summaries[article.url];
        if (summary) {
            content += `## ${article.title}\n${summary}\n\n---\n\n`;
        }
    });
    
    if (!content) {
        showNotification('다운로드할 요약이 없습니다.', 'error');
        return;
    }
    
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `mna_summary_${new Date().toISOString().split('T')[0]}.txt`;
    a.click();
    URL.revokeObjectURL(url);
}

// CSE 설정 저장
async function saveCSE() {
    const settings = {
        google_cse: {
            enabled: elements.cseEnabled().checked,
            api_key: elements.cseApiKey().value,
            search_engine_id: elements.cseEngineId().value,
        },
    };
    
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings),
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification('CSE 설정 저장 완료!', 'success');
        } else {
            showNotification('설정 저장 실패', 'error');
        }
    } catch (error) {
        console.error('설정 저장 오류:', error);
        showNotification('설정 저장 중 오류가 발생했습니다.', 'error');
    }
}

// Naver 설정 저장
async function saveNaver() {
    const settings = {
        naver_news: {
            enabled: elements.naverEnabled().checked,
            client_id: elements.naverClientId().value,
            client_secret: elements.naverClientSecret().value,
        },
    };
    
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings),
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification('Naver 설정 저장 완료!', 'success');
        } else {
            showNotification('설정 저장 실패', 'error');
        }
    } catch (error) {
        console.error('설정 저장 오류:', error);
        showNotification('설정 저장 중 오류가 발생했습니다.', 'error');
    }
}

// 로딩 표시
function showLoading(show) {
    if (show) {
        elements.loading().classList.remove('hidden');
    } else {
        elements.loading().classList.add('hidden');
    }
}

// 섹션 표시
function showSection(section) {
    if (section === 'articles' || section === 'summary') {
        elements.summaryFormatSection().classList.remove('hidden');
    }
}

// 알림
function showNotification(message, type = 'success') {
    const existing = document.querySelector('.notification');
    if (existing) existing.remove();
    
    const div = document.createElement('div');
    div.className = `notification ${type}`;
    div.textContent = message;
    document.body.appendChild(div);
    
    setTimeout(() => div.remove(), 3000);
}
