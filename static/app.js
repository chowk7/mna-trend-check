'use strict';

// ── Default values ────────────────────────────────────────────────────────────

const DEFAULT_KEYWORDS = '"to acquire" OR "to divest" OR "joint venture"';

const DEFAULT_FORMAT = `[예시 1번]
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
ㅡ 제목에서 회사이름을 언급하는 경우에 회사 본사가 위치한 국가를 한자로 덧붙여줌 (예를 들어 美 nVidia)`;

// ── App state ─────────────────────────────────────────────────────────────────

let articles = [];   // [{title, url, published, snippet, source}, ...]
let summaries = {};  // { url: summaryString }

// ── DOM refs ──────────────────────────────────────────────────────────────────

const $ = id => document.getElementById(id);

// ── Utility ───────────────────────────────────────────────────────────────────

/** Returns YYYY-MM-DD string in local time (avoids UTC offset issues). */
function toLocalDateStr(d) {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

/** Show error banner, auto-hide after 6 s. */
function showError(msg) {
  const banner = $('error-banner');
  banner.textContent = msg;
  banner.hidden = false;
  clearTimeout(banner._timer);
  banner._timer = setTimeout(() => { banner.hidden = true; }, 6000);
}

function hideError() {
  $('error-banner').hidden = true;
}

/** Minimal fetch wrapper — throws on HTTP error with backend error message. */
async function apiFetch(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

// ── Initialization ────────────────────────────────────────────────────────────

function initDefaults() {
  const today = new Date();
  const weekAgo = new Date(today);
  weekAgo.setDate(today.getDate() - 7);

  $('date-to').value = toLocalDateStr(today);
  $('date-from').value = toLocalDateStr(weekAgo);
  $('keywords').value = DEFAULT_KEYWORDS;
  $('format-template').value = DEFAULT_FORMAT;
}

// ── Search ────────────────────────────────────────────────────────────────────

async function handleSearch() {
  hideError();

  const dateFrom = $('date-from').value;
  const dateTo = $('date-to').value;

  if (!dateFrom || !dateTo) {
    showError('날짜를 입력해 주세요.');
    return;
  }
  if (dateFrom > dateTo) {
    showError('시작 날짜가 종료 날짜보다 늦을 수 없습니다.');
    return;
  }

  const btn = $('btn-search');
  btn.disabled = true;
  btn.classList.add('loading');
  btn.textContent = '검색 중...';

  try {
    const data = await apiFetch('/api/news', {
      date_from: dateFrom,
      date_to: dateTo,
      max_results: parseInt($('max-results').value, 10) || 30,
      keywords: $('keywords').value.trim() || DEFAULT_KEYWORDS,
    });

    articles = data.articles || [];
    summaries = {};
    $('summaries-container').innerHTML = '';
    $('results-panel').hidden = true;

    renderArticleList();
  } catch (err) {
    showError(`검색 오류: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.classList.remove('loading');
    btn.textContent = '뉴스 검색';
  }
}

// ── Article list ──────────────────────────────────────────────────────────────

function renderArticleList() {
  const list = $('article-list');
  list.innerHTML = '';

  if (articles.length === 0) {
    showError('해당 기간에 검색된 M&A 뉴스가 없습니다. 날짜 범위를 넓혀보세요.');
    $('article-panel').hidden = true;
    $('summary-panel').hidden = true;
    return;
  }

  articles.forEach((article, idx) => {
    const li = document.createElement('li');

    const cbId = `chk-${idx}`;
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.id = cbId;
    cb.dataset.url = article.url;
    cb.checked = true;

    const info = document.createElement('div');
    info.className = 'article-info';

    const meta = document.createElement('div');
    meta.className = 'article-meta';
    if (article.source) {
      const src = document.createElement('span');
      src.className = 'article-source';
      src.textContent = article.source;
      meta.appendChild(src);
    }
    if (article.published) {
      const dt = document.createElement('span');
      dt.className = 'article-date';
      dt.textContent = article.published;
      meta.appendChild(dt);
    }

    const titleDiv = document.createElement('div');
    titleDiv.className = 'article-title';
    const a = document.createElement('a');
    a.href = article.url;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.textContent = article.title;
    titleDiv.appendChild(a);

    info.appendChild(meta);
    info.appendChild(titleDiv);

    if (article.snippet) {
      const snip = document.createElement('div');
      snip.className = 'article-snippet';
      snip.textContent = article.snippet;
      info.appendChild(snip);
    }

    li.appendChild(cb);
    li.appendChild(info);
    list.appendChild(li);
  });

  $('article-count').textContent = `검색된 기사 목록 (${articles.length}건)`;
  $('article-panel').hidden = false;
  $('summary-panel').hidden = false;
}

function handleSelectAll() {
  $('article-list').querySelectorAll('input[type="checkbox"]').forEach(cb => { cb.checked = true; });
}

function handleSelectNone() {
  $('article-list').querySelectorAll('input[type="checkbox"]').forEach(cb => { cb.checked = false; });
}

// ── Summarize ─────────────────────────────────────────────────────────────────

async function handleSummarize() {
  hideError();

  const checked = Array.from($('article-list').querySelectorAll('input[type="checkbox"]:checked'));
  if (checked.length === 0) {
    showError('요약할 기사를 하나 이상 선택해 주세요.');
    return;
  }

  const selectedUrls = new Set(checked.map(cb => cb.dataset.url));
  const selected = articles.filter(a => selectedUrls.has(a.url));

  const customFormat = $('format-template').value;
  const model = $('model-select').value;

  const btn = $('btn-summarize');
  btn.disabled = true;
  btn.classList.add('loading');
  btn.textContent = '요약 중...';

  const progressArea = $('progress-area');
  const progressBar = $('progress-bar');
  const progressText = $('progress-text');
  progressArea.hidden = false;
  progressBar.value = 0;

  // Clear previous results
  $('summaries-container').innerHTML = '';
  $('results-panel').hidden = true;

  // Sequential summarization — avoids hitting rate limits
  for (let i = 0; i < selected.length; i++) {
    const article = selected[i];
    const pct = Math.round((i / selected.length) * 100);
    progressBar.value = pct;
    progressText.textContent = `요약 중... (${i + 1}/${selected.length}): ${article.title.slice(0, 50)}...`;

    try {
      const data = await apiFetch('/api/summarize', {
        url: article.url,
        custom_format: customFormat,
        model,
      });
      summaries[article.url] = data.summary;
    } catch (err) {
      summaries[article.url] = `[오류: ${err.message}]`;
    }

    renderSummary(article, summaries[article.url]);
    $('results-panel').hidden = false;
  }

  progressBar.value = 100;
  progressText.textContent = '완료!';

  btn.disabled = false;
  btn.classList.remove('loading');
  btn.textContent = '선택된 기사 요약';
}

// ── Render single summary ─────────────────────────────────────────────────────

function renderSummary(article, summaryText) {
  const container = $('summaries-container');

  const details = document.createElement('details');
  details.className = 'summary-card';
  details.open = true;

  const summary = document.createElement('summary');
  if (article.published) {
    const dateSpan = document.createElement('span');
    dateSpan.className = 'summary-date';
    dateSpan.textContent = article.published;
    summary.appendChild(dateSpan);
  }
  summary.appendChild(document.createTextNode(article.title));
  details.appendChild(summary);

  const body = document.createElement('div');
  body.className = 'summary-body' + (summaryText.startsWith('[오류') ? ' error' : '');
  body.textContent = summaryText;
  details.appendChild(body);

  const footer = document.createElement('div');
  footer.className = 'summary-footer';
  const link = document.createElement('a');
  link.href = article.url;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  link.textContent = '기사 원문 보기 →';
  footer.appendChild(link);
  details.appendChild(footer);

  container.appendChild(details);
}

// ── Download ──────────────────────────────────────────────────────────────────

function handleDownload() {
  let text = '';
  articles.forEach(a => {
    if (!summaries[a.url]) return;
    text += `## ${a.title}\n${summaries[a.url]}\n\n---\n\n`;
  });

  if (!text) return;

  const dateFrom = $('date-from').value;
  const dateTo = $('date-to').value;
  const filename = `mna_summary_${dateFrom}_${dateTo}.txt`;

  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const tmpA = document.createElement('a');
  tmpA.href = url;
  tmpA.download = filename;
  tmpA.click();
  URL.revokeObjectURL(url);
}

// ── Event bindings ────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  initDefaults();

  $('btn-search').addEventListener('click', handleSearch);
  $('btn-select-all').addEventListener('click', handleSelectAll);
  $('btn-select-none').addEventListener('click', handleSelectNone);
  $('btn-summarize').addEventListener('click', handleSummarize);
  $('btn-download').addEventListener('click', handleDownload);

  // Allow Enter key in search panel inputs to trigger search
  ['date-from', 'date-to', 'max-results'].forEach(id => {
    $(id).addEventListener('keydown', e => { if (e.key === 'Enter') handleSearch(); });
  });
});
