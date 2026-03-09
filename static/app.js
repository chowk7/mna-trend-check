'use strict';

// ── State ─────────────────────────────────────────────────────
const state = {
  articles: [],
  sourceCounts: {},
  summaries: {},      // url → summary text
  selected: new Set(),
  isSearching: false,
  isSummarizing: false,
};

// ── DOM refs ──────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

const dom = {
  startDate:        $('start-date'),
  endDate:          $('end-date'),
  maxResults:       $('max-results'),
  maxResultsValue:  $('max-results-value'),
  keywords:         $('keywords'),
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
};

// ── Utilities ─────────────────────────────────────────────────
function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function sourceBadgeClass(src) {
  if (src === 'DuckDuckGo')    return 'badge-ddg';
  if (src === 'Google News RSS') return 'badge-rss';
  if (src === 'Gemini Search')  return 'badge-gemini';
  return '';
}

function sourceBadgeLabel(src) {
  if (src === 'DuckDuckGo')    return 'DDG';
  if (src === 'Google News RSS') return 'RSS';
  if (src === 'Gemini Search')  return 'Gemini';
  return src;
}

function setLoading(btn, loading, originalText) {
  if (loading) {
    btn.disabled = true;
    btn.dataset.orig = originalText || btn.textContent;
    btn.innerHTML = `<span class="spinner"></span> ${btn.dataset.orig.replace(/^[^\s]+\s/, '')}...`;
  } else {
    btn.disabled = false;
    btn.textContent = btn.dataset.orig || originalText;
  }
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

// ── Render: Source Counts ─────────────────────────────────────
function renderSourceCounts(counts) {
  const parts = Object.entries(counts)
    .filter(([, n]) => n > 0)
    .map(([src, n]) =>
      `<span class="source-badge ${sourceBadgeClass(src)}">${sourceBadgeLabel(src)} ${n}건</span>`
    );

  if (parts.length === 0) {
    dom.sourceCounts.style.display = 'none';
    return;
  }

  dom.sourceCounts.innerHTML =
    `<span class="source-counts-label">검색 소스</span>` + parts.join('');
  dom.sourceCounts.style.display = 'flex';
}

// ── Render: Articles ──────────────────────────────────────────
function renderArticles() {
  const articles = state.articles;
  dom.articlesTitle.textContent = `기사 목록 (${articles.length}건)`;

  dom.articleList.innerHTML = articles.map((a, i) => {
    const srcClass = sourceBadgeClass(a.search_source);
    const srcLabel = sourceBadgeLabel(a.search_source);
    const isSelected = state.selected.has(a.url);

    return `
      <div class="article-card${isSelected ? ' selected' : ''}" data-idx="${i}">
        <input type="checkbox" data-url="${escHtml(a.url)}"${isSelected ? ' checked' : ''}>
        <div class="article-body">
          <div class="article-meta">
            ${a.search_source
              ? `<span class="article-src-badge ${srcClass}">${srcLabel}</span>`
              : ''}
            ${a.source
              ? `<span class="article-source">${escHtml(a.source)}</span>`
              : ''}
            ${a.published
              ? `<span class="article-date">${escHtml(a.published)}</span>`
              : ''}
          </div>
          <a class="article-title" href="${escHtml(a.url)}" target="_blank" rel="noopener noreferrer">
            ${escHtml(a.title)}
          </a>
          ${a.snippet
            ? `<p class="article-snippet">${escHtml(a.snippet)}</p>`
            : ''}
        </div>
      </div>`;
  }).join('');

  dom.results.style.display = 'block';
  dom.emptyState.style.display = 'none';
  updateSummarizeBtn();
}

// ── Render: Summary Card ──────────────────────────────────────
function renderSummary(url, title, summary) {
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
    const text = state.summaries[url] ?? '';
    navigator.clipboard.writeText(text).then(() => {
      this.textContent = '✓ 복사됨';
      setTimeout(() => { this.textContent = '복사'; }, 2000);
    });
  });

  const existing = dom.summaryList.querySelector(`[data-url="${CSS.escape(url)}"]`);
  if (existing) {
    existing.replaceWith(card);
  } else {
    dom.summaryList.appendChild(card);
  }

  dom.summariesSection.style.display = 'block';
  dom.downloadBtn.style.display = 'block';
}

// ── Event Handlers ────────────────────────────────────────────
function updateSummarizeBtn() {
  const n = state.selected.size;
  dom.summarizeBtn.disabled = n === 0 || state.isSummarizing;
  dom.summarizeBtn.textContent = n > 0
    ? `✨ 선택된 기사 요약 (${n}건)`
    : '✨ 선택된 기사 요약';
}

// Article checkbox delegation
document.addEventListener('change', (e) => {
  if (e.target.type !== 'checkbox' || !e.target.closest('.article-card')) return;
  const url = e.target.dataset.url;
  if (!url) return;
  if (e.target.checked) {
    state.selected.add(url);
  } else {
    state.selected.delete(url);
  }
  e.target.closest('.article-card').classList.toggle('selected', e.target.checked);
  updateSummarizeBtn();
});

function handleSelectAll() {
  state.articles.forEach((a) => state.selected.add(a.url));
  renderArticles();
}

function handleDeselectAll() {
  state.selected.clear();
  renderArticles();
}

// ── Search ────────────────────────────────────────────────────
async function handleSearch() {
  if (state.isSearching) return;
  state.isSearching = true;
  state.selected.clear();
  state.summaries = {};
  dom.summariesSection.style.display = 'none';
  dom.downloadBtn.style.display = 'none';
  dom.summaryList.innerHTML = '';

  setLoading(dom.searchBtn, true, '🔍 뉴스 검색');

  try {
    const res = await apiFetch('/api/search', {
      method: 'POST',
      body: JSON.stringify({
        start_date: dom.startDate.value,
        end_date:   dom.endDate.value,
        max_results: parseInt(dom.maxResults.value, 10),
        keywords: dom.keywords.value.trim() || null,
        use_gemini_fallback: dom.geminiFallback.checked,
      }),
    });

    const data = await res.json();
    state.articles = data.articles ?? [];
    state.sourceCounts = data.source_counts ?? {};

    if (state.articles.length === 0) {
      dom.emptyState.innerHTML =
        '<div class="empty-icon">🔍</div><p>검색 결과가 없습니다. 날짜 범위를 넓혀보세요.</p>';
      dom.emptyState.style.display = 'flex';
      dom.results.style.display = 'none';
    } else {
      renderSourceCounts(state.sourceCounts);
      renderArticles();
    }
  } catch (err) {
    dom.emptyState.innerHTML =
      `<div class="empty-icon">⚠️</div><p>검색 오류: ${escHtml(err.message)}</p>`;
    dom.emptyState.style.display = 'flex';
    dom.results.style.display = 'none';
  } finally {
    state.isSearching = false;
    setLoading(dom.searchBtn, false, '🔍 뉴스 검색');
  }
}

// ── Summarize (SSE streaming) ─────────────────────────────────
async function handleSummarize() {
  if (state.isSummarizing || state.selected.size === 0) return;
  state.isSummarizing = true;
  updateSummarizeBtn();

  const selectedArticles = state.articles
    .filter((a) => state.selected.has(a.url))
    .map((a) => ({ url: a.url, title: a.title }));

  dom.progressFill.style.width = '0%';
  dom.progressText.textContent = '요약 준비 중...';
  dom.progressSection.style.display = 'block';

  try {
    const res = await apiFetch('/api/summarize', {
      method: 'POST',
      body: JSON.stringify({
        articles: selectedArticles,
        custom_format: dom.customFormat.value,
        model: dom.model.value,
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
      buffer = lines.pop(); // keep last (possibly incomplete) line

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        let data;
        try {
          data = JSON.parse(line.slice(6));
        } catch {
          continue;
        }

        switch (data.type) {
          case 'progress': {
            const pct = Math.round(((data.index + 1) / data.total) * 100);
            dom.progressFill.style.width = `${pct}%`;
            dom.progressText.textContent =
              `요약 중... (${data.index + 1}/${data.total}): ${data.title.slice(0, 50)}`;
            break;
          }
          case 'result': {
            state.summaries[data.url] = data.summary;
            renderSummary(data.url, data.title, data.summary);
            break;
          }
          case 'done': {
            dom.progressFill.style.width = '100%';
            dom.progressText.textContent = '완료!';
            setTimeout(() => { dom.progressSection.style.display = 'none'; }, 1500);
            break;
          }
        }
      }
    }
  } catch (err) {
    dom.progressSection.style.display = 'none';
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
    lines.push(`## ${article.title}`);
    lines.push(`URL: ${article.url}`);
    lines.push('');
    lines.push(summary);
    lines.push('');
    lines.push('─'.repeat(60));
    lines.push('');
  }
  if (lines.length === 0) return;

  const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `mna_summary_${new Date().toISOString().slice(0, 10)}.txt`;
  a.click();
  URL.revokeObjectURL(a.href);
}

// ── Init ──────────────────────────────────────────────────────
async function init() {
  // Default dates: last 7 days
  const today = new Date();
  const weekAgo = new Date(today);
  weekAgo.setDate(today.getDate() - 7);
  dom.endDate.value   = today.toISOString().slice(0, 10);
  dom.startDate.value = weekAgo.toISOString().slice(0, 10);

  // Range slider display
  dom.maxResults.addEventListener('input', () => {
    dom.maxResultsValue.textContent = dom.maxResults.value;
  });

  // Load config from server
  try {
    const res = await fetch('/api/config');
    const config = await res.json();

    // Populate model dropdown
    dom.model.innerHTML = config.models
      .map((m) => `<option value="${escHtml(m.id)}">${escHtml(m.label)}</option>`)
      .join('');

    dom.keywords.value     = config.default_keywords ?? '';
    dom.customFormat.value = config.default_format ?? '';
  } catch (err) {
    console.error('Config load failed:', err);
    dom.keywords.value = '"to acquire" OR "to divest" OR "joint venture"';
  }

  // Event listeners
  dom.searchBtn.addEventListener('click', handleSearch);
  dom.summarizeBtn.addEventListener('click', handleSummarize);
  dom.downloadBtn.addEventListener('click', handleDownload);
  dom.selectAllBtn.addEventListener('click', handleSelectAll);
  dom.deselectAllBtn.addEventListener('click', handleDeselectAll);

  // Ctrl+Enter in keywords triggers search
  dom.keywords.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleSearch();
  });
}

document.addEventListener('DOMContentLoaded', init);
