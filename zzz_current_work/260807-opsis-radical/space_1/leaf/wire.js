/* opsis leaf — the scene wire, the globals it fills, and span queries.
   Carved verbatim from one file: order is load order, and every
   top-level binding stays in the global lexical environment the way it
   was, because the leaf is one program that lives in several files. */

'use strict';

/* opsis facets — the leaf. Generic and nameless: it draws addressed regions and
   reports gestures. Subjects never cross the seam; addresses do. The document
   plane is REAL text — native selection drives structural co-selection. */

'use strict';

const $ = (id) => document.getElementById(id);
const C = {
  field: '#0b0e14', ink: '#e8e2d6', dim: '#66707f', dimmer: '#3a4250',
  cool: '#6fc3c9', warm: '#e2a65c', violet: '#d98cf5', red: '#e06060',
  green: '#79c99a', closed: '#10282e', active: '#3a2f18', pending: '#2a3140',
};
let LH = 19;
const PAD_TOP = 8;
let docZoom = 1;

let S = null;            // the scene: doc, reader, spans, rules, meta
let M = null;            // measured geometry: charW, gutterW
let cur = { t: 0, playing: false, sel: -1, hover: -1, rule: '', docSel: null, frontier: -1, fstarts: null };
let dirty = false;
let pins = [];      // pinned occurrences and pinned facets — uncapped, by ruling
let speed = 1;      // derivation sweep multiplier ([ and ] halve/double)
let gView = 'depth3d';
let gTune = { levelstep: 150, ringscale: 1, flatten: 0.78, labelscale: 1 };
const policyTimers = {};

// The PARSING room's facet set. A value, a compiler, an artefact are NOT
// panes in this room — each is a ROOM that takes the screen and carries its
// own facets. There is no 'rooms' facet, because 'rooms' is not a subject.
// The facet system is GENERIC: layoutFacets walks a tree of leaf NAMES and
// places elements by id. Which facets exist, and which container they live
// in, belong to the ROOM — a value room's facets are as real as the
// reader's, in the same tree, seams, dock and tabs.
let FACETS = ['grammar', 'document', 'chart', 'spine'];
const FACET_WORD = { grammar: 'reader', document: 'document', chart: 'derivation', spine: 'spine' };
let facetOn = { grammar: true, document: true, chart: true, spine: true };
let GRID = 'grid';
const ROOMS = {};
let roomId = 'parse';

function saveArrangement(now = false) {
  // a room's arrangement belongs to the ROOM. Only the parsing room's tree
  // is session policy — otherwise resizing a value room silently rewrote
  // the reader/document/derivation/spine layout for the whole session.
  if (ROOMS[roomId]) ROOMS[roomId].tree = layoutTree;
  if (roomId !== 'parse') return;
  if (now) postPolicy('arrange.tree', treeToText(layoutTree));
  else postPolicyDebounced('arrange.tree', treeToText(layoutTree));
}

function enterRoom(id, spec) {
  const here = ROOMS[roomId];
  if (here) { here.facets = FACETS; here.on = facetOn; here.tree = layoutTree; }
  if (spec) ROOMS[id] = spec;
  const room = ROOMS[id];
  roomId = id;
  GRID = room.grid;
  FACETS = room.facets;
  facetOn = room.on;
  layoutTree = room.tree;
  // literal ids: GRID is the ACTIVE room's container and has just moved
  document.getElementById('grid').hidden = id !== 'parse';
  document.getElementById('place').hidden = id === 'parse';
  layoutFacets();
  buildDock();
}
// ── the arrangement is a TREE (THINKING §9b): internal nodes are h/v
//    splits carrying the a-side share; leaves are facets. Nothing imposes
//    columns; a one-leaf tree IS fullscreen; N facets = a deeper tree.
function defaultTree() {
  return ['h', 0.24, 'grammar', ['h', 0.61, 'document', ['v', 0.58, 'chart', 'spine']]];
}
let layoutTree = defaultTree();
let seamEdges = [];
ROOMS.parse = { grid: 'grid', facets: FACETS, on: facetOn, tree: layoutTree };

function treeToText(node) {
  if (typeof node === 'string') return node;
  const num = node[0] === 't' ? String(Math.round(node[1])) : node[1].toFixed(3);
  return `(${node[0]} ${num} ${treeToText(node[2])} ${treeToText(node[3])})`;
}

function treeOk(node) {
  if (typeof node === 'string') return FACETS.includes(node);
  return Array.isArray(node) && (node[0] === 'h' || node[0] === 'v' || node[0] === 't')
    && treeOk(node[2]) && treeOk(node[3]);
}

function treeFromText(text) {
  const toks = (text || '').replace(/[()]/g, (m) => ' ' + m + ' ').trim().split(/\s+/);
  let i = 0;
  function parse() {
    if (toks[i] === '(') {
      i++;
      const kind = toks[i++];
      const share = parseFloat(toks[i++]);
      const a = parse();
      const b = parse();
      i++;
      if (kind === 't') return ['t', Math.max(0, Math.round(share || 0)), a, b];
      return [kind, Math.max(0.05, Math.min(0.95, share || 0.5)), a, b];
    }
    return toks[i++];
  }
  try {
    const tree = parse();
    return treeOk(tree) ? tree : null;
  } catch { return null; }
}

function treeLeaves(node, out = []) {
  if (typeof node === 'string') out.push(node);
  else { treeLeaves(node[2], out); treeLeaves(node[3], out); }
  return out;
}

function visibleTree(node) {
  if (typeof node === 'string') return facetOn[node] ? node : null;
  const a = visibleTree(node[2]);
  const b = visibleTree(node[3]);
  if (a === null) return b;
  if (b === null) return a;
  return [node[0], node[1], a, b, node];  // [4]: the REAL node a seam edits
}

function layoutFacets() {
  const g = $(GRID);
  const W = g.clientWidth, H = g.clientHeight;
  if (!W || !H) return;
  seamEdges = [];
  const placed = new Set();
  $(GRID).querySelectorAll('.tabbar').forEach((el) => el.remove());
  function place(node, x, y, w, h) {
    if (typeof node === 'string') {
      const el = $(node);
      el.style.left = x + 'px';
      el.style.top = y + 'px';
      el.style.width = w + 'px';
      el.style.height = h + 'px';
      placed.add(node);
      return;
    }
    const [kind, share, a, b] = node;
    const real = node[4] || node;
    if (kind === 't') {
      const leaves = treeLeaves([kind, share, a, b]);
      const act = Math.max(0, Math.min(Math.round(real[1]), leaves.length - 1));
      const bar = document.createElement('div');
      bar.className = 'tabbar';
      bar.style.cssText = `left:${x}px;top:${y}px;width:${w}px`;
      leaves.forEach((nm, i) => {
        const tab = document.createElement('span');
        tab.className = 'tab' + (i === act ? ' on' : '');
        tab.textContent = FACET_WORD[nm] || nm;
        tab.draggable = true;  // a tab is an alias of its node too
        tab.addEventListener('dragstart', () => { dockDrag = nm; });
        tab.addEventListener('click', () => {
          real[1] = i;
          layoutFacets();
          saveArrangement();
          ask();
        });
        bar.appendChild(tab);
      });
      $(GRID).appendChild(bar);
      place(leaves[act], x, y + 22, w, h - 22);
      return;
    }
    if (kind === 'h') {
      const aw = w * share;
      place(a, x, y, aw, h);
      place(b, x + aw, y, w - aw, h);
      seamEdges.push({ axis: 'x', at: x + aw, from: y, to: y + h, real, base: x, size: w });
    } else {
      const ah = h * share;
      place(a, x, y, w, ah);
      place(b, x, y + ah, w, h - ah);
      seamEdges.push({ axis: 'y', at: y + ah, from: x, to: x + w, real, base: y, size: h });
    }
  }
  const vis = visibleTree(layoutTree);
  if (vis !== null) place(vis, 0, 0, W, H);
  for (const name of FACETS) $(name).style.display = placed.has(name) ? '' : 'none';
}

function applyFacets(post = false) {
  for (const name of FACETS) document.body.classList.toggle('off-' + name, !facetOn[name]);
  layoutFacets();
  buildDock();
  if (post) {
    if (roomId === 'parse') {
      for (const name of FACETS) postPolicy('facet.' + name, facetOn[name] ? 'on' : 'off');
    }
    saveArrangement(true);
  }
  ask();
}

function removeLeaf(node, name) {
  if (typeof node === 'string') return node === name ? null : node;
  const a = removeLeaf(node[2], name);
  const b = removeLeaf(node[3], name);
  if (a === null) return b;
  if (b === null) return a;
  return [node[0], node[1], a, b];
}

function moveLeaf(dragged, target, zone) {
  if (dragged === target) return;
  const without = removeLeaf(layoutTree, dragged);
  if (without === null) return;  // the last leaf stays
  function insert(node) {
    if (node === target) {
      if (zone === 'tab') return ['t', 1, node, dragged];
      const kind = zone === 'left' || zone === 'right' ? 'h' : 'v';
      const first = zone === 'left' || zone === 'top';
      return [kind, 0.5, first ? dragged : node, first ? node : dragged];
    }
    if (typeof node === 'string') return node;
    node[2] = insert(node[2]);
    node[3] = insert(node[3]);
    return node;
  }
  layoutTree = insert(without);
  facetOn[dragged] = true;  // dropping a minimized facet reopens it where it lands
  applyFacets(true);
}

function dropZone(el, e) {
  const r = el.getBoundingClientRect();
  const fx = (e.clientX - r.left) / r.width;
  const fy = (e.clientY - r.top) / r.height;
  if (fx < 0.28) return 'left';
  if (fx > 0.72) return 'right';
  if (fy < 0.28) return 'top';
  if (fy > 0.72) return 'bottom';
  return 'tab';
}

function zoneRect(el, zone) {
  const g = $(GRID).getBoundingClientRect();
  const r = el.getBoundingClientRect();
  const x = r.left - g.left, y = r.top - g.top;
  if (zone === 'left') return [x, y, r.width / 2, r.height];
  if (zone === 'right') return [x + r.width / 2, y, r.width / 2, r.height];
  if (zone === 'top') return [x, y, r.width, r.height / 2];
  if (zone === 'bottom') return [x, y + r.height / 2, r.width, r.height / 2];
  return [x + r.width * 0.2, y + r.height * 0.2, r.width * 0.6, r.height * 0.6];
}

function wireFacetDrops() {
  const overlay = document.createElement('div');
  overlay.id = 'dropzone';
  overlay.hidden = true;
  $(GRID).appendChild(overlay);
  // dragend fires on the SOURCE whatever happens — the one reliable cleanup
  window.addEventListener('dragend', () => {
    overlay.hidden = true;
    dockDrag = null;
  });
  for (const name of FACETS) {
    const el = $(name);
    const head = el.querySelector('h2');
    if (head) {
      // the facet's header is an alias of its node — drag it like the chip
      head.draggable = true;
      head.addEventListener('dragstart', (e) => {
        if (e.target.closest('button,select,input')) { e.preventDefault(); return; }
        dockDrag = name;
      });
    }
    el.addEventListener('dragover', (e) => {
      if (!dockDrag || dockDrag === name) return;
      e.preventDefault();
      const zone = dropZone(el, e);
      const [x, y, w, h] = zoneRect(el, zone);
      overlay.style.cssText = `left:${x}px;top:${y}px;width:${w}px;height:${h}px`;
      overlay.hidden = false;
      overlay.textContent = zone === 'tab' ? 'tab with ' + FACET_WORD[name] : 'split ' + zone;
    });
    el.addEventListener('dragleave', () => { overlay.hidden = true; });
    el.addEventListener('drop', (e) => {
      e.preventDefault();
      overlay.hidden = true;
      if (dockDrag && dockDrag !== name) moveLeaf(dockDrag, name, dropZone(el, e));
      dockDrag = null;
    });
  }
}

function swapLeaves(node, a, b) {
  if (typeof node === 'string') return node === a ? b : node === b ? a : node;
  node[2] = swapLeaves(node[2], a, b);
  node[3] = swapLeaves(node[3], a, b);
  return node;
}

let dockDrag = null;

function buildDock() {
  const dock = $('dock');
  if (!dock) return;
  dock.textContent = '';
  // The dock is the REGISTRY of facets, not a list of the ones already
  // placed: a facet absent from the tree still gets a chip, and clicking it
  // splices it in. Without this a facet has no door at all — which is how
  // the rooms facet went missing from the screen.
  const inTree = new Set(treeLeaves(layoutTree));
  for (const name of FACETS) {
    const chip = document.createElement('span');
    chip.className = 'fnode-chip' + (facetOn[name] && inTree.has(name) ? '' : ' off');
    chip.dataset.name = name;
    chip.title = inTree.has(name)
      ? `${FACET_WORD[name]} — click: minimize/reopen · drag onto another: swap places`
      : `${FACET_WORD[name]} — click: bring it into the arrangement`;
    chip.innerHTML = `<i></i>${FACET_WORD[name]}`;
    chip.draggable = true;
    chip.addEventListener('click', () => {
      if (!treeLeaves(layoutTree).includes(name)) {
        layoutTree = ['h', 0.62, layoutTree, name];
        facetOn[name] = true;
        $(name).hidden = false;
        saveArrangement();
        if (name === 'place' && !currentPlace) { openPlace('index', false); return; }
        applyFacets(true);
        return;
      }
      facetOn[name] = !facetOn[name];
      applyFacets(true);
    });
    chip.addEventListener('dragstart', () => { dockDrag = name; });
    chip.addEventListener('dragover', (e) => { e.preventDefault(); chip.classList.add('over'); });
    chip.addEventListener('dragleave', () => chip.classList.remove('over'));
    chip.addEventListener('drop', (e) => {
      e.preventDefault();
      chip.classList.remove('over');
      if (dockDrag && dockDrag !== name) {
        swapLeaves(layoutTree, dockDrag, name);
        applyFacets(true);
      }
      dockDrag = null;
    });
    dock.appendChild(chip);
  }
}

let policySnap = null;
let lastLocalPost = 0;

function postPolicy(key, value) {
  lastLocalPost = performance.now();
  if (policySnap) {
    if (value === '-') delete policySnap[key];
    else policySnap[key] = String(value);
  }
  fetch('/policy', { method: 'POST', body: `${key} ${value}` }).catch(() => {});
}

function postPolicyDebounced(key, value, ms = 350) {
  clearTimeout(policyTimers[key]);
  policyTimers[key] = setTimeout(() => postPolicy(key, value), ms);
}

function setSpeed(x) {
  speed = Math.max(1 / 512, Math.min(16, x));
  postPolicy('speed', speed);
  ask();
}
let pinSeq = 0;
let pinZ = 30;
let view0 = 0;           // chart viewport (leaf-local)
let chartZoom = 1;       // plain scroll on the chart: zoom the lane window
let chartClock = 'model';  // model | pda | earley — which clock the lanes tell
let clockHover = -1;       // hovered document position in a clock view
let clockHoverExt = null;  // the hovered frame / hypothesis extent
let clockData = null;      // { gen, enters, tries, items, entersTop, itemsTop, pdaEnd }
let clockWaiting = false;
let lastPost = 0;
let needsDraw = false;

/* ── scene wire: line-oriented text, length-prefixed blocks ── */

function parseScene(text) {
  const scene = { meta: {}, ruledefs: [], ruleNames: [], fieldNames: [], spans: [], ladder: [] };
  let i = 0;
  const nextLine = () => {
    const j = text.indexOf('\n', i);
    const line = text.slice(i, j);
    i = j + 1;
    return line;
  };
  nextLine(); // #META
  for (let line = nextLine(); !line.startsWith('#'); line = nextLine()) {
    const k = line.indexOf(' ');
    scene.meta[line.slice(0, k)] = line.slice(k + 1);
    if (text[i] === '#') break;
  }
  scene.edges = [];
  scene.depths = {};
  scene.policy = {};
  for (let guard = 0; guard < 12 && i < text.length; guard++) {
    const head = nextLine().split(' ');
    const tag = head[0], n = parseInt(head[1], 10);
    if (tag === '#READER') { scene.reader = text.slice(i, i + n); i += n + 1; continue; }
    if (tag === '#DOC') { scene.doc = text.slice(i, i + n); i += n + 1; continue; }
    const lines = [];
    for (let k = 0; k < n; k++) lines.push(nextLine());
    if (tag === '#RULEDEFS') {
      for (const ln of lines) {
        const parts = ln.split(' ');
        scene.ruledefs.push({ name: parts.slice(0, -2).join(' '), a: +parts.at(-2), b: +parts.at(-1) });
      }
    } else if (tag === '#LADDER') {
      for (const ln of lines) {
        const m = ln.match(/^(\d+) (\d) (\w) (.*)$/);
        if (m) scene.ladder.push({ i: +m[1], focused: m[2] === '1', kind: m[3], label: m[4] });
      }
    } else if (tag === '#RULENAMES') scene.ruleNames = lines;
    else if (tag === '#FIELDNAMES') scene.fieldNames = lines;
    else if (tag === '#SPANS') {
      for (const ln of lines) {
        const p = ln.split(' ');
        scene.spans.push({ s: +p[0], e: +p[1], d: +p[2], r: +p[3], f: +p[4] });
      }
    } else if (tag === '#EDGES') {
      scene.edges = lines.map((ln) => ln.split(' '));
    } else if (tag === '#DEPTHS') {
      for (const ln of lines) {
        const sp = ln.lastIndexOf(' ');
        scene.depths[ln.slice(0, sp)] = +ln.slice(sp + 1);
      }
    } else if (tag === '#POLICY') {
      for (const ln of lines) {
        const sp = ln.indexOf(' ');
        scene.policy[ln.slice(0, sp)] = ln.slice(sp + 1);
      }
    }
  }
  scene.lineStarts = starts(scene.doc);
  scene.readerLines = scene.reader.split('\n');
  scene.maxdepth = scene.spans.reduce((m, s) => Math.max(m, s.d), 0);
  scene.byEnd = [...scene.spans.keys()].sort((a, b) => scene.spans[a].e - scene.spans[b].e);
  scene.ruleOf = {};
  scene.ruledefs.forEach((r) => { scene.ruleOf[r.name] = r; });
  return scene;
}

function starts(text) {
  const out = [0];
  for (let i = 0; i < text.length; i++) if (text[i] === '\n') out.push(i + 1);
  return out;
}

/* ── span queries (linear scans: 12k spans is nothing) ── */

const lineOf = (off) => {
  let lo = 0, hi = S.lineStarts.length - 1;
  while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (S.lineStarts[mid] <= off) lo = mid; else hi = mid - 1; }
  return lo;
};
const deepestAt = (off) => {
  let best = -1;
  S.spans.forEach((s, i) => { if (s.s <= off && off < s.e && (best < 0 || s.d > S.spans[best].d)) best = i; });
  return best;
};
const smallestOver = (lo, hi) => {
  let best = -1;
  S.spans.forEach((s, i) => {
    if (s.s <= lo && hi <= s.e && (best < 0 || s.e - s.s < S.spans[best].e - S.spans[best].s)) best = i;
  });
  return best;
};
const openAt = (t) => S.spans.map((s, i) => i).filter((i) => S.spans[i].s < t && t < S.spans[i].e)
  .sort((a, b) => S.spans[a].d - S.spans[b].d);
