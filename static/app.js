'use strict';

// ── State ─────────────────────────────────────────────────────
const state = {
  articles: [],
  sourceCounts: {},
  summaries: {},
  selected: new Set(),
  isSearching: false,
  isSummarizing: false,
};

// ── DOM helpers ───────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

// DOM refs for elements present in the initial HTML.
// Built lazily inside init() to guarantee DOMContentLoaded.
let dom = {};

// Settings modal refs – populated inside init().
let modal = {};

// ── Utilities ─────────────────────────────────────────────────
function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function sourceBadgeClass(src) {
  if (src === 'DuckDuckGo')      return 'badge-ddg';
  if (src === 'Google News RSS') return 'badge-rss';
  if (src === 'Google CSE')      return 'badge-cse';
  if (src === 'Naver News')      return 'badge-naver';
  if (src === 'Gemini Search')   return 'badge-gemini';
  return '';
}

function sourceBadgeLabel(src) {
  if (src === 'DuckDuckGo')      return 'DDG';
  if (src === 'Google News RSS') return 'RSS';
  if (src === 'Google CSE')      return 'CSE';
  if (src === 'Naver News')      return 'Naver';
  if (src === 'Gemini Search')   return 'Gemini';
  return src;
}

function setLoading(btn, loading, originalText) {
  if (!btn) return;
  if (loading) {
    btn.disabled = true;
    btn.dataset.orig = originalText || btn.textContent;
    btn.innerHTML = `<span class="spinner"></span> ${btn.dataset.orig.replace(/^[^\s]+\s/, '')}...`;
  } else {
    btn.disabled = false;
    btn.textContent = btn.dataset.orig || originalText;
  }
}

function on(id, event, fn) {
  const el = typeof id === 'string' ? $(id) : id;
  if (el) el.addEventListener(event, fn);
}

// ── API ───────────────────────────────────────────────────────
async function apiFetch(url, options = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res;
}

// ── Source availability ───────────────────────────────────────
function updateSourceAvailability(key, available) {
  const s = dom.sources?.[key];
  if (!s) return;
  const badge = $(`badge-${key}`);
  if (available) {
    if (s.en) { s.en.disabled = false; s.en.checked = true; }
    if (s.kw)   s.kw.disabled = false;
    s.wrap?.classList.remove('source-unavailable');
    if (badge) badge.style.display = 'none';
  } else {
    if (s.en) { s.en.checked = false; s.en.disabled = true; }
    if (s.kw)   s.kw.disabled = true;
    s.wrap?.classList.add('source-unavailable');
    if (badge) badge.style.display = 'inline';
  }
}

// ── Render: Source Counts ─────────────────────────────────────
function renderSourceCounts(counts) {
  if (!dom.sourceCounts) return;
  const parts = Object.entries(counts)
    .filter(([, n]) => n > 0)
    .map(([src, n]) =>
      `<span class="source-badge ${sourceBadgeClass(src)}">${sourceBadgeLabel(src)} ${n}건</span>`
    );
  if (parts.length === 0) { dom.sourceCounts.style.display = 'none'; return; }
  dom.sourceCounts.innerHTML = `<span class="source-counts-label">검색 소스</span>` + parts.join('');
  dom.sourceCounts.style.display = 'flex';
}

// ── Render: Articles ──────────────────────────────────────────
function renderArticles() {
  if (!dom.articleList) return;
  const articles = state.articles;
  if (dom.articlesTitle) dom.articlesTitle.textContent = `기사 목록 (${articles.length}건)`;

  dom.articleList.innerHTML = articles.map((a, i) => {
    const srcClass = sourceBadgeClass(a.search_source);
    const srcLabel = sourceBadgeLabel(a.search_source);
    const isSelected = state.selected.has(a.url);
    return `
      <div class="article-card${isSelected ? ' selected' : ''}" data-idx="${i}">
        <input type="checkbox" data-url="${escHtml(a.url)}"${isSelected ? ' checked' : ''}>
        <div class="article-body">
          <div class="article-meta">
            ${a.search_source ? `<span class="article-src-badge ${srcClass}">${srcLabel}</span>` : ''}
            ${a.source        ? `<span class="article-source">${escHtml(a.source)}</span>` : ''}
            ${a.published     ? `<span class="article-date">${escHtml(a.published)}</span>` : ''}
          </div>
          <a class="article-title" href="${escHtml(a.url)}" target="_blank" rel="noopener noreferrer">
            ${escHtml(a.title)}
          </a>
          ${a.snippet ? `<p class="article-snippet">${escHtml(a.snippet)}</p>` : ''}
        </div>
      </div>`;
  }).join('');

  if (dom.results)    dom.results.style.display = 'block';
  if (dom.emptyState) dom.emptyState.style.display = 'none';
  updateSummarizeBtn();
}

// ── Render: Summary Card ──────────────────────────────────────
function renderSummary(url, title, summary) {
  if (!dom.summaryList) return;
  const card = document.createElement('div');
  card.className = 'summary-card';
  card.dataset.url = url;
  card.innerHTML = `
    <div class="summary-card-header">
      <span class="summary-card-title">${escHtml(title)}</span>
      <div class="summary-card-actions">
        <button class="btn btn-sm btn-outline copy-btn">복사</button>
        <a class="btn btn-sm btn-outline" href="${escHtml(url)}" target="_blank" rel="noopener noreferrer">원문</a>
      </div>
    </div>
    <div class="summary-card-body">${escHtml(summary)}</div>`;

  card.querySelector('.copy-btn').addEventListener('click', function () {
    navigator.clipboard.writeText(state.summaries[url] ?? '').then(() => {
      this.textContent = '✓ 복사됨';
      setTimeout(() => { this.textContent = '복사'; }, 2000);
    });
  });

  const existing = dom.summaryList.querySelector(`[data-url="${CSS.escape(url)}"]`);
  if (existing) existing.replaceWith(card);
  else dom.summaryList.appendChild(card);

  if (dom.summariesSection) dom.summariesSection.style.display = 'block';
  if (dom.downloadBtn)      dom.downloadBtn.style.display = 'block';
}

// ── Event Handlers ────────────────────────────────────────────
function updateSummarizeBtn() {
  if (!dom.summarizeBtn) return;
  const n = state.selected.size;
  dom.summarizeBtn.disabled = n === 0 || state.isSummarizing;
  dom.summarizeBtn.textContent = n > 0
    ? `✨ 선택된 기사 요약 (${n}건)`
    : '✨ 선택된 기사 요약';
}

document.addEventListener('change', (e) => {
  if (e.target.type !== 'checkbox' || !e.target.closest('.article-card')) return;
  const url = e.target.dataset.url;
  if (!url) return;
  e.target.checked ? state.selected.add(url) : state.selected.delete(url);
  e.target.closest('.article-card').classList.toggle('selected', e.target.checked);
  updateSummarizeBtn();
});

function handleSelectAll()   { state.articles.forEach((a) => state.selected.add(a.url)); renderArticles(); }
function handleDeselectAll() { state.selected.clear(); renderArticles(); }

// ── Search ────────────────────────────────────────────────────
async function handleSearch() {
  if (state.isSearching) return;
  state.isSearching = true;
  state.selected.clear();
  state.summaries = {};
  if (dom.summariesSection) dom.summariesSection.style.display = 'none';
  if (dom.downloadBtn)      dom.downloadBtn.style.display = 'none';
  if (dom.summaryList)      dom.summaryList.innerHTML = '';

  setLoading(dom.searchBtn, true, '🔍 뉴스 검색');

  try {
    const source_configs = {};
    for (const [key, s] of Object.entries(dom.sources || {})) {
      source_configs[key] = {
        enabled:  s.en  ? s.en.checked          : true,
        keywords: s.kw  ? (s.kw.value.trim() || null) : null,
      };
    }

    const res = await apiFetch('/api/search', {
      method: 'POST',
      body: JSON.stringify({
        start_date:          dom.startDate?.value ?? '',
        end_date:            dom.endDate?.value ?? '',
        max_results:         parseInt(dom.maxResults?.value ?? '30', 10),
        use_gemini_fallback: dom.geminiFallback?.checked ?? true,
        source_configs,
      }),
    });

    const data = await res.json();
    state.articles = data.articles ?? [];
    state.sourceCounts = data.source_counts ?? {};

    if (state.articles.length === 0) {
      if (dom.emptyState) {
        dom.emptyState.innerHTML = '<div class="empty-icon">🔍</div><p>검색 결과가 없습니다. 날짜 범위를 넓혀보세요.</p>';
        dom.emptyState.style.display = 'flex';
      }
      if (dom.results) dom.results.style.display = 'none';
    } else {
      renderSourceCounts(state.sourceCounts);
      renderArticles();
    }
  } catch (err) {
    if (dom.emptyState) {
      dom.emptyState.innerHTML = `<div class="empty-icon">⚠️</div><p>검색 오류: ${escHtml(err.message)}</p>`;
      dom.emptyState.style.display = 'flex';
    }
    if (dom.results) dom.results.style.display = 'none';
  } finally {
    state.isSearching = false;
    setLoading(dom.searchBtn, false, '🔍 뉴스 검색');
  }
}

// ── Summarize ─────────────────────────────────────────────────
async function handleSummarize() {
  if (state.isSummarizing || state.selected.size === 0) return;
  state.isSummarizing = true;
  updateSummarizeBtn();

  const selectedArticles = state.articles
    .filter((a) => state.selected.has(a.url))
    .map((a) => ({ url: a.url, title: a.title }));

  if (dom.progressFill) dom.progressFill.style.width = '0%';
  if (dom.progressText) dom.progressText.textContent = '요약 준비 중...';
  if (dom.progressSection) dom.progressSection.style.display = 'block';

  try {
    const res = await apiFetch('/api/summarize', {
      method: 'POST',
      body: JSON.stringify({
        articles:      selectedArticles,
        custom_format: dom.customFormat?.value ?? '',
        model:         dom.model?.value ?? 'gemini-3-flash-preview',
      }),
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        let data;
        try { data = JSON.parse(line.slice(6)); } catch { continue; }
        if (data.type === 'progress') {
          const pct = Math.round(((data.index + 1) / data.total) * 100);
          if (dom.progressFill) dom.progressFill.style.width = `${pct}%`;
          if (dom.progressText) dom.progressText.textContent =
            `요약 중... (${data.index + 1}/${data.total}): ${data.title.slice(0, 50)}`;
        } else if (data.type === 'result') {
          state.summaries[data.url] = data.summary;
          renderSummary(data.url, data.title, data.summary);
        } else if (data.type === 'done') {
          if (dom.progressFill) dom.progressFill.style.width = '100%';
          if (dom.progressText) dom.progressText.textContent = '완료!';
          setTimeout(() => { if (dom.progressSection) dom.progressSection.style.display = 'none'; }, 1500);
        }
      }
    }
  } catch (err) {
    if (dom.progressSection) dom.progressSection.style.display = 'none';
    alert(`요약 오류: ${err.message}`);
  } finally {
    state.isSummarizing = false;
    updateSummarizeBtn();
  }
}

// ── Download ──────────────────────────────────────────────────
function handleDownload() {
  const lines = [];
  for (const article of state.articles) {
    const summary = state.summaries[article.url];
    if (!summary) continue;
    lines.push(`## ${article.title}`, `URL: ${article.url}`, '', summary, '', '─'.repeat(60), '');
  }
  if (!lines.length) return;
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' }));
  a.download = `mna_summary_${new Date().toISOString().slice(0, 10)}.txt`;
  a.click();
  URL.revokeObjectURL(a.href);
}

// ── Manual Summarize ──────────────────────────────────────────
async function handleManualSummarize() {
  const title    = $('manual-title')?.value.trim() ?? '';
  const url      = $('manual-url')?.value.trim() ?? '';
  const content  = $('manual-content')?.value.trim() ?? '';
  const statusEl = $('manual-status');
  const btn      = $('manual-summarize-btn');

  if (!content) {
    if (statusEl) { statusEl.textContent = '기사 내용을 입력해 주세요.'; statusEl.style.color = 'var(--danger)'; }
    return;
  }

  if (btn) { btn.disabled = true; btn.textContent = '요약 중...'; }
  if (statusEl) { statusEl.textContent = 'Gemini가 요약 중...'; statusEl.style.color = 'var(--text-muted)'; }

  try {
    const res = await apiFetch('/api/summarize-manual', {
      method: 'POST',
      body: JSON.stringify({
        title, url, content,
        custom_format: dom.customFormat?.value ?? '',
        model:         dom.model?.value ?? 'gemini-3-flash-preview',
      }),
    });
    const data = await res.json();
    const displayUrl   = url || `manual-${Date.now()}`;
    const displayTitle = title || url || '수동 입력 기사';
    state.summaries[displayUrl] = data.summary;
    renderSummary(displayUrl, displayTitle, data.summary);
    if (statusEl) { statusEl.textContent = '요약 완료!'; statusEl.style.color = 'var(--success, #16a34a)'; }
    setTimeout(() => { if (statusEl) statusEl.textContent = ''; }, 3000);
  } catch (err) {
    if (statusEl) { statusEl.textContent = `오류: ${err.message}`; statusEl.style.color = 'var(--danger)'; }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '✨ 요약하기'; }
  }
}

// ── Settings Modal ────────────────────────────────────────────
async function openSettings() {
  console.log('openSettings called, modal.el:', modal.el);
  if (!modal.el) {
    alert('설정 모달을 찾을 수 없습니다. 페이지를 새로고침해주세요.');
    return;
  }
  modal.el.style.display = 'flex';
  if (modal.statusEl) modal.statusEl.textContent = '';

  try {
    const res = await fetch('/api/settings');
    const data = await res.json();
    if (modal.fields.cseKey)      modal.fields.cseKey.value      = data.cse_api_key || '';
    if (modal.fields.cseCx)       modal.fields.cseCx.value       = data.cse_cx || '';
    if (modal.fields.naverId)     modal.fields.naverId.value     = data.naver_client_id || '';
    if (modal.fields.naverSecret) modal.fields.naverSecret.value = data.naver_client_secret || '';

    if (modal.gcsBar) {
      if (!data.gcs_configured) {
        modal.gcsBar.textContent = 'GCS_SETTINGS_BUCKET 환경변수가 설정되지 않아 저장할 수 없습니다.';
        modal.gcsBar.style.display = 'block';
        if (modal.saveBtn) modal.saveBtn.disabled = true;
      } else {
        modal.gcsBar.style.display = 'none';
        if (modal.saveBtn) modal.saveBtn.disabled = false;
      }
    }
  } catch (err) {
    if (modal.statusEl) modal.statusEl.textContent = `로드 실패: ${err.message}`;
  }
}

function closeSettings() {
  if (modal.el) modal.el.style.display = 'none';
}

async function saveSettings() {
  if (modal.saveBtn) modal.saveBtn.disabled = true;
  if (modal.statusEl) modal.statusEl.textContent = '저장 중...';

  try {
    const res = await apiFetch('/api/settings', {
      method: 'POST',
      body: JSON.stringify({
        cse_api_key:         modal.fields.cseKey?.value.trim()      ?? '',
        cse_cx:              modal.fields.cseCx?.value.trim()       ?? '',
        naver_client_id:     modal.fields.naverId?.value.trim()     ?? '',
        naver_client_secret: modal.fields.naverSecret?.value.trim() ?? '',
      }),
    });
    const data = await res.json();
    if (modal.statusEl) { modal.statusEl.textContent = '✓ 저장 완료'; modal.statusEl.style.color = '#16a34a'; }
    updateSourceAvailability('cse',   data.cse_available);
    updateSourceAvailability('naver', data.naver_available);
    setTimeout(() => { if (modal.statusEl) modal.statusEl.textContent = ''; closeSettings(); }, 1200);
  } catch (err) {
    if (modal.statusEl) { modal.statusEl.textContent = `오류: ${err.message}`; modal.statusEl.style.color = 'var(--danger)'; }
    if (modal.saveBtn) modal.saveBtn.disabled = false;
  }
}

// ── Init ──────────────────────────────────────────────────────
async function init() {
  // 1. DOM 레퍼런스 구성 (DOMContentLoaded 이후 보장)
  dom = {
    startDate:        $('start-date'),
    endDate:          $('end-date'),
    maxResults:       $('max-results'),
    maxResultsValue:  $('max-results-value'),
    geminiFallback:   $('gemini-fallback'),
    searchBtn:        $('search-btn'),
    model:            $('model'),
    customFormat:     $('custom-format'),
    summarizeBtn:     $('summarize-btn'),
    downloadBtn:      $('download-btn'),
    emptyState:       $('empty-state'),
    results:          $('results'),
    sourceCounts:     $('source-counts'),
    articlesTitle:    $('articles-title'),
    selectAllBtn:     $('select-all-btn'),
    deselectAllBtn:   $('deselect-all-btn'),
    articleList:      $('article-list'),
    progressSection:  $('progress-section'),
    progressText:     $('progress-text'),
    progressFill:     $('progress-fill'),
    summariesSection: $('summaries-section'),
    summaryList:      $('summary-list'),
    sources: {
      rss:   { wrap: $('src-rss'),   kw: $('kw-rss'),   en: $('en-rss')   },
      ddg:   { wrap: $('src-ddg'),   kw: $('kw-ddg'),   en: $('en-ddg')   },
      cse:   { wrap: $('src-cse'),   kw: $('kw-cse'),   en: $('en-cse')   },
      naver: { wrap: $('src-naver'), kw: $('kw-naver'), en: $('en-naver') },
    },
  };

  modal = {
    el:       $('settings-modal'),
    backdrop: $('settings-backdrop'),
    closeBtn: $('settings-close-btn'),
    saveBtn:  $('settings-save-btn'),
    statusEl: $('settings-save-status'),
    gcsBar:   $('gcs-status-bar'),
    fields: {
      cseKey:      $('s-cse-key'),
      cseCx:       $('s-cse-cx'),
      naverId:     $('s-naver-id'),
      naverSecret: $('s-naver-secret'),
    },
  };

  // 2. 기본 날짜 설정
  const today = new Date();
  const weekAgo = new Date(today);
  weekAgo.setDate(today.getDate() - 7);
  if (dom.endDate)   dom.endDate.value   = today.toISOString().slice(0, 10);
  if (dom.startDate) dom.startDate.value = weekAgo.toISOString().slice(0, 10);

  on(dom.maxResults, 'input', () => {
    if (dom.maxResultsValue) dom.maxResultsValue.textContent = dom.maxResults.value;
  });

  // 3. 이벤트 리스너를 먼저 등록 (async fetch 전에)
  on('manual-summarize-btn', 'click', handleManualSummarize);
  on('settings-btn',         'click', openSettings);
  on(modal.closeBtn,         'click', closeSettings);
  on(modal.backdrop,         'click', closeSettings);
  on(modal.saveBtn,          'click', saveSettings);

  document.querySelectorAll('.toggle-vis-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const target = $(btn.dataset.target);
      if (target) target.type = target.type === 'password' ? 'text' : 'password';
    });
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal.el?.style.display !== 'none') closeSettings();
  });

  on(dom.searchBtn,      'click', handleSearch);
  on(dom.summarizeBtn,   'click', handleSummarize);
  on(dom.downloadBtn,    'click', handleDownload);
  on(dom.selectAllBtn,   'click', handleSelectAll);
  on(dom.deselectAllBtn, 'click', handleDeselectAll);

  // 4. 설정 로드 (비동기, 위 리스너 등록 후 실행)
  try {
    const res = await fetch('/api/config');
    const config = await res.json();
    if (dom.model) {
      dom.model.innerHTML = (config.models || [])
        .map((m) => `<option value="${escHtml(m.id)}">${escHtml(m.label)}</option>`)
        .join('');
    }
    if (dom.customFormat) dom.customFormat.value = config.default_format ?? '';
    for (const [key, info] of Object.entries(config.sources || {})) {
      const s = dom.sources[key];
      if (s?.kw) s.kw.value = info.default_keywords ?? '';
      updateSourceAvailability(key, info.available);
    }
  } catch (err) {
    console.error('Config load failed:', err);
  }
}

// DOMContentLoaded 이미 지난 경우도 처리
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
