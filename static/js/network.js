/* ============================================================
   Paper Network — Cytoscape-based interactive graph
   ============================================================
   Renders the Evidence Layer paper relationship network.
   - Green gradient nodes (citation count → darkness)
   - No arrowheads on edges
   - Labels on hover only
   - Cross-view selection integration

   Expects global: paperNodes[], paperEdges[] (from API)
   Expects global selector: #network-container
   ============================================================ */

const PaperNetwork = (function () {
  'use strict';

  let cyInstance = null;

  // ── Green gradient: light (low citations) → dark (high citations) ──
  function citationColor(citations) {
    const lo = 200, hi = 100000;
    const t = Math.max(0, Math.min(1, (Math.log(citations) - Math.log(lo)) / (Math.log(hi) - Math.log(lo))));
    const h = 142 + t * 20;
    const s = 76 - t * 16;
    const l = 45 - t * 29;
    return 'hsl(' + h + ',' + s + '%,' + l + '%)';
  }

  // ── Initialize Cytoscape ──
  function init(papers, edges) {
    papers = papers || [];
    edges = edges || [];

    if (cyInstance) {
      cyInstance.destroy();
    }

    cyInstance = cytoscape({
      container: document.getElementById('network-container'),
      style: [
        {
          selector: 'node',
          style: {
            label: '',
            width: 'mapData(citations,200,100000,18,58)',
            height: 'mapData(citations,200,100000,18,58)',
            'border-width': 2,
            'border-color': '#fff',
            'font-size': 9,
            color: '#55514A',
            'text-wrap': 'wrap',
            'text-max-width': 80,
            'text-valign': 'bottom',
            'text-halign': 'center',
            'text-margin-y': 4,
            'shadow-blur': 3,
            'shadow-color': 'rgba(0,0,0,.06)',
          },
        },
        {
          selector: 'node[isFound]',
          style: {
            'border-color': '#166534',
            'border-width': 3,
            width: 'mapData(citations,200,100000,24,62)',
            height: 'mapData(citations,200,100000,24,62)',
          },
        },
        {
          selector: 'edge',
          style: {
            width: 0.7,
            'line-color': '#C5D5BD',
            'target-arrow-shape': 'none',
            'curve-style': 'bezier',
            opacity: 0.45,
          },
        },
        {
          selector: 'node:selected',
          style: {
            'border-color': '#F59E0B',
            'border-width': 3,
            'shadow-blur': 10,
            'shadow-color': 'rgba(245,158,11,.35)',
          },
        },
        {
          selector: 'node.highlighted',
          style: {
            'border-color': '#F59E0B',
            'border-width': 3,
            'shadow-blur': 12,
            'shadow-color': 'rgba(245,158,11,.5)',
          },
        },
        { selector: 'node.dimmed', style: { opacity: 0.12 } },
        { selector: 'edge.dimmed', style: { opacity: 0.04 } },
      ],
    });

    // Add nodes with per-node green
    papers.forEach(function (n) {
      cyInstance.add({
        group: 'nodes',
        data: n,
        style: { 'background-color': citationColor(n.citations || 0) },
      });
    });
    edges.forEach(function (e) {
      cyInstance.add({ group: 'edges', data: e });
    });

    // Force-directed layout
    cyInstance
      .layout({
        name: 'cose',
        idealEdgeLength: 130,
        nodeOverlap: 20,
        fit: true,
        padding: 30,
        componentSpacing: 120,
        nodeRepulsion: function () { return 7000; },
        edgeElasticity: function () { return 80; },
        gravity: 100,
        numIter: 1200,
      })
      .run();

    // Hover: show label + tooltip
    cyInstance.on('mouseover', 'node', function (evt) {
      var d = evt.target.data();
      evt.target.style('label', (d.label || '').replace(/\n/g, ' '));
      // tooltip handled externally if needed
    });
    cyInstance.on('mouseout', 'node', function (evt) {
      if (!evt.target.hasClass('highlighted')) {
        evt.target.style('label', '');
      }
    });

    // Expose globally for poster integration
    window.paperCy = cyInstance;
    return cyInstance;
  }

  // ── Highlight papers belonging to a module ──
  function highlightByPaperIds(paperIds) {
    if (!cyInstance || !paperIds) return;
    cyInstance.elements().removeClass('dimmed').removeClass('highlighted');
    cyInstance.elements().addClass('dimmed');
    cyInstance
      .nodes()
      .filter(function (n) { return paperIds.indexOf(n.id()) >= 0; })
      .removeClass('dimmed')
      .addClass('highlighted');
  }

  // ── Clear all highlights ──
  function clearHighlights() {
    if (!cyInstance) return;
    cyInstance.elements().removeClass('dimmed').removeClass('highlighted');
  }

  // ── Toggle edges ──
  function toggleEdges(visible) {
    if (!cyInstance) return;
    cyInstance.edges().style('display', visible ? 'element' : 'none');
  }

  // ── Fit to viewport ──
  function fit() {
    if (!cyInstance) return;
    cyInstance.fit(undefined, 30);
  }

  // ── Apply filters ──
  function applyFilters(yearFilter, clusterFilter) {
    if (!cyInstance) return;
    cyInstance.nodes().forEach(function (n) {
      var d = n.data();
      var show = true;
      if (yearFilter === 'early' && d.year > 2017) show = false;
      if (yearFilter === 'mid' && (d.year < 2019 || d.year > 2021)) show = false;
      if (yearFilter === 'late' && d.year < 2022) show = false;
      if (clusterFilter !== 'all' && d.cluster !== clusterFilter) show = false;
      n.style('display', show ? 'element' : 'none');
    });
  }

  return {
    init: init,
    highlightByPaperIds: highlightByPaperIds,
    clearHighlights: clearHighlights,
    toggleEdges: toggleEdges,
    fit: fit,
    applyFilters: applyFilters,
    getInstance: function () { return cyInstance; },
  };
})();
