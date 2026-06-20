/* ============================================================
   Poster Knowledge Map — Render & Interaction
   ============================================================
   Renders a poster-style knowledge evolution diagram with:
   - Center theme node
   - 4 module cards in diamond layout
   - SVG arrows with evolution rationale labels
   - Click → highlight papers in Cytoscape network

   Expects global: modules[], arrows[], paperCy (Cytoscape instance)
   Expects global selectors: #poster-container, #poster-scroll
   ============================================================ */

const PosterMap = (function () {
  'use strict';

  // ── Shared selection state ──
  let selectedModuleId = null;

  // ── Module data (populated by API or fallback) ──
  let modules = [];
  let arrows = [];

  // ── Layout geometry ──
  const CENTER_R = 65;
  const CARD_W = 240;

  // ── Get container dimensions ──
  function containerSize() {
    const el = document.getElementById('poster-container');
    const w = Math.max(620, (el ? el.clientWidth : 700) - 20);
    const h = Math.max(700, (el ? el.clientHeight : 800) - 10);
    return { w, h, cx: w / 2, cy: h / 2 };
  }

  // ── Module card positions (diamond around center) ──
  function cardPositions(cx, cy) {
    return [
      { x: cx - 180, y: cy - 180 },
      { x: cx + 180, y: cy - 180 },
      { x: cx - 180, y: cy + 180 },
      { x: cx + 180, y: cy + 180 },
    ];
  }

  // ── Render the complete poster ──
  function render(mods, arrs) {
    modules = mods || modules;
    arrows = arrs || arrows;
    if (!modules.length) return;

    const scroll = document.getElementById('poster-scroll');
    const { w, h, cx, cy } = containerSize();
    const positions = cardPositions(cx, cy);

    // Build SVG arrows
    let svgArrows = '';
    arrows.forEach((a) => {
      const fromI = modules.findIndex((m) => m.id === a.from);
      const toI = modules.findIndex((m) => m.id === a.to);
      if (fromI < 0 || toI < 0) return;
      const fp = positions[fromI];
      const tp = positions[toI];
      const fx = fp.x + CARD_W / 2;
      const fy = fp.y + 70;
      const tx = tp.x - CARD_W / 2;
      const ty = tp.y + 70;
      const mx = (fx + tx) / 2;
      const my = (fy + ty) / 2;
      svgArrows += `
        <path d="M${fx},${fy} C${mx},${fy - 20} ${mx},${ty - 20} ${tx},${ty}"
              stroke="#A3B89A" stroke-width="2.5" fill="none"
              marker-end="url(#arrowGreen)"/>
        <rect x="${mx - 55}" y="${my - 20}" width="110" height="18" rx="8"
              fill="rgba(255,255,255,0.88)" stroke="none"/>
        <text x="${mx}" y="${my - 7}" text-anchor="middle"
              font-size="11" font-weight="600" fill="#166534" font-family="system-ui,sans-serif">${a.label}</text>`;
    });

    // Subtle dashed lines from center to each module
    modules.forEach((_m, i) => {
      const tc = positions[i];
      svgArrows += `
        <line x1="${cx}" y1="${cy + CENTER_R}" x2="${tc.x}" y2="${tc.y - 70}"
              stroke="#D1D5DB" stroke-width="1" stroke-dasharray="4 4" opacity="0.3"/>`;
    });

    // Build card HTML
    let cardsHTML = '';
    modules.forEach((m, i) => {
      const pos = positions[i];
      const isActive = selectedModuleId === m.id;
      const left = pos.x - CARD_W / 2;
      const top = pos.y - 70;
      cardsHTML += `
        <div class="module-card${isActive ? ' active' : ''}" id="mcard-${m.id}" data-module="${m.id}"
             style="left:${left}px;top:${top}px;border-top:3px solid ${m.color || '#2F9E71'}">
          <div class="mod-num">Module ${m.num || i + 1} · ${m.en || ''}</div>
          <div class="mod-title">${m.title}</div>
          <div class="mod-tag">${m.tag || ''}</div>
          <div class="mod-idea">${m.idea}</div>
          <div class="mod-papers">${(m.papers || []).map((p) => '<span>·</span> ' + p).join('<br>')}</div>
        </div>`;
    });

    scroll.innerHTML = `
      <div class="poster-inner" style="position:relative;width:${w}px;height:${h}px;margin:0 auto">
        <svg class="poster-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMid meet">
          <defs>
            <marker id="arrowGreen" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="#A3B89A"/>
            </marker>
          </defs>
          ${svgArrows}
        </svg>

        <div class="center-node" style="left:${cx - CENTER_R}px;top:${cy - CENTER_R}px">
          ${modules[0]?.topic || 'Algorithm<br>Evolution'}
        </div>

        ${cardsHTML}
      </div>`;

    // Attach click handlers
    scroll.querySelectorAll('.module-card').forEach((card) => {
      card.addEventListener('click', function () {
        const mid = this.dataset.module;
        if (selectedModuleId === mid) {
          selectedModuleId = null;
          clearSelection();
          return;
        }
        selectedModuleId = mid;
        applySelection();
      });
    });

    // Re-attach on resize
    if (window._posterResizeHandler) {
      window.removeEventListener('resize', window._posterResizeHandler);
    }
    window._posterResizeHandler = function () {
      clearTimeout(window._posterResizeTimer);
      window._posterResizeTimer = setTimeout(function () {
        render(modules, arrows);
        if (selectedModuleId) applySelection();
      }, 250);
    };
    window.addEventListener('resize', window._posterResizeHandler);
  }

  // ── Apply cross-view selection ──
  function applySelection() {
    if (!selectedModuleId) return;
    const m = modules.find((m) => m.id === selectedModuleId);
    if (!m) return;

    // Highlight module card
    document.querySelectorAll('.module-card').forEach((c) => c.classList.remove('active'));
    document.getElementById('mcard-' + selectedModuleId)?.classList.add('active');

    // Highlight papers in network
    if (typeof paperCy !== 'undefined' && m.paperIds) {
      paperCy.elements().removeClass('dimmed').removeClass('highlighted');
      paperCy.elements().addClass('dimmed');
      paperCy
        .nodes()
        .filter((n) => m.paperIds.includes(n.id()))
        .removeClass('dimmed')
        .addClass('highlighted');
    }

    // Show module detail (if drawer exists)
    if (typeof showModuleDetail === 'function') {
      showModuleDetail(m, m.paperIds || []);
    }
  }

  function clearSelection() {
    selectedModuleId = null;
    document.querySelectorAll('.module-card').forEach((c) => c.classList.remove('active'));
    if (typeof paperCy !== 'undefined') {
      paperCy.elements().removeClass('dimmed').removeClass('highlighted');
    }
  }

  function selectModule(mid) {
    if (selectedModuleId === mid) {
      clearSelection();
      return;
    }
    selectedModuleId = mid;
    applySelection();
  }

  function getSelectedModuleId() {
    return selectedModuleId;
  }

  // ── Public API ──
  return {
    render: render,
    selectModule: selectModule,
    clearSelection: clearSelection,
    getSelectedModuleId: getSelectedModuleId,
  };
})();

// ── Global convenience ──
function selectPosterModule(mid) { PosterMap.selectModule(mid); }
