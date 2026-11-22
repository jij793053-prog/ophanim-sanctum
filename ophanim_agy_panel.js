/* ============================================================================
 * ophanim_agy_panel.js
 * Dual-Mode Antigravity Agent Beautification Suite + AI Usage Telemetry Engine
 * for Ophanim Sanctum:
 *   1. Mode B (Top-Left Launcher -> Left Slide-Out Dual-Column Agent Workbench)
 *   2. Mode A (Classic Right-Half Session List + Center-Locked Resizable Core Modal)
 *   3. Strict True-Completion Radiant White Sphere Tracker + Auto-Locate +
 *      Multi-Completed Columns (`已完成栏目`) — zero false triggers on queued turns
 *   4. Queue vs Immediate Jump-Queue (`排队发送` / `插队送入` + per-turn flush/cancel)
 *   5. Interactive Attachment & File Chips (Left-click: Open File, Right-click: Locate)
 *   6. Antigravity-Grade Hierarchical Markdown Typography
 *   7. Full Local `AI Usage` Dashboard mounted in BOTH `3 · 遥测与额度` AND `#ornamental-deck`
 *   8. 60fps Tortoise-Smooth Token Velocity Canvas Loop
 * ============================================================================ */
(function () {
  'use strict';

  const STORAGE_LAST_CID_KEY = 'ophanim_agy_active_cid_v1';
  const STORAGE_MODAL_SIZE_KEY = 'ophanim_core_modal_size_v1';
  const HTTP_API_BASE = window.location.protocol === 'file:' ? 'http://127.0.0.1:18790' : '';
  const USD_TO_CNY = 7.25;
  const IS_WALLPAPER_VIEW = window.location.search.indexOf('wallpaper=1') !== -1;

  // Pure Monochrome Inline SVG Icons (never falls back to Windows colored Segoe UI Emoji!)
  const ICON_BOLT = '<svg class="agy-mono-svg" viewBox="0 0 16 16" aria-hidden="true"><path d="M9.2 1.2L3.3 9.1h4.1l-.6 5.7 5.9-7.9H8.6l.6-5.7z" fill="currentColor"/></svg>';
  const ICON_STOP = '<svg class="agy-mono-svg" viewBox="0 0 16 16" aria-hidden="true"><rect x="3.2" y="3.2" width="9.6" height="9.6" rx="1.1" fill="currentColor"/></svg>';
  const ICON_QUEUE = '<svg class="agy-mono-svg" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 2h8M4 14h8M5 2c0 3.2 3 4.2 3 6s-3 2.8-3 6M11 2c0 3.2-3 4.2-3 6s3 2.8 3 6" fill="none" stroke="currentColor" stroke-width="1.45" stroke-linecap="round"/></svg>';
  const ICON_GEAR = '<svg class="agy-mono-svg" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="2.2" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M8 1.6v1.8M8 12.6v1.8M1.6 8h1.8M12.6 8h1.8M3.5 3.5l1.3 1.3M11.2 11.2l1.3 1.3M12.5 3.5l-1.3 1.3M4.8 11.2l-1.3 1.3" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>';
  const ICON_WARN = '<svg class="agy-mono-svg" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2.1L14.5 13.5H1.5L8 2.1z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M8 6.2v3.6M8 11.8h.01" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>';

  // Latest-turn header-anchored scroll stickiness for chronological streams (oldest #1 at top -> newest #N at bottom,
  // opening/switching aligns the newest turn's [第 N 轮] title header cleanly at the top of the viewport!)
  const streamStickBottom = {
    'agy-chat-stream': true,
    'agy-wb-chat-stream': true
  };

  function getOffsetTopWithin(el, child) {
    let y = 0;
    let node = child;
    while (node && node !== el) {
      y += node.offsetTop || 0;
      node = node.offsetParent;
    }
    if (node === el) return y;
    return el.scrollTop + (child.getBoundingClientRect().top - el.getBoundingClientRect().top);
  }

  function computeTurnCardTargetScrollTop(el, card) {
    if (!el || !card) return el ? el.scrollHeight : 0;
    const padTop = parseFloat(window.getComputedStyle(el).paddingTop) || 12;
    const cardTop = getOffsetTopWithin(el, card);
    const rawTarget = cardTop - Math.max(8, padTop - 2);
    const maxScroll = Math.max(0, el.scrollHeight - el.clientHeight);
    return Math.max(0, Math.min(maxScroll, rawTarget));
  }

  function computeLatestTurnTargetScrollTop(el) {
    if (!el) return 0;
    const cards = el.querySelectorAll('.agy-turn-card');
    if (!cards || cards.length === 0) return Math.max(0, el.scrollHeight - el.clientHeight);
    return computeTurnCardTargetScrollTop(el, cards[cards.length - 1]);
  }

  function snapStreamElToBottomNow(sid) {
    const el = document.getElementById(sid);
    if (!el) return;
    el.scrollTop = computeLatestTurnTargetScrollTop(el);
  }

  function scheduleSnapStreamsToBottom(streamIds) {
    const ids = Array.isArray(streamIds) ? streamIds : ['agy-chat-stream', 'agy-wb-chat-stream'];
    ids.forEach(function (sid) {
      streamStickBottom[sid] = true;
      snapStreamElToBottomNow(sid);
    });
    requestAnimationFrame(function () {
      ids.forEach(snapStreamElToBottomNow);
    });
    [65, 190, 390].forEach(function (delayMs) {
      setTimeout(function () {
        ids.forEach(function (sid) {
          if (streamStickBottom[sid]) snapStreamElToBottomNow(sid);
        });
      }, delayMs);
    });
  }

  // Universal Emoji-to-Monochrome HTML Wrapper (skips all <...> HTML tags, forces grayscale on any emoji glyph in text)
  const EMOJI_OR_TAG_RE = /(<[^>]*>)|((?:[\u231A-\u23FA\u2600-\u27BF\u2B50\u2B55]|\uD83C[\uDC00-\uDFFF]|\uD83D[\uDC00-\uDFFF]|\uD83E[\uDD00-\uDFFF])(?:\uFE0F|\u200D(?:[\u2600-\u27BF]|\uD83C[\uDC00-\uDFFF]|\uD83D[\uDC00-\uDFFF]|\uD83E[\uDD00-\uDFFF]))*)/g;
  function monochromizeEmojis(htmlStr) {
    if (!htmlStr) return '';
    return String(htmlStr).replace(EMOJI_OR_TAG_RE, function (full, tag, emojiSeq) {
      if (tag) return tag;
      return '<span class="mono-emoji">' + emojiSeq + '</span>';
    });
  }

  let activeWS = null;
  let conversations = [];
  let currentCid = '';
  let isDraftNew = false;
  let currentStatus = 'idle';

  // Right-half classic session panel & mutual collapse with #codex-panel
  let panelVisible = false;
  let codexBodyCollapsed = false;
  let savedCodexWidthPx = 382;
  // Left slide-out Agent Workbench state (`workbenchMainExpanded` defaults FALSE so opening shows ONLY session list first!)
  let workbenchOpen = false;
  let workbenchMainExpanded = false;
  let workbenchRightPane = 'chat'; // 'chat' | 'settings'
  let workbenchSettingsTab = 'quick'; // 'quick' | 'codex' | 'telemetry' | 'wallpaper'
  let workbenchWidthPx = 860;
  let workbenchSidebarWidthPx = 268;
  let activeAgentBrandName = 'ANTIGRAVITY AGENT';
  let showArchivedList = false;

  // Center-locked symmetric Core Modal user size
  let coreModalWidthPx = 0;
  let coreModalHeightPx = 0;
  (function loadSavedCoreModalSize() {
    try {
      const raw = window.localStorage.getItem(STORAGE_MODAL_SIZE_KEY);
      if (raw) {
        const obj = JSON.parse(raw);
        if (obj && Number(obj.w) >= 620) coreModalWidthPx = Number(obj.w);
        if (obj && Number(obj.h) >= 440) coreModalHeightPx = Number(obj.h);
      }
    } catch (err) { /* ignore */ }
  })();

  // Send mode ('queue' | 'interrupt')
  let composerSendMode = 'queue';
  let isSending = false;
  let lastSnapshot = null;
  const MAX_TRACKED_CIDS = 200;
  const MAX_SEEN_COMPLETED_KEYS = 200;
  const MAX_EXPANDED_TURN_KEYS = 200;
  const MAX_LOCAL_ATT_PATH_KEYS = 100;

  const expandedTurnKeys = new Set();
  const lastSeenTurnNumByCid = {};
  const maxCompletedTurnByCid = {};
  let pendingScrollTurnKey = '';

  // Shared attachment state (synced across both Core Modal & Left Workbench composers)
  let pendingAttachments = [];
  // Cache staged paths by cid + turnNumber so optimistic attachment chips remain clickable
  const localTurnAttachmentPaths = {};
  let coreDragDepth = 0;
  let wbDragDepth = 0;

  // ==========================================================================
  // Strict True-Completion Tracking (ONLY after full final assistant text output!)
  // ==========================================================================
  let hasSeededInitialCompletions = false;
  const seenCompletedTurnKeys = new Set(); // `${cid}:${turnNumber}` (bounded LRU <= 200)
  const unreadWhiteSphereKeys = new Set(); // Keys currently lighting the 3D White Sphere
  let completedTaskColumns = []; // Array of { key, cid, convTitle, turnNumber, turnTitle, snippet, ts }
  let activeCompletedColKey = '';

  function addBoundedSetKey(setObj, key, maxEntries) {
    if (!key) return;
    if (setObj.has(key)) setObj.delete(key);
    setObj.add(key);
    while (setObj.size > maxEntries) {
      const oldest = setObj.values().next().value;
      if (oldest === undefined) break;
      setObj.delete(oldest);
    }
  }

  function addSeenCompletedTurnKey(key) {
    addBoundedSetKey(seenCompletedTurnKeys, key, MAX_SEEN_COMPLETED_KEYS);
  }

  function setBoundedMapEntry(mapObj, key, val, maxEntries) {
    if (!key) return;
    if (Object.prototype.hasOwnProperty.call(mapObj, key)) {
      delete mapObj[key];
    }
    mapObj[key] = val;
    const keys = Object.keys(mapObj);
    if (keys.length > maxEntries) {
      const excess = keys.length - maxEntries;
      for (let i = 0; i < excess; i++) {
        delete mapObj[keys[i]];
      }
    }
  }

  function pruneMapByLiveIds(mapObj, liveIds, maxEntries) {
    const keys = Object.keys(mapObj);
    if (keys.length <= maxEntries) return;
    for (let i = 0; i < keys.length && Object.keys(mapObj).length > maxEntries; i++) {
      if (!liveIds.has(keys[i])) {
        delete mapObj[keys[i]];
      }
    }
    const rem = Object.keys(mapObj);
    if (rem.length > maxEntries) {
      const excess = rem.length - maxEntries;
      for (let i = 0; i < excess; i++) {
        delete mapObj[rem[i]];
      }
    }
  }

  // Context menu target
  let ctxMenuCid = '';

  // ==========================================================================
  // AI Usage Shared State (mounted in BOTH Workbench Telemetry & Ornamental Deck)
  // ==========================================================================
  const aiUsageState = {
    loading: false,
    loadedOnce: false,
    error: '',
    overview: null,
    sessions: null,
    tab: 'overview', // 'overview' | 'sessions'
    period: 'all', // 'today' | 'yesterday' | 'week' | 'month' | 'all' | 'YYYY-MM-DD'
    calOpen: false,
    calMonth: '', // 'YYYY-MM'
    unitMode: 'tokens', // 'tokens' | 'quota' | 'usd'
    showCompHelp: false,
    trendGran: 'day', // 'day' | 'month' | 'year'
    trendOffset: 0,
    sessSort: 'recent', // 'recent' | 'total' | 'avg_turn'
    expandedSessIds: new Set(),
    turnsBySessId: {},
    loadingTurnsIds: new Set(),
    liveNowExpanded: true,
    lastFetchMs: 0
  };

  function formatBytes(bytes) {
    const b = Number(bytes) || 0;
    if (b < 1024) return b + ' B';
    if (b < 1024 * 1024) return (b / 1024).toFixed(1) + ' KB';
    return (b / (1024 * 1024)).toFixed(2) + ' MB';
  }

  function escapeHtml(str) {
    return String(str == null ? '' : str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function formatRelTime(isoStr, epochSec) {
    let ts = Number(epochSec) || 0;
    if (!ts && isoStr) {
      const parsed = Date.parse(isoStr);
      if (!isNaN(parsed)) ts = parsed / 1000;
    }
    if (!ts) return '';
    const diff = Math.max(0, Date.now() / 1000 - ts);
    if (diff < 35) return '刚刚';
    if (diff < 3600) return Math.floor(diff / 60) + 'm';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h';
    const d = new Date(ts * 1000);
    return String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }

  function fmtCnTokens(n) {
    const v = Math.max(0, Number(n) || 0);
    if (v >= 1e8) return { num: (v / 1e8).toFixed(2), unit: '亿', full: (v / 1e8).toFixed(2) + ' 亿' };
    if (v >= 1e4) {
      const w = v / 1e4;
      const s = w >= 100 ? Math.round(w).toLocaleString() : w.toFixed(1);
      return { num: s, unit: '万', full: s + ' 万' };
    }
    return { num: Math.round(v).toLocaleString(), unit: '', full: Math.round(v).toLocaleString() };
  }

  function fmtResetCountdown(isoStr) {
    if (!isoStr) return '';
    const t = Date.parse(isoStr);
    if (isNaN(t)) return '';
    const diffSec = Math.max(0, Math.floor((t - Date.now()) / 1000));
    if (diffSec <= 0) return '即将重置';
    const d = Math.floor(diffSec / 86400);
    const h = Math.floor((diffSec % 86400) / 3600);
    const m = Math.floor((diffSec % 3600) / 60);
    if (d > 0) return d + '天' + h + '小时后重置';
    if (h > 0) return h + '小时' + m + '分后重置';
    return m + '分钟后重置';
  }

  // ==========================================================================
  // Local File Action Dispatcher (Left-Click = Open File, Right-Click = Open Location)
  // ==========================================================================
  function triggerLocalFileAction(actionName, rawPath, displayFile) {
    const cleanPath = String(rawPath || '').trim();
    const fname = String(displayFile || cleanPath.split(/[\\/]/).pop() || '文件').trim();
    if (!cleanPath && !fname) return;
    const payload = {
      type: 'ophanim_file_action',
      action: actionName === 'open_file' ? 'open_file' : 'open_location',
      file: fname,
      path: cleanPath
    };
    if (activeWS && activeWS.readyState === 1) {
      try {
        activeWS.send(JSON.stringify(payload));
        return;
      } catch (err) { /* fallback to HTTP */ }
    }
    fetch(HTTP_API_BASE + '/api/file-action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).catch(function () {});
  }

  // ==========================================================================
  // Antigravity-Grade Structured Markdown Formatter
  // ==========================================================================
  function formatInlineMarkdown(escapedLine) {
    let s = escapedLine;
    const inlineTokens = [];
    function stashToken(htmlStr) {
      const id = '@@AGY_INL_' + inlineTokens.length + '@@';
      inlineTokens.push(htmlStr);
      return id;
    }

    // 1. Inline code spans first so inner symbols are untouched
    s = s.replace(/`([^`\n]+)`/g, function (_, codeTxt) {
      return stashToken('<code class="agy-inline-code">' + codeTxt + '</code>');
    });

    // 2. Clickable local file:/// links (Left click: open file, Right click: open location)
    s = s.replace(/\[([^\]]+)\]\((file:\/\/\/[^)\s]+)\)/g, function (_, label, rawUri) {
      let cleanPath = rawUri.replace(/^file:\/\/\//, '').replace(/#L\d+.*$/, '');
      try { cleanPath = decodeURIComponent(cleanPath); } catch (err) { /* keep raw */ }
      return stashToken(
        '<button type="button" class="agy-file-pill" data-open-path="' +
        escapeHtml(cleanPath) +
        '" data-open-name="' +
        escapeHtml(label) +
        '" title="左键直接打开文件 · 右键定位所在文件夹: ' +
        escapeHtml(cleanPath) +
        '">' +
        label +
        '</button>'
      );
    });

    // 3. Standard web markdown links
    s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, function (_, label, url) {
      return stashToken(
        '<a class="agy-web-link" href="' + url + '" target="_blank" rel="noopener noreferrer">' + label + '</a>'
      );
    });

    // 4. Bold (**...**) & Italic (*...*)
    s = s.replace(/\*\*([\s\S]+?)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/(^|[^\*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>');

    for (let i = 0; i < inlineTokens.length; i++) {
      s = s.replace('@@AGY_INL_' + i + '@@', inlineTokens[i]);
    }
    return s;
  }

  function formatAssistantBody(rawText) {
    if (!rawText) return '';
    const normalized = String(rawText).replace(/\r\n/g, '\n');

    // Extract fenced code blocks before line-by-line block layout
    const codeBlocks = [];
    const withPlaceholders = normalized.replace(/```([a-zA-Z0-9_+\-]*)\n?([\s\S]*?)```/g, function (_, lang, codeBody) {
      const idx = codeBlocks.length;
      const cleanLang = escapeHtml((lang || 'CODE').trim());
      const cleanCode = escapeHtml(String(codeBody || '').replace(/\n$/, ''));
      codeBlocks.push(
        '<div class="agy-code-wrap">' +
        '  <div class="agy-code-hdr"><span>' + cleanLang + '</span><button type="button" class="agy-code-copy-btn" data-copy-code="1">复制</button></div>' +
        '  <pre class="agy-msg-pre"><code>' + cleanCode + '</code></pre>' +
        '</div>'
      );
      return '\n@@AGY_FENCE_BLOCK_' + idx + '@@\n';
    });

    const lines = withPlaceholders.split('\n');
    const out = [];
    let i = 0;

    while (i < lines.length) {
      const rawLine = lines[i];
      const trimmed = rawLine.trim();

      if (!trimmed) {
        i++;
        continue;
      }

      // Fenced code placeholder
      const fenceMatch = trimmed.match(/^@@AGY_FENCE_BLOCK_(\d+)@@$/);
      if (fenceMatch) {
        const bIdx = parseInt(fenceMatch[1], 10);
        if (codeBlocks[bIdx]) out.push(codeBlocks[bIdx]);
        i++;
        continue;
      }

      // Horizontal rule
      if (/^(?:---+|\*\*\*+|___+)$/.test(trimmed)) {
        out.push('<hr class="agy-md-hr" />');
        i++;
        continue;
      }

      // ATX Headings (# .. ####)
      const hMatch = trimmed.match(/^(#{1,4})\s+(.+)$/);
      if (hMatch) {
        const lvl = Math.min(4, hMatch[1].length);
        out.push('<div class="agy-md-h agy-md-h' + lvl + '">' + formatInlineMarkdown(escapeHtml(hMatch[2].trim())) + '</div>');
        i++;
        continue;
      }

      // Markdown Table
      if (trimmed.indexOf('|') !== -1 && (i + 1) < lines.length && /^\s*\|?[\s:\-|]+\|[\s:\-|]*$/.test(lines[i + 1])) {
        const parseCells = function (rowStr) {
          return rowStr.trim().replace(/^\||\|$/g, '').split('|').map(function (c) {
            return formatInlineMarkdown(escapeHtml(c.trim()));
          });
        };
        const headers = parseCells(trimmed);
        i += 2; // skip header + separator
        const bodyRows = [];
        while (i < lines.length && lines[i].trim().indexOf('|') !== -1 && lines[i].trim() !== '') {
          bodyRows.push(parseCells(lines[i]));
          i++;
        }
        out.push(
          '<div class="agy-md-table-wrap"><table class="agy-md-table"><thead><tr>' +
          headers.map(function (h) { return '<th>' + h + '</th>'; }).join('') +
          '</tr></thead><tbody>' +
          bodyRows.map(function (r) {
            return '<tr>' + r.map(function (c) { return '<td>' + c + '</td>'; }).join('') + '</tr>';
          }).join('') +
          '</tbody></table></div>'
        );
        continue;
      }

      // Blockquote (> ...)
      if (/^>\s?/.test(trimmed)) {
        const qLines = [];
        while (i < lines.length && /^>\s?/.test(lines[i].trim())) {
          qLines.push(formatInlineMarkdown(escapeHtml(lines[i].trim().replace(/^>\s?/, ''))));
          i++;
        }
        out.push('<blockquote class="agy-md-quote">' + qLines.join('<br/>') + '</blockquote>');
        continue;
      }

      // Ordered or Unordered Lists (supports nested indentation AND tight `-文字` bullets!)
      const isBulletLine = function (ln) {
        const t = ln.trim();
        if (!t || /^(?:---+|\*\*\*+)$/.test(t) || /^@@AGY_FENCE_BLOCK_\d+@@$/.test(t)) return null;
        const mOrd = ln.match(/^(\s*)(\d+)[\.\)]\s*(.+)$/);
        if (mOrd) return { type: 'ol', indent: mOrd[1].length, num: mOrd[2], body: mOrd[3] };
        const mUnord = ln.match(/^(\s*)(?:[-•]|\*(?!\*))\s*(.+)$/);
        if (mUnord) return { type: 'ul', indent: mUnord[1].length, body: mUnord[2] };
        return null;
      };

      const firstItem = isBulletLine(rawLine);
      if (firstItem) {
        const listTag = firstItem.type;
        const listItems = [];
        while (i < lines.length) {
          const curLn = lines[i];
          if (!curLn.trim()) {
            // Look ahead across a single blank line if another list item immediately follows
            if ((i + 1) < lines.length && isBulletLine(lines[i + 1])) {
              i++;
              continue;
            }
            break;
          }
          const bInfo = isBulletLine(curLn);
          if (bInfo) {
            listItems.push({
              sub: bInfo.indent >= 2 && listItems.length > 0,
              type: bInfo.type,
              html: formatInlineMarkdown(escapeHtml(bInfo.body.trim()))
            });
            i++;
          } else if (/^\s{2,}\S/.test(curLn) && listItems.length > 0) {
            // Indented continuation line inside the current list item
            const contFence = curLn.trim().match(/^@@AGY_FENCE_BLOCK_(\d+)@@$/);
            if (contFence && codeBlocks[parseInt(contFence[1], 10)]) {
              listItems[listItems.length - 1].html += codeBlocks[parseInt(contFence[1], 10)];
            } else {
              listItems[listItems.length - 1].html += '<div class="agy-md-li-cont">' + formatInlineMarkdown(escapeHtml(curLn.trim())) + '</div>';
            }
            i++;
          } else {
            break;
          }
        }

        let listHtml = '<' + listTag + ' class="agy-md-list agy-md-' + listTag + '">';
        let k = 0;
        while (k < listItems.length) {
          let liInner = listItems[k].html;
          k++;
          const subItems = [];
          while (k < listItems.length && listItems[k].sub) {
            subItems.push(listItems[k].html);
            k++;
          }
          if (subItems.length > 0) {
            liInner += '<ul class="agy-md-list agy-md-sublist">' + subItems.map(function (x) { return '<li>' + x + '</li>'; }).join('') + '</ul>';
          }
          listHtml += '<li>' + liInner + '</li>';
        }
        listHtml += '</' + listTag + '>';
        out.push(listHtml);
        continue;
      }

      // Standard paragraph (coalesce consecutive plain lines)
      const pLines = [];
      while (i < lines.length) {
        const ln = lines[i];
        const tr = ln.trim();
        if (
          !tr ||
          /^@@AGY_FENCE_BLOCK_\d+@@$/.test(tr) ||
          /^(?:---+|\*\*\*+|___+)$/.test(tr) ||
          /^(#{1,4})\s+/.test(tr) ||
          /^>\s?/.test(tr) ||
          isBulletLine(ln)
        ) {
          break;
        }
        pLines.push(formatInlineMarkdown(escapeHtml(tr)));
        i++;
      }
      if (pLines.length > 0) {
        out.push('<p class="agy-md-p">' + pLines.join('<br/>') + '</p>');
      } else {
        i++;
      }
    }

    return monochromizeEmojis(out.join(''));
  }

  // ==========================================================================
  // Strict True-Completion Engine + Multi-Completed Columns (`已完成栏目`)
  // ==========================================================================
  function isTurnTrulyCompleted(t) {
    if (!t || typeof t !== 'object') return false;
    const text = String(t.assistantText || '').trim();
    if (!text) return false;
    if (typeof t.hasFinalReply === 'boolean') {
      return t.hasFinalReply === true && t.status === 'done';
    }
    return t.status === 'done';
  }

  function makeSnippetText(rawText) {
    return String(rawText || '')
      .replace(/```[\s\S]*?```/g, '[代码块]')
      .replace(/[#>*`]/g, '')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 88);
  }

  function upsertCompletedColumnItem(item) {
    if (!item || !item.key) return;
    completedTaskColumns = completedTaskColumns.filter(function (x) { return x.key !== item.key; });
    completedTaskColumns.unshift(item);
    if (completedTaskColumns.length > 12) {
      completedTaskColumns.length = 12;
    }
  }

  function computeRunningCount() {
    let cnt = 0;
    for (let i = 0; i < conversations.length; i++) {
      if (!conversations[i].archived && conversations[i].status === 'running') {
        cnt++;
      }
    }
    if (cnt === 0 && currentStatus === 'running') cnt = 1;
    return cnt;
  }

  function pushCompletionTo3DEngine() {
    const runningCount = computeRunningCount();
    const unreadCount = unreadWhiteSphereKeys.size;
    if (window.ophanimAgent && typeof window.ophanimAgent.setCompletionState === 'function') {
      window.ophanimAgent.setCompletionState({
        runningCount: runningCount,
        unreadCount: unreadCount
      });
    }
    syncUnreadBadgesUI(runningCount, unreadCount);
    renderCompletedColumnsBars();
  }

  function syncUnreadBadgesUI(runningCount, unreadCount) {
    if (IS_WALLPAPER_VIEW) return;
    const colCount = completedTaskColumns.length;
    const dockBadge = document.getElementById('agy-left-dock-unread');
    if (dockBadge) {
      if (unreadCount > 0) {
        dockBadge.style.display = 'inline-flex';
        dockBadge.textContent = unreadCount + ' 已完成';
      } else if (runningCount > 0) {
        dockBadge.style.display = 'inline-flex';
        dockBadge.textContent = runningCount + ' 运行中';
      } else {
        dockBadge.style.display = 'none';
      }
    }
    const wbAckBtn = document.getElementById('btn-wb-ack-unread');
    if (wbAckBtn) {
      const badgeN = Math.max(unreadCount, colCount);
      wbAckBtn.style.display = badgeN > 0 ? 'inline-flex' : 'none';
      wbAckBtn.textContent = '✓ 已查收 (' + badgeN + ')';
    }
  }

  function convHasUnreadCompletion(cid) {
    if (!cid) return false;
    const prefix = cid + ':';
    let found = false;
    unreadWhiteSphereKeys.forEach(function (k) {
      if (k.indexOf(prefix) === 0) found = true;
    });
    if (found) return true;
    return completedTaskColumns.some(function (c) { return c.cid === cid; });
  }

  function trackConversationsTransitions(nextConvs) {
    if (!Array.isArray(nextConvs)) return;
    const liveIds = new Set();

    if (!hasSeededInitialCompletions) {
      for (let i = 0; i < nextConvs.length; i++) {
        const c = nextConvs[i];
        liveIds.add(c.id);
        if (c.lastCompletedTurn && Number(c.lastCompletedTurn.turnNumber) > 0) {
          const maxTn = Number(c.lastCompletedTurn.turnNumber);
          setBoundedMapEntry(maxCompletedTurnByCid, c.id, maxTn, MAX_TRACKED_CIDS);
          addSeenCompletedTurnKey(c.id + ':' + maxTn);
        }
      }
      hasSeededInitialCompletions = true;
      pushCompletionTo3DEngine();
      return;
    }

    for (let i = 0; i < nextConvs.length; i++) {
      const c = nextConvs[i];
      liveIds.add(c.id);
      if (c.archived) continue;
      const lct = c.lastCompletedTurn;
      if (lct && Number(lct.turnNumber) > 0 && String(lct.snippet || '').trim().length > 0) {
        const tNum = Number(lct.turnNumber);
        const key = c.id + ':' + tNum;
        const alreadySeen = seenCompletedTurnKeys.has(key) || tNum <= (maxCompletedTurnByCid[c.id] || 0);
        if (alreadySeen) {
          addSeenCompletedTurnKey(key);
          if (tNum > (maxCompletedTurnByCid[c.id] || 0)) {
            setBoundedMapEntry(maxCompletedTurnByCid, c.id, tNum, MAX_TRACKED_CIDS);
          }
        } else {
          addSeenCompletedTurnKey(key);
          setBoundedMapEntry(maxCompletedTurnByCid, c.id, tNum, MAX_TRACKED_CIDS);
          unreadWhiteSphereKeys.add(key);
          upsertCompletedColumnItem({
            key: key,
            cid: c.id,
            convTitle: c.title || ('#' + (c.shortId || c.id.slice(0, 8))),
            turnNumber: tNum,
            turnTitle: lct.title || ('第 ' + tNum + ' 轮已完成任务'),
            snippet: lct.snippet || '',
            ts: Date.now()
          });
        }
      }
    }

    Array.from(unreadWhiteSphereKeys).forEach(function (k) {
      const cidPart = k.split(':')[0];
      if (!liveIds.has(cidPart)) unreadWhiteSphereKeys.delete(k);
    });
    completedTaskColumns = completedTaskColumns.filter(function (item) {
      return liveIds.has(item.cid);
    });
    pruneMapByLiveIds(lastSeenTurnNumByCid, liveIds, MAX_TRACKED_CIDS);
    pruneMapByLiveIds(maxCompletedTurnByCid, liveIds, MAX_TRACKED_CIDS);
    pushCompletionTo3DEngine();
  }

  function trackSnapshotTrueCompletions(snap, isInitialSnapshot) {
    if (!snap || !snap.cascadeId || snap.cascadeId === '__new__') return;
    const cid = snap.cascadeId;
    const turns = buildTurnsFromSnapshot(snap);
    const seedKey = '__seeded_cid__:' + cid;
    const seedOnly = Boolean(isInitialSnapshot) || (!seenCompletedTurnKeys.has(seedKey) && !Object.prototype.hasOwnProperty.call(maxCompletedTurnByCid, cid));
    addSeenCompletedTurnKey(seedKey);

    let addedNew = false;
    let highestCompleted = maxCompletedTurnByCid[cid] || 0;
    for (let i = 0; i < turns.length; i++) {
      const t = turns[i];
      const tNum = t.turnNumber || (i + 1);
      if (!isTurnTrulyCompleted(t)) continue;
      const key = cid + ':' + tNum;
      if (seedOnly) {
        if (tNum > highestCompleted) highestCompleted = tNum;
      } else if (!seenCompletedTurnKeys.has(key) && tNum > highestCompleted) {
        highestCompleted = tNum;
        addSeenCompletedTurnKey(key);
        unreadWhiteSphereKeys.add(key);
        upsertCompletedColumnItem({
          key: key,
          cid: cid,
          convTitle: snap.title || '当前会话',
          turnNumber: tNum,
          turnTitle: t.title || ('第 ' + tNum + ' 轮请求'),
          snippet: makeSnippetText(t.assistantText),
          ts: Date.now()
        });
        addedNew = true;
      }
    }
    if (highestCompleted > 0) {
      setBoundedMapEntry(maxCompletedTurnByCid, cid, highestCompleted, MAX_TRACKED_CIDS);
      addSeenCompletedTurnKey(cid + ':' + highestCompleted);
    }
    if (addedNew) {
      pushCompletionTo3DEngine();
    }
  }

  function clearUnreadCompletions() {
    unreadWhiteSphereKeys.clear();
    completedTaskColumns = [];
    activeCompletedColKey = '';
    renderCompletedColumnsBars();
    renderSessionList();
    syncUnreadBadgesUI(computeRunningCount(), 0);
  }

  function dismissSingleCompletedColumn(colKey) {
    if (!colKey) return;
    unreadWhiteSphereKeys.delete(colKey);
    completedTaskColumns = completedTaskColumns.filter(function (x) { return x.key !== colKey; });
    if (activeCompletedColKey === colKey) {
      activeCompletedColKey = completedTaskColumns[0] ? completedTaskColumns[0].key : '';
    }
    pushCompletionTo3DEngine();
    renderSessionList();
  }

  function focusCompletedTaskColumn(colItem, openInWorkbench) {
    if (!colItem) return;
    activeCompletedColKey = colItem.key;
    unreadWhiteSphereKeys.delete(colItem.key);
    const turnKey = colItem.cid + ':' + colItem.turnNumber;
    addBoundedSetKey(expandedTurnKeys, turnKey, MAX_EXPANDED_TURN_KEYS);
    pendingScrollTurnKey = turnKey;

    if (openInWorkbench && workbenchOpen && workbenchRightPane !== 'chat') {
      switchWorkbenchRightPane('chat');
    }

    if (currentCid !== colItem.cid || isDraftNew) {
      selectConversation(colItem.cid, Boolean(openInWorkbench));
    } else if (lastSnapshot) {
      renderConversationStream(lastSnapshot, false);
      scrollStreamToTurnKey(turnKey);
    }
    pushCompletionTo3DEngine();
    renderSessionList();
  }

  function scrollStreamToTurnKey(turnKey) {
    if (!turnKey) return;
    requestAnimationFrame(function () {
      ['agy-chat-stream', 'agy-wb-chat-stream'].forEach(function (sid) {
        const container = document.getElementById(sid);
        if (!container) return;
        const targetCard = container.querySelector('[data-turn-key="' + CSS.escape(turnKey) + '"]');
        if (targetCard) {
          streamStickBottom[sid] = false;
          targetCard.classList.add('completed-locate-flash');
          const targetTop = computeTurnCardTargetScrollTop(container, targetCard);
          if (typeof container.scrollTo === 'function') {
            container.scrollTo({ top: targetTop, behavior: 'smooth' });
          } else {
            container.scrollTop = targetTop;
          }
          setTimeout(function () {
            targetCard.classList.remove('completed-locate-flash');
            const latestAnchor = computeLatestTurnTargetScrollTop(container);
            if (Math.abs(container.scrollTop - latestAnchor) <= 52) {
              streamStickBottom[sid] = true;
            }
          }, 1800);
        }
      });
    });
  }

  function renderCompletedColumnsBars() {
    if (IS_WALLPAPER_VIEW) return;
    ['agy-core-completed-bar', 'agy-wb-completed-bar'].forEach(function (barId) {
      const bar = document.getElementById(barId);
      if (!bar) return;
      if (completedTaskColumns.length === 0) {
        bar.style.display = 'none';
        bar.innerHTML = '';
        return;
      }
      bar.style.display = 'flex';
      const isWb = barId === 'agy-wb-completed-bar';
      const colsHtml = completedTaskColumns.map(function (col, idx) {
        const isAct = col.key === activeCompletedColKey || (!activeCompletedColKey && idx === 0);
        return (
          '<div class="agy-done-col-card' + (isAct ? ' active' : '') + '" data-done-col-key="' + escapeHtml(col.key) + '" data-done-wb="' + (isWb ? '1' : '0') + '" title="点击自动切换并定位到该已完成任务输出">' +
          '  <div class="agy-done-col-top">' +
          '    <span class="agy-done-col-tag">已完成 #' + (idx + 1) + ' · 第 ' + col.turnNumber + ' 轮</span>' +
          '    <button type="button" class="agy-done-col-rm" data-rm-done-col="' + escapeHtml(col.key) + '" title="移出此已完成栏目">×</button>' +
          '  </div>' +
          '  <div class="agy-done-col-conv">' + monochromizeEmojis(escapeHtml(col.convTitle)) + ' — ' + monochromizeEmojis(escapeHtml(col.turnTitle)) + '</div>' +
          (col.snippet ? ('  <div class="agy-done-col-snip">' + monochromizeEmojis(escapeHtml(col.snippet)) + '</div>') : '') +
          '</div>'
        );
      }).join('');

      bar.innerHTML =
        '<div class="agy-done-bar-hdr">' +
        '  <span>✦ 已完成待查收栏目 (' + completedTaskColumns.length + ') · 点击任一栏目直接定位查看完成结果</span>' +
        '  <button type="button" class="mini-close-deck-btn" data-ack-all-done="1">✓ 全部已查收</button>' +
        '</div>' +
        '<div class="agy-done-cols-grid">' + colsHtml + '</div>';
    });
  }

  function markSingleConversationRead(cid) {
    if (!cid) return;
    const prefix = cid + ':';
    Array.from(unreadWhiteSphereKeys).forEach(function (k) {
      if (k.indexOf(prefix) === 0) unreadWhiteSphereKeys.delete(k);
    });
    completedTaskColumns = completedTaskColumns.filter(function (c) { return c.cid !== cid; });
    pushCompletionTo3DEngine();
    renderSessionList();
  }

  // ==========================================================================
  // Styles Injection
  // ==========================================================================
  function injectStyles() {
    if (document.getElementById('agy-bridge-panel-styles')) return;
    const style = document.createElement('style');
    style.id = 'agy-bridge-panel-styles';
    style.textContent = [
      '/* Top-Left Mode Trigger Button (Shared inside #top-left-toolbar beside 司仪台) */',
      '#agy-left-dock-trigger {',
      '  position: fixed; top: 20px; left: 22px; z-index: 16;',
      '  background: var(--bg-panel); border: 1px solid var(--line-strong); color: var(--ink-primary);',
      '  padding: 7px 13px; font-family: var(--font-mono); font-size: 11.5px; font-weight: 600; letter-spacing: 0.06em;',
      '  cursor: pointer; display: inline-flex; align-items: center; gap: 8px;',
      '  backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);',
      '  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.45);',
      '  transition: transform 0.32s cubic-bezier(0.22, 1, 0.36, 1), opacity 0.32s ease, background-color 0.2s ease;',
      '}',
      '#top-left-toolbar #agy-left-dock-trigger { position: relative; top: auto; left: auto; z-index: auto; }',
      '#agy-left-dock-trigger:hover { background: var(--bg-panel-hover); transform: translateY(-1px); }',
      '#agy-left-dock-trigger.active { background: var(--accent-invert-bg); color: var(--accent-invert-fg); }',
      '#agy-left-dock-trigger svg { width: 14px; height: 14px; stroke: currentColor; fill: none; stroke-width: 1.7; }',
      '#agy-left-dock-unread {',
      '  display: none; align-items: center; padding: 1px 6px; font-size: 9.5px;',
      '  border: 1px solid currentColor; animation: agyRunPulse 1.3s ease-in-out infinite;',
      '}',
      'body.pre-genesis #agy-left-dock-trigger, body.dormant-sanctum #agy-left-dock-trigger {',
      '  opacity: 0 !important; pointer-events: none !important; transform: translate3d(-18px, 0, 0);',
      '}',
      '',
      '/* Left Slide-Out Full Agent Workbench (#agy-workbench-drawer) */',
      '#agy-workbench-drawer {',
      '  position: fixed; top: 62px; left: 16px; bottom: 18px; width: 268px; max-width: calc(100vw - 32px); z-index: 15;',
      '  background: var(--bg-panel); border: 1px solid var(--line-strong); box-shadow: 24px 24px 72px rgba(0, 0, 0, 0.78);',
      '  backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);',
      '  display: flex; flex-direction: row; overflow: hidden; opacity: 0; pointer-events: none;',
      '  transform: translate3d(calc(-100% - 36px), 0, 0);',
      '  transition: transform 0.42s cubic-bezier(0.22, 1, 0.36, 1), opacity 0.34s cubic-bezier(0.22, 1, 0.36, 1), width 0.34s cubic-bezier(0.22, 1, 0.36, 1);',
      '}',
      '#agy-workbench-drawer.open { opacity: var(--panel-hud-opacity, 0.96); pointer-events: auto; transform: translate3d(0, 0, 0); }',
      '#agy-workbench-drawer.resizing-now { transition: none !important; user-select: none; }',
      'body.pre-genesis #agy-workbench-drawer, body.dormant-sanctum #agy-workbench-drawer {',
      '  opacity: 0 !important; pointer-events: none !important; transform: translate3d(calc(-100% - 36px), 0, 0) !important;',
      '}',
      '#agy-wb-sidebar { width: 268px; min-width: 176px; max-width: 480px; display: flex; flex-direction: column; background: rgba(0, 0, 0, 0.16); flex-shrink: 0; overflow: hidden; }',
      '#agy-workbench-drawer.sidebar-only #agy-wb-sidebar { width: 100% !important; max-width: none; }',
      'body.paper-ink-theme #agy-wb-sidebar { background: rgba(0, 0, 0, 0.035); }',
      '.agy-wb-side-top { padding: 11px 11px 9px; border-bottom: 1px solid var(--line-faint); display: flex; flex-direction: column; gap: 8px; flex-shrink: 0; }',
      '.agy-wb-brand-row { display: flex; justify-content: space-between; align-items: center; gap: 5px; font-family: var(--font-mono); font-size: 9.5px; letter-spacing: 0.10em; color: var(--ink-muted); }',
      '.agy-wb-brand-actions { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }',
      '#btn-wb-toggle-main.active { background: var(--accent-invert-bg); color: var(--accent-invert-fg); border-color: var(--line-strong); font-weight: 600; }',
      '#btn-wb-new-session {',
      '  width: 100%; padding: 7px 10px; background: var(--accent-invert-bg); color: var(--accent-invert-fg);',
      '  border: 1px solid var(--line-strong); font-family: var(--font-mono); font-size: 11px; font-weight: 600;',
      '  letter-spacing: 0.06em; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px;',
      '}',
      '#btn-wb-new-session:hover { opacity: 0.9; }',
      '#agy-wb-session-list { flex: 1 1 0; overflow-y: auto; overflow-x: hidden; scrollbar-width: thin; scrollbar-color: var(--line-mid) transparent; }',
      '.agy-wb-sec-divider { padding: 6px 10px 4px; font-family: var(--font-mono); font-size: 9px; letter-spacing: 0.12em; color: var(--ink-muted); border-bottom: 1px solid var(--line-faint); display: flex; justify-content: space-between; align-items: center; }',
      '.agy-wb-arch-toggle { width: 100%; background: transparent; border: none; border-top: 1px solid var(--line-faint); border-bottom: 1px solid var(--line-faint); color: var(--ink-muted); font-family: var(--font-mono); font-size: 9.5px; padding: 6px 10px; text-align: left; cursor: pointer; display: flex; justify-content: space-between; align-items: center; }',
      '.agy-wb-arch-toggle:hover { color: var(--ink-primary); background: rgba(255,255,255,0.03); }',
      '.agy-wb-side-footer { padding: 8px 10px; border-top: 1px solid var(--line-dim); display: flex; gap: 6px; flex-shrink: 0; }',
      '.agy-wb-foot-btn { flex: 1; background: transparent; border: 1px solid var(--line-dim); color: var(--ink-primary); font-family: var(--font-mono); font-size: 10.6px; padding: 6px 8px; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 5px; transition: all 0.18s ease; }',
      '.agy-wb-foot-btn:hover { border-color: var(--line-strong); background: var(--bg-panel-hover); }',
      '.agy-wb-foot-btn.active { background: var(--accent-invert-bg); color: var(--accent-invert-fg); border-color: var(--line-strong); font-weight: 600; }',
      '#agy-wb-col-splitter { width: 6px; cursor: col-resize; background: transparent; border-left: 1px solid var(--line-dim); flex-shrink: 0; position: relative; transition: background-color 0.16s ease; }',
      '#agy-workbench-drawer.sidebar-only #agy-wb-col-splitter { display: none !important; }',
      '#agy-wb-col-splitter:hover, #agy-wb-col-splitter.active { background: rgba(242, 242, 245, 0.18); }',
      '#agy-wb-outer-resizer { position: absolute; top: 0; right: -3px; bottom: 0; width: 8px; cursor: ew-resize; z-index: 20; }',
      '#agy-wb-outer-resizer:hover { background: rgba(242, 242, 245, 0.18); }',
      '#agy-wb-main { flex: 1 1 0; min-width: 280px; display: flex; flex-direction: column; overflow: hidden; position: relative; opacity: 1; transform: translate3d(0, 0, 0); transition: opacity 0.24s ease, transform 0.32s cubic-bezier(0.22, 1, 0.36, 1); }',
      '#agy-workbench-drawer.sidebar-only #agy-wb-main { flex: 0 0 0 !important; width: 0 !important; min-width: 0 !important; opacity: 0; pointer-events: none; transform: translate3d(-14px, 0, 0); }',
      '#agy-wb-chat-pane, #agy-wb-settings-pane { flex: 1 1 0; display: flex; flex-direction: column; overflow: hidden; position: relative; }',
      '#agy-wb-settings-pane { display: none; }',
      '#agy-workbench-drawer.settings-mode #agy-wb-chat-pane { display: none; }',
      '#agy-workbench-drawer.settings-mode #agy-wb-settings-pane { display: flex; }',
      '.agy-wb-main-hdr { padding: 10px 15px 9px; border-bottom: 1px solid var(--line-dim); display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-shrink: 0; }',
      '#agy-wb-chat-title { font-family: var(--font-serif); font-size: 15.5px; font-weight: 600; color: var(--ink-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 380px; }',
      '#agy-wb-chat-stream { position: relative; flex: 1 1 0; overflow-y: auto; overflow-x: hidden; padding: 12px 15px; display: flex; flex-direction: column; gap: 8px; scrollbar-width: thin; scrollbar-color: var(--line-mid) transparent; }',
      '#agy-wb-drop-overlay { position: absolute; inset: 8px; z-index: 35; display: none; align-items: center; justify-content: center; flex-direction: column; gap: 8px; background: rgba(6, 6, 10, 0.88); border: 2px dashed var(--line-strong); color: var(--ink-primary); font-family: var(--font-mono); font-size: 12.5px; pointer-events: none; }',
      'body.paper-ink-theme #agy-wb-drop-overlay { background: rgba(242, 240, 234, 0.92); }',
      '#agy-wb-chat-pane.drag-over #agy-wb-drop-overlay { display: flex; }',
      '',
      '/* Multi-Completed Task Columns Strip (`已完成栏目`) */',
      '.agy-completed-bar { display: none; flex-direction: column; gap: 7px; padding: 9px 15px 10px; border-bottom: 1px solid var(--line-strong); background: rgba(255, 255, 255, 0.045); flex-shrink: 0; }',
      'body.paper-ink-theme .agy-completed-bar { background: rgba(17, 18, 22, 0.055); }',
      '.agy-done-bar-hdr { display: flex; justify-content: space-between; align-items: center; gap: 8px; font-family: var(--font-mono); font-size: 10px; color: var(--ink-primary); letter-spacing: 0.04em; }',
      '.agy-done-cols-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 7px; max-height: 132px; overflow-y: auto; }',
      '.agy-done-col-card { border: 1px solid var(--line-mid); background: rgba(0, 0, 0, 0.28); padding: 7px 9px; cursor: pointer; display: flex; flex-direction: column; gap: 3px; transition: border-color 0.16s ease, background-color 0.16s ease; }',
      'body.paper-ink-theme .agy-done-col-card { background: rgba(255, 255, 255, 0.72); }',
      '.agy-done-col-card:hover, .agy-done-col-card.active { border-color: var(--line-strong); background: rgba(242, 242, 245, 0.11); }',
      'body.paper-ink-theme .agy-done-col-card.active { background: rgba(17, 18, 22, 0.10); }',
      '.agy-done-col-top { display: flex; justify-content: space-between; align-items: center; gap: 6px; }',
      '.agy-done-col-tag { font-family: var(--font-mono); font-size: 9px; font-weight: 600; color: var(--accent-invert-fg); background: var(--accent-invert-bg); padding: 1px 6px; }',
      '.agy-done-col-rm { background: transparent; border: none; color: var(--ink-muted); font-family: var(--font-mono); font-size: 12px; cursor: pointer; padding: 0 3px; line-height: 1; }',
      '.agy-done-col-rm:hover { color: var(--ink-primary); }',
      '.agy-done-col-conv { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei UI", sans-serif; font-size: 11.8px; font-weight: 600; color: var(--ink-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }',
      '.agy-done-col-snip { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei UI", sans-serif; font-size: 11px; color: var(--ink-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }',
      '@keyframes agyLocateFlash { 0% { box-shadow: 0 0 0 2px #ffffff; } 100% { box-shadow: 0 0 0 0 rgba(255,255,255,0); } }',
      '.agy-turn-card.completed-locate-flash { animation: agyLocateFlash 1.5s ease-out; border-color: #ffffff !important; }',
      '',
      '/* In-Place Embedded Settings Tabs & Controls */',
      '.agy-wb-set-nav { display: grid; grid-template-columns: repeat(4, 1fr); gap: 5px; padding: 9px 15px; border-bottom: 1px solid var(--line-dim); background: var(--line-faint); flex-shrink: 0; }',
      '.agy-wb-set-tab { background: transparent; border: 1px solid var(--line-dim); color: var(--ink-muted); font-family: var(--font-mono); font-size: 10.4px; padding: 6px 6px; cursor: pointer; text-align: center; transition: all 0.16s ease; }',
      '.agy-wb-set-tab:hover { border-color: var(--line-strong); color: var(--ink-primary); }',
      '.agy-wb-set-tab.active { background: var(--accent-invert-bg); color: var(--accent-invert-fg); border-color: var(--line-strong); font-weight: 600; }',
      '#agy-wb-settings-body { flex: 1 1 0; overflow-y: auto; padding: 13px 15px 18px; display: flex; flex-direction: column; gap: 12px; scrollbar-width: thin; scrollbar-color: var(--line-mid) transparent; }',
      '.wb-set-card { border: 1px solid var(--line-dim); background: var(--line-faint); padding: 11px 12px; display: flex; flex-direction: column; gap: 8px; }',
      '.wb-set-card-hdr { display: flex; justify-content: space-between; align-items: center; font-family: var(--font-mono); font-size: 10.2px; letter-spacing: 0.08em; color: var(--ink-primary); border-bottom: 1px solid var(--line-faint); padding-bottom: 5px; }',
      '.wb-set-grid-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; }',
      '.wb-set-grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }',
      '.wb-set-grid-6 { display: grid; grid-template-columns: repeat(6, 1fr); gap: 5px; }',
      '.wb-opt-btn { background: transparent; border: 1px solid var(--line-dim); color: var(--ink-primary); font-family: var(--font-mono); font-size: 10.4px; padding: 7px 8px; cursor: pointer; text-align: center; transition: all 0.16s ease; }',
      '.wb-opt-btn:hover { border-color: var(--line-strong); background: var(--bg-panel-hover); }',
      '.wb-opt-btn.active { background: var(--accent-invert-bg); color: var(--accent-invert-fg); border-color: var(--line-strong); font-weight: 600; }',
      '.wb-slider-row { display: flex; flex-direction: column; gap: 3px; }',
      '.wb-slider-meta { display: flex; justify-content: space-between; font-family: var(--font-mono); font-size: 9.8px; color: var(--ink-muted); }',
      '.wb-slider-meta strong { color: var(--ink-primary); font-weight: 500; }',
      '#agy-wb-quota-canvas { width: 100%; height: 124px; display: block; border: 1px solid var(--line-dim); background: rgba(0, 0, 0, 0.22); }',
      'body.paper-ink-theme #agy-wb-quota-canvas { background: rgba(255, 255, 255, 0.45); }',
      '',
      '/* Monochrome SVG & Universal Emoji Grayscale Enforcement */',
      '.agy-mono-svg { width: 11px; height: 11px; vertical-align: -1.5px; display: inline-block; flex-shrink: 0; }',
      '.mono-emoji { display: inline-block; filter: grayscale(100%) contrast(1.18); -webkit-filter: grayscale(100%) contrast(1.18); font-variant-emoji: text; }',
      '',
      '/* Mutual Bidirectional Collapse Between #codex-panel (司仪台) and #codex-agy-wing (右侧会话列表) */',
      '#btn-codex-session-wing.active, #btn-wing-toggle-codex.active { background: var(--accent-invert-bg); color: var(--accent-invert-fg); border-color: var(--line-strong); font-weight: 600; }',
      '#codex-panel.wing-fold-animating {',
      '  transition: left 0.36s cubic-bezier(0.22, 1, 0.36, 1), width 0.36s cubic-bezier(0.22, 1, 0.36, 1), opacity 0.32s ease, transform 0.36s cubic-bezier(0.22, 1, 0.36, 1) !important;',
      '}',
      '#codex-panel > #codex-drag-handle, #codex-panel > .panel-scroll-body {',
      '  transition: opacity 0.24s ease, transform 0.32s cubic-bezier(0.22, 1, 0.36, 1);',
      '}',
      '#codex-panel.codex-body-collapsed {',
      '  width: 0px !important; min-width: 0px !important; padding-left: 0 !important; padding-right: 0 !important;',
      '  background: transparent !important; border-color: transparent !important; box-shadow: none !important;',
      '  backdrop-filter: none !important; -webkit-backdrop-filter: none !important; pointer-events: none !important;',
      '}',
      '#codex-panel.codex-body-collapsed > #codex-drag-handle,',
      '#codex-panel.codex-body-collapsed > .panel-scroll-body,',
      '#codex-panel.codex-body-collapsed > .rs-handle {',
      '  opacity: 0 !important; pointer-events: none !important; transform: translate3d(22px, 0, 0); overflow: hidden !important;',
      '}',
      '#codex-agy-wing-shell {',
      '  position: absolute; left: calc(100% - 1px); top: -1px; bottom: -1px; width: 0;',
      '  overflow: hidden; pointer-events: none; z-index: 8;',
      '  transition: width 0.38s cubic-bezier(0.22, 1, 0.36, 1), left 0.36s cubic-bezier(0.22, 1, 0.36, 1);',
      '}',
      '#codex-panel.session-wing-open #codex-agy-wing-shell { width: 312px; pointer-events: auto; }',
      '#codex-panel.codex-body-collapsed #codex-agy-wing-shell { left: 0px; top: 0px; bottom: 0px; width: 312px; pointer-events: auto; }',
      '#codex-panel.hidden-hud #codex-agy-wing-shell { pointer-events: none !important; }',
      '#codex-agy-wing {',
      '  width: 312px; height: 100%; box-sizing: border-box;',
      '  background: var(--bg-panel); border: 1px solid var(--line-strong);',
      '  backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);',
      '  box-shadow: 18px 18px 46px rgba(0, 0, 0, 0.62);',
      '  padding: 11px 12px 10px; display: flex; flex-direction: column; overflow: hidden;',
      '  opacity: 0; transform: translate3d(-18px, 0, 0);',
      '  transition: opacity 0.28s cubic-bezier(0.22, 1, 0.36, 1), transform 0.38s cubic-bezier(0.22, 1, 0.36, 1);',
      '}',
      '#codex-panel.session-wing-open #codex-agy-wing, #codex-panel.codex-body-collapsed #codex-agy-wing { opacity: 1; transform: translate3d(0, 0, 0); }',
      '.codex-wing-hdr { display: flex; justify-content: space-between; align-items: flex-start; gap: 6px; padding-bottom: 8px; margin-bottom: 7px; border-bottom: 1px solid var(--line-dim); flex-shrink: 0; cursor: grab; user-select: none; }',
      '#codex-panel.dragging .codex-wing-hdr { cursor: grabbing; }',
      'body.eye-closeup-blur #agy-workbench-drawer { filter: blur(8px) brightness(0.45); pointer-events: none; }',
      '',
      '/* Shared Session Item & Clean Monochrome Right-Click Context Menu (Zero Colored Emojis!) */',
      '.agy-hdr-actions { display: flex; align-items: center; gap: 5px; flex-wrap: wrap; }',
      '.agy-beam-mode-bar { display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; margin-bottom: 7px; flex-shrink: 0; }',
      '.agy-beam-pill { background: transparent; border: 1px solid var(--line-dim); color: var(--ink-muted); font-family: var(--font-mono); font-size: 9.2px; padding: 4px 4px; cursor: pointer; letter-spacing: 0.03em; transition: all 0.16s ease; text-align: center; }',
      '.agy-beam-pill:hover { border-color: var(--line-strong); color: var(--ink-primary); }',
      '.agy-beam-pill.active { background: var(--accent-invert-bg); color: var(--accent-invert-fg); border-color: var(--line-strong); font-weight: 600; }',
      '.agy-sub-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 6px; margin-bottom: 6px; flex-shrink: 0; }',
      '.agy-sec-title { font-family: var(--font-mono); font-size: 9.5px; color: var(--ink-muted); letter-spacing: 0.08em; display: flex; align-items: center; gap: 6px; }',
      '.agy-new-conv-btn { background: var(--accent-invert-bg); color: var(--accent-invert-fg); border: 1px solid var(--line-strong); font-family: var(--font-mono); font-size: 9.6px; font-weight: 600; padding: 3px 9px; cursor: pointer; letter-spacing: 0.05em; }',
      '#agy-session-list { flex: 1 1 0; min-height: 84px; overflow-y: auto; border: 1px solid var(--line-dim); background: var(--line-faint); margin-bottom: 7px; scrollbar-width: thin; scrollbar-color: var(--line-mid) transparent; }',
      '.agy-conv-item { padding: 7px 9px; border-bottom: 1px solid var(--line-faint); cursor: pointer; display: flex; flex-direction: column; gap: 3px; position: relative; transition: background-color 0.15s ease; }',
      '.agy-conv-item:hover { background: rgba(242, 242, 245, 0.06); }',
      'body.paper-ink-theme .agy-conv-item:hover { background: rgba(0, 0, 0, 0.05); }',
      '.agy-conv-item.active { background: rgba(242, 242, 245, 0.13); border-left: 2.5px solid var(--line-strong); padding-left: 7px; }',
      'body.paper-ink-theme .agy-conv-item.active { background: rgba(17, 18, 21, 0.10); }',
      '.agy-conv-top { display: flex; justify-content: space-between; align-items: center; gap: 5px; }',
      '.agy-conv-title { font-family: var(--font-serif); font-size: 12.2px; font-weight: 600; color: var(--ink-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; }',
      '.agy-conv-more-btn { background: transparent; border: 1px solid transparent; color: var(--ink-muted); font-family: var(--font-mono); font-size: 11px; padding: 0 4px; cursor: pointer; opacity: 0; transition: opacity 0.14s ease; }',
      '.agy-conv-item:hover .agy-conv-more-btn { opacity: 0.9; }',
      '.agy-conv-more-btn:hover { border-color: var(--line-dim); color: var(--ink-primary); }',
      '.agy-conv-meta { display: flex; align-items: center; gap: 6px; font-family: var(--font-mono); font-size: 8.6px; color: var(--ink-muted); }',
      '.agy-st-pill { font-family: var(--font-mono); font-size: 8.4px; padding: 0 5px; border: 1px solid var(--line-dim); white-space: nowrap; }',
      '.agy-st-pill.running { color: var(--accent-invert-fg); background: var(--accent-invert-bg); border-color: var(--line-strong); font-weight: 600; animation: agyRunPulse 1.35s ease-in-out infinite; }',
      '.agy-st-pill.unread-done { color: var(--accent-invert-fg); background: var(--accent-invert-bg); border-color: var(--line-strong); font-weight: 600; }',
      '.agy-st-pill.queued-pill { color: var(--ink-primary); border-color: var(--line-strong); background: rgba(255,255,255,0.08); }',
      '.agy-st-pill.idle { color: var(--ink-muted); }',
      '@keyframes agyRunPulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.55; } }',
      '',
      '#agy-session-ctx-menu {',
      '  position: fixed; z-index: 60; min-width: 162px; background: var(--bg-panel); border: 1px solid var(--line-strong);',
      '  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.72); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);',
      '  padding: 4px; display: none; flex-direction: column; gap: 2px;',
      '}',
      '#agy-session-ctx-menu.open { display: flex; }',
      '.agy-ctx-item {',
      '  background: transparent; border: none; color: var(--ink-primary); font-family: var(--font-mono); font-size: 10.8px;',
      '  padding: 6px 11px; text-align: left; cursor: pointer; display: flex; justify-content: space-between; align-items: center; gap: 14px;',
      '}',
      '.agy-ctx-item .ctx-sub { font-size: 9px; opacity: 0.62; letter-spacing: 0.08em; }',
      '.agy-ctx-item:hover { background: var(--accent-invert-bg); color: var(--accent-invert-fg); }',
      '.agy-ctx-sep { height: 1px; background: var(--line-faint); margin: 2px 4px; }',
      '',
      '#btn-agy-open-core {',
      '  width: 100%; background: var(--line-faint); border: 1px solid var(--line-dim); border-left: 2px solid var(--line-strong);',
      '  color: var(--ink-primary); padding: 6px 8px; font-family: var(--font-mono); font-size: 9.2px; cursor: pointer;',
      '  display: flex; justify-content: space-between; align-items: center; gap: 6px; flex-shrink: 0;',
      '}',
      '#btn-agy-open-core:hover { border-color: var(--line-strong); background: var(--bg-panel-hover); }',
      '#btn-agy-open-core .core-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; border: 1.4px solid currentColor; margin-right: 4px; vertical-align: middle; }',
      '',
      '/* Larger Default Central Core Modal + 8-Way Symmetric Center-Locked Resizing! */',
      '#agy-core-modal-backdrop {',
      '  position: fixed; inset: 0; z-index: 25; background: rgba(4, 4, 8, 0.0);',
      '  display: none; align-items: center; justify-content: center; padding: 14px;',
      '  transition: background-color 0.42s ease, opacity 0.32s ease; opacity: 0;',
      '}',
      '#agy-core-modal-backdrop.open { display: flex; }',
      '#agy-core-modal-backdrop.visible-phase { background: rgba(4, 4, 8, 0.30); opacity: 1; }',
      'body.paper-ink-theme #agy-core-modal-backdrop.visible-phase { background: rgba(235, 233, 226, 0.38); }',
      '#agy-core-modal {',
      '  width: min(92vw, 1160px); height: min(88vh, 840px);',
      '  max-width: calc(100vw - 24px); max-height: calc(100vh - 24px);',
      '  min-width: 620px; min-height: 440px;',
      '  background: rgba(8, 8, 12, 0.84); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);',
      '  color: var(--ink-primary); border: 1px solid var(--line-strong);',
      '  display: flex; flex-direction: column; overflow: hidden; position: relative;',
      '  box-shadow: 0 28px 80px rgba(0, 0, 0, 0.82);',
      '  transform: translateY(14px) scale(0.96); opacity: 0;',
      '  transition: transform 0.38s cubic-bezier(0.22, 1, 0.36, 1), opacity 0.34s ease;',
      '}',
      '#agy-core-modal.resizing-now { transition: none !important; user-select: none; }',
      'body.paper-ink-theme #agy-core-modal { background: rgba(244, 242, 236, 0.90); box-shadow: 0 24px 64px rgba(0,0,0,0.22); }',
      '#agy-core-modal-backdrop.visible-phase #agy-core-modal { transform: translateY(0) scale(1); opacity: 1; }',
      '',
      '/* Center-Locked Symmetric Resize Handles on #agy-core-modal (including visible Top-Right & Bottom-Right grips!) */',
      '.agy-core-rs { position: absolute; z-index: 32; }',
      '.agy-core-rs-n { top: 0; left: 16px; right: 16px; height: 6px; cursor: ns-resize; }',
      '.agy-core-rs-s { bottom: 0; left: 16px; right: 16px; height: 6px; cursor: ns-resize; }',
      '.agy-core-rs-e { right: 0; top: 18px; bottom: 18px; width: 6px; cursor: ew-resize; }',
      '.agy-core-rs-w { left: 0; top: 18px; bottom: 18px; width: 6px; cursor: ew-resize; }',
      '.agy-core-rs-nw { top: 0; left: 0; width: 15px; height: 15px; cursor: nwse-resize; }',
      '.agy-core-rs-sw { bottom: 0; left: 0; width: 15px; height: 15px; cursor: nesw-resize; }',
      '.agy-core-rs-ne {',
      '  top: 0; right: 0; width: 20px; height: 20px; cursor: nesw-resize; z-index: 36;',
      '  border-top: 2px solid var(--line-strong); border-right: 2px solid var(--line-strong); opacity: 0.72;',
      '  transition: opacity 0.15s ease, background-color 0.15s ease;',
      '}',
      '.agy-core-rs-se {',
      '  bottom: 0; right: 0; width: 18px; height: 18px; cursor: nwse-resize; z-index: 36;',
      '  border-bottom: 2px solid var(--line-strong); border-right: 2px solid var(--line-strong); opacity: 0.72;',
      '  transition: opacity 0.15s ease, background-color 0.15s ease;',
      '}',
      '.agy-core-rs-ne:hover, .agy-core-rs-se:hover { opacity: 1; background: rgba(255,255,255,0.14); }',
      '',
      '.agy-core-modal-hdr {',
      '  display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;',
      '  padding: 12px 26px 10px 18px; border-bottom: 1px solid var(--line-dim); flex-shrink: 0;',
      '}',
      '.agy-core-kicker { font-family: var(--font-mono); font-size: 9.2px; letter-spacing: 0.12em; color: var(--ink-muted); margin-bottom: 3px; }',
      '.agy-core-title-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }',
      '#agy-core-modal-title { font-family: var(--font-serif); font-size: 16.5px; font-weight: 600; color: var(--ink-primary); }',
      '#agy-core-binding-counts, #agy-wb-binding-counts { font-family: var(--font-mono); font-size: 9.4px; color: var(--ink-muted); }',
      '#agy-chat-stream {',
      '  position: relative; flex: 1 1 0; min-height: 140px; overflow-y: auto; overflow-x: hidden;',
      '  padding: 14px 18px; display: flex; flex-direction: column; gap: 9px;',
      '  scrollbar-width: thin; scrollbar-color: var(--line-mid) transparent;',
      '}',
      '#agy-wb-chat-stream > :first-child, #agy-chat-stream > :first-child { margin-top: auto; }',
      '#agy-wb-chat-stream > .agy-empty-hint, #agy-chat-stream > .agy-empty-hint { margin: auto; }',
      '.agy-turn-card { border: 1px solid var(--line-dim); background: rgba(255, 255, 255, 0.022); transition: border-color 0.16s ease, background-color 0.16s ease; flex-shrink: 0; }',
      'body.paper-ink-theme .agy-turn-card { background: rgba(0, 0, 0, 0.025); }',
      '.agy-turn-card:hover { border-color: var(--line-mid); }',
      '.agy-turn-card.expanded { border-color: var(--line-strong); background: rgba(242, 242, 245, 0.042); }',
      'body.paper-ink-theme .agy-turn-card.expanded { background: rgba(17, 18, 21, 0.045); }',
      '.agy-turn-hdr { width: 100%; background: transparent; border: none; color: var(--ink-primary); padding: 9px 13px; display: flex; align-items: center; gap: 9px; cursor: pointer; text-align: left; }',
      '.agy-turn-hdr:hover { background: rgba(255, 255, 255, 0.03); }',
      '.agy-turn-badge { font-family: var(--font-mono); font-size: 9.5px; font-weight: 600; letter-spacing: 0.06em; padding: 2px 7px; border: 1px solid var(--line-strong); background: var(--accent-invert-bg); color: var(--accent-invert-fg); white-space: nowrap; flex-shrink: 0; }',
      '.agy-turn-title { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI Variable Text", "Segoe UI", "PingFang SC", "Microsoft YaHei UI", sans-serif; font-size: 13.5px; font-weight: 600; color: var(--ink-primary); flex: 1 1 auto; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }',
      '.agy-turn-meta { display: flex; align-items: center; gap: 6px; font-family: var(--font-mono); font-size: 8.8px; color: var(--ink-muted); flex-shrink: 0; }',
      '.agy-turn-chev { font-family: var(--font-mono); font-size: 11px; color: var(--ink-primary); width: 14px; text-align: center; transition: transform 0.18s ease; flex-shrink: 0; }',
      '.agy-turn-card.expanded .agy-turn-chev { transform: rotate(90deg); }',
      '.agy-turn-body { display: none; border-top: 1px solid var(--line-faint); padding: 11px 15px 14px; flex-direction: column; gap: 10px; }',
      '.agy-turn-card.expanded .agy-turn-body { display: flex; }',
      '.agy-turn-sec { padding: 9px 13px; border-left: 2px solid var(--line-dim); background: rgba(0, 0, 0, 0.20); }',
      'body.paper-ink-theme .agy-turn-sec { background: rgba(255, 255, 255, 0.56); }',
      '.agy-turn-sec.user-req { border-left-color: var(--line-strong); }',
      '.agy-turn-sec-lbl { font-family: var(--font-mono); font-size: 8.8px; letter-spacing: 0.08em; color: var(--ink-muted); margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center; gap: 8px; }',
      '',
      '/* Antigravity-Grade Structured Markdown Typography */',
      '.agy-msg-user-text {',
      '  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI Variable Text", "Segoe UI", "Inter", "PingFang SC", "Microsoft YaHei UI", sans-serif;',
      '  font-size: 13.6px; line-height: 1.68; color: var(--ink-primary); white-space: pre-wrap; word-break: break-word; user-select: text; -webkit-user-select: text;',
      '}',
      '.agy-msg-body {',
      '  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI Variable Text", "Segoe UI", "Inter", "PingFang SC", "Microsoft YaHei UI", sans-serif;',
      '  font-size: 13.7px; line-height: 1.72; color: var(--ink-primary); white-space: normal; word-break: break-word; user-select: text; -webkit-user-select: text;',
      '}',
      '.agy-md-p { margin: 0 0 9px 0; }',
      '.agy-md-p:last-child { margin-bottom: 0; }',
      '.agy-md-h { font-weight: 600; color: var(--ink-primary); margin: 12px 0 6px 0; line-height: 1.38; }',
      '.agy-md-h:first-child { margin-top: 2px; }',
      '.agy-md-h1 { font-size: 16.5px; border-bottom: 1px solid var(--line-faint); padding-bottom: 4px; }',
      '.agy-md-h2 { font-size: 15px; border-bottom: 1px solid var(--line-faint); padding-bottom: 3px; }',
      '.agy-md-h3 { font-size: 14px; }',
      '.agy-md-h4 { font-size: 13.5px; color: var(--ink-muted); }',
      '.agy-md-list { margin: 5px 0 10px 0; padding-left: 21px; display: flex; flex-direction: column; gap: 5px; }',
      '.agy-md-list:last-child { margin-bottom: 0; }',
      '.agy-md-sublist { margin: 4px 0 2px 0; padding-left: 18px; gap: 3px; }',
      '.agy-md-list li { line-height: 1.68; }',
      '.agy-md-li-cont { margin-top: 3px; }',
      '.agy-md-hr { border: none; border-top: 1px solid var(--line-faint); margin: 10px 0; }',
      '.agy-md-quote { margin: 6px 0 10px 0; padding: 6px 11px; border-left: 2.5px solid var(--line-mid); background: rgba(255,255,255,0.03); color: var(--ink-muted); }',
      '.agy-md-table-wrap { overflow-x: auto; margin: 8px 0 10px 0; }',
      '.agy-md-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }',
      '.agy-md-table th, .agy-md-table td { border: 1px solid var(--line-dim); padding: 5px 9px; text-align: left; }',
      '.agy-md-table th { background: rgba(255,255,255,0.06); font-weight: 600; }',
      '.agy-code-wrap { margin: 8px 0 10px 0; border: 1px solid var(--line-dim); background: rgba(0, 0, 0, 0.42); overflow: hidden; }',
      'body.paper-ink-theme .agy-code-wrap { background: rgba(0, 0, 0, 0.055); }',
      '.agy-code-hdr { display: flex; justify-content: space-between; align-items: center; padding: 4px 10px; border-bottom: 1px solid var(--line-faint); background: rgba(255,255,255,0.03); font-family: var(--font-mono); font-size: 9px; color: var(--ink-muted); text-transform: uppercase; }',
      '.agy-code-copy-btn { background: transparent; border: 1px solid var(--line-dim); color: var(--ink-muted); font-family: var(--font-mono); font-size: 8.8px; padding: 1px 6px; cursor: pointer; }',
      '.agy-code-copy-btn:hover { color: var(--ink-primary); border-color: var(--line-strong); }',
      '.agy-msg-pre { margin: 0; padding: 9px 11px; font-family: var(--font-mono); font-size: 11.5px; line-height: 1.52; overflow-x: auto; white-space: pre; }',
      '.agy-inline-code { font-family: var(--font-mono); font-size: 11.8px; padding: 1px 5px; border: 1px solid var(--line-dim); background: rgba(255,255,255,0.06); border-radius: 3px; }',
      'body.paper-ink-theme .agy-inline-code { background: rgba(0,0,0,0.06); }',
      '.agy-file-pill {',
      '  display: inline-flex; align-items: center; gap: 4px; background: rgba(255,255,255,0.05); border: 1px solid var(--line-mid);',
      '  color: var(--ink-primary); font-family: var(--font-mono); font-size: 11px; padding: 1px 7px; margin: 1px 2px; border-radius: 3px; cursor: pointer;',
      '}',
      '.agy-file-pill:hover { background: var(--accent-invert-bg); color: var(--accent-invert-fg); border-color: var(--line-strong); }',
      '.agy-web-link { color: var(--ink-primary); text-decoration: underline; text-underline-offset: 2px; }',
      '',
      '/* Interactive User Attachment Chips (Left-click: Open File, Right-click: Open Location) */',
      '.agy-turn-att-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 7px; }',
      '.agy-turn-att-chip {',
      '  font-family: var(--font-mono); font-size: 10px; color: var(--ink-primary); border: 1px solid var(--line-mid);',
      '  padding: 3px 9px; background: rgba(255,255,255,0.045); cursor: pointer; display: inline-flex; align-items: center; gap: 6px;',
      '  transition: background-color 0.15s ease, border-color 0.15s ease;',
      '}',
      '.agy-turn-att-chip:hover { background: var(--accent-invert-bg); color: var(--accent-invert-fg); border-color: var(--line-strong); }',
      '.agy-att-kind-tag { font-size: 8.4px; opacity: 0.72; border: 1px solid currentColor; padding: 0 3px; }',
      '',
      '/* Queue Action Controls (`主动送进去插队` + `撤回`) */',
      '.agy-queue-ctrl-bar { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; margin-top: 7px; padding-top: 6px; border-top: 1px dashed var(--line-faint); font-family: var(--font-mono); font-size: 9.5px; color: var(--ink-muted); }',
      '.agy-queue-btn-group { display: inline-flex; align-items: center; gap: 6px; }',
      '.agy-q-act-btn { background: transparent; border: 1px solid var(--line-strong); color: var(--ink-primary); font-family: var(--font-mono); font-size: 9.6px; padding: 2px 9px; cursor: pointer; transition: all 0.15s ease; }',
      '.agy-q-act-btn.primary { background: var(--accent-invert-bg); color: var(--accent-invert-fg); font-weight: 600; }',
      '.agy-q-act-btn:hover { opacity: 0.88; transform: translateY(-0.5px); }',
      '.agy-send-mode-switch { display: inline-flex; border: 1px solid var(--line-dim); overflow: hidden; }',
      '.agy-smode-btn { background: transparent; border: none; color: var(--ink-muted); font-family: var(--font-mono); font-size: 9.4px; padding: 3px 8px; cursor: pointer; transition: all 0.15s ease; }',
      '.agy-smode-btn.active { background: var(--accent-invert-bg); color: var(--accent-invert-fg); font-weight: 600; }',
      '.agy-interrupt-send-btn {',
      '  background: transparent; border: 1px solid var(--line-strong); color: var(--ink-primary);',
      '  font-family: var(--font-mono); font-size: 10.2px; font-weight: 600; padding: 0 12px; cursor: pointer; white-space: nowrap;',
      '  transition: all 0.15s ease;',
      '}',
      '.agy-interrupt-send-btn:hover { background: var(--accent-invert-bg); color: var(--accent-invert-fg); }',
      '.agy-interrupt-send-btn:disabled { opacity: 0.42; cursor: wait; }',
      '.agy-stop-exec-btn {',
      '  background: rgba(255, 255, 255, 0.08); border: 1.5px solid var(--line-strong); color: var(--ink-primary);',
      '  font-family: var(--font-mono); font-size: 10.4px; font-weight: 600; padding: 0 13px; cursor: pointer; white-space: nowrap;',
      '  display: inline-flex; align-items: center; justify-content: center; gap: 5px; letter-spacing: 0.04em;',
      '  transition: all 0.15s ease;',
      '}',
      'body.paper-ink-theme .agy-stop-exec-btn { background: rgba(17, 18, 22, 0.07); }',
      '.agy-stop-exec-btn:hover { background: var(--accent-invert-bg); color: var(--accent-invert-fg); }',
      '.agy-stop-exec-btn:disabled { opacity: 0.45; cursor: wait; }',
      '',
      '#agy-drop-overlay { position: absolute; inset: 6px; z-index: 40; display: none; align-items: center; justify-content: center; flex-direction: column; gap: 8px; background: rgba(6, 6, 10, 0.88); border: 2px dashed var(--line-strong); color: var(--ink-primary); font-family: var(--font-mono); font-size: 13px; letter-spacing: 0.08em; pointer-events: none; }',
      'body.paper-ink-theme #agy-drop-overlay { background: rgba(242, 240, 234, 0.92); }',
      '#agy-core-modal.drag-over #agy-drop-overlay { display: flex; }',
      '.agy-att-tray { display: none; flex-wrap: wrap; gap: 7px; margin-bottom: 7px; padding: 6px 8px; border: 1px dashed var(--line-mid); background: rgba(0, 0, 0, 0.22); max-height: 112px; overflow-y: auto; }',
      '.agy-att-tray.has-items { display: flex; }',
      '.agy-att-item { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--line-dim); background: rgba(255, 255, 255, 0.05); padding: 3px 7px; font-family: var(--font-mono); font-size: 9.5px; color: var(--ink-primary); max-width: 240px; }',
      '.agy-att-thumb { width: 26px; height: 26px; object-fit: cover; border: 1px solid var(--line-dim); flex-shrink: 0; }',
      '.agy-att-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }',
      '.agy-att-rm { background: transparent; border: none; color: var(--ink-muted); cursor: pointer; font-size: 11px; padding: 0 2px; }',
      '.agy-att-rm:hover { color: var(--ink-primary); }',
      '.agy-attach-btn { background: transparent; border: 1px solid var(--line-dim); color: var(--ink-primary); font-family: var(--font-mono); font-size: 9.5px; padding: 3px 8px; cursor: pointer; white-space: nowrap; }',
      '.agy-attach-btn:hover { border-color: var(--line-strong); background: var(--bg-panel-hover); }',
      '.agy-live-working-banner { font-family: var(--font-mono); font-size: 9.8px; color: var(--ink-primary); border: 1px dashed var(--line-mid); padding: 6px 11px; display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }',
      '.agy-empty-hint { margin: auto; text-align: center; font-family: var(--font-mono); font-size: 10px; color: var(--ink-muted); line-height: 1.65; padding: 18px 12px; }',
      '.agy-composer-box { border-top: 1px solid var(--line-dim); padding: 10px 15px 12px; background: var(--line-faint); flex-shrink: 0; }',
      '.agy-composer-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }',
      '.agy-model-sel { background: transparent; border: 1px solid var(--line-dim); color: var(--ink-primary); font-family: var(--font-mono); font-size: 9.8px; padding: 3px 6px; outline: none; max-width: 280px; }',
      '.agy-model-sel option { background: #0b0b0e; color: #f2f2f5; }',
      '.agy-verbatim-tag { font-family: var(--font-mono); font-size: 8.8px; color: var(--ink-muted); white-space: nowrap; }',
      '.agy-composer-row { display: flex; gap: 7px; align-items: stretch; }',
      '.agy-chat-ta { flex: 1; min-height: 58px; max-height: 168px; resize: vertical; background: rgba(0, 0, 0, 0.22); border: 1px solid var(--line-dim); color: var(--ink-primary); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei UI", sans-serif; font-size: 12.6px; line-height: 1.52; padding: 7px 10px; outline: none; }',
      'body.paper-ink-theme .agy-chat-ta { background: rgba(255, 255, 255, 0.65); }',
      '.agy-chat-ta:focus { border-color: var(--line-strong); }',
      '.agy-send-primary { background: var(--accent-invert-bg); color: var(--accent-invert-fg); border: 1px solid var(--line-strong); font-family: var(--font-mono); font-size: 10.6px; font-weight: 600; padding: 0 18px; cursor: pointer; white-space: nowrap; }',
      '.agy-send-primary:disabled { opacity: 0.45; cursor: wait; }',
      '.wb-opt-btn:disabled { opacity: 0.45; cursor: wait; pointer-events: none; }',
      '',
      '/* ======================================================================',
      '   AI USAGE EMBEDDED DASHBOARD (Shared by Workbench Telemetry & Ornamental Deck)',
      '   ====================================================================== */',
      '.aiu-root {',
      '  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI Variable Text", "Segoe UI", "PingFang SC", "Microsoft YaHei UI", sans-serif;',
      '  color: var(--ink-primary); display: flex; flex-direction: column; gap: 9px; font-size: 11.5px;',
      '}',
      '.aiu-topbar { display: flex; justify-content: space-between; align-items: center; gap: 6px; padding-bottom: 5px; border-bottom: 1px solid var(--line-faint); flex-wrap: wrap; }',
      '.aiu-brand-tabs { display: inline-flex; align-items: center; gap: 10px; }',
      '.aiu-brand { font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.14em; color: var(--ink-muted); }',
      '.aiu-main-tab { background: transparent; border: none; color: var(--ink-muted); font-size: 12px; font-weight: 600; padding: 2px 4px; cursor: pointer; border-bottom: 2px solid transparent; }',
      '.aiu-main-tab.active { color: var(--ink-primary); border-bottom-color: var(--line-strong); }',
      '.aiu-periods { display: flex; align-items: center; justify-content: space-between; gap: 4px; flex-wrap: wrap; position: relative; }',
      '.aiu-period-group { display: inline-flex; align-items: center; gap: 6px; flex-wrap: wrap; }',
      '.aiu-p-btn { background: transparent; border: none; color: var(--ink-muted); font-size: 11.2px; padding: 2px 3px; cursor: pointer; border-bottom: 1.5px solid transparent; }',
      '.aiu-p-btn:hover { color: var(--ink-primary); }',
      '.aiu-p-btn.active { color: var(--ink-primary); font-weight: 600; border-bottom-color: var(--line-strong); }',
      '.aiu-cal-btn { background: transparent; border: 1px solid var(--line-dim); color: var(--ink-muted); font-size: 10.2px; padding: 2px 7px; border-radius: 4px; cursor: pointer; }',
      '.aiu-cal-btn.active, .aiu-cal-btn:hover { color: var(--ink-primary); border-color: var(--line-strong); }',
      '.aiu-cal-pop { border: 1px solid var(--line-strong); background: var(--bg-panel); padding: 8px; display: flex; flex-direction: column; gap: 6px; }',
      '.aiu-cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 3px; text-align: center; font-family: var(--font-mono); font-size: 9.6px; }',
      '.aiu-cal-day { background: transparent; border: 1px solid transparent; color: var(--ink-muted); padding: 3px 0; cursor: pointer; }',
      '.aiu-cal-day.has-data { color: var(--ink-primary); background: rgba(255,255,255,0.05); }',
      '.aiu-cal-day.selected { background: var(--accent-invert-bg); color: var(--accent-invert-fg); font-weight: 600; }',
      '.aiu-hero { padding: 4px 0 2px; display: flex; flex-direction: column; gap: 5px; }',
      '.aiu-hero-val-row { display: flex; align-items: baseline; gap: 5px; flex-wrap: wrap; }',
      '.aiu-hero-num { font-family: "Segoe UI Light", "Inter", sans-serif; font-size: 36px; font-weight: 300; line-height: 1.05; letter-spacing: -0.02em; color: var(--ink-primary); }',
      '#ornamental-deck .aiu-hero-num { font-size: 29px; }',
      '.aiu-hero-unit { font-size: 14px; color: var(--ink-muted); }',
      '.aiu-hero-sub { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 11px; color: var(--ink-muted); }',
      '.aiu-unit-sel { background: rgba(255,255,255,0.05); border: 1px solid var(--line-dim); color: #e2b97f; font-family: var(--font-mono); font-size: 10.4px; padding: 2px 7px; border-radius: 4px; outline: none; cursor: pointer; }',
      'body.paper-ink-theme .aiu-unit-sel { color: #8a5a19; background: rgba(0,0,0,0.04); }',
      '.aiu-unit-sel option { background: #0d0d11; color: #f2f2f5; }',
      '.aiu-kpi-grid { display: grid; grid-template-columns: repeat(3, 1fr); border-top: 1px solid var(--line-faint); border-bottom: 1px solid var(--line-faint); padding: 8px 0; }',
      '.aiu-kpi-cell { padding: 0 8px; border-right: 1px solid var(--line-faint); display: flex; flex-direction: column; gap: 3px; }',
      '.aiu-kpi-cell:first-child { padding-left: 2px; }',
      '.aiu-kpi-cell:last-child { border-right: none; }',
      '.aiu-kpi-lbl { font-size: 10px; color: var(--ink-muted); }',
      '.aiu-kpi-val { font-family: var(--font-mono); font-size: 15.5px; color: var(--ink-primary); }',
      '#ornamental-deck .aiu-kpi-val { font-size: 13px; }',
      '.aiu-kpi-val small { font-size: 10px; color: var(--ink-muted); margin-left: 2px; }',
      '.aiu-box { border: 1px solid var(--line-dim); background: rgba(255,255,255,0.02); padding: 8px 10px; border-radius: 4px; display: flex; flex-direction: column; gap: 6px; }',
      'body.paper-ink-theme .aiu-box { background: rgba(0,0,0,0.025); }',
      '.aiu-sec-hdr { display: flex; justify-content: space-between; align-items: baseline; gap: 6px; font-size: 10.2px; color: var(--ink-muted); letter-spacing: 0.04em; flex-wrap: wrap; }',
      '.aiu-q-line { display: flex; justify-content: space-between; align-items: center; gap: 6px; font-size: 11px; flex-wrap: wrap; }',
      '.aiu-gold { color: #e2b97f; font-family: var(--font-mono); }',
      'body.paper-ink-theme .aiu-gold { color: #8a5a19; }',
      '.aiu-pool-row { display: flex; flex-direction: column; gap: 3px; padding-top: 4px; border-top: 1px dashed var(--line-faint); }',
      '.aiu-bar-track { width: 100%; height: 5px; background: rgba(255,255,255,0.08); overflow: hidden; border-radius: 2px; display: flex; }',
      'body.paper-ink-theme .aiu-bar-track { background: rgba(0,0,0,0.10); }',
      '.aiu-bar-fill { height: 100%; background: var(--ink-primary); transition: width 0.25s ease; }',
      '.aiu-bar-fill.warm { background: #e2b97f; }',
      '.aiu-bar-fill.mid { background: var(--line-mid); }',
      '.aiu-rank-row { display: flex; flex-direction: column; gap: 2px; }',
      '.aiu-rank-top { display: flex; justify-content: space-between; gap: 6px; font-size: 10.8px; }',
      '.aiu-trend-bars { display: flex; align-items: flex-end; gap: 3px; height: 68px; padding-top: 6px; border-bottom: 1px solid var(--line-faint); }',
      '.aiu-tbar-col { flex: 1; min-width: 0; height: 100%; display: flex; flex-direction: column; justify-content: flex-end; align-items: center; gap: 2px; }',
      '.aiu-tbar { width: 100%; max-width: 18px; background: rgba(242,242,245,0.72); min-height: 1px; border-radius: 1px 1px 0 0; }',
      'body.paper-ink-theme .aiu-tbar { background: rgba(17,18,22,0.72); }',
      '.aiu-tbar.today { background: #e2b97f; }',
      '.aiu-tbar-lbl { font-family: var(--font-mono); font-size: 8px; color: var(--ink-muted); white-space: nowrap; overflow: hidden; max-width: 100%; }',
      '.aiu-live-card { border: 1px solid var(--line-mid); background: rgba(14, 13, 12, 0.72); padding: 9px 11px; border-radius: 4px; display: flex; flex-direction: column; gap: 5px; }',
      'body.paper-ink-theme .aiu-live-card { background: rgba(255,255,255,0.72); }',
      '.aiu-sess-item { border: 1px solid var(--line-faint); background: rgba(255,255,255,0.018); padding: 7px 9px; display: flex; flex-direction: column; gap: 4px; cursor: pointer; }',
      '.aiu-sess-item:hover { border-color: var(--line-mid); }',
      '.aiu-turn-sub { border-top: 1px dashed var(--line-faint); margin-top: 4px; padding-top: 5px; display: flex; flex-direction: column; gap: 5px; cursor: default; }',
      '.aiu-turn-row { padding: 5px 7px; background: rgba(0,0,0,0.22); border-left: 2px solid var(--line-mid); font-size: 10.5px; display: flex; flex-direction: column; gap: 2px; }'
    ].join('\n');
    document.head.appendChild(style);
  }

  function buildModelOptionsHtml() {
    return [
      '<option value="inherit">模型: 跟随对话默认设置</option>',
      '<option value="gemini-4-carbon-medium">Gemini 4 Carbon (Medium)</option>',
      '<option value="gemini-4-carbon-high">Gemini 4 Carbon (High)</option>',
      '<option value="gemini-4-argon-high">Gemini 4 Argon (High)</option>',
      '<option value="claude-opus-5-5-high">Claude Opus 5.5 (High)</option>',
      '<option value="claude-sonnet-5-5-high">Claude Sonnet 5.5 (High)</option>',
      '<option value="gemini-3.8-flash-high">Gemini 3.8 Flash (High)</option>'
    ].join('');
  }

  function buildSendModeSwitchHtml(prefix) {
    const isInt = composerSendMode === 'interrupt';
    return (
      '<div class="agy-send-mode-switch" role="group" aria-label="发送排队或插队模式">' +
      '  <button type="button" class="agy-smode-btn' + (!isInt ? ' active' : '') + '" data-smode="queue" title="默认排队：若当前有任务在运行，排在当前轮次之后依次执行">排队发送</button>' +
      '  <button type="button" class="agy-smode-btn' + (isInt ? ' active' : '') + '" data-smode="interrupt" title="主动插队：发送后立即送入当前正在运行的智能体轮次（等同 Antigravity 插队送入）">' + ICON_BOLT + ' 插队送入</button>' +
      '</div>'
    );
  }

  function syncSendModeSwitchUI() {
    if (IS_WALLPAPER_VIEW) return;
    const isInt = composerSendMode === 'interrupt';
    const isRunning = (currentStatus === 'running');
    document.querySelectorAll('[data-smode]').forEach(function (btn) {
      btn.classList.toggle('active', btn.getAttribute('data-smode') === composerSendMode);
    });
    ['agy-send-btn', 'agy-wb-send-btn'].forEach(function (id) {
      const b = document.getElementById(id);
      if (b) b.innerHTML = isInt ? (ICON_BOLT + ' 插队发送') : '✦ 发送';
    });
    ['agy-interrupt-now-btn', 'agy-wb-interrupt-now-btn'].forEach(function (id) {
      const b = document.getElementById(id);
      if (b) {
        b.style.display = (!isInt && isRunning) ? 'inline-block' : 'none';
      }
    });
    ['agy-stop-btn', 'agy-wb-stop-btn'].forEach(function (id) {
      const b = document.getElementById(id);
      if (b) {
        b.style.display = isRunning ? 'inline-flex' : 'none';
        if (!isRunning) {
          b.disabled = false;
          b.innerHTML = ICON_STOP + ' 停止';
        }
      }
    });
  }

  // ==========================================================================
  // DOM Construction
  // ==========================================================================
  function buildPanelDOM() {
    if (IS_WALLPAPER_VIEW) return;
    if (document.getElementById('codex-agy-wing-shell') || document.getElementById('agy-workbench-drawer')) return;
    injectStyles();

    // A. Top-Left Mode Button (Mounted as leftmost button inside #top-left-toolbar right beside 司仪台!)
    const dockTrigger = document.createElement('button');
    dockTrigger.type = 'button';
    dockTrigger.id = 'agy-left-dock-trigger';
    dockTrigger.title = '从最左侧平滑展开 / 收起 Antigravity 对话列表与工作台';
    dockTrigger.innerHTML = [
      '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="1.5"/><path d="M9 4v16M13 9h5M13 13h4"/></svg>',
      '<span id="agy-left-dock-label">AGENT 控制台</span>',
      '<span id="agy-left-dock-unread"></span>'
    ].join('');
    const topLeftBar = document.getElementById('top-left-toolbar');
    if (topLeftBar) {
      topLeftBar.insertBefore(dockTrigger, topLeftBar.firstChild);
    } else {
      document.body.appendChild(dockTrigger);
    }

    // B. Left Slide-Out Dual-Column Agent Workbench (`#agy-workbench-drawer` — defaults to `.sidebar-only` on open!)
    const wb = document.createElement('section');
    wb.id = 'agy-workbench-drawer';
    wb.className = 'sidebar-only';
    wb.setAttribute('aria-label', '左侧双栏 Agent 交互与内嵌设置工作台');
    wb.innerHTML = [
      '<div id="agy-wb-sidebar">',
      '  <div class="agy-wb-side-top">',
      '    <div class="agy-wb-brand-row">',
      '      <span id="agy-wb-brand-title" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">ANTIGRAVITY AGENT</span>',
      '      <div class="agy-wb-brand-actions">',
      '        <button type="button" id="btn-wb-refresh-list" class="mini-close-deck-btn" title="刷新会话列表">↻</button>',
      '        <button type="button" id="btn-wb-toggle-main" class="mini-close-deck-btn" title="展开或收起右侧对话/设置栏（保留当前对话列表）">对话栏 ▸</button>',
      '        <button type="button" id="btn-wb-close-sidebar" class="mini-close-deck-btn" title="关闭整个左侧 AGENT 控制台">⇤ 关闭</button>',
      '      </div>',
      '    </div>',
      '    <button type="button" id="btn-wb-new-session" title="新建空白会话并在右侧直接展开对话"><span>＋ 新建会话</span></button>',
      '  </div>',
      '  <div id="agy-wb-session-list" role="listbox" aria-label="会话列表（左键展开对话 · 右键置顶/归档/删除）"></div>',
      '  <div class="agy-wb-side-footer">',
      '    <button type="button" id="btn-wb-view-chat" class="agy-wb-foot-btn" title="展开或收起右侧对话栏（再次点击可只收起对话栏并保留左侧列表）">◈ 对话</button>',
      '    <button type="button" id="btn-wb-view-settings" class="agy-wb-foot-btn" title="在右侧展开或收起全部圣轮与 AI Usage 内嵌设置">' + ICON_GEAR + ' 设置</button>',
      '  </div>',
      '</div>',
      '<div id="agy-wb-col-splitter" title="左右拖动调节会话列表与右侧对话/设置区域的宽度"></div>',
      '<div id="agy-wb-main">',
      '  <!-- Right Pane View 1: Full Agent Chat -->',
      '  <div id="agy-wb-chat-pane">',
      '    <div id="agy-wb-drop-overlay">',
      '      <div>✦ 松开鼠标添加图片或文件至当前会话</div>',
      '      <div style="font-size:10.5px;color:var(--ink-muted);">支持截图、源码与任意文档直接拖入</div>',
      '    </div>',
      '    <div class="agy-wb-main-hdr">',
      '      <div style="min-width:0;display:flex;flex-direction:column;gap:2px;">',
      '        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">',
      '          <span id="agy-wb-chat-title">正在同步当前会话...</span>',
      '          <span id="agy-wb-status-pill" class="agy-st-pill idle">待命</span>',
      '          <button type="button" id="btn-wb-ack-unread" class="mini-close-deck-btn" style="display:none;" title="查收已完成任务，熄灭白球提醒">✓ 已查收</button>',
      '        </div>',
      '        <span id="agy-wb-binding-counts">薄板 0 · 圣瞳 0 · 蜂群 0</span>',
      '      </div>',
      '      <div class="agy-hdr-actions">',
      '        <button type="button" id="btn-wb-toggle-turns" class="mini-close-deck-btn" title="一键展开或折叠所有对话轮次">展开全部</button>',
      '        <button type="button" id="btn-wb-collapse-drawer" class="mini-close-deck-btn" title="仅收起右侧对话栏，保留左侧对话列表">⇤ 收起对话</button>',
      '      </div>',
      '    </div>',
      '    <div id="agy-wb-completed-bar" class="agy-completed-bar"></div>',
      '    <div id="agy-wb-chat-stream" aria-live="polite">',
      '      <div class="agy-empty-hint">正在同步本地会话...</div>',
      '    </div>',
      '    <div class="agy-composer-box">',
      '      <div class="agy-composer-top">',
      '        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">',
      '          <select id="agy-wb-model-select" class="agy-model-sel" title="选择执行模型">' + buildModelOptionsHtml() + '</select>',
      '          <button type="button" id="btn-wb-attach" class="agy-attach-btn" title="选择图片或文件，也支持拖入或 Ctrl+V 粘贴图片">+ 添加图片/文件</button>',
      '          <input type="file" id="agy-wb-file-input" multiple style="display:none;" />',
      '          ' + buildSendModeSwitchHtml('wb'),
      '        </div>',
      '        <span class="agy-verbatim-tag">Ctrl+Enter 立即插队送入</span>',
      '      </div>',
      '      <div id="agy-wb-attachment-tray" class="agy-att-tray"></div>',
      '      <div class="agy-composer-row">',
      '        <textarea id="agy-wb-chat-input" class="agy-chat-ta" placeholder="输入指令与 Agent 对话（Enter 发送，Ctrl+Enter 立即插队送入，Shift+Enter 换行，Ctrl+V 粘贴截图）..."></textarea>',
      '        <button type="button" id="agy-wb-stop-btn" class="agy-stop-exec-btn" style="display:none;" title="立即停止暂停当前正在执行的生成轮次">' + ICON_STOP + ' 停止</button>',
      '        <button type="button" id="agy-wb-interrupt-now-btn" class="agy-interrupt-send-btn" style="display:none;" title="不等当前轮结束，直接插队送入当前运行会话">' + ICON_BOLT + ' 插队</button>',
      '        <button type="button" id="agy-wb-send-btn" class="agy-send-primary">✦ 发送</button>',
      '      </div>',
      '    </div>',
      '  </div>',
      '  <!-- Right Pane View 2: In-Place Embedded Settings Suite -->',
      '  <div id="agy-wb-settings-pane">',
      '    <div class="agy-wb-main-hdr">',
      '      <div>',
      '        <div class="agy-core-kicker">EMBEDDED SANCTUM SETTINGS // 内嵌独立设置中心（不跳出外部弹窗）</div>',
      '        <div style="font-family:var(--font-serif);font-size:15.5px;font-weight:600;color:var(--ink-primary);">圣轮美化包 · 全功能内嵌控制中心</div>',
      '      </div>',
      '      <div class="agy-hdr-actions">',
      '        <button type="button" id="btn-wb-settings-to-chat" class="mini-close-deck-btn" title="切回对话窗口">◈ 返回对话</button>',
      '        <button type="button" id="btn-wb-collapse-from-set" class="mini-close-deck-btn" title="仅收起右侧设置栏，保留左侧对话列表">⇤ 收起设置</button>',
      '      </div>',
      '    </div>',
      '    <div class="agy-wb-set-nav" role="tablist">',
      '      <button type="button" class="agy-wb-set-tab active" data-wb-stab="quick">1 · 快捷与视图</button>',
      '      <button type="button" class="agy-wb-set-tab" data-wb-stab="codex">2 · 圣轮司仪参数</button>',
      '      <button type="button" class="agy-wb-set-tab" data-wb-stab="telemetry">3 · 遥测与额度</button>',
      '      <button type="button" class="agy-wb-set-tab" data-wb-stab="wallpaper">4 · 桌面动态壁纸</button>',
      '    </div>',
      '    <div id="agy-wb-settings-body"></div>',
      '  </div>',
      '</div>',
      '<div id="agy-wb-outer-resizer" title="左右拖拽调节控制台宽度"></div>'
    ].join('');
    document.body.appendChild(wb);

    // C. Mutual Bidirectional Collapsible Session List Wing <-> #codex-panel (司仪台与会话列表可互相独立收起/只留任意一边)
    const codexEl = document.getElementById('codex-panel');
    const codexHdrActions = document.getElementById('codex-hdr-actions');
    if (codexHdrActions && !document.getElementById('btn-codex-session-wing')) {
      const foldCodexBtn = document.createElement('button');
      foldCodexBtn.type = 'button';
      foldCodexBtn.id = 'btn-fold-codex-body';
      foldCodexBtn.className = 'mini-close-deck-btn';
      foldCodexBtn.title = '把左侧司仪台参数面板向右收起，只保留右侧会话列表';
      foldCodexBtn.textContent = '只留列表 ▸';
      codexHdrActions.insertBefore(foldCodexBtn, codexHdrActions.firstChild);
      foldCodexBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        setCodexBodyCollapsed(true);
      });

      const wingBtn = document.createElement('button');
      wingBtn.type = 'button';
      wingBtn.id = 'btn-codex-session-wing';
      wingBtn.className = 'mini-close-deck-btn';
      wingBtn.title = '在司仪台右侧平滑长出 / 收起会话列表';
      wingBtn.textContent = '会话列表 ▸';
      codexHdrActions.insertBefore(wingBtn, foldCodexBtn);
      wingBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        setPanelVisible(!panelVisible);
      });
    }

    const wingShell = document.createElement('div');
    wingShell.id = 'codex-agy-wing-shell';
    wingShell.setAttribute('aria-label', '司仪台右侧可双向折叠会话列表');
    wingShell.innerHTML = [
      '<div id="codex-agy-wing">',
      '  <div class="codex-wing-hdr" id="codex-wing-drag-handle" title="按住此处可自由拖动会话列表位置">',
      '    <div>',
      '      <div class="codex-kicker">SESSIONS WING // 可与司仪台双向互收</div>',
      '      <div class="codex-title" id="agy-wing-brand-title" style="font-size:13.5px;">ANTIGRAVITY 会话列表</div>',
      '    </div>',
      '    <div class="agy-hdr-actions">',
      '      <button type="button" id="btn-wing-toggle-codex" class="mini-close-deck-btn" title="把左侧司仪台向右收起只留会话列表，或重新向左展开司仪台">收起司仪 ▸</button>',
      '      <button type="button" id="btn-agy-refresh" class="mini-close-deck-btn" title="刷新会话列表">刷新</button>',
      '      <button type="button" id="btn-agy-hide" class="mini-close-deck-btn" title="向司仪台内折叠收起会话列表">◂ 收起</button>',
      '    </div>',
      '  </div>',
      '  <div class="agy-beam-mode-bar" role="group" aria-label="圣轮光束驱动模式切换">',
      '    <button type="button" class="agy-beam-pill active" data-agy-beam="tool_io">调用收发</button>',
      '    <button type="button" class="agy-beam-pill" data-agy-beam="model_active">工作随动</button>',
      '    <button type="button" class="agy-beam-pill" data-agy-beam="ambient">常驻流光</button>',
      '  </div>',
      '  <div class="agy-sub-toolbar">',
      '    <div class="agy-sec-title">',
      '      <span>SESSIONS</span>',
      '      <span id="agy-conv-count-badge">(加载中...)</span>',
      '    </div>',
      '    <button type="button" id="btn-agy-new-conv" class="agy-new-conv-btn">+ 新建对话</button>',
      '  </div>',
      '  <div id="agy-session-list" role="listbox" aria-label="会话列表"></div>',
      '  <button type="button" id="btn-agy-open-core" title="点击中央圣球或此按钮查看回执与发消息">',
      '    <span id="agy-binding-mini"><span class="core-dot"></span>点击中央圣球查看回执与发消息</span>',
      '    <span>开启核心 ⇢</span>',
      '  </button>',
      '</div>'
    ].join('');

    if (codexEl) {
      codexEl.appendChild(wingShell);
    } else {
      document.body.appendChild(wingShell);
    }

    // D. Central Black/White Sphere Core Modal (Mode A — Center-Locked 8-Way Symmetric Resizing!)
    const coreBackdrop = document.createElement('div');
    coreBackdrop.id = 'agy-core-modal-backdrop';
    coreBackdrop.setAttribute('aria-label', '座天使中央圣球 · 会话回执与任务派发圣枢');
    coreBackdrop.innerHTML = [
      '<div id="agy-core-modal" role="dialog" aria-modal="true">',
      '  <div class="agy-core-rs agy-core-rs-n" data-crs="n" title="上下对称拉伸高度（始终保持屏幕居中）"></div>',
      '  <div class="agy-core-rs agy-core-rs-s" data-crs="s" title="上下对称拉伸高度（始终保持屏幕居中）"></div>',
      '  <div class="agy-core-rs agy-core-rs-e" data-crs="e" title="左右对称拉伸宽度（始终保持屏幕居中）"></div>',
      '  <div class="agy-core-rs agy-core-rs-w" data-crs="w" title="左右对称拉伸宽度（始终保持屏幕居中）"></div>',
      '  <div class="agy-core-rs agy-core-rs-nw" data-crs="nw" title="对称拉伸长宽（始终保持屏幕居中）"></div>',
      '  <div class="agy-core-rs agy-core-rs-ne" data-crs="ne" title="按住右上角自由拉伸长宽大小（始终保持正中心居中！）"></div>',
      '  <div class="agy-core-rs agy-core-rs-sw" data-crs="sw" title="对称拉伸长宽（始终保持屏幕居中）"></div>',
      '  <div class="agy-core-rs agy-core-rs-se" data-crs="se" title="按住右下角自由拉伸长宽大小（始终保持正中心居中！）"></div>',
      '  <div id="agy-drop-overlay">',
      '    <div>✦ 松开鼠标添加图片或文件至本轮对话</div>',
      '    <div style="font-size:10.5px;color:var(--ink-muted);">支持任意图片与代码/文档文件直接拖入</div>',
      '  </div>',
      '  <div class="agy-core-modal-hdr">',
      '    <div>',
      '      <div class="agy-core-kicker">CENTRAL CORE // 座天使中央圣球 · 四边及右上角/右下角可居中拉伸大小</div>',
      '      <div class="agy-core-title-row">',
      '        <span id="agy-core-modal-title">正在同步当前会话...</span>',
      '        <span id="agy-core-status-pill" class="agy-st-pill idle">待命</span>',
      '        <span id="agy-core-binding-counts">薄板 0 · 圣瞳 0 · 蜂群 0</span>',
      '      </div>',
      '    </div>',
      '    <div class="agy-hdr-actions">',
      '      <button type="button" id="btn-agy-toggle-all-turns" class="mini-close-deck-btn">展开全部</button>',
      '      <button type="button" id="btn-agy-core-new" class="mini-close-deck-btn">+ 新对话</button>',
      '      <button type="button" id="btn-close-agy-core-modal" class="mini-close-deck-btn">✕ 关闭</button>',
      '    </div>',
      '  </div>',
      '  <div id="agy-core-completed-bar" class="agy-completed-bar"></div>',
      '  <div id="agy-chat-stream" aria-live="polite">',
      '    <div class="agy-empty-hint">正在同步本地 Antigravity 真实会话回执...</div>',
      '  </div>',
      '  <div class="agy-composer-box">',
      '    <div class="agy-composer-top">',
      '      <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">',
      '        <select id="agy-model-select" class="agy-model-sel">' + buildModelOptionsHtml() + '</select>',
      '        <button type="button" id="btn-agy-attach" class="agy-attach-btn">+ 拖入/添加图片与文件</button>',
      '        <input type="file" id="agy-file-input" multiple style="display:none;" />',
      '        ' + buildSendModeSwitchHtml('core'),
      '      </div>',
      '      <span class="agy-verbatim-tag">Ctrl+Enter 立即插队送入 · 附件左键打开 / 右键定位目录</span>',
      '    </div>',
      '    <div id="agy-attachment-tray" class="agy-att-tray"></div>',
      '    <div class="agy-composer-row">',
      '      <textarea id="agy-chat-input" class="agy-chat-ta" placeholder="在此输入新任务，或直接拖入图片/文件一并发送（Enter 发送，Ctrl+Enter 立即插队送入，Shift+Enter 换行）..."></textarea>',
      '      <button type="button" id="agy-stop-btn" class="agy-stop-exec-btn" style="display:none;" title="立即停止暂停当前正在执行的生成轮次">' + ICON_STOP + ' 停止</button>',
      '      <button type="button" id="agy-interrupt-now-btn" class="agy-interrupt-send-btn" style="display:none;" title="不等当前轮结束，直接插队送入当前运行会话">' + ICON_BOLT + ' 插队送入</button>',
      '      <button type="button" id="agy-send-btn" class="agy-send-primary">✦ 发送</button>',
      '    </div>',
      '  </div>',
      '</div>'
    ].join('');
    document.body.appendChild(coreBackdrop);

    // E. Clean Monochrome Right-Click Context Menu (Zero Colored Emojis!)
    const ctxMenu = document.createElement('div');
    ctxMenu.id = 'agy-session-ctx-menu';
    ctxMenu.setAttribute('role', 'menu');
    ctxMenu.innerHTML = [
      '<button type="button" class="agy-ctx-item" data-ctx-act="toggle_pin"><span id="ctx-lbl-pin">置顶会话</span><span class="ctx-sub">PIN</span></button>',
      '<button type="button" class="agy-ctx-item" data-ctx-act="toggle_archive"><span id="ctx-lbl-arch">归档会话</span><span class="ctx-sub">ARCH</span></button>',
      '<button type="button" class="agy-ctx-item" data-ctx-act="mark_read" id="ctx-btn-read"><span>标记已查收</span><span class="ctx-sub">ACK</span></button>',
      '<div class="agy-ctx-sep"></div>',
      '<button type="button" class="agy-ctx-item" data-ctx-act="delete"><span>删除会话</span><span class="ctx-sub">DEL</span></button>'
    ].join('');
    document.body.appendChild(ctxMenu);

    applyWorkbenchWidths();
    applyCoreModalSavedSize();
    wireWorkbenchResizers(wb);
    wireCoreModalSymmetricResizer(document.getElementById('agy-core-modal'));
    wireAllEvents(wb, wingShell, coreBackdrop, ctxMenu, dockTrigger);
    wireAiUsageMountDelegation(document.getElementById('orn-ai-usage-mount'));

    if (window.ophanimAgent) {
      if (typeof window.ophanimAgent.getBeamMode === 'function') {
        syncBeamModeUI(window.ophanimAgent.getBeamMode());
      }
      if (typeof window.ophanimAgent.onControlChange === 'function') {
        window.ophanimAgent.onControlChange(function () {
          if (workbenchOpen && workbenchRightPane === 'settings') {
            syncEmbeddedSettingsLiveValues();
          }
        });
      }
    }

    // 60fps Tortoise-Smooth RAF loop for Workbench Telemetry Canvas + periodic AI Usage sync
    function workbenchTelemetryRafLoop() {
      requestAnimationFrame(workbenchTelemetryRafLoop);
      if (workbenchOpen && workbenchRightPane === 'settings' && workbenchSettingsTab === 'telemetry') {
        drawEmbeddedTelemetryChart();
      }
    }
    requestAnimationFrame(workbenchTelemetryRafLoop);

    if (!IS_WALLPAPER_VIEW) {
      setInterval(function () {
        if (workbenchOpen && workbenchRightPane === 'settings' && workbenchSettingsTab === 'telemetry') {
          syncEmbeddedSettingsLiveValues();
        }
      }, 500);

      // Initial + periodic AI Usage fetch for Ornamental Deck & Workbench Telemetry
      setTimeout(function () { requestAiUsageData(false); }, 450);
      setInterval(function () {
        const ornVisible = document.getElementById('ornamental-deck') && !document.getElementById('ornamental-deck').classList.contains('hidden-hud');
        const wbTelVisible = workbenchOpen && workbenchRightPane === 'settings' && workbenchSettingsTab === 'telemetry';
        if (ornVisible || wbTelVisible) {
          requestAiUsageData(false);
        }
      }, 10000);
    }
  }

  // ==========================================================================
  // Center-Locked Symmetric Resizer for #agy-core-modal
  // ==========================================================================
  function applyCoreModalSavedSize() {
    const modalEl = document.getElementById('agy-core-modal');
    if (!modalEl) return;
    const vw = Math.max(680, window.innerWidth || 1440);
    const vh = Math.max(500, window.innerHeight || 900);
    if (coreModalWidthPx >= 620) {
      modalEl.style.width = Math.min(vw - 24, coreModalWidthPx) + 'px';
    }
    if (coreModalHeightPx >= 440) {
      modalEl.style.height = Math.min(vh - 24, coreModalHeightPx) + 'px';
    }
  }

  function wireCoreModalSymmetricResizer(modalEl) {
    if (!modalEl) return;
    let resizing = false;
    let dir = '';
    let startX = 0, startY = 0, startW = 0, startH = 0;
    const minW = 620, minH = 440;

    modalEl.querySelectorAll('.agy-core-rs').forEach(function (h) {
      h.addEventListener('mousedown', function (e) {
        if (e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();
        const rect = modalEl.getBoundingClientRect();
        resizing = true;
        dir = h.getAttribute('data-crs') || 'ne';
        startX = e.clientX;
        startY = e.clientY;
        startW = rect.width;
        startH = rect.height;
        modalEl.classList.add('resizing-now');
      });
    });

    window.addEventListener('mousemove', function (e) {
      if (!resizing) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      const maxW = Math.max(minW, (window.innerWidth || 1440) - 24);
      const maxH = Math.max(minH, (window.innerHeight || 900) - 24);

      let nextW = startW;
      let nextH = startH;

      // Multiply delta by 2 because flexbox keeps #agy-core-modal dead-center symmetrically!
      if (dir.indexOf('e') !== -1) {
        nextW = Math.max(minW, Math.min(maxW, Math.round(startW + dx * 2)));
      } else if (dir.indexOf('w') !== -1) {
        nextW = Math.max(minW, Math.min(maxW, Math.round(startW - dx * 2)));
      }

      if (dir.indexOf('s') !== -1) {
        nextH = Math.max(minH, Math.min(maxH, Math.round(startH + dy * 2)));
      } else if (dir.indexOf('n') !== -1) {
        nextH = Math.max(minH, Math.min(maxH, Math.round(startH - dy * 2)));
      }

      coreModalWidthPx = nextW;
      coreModalHeightPx = nextH;
      modalEl.style.width = nextW + 'px';
      modalEl.style.height = nextH + 'px';
    });

    window.addEventListener('mouseup', function () {
      if (!resizing) return;
      resizing = false;
      modalEl.classList.remove('resizing-now');
      try {
        window.localStorage.setItem(STORAGE_MODAL_SIZE_KEY, JSON.stringify({
          w: coreModalWidthPx,
          h: coreModalHeightPx
        }));
      } catch (err) { /* ignore */ }
    });

    window.addEventListener('resize', applyCoreModalSavedSize);
  }

  // ==========================================================================
  // Workbench Slide, Sidebar-Only Default & Independent Right-Pane Collapse
  // ==========================================================================
  function syncWorkbenchModeButtonsUI() {
    const wb = document.getElementById('agy-workbench-drawer');
    const btnChat = document.getElementById('btn-wb-view-chat');
    const btnSet = document.getElementById('btn-wb-view-settings');
    const btnToggleMain = document.getElementById('btn-wb-toggle-main');
    if (wb) {
      wb.classList.toggle('sidebar-only', !workbenchMainExpanded);
      wb.classList.toggle('settings-mode', workbenchMainExpanded && workbenchRightPane === 'settings');
    }
    if (btnChat) {
      btnChat.classList.toggle('active', workbenchMainExpanded && workbenchRightPane === 'chat');
    }
    if (btnSet) {
      btnSet.classList.toggle('active', workbenchMainExpanded && workbenchRightPane === 'settings');
    }
    if (btnToggleMain) {
      btnToggleMain.classList.toggle('active', workbenchMainExpanded);
      btnToggleMain.textContent = workbenchMainExpanded ? '◂ 收起对话' : '对话栏 ▸';
    }
  }

  function applyWorkbenchWidths() {
    const wb = document.getElementById('agy-workbench-drawer');
    const side = document.getElementById('agy-wb-sidebar');
    const vw = Math.max(640, window.innerWidth || 1440);
    workbenchWidthPx = Math.max(520, Math.min(vw - 28, workbenchWidthPx));
    workbenchSidebarWidthPx = Math.max(186, Math.min(Math.min(480, workbenchWidthPx - 290), workbenchSidebarWidthPx));
    if (wb) {
      wb.classList.toggle('sidebar-only', !workbenchMainExpanded);
      wb.style.width = (workbenchMainExpanded ? workbenchWidthPx : workbenchSidebarWidthPx) + 'px';
    }
    if (side) {
      side.style.width = (workbenchMainExpanded ? (workbenchSidebarWidthPx + 'px') : '100%');
    }
    syncWorkbenchModeButtonsUI();
  }

  function setWorkbenchMainExpanded(expandFlag) {
    workbenchMainExpanded = Boolean(expandFlag);
    applyWorkbenchWidths();
    if (workbenchOpen && workbenchMainExpanded) {
      if (workbenchRightPane === 'settings') {
        renderEmbeddedSettingsBody();
        if (workbenchSettingsTab === 'telemetry') requestAiUsageData(false);
      } else {
        scheduleSnapStreamsToBottom(['agy-wb-chat-stream']);
      }
    }
  }

  function setWorkbenchOpen(openFlag, expandMainOpt) {
    const nextOpen = Boolean(openFlag);
    // When opening from closed state via top-left AGENT 控制台 button, default to Sidebar-Only (left conversation list only!)
    if (nextOpen && !workbenchOpen && typeof expandMainOpt !== 'boolean') {
      workbenchMainExpanded = false;
    } else if (typeof expandMainOpt === 'boolean') {
      workbenchMainExpanded = expandMainOpt;
    }
    workbenchOpen = nextOpen;
    const wb = document.getElementById('agy-workbench-drawer');
    const trig = document.getElementById('agy-left-dock-trigger');
    const lbl = document.getElementById('agy-left-dock-label');
    applyWorkbenchWidths();
    if (wb) wb.classList.toggle('open', workbenchOpen);
    if (trig) trig.classList.toggle('active', workbenchOpen);
    if (lbl) lbl.textContent = workbenchOpen ? '收起 AGENT 台' : 'AGENT 控制台';
    if (workbenchOpen && workbenchMainExpanded) {
      if (workbenchRightPane === 'settings') {
        renderEmbeddedSettingsBody();
      } else {
        scheduleSnapStreamsToBottom(['agy-wb-chat-stream']);
      }
    }
    if (window.ophanimAgent && typeof window.ophanimAgent.syncPanelVisibility === 'function') {
      window.ophanimAgent.syncPanelVisibility();
    }
  }

  function switchWorkbenchRightPane(paneMode, forceExpand) {
    workbenchRightPane = paneMode === 'settings' ? 'settings' : 'chat';
    if (forceExpand !== false) {
      workbenchMainExpanded = true;
    }
    applyWorkbenchWidths();
    if (workbenchMainExpanded && workbenchRightPane === 'settings') {
      renderEmbeddedSettingsBody();
      if (workbenchSettingsTab === 'telemetry') requestAiUsageData(false);
    } else if (workbenchOpen && workbenchMainExpanded && workbenchRightPane === 'chat') {
      scheduleSnapStreamsToBottom(['agy-wb-chat-stream']);
    }
  }

  function wireWorkbenchResizers(wbEl) {
    const outerHandle = document.getElementById('agy-wb-outer-resizer');
    const colSplitter = document.getElementById('agy-wb-col-splitter');
    let dragKind = '';
    let startX = 0, startOuterW = 0, startColW = 0;

    if (outerHandle) {
      outerHandle.addEventListener('mousedown', function (e) {
        if (e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();
        dragKind = workbenchMainExpanded ? 'outer' : 'sidebar_outer';
        startX = e.clientX;
        startOuterW = workbenchWidthPx;
        startColW = workbenchSidebarWidthPx;
        wbEl.classList.add('resizing-now');
      });
    }
    if (colSplitter) {
      colSplitter.addEventListener('mousedown', function (e) {
        if (e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();
        dragKind = 'col';
        startX = e.clientX;
        startColW = workbenchSidebarWidthPx;
        colSplitter.classList.add('active');
        wbEl.classList.add('resizing-now');
      });
    }

    window.addEventListener('mousemove', function (e) {
      if (!dragKind) return;
      const dx = e.clientX - startX;
      if (dragKind === 'outer') {
        workbenchWidthPx = startOuterW + dx;
        applyWorkbenchWidths();
      } else if (dragKind === 'col' || dragKind === 'sidebar_outer') {
        workbenchSidebarWidthPx = startColW + dx;
        applyWorkbenchWidths();
      }
    });

    window.addEventListener('mouseup', function () {
      if (!dragKind) return;
      dragKind = '';
      wbEl.classList.remove('resizing-now');
      if (colSplitter) colSplitter.classList.remove('active');
    });

    window.addEventListener('resize', applyWorkbenchWidths);
  }

  // ==========================================================================
  // AI USAGE FULL DASHBOARD ENGINE (Mounted in BOTH Workbench & Ornamental Deck!)
  // ==========================================================================
  function requestAiUsageData(forceFlag) {
    if (IS_WALLPAPER_VIEW) return;
    const now = Date.now();
    if (aiUsageState.loading && !forceFlag) return;
    if (!forceFlag && aiUsageState.loadedOnce && (now - aiUsageState.lastFetchMs) < 3500) return;
    aiUsageState.loading = true;
    aiUsageState.lastFetchMs = now;

    if (activeWS && activeWS.readyState === 1) {
      try {
        activeWS.send(JSON.stringify({ type: 'ophanim_ai_usage_query', force: Boolean(forceFlag) }));
        return;
      } catch (err) { /* fallback HTTP */ }
    }
    fetch(HTTP_API_BASE + '/api/ai-usage' + (forceFlag ? '?force=1' : ''))
      .then(function (r) { return r.json(); })
      .then(function (data) { handleAiUsagePayload(data); })
      .catch(function (err) {
        aiUsageState.loading = false;
        aiUsageState.error = String(err || '连接失败');
        renderAllAiUsageMounts();
      });
  }

  function requestAiUsageSessionTurns(sessId) {
    if (IS_WALLPAPER_VIEW) return;
    if (!sessId || aiUsageState.loadingTurnsIds.has(sessId)) return;
    aiUsageState.loadingTurnsIds.add(sessId);
    renderAllAiUsageMounts();
    if (activeWS && activeWS.readyState === 1) {
      try {
        activeWS.send(JSON.stringify({ type: 'ophanim_ai_usage_turns', id: sessId }));
        return;
      } catch (err) { /* fallback HTTP */ }
    }
    fetch(HTTP_API_BASE + '/api/ai-usage/turns?id=' + encodeURIComponent(sessId))
      .then(function (r) { return r.json(); })
      .then(function (data) { handleAiUsageTurnsPayload(data); })
      .catch(function () {
        aiUsageState.loadingTurnsIds.delete(sessId);
        renderAllAiUsageMounts();
      });
  }

  function handleAiUsagePayload(payload) {
    if (IS_WALLPAPER_VIEW) return;
    aiUsageState.loading = false;
    if (!payload || !payload.ok || !payload.overview) {
      aiUsageState.error = (payload && payload.error) ? payload.error : '暂无 AI Usage 统计数据';
      renderAllAiUsageMounts();
      return;
    }
    aiUsageState.loadedOnce = true;
    aiUsageState.error = '';
    aiUsageState.overview = payload.overview;
    aiUsageState.sessions = payload.sessions || {};
    if (!aiUsageState.calMonth && payload.overview.today) {
      aiUsageState.calMonth = String(payload.overview.today).slice(0, 7);
    }
    renderAllAiUsageMounts();
  }

  function handleAiUsageTurnsPayload(payload) {
    if (IS_WALLPAPER_VIEW) return;
    const sid = payload && payload.id ? String(payload.id) : '';
    if (sid) aiUsageState.loadingTurnsIds.delete(sid);
    if (payload && payload.ok && sid) {
      aiUsageState.turnsBySessId[sid] = Array.isArray(payload.turns) ? payload.turns : [];
    }
    renderAllAiUsageMounts();
  }

  function getActivePeriodSummary(ov) {
    const p = aiUsageState.period;
    if (ov.periods && ov.periods[p]) return ov.periods[p];
    if (ov.by_day && ov.by_day[p]) return ov.by_day[p];
    return (ov.periods && ov.periods.all) || { total: 0, cache: 0, output: 0, msgs: 0, active_ms: 0, tools: {}, models: {} };
  }

  function getActiveQuotaPeriod(qObj) {
    if (!qObj) return {};
    const p = aiUsageState.period;
    if (qObj.periods && qObj.periods[p]) return qObj.periods[p];
    if (qObj.by_day && qObj.by_day[p]) return qObj.by_day[p];
    return (qObj.periods && qObj.periods.all) || {};
  }

  function getPeriodDisplayName(p) {
    const names = { today: '今天', yesterday: '昨天', week: '近 7 天', month: '本月', all: '全部时间' };
    return names[p] || p;
  }

  function computePeriodTotals(sumObj, qPeriodMap) {
    const tokTotal = Number(sumObj.total) || 0;
    const gGem = qPeriodMap.gemini || { p5: 0, pw: 0, cost: 0 };
    const g3p = qPeriodMap['3p'] || { p5: 0, pw: 0, cost: 0 };
    const gDsh = qPeriodMap.dsh || { p5: 0, pw: 0, cost: 0, tokens: 0, turns: 0 };
    const totalQuota5hPct = (Number(gGem.p5) || 0) + (Number(g3p.p5) || 0);
    const totalQuotaWkPct = (Number(gGem.pw) || 0) + (Number(g3p.pw) || 0);
    let estUsd = (Number(gGem.cost) || 0) + (Number(g3p.cost) || 0) + (Number(gDsh.cost) || 0);
    if (estUsd <= 0 && tokTotal > 0) {
      estUsd = (tokTotal / 1e6) * 0.28;
    }
    const estCny = Math.round(estUsd * USD_TO_CNY);
    return {
      tokTotal: tokTotal,
      quota5hPct: totalQuota5hPct,
      quotaWkPct: totalQuotaWkPct,
      estUsd: estUsd,
      estCny: estCny,
      gem: gGem,
      tp: g3p,
      dsh: gDsh
    };
  }

  function buildCalendarPopupHtml(ov) {
    if (!aiUsageState.calOpen) return '';
    const curYm = aiUsageState.calMonth || String(ov.today || '2026-11-15').slice(0, 7);
    const parts = curYm.split('-');
    const yr = parseInt(parts[0], 10) || 2026;
    const mo = parseInt(parts[1], 10) || 1;
    const firstDow = new Date(yr, mo - 1, 1).getDay();
    const daysInMo = new Date(yr, mo, 0).getDate();
    const cells = [];
    ['日', '一', '二', '三', '四', '五', '六'].forEach(function (w) {
      cells.push('<span style="color:var(--ink-muted);padding:2px 0;">' + w + '</span>');
    });
    for (let b = 0; b < firstDow; b++) cells.push('<span></span>');
    const daily = ov.daily || {};
    for (let d = 1; d <= daysInMo; d++) {
      const iso = yr + '-' + String(mo).padStart(2, '0') + '-' + String(d).padStart(2, '0');
      const hasVal = (Number(daily[iso]) || 0) > 0;
      const isSel = aiUsageState.period === iso;
      cells.push(
        '<button type="button" class="aiu-cal-day' + (hasVal ? ' has-data' : '') + (isSel ? ' selected' : '') + '" data-aiu-day="' + iso + '" title="' + iso + (hasVal ? (' · ' + fmtCnTokens(daily[iso]).full + ' tok') : '') + '">' + d + '</button>'
      );
    }
    return (
      '<div class="aiu-cal-pop">' +
      '  <div style="display:flex;justify-content:space-between;align-items:center;font-family:var(--font-mono);font-size:10px;">' +
      '    <button type="button" class="mini-close-deck-btn" data-aiu-calnav="-1">‹ 上月</button>' +
      '    <strong>' + yr + ' 年 ' + mo + ' 月</strong>' +
      '    <div style="display:inline-flex;gap:4px;">' +
      '      <button type="button" class="mini-close-deck-btn" data-aiu-day="' + escapeHtml(ov.today || '') + '">今</button>' +
      '      <button type="button" class="mini-close-deck-btn" data-aiu-calnav="1">下月 ›</button>' +
      '    </div>' +
      '  </div>' +
      '  <div class="aiu-cal-grid">' + cells.join('') + '</div>' +
      '</div>'
    );
  }

  function buildTrendSectionHtml(ov) {
    const daily = ov.daily || {};
    const gran = aiUsageState.trendGran;
    const buckets = [];
    if (gran === 'day') {
      const baseDate = ov.today ? new Date(ov.today + 'T00:00:00') : new Date();
      const span = 14;
      const endShift = aiUsageState.trendOffset * span;
      for (let i = span - 1; i >= 0; i--) {
        const d = new Date(baseDate);
        d.setDate(d.getDate() - i + endShift);
        const iso = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
        buckets.push({ key: iso, label: String(d.getMonth() + 1) + '/' + String(d.getDate()), val: Number(daily[iso]) || 0, isToday: iso === ov.today });
      }
    } else if (gran === 'month') {
      const monthMap = {};
      Object.keys(daily).forEach(function (d) {
        const ym = d.slice(0, 7);
        monthMap[ym] = (monthMap[ym] || 0) + (Number(daily[d]) || 0);
      });
      const sortedM = Object.keys(monthMap).sort().slice(-12);
      sortedM.forEach(function (ym) {
        buckets.push({ key: ym, label: ym.slice(5) + '月', val: monthMap[ym], isToday: ym === String(ov.today || '').slice(0, 7) });
      });
    } else {
      const yearMap = {};
      Object.keys(daily).forEach(function (d) {
        const yy = d.slice(0, 4);
        yearMap[yy] = (yearMap[yy] || 0) + (Number(daily[d]) || 0);
      });
      Object.keys(yearMap).sort().forEach(function (yy) {
        buckets.push({ key: yy, label: yy, val: yearMap[yy], isToday: yy === String(ov.today || '').slice(0, 4) });
      });
    }

    const maxV = Math.max(1, Math.max.apply(null, buckets.map(function (b) { return b.val; }).concat([1])));
    const barsHtml = buckets.map(function (b) {
      const hPct = b.val > 0 ? Math.max(4, Math.round((b.val / maxV) * 100)) : 1;
      return (
        '<div class="aiu-tbar-col" title="' + escapeHtml(b.key + ': ' + fmtCnTokens(b.val).full + ' tok') + '">' +
        '  <div class="aiu-tbar' + (b.isToday ? ' today' : '') + '" style="height:' + hPct + '%;"></div>' +
        '  <span class="aiu-tbar-lbl">' + escapeHtml(b.label) + '</span>' +
        '</div>'
      );
    }).join('');

    return (
      '<div class="aiu-box">' +
      '  <div class="aiu-sec-hdr">' +
      '    <span>趋势 · TREND</span>' +
      '    <div style="display:inline-flex;gap:4px;align-items:center;">' +
      (gran === 'day' ? '<button type="button" class="mini-close-deck-btn" data-aiu-tnav="-1">‹</button><button type="button" class="mini-close-deck-btn" data-aiu-tnav="1">›</button>' : '') +
      '      <button type="button" class="mini-close-deck-btn' + (gran === 'day' ? ' active' : '') + '" data-aiu-tgran="day">日</button>' +
      '      <button type="button" class="mini-close-deck-btn' + (gran === 'month' ? ' active' : '') + '" data-aiu-tgran="month">月</button>' +
      '      <button type="button" class="mini-close-deck-btn' + (gran === 'year' ? ' active' : '') + '" data-aiu-tgran="year">年</button>' +
      '    </div>' +
      '  </div>' +
      '  <div class="aiu-trend-bars">' + barsHtml + '</div>' +
      '</div>'
    );
  }

  function buildLiveCurrentSessionCardHtml(cur) {
    if (!cur) return '';
    const nt = cur.now_turn;
    const hitPct = cur.hit != null ? Math.round(cur.hit * 100) + '%' : '--';
    const rightBigPct = nt && nt.p5 != null ? (Number(nt.p5).toFixed(2) + '%') : (cur.q5 != null ? (Number(cur.q5).toFixed(1) + '%') : fmtCnTokens(cur.total).full);
    const rightDelta = nt ? ('+' + fmtCnTokens(nt.tokens).full) : (cur.turns + ' 轮');

    let turnDetailHtml = '';
    if (nt) {
      const acctEmail = nt.account || '--';
      const tierLbl = nt.tier || '--';
      const p5Str = Number(nt.p5 || 0).toFixed(2) + '%';
      const pwStr = Number(nt.pw || 0).toFixed(2) + '%';
      turnDetailHtml =
        '<div class="aiu-q-line" style="font-size:10.4px;color:var(--ink-muted);">' +
        '  <span>本轮额度 &nbsp;5小时 <span class="aiu-gold">' + p5Str + '</span> · 每周 <span class="aiu-gold">' + pwStr + '</span></span>' +
        '  <button type="button" class="aiu-p-btn" data-aiu-toggle-live="1" style="font-size:10px;">第 ' + nt.turn + ' 轮已用 ' + (aiUsageState.liveNowExpanded ? '▴' : '▾') + '</button>' +
        '</div>' +
        '<div style="font-size:10.4px;color:var(--ink-muted);">' +
        '  本轮用量 <span class="aiu-gold">' + fmtCnTokens(nt.tokens).full + '</span> tok (输入 ' + fmtCnTokens(nt.input).full + ' · 缓存 ' + fmtCnTokens(nt.cache).full + ' · 回复 ' + fmtCnTokens(nt.output).full + ')' +
        '</div>' +
        (aiUsageState.liveNowExpanded
          ? (
            '<div style="border-top:1px solid var(--line-faint);padding-top:5px;margin-top:2px;display:flex;flex-direction:column;gap:3px;font-size:10.4px;">' +
            '  <div class="aiu-q-line"><span style="color:var(--ink-muted);">本轮使用模型</span><span class="aiu-gold">' + escapeHtml(nt.model_label || nt.model || cur.model) + '</span></div>' +
            '  <div class="aiu-q-line"><span style="color:var(--ink-muted);">消耗额度账号</span><span><span class="aiu-gold">' + escapeHtml(acctEmail) + '</span> <span style="border:1px solid var(--line-dim);padding:0 5px;font-size:9.2px;color:var(--ink-muted);">' + escapeHtml(tierLbl) + '</span></span></div>' +
            '  <div class="aiu-q-line"><span style="color:var(--ink-muted);">本轮额度归属</span><span>扣自该账号额度池 · 5小时 <span class="aiu-gold">' + p5Str + '</span> / 每周 <span class="aiu-gold">' + pwStr + '</span></span></div>' +
            '</div>'
          )
          : '');
    }

    return (
      '<div class="aiu-live-card">' +
      '  <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">' +
      '    <div style="min-width:0;flex:1;">' +
      '      <div style="font-size:11.2px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' +
      '        <span class="aiu-gold">● 进行中</span> &nbsp;' + escapeHtml(cur.title) +
      '      </div>' +
      '      <div style="font-size:10.6px;color:var(--ink-muted);margin-top:2px;">' +
      '        <strong style="color:var(--ink-primary);">' + (cur.turns || 1) + ' 轮 ' + (cur.msgs || 1) + ' 步</strong> · <strong style="color:var(--ink-primary);">' + fmtCnTokens(cur.total).full + '</strong> tok · 缓存命中 <strong>' + hitPct + '</strong>' +
      '      </div>' +
      '    </div>' +
      '    <div style="text-align:right;flex-shrink:0;">' +
      '      <div class="aiu-gold" style="font-size:18px;line-height:1.05;">' + escapeHtml(rightBigPct) + '</div>' +
      '      <div style="font-size:9.8px;color:var(--ink-muted);">' + escapeHtml(rightDelta) + '</div>' +
      '    </div>' +
      '  </div>' +
      turnDetailHtml +
      '</div>'
    );
  }

  function buildSessionsTabHtml(sessPayload) {
    if (!sessPayload || sessPayload.error) {
      return '<div class="agy-empty-hint">' + escapeHtml((sessPayload && sessPayload.error) || '暂无对话用量记录') + '</div>';
    }
    const p = aiUsageState.period;
    let rawList = [];
    if (sessPayload[p] && Array.isArray(sessPayload[p])) rawList = sessPayload[p].slice();
    else if (sessPayload.by_day && Array.isArray(sessPayload.by_day[p])) rawList = sessPayload.by_day[p].slice();
    else if (Array.isArray(sessPayload.all)) rawList = sessPayload.all.slice();

    if (aiUsageState.sessSort === 'total') {
      rawList.sort(function (a, b) { return (b.total || 0) - (a.total || 0); });
    } else if (aiUsageState.sessSort === 'avg_turn') {
      rawList.sort(function (a, b) {
        return ((b.total || 0) / Math.max(1, b.turns || 1)) - ((a.total || 0) / Math.max(1, a.turns || 1));
      });
    } else {
      rawList.sort(function (a, b) { return String(b.last || '').localeCompare(String(a.last || '')); });
    }

    const shown = rawList.slice(0, 45);
    const rowsHtml = shown.map(function (s) {
      const isExp = aiUsageState.expandedSessIds.has(s.id);
      const hitStr = s.hit != null ? Math.round(s.hit * 100) + '%' : '--';
      const qTag = s.q5 != null && s.q5 > 0
        ? ('5h ' + Number(s.q5).toFixed(2) + '% · 周 ' + Number(s.qw || 0).toFixed(2) + '%')
        : (s.cost > 0 ? ('$' + Number(s.cost).toFixed(2)) : '');
      let turnsSubHtml = '';
      if (isExp) {
        if (aiUsageState.loadingTurnsIds.has(s.id)) {
          turnsSubHtml = '<div class="aiu-turn-sub"><div style="color:var(--ink-muted);font-size:10px;">正在加载每轮明细...</div></div>';
        } else {
          const tList = aiUsageState.turnsBySessId[s.id] || [];
          if (tList.length === 0) {
            turnsSubHtml = '<div class="aiu-turn-sub"><div style="color:var(--ink-muted);font-size:10px;">暂无分轮明细</div></div>';
          } else {
            turnsSubHtml = '<div class="aiu-turn-sub">' + tList.slice(0, 25).map(function (tr) {
              const filesBtns = Array.isArray(tr.files) && tr.files.length > 0
                ? ('<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:2px;">' + tr.files.slice(0, 6).map(function (fp) {
                    const pStr = typeof fp === 'string' ? fp : (fp && (fp.path || fp.file) || '');
                    const fName = pStr.split(/[\\/]/).pop() || '文件';
                    return '<button type="button" class="agy-file-pill" data-open-path="' + escapeHtml(pStr) + '" data-open-name="' + escapeHtml(fName) + '" title="左键打开 · 右键定位: ' + escapeHtml(pStr) + '">' + escapeHtml(fName) + '</button>';
                  }).join('') + '</div>')
                : '';
              return (
                '<div class="aiu-turn-row">' +
                '  <div class="aiu-q-line">' +
                '    <strong>第 ' + tr.turn + ' 轮 · ' + escapeHtml(tr.model_label || tr.model || '') + '</strong>' +
                '    <span class="aiu-gold">' + fmtCnTokens(tr.tokens).full + ' tok' + (tr.p5 ? (' · 5h ' + Number(tr.p5).toFixed(2) + '%') : '') + '</span>' +
                '  </div>' +
                (tr.user_text ? ('  <div style="color:var(--ink-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + escapeHtml(String(tr.user_text).slice(0, 90)) + '</div>') : '') +
                '  <div style="color:var(--ink-muted);font-size:9.6px;">账号: ' + escapeHtml(tr.account || '') + ' (' + escapeHtml(tr.tier || '') + ') · ' + (tr.steps || 1) + ' 步 · ' + escapeHtml(tr.day + ' ' + tr.hm) + '</div>' +
                filesBtns +
                '</div>'
              );
            }).join('') + '</div>';
          }
        }
      }

      return (
        '<div class="aiu-sess-item" data-aiu-sess="' + escapeHtml(s.id) + '">' +
        '  <div class="aiu-q-line">' +
        '    <strong style="flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + (isExp ? '▾ ' : '▸ ') + escapeHtml(s.title) + '</strong>' +
        '    <span class="aiu-gold">' + fmtCnTokens(s.total).full + ' tok</span>' +
        '  </div>' +
        '  <div class="aiu-q-line" style="font-size:9.8px;color:var(--ink-muted);">' +
        '    <span>' + escapeHtml(s.tool) + ' · ' + escapeHtml(s.model) + ' · ' + (s.turns || 1) + '轮/' + (s.msgs || 1) + '步 · 命中' + hitStr + '</span>' +
        (qTag ? ('    <span>' + escapeHtml(qTag) + '</span>') : '') +
        '  </div>' +
        turnsSubHtml +
        '</div>'
      );
    }).join('');

    return (
      '<div style="display:flex;justify-content:space-between;align-items:center;gap:6px;flex-wrap:wrap;">' +
      '  <span style="font-size:10px;color:var(--ink-muted);">共 ' + rawList.length + ' 个对话 (' + escapeHtml(getPeriodDisplayName(p)) + ') · 点击展开每轮明细</span>' +
      '  <div style="display:inline-flex;gap:4px;">' +
      '    <button type="button" class="mini-close-deck-btn' + (aiUsageState.sessSort === 'recent' ? ' active' : '') + '" data-aiu-sort="recent">最近</button>' +
      '    <button type="button" class="mini-close-deck-btn' + (aiUsageState.sessSort === 'total' ? ' active' : '') + '" data-aiu-sort="total">最多</button>' +
      '    <button type="button" class="mini-close-deck-btn' + (aiUsageState.sessSort === 'avg_turn' ? ' active' : '') + '" data-aiu-sort="avg_turn">每轮最多</button>' +
      '  </div>' +
      '</div>' +
      '<div style="display:flex;flex-direction:column;gap:5px;">' + (rowsHtml || '<div class="agy-empty-hint">所选时段无对话记录</div>') + '</div>'
    );
  }

  function buildAiUsageHtml() {
    if (!aiUsageState.loadedOnce) {
      if (aiUsageState.error) {
        return (
          '<div class="aiu-root">' +
          '  <div class="aiu-topbar"><span class="aiu-brand">AI USAGE</span><button type="button" class="mini-close-deck-btn" data-aiu-refresh="1">↻ 重试</button></div>' +
          '  <div class="agy-empty-hint">' + escapeHtml(aiUsageState.error) + '</div>' +
          '</div>'
        );
      }
      return '<div class="aiu-root"><div class="agy-empty-hint">正在同步本机 AI Usage 全量数据...</div></div>';
    }

    const ov = aiUsageState.overview;
    const qObj = ov.quota || {};
    const sumObj = getActivePeriodSummary(ov);
    const qPeriod = getActiveQuotaPeriod(qObj);
    const calc = computePeriodTotals(sumObj, qPeriod);
    const p = aiUsageState.period;
    const isCustomDay = !['today', 'yesterday', 'week', 'month', 'all'].includes(p);

    // Hero primary value based on unitMode
    let heroNum = '';
    let heroUnit = '';
    let subSummary = '';
    if (aiUsageState.unitMode === 'quota') {
      heroNum = calc.quota5hPct.toFixed(1);
      heroUnit = '% (5h 累计额度)';
      subSummary = fmtCnTokens(calc.tokTotal).full + ' tok · 周额度 ' + calc.quotaWkPct.toFixed(1) + '% · 约 $' + calc.estUsd.toFixed(1) + ' (¥' + calc.estCny.toLocaleString() + ')';
    } else if (aiUsageState.unitMode === 'usd') {
      heroNum = '$' + calc.estUsd.toFixed(1);
      heroUnit = '(≈ ¥' + calc.estCny.toLocaleString() + ')';
      subSummary = fmtCnTokens(calc.tokTotal).full + ' tok · 额度 ' + calc.quota5hPct.toFixed(1) + '%';
    } else {
      const fTok = fmtCnTokens(calc.tokTotal);
      heroNum = fTok.num;
      heroUnit = fTok.unit;
      subSummary = '额度 ' + calc.quota5hPct.toFixed(1) + '% · 约 $' + calc.estUsd.toFixed(1) + ' (¥' + calc.estCny.toLocaleString() + ')';
    }

    const steps = Math.max(0, Number(sumObj.msgs) || 0);
    const hours = ((Number(sumObj.active_ms) || 0) / 3600000).toFixed(1);
    const avgPerStep = steps > 0 ? fmtCnTokens(calc.tokTotal / steps) : { num: '0', unit: '' };

    // Quota groups & DeepSeek ledger
    const acct = qObj.account || { email: '', tier: '' };
    const tierShort = String(acct.tier || '--').replace(/^Google AI\s+/i, '');
    const dshLed = qObj.dsh_ledger || {};
    const dshCny = calc.dsh.cost > 0 ? (calc.dsh.cost * USD_TO_CNY) : (Number(dshLed.total_spent_cny) || 0);
    const dshBal = dshLed.balance_cny != null ? (' · 余额 ¥' + Number(dshLed.balance_cny).toFixed(2)) : '';

    const liveGroupsHtml = Array.isArray(qObj.groups) && qObj.groups.length > 0
      ? qObj.groups.map(function (g) {
          const rem5 = g.h5 && g.h5.remaining != null ? Math.round(Number(g.h5.remaining) * 100) : null;
          const remW = g.week && g.week.remaining != null ? Math.round(Number(g.week.remaining) * 100) : null;
          const rst5 = g.h5 && g.h5.reset ? fmtResetCountdown(g.h5.reset) : '';
          const rstW = g.week && g.week.reset ? fmtResetCountdown(g.week.reset) : '';
          return (
            '<div class="aiu-pool-row">' +
            '  <div class="aiu-q-line">' +
            '    <strong>' + escapeHtml(g.name || g.id) + ' 当前剩余池</strong>' +
            '    <span style="font-size:10px;color:var(--ink-muted);">' +
            (rem5 != null ? ('5h 剩 <span class="aiu-gold">' + rem5 + '%</span>' + (rst5 ? (' (' + rst5 + ')') : '')) : '') +
            (remW != null ? (' · 周剩 <span class="aiu-gold">' + remW + '%</span>' + (rstW ? (' (' + rstW + ')') : '')) : '') +
            '    </span>' +
            '  </div>' +
            (rem5 != null
              ? ('<div class="aiu-bar-track" title="5小时额度池剩余 ' + rem5 + '%"><div class="aiu-bar-fill warm" style="width:' + Math.max(0, Math.min(100, rem5)) + '%;"></div></div>')
              : '') +
            '</div>'
          );
        }).join('')
      : '';

    // Composition (Cache vs Fresh Input vs Output)
    const tot = Math.max(1, calc.tokTotal);
    const cacheTok = Math.max(0, Number(sumObj.cache) || 0);
    const outTok = Math.max(0, Number(sumObj.output) || 0);
    const inTok = Math.max(0, calc.tokTotal - cacheTok - outTok);
    const cachePct = Math.round((cacheTok / tot) * 100);
    const inPct = Math.round((inTok / tot) * 100);
    const outPct = Math.max(0, 100 - cachePct - inPct);

    // Models & Tools rankings
    const renderRankBox = function (titleTxt, mapObj) {
      const entries = Object.keys(mapObj || {}).map(function (k) { return [k, Number(mapObj[k]) || 0]; })
        .filter(function (x) { return x[1] > 0; })
        .sort(function (a, b) { return b[1] - a[1]; })
        .slice(0, 6);
      if (entries.length === 0) return '';
      const topV = Math.max(1, entries[0][1]);
      return (
        '<div class="aiu-box">' +
        '  <div class="aiu-sec-hdr"><span>' + escapeHtml(titleTxt) + '</span><span>TOKENS</span></div>' +
        entries.map(function (pair) {
          const pct = Math.max(2, Math.round((pair[1] / topV) * 100));
          return (
            '<div class="aiu-rank-row">' +
            '  <div class="aiu-rank-top"><span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + escapeHtml(pair[0]) + '</span><span class="aiu-gold">' + fmtCnTokens(pair[1]).full + '</span></div>' +
            '  <div class="aiu-bar-track"><div class="aiu-bar-fill" style="width:' + pct + '%;"></div></div>' +
            '</div>'
          );
        }).join('') +
        '</div>'
      );
    };

    const overviewBodyHtml =
      '<div class="aiu-hero">' +
      '  <div class="aiu-hero-val-row">' +
      '    <span class="aiu-hero-num">' + escapeHtml(heroNum) + '</span>' +
      '    <span class="aiu-hero-unit">' + escapeHtml(heroUnit) + '</span>' +
      '  </div>' +
      '  <div class="aiu-hero-sub">' +
      '    <select class="aiu-unit-sel" data-aiu-unit="1" aria-label="切换主指标显示单位">' +
      '      <option value="tokens"' + (aiUsageState.unitMode === 'tokens' ? ' selected' : '') + '>tokens</option>' +
      '      <option value="quota"' + (aiUsageState.unitMode === 'quota' ? ' selected' : '') + '>消耗额度 %</option>' +
      '      <option value="usd"' + (aiUsageState.unitMode === 'usd' ? ' selected' : '') + '>预估开销 $</option>' +
      '    </select>' +
      '    <span>' + escapeHtml(subSummary) + '</span>' +
      '  </div>' +
      '</div>' +
      '<div class="aiu-kpi-grid">' +
      '  <div class="aiu-kpi-cell"><span class="aiu-kpi-lbl">AI 步数</span><span class="aiu-kpi-val">' + steps.toLocaleString() + '<small>步</small></span></div>' +
      '  <div class="aiu-kpi-cell"><span class="aiu-kpi-lbl">时长</span><span class="aiu-kpi-val">' + hours + '<small>小时</small></span></div>' +
      '  <div class="aiu-kpi-cell"><span class="aiu-kpi-lbl">每步平均</span><span class="aiu-kpi-val">' + escapeHtml(avgPerStep.num) + '<small>' + escapeHtml(avgPerStep.unit) + '</small></span></div>' +
      '</div>' +
      '<div class="aiu-sec-hdr" style="padding-top:2px;">' +
      '  <span>ANTIGRAVITY 额度 · DEEPSEEK 开销</span>' +
      '  <span style="color:var(--ink-primary);">' + escapeHtml(acct.email || '--') + ' · ' + escapeHtml(tierShort) + ' · 当前剩余</span>' +
      '</div>' +
      '<div class="aiu-box">' +
      '  <div class="aiu-sec-hdr"><span>' + escapeHtml(getPeriodDisplayName(p)) + ' 用掉额度与开销</span><span>累计消耗</span></div>' +
      '  <div class="aiu-q-line"><span>Gemini</span><span>5小时 <span class="aiu-gold">' + Number(calc.gem.p5 || 0).toFixed(2) + '%</span> · 每周 <span class="aiu-gold">' + Number(calc.gem.pw || 0).toFixed(2) + '%</span></span></div>' +
      '  <div class="aiu-q-line"><span>Claude / GPT</span><span>5小时 <span class="aiu-gold">' + Number(calc.tp.p5 || 0).toFixed(2) + '%</span> · 每周 <span class="aiu-gold">' + Number(calc.tp.pw || 0).toFixed(2) + '%</span></span></div>' +
      '  <div class="aiu-q-line"><span>DeepSeek</span><span>开销 <span class="aiu-gold">¥' + dshCny.toFixed(2) + '</span> · <span class="aiu-gold">' + fmtCnTokens(calc.dsh.tokens || 0).full + '</span> tok (' + (calc.dsh.turns || 0) + ' 轮)' + escapeHtml(dshBal) + '</span></div>' +
      liveGroupsHtml +
      '</div>' +
      '<div class="aiu-box">' +
      '  <div class="aiu-sec-hdr">' +
      '    <span>构成 · COMPOSITION (缓存命中 ' + cachePct + '%)</span>' +
      '    <button type="button" class="mini-close-deck-btn" data-aiu-help="1">? 说明</button>' +
      '  </div>' +
      '  <div class="aiu-bar-track">' +
      '    <div class="aiu-bar-fill warm" style="width:' + cachePct + '%;" title="缓存读取 ' + cachePct + '%"></div>' +
      '    <div class="aiu-bar-fill" style="width:' + inPct + '%;" title="新输入 ' + inPct + '%"></div>' +
      '    <div class="aiu-bar-fill mid" style="width:' + outPct + '%;" title="模型输出 ' + outPct + '%"></div>' +
      '  </div>' +
      '  <div class="aiu-q-line" style="font-size:10px;color:var(--ink-muted);">' +
      '    <span>缓存读取 ' + fmtCnTokens(cacheTok).full + ' (' + cachePct + '%)</span>' +
      '    <span>新输入 ' + fmtCnTokens(inTok).full + '</span>' +
      '    <span>回复 ' + fmtCnTokens(outTok).full + '</span>' +
      '  </div>' +
      (aiUsageState.showCompHelp
        ? '<div style="font-size:10px;color:var(--ink-muted);border-top:1px dashed var(--line-faint);padding-top:4px;">缓存读取代表复用上下文前缀，计费与额度权重远低于新输入与模型回复输出。</div>'
        : '') +
      '</div>' +
      buildTrendSectionHtml(ov) +
      renderRankBox('模型排行 · MODELS', sumObj.models) +
      renderRankBox('软件来源 · CLIENTS', sumObj.tools);

    return (
      '<div class="aiu-root">' +
      '  <div class="aiu-topbar">' +
      '    <div class="aiu-brand-tabs">' +
      '      <span class="aiu-brand">AI USAGE</span>' +
      '      <button type="button" class="aiu-main-tab' + (aiUsageState.tab === 'overview' ? ' active' : '') + '" data-aiu-tab="overview">概览</button>' +
      '      <button type="button" class="aiu-main-tab' + (aiUsageState.tab === 'sessions' ? ' active' : '') + '" data-aiu-tab="sessions">对话</button>' +
      '    </div>' +
      '    <div style="display:inline-flex;align-items:center;gap:6px;">' +
      '      <span style="font-family:var(--font-mono);font-size:9.2px;color:var(--ink-muted);">更新 ' + escapeHtml(ov.updated || '') + '</span>' +
      '      <button type="button" class="mini-close-deck-btn" data-aiu-refresh="1" title="立即同步最新 AI Usage 用量">↻</button>' +
      '    </div>' +
      '  </div>' +
      '  <div class="aiu-periods">' +
      '    <div class="aiu-period-group">' +
      '      <button type="button" class="aiu-p-btn' + (p === 'today' ? ' active' : '') + '" data-aiu-period="today">今天</button>' +
      '      <button type="button" class="aiu-p-btn' + (p === 'yesterday' ? ' active' : '') + '" data-aiu-period="yesterday">昨天</button>' +
      '      <button type="button" class="aiu-p-btn' + (p === 'week' ? ' active' : '') + '" data-aiu-period="week">7 天</button>' +
      '      <button type="button" class="aiu-p-btn' + (p === 'month' ? ' active' : '') + '" data-aiu-period="month">本月</button>' +
      '      <button type="button" class="aiu-p-btn' + (p === 'all' ? ' active' : '') + '" data-aiu-period="all">全部</button>' +
      '    </div>' +
      '    <button type="button" class="aiu-cal-btn' + (isCustomDay || aiUsageState.calOpen ? ' active' : '') + '" data-aiu-caltoggle="1">' + (isCustomDay ? escapeHtml(p) : '选日期') + '</button>' +
      '  </div>' +
      buildCalendarPopupHtml(ov) +
      (aiUsageState.tab === 'sessions' ? buildSessionsTabHtml(aiUsageState.sessions) : overviewBodyHtml) +
      buildLiveCurrentSessionCardHtml(ov.current) +
      '</div>'
    );
  }

  function renderAllAiUsageMounts() {
    if (IS_WALLPAPER_VIEW) return;
    const html = monochromizeEmojis(buildAiUsageHtml());
    ['wb-ai-usage-mount', 'orn-ai-usage-mount'].forEach(function (id) {
      const el = document.getElementById(id);
      if (!el) return;
      const prevScroll = el.scrollTop;
      el.innerHTML = html;
      el.scrollTop = prevScroll;
    });
  }

  function wireAiUsageMountDelegation(mountEl) {
    if (!mountEl || mountEl.dataset.aiuBound === '1') return;
    mountEl.dataset.aiuBound = '1';

    mountEl.addEventListener('click', function (e) {
      const filePill = e.target.closest('.agy-file-pill');
      if (filePill) {
        e.stopPropagation();
        triggerLocalFileAction('open_file', filePill.getAttribute('data-open-path'), filePill.getAttribute('data-open-name'));
        return;
      }
      const tabBtn = e.target.closest('[data-aiu-tab]');
      if (tabBtn) {
        aiUsageState.tab = tabBtn.getAttribute('data-aiu-tab') || 'overview';
        renderAllAiUsageMounts();
        return;
      }
      const pBtn = e.target.closest('[data-aiu-period]');
      if (pBtn) {
        aiUsageState.period = pBtn.getAttribute('data-aiu-period') || 'all';
        aiUsageState.calOpen = false;
        renderAllAiUsageMounts();
        return;
      }
      const calToggle = e.target.closest('[data-aiu-caltoggle]');
      if (calToggle) {
        aiUsageState.calOpen = !aiUsageState.calOpen;
        renderAllAiUsageMounts();
        return;
      }
      const calNav = e.target.closest('[data-aiu-calnav]');
      if (calNav) {
        const delta = parseInt(calNav.getAttribute('data-aiu-calnav'), 10) || 0;
        const cur = (aiUsageState.calMonth || '2026-11').split('-');
        const dt = new Date(parseInt(cur[0], 10), (parseInt(cur[1], 10) - 1) + delta, 1);
        aiUsageState.calMonth = dt.getFullYear() + '-' + String(dt.getMonth() + 1).padStart(2, '0');
        renderAllAiUsageMounts();
        return;
      }
      const dayBtn = e.target.closest('[data-aiu-day]');
      if (dayBtn) {
        const dIso = dayBtn.getAttribute('data-aiu-day');
        if (dIso) {
          aiUsageState.period = dIso;
          aiUsageState.calOpen = false;
          renderAllAiUsageMounts();
        }
        return;
      }
      if (e.target.closest('[data-aiu-refresh]')) {
        requestAiUsageData(true);
        return;
      }
      if (e.target.closest('[data-aiu-help]')) {
        aiUsageState.showCompHelp = !aiUsageState.showCompHelp;
        renderAllAiUsageMounts();
        return;
      }
      if (e.target.closest('[data-aiu-toggle-live]')) {
        aiUsageState.liveNowExpanded = !aiUsageState.liveNowExpanded;
        renderAllAiUsageMounts();
        return;
      }
      const granBtn = e.target.closest('[data-aiu-tgran]');
      if (granBtn) {
        aiUsageState.trendGran = granBtn.getAttribute('data-aiu-tgran') || 'day';
        aiUsageState.trendOffset = 0;
        renderAllAiUsageMounts();
        return;
      }
      const tNav = e.target.closest('[data-aiu-tnav]');
      if (tNav) {
        const d = parseInt(tNav.getAttribute('data-aiu-tnav'), 10) || 0;
        aiUsageState.trendOffset = Math.min(0, aiUsageState.trendOffset + d);
        renderAllAiUsageMounts();
        return;
      }
      const sortBtn = e.target.closest('[data-aiu-sort]');
      if (sortBtn) {
        aiUsageState.sessSort = sortBtn.getAttribute('data-aiu-sort') || 'recent';
        renderAllAiUsageMounts();
        return;
      }
      const sessCard = e.target.closest('[data-aiu-sess]');
      if (sessCard && !e.target.closest('.aiu-turn-sub')) {
        const sid = sessCard.getAttribute('data-aiu-sess');
        if (sid) {
          if (aiUsageState.expandedSessIds.has(sid)) {
            aiUsageState.expandedSessIds.delete(sid);
            renderAllAiUsageMounts();
          } else {
            aiUsageState.expandedSessIds.add(sid);
            if (!aiUsageState.turnsBySessId[sid]) {
              requestAiUsageSessionTurns(sid);
            } else {
              renderAllAiUsageMounts();
            }
          }
        }
      }
    });

    mountEl.addEventListener('contextmenu', function (e) {
      const filePill = e.target.closest('.agy-file-pill');
      if (filePill) {
        e.preventDefault();
        e.stopPropagation();
        triggerLocalFileAction('open_location', filePill.getAttribute('data-open-path'), filePill.getAttribute('data-open-name'));
      }
    });

    mountEl.addEventListener('change', function (e) {
      const unitSel = e.target.closest('[data-aiu-unit]');
      if (unitSel) {
        aiUsageState.unitMode = unitSel.value || 'tokens';
        renderAllAiUsageMounts();
      }
    });
  }

  // ==========================================================================
  // Embedded Settings Renderer & Live Bidirectional Binding
  // ==========================================================================
  function sliderItemHtml(id, label, dispVal, min, max, step, curVal) {
    return [
      '<div class="wb-slider-row">',
      '  <div class="wb-slider-meta"><span>' + escapeHtml(label) + '</span><strong data-wb-sval="' + id + '">' + escapeHtml(dispVal) + '</strong></div>',
      '  <input type="range" class="astrolabe-slider" data-wb-slider="' + id + '" min="' + min + '" max="' + max + '" step="' + step + '" value="' + curVal + '" />',
      '</div>'
    ].join('');
  }

  function renderEmbeddedSettingsBody() {
    if (IS_WALLPAPER_VIEW) return;
    const bodyEl = document.getElementById('agy-wb-settings-body');
    if (!bodyEl || !window.ophanimAgent || typeof window.ophanimAgent.getFullControlState !== 'function') return;
    const st = window.ophanimAgent.getFullControlState();

    document.querySelectorAll('.agy-wb-set-tab').forEach(function (t) {
      t.classList.toggle('active', t.getAttribute('data-wb-stab') === workbenchSettingsTab);
    });

    if (workbenchSettingsTab === 'quick') {
      const comp = st.completion || { runningCount: 0, unreadCount: 0, previewOverride: false };
      const pMode = st.pyramidMode || 'occasional';
      bodyEl.innerHTML = [
        '<div class="wb-set-card">',
        '  <div class="wb-set-card-hdr"><span>Ⅰ · 圣殿快捷动作与视图</span><span>QUICK ACTIONS</span></div>',
        '  <div class="wb-set-grid-3">',
        '    <button type="button" class="wb-opt-btn' + (st.topologyOverlay ? ' active' : '') + '" data-wb-act="topology">⌖ 测绘准星连线</button>',
        '    <button type="button" class="wb-opt-btn" data-wb-act="pulse">' + ICON_BOLT + ' 触发并发脉冲</button>',
        '    <button type="button" class="wb-opt-btn' + (st.audioEnabled ? ' active' : '') + '" data-wb-act="audio">♪ 圣咏低频共鸣</button>',
        '    <button type="button" class="wb-opt-btn" data-wb-act="resetCam">⟲ 镜头视域归位</button>',
        '    <button type="button" class="wb-opt-btn" data-wb-act="saveConfig">✦ 保存当前配置</button>',
        '    <button type="button" class="wb-opt-btn" data-wb-act="openCoreHub">◎ 打开中央圣球面板</button>',
        '  </div>',
        '</div>',
        '<div class="wb-set-card">',
        '  <div class="wb-set-card-hdr"><span>Ⅱ · 任务完结白球提醒 · 阶梯金字塔</span><span class="param-cat-hdr-right"><span id="wb-comp-state-txt">' +
          (comp.previewOverride ? '金字塔预览开启中' : (comp.unreadCount > 0 ? (comp.unreadCount + ' 项待查收') : '正常轨道')) + '</span><button type="button" class="cat-reset-btn" data-wb-act="resetCat" data-wb-arg="cat_pyr">↺ 重置</button></span></div>',
        '  <div style="font-family:var(--font-mono);font-size:9.6px;color:var(--ink-muted);line-height:1.58;">',
        '    • 仅当任务完整输出完一段最终回答正文后，中央圣球才会亮起白光；选「每次金字塔」时任一任务完成即化作七层同心阶梯金字塔并托举白球（选「偶发金字塔」时约每1~2次完工惊喜变形）。<br/>',
        '    • 点击发光白球自动切换定位到已完成任务；若同时有多个任务完成，顶部会展开多个已完成栏目供逐一查看。',
        '  </div>',
        '  <div class="wb-set-grid-3">',
        '    <button type="button" class="wb-opt-btn' + (pMode === 'occasional' ? ' active' : '') + '" data-wb-act="pyramidMode" data-wb-arg="occasional">偶发金字塔 (默认)</button>',
        '    <button type="button" class="wb-opt-btn' + (pMode === 'always' ? ' active' : '') + '" data-wb-act="pyramidMode" data-wb-arg="always">每次金字塔</button>',
        '    <button type="button" class="wb-opt-btn' + (pMode === 'off' ? ' active' : '') + '" data-wb-act="pyramidMode" data-wb-arg="off">仅亮白球</button>',
        '  </div>',
        '  <div class="wb-set-grid-2">',
        '    <button type="button" class="wb-opt-btn' + (comp.previewOverride ? ' active' : '') + '" data-wb-comp="preview">✦ 金字塔完结预览</button>',
        '    <button type="button" class="wb-opt-btn' + (comp.unreadCount > 0 || completedTaskColumns.length > 0 ? ' active' : '') + '" data-wb-comp="ack">✓ 标记全部已查收归位</button>',
        '  </div>',
        '</div>',
        '<div class="wb-set-card">',
        '  <div class="wb-set-card-hdr"><span>Ⅲ · 司仪台与合并会话列表折叠页开关</span><span>PANELS</span></div>',
        '  <div class="wb-set-grid-2">',
        '    <button type="button" class="wb-opt-btn' + (st.hudVisible ? ' active' : '') + '" data-wb-act="toggleHud">浮窗司仪台: ' + (st.hudVisible ? '已开启' : '已收起') + '</button>',
        '    <button type="button" class="wb-opt-btn' + (panelVisible ? ' active' : '') + '" data-wb-act="toggleAgyRight">司仪台右侧会话页: ' + (panelVisible ? '已展开' : '已收起') + '</button>',
        '    <button type="button" class="wb-opt-btn' + (st.ornamentalVisible ? ' active' : '') + '" data-wb-act="toggleOrnamental">观赏仪盘 (含 AI Usage): ' + (st.ornamentalVisible ? '已开启' : '已收起') + '</button>',
        '    <button type="button" class="wb-opt-btn' + (st.ornamentalHorizontal ? ' active' : '') + '" data-wb-act="toggleOrnamentalOrient">观赏仪盘排版: ' + (st.ornamentalHorizontal ? '左→右横排' : '上→下竖排') + '</button>',
        '  </div>',
        '</div>',
        '<div class="wb-set-card">',
        '  <div class="wb-set-card-hdr"><span>Ⅳ · 全局恢复出厂默认</span><span>FACTORY RESET</span></div>',
        '  <button type="button" class="wb-opt-btn" data-wb-act="resetAll">↺ 一键重置所有圣轮参数与镜头视角</button>',
        '</div>'
      ].join('');
      return;
    }

    if (workbenchSettingsTab === 'codex') {
      const sl = st.slabLayers || {};
      const layerBtns = [];
      for (let r = 1; r <= 6; r++) {
        layerBtns.push(
          '<button type="button" class="wb-opt-btn' + (sl[r] ? ' active' : '') + '" data-wb-act="slabLayer" data-wb-arg="' + r + '">第' + (r + 1) + '层</button>'
        );
      }
      const scripSize = typeof st.scriptureSizeMult === 'number' ? st.scriptureSizeMult : 1.0;
      const scripBright = typeof st.scriptureBrightMult === 'number' ? st.scriptureBrightMult : 1.0;
      bodyEl.innerHTML = [
        '<div class="wb-set-card">',
        '  <div class="wb-set-card-hdr"><span>光束模式 · 运转仪轨 · 结构主题</span><span class="param-cat-hdr-right"><span>SCHEMA &amp; MODUS</span><button type="button" class="cat-reset-btn" data-wb-act="resetCat" data-wb-arg="cat0">↺ 重置</button></span></div>',
        '  <div class="wb-set-grid-3">',
        '    <button type="button" class="wb-opt-btn' + (st.beamMode === 'tool_io' ? ' active' : '') + '" data-wb-act="beamMode" data-wb-arg="tool_io">调用收发</button>',
        '    <button type="button" class="wb-opt-btn' + (st.beamMode === 'model_active' ? ' active' : '') + '" data-wb-act="beamMode" data-wb-arg="model_active">工作随动</button>',
        '    <button type="button" class="wb-opt-btn' + (st.beamMode === 'ambient' ? ' active' : '') + '" data-wb-act="beamMode" data-wb-arg="ambient">常驻流光</button>',
        '  </div>',
        '  <div class="wb-set-grid-2">',
        '    <button type="button" class="wb-opt-btn' + (st.mode === 'contemplatio' ? ' active' : '') + '" data-wb-act="mode" data-wb-arg="contemplatio">Ⅰ · 静谧圣巡</button>',
        '    <button type="button" class="wb-opt-btn' + (st.mode === 'theophania' ? ' active' : '') + '" data-wb-act="mode" data-wb-arg="theophania">Ⅱ · 神谕显现</button>',
        '    <button type="button" class="wb-opt-btn' + (st.mode === 'seraphicus' ? ' active' : '') + '" data-wb-act="mode" data-wb-arg="seraphicus">Ⅲ · 天穹圣焰</button>',
        '    <button type="button" class="wb-opt-btn' + (st.mode === 'astrolabium' ? ' active' : '') + '" data-wb-act="mode" data-wb-arg="astrolabium">Ⅳ · 星盘正交</button>',
        '  </div>',
        '  <div class="wb-set-grid-2">',
        '    <button type="button" class="wb-opt-btn' + (st.schema === 'obsidian' ? ' active' : '') + '" data-wb-act="schema" data-wb-arg="obsidian">黑曜铬银主题</button>',
        '    <button type="button" class="wb-opt-btn' + (st.schema === 'alabaster' ? ' active' : '') + '" data-wb-act="schema" data-wb-arg="alabaster">炽白瓷钢主题</button>',
        '  </div>',
        '</div>',
        '<div class="wb-set-card">',
        '  <div class="wb-set-card-hdr"><span>Ⅰ · 顶冠圣言与界面</span><span class="param-cat-hdr-right"><span>EZECHIEL &amp; TABULA</span><button type="button" class="cat-reset-btn" data-wb-act="resetCat" data-wb-arg="cat1">↺ 重置</button></span></div>',
        sliderItemHtml('slider-scripture-size', '以西结经文字号', Math.round(scripSize * 100) + '%', 40, 220, 5, Math.round(scripSize * 100)),
        sliderItemHtml('slider-scripture-bright', '以西结经文亮度', scripBright <= 0.02 ? 'OFF' : (Math.round(scripBright * 100) + '%'), 0, 200, 5, Math.round(scripBright * 100)),
        sliderItemHtml('slider-panel-opacity', '面板背景不透明度', Math.round(st.panelOpacity * 100) + '%', 8, 100, 2, Math.round(st.panelOpacity * 100)),
        '</div>',
        '<div class="wb-set-card">',
        '  <div class="wb-set-card-hdr"><span>Ⅱ · 圣轮结构与光流 (任一环按住中键皆可拖拽)</span><span class="param-cat-hdr-right"><span>ROTAE &amp; FLUXUS</span><button type="button" class="cat-reset-btn" data-wb-act="resetCat" data-wb-arg="cat2">↺ 重置</button></span></div>',
        sliderItemHtml('slider-spacing', '七环间距', Math.round(st.spacingMult * 100) + '%', 45, 1000, 5, Math.round(st.spacingMult * 100)),
        sliderItemHtml('slider-ring-size', '圣轮整体大小', Math.round(st.ringSizeMult * 100) + '%', 35, 320, 5, Math.round(st.ringSizeMult * 100)),
        sliderItemHtml('slider-ring-thickness', '圣轮环体粗细', Math.round(st.ringThicknessMult * 100) + '%', 25, 350, 5, Math.round(st.ringThicknessMult * 100)),
        sliderItemHtml('slider-tilt', '流形倾角', Math.round(st.tiltMult * 100) + '%', 0, 150, 5, Math.round(st.tiltMult * 100)),
        sliderItemHtml('slider-speed', '圣轮角速', st.speedMult.toFixed(2) + '×', 0, 2.5, 0.05, st.speedMult),
        sliderItemHtml('slider-flux', '装饰圣光流速', st.fluxDecorMult <= 0.02 ? 'OFF' : (st.fluxDecorMult.toFixed(2) + '×'), 0, 3.0, 0.05, st.fluxDecorMult),
        sliderItemHtml('slider-beam-thickness', '光束粗细大小', Math.round(st.beamThicknessMult * 100) + '%', 15, 300, 5, Math.round(st.beamThicknessMult * 100)),
        '</div>',
        '<div class="wb-set-card">',
        '  <div class="wb-set-card-hdr"><span>Ⅲ · 代码薄板与圣瞳</span><span class="param-cat-hdr-right"><span>LAMINAE &amp; OCULI</span><button type="button" class="cat-reset-btn" data-wb-act="resetCat" data-wb-arg="cat3">↺ 重置</button></span></div>',
        '  <div class="wb-set-grid-6">' + layerBtns.join('') + '</div>',
        sliderItemHtml('slider-slab-size', '薄板卡片大小', Math.round(st.slabSizeMult * 100) + '%', 50, 320, 5, Math.round(st.slabSizeMult * 100)),
        sliderItemHtml('slider-eye-open', '圣瞳张合度', Math.round(st.eyeOpenMult * 100) + '%', 12, 130, 2, Math.round(st.eyeOpenMult * 100)),
        sliderItemHtml('slider-eye-density', '圣瞳密集度', Math.round(st.eyeDensityMult * 100) + '%', 0, 250, 5, Math.round(st.eyeDensityMult * 100)),
        '</div>',
        '<div class="wb-set-card">',
        '  <div class="wb-set-card-hdr"><span>Ⅳ · 蜂群子模型星群</span><span class="param-cat-hdr-right"><span>SIDERA SWARM</span><button type="button" class="cat-reset-btn" data-wb-act="resetCat" data-wb-arg="cat4">↺ 重置</button></span></div>',
        sliderItemHtml('slider-swarm', '蜂群子模型数量', String(st.swarmCount), 0, 12, 1, st.swarmCount),
        sliderItemHtml('slider-star-size', '子模型四芒星大小', Math.round(st.starSizeMult * 100) + '%', 35, 280, 5, Math.round(st.starSizeMult * 100)),
        sliderItemHtml('slider-star-spacing', '子模型轨道间距', Math.round(st.starSpacingMult * 100) + '%', 45, 420, 5, Math.round(st.starSpacingMult * 100)),
        '</div>',
        '<div class="wb-set-card">',
        '  <div class="wb-set-card-hdr"><span>Ⅴ · 深空星穹与镜头</span><span class="param-cat-hdr-right"><span>CAELUM &amp; CAMERA</span><button type="button" class="cat-reset-btn" data-wb-act="resetCat" data-wb-arg="cat5">↺ 重置</button></span></div>',
        sliderItemHtml('slider-sky-count', '星空数量', Math.round(st.skyCountMult * 100) + '%', 0, 200, 5, Math.round(st.skyCountMult * 100)),
        sliderItemHtml('slider-sky-bright', '星空亮度', Math.round(st.skyBrightMult * 100) + '%', 0, 260, 5, Math.round(st.skyBrightMult * 100)),
        sliderItemHtml('slider-meteor-rate', '流星频率', Math.round(st.meteorRateMult * 100) + '%', 0, 400, 10, Math.round(st.meteorRateMult * 100)),
        sliderItemHtml('slider-fov', '镜头广角 FOV', Math.round(st.fov) + '°', 45, 95, 1, Math.round(st.fov)),
        sliderItemHtml('slider-glow', '结构线条对比', Math.round(st.glowMult * 100) + '%', 30, 130, 5, Math.round(st.glowMult * 100)),
        '  <div class="wb-set-grid-2" style="margin-top:4px;">',
        '    <button type="button" class="wb-opt-btn active" data-wb-act="saveConfig">✦ 保存所有参数配置</button>',
        '    <button type="button" class="wb-opt-btn" data-wb-act="resetAll">↺ 重置所有参数</button>',
        '  </div>',
        '</div>'
      ].join('');
      return;
    }

    if (workbenchSettingsTab === 'telemetry') {
      const q = st.quota || {};
      const slabCnt = (lastSnapshot && lastSnapshot.slabs) ? lastSnapshot.slabs.length : 0;
      const delivCnt = (lastSnapshot && lastSnapshot.deliverables) ? lastSnapshot.deliverables.length : 0;
      const eyeCap = Math.max(0, Math.min(20, Math.round(8 * (typeof st.eyeDensityMult === 'number' ? st.eyeDensityMult : 1))));
      const mountedEyeCnt = Math.min(delivCnt, eyeCap);
      const wkCnt = (lastSnapshot && lastSnapshot.workers) ? lastSnapshot.workers.length : st.swarmCount;
      bodyEl.innerHTML = [
        '<div class="wb-set-card">',
        '  <div class="wb-set-card-hdr"><span>TOKEN VELOCITY // 60FPS 丝滑连续滚动 Token 消耗速率图</span><span id="wb-tel-rate">' + (q.burnRateTokPerSec || 0) + ' tok/s (峰值 ' + (q.peakTokPerSec || 0) + ')</span></div>',
        '  <canvas id="agy-wb-quota-canvas"></canvas>',
        '  <div class="wb-set-grid-3" style="font-family:var(--font-mono);font-size:10px;">',
        '    <div style="border:1px solid var(--line-faint);padding:6px 8px;">已用额度: <strong id="wb-tel-used">' + Number(q.usedPct || 0).toFixed(1) + '%</strong></div>',
        '    <div style="border:1px solid var(--line-faint);padding:6px 8px;">会话/余量: <strong id="wb-tel-rem">' + escapeHtml(q.remText || '--') + '</strong></div>',
        '    <div style="border:1px solid var(--line-faint);padding:6px 8px;">通道状态: <strong id="wb-tel-tier">' + escapeHtml(q.tierText || 'LIVE·AGY') + '</strong></div>',
        '  </div>',
        '</div>',
        '<div class="wb-set-card" id="wb-ai-usage-mount">' + buildAiUsageHtml() + '</div>',
        '<div class="wb-set-card">',
        '  <div class="wb-set-card-hdr"><span>当前会话三维圣轮装载概览</span><span>3D MANIFOLD</span></div>',
        '  <div class="wb-set-grid-3" style="font-family:var(--font-mono);font-size:10.5px;">',
        '    <div style="border:1px solid var(--line-faint);padding:8px;">代码薄板: <strong>' + slabCnt + ' 枚</strong></div>',
        '    <div style="border:1px solid var(--line-faint);padding:8px;">外环交付圣瞳: <strong>' + mountedEyeCnt + ' 眼' + (delivCnt > mountedEyeCnt ? (' (历史 ' + delivCnt + ' 份)') : '') + '</strong></div>',
        '    <div style="border:1px solid var(--line-faint);padding:8px;">蜂群子模型: <strong>' + wkCnt + ' 星</strong></div>',
        '  </div>',
        '</div>'
      ].join('');
      wireAiUsageMountDelegation(document.getElementById('wb-ai-usage-mount'));
      requestAiUsageData(false);
      requestAnimationFrame(drawEmbeddedTelemetryChart);
      return;
    }

    if (workbenchSettingsTab === 'wallpaper') {
      const wp = st.wallpaper || { active: false, actionInFlight: false, wallpaperMode: 'agy_live', autoFollowWorking: true };
      const wpBusy = Boolean(wp.actionInFlight);
      const autoFollowOn = wp.autoFollowWorking !== false;
      const trackLine = (wp.active && wp.wallpaperTitle)
        ? ('<div id="wb-wp-track" style="font-family:var(--font-mono);font-size:9.6px;color:var(--ink-primary);padding:4px 7px;border:1px solid var(--line-dim);background:var(--line-faint);">壁纸当前圣轮：[' +
            (wp.wallpaperStatus === 'running' ? '● 工作中' : '✓ 已完成') + '] ' + escapeHtml(wp.wallpaperTitle) + '</div>')
        : '<div id="wb-wp-track" style="display:none;font-family:var(--font-mono);font-size:9.6px;color:var(--ink-primary);padding:4px 7px;border:1px solid var(--line-dim);background:var(--line-faint);"></div>';
      bodyEl.innerHTML = [
        '<div class="wb-set-card">',
        '  <div class="wb-set-card-hdr"><span>可交互动态桌面壁纸 · INTERACTIVE WINDOWS WALLPAPER</span><span id="wb-wp-status">' +
          (wp.active ? (wp.wallpaperMode === 'ambient_eco' ? '● 运行中 (常驻流光节能)' : '● 运行中 (Antigravity 实时随动)') : '○ 未启用') + '</span></div>',
        '  <div style="font-family:var(--font-mono);font-size:9.8px;color:var(--ink-muted);line-height:1.62;">',
        '    • 嵌入 Windows 桌面图标底层（保留顶部 OPHANIM 标题与以西结书圣言，桌面快捷方式完全正常点击）。<br/>',
        '    • <strong>自动跳至工作中对话</strong>：默认开启，只要任意会话处于「工作中」，即使主面板停留在已完成会话，壁纸圣轮也会自动跳转至正在工作的会话实时运转。<br/>',
        '    • <strong>壁纸原生三维交互</strong>：左键在桌面空白处拖动可旋转星系；任务完工亮起白球/金字塔时<strong>直接左键点白球即可一键查阅归位</strong>；按住鼠标<strong>中键</strong>在任意一个环上可单独三维转动该环；壁纸下<strong>按住中键+滑动滚轮</strong>可自由伸缩镜头距离（普通窗口内直接滑滚轮即可缩放）；鼠标移上代码薄板会随鼠微倾；全部圣瞳实时跟鼠且屏蔽弹窗。',
        '  </div>',
        trackLine,
        '  <div class="wb-set-grid-2">',
        '    <button type="button" class="wb-opt-btn' + (wp.wallpaperMode !== 'ambient_eco' ? ' active' : '') + '" data-wb-wpmode="agy_live">模式 1 · Antigravity 实时刷新随动<br/><span style="font-size:8.6px;opacity:0.75;">跟随所选：调用收发 / 工作随动 / 常驻流光</span></button>',
        '    <button type="button" class="wb-opt-btn' + (wp.wallpaperMode === 'ambient_eco' ? ' active' : '') + '" data-wb-wpmode="ambient_eco">模式 2 · 常驻流光 (低耗节能)<br/><span style="font-size:8.6px;opacity:0.75;">独立常驻圣光穿梭 + 交互时自动满帧</span></button>',
        '  </div>',
        '  <div style="margin-top:4px;">',
        '    <button type="button" id="wb-wp-follow-btn" class="wb-opt-btn' + (autoFollowOn ? ' active' : '') + '" style="width:100%;" data-wb-wpfollow="toggle">' +
          (autoFollowOn ? '● 壁纸自动跳至工作中对话 (默认开启)' : '○ 壁纸锁定当前选中对话 (点击恢复自动跳转)') + '</button>',
        '  </div>',
        '  <div class="wb-set-grid-2" style="margin-top:4px;">',
        '    <button type="button" class="wb-opt-btn active" data-wb-wpact="enable"' + (wpBusy ? ' disabled' : '') + '>' + (wpBusy ? '⏳ 处理中...' : '✦ 设为可交互桌面壁纸') + '</button>',
        '    <button type="button" class="wb-opt-btn" data-wb-wpact="disable"' + (wpBusy ? ' disabled' : '') + '>' + (wpBusy ? '⏳ 处理中...' : '✕ 取消壁纸 (恢复原电脑壁纸)') + '</button>',
        '  </div>',
        '</div>'
      ].join('');
    }
  }

  function syncEmbeddedSettingsLiveValues() {
    if (IS_WALLPAPER_VIEW) return;
    if (!window.ophanimAgent || typeof window.ophanimAgent.getFullControlState !== 'function') return;
    const st = window.ophanimAgent.getFullControlState();
    const scripSize = typeof st.scriptureSizeMult === 'number' ? st.scriptureSizeMult : 1.0;
    const scripBright = typeof st.scriptureBrightMult === 'number' ? st.scriptureBrightMult : 1.0;
    const mapText = {
      'slider-scripture-size': Math.round(scripSize * 100) + '%',
      'slider-scripture-bright': scripBright <= 0.02 ? 'OFF' : (Math.round(scripBright * 100) + '%'),
      'slider-panel-opacity': Math.round(st.panelOpacity * 100) + '%',
      'slider-spacing': Math.round(st.spacingMult * 100) + '%',
      'slider-ring-size': Math.round(st.ringSizeMult * 100) + '%',
      'slider-ring-thickness': Math.round(st.ringThicknessMult * 100) + '%',
      'slider-tilt': Math.round(st.tiltMult * 100) + '%',
      'slider-speed': st.speedMult.toFixed(2) + '×',
      'slider-flux': st.fluxDecorMult <= 0.02 ? 'OFF' : (st.fluxDecorMult.toFixed(2) + '×'),
      'slider-beam-thickness': Math.round(st.beamThicknessMult * 100) + '%',
      'slider-slab-size': Math.round(st.slabSizeMult * 100) + '%',
      'slider-eye-open': Math.round(st.eyeOpenMult * 100) + '%',
      'slider-eye-density': Math.round(st.eyeDensityMult * 100) + '%',
      'slider-swarm': String(st.swarmCount),
      'slider-star-size': Math.round(st.starSizeMult * 100) + '%',
      'slider-star-spacing': Math.round(st.starSpacingMult * 100) + '%',
      'slider-sky-count': Math.round(st.skyCountMult * 100) + '%',
      'slider-sky-bright': Math.round(st.skyBrightMult * 100) + '%',
      'slider-meteor-rate': Math.round(st.meteorRateMult * 100) + '%',
      'slider-fov': Math.round(st.fov) + '°',
      'slider-glow': Math.round(st.glowMult * 100) + '%'
    };
    Object.keys(mapText).forEach(function (k) {
      const el = document.querySelector('[data-wb-sval="' + k + '"]');
      if (el) el.textContent = mapText[k];
    });
    const q = st.quota || {};
    const rEl = document.getElementById('wb-tel-rate');
    if (rEl) rEl.textContent = (q.burnRateTokPerSec || 0) + ' tok/s (峰值 ' + (q.peakTokPerSec || 0) + ')';
    const uEl = document.getElementById('wb-tel-used');
    if (uEl) uEl.textContent = Number(q.usedPct || 0).toFixed(1) + '%';
    const remEl = document.getElementById('wb-tel-rem');
    if (remEl) remEl.textContent = q.remText || '--';
    const wpEl = document.getElementById('wb-wp-status');
    if (wpEl && st.wallpaper) {
      wpEl.textContent = st.wallpaper.active
        ? (st.wallpaper.wallpaperMode === 'ambient_eco' ? '● 运行中 (常驻流光节能)' : '● 运行中 (Antigravity 实时随动)')
        : '○ 未启用';
    }
    const wpTrackEl = document.getElementById('wb-wp-track');
    if (wpTrackEl && st.wallpaper) {
      if (st.wallpaper.active && st.wallpaper.wallpaperTitle) {
        wpTrackEl.style.display = 'block';
        wpTrackEl.textContent = '壁纸当前圣轮：[' +
          (st.wallpaper.wallpaperStatus === 'running' ? '● 工作中' : '✓ 已完成') + '] ' + st.wallpaper.wallpaperTitle;
      } else {
        wpTrackEl.style.display = 'none';
      }
    }
    const wpFollowBtn = document.getElementById('wb-wp-follow-btn');
    if (wpFollowBtn && st.wallpaper) {
      const af = st.wallpaper.autoFollowWorking !== false;
      wpFollowBtn.classList.toggle('active', af);
      wpFollowBtn.textContent = af
        ? '● 壁纸自动跳至工作中对话 (默认开启)'
        : '○ 壁纸锁定当前选中对话 (点击恢复自动跳转)';
    }
    if (st.wallpaper) {
      const wpBusy = Boolean(st.wallpaper.actionInFlight);
      document.querySelectorAll('[data-wb-wpact]').forEach(function (b) {
        b.disabled = wpBusy;
        const act = b.getAttribute('data-wb-wpact');
        if (act === 'enable') {
          b.textContent = wpBusy ? '⏳ 处理中...' : '✦ 设为可交互桌面壁纸';
        } else if (act === 'disable') {
          b.textContent = wpBusy ? '⏳ 处理中...' : '✕ 取消壁纸 (恢复原电脑壁纸)';
        }
      });
    }
  }

  function drawEmbeddedTelemetryChart() {
    const cv = document.getElementById('agy-wb-quota-canvas');
    if (!cv || !window.ophanimAgent) return;
    if (typeof window.ophanimAgent.drawSmoothVelocityCanvas === 'function') {
      window.ophanimAgent.drawSmoothVelocityCanvas(cv);
    }
  }

  // ==========================================================================
  // Floating Right-Half Panel Drag & Resize
  // ==========================================================================
  function wireDragAndResize(panelEl, handleEl) {
    let dragging = false;
    let offsetX = 0, offsetY = 0;

    function startDrag(clientX, clientY, target) {
      if (target && (target.tagName === 'BUTTON' || target.closest('button'))) return;
      const rect = panelEl.getBoundingClientRect();
      panelEl.style.left = rect.left + 'px';
      panelEl.style.top = rect.top + 'px';
      panelEl.style.right = 'auto';
      panelEl.style.bottom = 'auto';
      offsetX = clientX - rect.left;
      offsetY = clientY - rect.top;
      dragging = true;
      panelEl.classList.add('dragging');
    }

    function moveDrag(clientX, clientY) {
      if (!dragging) return;
      const maxLeft = Math.max(8, window.innerWidth - panelEl.offsetWidth - 8);
      const maxTop = Math.max(8, window.innerHeight - 52);
      panelEl.style.left = Math.max(8, Math.min(maxLeft, clientX - offsetX)) + 'px';
      panelEl.style.top = Math.max(8, Math.min(maxTop, clientY - offsetY)) + 'px';
    }

    function stopDrag() {
      if (!dragging) return;
      dragging = false;
      panelEl.classList.remove('dragging');
    }

    handleEl.addEventListener('mousedown', function (e) {
      if (e.button !== 0) return;
      if (e.target && (e.target.tagName === 'BUTTON' || e.target.closest('button'))) return;
      e.preventDefault();
      e.stopPropagation();
      startDrag(e.clientX, e.clientY, e.target);
    });
    window.addEventListener('mousemove', function (e) {
      if (dragging) moveDrag(e.clientX, e.clientY);
    });
    window.addEventListener('mouseup', stopDrag);

    let resizing = false, rsDir = '', sx = 0, sy = 0, sl = 0, st = 0, sw = 0, sh = 0;
    const minW = 268, minH = 220;

    panelEl.querySelectorAll('.rs-handle').forEach(function (rh) {
      rh.addEventListener('mousedown', function (e) {
        if (e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();
        const rect = panelEl.getBoundingClientRect();
        panelEl.style.left = rect.left + 'px';
        panelEl.style.top = rect.top + 'px';
        panelEl.style.right = 'auto';
        panelEl.style.bottom = 'auto';
        panelEl.style.width = rect.width + 'px';
        panelEl.style.height = rect.height + 'px';
        resizing = true;
        rsDir = rh.getAttribute('data-rs') || 'se';
        sx = e.clientX; sy = e.clientY;
        sl = rect.left; st = rect.top; sw = rect.width; sh = rect.height;
        panelEl.classList.add('dragging');
      });
    });

    window.addEventListener('mousemove', function (e) {
      if (!resizing) return;
      const dx = e.clientX - sx, dy = e.clientY - sy;
      let nl = sl, nt = st, nw = sw, nh = sh;
      if (rsDir.indexOf('e') !== -1) nw = Math.max(minW, Math.min(window.innerWidth - sl - 8, sw + dx));
      if (rsDir.indexOf('s') !== -1) nh = Math.max(minH, Math.min(window.innerHeight - st - 8, sh + dy));
      if (rsDir.indexOf('w') !== -1) {
        const clampedDx = Math.max(-sl + 8, Math.min(sw - minW, dx));
        nw = sw - clampedDx;
        nl = sl + clampedDx;
      }
      if (rsDir.indexOf('n') !== -1) {
        const clampedDy = Math.max(-st + 8, Math.min(sh - minH, dy));
        nh = sh - clampedDy;
        nt = st + clampedDy;
      }
      panelEl.style.left = nl + 'px';
      panelEl.style.top = nt + 'px';
      panelEl.style.width = nw + 'px';
      panelEl.style.height = nh + 'px';
    });

    window.addEventListener('mouseup', function () {
      if (!resizing) return;
      resizing = false;
      panelEl.classList.remove('dragging');
    });
  }

  function syncCodexAndWingButtonsUI() {
    const wingBtn = document.getElementById('btn-codex-session-wing');
    const foldCodexBtn = document.getElementById('btn-fold-codex-body');
    const wingToggleCodexBtn = document.getElementById('btn-wing-toggle-codex');
    const agyHideBtn = document.getElementById('btn-agy-hide');
    if (wingBtn) {
      wingBtn.classList.toggle('active', panelVisible);
      wingBtn.textContent = panelVisible ? '◂ 收起列表' : '会话列表 ▸';
    }
    if (foldCodexBtn) {
      foldCodexBtn.textContent = panelVisible ? '收起司仪 ▸' : '只留列表 ▸';
      foldCodexBtn.title = panelVisible
        ? '将左侧司仪台向右收进会话列表，只保留右侧会话列表'
        : '收起左侧司仪台参数，单独打开并保留右侧会话列表';
    }
    if (wingToggleCodexBtn) {
      wingToggleCodexBtn.classList.toggle('active', codexBodyCollapsed);
      wingToggleCodexBtn.textContent = codexBodyCollapsed ? '◂ 展开司仪台' : '收起司仪 ▸';
      wingToggleCodexBtn.title = codexBodyCollapsed
        ? '向左平滑展开圣轮司仪台参数面板'
        : '将左侧司仪台向右收起，只保留当前会话列表';
    }
    if (agyHideBtn) {
      agyHideBtn.textContent = codexBodyCollapsed ? '隐藏' : '◂ 收起';
      agyHideBtn.title = codexBodyCollapsed
        ? '隐藏当前独立会话列表（可点顶部「展开司仪台」随时呼出）'
        : '向左侧司仪台内折叠收起会话列表（只留司仪台）';
    }
  }

  let codexFoldAnimTimer = null;
  function setCodexBodyCollapsed(collapseFlag, skipShift) {
    const nextCollapsed = Boolean(collapseFlag);
    const codexEl = document.getElementById('codex-panel');
    if (!codexEl) {
      codexBodyCollapsed = nextCollapsed;
      if (nextCollapsed) panelVisible = true;
      syncCodexAndWingButtonsUI();
      return;
    }

    if (nextCollapsed === codexBodyCollapsed) {
      if (nextCollapsed && !panelVisible) setPanelVisible(true);
      syncCodexAndWingButtonsUI();
      return;
    }

    const rect = codexEl.getBoundingClientRect();
    const curLeft = Math.max(8, Math.round(rect.left || parseFloat(codexEl.style.left) || 22));
    const wasWingAlreadyOpen = panelVisible;

    if (codexFoldAnimTimer) {
      clearTimeout(codexFoldAnimTimer);
      codexFoldAnimTimer = null;
    }
    codexEl.classList.add('wing-fold-animating');

    if (nextCollapsed) {
      if (rect.width >= 260) {
        savedCodexWidthPx = Math.round(rect.width);
      }
      // Ensure HUD & right Session List are visible when collapsing 司仪台 to leave only Session List!
      panelVisible = true;
      codexEl.classList.add('session-wing-open');
      if (codexEl.classList.contains('hidden-hud') && window.ophanimAgent && typeof window.ophanimAgent.triggerControlAction === 'function') {
        window.ophanimAgent.triggerControlAction('toggleHud');
      }
      if (!skipShift && wasWingAlreadyOpen) {
        // Shift left anchor rightward by +savedCodexWidthPx so the right-hand Session List stays anchored on screen!
        const targetLeft = Math.min(Math.max(12, (window.innerWidth || 1440) - 324), curLeft + Math.max(0, savedCodexWidthPx - 1));
        codexEl.style.right = 'auto';
        codexEl.style.left = targetLeft + 'px';
      }
      codexBodyCollapsed = true;
      codexEl.classList.add('codex-body-collapsed');
    } else {
      codexBodyCollapsed = false;
      const restoreW = Math.max(320, savedCodexWidthPx || 382);
      codexEl.classList.remove('codex-body-collapsed');
      codexEl.style.width = restoreW + 'px';
      if (!skipShift) {
        // Grow 司仪台 smoothly back out to the left while clamping >= 14px so it never clips off-screen
        const targetLeft = Math.max(14, curLeft - (restoreW - 1));
        codexEl.style.right = 'auto';
        codexEl.style.left = targetLeft + 'px';
      }
    }

    syncCodexAndWingButtonsUI();
    codexFoldAnimTimer = setTimeout(function () {
      codexEl.classList.remove('wing-fold-animating');
      codexFoldAnimTimer = null;
    }, 410);

    if (window.ophanimAgent && typeof window.ophanimAgent.syncPanelVisibility === 'function') {
      window.ophanimAgent.syncPanelVisibility();
    }
  }

  function setPanelVisible(vis) {
    const nextVis = Boolean(vis);
    if (!nextVis && codexBodyCollapsed) {
      // If user asks to close Session List while 司仪台 was collapsed, unfold 司仪台 first so user isn't left with an invisible 0px box
      setCodexBodyCollapsed(false);
    }
    panelVisible = nextVis;
    const codexEl = document.getElementById('codex-panel');
    if (codexEl) {
      codexEl.classList.toggle('session-wing-open', panelVisible);
      if (panelVisible && codexEl.classList.contains('hidden-hud') && window.ophanimAgent && typeof window.ophanimAgent.triggerControlAction === 'function') {
        window.ophanimAgent.triggerControlAction('toggleHud');
      }
    }
    syncCodexAndWingButtonsUI();
    if (window.ophanimAgent && typeof window.ophanimAgent.syncPanelVisibility === 'function') {
      window.ophanimAgent.syncPanelVisibility();
    }
  }

  function wireWingHeaderDrag(codexEl, wingHdrEl) {
    if (!codexEl || !wingHdrEl) return;
    let dragging = false;
    let offsetX = 0, offsetY = 0;

    wingHdrEl.addEventListener('mousedown', function (e) {
      if (e.button !== 0) return;
      if (e.target && (e.target.tagName === 'BUTTON' || e.target.closest('button'))) return;
      e.preventDefault();
      e.stopPropagation();
      const rect = codexEl.getBoundingClientRect();
      codexEl.style.left = rect.left + 'px';
      codexEl.style.top = rect.top + 'px';
      codexEl.style.right = 'auto';
      codexEl.style.bottom = 'auto';
      offsetX = e.clientX - rect.left;
      offsetY = e.clientY - rect.top;
      dragging = true;
      codexEl.classList.add('dragging');
    });

    window.addEventListener('mousemove', function (e) {
      if (!dragging) return;
      const totalSpanW = codexBodyCollapsed ? 312 : ((codexEl.offsetWidth || 382) + (panelVisible ? 311 : 0));
      const maxLeft = Math.max(8, (window.innerWidth || 1440) - totalSpanW - 8);
      const maxTop = Math.max(8, (window.innerHeight || 900) - 56);
      codexEl.style.left = Math.max(8, Math.min(maxLeft, e.clientX - offsetX)) + 'px';
      codexEl.style.top = Math.max(8, Math.min(maxTop, e.clientY - offsetY)) + 'px';
    });

    window.addEventListener('mouseup', function () {
      if (!dragging) return;
      dragging = false;
      codexEl.classList.remove('dragging');
    });
  }

  function syncBeamModeUI(mode) {
    if (IS_WALLPAPER_VIEW) return;
    document.querySelectorAll('.agy-beam-pill').forEach(function (b) {
      b.classList.toggle('active', b.getAttribute('data-agy-beam') === mode);
    });
  }

  function openCoreHubModalUI() {
    if (window.ophanimAgent && typeof window.ophanimAgent.openCoreHubModal === 'function') {
      window.ophanimAgent.openCoreHubModal();
    }
  }

  function closeCoreHubModalUI() {
    if (window.ophanimAgent && typeof window.ophanimAgent.closeCoreHubModal === 'function') {
      window.ophanimAgent.closeCoreHubModal();
    }
  }

  function sendWSOrFetch(wsPayload, httpFallbackUrl, httpMethod, httpBody) {
    if (activeWS && activeWS.readyState === 1) {
      activeWS.send(JSON.stringify(wsPayload));
      return Promise.resolve({ via: 'ws' });
    }
    return fetch(HTTP_API_BASE + httpFallbackUrl, {
      method: httpMethod || 'GET',
      headers: httpBody ? { 'Content-Type': 'application/json' } : undefined,
      body: httpBody ? JSON.stringify(httpBody) : undefined
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data) handleServerPayload(data);
        return data;
      })
      .catch(function () { return null; });
  }

  // ==========================================================================
  // Queue & Stop Actions (`主动送进去插队` / `撤回排队` / `■ 停止`)
  // ==========================================================================
  function triggerQueueAction(actionKind, targetCid, stepIndex) {
    const cid = targetCid || currentCid;
    if (!cid || cid === '__new__') return;
    const modelSel = document.getElementById('agy-model-select');
    const modelKey = modelSel ? modelSel.value : 'inherit';
    sendWSOrFetch(
      { type: 'agy_queue_action', action: actionKind, cascadeId: cid, stepIndex: Number(stepIndex) || 0, model: modelKey },
      '/api/conversation/queue-action',
      'POST',
      { action: actionKind, cascadeId: cid, stepIndex: Number(stepIndex) || 0, model: modelKey }
    );
  }

  function stopActiveExecution(targetCid) {
    const cid = targetCid || currentCid;
    if (!cid || cid === '__new__') return;
    ['agy-stop-btn', 'agy-wb-stop-btn'].forEach(function (id) {
      const btn = document.getElementById(id);
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = ICON_STOP + ' 停止中...';
      }
    });
    triggerQueueAction('cancel', cid, 0);
    setTimeout(function () {
      ['agy-stop-btn', 'agy-wb-stop-btn'].forEach(function (id) {
        const btn = document.getElementById(id);
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = ICON_STOP + ' 停止';
        }
      });
    }, 650);
  }

  // ==========================================================================
  // Session Selection, New Session & Right-Click Context Actions
  // ==========================================================================
  function selectConversation(cid, switchWbToChat) {
    if (!cid) return;
    if (switchWbToChat && workbenchOpen) {
      switchWorkbenchRightPane('chat', true);
    }
    if (cid === currentCid && !isDraftNew) {
      if (!switchWbToChat) {
        openCoreHubModalUI();
      }
      scheduleSnapStreamsToBottom(['agy-chat-stream', 'agy-wb-chat-stream']);
      return;
    }
    isDraftNew = false;
    currentCid = cid;
    streamStickBottom['agy-chat-stream'] = true;
    streamStickBottom['agy-wb-chat-stream'] = true;
    try { window.localStorage.setItem(STORAGE_LAST_CID_KEY, cid); } catch (err) { /* ignore */ }
    renderSessionList();

    const miniEl = document.getElementById('agy-binding-mini');
    if (miniEl) {
      miniEl.innerHTML = '<span class="core-dot"></span>正在重构切换至 #' + escapeHtml(cid.slice(0, 8)) + '...';
    }
    sendWSOrFetch(
      { type: 'agy_select_conversation', cascadeId: cid, animate: true },
      '/api/conversation/' + encodeURIComponent(cid) + '?animate=1',
      'GET'
    );
  }

  function startDraftNewConversation(modeTarget) {
    isDraftNew = true;
    currentCid = '__new__';
    currentStatus = 'idle';
    lastSnapshot = {
      cascadeId: '__new__',
      shortId: 'NEW',
      title: '新建对话 · 待发首条指令',
      status: 'idle',
      messages: [],
      turns: [],
      workers: [],
      slabs: [],
      outerFiles: [],
      deliverables: []
    };
    renderSessionList();
    renderConversationStream(lastSnapshot, true);
    if (window.ophanimAgent && typeof window.ophanimAgent.transitionToConversationState === 'function') {
      window.ophanimAgent.transitionToConversationState(lastSnapshot, { animate: modeTarget !== 'core_modal' });
    }
    if (modeTarget === 'workbench') {
      if (!workbenchOpen) setWorkbenchOpen(true, true);
      switchWorkbenchRightPane('chat', true);
      setTimeout(function () {
        const inp = document.getElementById('agy-wb-chat-input');
        if (inp) inp.focus();
      }, 120);
    } else if (modeTarget === 'core_modal') {
      openCoreHubModalUI();
      setTimeout(function () {
        const inp = document.getElementById('agy-chat-input');
        if (inp) inp.focus();
      }, 260);
    } else {
      const inp = document.getElementById('agy-chat-input');
      if (inp) inp.focus();
    }
  }

  function openSessionContextMenu(cid, clientX, clientY) {
    if (!cid || cid === '__new__') return;
    const conv = conversations.find(function (c) { return c.id === cid; });
    if (!conv) return;
    ctxMenuCid = cid;
    const menu = document.getElementById('agy-session-ctx-menu');
    const pinLbl = document.getElementById('ctx-lbl-pin');
    const archLbl = document.getElementById('ctx-lbl-arch');
    const readBtn = document.getElementById('ctx-btn-read');
    if (!menu) return;

    // Clean monochrome text — zero ugly emojis!
    if (pinLbl) pinLbl.textContent = conv.pinned ? '取消置顶' : '置顶会话';
    if (archLbl) archLbl.textContent = conv.archived ? '移出归档' : '归档会话';
    if (readBtn) readBtn.style.display = convHasUnreadCompletion(cid) ? 'flex' : 'none';

    menu.classList.add('open');
    const mw = 172, mh = 148;
    const lx = Math.max(8, Math.min(window.innerWidth - mw - 8, clientX));
    const ly = Math.max(8, Math.min(window.innerHeight - mh - 8, clientY));
    menu.style.left = lx + 'px';
    menu.style.top = ly + 'px';
  }

  function closeSessionContextMenu() {
    const menu = document.getElementById('agy-session-ctx-menu');
    if (menu) menu.classList.remove('open');
    ctxMenuCid = '';
  }

  function performSessionMetaAction(cid, action) {
    if (!cid || cid === '__new__') return;
    if (action === 'mark_read') {
      markSingleConversationRead(cid);
      return;
    }
    if (action === 'delete') {
      markSingleConversationRead(cid);
    }
    sendWSOrFetch(
      { type: 'agy_session_meta_action', cascadeId: cid, action: action },
      '/api/conversation/meta',
      'POST',
      { cascadeId: cid, action: action }
    );
  }

  // ==========================================================================
  // Attachments & Verbatim Message Dispatch (Supports Queue & Jump-Queue!)
  // ==========================================================================
  function renderAttachmentTrays() {
    ['agy-attachment-tray', 'agy-wb-attachment-tray'].forEach(function (trayId) {
      const tray = document.getElementById(trayId);
      if (!tray) return;
      if (pendingAttachments.length === 0) {
        tray.classList.remove('has-items');
        tray.innerHTML = '';
        return;
      }
      tray.classList.add('has-items');
      tray.innerHTML = pendingAttachments.map(function (att, idx) {
        const thumbHtml = att.isImage && att.previewUrl
          ? '<img class="agy-att-thumb" src="' + escapeHtml(att.previewUrl) + '" alt="" />'
          : '<span class="agy-att-kind-tag">FILE</span>';
        return (
          '<div class="agy-att-item" title="' + escapeHtml(att.name + ' (' + formatBytes(att.size) + ')') + '">' +
          thumbHtml +
          '<span class="agy-att-name">' + escapeHtml(att.name) + '</span>' +
          '<span style="color:var(--ink-muted);font-size:8.5px;">' + escapeHtml(formatBytes(att.size)) + '</span>' +
          '<button type="button" class="agy-att-rm" data-rm-att="' + idx + '" title="移除此附件">✕</button>' +
          '</div>'
        );
      }).join('');
    });
  }

  function ingestDroppedOrSelectedFiles(fileList) {
    if (!fileList || fileList.length === 0) return;
    Array.from(fileList).forEach(function (file) {
      if (!file || file.size > 42 * 1024 * 1024) return;
      const reader = new FileReader();
      reader.onload = function () {
        const dataUrl = String(reader.result || '');
        const commaIdx = dataUrl.indexOf(',');
        const b64 = commaIdx >= 0 ? dataUrl.slice(commaIdx + 1) : '';
        const mime = file.type || (/\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(file.name || '') ? 'image/png' : 'application/octet-stream');
        const isImg = /^image\//i.test(mime);
        pendingAttachments.push({
          name: file.name || (isImg ? ('image_' + Date.now() + '.png') : ('file_' + Date.now())),
          mimeType: mime,
          size: file.size || 0,
          isImage: isImg,
          dataBase64: b64,
          previewUrl: isImg ? dataUrl : '',
          localPath: typeof file.path === 'string' ? file.path : ''
        });
        renderAttachmentTrays();
      };
      reader.readAsDataURL(file);
    });
  }

  function buildTurnsFromSnapshot(snap) {
    if (Array.isArray(snap.turns) && snap.turns.length > 0) {
      return snap.turns;
    }
    const msgs = Array.isArray(snap.messages) ? snap.messages : [];
    const fallback = [];
    let cur = null;
    for (let i = 0; i < msgs.length; i++) {
      const m = msgs[i];
      if (m.role === 'user') {
        if (cur) fallback.push(cur);
        const rawT = String(m.text || '').trim();
        const firstLine = rawT.split(/\r?\n/)[0] || '[图片/文件请求]';
        cur = {
          turnNumber: fallback.length + 1,
          title: firstLine.length > 64 ? (firstLine.slice(0, 64) + '…') : firstLine,
          userText: m.text || '',
          attachments: m.attachments || [],
          assistantText: '',
          hasFinalReply: false,
          userStepIndex: typeof m.stepIndex === 'number' ? m.stepIndex : -1,
          time: m.time || '',
          status: m.stepStatus === 'PENDING' ? 'queued' : 'pending'
        };
      } else if (m.text) {
        if (!cur) {
          cur = {
            turnNumber: fallback.length + 1,
            title: '系统初始会话响应',
            userText: '',
            attachments: [],
            assistantText: '',
            hasFinalReply: false,
            userStepIndex: -1,
            time: m.time || '',
            status: 'done'
          };
        }
        cur.assistantText = cur.assistantText ? (cur.assistantText + '\n\n' + m.text) : m.text;
        cur.hasFinalReply = true;
        cur.status = 'done';
        if (m.time) cur.time = m.time;
      }
    }
    if (cur) fallback.push(cur);
    if (fallback.length > 0 && snap.status === 'running') {
      const last = fallback[fallback.length - 1];
      if (!last.hasFinalReply && last.status !== 'queued') last.status = 'running';
    }
    return fallback;
  }

  function dispatchVerbatimMessageFromSource(sourceKind, explicitModeOverride) {
    const isWb = sourceKind === 'workbench';
    const inp = document.getElementById(isWb ? 'agy-wb-chat-input' : 'agy-chat-input');
    const sendBtnA = document.getElementById('agy-send-btn');
    const sendBtnB = document.getElementById('agy-wb-send-btn');
    const intBtnA = document.getElementById('agy-interrupt-now-btn');
    const intBtnB = document.getElementById('agy-wb-interrupt-now-btn');
    const modelSel = document.getElementById(isWb ? 'agy-wb-model-select' : 'agy-model-select');
    if (!inp || isSending) return;

    const exactRawText = inp.value || ''; // 100% VERBATIM
    const hasText = exactRawText.trim().length > 0;
    const hasAtts = pendingAttachments.length > 0;
    if (!hasText && !hasAtts) return;

    const chosenSendMode = explicitModeOverride || composerSendMode || 'queue';
    const modelKey = modelSel ? modelSel.value : 'inherit';
    const targetCid = isDraftNew || !currentCid ? '__new__' : currentCid;
    const outgoingAttachments = pendingAttachments.map(function (a) {
      return {
        name: a.name,
        mimeType: a.mimeType,
        size: a.size,
        isImage: a.isImage,
        dataBase64: a.dataBase64,
        localPath: a.localPath || ''
      };
    });
    const optimisticAttChips = pendingAttachments.map(function (a) {
      return {
        name: a.name,
        kind: a.isImage ? 'image' : 'file',
        path: a.localPath || ''
      };
    });

    isSending = true;
    [sendBtnA, sendBtnB, intBtnA, intBtnB].forEach(function (b) { if (b) b.disabled = true; });
    inp.value = '';
    pendingAttachments = [];
    renderAttachmentTrays();

    const wasAlreadyRunning = (currentStatus === 'running');
    currentStatus = 'running';
    if (targetCid !== '__new__') {
      for (let i = 0; i < conversations.length; i++) {
        if (conversations[i].id === targetCid) conversations[i].status = 'running';
      }
    }
    pushCompletionTo3DEngine();

    const fallbackTitle = hasText
      ? exactRawText.trim().split(/\r?\n/)[0].slice(0, 62)
      : ('[附件] ' + optimisticAttChips.map(function (x) { return x.name; }).join(', ').slice(0, 52));
    if (!lastSnapshot) {
      lastSnapshot = { cascadeId: targetCid, title: fallbackTitle, status: 'running', messages: [], turns: [], workers: [], slabs: [], outerFiles: [], deliverables: [] };
    }
    lastSnapshot.status = 'running';
    const prevTurns = buildTurnsFromSnapshot(lastSnapshot).slice();
    const nextTurnNum = prevTurns.length + 1;
    const optimisticStatus = (wasAlreadyRunning && chosenSendMode !== 'interrupt') ? 'queued' : 'running';
    prevTurns.push({
      turnNumber: nextTurnNum,
      title: fallbackTitle,
      userText: exactRawText,
      attachments: optimisticAttChips,
      assistantText: '',
      hasFinalReply: false,
      userStepIndex: -1,
      time: new Date().toISOString(),
      status: optimisticStatus
    });
    lastSnapshot.turns = prevTurns;
    renderConversationStream(lastSnapshot, true);
    renderSessionList();

    sendWSOrFetch(
      {
        type: 'agy_send_message',
        cascadeId: targetCid,
        text: exactRawText,
        model: modelKey,
        sendMode: chosenSendMode,
        attachments: outgoingAttachments,
        optimisticTurnNumber: nextTurnNum
      },
      '/api/conversation/send',
      'POST',
      {
        cascadeId: targetCid,
        text: exactRawText,
        model: modelKey,
        sendMode: chosenSendMode,
        attachments: outgoingAttachments
      }
    ).finally(function () {
      setTimeout(function () {
        isSending = false;
        [sendBtnA, sendBtnB, intBtnA, intBtnB].forEach(function (b) { if (b) b.disabled = false; });
      }, 260);
    });
  }

  // ==========================================================================
  // Event Wiring
  // ==========================================================================
  function wireDropTarget(boxEl, isWb) {
    if (!boxEl) return;
    boxEl.addEventListener('dragenter', function (e) {
      if (!e.dataTransfer || !Array.from(e.dataTransfer.types || []).includes('Files')) return;
      e.preventDefault();
      e.stopPropagation();
      if (isWb) wbDragDepth++; else coreDragDepth++;
      boxEl.classList.add('drag-over');
    });
    boxEl.addEventListener('dragover', function (e) {
      if (!e.dataTransfer || !Array.from(e.dataTransfer.types || []).includes('Files')) return;
      e.preventDefault();
      e.stopPropagation();
      e.dataTransfer.dropEffect = 'copy';
      boxEl.classList.add('drag-over');
    });
    boxEl.addEventListener('dragleave', function (e) {
      e.preventDefault();
      e.stopPropagation();
      if (isWb) {
        wbDragDepth = Math.max(0, wbDragDepth - 1);
        if (wbDragDepth === 0) boxEl.classList.remove('drag-over');
      } else {
        coreDragDepth = Math.max(0, coreDragDepth - 1);
        if (coreDragDepth === 0) boxEl.classList.remove('drag-over');
      }
    });
    boxEl.addEventListener('drop', function (e) {
      e.preventDefault();
      e.stopPropagation();
      if (isWb) wbDragDepth = 0; else coreDragDepth = 0;
      boxEl.classList.remove('drag-over');
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        ingestDroppedOrSelectedFiles(e.dataTransfer.files);
        const inpEl = document.getElementById(isWb ? 'agy-wb-chat-input' : 'agy-chat-input');
        if (inpEl) inpEl.focus();
      }
    });
  }

  function handleStreamClickDelegation(e) {
    // 1. Copy button on fenced code blocks
    const copyBtn = e.target.closest('[data-copy-code]');
    if (copyBtn) {
      e.stopPropagation();
      const wrap = copyBtn.closest('.agy-code-wrap');
      const codeEl = wrap ? wrap.querySelector('code') : null;
      if (codeEl && navigator.clipboard) {
        navigator.clipboard.writeText(codeEl.textContent || '').then(function () {
          copyBtn.textContent = '已复制';
          setTimeout(function () { copyBtn.textContent = '复制'; }, 1200);
        }).catch(function () {});
      }
      return;
    }

    // 2. Queue & Stop action buttons (`立即插队送入` / `✕ 撤回排队` / `■ 停止`)
    const qBtn = e.target.closest('[data-queue-act]');
    if (qBtn) {
      e.stopPropagation();
      const act = qBtn.getAttribute('data-queue-act');
      const cid = qBtn.getAttribute('data-queue-cid') || currentCid;
      if (act === 'cancel' || act === 'stop') {
        stopActiveExecution(cid);
        return;
      }
      const stepIdx = parseInt(qBtn.getAttribute('data-step-idx') || '-1', 10);
      triggerQueueAction(act, cid, stepIdx);
      return;
    }

    // 3. User Attachment Chip -> Left-Click opens the file directly!
    const attChip = e.target.closest('.agy-turn-att-chip');
    if (attChip) {
      e.stopPropagation();
      const fPath = attChip.getAttribute('data-file-path') || '';
      const fName = attChip.getAttribute('data-file-name') || '';
      triggerLocalFileAction('open_file', fPath, fName);
      return;
    }

    // 4. Markdown File Pill -> Left-Click opens the file directly!
    const pill = e.target.closest('.agy-file-pill');
    if (pill) {
      e.stopPropagation();
      const filePath = pill.getAttribute('data-open-path') || '';
      const fileName = pill.getAttribute('data-open-name') || '';
      triggerLocalFileAction('open_file', filePath, fileName);
      return;
    }

    // 5. Turn accordion toggle
    const turnHdr = e.target.closest('.agy-turn-hdr');
    if (turnHdr) {
      const card = turnHdr.closest('.agy-turn-card');
      const turnKey = card ? card.getAttribute('data-turn-key') : '';
      if (card && turnKey) {
        const nowOpen = !card.classList.contains('expanded');
        if (nowOpen) addBoundedSetKey(expandedTurnKeys, turnKey, MAX_EXPANDED_TURN_KEYS);
        else expandedTurnKeys.delete(turnKey);
        if (lastSnapshot) renderConversationStream(lastSnapshot, false);
      }
    }
  }

  function handleStreamContextMenuDelegation(e) {
    // Right-click on User Attachment Chip OR Markdown File Pill -> Open File Location in Explorer!
    const attChip = e.target.closest('.agy-turn-att-chip');
    if (attChip) {
      e.preventDefault();
      e.stopPropagation();
      triggerLocalFileAction('open_location', attChip.getAttribute('data-file-path') || '', attChip.getAttribute('data-file-name') || '');
      return;
    }
    const pill = e.target.closest('.agy-file-pill');
    if (pill) {
      e.preventDefault();
      e.stopPropagation();
      triggerLocalFileAction('open_location', pill.getAttribute('data-open-path') || '', pill.getAttribute('data-open-name') || '');
    }
  }

  function handleCompletedBarClick(e) {
    const rmBtn = e.target.closest('[data-rm-done-col]');
    if (rmBtn) {
      e.stopPropagation();
      dismissSingleCompletedColumn(rmBtn.getAttribute('data-rm-done-col'));
      return;
    }
    if (e.target.closest('[data-ack-all-done]')) {
      e.stopPropagation();
      if (window.ophanimAgent && typeof window.ophanimAgent.acknowledgeCompletions === 'function') {
        window.ophanimAgent.acknowledgeCompletions(false);
      } else {
        clearUnreadCompletions();
      }
      return;
    }
    const colCard = e.target.closest('[data-done-col-key]');
    if (colCard) {
      const key = colCard.getAttribute('data-done-col-key');
      const isWb = colCard.getAttribute('data-done-wb') === '1';
      const item = completedTaskColumns.find(function (x) { return x.key === key; });
      if (item) focusCompletedTaskColumn(item, isWb);
    }
  }

  function wireAllEvents(wbEl, panelEl, coreBackdrop, ctxMenu, dockTrigger) {
    // 1. Top-Left `AGENT 控制台` opens ONLY the left conversation list sidebar at first glance; clicking again closes it
    dockTrigger.addEventListener('click', function () {
      if (!workbenchOpen) {
        setWorkbenchOpen(true, false);
      } else {
        setWorkbenchOpen(false);
      }
    });

    // Sidebar header controls: toggle right-hand pane (`对话栏 ▸` / `◂ 收起对话`) & close sidebar (`⇤ 关闭`)
    const btnWbToggleMain = document.getElementById('btn-wb-toggle-main');
    if (btnWbToggleMain) {
      btnWbToggleMain.addEventListener('click', function () {
        setWorkbenchMainExpanded(!workbenchMainExpanded);
      });
    }
    const btnWbCloseSidebar = document.getElementById('btn-wb-close-sidebar');
    if (btnWbCloseSidebar) {
      btnWbCloseSidebar.addEventListener('click', function () {
        setWorkbenchOpen(false);
      });
    }

    // 2. Clicking `⇤ 收起对话` / `⇤ 收起设置` on the right pane ONLY collapses the right pane — keeps left conversation list open!
    document.getElementById('btn-wb-collapse-drawer').addEventListener('click', function () {
      setWorkbenchMainExpanded(false);
    });
    document.getElementById('btn-wb-collapse-from-set').addEventListener('click', function () {
      setWorkbenchMainExpanded(false);
    });

    // Bottom footer buttons (`◈ 对话` / `⚙ 设置`) expand right pane or collapse it if already active on that view
    document.getElementById('btn-wb-view-chat').addEventListener('click', function () {
      if (!workbenchMainExpanded) {
        switchWorkbenchRightPane('chat', true);
      } else if (workbenchRightPane === 'chat') {
        setWorkbenchMainExpanded(false);
      } else {
        switchWorkbenchRightPane('chat', true);
      }
    });
    document.getElementById('btn-wb-view-settings').addEventListener('click', function () {
      if (!workbenchMainExpanded) {
        switchWorkbenchRightPane('settings', true);
      } else if (workbenchRightPane === 'settings') {
        setWorkbenchMainExpanded(false);
      } else {
        switchWorkbenchRightPane('settings', true);
      }
    });
    document.getElementById('btn-wb-settings-to-chat').addEventListener('click', function () {
      switchWorkbenchRightPane('chat', true);
    });

    wbEl.querySelectorAll('.agy-wb-set-tab').forEach(function (tabBtn) {
      tabBtn.addEventListener('click', function () {
        workbenchSettingsTab = tabBtn.getAttribute('data-wb-stab') || 'quick';
        renderEmbeddedSettingsBody();
      });
    });

    const setBody = document.getElementById('agy-wb-settings-body');
    setBody.addEventListener('click', function (e) {
      if (e.target.closest('#wb-ai-usage-mount')) return;
      const actBtn = e.target.closest('[data-wb-act]');
      if (actBtn && window.ophanimAgent && typeof window.ophanimAgent.triggerControlAction === 'function') {
        const act = actBtn.getAttribute('data-wb-act');
        const arg = actBtn.getAttribute('data-wb-arg');
        window.ophanimAgent.triggerControlAction(act, arg);
        renderEmbeddedSettingsBody();
        return;
      }
      const compBtn = e.target.closest('[data-wb-comp]');
      if (compBtn && window.ophanimAgent) {
        const cAct = compBtn.getAttribute('data-wb-comp');
        if (cAct === 'preview' && typeof window.ophanimAgent.toggleCompletionPreview === 'function') {
          window.ophanimAgent.toggleCompletionPreview();
        } else if (cAct === 'ack' && typeof window.ophanimAgent.acknowledgeCompletions === 'function') {
          window.ophanimAgent.acknowledgeCompletions(false);
        }
        renderEmbeddedSettingsBody();
        return;
      }
      const wpModeBtn = e.target.closest('[data-wb-wpmode]');
      if (wpModeBtn && window.ophanimAgent && typeof window.ophanimAgent.setWallpaperModeSelection === 'function') {
        window.ophanimAgent.setWallpaperModeSelection(wpModeBtn.getAttribute('data-wb-wpmode'));
        renderEmbeddedSettingsBody();
        return;
      }
      const wpFollowBtn = e.target.closest('[data-wb-wpfollow]');
      if (wpFollowBtn && window.ophanimAgent && typeof window.ophanimAgent.setWallpaperAutoFollow === 'function') {
        const curWp = typeof window.ophanimAgent.getWallpaperState === 'function'
          ? (window.ophanimAgent.getWallpaperState() || {})
          : {};
        window.ophanimAgent.setWallpaperAutoFollow(curWp.autoFollowWorking === false);
        setTimeout(renderEmbeddedSettingsBody, 120);
        return;
      }
      const wpActBtn = e.target.closest('[data-wb-wpact]');
      if (wpActBtn && window.ophanimAgent && typeof window.ophanimAgent.requestWallpaperAction === 'function') {
        const curWp = typeof window.ophanimAgent.getWallpaperState === 'function'
          ? (window.ophanimAgent.getWallpaperState() || {})
          : {};
        if (wpActBtn.disabled || curWp.actionInFlight) return;
        const wAct = wpActBtn.getAttribute('data-wb-wpact');
        document.querySelectorAll('[data-wb-wpact]').forEach(function (b) { b.disabled = true; });
        window.ophanimAgent.requestWallpaperAction(wAct);
        syncEmbeddedSettingsLiveValues();
      }
    });

    setBody.addEventListener('input', function (e) {
      const slEl = e.target.closest('[data-wb-slider]');
      if (!slEl || !window.ophanimAgent || typeof window.ophanimAgent.setSliderById !== 'function') return;
      const sid = slEl.getAttribute('data-wb-slider');
      window.ophanimAgent.setSliderById(sid, slEl.value);
      syncEmbeddedSettingsLiveValues();
    });

    function refreshConvs() {
      sendWSOrFetch(
        { type: 'agy_refresh_conversations', cascadeId: isDraftNew ? '' : currentCid },
        '/api/conversations',
        'GET'
      );
    }
    document.getElementById('btn-wb-refresh-list').addEventListener('click', refreshConvs);
    document.getElementById('btn-agy-refresh').addEventListener('click', refreshConvs);

    document.getElementById('btn-wb-new-session').addEventListener('click', function () {
      startDraftNewConversation('workbench');
    });
    document.getElementById('btn-agy-new-conv').addEventListener('click', function () {
      startDraftNewConversation('core_modal');
    });
    document.getElementById('btn-agy-core-new').addEventListener('click', function () {
      startDraftNewConversation('inline');
    });

    document.getElementById('btn-wb-ack-unread').addEventListener('click', function () {
      if (window.ophanimAgent && typeof window.ophanimAgent.acknowledgeCompletions === 'function') {
        window.ophanimAgent.acknowledgeCompletions(false);
      } else {
        clearUnreadCompletions();
      }
    });

    document.getElementById('agy-core-completed-bar').addEventListener('click', handleCompletedBarClick);
    document.getElementById('agy-wb-completed-bar').addEventListener('click', handleCompletedBarClick);

    // Mutual collapse & drag wiring on #codex-agy-wing (`收起司仪 ▸` / `◂ 展开司仪台` + `◂ 收起` / `隐藏`)
    const codexPanelRef = document.getElementById('codex-panel');
    const wingDragHdr = document.getElementById('codex-wing-drag-handle');
    if (codexPanelRef && wingDragHdr) {
      wireWingHeaderDrag(codexPanelRef, wingDragHdr);
    }
    const btnWingToggleCodex = document.getElementById('btn-wing-toggle-codex');
    if (btnWingToggleCodex) {
      btnWingToggleCodex.addEventListener('click', function (e) {
        e.stopPropagation();
        setCodexBodyCollapsed(!codexBodyCollapsed);
      });
    }
    document.getElementById('btn-agy-hide').addEventListener('click', function (e) {
      e.stopPropagation();
      if (codexBodyCollapsed) {
        if (window.ophanimAgent && typeof window.ophanimAgent.triggerControlAction === 'function') {
          window.ophanimAgent.triggerControlAction('toggleHud');
        }
      } else {
        setPanelVisible(false);
      }
    });
    syncCodexAndWingButtonsUI();
    panelEl.querySelectorAll('.agy-beam-pill').forEach(function (pill) {
      pill.addEventListener('click', function () {
        const m = pill.getAttribute('data-agy-beam');
        if (window.ophanimAgent && typeof window.ophanimAgent.setBeamMode === 'function') {
          window.ophanimAgent.setBeamMode(m, false);
        }
        syncBeamModeUI(m);
      });
    });
    document.getElementById('btn-agy-open-core').addEventListener('click', openCoreHubModalUI);

    function toggleAllTurns() {
      if (!lastSnapshot) return;
      const turns = buildTurnsFromSnapshot(lastSnapshot);
      const cidKey = lastSnapshot.cascadeId || currentCid || 'new';
      const anyCollapsed = turns.some(function (t) { return !expandedTurnKeys.has(cidKey + ':' + t.turnNumber); });
      turns.forEach(function (t) {
        const k = cidKey + ':' + t.turnNumber;
        if (anyCollapsed) expandedTurnKeys.add(k);
        else expandedTurnKeys.delete(k);
      });
      const lbl = anyCollapsed ? '全部折叠' : '展开全部';
      const b1 = document.getElementById('btn-agy-toggle-all-turns');
      const b2 = document.getElementById('btn-wb-toggle-turns');
      if (b1) b1.textContent = lbl;
      if (b2) b2.textContent = lbl;
      renderConversationStream(lastSnapshot, false);
    }
    document.getElementById('btn-agy-toggle-all-turns').addEventListener('click', toggleAllTurns);
    document.getElementById('btn-wb-toggle-turns').addEventListener('click', toggleAllTurns);

    document.getElementById('btn-close-agy-core-modal').addEventListener('click', closeCoreHubModalUI);
    coreBackdrop.addEventListener('click', function (e) {
      if (e.target === coreBackdrop) closeCoreHubModalUI();
    });

    // Send Mode Switch (`排队发送` vs `插队送入`)
    document.querySelectorAll('[data-smode]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        composerSendMode = btn.getAttribute('data-smode') === 'interrupt' ? 'interrupt' : 'queue';
        syncSendModeSwitchUI();
      });
    });

    const modelSelA = document.getElementById('agy-model-select');
    const modelSelB = document.getElementById('agy-wb-model-select');
    if (modelSelA && modelSelB) {
      modelSelA.addEventListener('change', function () { modelSelB.value = modelSelA.value; });
      modelSelB.addEventListener('change', function () { modelSelA.value = modelSelB.value; });
    }

    document.getElementById('agy-send-btn').addEventListener('click', function () {
      dispatchVerbatimMessageFromSource('core');
    });
    document.getElementById('agy-wb-send-btn').addEventListener('click', function () {
      dispatchVerbatimMessageFromSource('workbench');
    });
    document.getElementById('agy-interrupt-now-btn').addEventListener('click', function () {
      dispatchVerbatimMessageFromSource('core', 'interrupt');
    });
    document.getElementById('agy-wb-interrupt-now-btn').addEventListener('click', function () {
      dispatchVerbatimMessageFromSource('workbench', 'interrupt');
    });
    const stopBtnCore = document.getElementById('agy-stop-btn');
    if (stopBtnCore) {
      stopBtnCore.addEventListener('click', function () {
        stopActiveExecution(currentCid);
      });
    }
    const stopBtnWb = document.getElementById('agy-wb-stop-btn');
    if (stopBtnWb) {
      stopBtnWb.addEventListener('click', function () {
        stopActiveExecution(currentCid);
      });
    }

    [
      { btn: 'btn-agy-attach', inp: 'agy-file-input' },
      { btn: 'btn-wb-attach', inp: 'agy-wb-file-input' }
    ].forEach(function (pair) {
      const b = document.getElementById(pair.btn);
      const fi = document.getElementById(pair.inp);
      if (b && fi) {
        b.addEventListener('click', function () { fi.click(); });
        fi.addEventListener('change', function () {
          if (fi.files && fi.files.length > 0) {
            ingestDroppedOrSelectedFiles(fi.files);
            fi.value = '';
          }
        });
      }
    });

    ['agy-attachment-tray', 'agy-wb-attachment-tray'].forEach(function (tid) {
      const trayEl = document.getElementById(tid);
      if (!trayEl) return;
      trayEl.addEventListener('click', function (e) {
        const rmBtn = e.target.closest('[data-rm-att]');
        if (!rmBtn) return;
        const idx = parseInt(rmBtn.getAttribute('data-rm-att'), 10);
        if (!isNaN(idx) && idx >= 0 && idx < pendingAttachments.length) {
          pendingAttachments.splice(idx, 1);
          renderAttachmentTrays();
        }
      });
    });

    wireDropTarget(document.getElementById('agy-core-modal'), false);
    wireDropTarget(document.getElementById('agy-wb-chat-pane'), true);

    [
      { id: 'agy-chat-input', src: 'core' },
      { id: 'agy-wb-chat-input', src: 'workbench' }
    ].forEach(function (item) {
      const ta = document.getElementById(item.id);
      if (!ta) return;
      ta.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
          e.preventDefault();
          if (e.ctrlKey || e.metaKey) {
            dispatchVerbatimMessageFromSource(item.src, 'interrupt');
          } else {
            dispatchVerbatimMessageFromSource(item.src);
          }
        }
      });
      ta.addEventListener('paste', function (e) {
        const items = e.clipboardData && e.clipboardData.items;
        if (!items) return;
        const files = [];
        for (let i = 0; i < items.length; i++) {
          if (items[i].kind === 'file') {
            const f = items[i].getAsFile();
            if (f) files.push(f);
          }
        }
        if (files.length > 0) ingestDroppedOrSelectedFiles(files);
      });
    });

    ['agy-chat-stream', 'agy-wb-chat-stream'].forEach(function (sid) {
      const el = document.getElementById(sid);
      if (!el) return;
      el.addEventListener('click', handleStreamClickDelegation);
      el.addEventListener('contextmenu', handleStreamContextMenuDelegation);
      el.addEventListener('scroll', function () {
        if (el.clientHeight < 40) return;
        const anchorTop = computeLatestTurnTargetScrollTop(el);
        streamStickBottom[sid] = Math.abs(el.scrollTop - anchorTop) <= 52;
      }, { passive: true });
      if (typeof ResizeObserver !== 'undefined') {
        const ro = new ResizeObserver(function () {
          if (el.clientHeight >= 40 && streamStickBottom[sid] && !pendingScrollTurnKey) {
            snapStreamElToBottomNow(sid);
          }
        });
        ro.observe(el);
      }
    });

    ctxMenu.addEventListener('click', function (e) {
      const item = e.target.closest('[data-ctx-act]');
      if (!item) return;
      const act = item.getAttribute('data-ctx-act');
      const targetCid = ctxMenuCid;
      closeSessionContextMenu();
      performSessionMetaAction(targetCid, act);
    });
    window.addEventListener('click', function (e) {
      if (!e.target.closest('#agy-session-ctx-menu') && !e.target.closest('.agy-conv-more-btn')) {
        closeSessionContextMenu();
      }
    });
    window.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeSessionContextMenu();
    });
  }

  // ==========================================================================
  // Render Session Lists (Zero Colored Emojis!)
  // ==========================================================================
  function renderSingleConvItemHtml(c) {
    const isAct = !isDraftNew && c.id === currentCid;
    const isRun = c.status === 'running';
    const isUnread = convHasUnreadCompletion(c.id);
    const stLabel = isRun ? '● 工作中' : (isUnread ? '✦ 待查收' : '✓ 已完成');
    const stCls = isRun ? 'running' : (isUnread ? 'unread-done' : 'idle');
    const pinPrefix = c.pinned ? '◆ ' : '';
    const subBadge = c.subagentCount > 0 ? ('<span>SWARM×' + c.subagentCount + '</span>') : '';
    const relT = formatRelTime(c.updatedAt, c.updatedEpoch);

    return [
      '<div class="agy-conv-item' + (isAct ? ' active' : '') + '" data-cid="' + escapeHtml(c.id) + '" title="左键切换会话（再点一次当前会话即拉近核心打开对话窗） · 右键置顶 / 归档 / 删除">',
      '  <div class="agy-conv-top">',
      '    <span class="agy-conv-title">' + pinPrefix + monochromizeEmojis(escapeHtml(c.title)) + '</span>',
      '    <span class="agy-st-pill ' + stCls + '">' + stLabel + '</span>',
      '    <button type="button" class="agy-conv-more-btn" data-more-cid="' + escapeHtml(c.id) + '" title="置顶 / 归档 / 删除">⋯</button>',
      '  </div>',
      '  <div class="agy-conv-meta">',
      '    <span>#' + escapeHtml(c.shortId || c.id.slice(0, 8)) + '</span>',
      subBadge,
      (c.archived ? '<span>[已归档]</span>' : ''),
      (relT ? '    <span style="margin-left:auto">' + escapeHtml(relT) + '</span>' : ''),
      '  </div>',
      '</div>'
    ].join('');
  }

  function bindSessionListInteractions(containerEl, isWorkbenchList) {
    if (!containerEl) return;
    containerEl.querySelectorAll('.agy-conv-item').forEach(function (item) {
      item.addEventListener('click', function (e) {
        const moreBtn = e.target.closest('[data-more-cid]');
        if (moreBtn) {
          e.stopPropagation();
          const rect = moreBtn.getBoundingClientRect();
          openSessionContextMenu(moreBtn.getAttribute('data-more-cid'), rect.left, rect.bottom + 4);
          return;
        }
        const cid = item.getAttribute('data-cid');
        if (cid === '__new__') {
          if (isWorkbenchList) switchWorkbenchRightPane('chat');
          else openCoreHubModalUI();
          return;
        }
        selectConversation(cid, isWorkbenchList);
      });

      item.addEventListener('contextmenu', function (e) {
        const cid = item.getAttribute('data-cid');
        if (!cid || cid === '__new__') return;
        e.preventDefault();
        e.stopPropagation();
        openSessionContextMenu(cid, e.clientX, e.clientY);
      });
    });

    const archToggle = containerEl.querySelector('[data-toggle-archived]');
    if (archToggle) {
      archToggle.addEventListener('click', function () {
        showArchivedList = !showArchivedList;
        renderSessionList();
      });
    }
  }

  function renderSessionList() {
    if (IS_WALLPAPER_VIEW) return;
    const rightListEl = document.getElementById('agy-session-list');
    const wbListEl = document.getElementById('agy-wb-session-list');
    const cntEl = document.getElementById('agy-conv-count-badge');

    const activeConvs = conversations.filter(function (c) { return !c.archived; });
    const archivedConvs = conversations.filter(function (c) { return Boolean(c.archived); });

    if (cntEl) cntEl.textContent = '(' + activeConvs.length + ' 活跃' + (archivedConvs.length ? (' · ' + archivedConvs.length + ' 归档') : '') + ')';

    const parts = [];
    if (isDraftNew) {
      parts.push(
        '<div class="agy-conv-item active" data-cid="__new__">',
        '  <div class="agy-conv-top">',
        '    <span class="agy-conv-title">✦ 新建空白会话 (待发送指令)</span>',
        '    <span class="agy-st-pill running">待派单</span>',
        '  </div>',
        '  <div class="agy-conv-meta"><span>#NEW_CASCADE</span><span>直接输入指令即可创建</span></div>',
        '</div>'
      );
    }

    const pinnedConvs = activeConvs.filter(function (c) { return Boolean(c.pinned); });
    const normalConvs = activeConvs.filter(function (c) { return !c.pinned; });

    if (pinnedConvs.length > 0) {
      parts.push('<div class="agy-wb-sec-divider"><span>◆ 已置顶</span><span>' + pinnedConvs.length + '</span></div>');
      for (let i = 0; i < pinnedConvs.length; i++) parts.push(renderSingleConvItemHtml(pinnedConvs[i]));
    }
    if (normalConvs.length > 0) {
      if (pinnedConvs.length > 0) {
        parts.push('<div class="agy-wb-sec-divider"><span>会话列表</span><span>' + normalConvs.length + '</span></div>');
      }
      for (let i = 0; i < normalConvs.length; i++) parts.push(renderSingleConvItemHtml(normalConvs[i]));
    }

    if (archivedConvs.length > 0) {
      parts.push(
        '<button type="button" class="agy-wb-arch-toggle" data-toggle-archived="1">',
        '  <span>已归档会话 (' + archivedConvs.length + ')</span>',
        '  <span>' + (showArchivedList ? '▾ 收起' : '▸ 展开') + '</span>',
        '</button>'
      );
      if (showArchivedList) {
        for (let i = 0; i < archivedConvs.length; i++) parts.push(renderSingleConvItemHtml(archivedConvs[i]));
      }
    }

    if (parts.length === 0) {
      parts.push('<div class="agy-empty-hint">暂无会话，点击上方「+ 新建会话」发起任务</div>');
    }

    const finalHtml = parts.join('');
    if (rightListEl) {
      rightListEl.innerHTML = finalHtml;
      bindSessionListInteractions(rightListEl, false);
    }
    if (wbListEl) {
      wbListEl.innerHTML = finalHtml;
      bindSessionListInteractions(wbListEl, true);
    }
  }

  // ==========================================================================
  // Render Conversation Stream (Chronological Bottom-Anchored + Stop + Queue Jump!)
  // ==========================================================================
  function renderConversationStream(snap, forceScrollBottom) {
    if (!snap) return;
    lastSnapshot = snap;
    currentStatus = snap.status || 'idle';
    if (IS_WALLPAPER_VIEW) return;
    syncSendModeSwitchUI();
    renderCompletedColumnsBars();

    const slabCnt = (snap.slabs || []).length;
    const delivCnt = (snap.deliverables || []).length;
    const curSt = (window.ophanimAgent && typeof window.ophanimAgent.getFullControlState === 'function')
      ? (window.ophanimAgent.getFullControlState() || {})
      : {};
    const eyeCapNow = Math.max(0, Math.min(20, Math.round(8 * (typeof curSt.eyeDensityMult === 'number' ? curSt.eyeDensityMult : 1))));
    const mountedEyesNow = Math.min(delivCnt, eyeCapNow);
    const workerCnt = (snap.workers || []).length;
    const isRun = snap.status === 'running';
    const stTag = isRun ? '● 工作中' : '✓ 已完成';
    const eyeCountLabel = delivCnt > mountedEyesNow
      ? (mountedEyesNow + '/' + delivCnt)
      : String(mountedEyesNow);
    const countsTxt = '薄板 ' + slabCnt + ' · 圣瞳 ' + eyeCountLabel + ' · 蜂群 ' + workerCnt;

    ['agy-core-modal-title', 'agy-wb-chat-title'].forEach(function (id) {
      const el = document.getElementById(id);
      if (el) el.innerHTML = monochromizeEmojis(escapeHtml(snap.title || '当前 Antigravity 会话'));
    });
    ['agy-core-status-pill', 'agy-wb-status-pill'].forEach(function (id) {
      const el = document.getElementById(id);
      if (el) {
        el.textContent = stTag;
        el.className = 'agy-st-pill ' + (isRun ? 'running' : 'idle');
      }
    });
    ['agy-core-binding-counts', 'agy-wb-binding-counts'].forEach(function (id) {
      const el = document.getElementById(id);
      if (el) el.textContent = countsTxt;
    });

    const miniEl = document.getElementById('agy-binding-mini');
    if (miniEl) {
      const shortT = String(snap.title || '当前会话').slice(0, 14);
      miniEl.innerHTML = '<span class="core-dot"></span>核心回执: ' + monochromizeEmojis(escapeHtml(shortT)) + ' [' + stTag + ']';
    }

    const turns = buildTurnsFromSnapshot(snap);
    let streamHtml = '';
    let hadNewTurn = false;
    const cidKey = snap.cascadeId || currentCid || 'new';
    const brandShort = (activeAgentBrandName || 'ANTIGRAVITY').replace(/\s*AGENT$/i, '').trim() || 'Antigravity';

    if (turns.length === 0) {
      streamHtml =
        '<div class="agy-empty-hint">' +
        (isDraftNew
          ? '✦ 新建会话已就绪：在下方输入框直接写下指令（支持拖入图片/文件或粘贴截图），原封不动派发给 ' + escapeHtml(brandShort) + ' 执行！'
          : '该会话暂无轮次记录，可在下方直接追加新任务。') +
        '</div>';
    } else {
      const latestTurnObj = turns[turns.length - 1];
      const latestTurnNum = latestTurnObj ? (latestTurnObj.turnNumber || turns.length) : turns.length;
      const prevSeenTurnNum = lastSeenTurnNumByCid[cidKey] || 0;
      if (prevSeenTurnNum < latestTurnNum) {
        hadNewTurn = true;
        setBoundedMapEntry(lastSeenTurnNumByCid, cidKey, latestTurnNum, MAX_TRACKED_CIDS);
        addBoundedSetKey(expandedTurnKeys, cidKey + ':' + latestTurnNum, MAX_EXPANDED_TURN_KEYS);
      }

      const queuedCount = turns.filter(function (x) { return x.status === 'queued'; }).length;
      const htmlParts = [];

      // Ascending chronological order: oldest turn (#1) at top, newest turn (#N) at bottom right above composer!
      for (let i = 0; i < turns.length; i++) {
        const t = turns[i];
        const tNum = t.turnNumber || (i + 1);
        const turnKey = cidKey + ':' + tNum;
        const isExpanded = expandedTurnKeys.has(turnKey);
        const stRaw = t.status || 'done';
        const isTurnQueued = stRaw === 'queued';
        const isTurnIngested = stRaw === 'ingested' || stRaw === 'merged';
        const tRun = stRaw === 'running' || (isRun && i === turns.length - 1 && !isTurnQueued && !t.hasFinalReply);
        const relTime = t.time ? formatRelTime(t.time, 0) : '';
        const atts = Array.isArray(t.attachments) ? t.attachments : [];
        const cachedPaths = localTurnAttachmentPaths[turnKey] || [];

        const attBadge = atts.length > 0 ? ('<span>附件 ' + atts.length + '</span>') : '';
        let stateBadge = '<span>待回执</span>';
        if (isTurnQueued) {
          stateBadge = '<span class="agy-st-pill queued-pill">' + ICON_QUEUE + ' 排队中</span>';
        } else if (tRun) {
          stateBadge = '<span class="agy-st-pill running">● 执行中</span>';
        } else if (t.hasFinalReply || (t.assistantText && stRaw === 'done')) {
          stateBadge = '<span>✓ 已完成</span>';
        } else if (isTurnIngested) {
          stateBadge = '<span>⇢ 已插队并入</span>';
        }

        let attChipsHtml = '';
        if (atts.length > 0) {
          attChipsHtml = '<div class="agy-turn-att-row">' + atts.map(function (a, aIdx) {
            const fullPath = a.path || cachedPaths[aIdx] || '';
            const kindTag = a.kind === 'image' ? 'IMG' : 'FILE';
            const fName = a.name || (fullPath ? fullPath.split(/[\\/]/).pop() : '附件');
            return (
              '<button type="button" class="agy-turn-att-chip" data-file-path="' + escapeHtml(fullPath) + '" data-file-name="' + escapeHtml(fName) + '" title="左键直接打开此文件 · 右键打开文件所在文件夹' + (fullPath ? ('\n' + escapeHtml(fullPath)) : '') + '">' +
              '<span class="agy-att-kind-tag">' + kindTag + '</span>' +
              '<span>' + monochromizeEmojis(escapeHtml(fName)) + '</span>' +
              '</button>'
            );
          }).join('') + '</div>';
        }

        let queueActionBarHtml = '';
        if (isTurnQueued || (isRun && i === turns.length - 1 && !t.assistantText && stRaw !== 'done')) {
          const canDeleteStep = isTurnQueued && typeof t.userStepIndex === 'number' && t.userStepIndex >= 0;
          queueActionBarHtml =
            '<div class="agy-queue-ctrl-bar">' +
            '  <span>' + (isTurnQueued ? (ICON_QUEUE + ' 此请求当前处于排队队列，可一键主动送入当前轮插队执行：') : (ICON_BOLT + ' 当前会话运行中，可停止当前任务或将排队请求立即插队送入：')) + '</span>' +
            '  <div class="agy-queue-btn-group">' +
            '    <button type="button" class="agy-q-act-btn" data-queue-act="cancel" data-queue-cid="' + escapeHtml(cidKey) + '" title="立即停止并中断当前正在执行的轮次">' + ICON_STOP + ' 停止</button>' +
            '    <button type="button" class="agy-q-act-btn primary" data-queue-act="flush" data-queue-cid="' + escapeHtml(cidKey) + '" title="不等上一条结束，立即主动送进去插队执行">' + ICON_BOLT + ' 立即插队送入</button>' +
            (canDeleteStep
              ? ('    <button type="button" class="agy-q-act-btn" data-queue-act="delete_step" data-queue-cid="' + escapeHtml(cidKey) + '" data-step-idx="' + t.userStepIndex + '" title="从排队队列中撤回此条请求">✕ 撤回排队</button>')
              : '') +
            '  </div>' +
            '</div>';
        }

        const reqHtml =
          '<div class="agy-turn-sec user-req">' +
          '  <div class="agy-turn-sec-lbl"><span>我的请求 · 第 ' + tNum + ' 轮</span><span>' + escapeHtml(relTime) + '</span></div>' +
          (t.userText ? '<div class="agy-msg-user-text">' + monochromizeEmojis(escapeHtml(t.userText)) + '</div>' : '') +
          attChipsHtml +
          queueActionBarHtml +
          '</div>';

        let ansBody = '';
        if (t.assistantText) {
          ansBody = '<div class="agy-msg-body">' + formatAssistantBody(t.assistantText) + '</div>';
        } else if (isTurnQueued) {
          ansBody = '<div class="agy-msg-body" style="color:var(--ink-muted);font-style:italic;">' + ICON_QUEUE + ' 正在排队等待前序任务执行（可点击上方「' + ICON_BOLT + ' 立即插队送入」直接送入当前会话）...</div>';
        } else if (tRun) {
          ansBody = '<div class="agy-msg-body" style="color:var(--ink-muted);font-style:italic;">✦ ' + escapeHtml(brandShort) + ' 正在执行本轮任务，完整输出生成后将自动呈现并点亮白球提醒...</div>';
        } else if (isTurnIngested) {
          ansBody = '<div class="agy-msg-body" style="color:var(--ink-muted);font-style:italic;">⇢ 本条请求已插队合并至后续执行轮次中一并回复。</div>';
        } else {
          ansBody = '<div class="agy-msg-body" style="color:var(--ink-muted);font-style:italic;">（等待智能体生成最终文本回执）</div>';
        }

        const ansHtml =
          '<div class="agy-turn-sec">' +
          '  <div class="agy-turn-sec-lbl"><span>智能体回执与回答</span><span>' + escapeHtml(brandShort.toUpperCase()) + '</span></div>' +
          ansBody +
          '</div>';

        htmlParts.push(
          '<div class="agy-turn-card' + (isExpanded ? ' expanded' : '') + '" data-turn-key="' + escapeHtml(turnKey) + '">',
          '  <button type="button" class="agy-turn-hdr">',
          '    <span class="agy-turn-badge">第 ' + tNum + ' 轮</span>',
          '    <span class="agy-turn-title">' + monochromizeEmojis(escapeHtml(t.title || t.userTitle || ('第 ' + tNum + ' 轮请求'))) + '</span>',
          '    <span class="agy-turn-meta">' + attBadge + stateBadge + (relTime ? ('<span>' + escapeHtml(relTime) + '</span>') : '') + '</span>',
          '    <span class="agy-turn-chev">▸</span>',
          '  </button>',
          '  <div class="agy-turn-body">',
          reqHtml,
          ansHtml,
          '  </div>',
          '</div>'
        );
      }

      if (isRun) {
        htmlParts.push(
          '<div class="agy-live-working-banner">' +
          '  <span>✦ ' + escapeHtml(brandShort) + ' 正在执行任务' + (queuedCount > 0 ? (' · 当前有 ' + queuedCount + ' 条请求排队中') : ' · 最新轮次位于底部') + '</span>' +
          '  <div class="agy-queue-btn-group">' +
          '    <button type="button" class="agy-q-act-btn" data-queue-act="cancel" data-queue-cid="' + escapeHtml(cidKey) + '" title="立即停止当前正在执行的轮次">' + ICON_STOP + ' 停止</button>' +
          (queuedCount > 0
            ? ('    <button type="button" class="agy-q-act-btn primary" data-queue-act="flush" data-queue-cid="' + escapeHtml(cidKey) + '" title="立即将所有排队中的消息主动插队送入当前执行轮次！">' + ICON_BOLT + ' 立即插队送入 (' + queuedCount + ')</button>')
            : '') +
          '  </div>' +
          '</div>'
        );
      }

      streamHtml = htmlParts.join('');
    }

    ['agy-chat-stream', 'agy-wb-chat-stream'].forEach(function (sid) {
      const el = document.getElementById(sid);
      if (!el) return;
      const prevScrollTop = el.scrollTop;
      const shouldSnapLatest = Boolean(forceScrollBottom) || hadNewTurn || Boolean(streamStickBottom[sid]) || (el.clientHeight < 40);
      el.innerHTML = streamHtml;
      if (pendingScrollTurnKey && pendingScrollTurnKey.indexOf(cidKey + ':') === 0) {
        const keyToScroll = pendingScrollTurnKey;
        pendingScrollTurnKey = '';
        scrollStreamToTurnKey(keyToScroll);
      } else if (shouldSnapLatest) {
        streamStickBottom[sid] = true;
        snapStreamElToBottomNow(sid);
        if (forceScrollBottom || hadNewTurn) {
          scheduleSnapStreamsToBottom([sid]);
        }
      } else {
        el.scrollTop = prevScrollTop;
      }
    });
  }

  // ==========================================================================
  // Server Payload Handler
  // ==========================================================================
  function handleServerPayload(payload) {
    if (!payload || typeof payload !== 'object') return false;

    if (payload.type === 'ophanim_backend_info') {
      if (payload.agentName) {
        activeAgentBrandName = String(payload.agentName).trim() || 'ANTIGRAVITY AGENT';
        const wbBrand = document.getElementById('agy-wb-brand-title');
        if (wbBrand) wbBrand.textContent = activeAgentBrandName;
        const wingBrand = document.getElementById('agy-wing-brand-title');
        if (wingBrand) {
          const shortPrefix = activeAgentBrandName.replace(/\s*AGENT$/i, '').trim() || activeAgentBrandName;
          wingBrand.textContent = shortPrefix + ' 会话列表';
        }
      }
      return true;
    }

    if (payload.type === 'ophanim_ai_usage_data' || payload.type === 'ophanim_ai_usage_bundle') {
      handleAiUsagePayload(payload);
      return true;
    }

    if (payload.type === 'ophanim_ai_usage_turns' || payload.type === 'ophanim_ai_usage_turns_ack') {
      handleAiUsageTurnsPayload(payload);
      return true;
    }

    if (payload.type === 'agy_queue_ack' || payload.type === 'agy_queue_action_ack') {
      if (Array.isArray(payload.conversations)) {
        conversations = payload.conversations;
        trackConversationsTransitions(conversations);
      }
      if (payload.snapshot) {
        trackSnapshotTrueCompletions(payload.snapshot, false);
        renderConversationStream(payload.snapshot, false);
      }
      renderSessionList();
      return true;
    }

    if (payload.type === 'agy_session_meta_ack') {
      if (Array.isArray(payload.conversations)) {
        conversations = payload.conversations;
        trackConversationsTransitions(conversations);
      }
      if (payload.activeCascadeId && payload.action === 'delete') {
        currentCid = payload.activeCascadeId;
      }
      if (payload.snapshot) {
        trackSnapshotTrueCompletions(payload.snapshot, true);
        renderConversationStream(payload.snapshot, true);
      }
      renderSessionList();
      return true;
    }

    if (payload.type === 'agy_conversations_list') {
      if (Array.isArray(payload.conversations)) {
        conversations = payload.conversations;
        trackConversationsTransitions(conversations);
      }
      if (!currentCid && payload.activeCascadeId && !isDraftNew) {
        currentCid = payload.activeCascadeId;
      }
      renderSessionList();
      return true;
    }

    if (payload.type === 'agy_conversation_snapshot' && payload.snapshot) {
      const snap = payload.snapshot;
      isDraftNew = false;
      currentCid = snap.cascadeId || currentCid;
      try {
        if (currentCid && currentCid !== '__new__') {
          window.localStorage.setItem(STORAGE_LAST_CID_KEY, currentCid);
        }
      } catch (err) { /* ignore */ }

      if (Array.isArray(payload.conversations)) {
        conversations = payload.conversations;
        trackConversationsTransitions(conversations);
      } else {
        for (let i = 0; i < conversations.length; i++) {
          if (conversations[i].id === currentCid) {
            conversations[i].status = snap.status;
            conversations[i].subagentCount = (snap.workers || []).length;
            conversations[i].title = snap.title || conversations[i].title;
          }
        }
      }
      trackSnapshotTrueCompletions(snap, true);

      renderSessionList();
      renderConversationStream(snap, !pendingScrollTurnKey);

      if (window.ophanimAgent && typeof window.ophanimAgent.transitionToConversationState === 'function') {
        window.ophanimAgent.transitionToConversationState(snap, {
          animate: payload.animateTransition !== false
        });
      }
      return true;
    }

    if (payload.type === 'agy_conversation_delta' && payload.snapshot) {
      const snap = payload.snapshot;
      if (Array.isArray(payload.conversations)) {
        conversations = payload.conversations;
        trackConversationsTransitions(conversations);
      }
      trackSnapshotTrueCompletions(snap, false);

      if (!isDraftNew && snap.cascadeId === currentCid) {
        renderSessionList();
        renderConversationStream(snap, false);
        if (window.ophanimAgent && typeof window.ophanimAgent.syncConversationDelta === 'function') {
          window.ophanimAgent.syncConversationDelta(snap);
        }
      } else {
        renderSessionList();
      }
      return true;
    }

    if (payload.type === 'agy_send_ack') {
      isSending = false;
      ['agy-send-btn', 'agy-wb-send-btn', 'agy-interrupt-now-btn', 'agy-wb-interrupt-now-btn'].forEach(function (id) {
        const b = document.getElementById(id);
        if (b) b.disabled = false;
      });

      if (payload.ok && payload.cascadeId) {
        isDraftNew = false;
        currentCid = payload.cascadeId;
        try { window.localStorage.setItem(STORAGE_LAST_CID_KEY, currentCid); } catch (err) { /* ignore */ }

        if (Array.isArray(payload.stagedPaths) && payload.stagedPaths.length > 0 && lastSnapshot) {
          const turns = buildTurnsFromSnapshot(lastSnapshot);
          if (turns.length > 0) {
            const latestT = turns[turns.length - 1];
            const tKey = currentCid + ':' + (latestT.turnNumber || turns.length);
            setBoundedMapEntry(localTurnAttachmentPaths, tKey, payload.stagedPaths.slice(), MAX_LOCAL_ATT_PATH_KEYS);
            if (Array.isArray(latestT.attachments)) {
              for (let k = 0; k < Math.min(latestT.attachments.length, payload.stagedPaths.length); k++) {
                latestT.attachments[k].path = payload.stagedPaths[k];
              }
            }
          }
        }

        if (Array.isArray(payload.conversations)) {
          conversations = payload.conversations;
          trackConversationsTransitions(conversations);
        }
        if (payload.snapshot) {
          trackSnapshotTrueCompletions(payload.snapshot, false);
          renderConversationStream(payload.snapshot, true);
        } else if (lastSnapshot) {
          lastSnapshot.cascadeId = currentCid;
          renderConversationStream(lastSnapshot, false);
        }
        renderSessionList();
        pushCompletionTo3DEngine();
      } else if (!payload.ok && payload.error) {
        ['agy-chat-stream', 'agy-wb-chat-stream'].forEach(function (sid) {
          const streamEl = document.getElementById(sid);
          if (streamEl) {
            const errDiv = document.createElement('div');
            errDiv.className = 'agy-live-working-banner';
            errDiv.innerHTML = ICON_WARN + ' <span>发送失败: ' + monochromizeEmojis(escapeHtml(payload.error)) + '</span>';
            streamEl.appendChild(errDiv);
            streamStickBottom[sid] = true;
            streamEl.scrollTop = streamEl.scrollHeight;
          }
        });
      }
      return true;
    }

    return false;
  }

  function onSocketOpen(ws) {
    activeWS = ws;
    let preferredCid = '';
    try {
      preferredCid = window.localStorage.getItem(STORAGE_LAST_CID_KEY) || '';
    } catch (err) { /* ignore */ }
    if (ws && ws.readyState === 1) {
      ws.send(JSON.stringify({
        type: 'agy_init_sync',
        preferredCascadeId: preferredCid,
        isWallpaper: IS_WALLPAPER_VIEW
      }));
      if (!IS_WALLPAPER_VIEW) {
        ws.send(JSON.stringify({
          type: 'ophanim_ai_usage_query',
          force: false
        }));
      }
    }
  }

  function getActiveSummary() {
    if (unreadWhiteSphereKeys.size > 0 && completedTaskColumns.length > 0) {
      const topItem = completedTaskColumns[0];
      return {
        title: '✦ 已完成待查收 (' + completedTaskColumns.length + ' 项): ' + topItem.convTitle,
        status: currentStatus,
        statusLabel: '待查收',
        msgCount: completedTaskColumns.length
      };
    }
    const title = lastSnapshot ? (lastSnapshot.title || '当前 Antigravity 会话') : 'Antigravity 会话回执';
    const isRun = currentStatus === 'running';
    const msgCount = (lastSnapshot && Array.isArray(lastSnapshot.messages)) ? lastSnapshot.messages.length : 0;
    return {
      title: title,
      status: currentStatus,
      statusLabel: isRun ? '工作中' : '已完成',
      msgCount: msgCount
    };
  }

  // Called BEFORE 3D White Sphere unread count is cleared when user clicks the Central Sphere!
  function onCoreModalOpening() {
    const hadUnreadSphere = unreadWhiteSphereKeys.size > 0;
    unreadWhiteSphereKeys.clear();
    syncUnreadBadgesUI(computeRunningCount(), 0);
    renderCompletedColumnsBars();

    if (hadUnreadSphere && completedTaskColumns.length > 0) {
      // Auto-locate immediately to the completed task regardless of which conversation was open!
      const targetCol = completedTaskColumns[0];
      focusCompletedTaskColumn(targetCol, false);
      return;
    }

    scheduleSnapStreamsToBottom(['agy-chat-stream']);
  }

  function getPanelConfig() {
    return {
      visible: panelVisible,
      codexBodyCollapsed: codexBodyCollapsed,
      savedCodexWidth: savedCodexWidthPx,
      workbenchOpen: workbenchOpen,
      workbenchMainExpanded: workbenchMainExpanded,
      workbenchWidth: workbenchWidthPx,
      workbenchSidebarWidth: workbenchSidebarWidthPx,
      coreModalWidth: coreModalWidthPx,
      coreModalHeight: coreModalHeightPx
    };
  }

  function applyPanelConfig(cfg) {
    if (IS_WALLPAPER_VIEW || !cfg || typeof cfg !== 'object') return;
    if (typeof cfg.savedCodexWidth === 'number' && cfg.savedCodexWidth >= 300) savedCodexWidthPx = cfg.savedCodexWidth;
    if (typeof cfg.visible === 'boolean') setPanelVisible(cfg.visible);
    if (typeof cfg.codexBodyCollapsed === 'boolean') setCodexBodyCollapsed(cfg.codexBodyCollapsed, true);
    if (typeof cfg.workbenchWidth === 'number') workbenchWidthPx = cfg.workbenchWidth;
    if (typeof cfg.workbenchSidebarWidth === 'number') workbenchSidebarWidthPx = cfg.workbenchSidebarWidth;
    if (typeof cfg.workbenchMainExpanded === 'boolean') workbenchMainExpanded = cfg.workbenchMainExpanded;
    if (typeof cfg.coreModalWidth === 'number' && cfg.coreModalWidth >= 620) coreModalWidthPx = cfg.coreModalWidth;
    if (typeof cfg.coreModalHeight === 'number' && cfg.coreModalHeight >= 440) coreModalHeightPx = cfg.coreModalHeight;
    applyWorkbenchWidths();
    applyCoreModalSavedSize();
    if (typeof cfg.workbenchOpen === 'boolean') setWorkbenchOpen(cfg.workbenchOpen, workbenchMainExpanded);
  }

  window.ophanimAgyPanel = {
    init: buildPanelDOM,
    onSocketOpen: onSocketOpen,
    handleServerPayload: handleServerPayload,
    setVisible: function (vis) {
      if (!vis) {
        if (panelVisible) setPanelVisible(false);
        if (workbenchOpen) setWorkbenchOpen(false);
      }
    },
    toggleRightPanel: function () { setPanelVisible(!panelVisible); },
    setWorkbenchOpen: setWorkbenchOpen,
    isVisible: function () { return workbenchOpen; },
    clearUnreadCompletions: clearUnreadCompletions,
    getPanelConfig: getPanelConfig,
    applyPanelConfig: applyPanelConfig,
    selectConversation: selectConversation,
    getActiveSummary: getActiveSummary,
    onCoreModalOpening: onCoreModalOpening,
    syncBeamModeUI: syncBeamModeUI,
    refreshAiUsage: function () { requestAiUsageData(true); }
  };

  if (!IS_WALLPAPER_VIEW) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', buildPanelDOM);
    } else {
      buildPanelDOM();
    }
  }
})();
