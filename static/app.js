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

const ARTICLE_SUMMARY_BATCH_SIZE = 5;

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

// ── Deal Grouping ─────────────────────────────────────────────

const DEAL_PATTERNS = [
  /([A-Z][A-Za-z\s&'.,-]+)\s+(?:to\s+acquire|acquir| übernimmt| acquires|compra|매수|인수|합병|인수합병)\s+([A-Z][A-Za-z\s&'.,-]+)/i,
  /([A-Z][A-Za-z\s&'.,-]+)\s+(?:to\s+divest|divest|sells?|매각|매도|양도)\s+([A-Z][A-Za-z\s&'.,-]+)/i,
  /([A-Z][A-Za-z\s&'.,-]+)\s+(?:joint\s+venture|M&A|merger|합병)\s+(?:with\s+)?([A-Z][A-Za-z\s&'.,-]+)/i,
  /([A-Z][A-Za-z\s&'.,-]+)\s+(?:and|c와|과)\s+([A-Z][A-Za-z\s&'.,-]+)\s+(?:in\s+)?(?:a\s+)?(?:deal|transaction)/i,
];

function extractDealKey(title) {
  for (const pattern of DEAL_PATTERNS) {
    const match = title.match(pattern);
    if (match && match[1] && match[2]) {
      const a = match[1].trim().toLowerCase().replace(/\s+/g, ' ');
      const b = match[2].trim().toLowerCase().replace(/\s+/g, ' ');
      return [a, b].sort().join('|||');
    }
  }
  return null;
}

function extractCompanies(title) {
  for (const pattern of DEAL_PATTERNS) {
    const match = title.match(pattern);
    if (match && match[1] && match[2]) {
      return { companyA: match[1].trim(), companyB: match[2].trim() };
    }
  }
  return null;
}

function groupArticlesByDeal(articles) {
  const deals = new Map();
  const ungrouped = [];

  for (const article of articles) {
    const dealKey = extractDealKey(article.title);
    if (dealKey) {
      if (!deals.has(dealKey)) {
        const companies = extractCompanies(article.title);
        deals.set(dealKey, {
          key: dealKey,
          companyA: companies?.companyA || 'Unknown',
          companyB: companies?.companyB || 'Unknown',
          articles: [],
          sources: new Set(),
        });
      }
      const deal = deals.get(dealKey);
      deal.articles.push(article);
      if (article.search_source) deal.sources.add(article.search_source);
    } else {
      ungrouped.push(article);
    }
  }

  return {
    deals: Array.from(deals.values()).sort((a, b) => b.articles.length - a.articles.length),
    ungrouped,
  };
}

function renderDealCard(deal, index) {
  const sourceBadges = Array.from(deal.sources).map(src =>
    `<span class="article-src-badge ${sourceBadgeClass(src)}">${sourceBadgeLabel(src)}</span>`
  ).join('');

  // Check if all articles in this deal are selected
  const allSelected = deal.articles.every(a => state.selected.has(a.url));
  const dealKey = `deal-${index}`;

  return `
    <div class="deal-card" data-deal-index="${index}">
      <div class="deal-header" onclick="toggleDeal(${index})">
        <div class="deal-info">
          <input type="checkbox" class="deal-select-all" id="${dealKey}" ${allSelected ? 'checked' : ''}
                 onchange="handleDealSelectAll(${index}, this.checked)"
                 onclick="event.stopPropagation()">
          <div class="deal-select-label">
            <span class="deal-icon">🤝</span>
            <div class="deal-companies">
              <span class="deal-company">${escHtml(deal.companyA)}</span>
              <span class="deal-arrow">→</span>
              <span class="deal-company">${escHtml(deal.companyB)}</span>
            </div>
            <span class="deal-count">${deal.articles.length}건</span>
          </div>
        </div>
        <div class="deal-meta">
          ${sourceBadges}
          <span class="deal-expand-icon" id="deal-icon-${index}">▼</span>
        </div>
      </div>
      <div class="deal-articles" id="deal-articles-${index}" style="display:none">
        ${deal.articles.map(a => renderArticleItem(a)).join('')}
      </div>
    </div>`;
}

function handleDealSelectAll(dealIndex, checked) {
  const deal = groupArticlesByDeal(state.articles).deals[dealIndex];
  if (!deal) return;
  
  deal.articles.forEach(a => {
    if (checked) {
      state.selected.add(a.url);
    } else {
      state.selected.delete(a.url);
    }
  });
  
  renderArticles();
  updateSummarizeBtn();
}

window.handleDealSelectAll = handleDealSelectAll;

function renderArticleItem(a) {
  const srcClass = sourceBadgeClass(a.search_source);
  const srcLabel = sourceBadgeLabel(a.search_source);
  const isSelected = state.selected.has(a.url);
  return `
    <div class="article-card${isSelected ? ' selected' : ''}" data-url="${escHtml(a.url)}">
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
}

function renderUngroupedArticle(a, globalIndex) {
  const srcClass = sourceBadgeClass(a.search_source);
  const srcLabel = sourceBadgeLabel(a.search_source);
  const isSelected = state.selected.has(a.url);
  return `
    <div class="article-card${isSelected ? ' selected' : ''}" data-idx="${globalIndex}">
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
}

function toggleDeal(index) {
  const articlesDiv = document.getElementById(`deal-articles-${index}`);
  const icon = document.getElementById(`deal-icon-${index}`);
  if (!articlesDiv) return;
  
  if (articlesDiv.style.display === 'none') {
    articlesDiv.style.display = 'block';
    if (icon) icon.textContent = '▲';
  } else {
    articlesDiv.style.display = 'none';
    if (icon) icon.textContent = '▼';
  }
}

window.toggleDeal = toggleDeal;

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
  
  // 딜 그룹핑
  const { deals, ungrouped } = groupArticlesByDeal(articles);
  
  if (dom.articlesTitle) {
    if (deals.length > 0) {
      dom.articlesTitle.textContent = `📊 딜 ${deals.length}개 · 기사 ${articles.length}건`;
    } else {
      dom.articlesTitle.textContent = `기사 목록 (${articles.length}건)`;
    }
  }

  let html = '';
  
  // 딜 카드 렌더링
  deals.forEach((deal, index) => {
    html += renderDealCard(deal, index);
  });
  
  // 그룹화되지 않은 기스는 일반 목록으로
  if (ungrouped.length > 0) {
    if (deals.length > 0) {
      html += `<div class="ungrouped-header">📰 개별 기사 (${ungrouped.length}건)</div>`;
    }
    ungrouped.forEach((a, i) => {
      html += renderUngroupedArticle(a, i);
    });
  }

  dom.articleList.innerHTML = html;

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
    let enabledCount = 0;
    for (const [key, s] of Object.entries(dom.sources || {})) {
      const enabled = s.en ? s.en.checked : true;
      source_configs[key] = {
        enabled,
        keywords: s.kw ? (s.kw.value.trim() || null) : null,
      };
      if (enabled) enabledCount++;
    }

    let maxResults = parseInt(dom.maxResults?.value ?? '100', 10);
    const equalPerSource = dom.equalPerSource?.checked ?? false;
    
    // 소스별 동일 수 할당 시 per_source_max_results 계산
    let perSourceMax = null;
    if (equalPerSource && enabledCount > 0) {
      perSourceMax = Math.floor(maxResults / enabledCount);
      maxResults = perSourceMax * enabledCount; // 실제 총합
    }

    const res = await apiFetch('/api/search', {
      method: 'POST',
      body: JSON.stringify({
        start_date:          dom.startDate?.value ?? '',
        end_date:            dom.endDate?.value ?? '',
        max_results:         maxResults,
        use_gemini_fallback: dom.geminiFallback?.checked ?? true,
        source_configs,
        equal_per_source:     equalPerSource,
        per_source_max:      perSourceMax,
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

  if (dom.progressFill) dom.progressFill.style.width = '0%';
  if (dom.progressText) dom.progressText.textContent = '요약 준비 중...';
  if (dom.progressSection) dom.progressSection.style.display = 'block';

  try {
    const selectedArticles = state.articles
      .filter((a) => state.selected.has(a.url))
      .map((a) => ({ url: a.url, title: a.title }));

    // Check if we have deal-based selection
    const { deals, ungrouped } = groupArticlesByDeal(state.articles);
    const selectedDeals = deals.filter(deal => 
      deal.articles.some(a => state.selected.has(a.url))
    );

    if (selectedDeals.length > 0) {
      // Deal-based summarization
      await summarizeDeals(selectedDeals, selectedArticles);
    } else {
      // Individual article summarization
      await summarizeArticles(selectedArticles);
    }
  } catch (err) {
    if (dom.progressSection) dom.progressSection.style.display = 'none';
    alert(`요약 오류: ${err.message}`);
  } finally {
    state.isSummarizing = false;
    updateSummarizeBtn();
  }
}

async function summarizeDeals(selectedDeals, selectedArticles) {
  const customFormat = dom.customFormat?.value ?? '';
  const model = dom.model?.value ?? 'gemini-3-flash-preview';
  
  // Count total items (deals + individual articles)
  const dealCount = selectedDeals.length;
  const ungroupedCount = selectedArticles.filter(a => {
    return !selectedDeals.some(d => d.articles.some(a2 => a2.url === a.url));
  }).length;
  const total = dealCount + ungroupedCount;
  let processed = 0;

  for (const deal of selectedDeals) {
    const dealArticles = deal.articles.filter(a => state.selected.has(a.url));
    const dealTitle = `${deal.companyA} → ${deal.companyB}`;

    // Progress update
    if (dom.progressFill) dom.progressFill.style.width = `${Math.round(processed / total * 100)}%`;
    if (dom.progressText) dom.progressText.textContent = `딜 요약 중... (${processed + 1}/${total}): ${dealTitle}`;

    try {
      const res = await apiFetch('/api/summarize-deal', {
        method: 'POST',
        body: JSON.stringify({
          deal_key: deal.key,
          deal_title: dealTitle,
          articles: dealArticles.map(a => ({ url: a.url, title: a.title })),
          custom_format: customFormat,
          model: model,
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
          if (data.type === 'result') {
            state.summaries[data.url] = data.summary;
            renderSummary(data.url, data.title, data.summary);
          }
        }
      }
    } catch (err) {
      console.error('Deal summarization error:', err);
    }
    processed++;
  }

  // Handle ungrouped articles
  const ungrouped = selectedArticles.filter(a => {
    return !selectedDeals.some(d => d.articles.some(a2 => a2.url === a.url));
  });

  if (ungrouped.length > 0) {
    await summarizeArticles(ungrouped, processed, total);
  } else {
    if (dom.progressFill) dom.progressFill.style.width = '100%';
    if (dom.progressText) dom.progressText.textContent = '완료!';
    setTimeout(() => { if (dom.progressSection) dom.progressSection.style.display = 'none'; }, 1500);
  }
}

async function summarizeArticles(articles, startIndex = 0, total = articles.length) {
  if (articles.length === 0) return;

  const customFormat = dom.customFormat?.value ?? '';
  const model = dom.model?.value ?? 'gemini-3-flash-preview';

  for (let batchStart = 0; batchStart < articles.length; batchStart += ARTICLE_SUMMARY_BATCH_SIZE) {
    const batch = articles.slice(batchStart, batchStart + ARTICLE_SUMMARY_BATCH_SIZE);

    try {
      const res = await apiFetch('/api/summarize', {
        method: 'POST',
        body: JSON.stringify({
          articles: batch,
          custom_format: customFormat,
          model: model,
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
            const absoluteIndex = startIndex + batchStart + data.index + 1;
            const pct = Math.round((absoluteIndex / total) * 100);
            if (dom.progressFill) dom.progressFill.style.width = `${pct}%`;
            if (dom.progressText) dom.progressText.textContent =
              `요약 중... (${absoluteIndex}/${total}): ${data.title.slice(0, 50)}`;
          } else if (data.type === 'result') {
            state.summaries[data.url] = data.summary;
            renderSummary(data.url, data.title, data.summary);
          }
        }
      }
    } catch (err) {
      throw err;
    }
  }

  if (dom.progressFill) dom.progressFill.style.width = '100%';
  if (dom.progressText) dom.progressText.textContent = '완료!';
  setTimeout(() => { if (dom.progressSection) dom.progressSection.style.display = 'none'; }, 1500);
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
  const titleEl = $('manual-title');
  const urlEl   = $('manual-url');
  const contentEl = $('manual-content');

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
    
    // Clear inputs for next use
    if (titleEl)   titleEl.value = '';
    if (urlEl)     urlEl.value = '';
    if (contentEl) contentEl.value = '';
    
    setTimeout(() => { if (statusEl) statusEl.textContent = ''; }, 3000);
  } catch (err) {
    if (statusEl) { statusEl.textContent = `오류: ${err.message}`; statusEl.style.color = 'var(--danger)'; }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '✨ 요약하기'; }
  }
}

// ── Settings Modal ────────────────────────────────────────────
async function openSettings() {
  if (!modal.el) return;
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
    equalPerSource:   $('equal-per-source'),
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
