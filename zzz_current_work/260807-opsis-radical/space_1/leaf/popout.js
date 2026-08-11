/* opsis leaf — pop a surface out, or clone it.

   Every facet can leave the grid and float, and every facet can be opened a
   second time beside itself. This replaces the old "x needs a window" mark,
   which told you a surface did not fit and then sent every one of them to
   the same place. A surface that wants more room is not a diagnosis; it is
   something you do. */

'use strict';

let winZ = 400;
const popped = new Map();   // facet name → its floating window

function facetTitle(name) {
  const said = (S && S.facets || []).find((f) => f.name === name);
  return said ? said.title : (FACET_WORD[name] || name);
}

function armFacetButtons() {
  // driven by the facet list the reading sends, so a new surface gets these
  // affordances without the leaf being told about it
  for (const f of (S && S.facets) || []) {
    const head = document.querySelector(`#${f.name} h2`);
    if (!head || head.querySelector('.fpop')) continue;
    const pop = document.createElement('button');
    pop.className = 'fpop';
    pop.textContent = '⧉';
    pop.title = `${f.name} — float it in a window`;
    pop.addEventListener('click', (ev) => { ev.stopPropagation(); popFacet(f.name); });
    const twin = document.createElement('button');
    twin.className = 'fpop';
    twin.textContent = '⧉+';
    twin.title = `${f.name} — open a second one beside this`;
    twin.addEventListener('click', (ev) => { ev.stopPropagation(); cloneFacet(f.name); });
    head.appendChild(pop);
    head.appendChild(twin);
  }
}

function floatWindow(title, at) {
  const el = document.createElement('div');
  el.className = 'pin facetwin';
  el.style.left = (240 + at * 26) + 'px';
  el.style.top = (110 + at * 26) + 'px';
  el.style.width = '620px';
  el.style.height = '460px';
  el.style.zIndex = ++winZ;
  el.innerHTML = `<header><span>${stEsc(title)}</span>`
    + '<button class="x" title="close — the facet goes back where it was">×</button>'
    + '</header>'
    + '<div class="body winbody"></div>'
    + '<div class="wingrip" title="drag to resize"></div>';
  $('pinlayer').appendChild(el);
  dragWindow(el);
  return el;
}

function dragWindow(el) {
  const head = el.querySelector('header');
  let drag = null;
  head.addEventListener('pointerdown', (ev) => {
    if (ev.target.closest('.x')) return;
    drag = { x: ev.clientX - el.offsetLeft, y: ev.clientY - el.offsetTop };
    el.style.zIndex = ++winZ;
    head.setPointerCapture(ev.pointerId);
  });
  head.addEventListener('pointermove', (ev) => {
    if (!drag) return;
    el.style.left = Math.max(0, ev.clientX - drag.x) + 'px';
    el.style.top = Math.max(0, ev.clientY - drag.y) + 'px';
  });
  head.addEventListener('pointerup', () => { drag = null; ask(); });
  const grip = el.querySelector('.wingrip');
  let size = null;
  grip.addEventListener('pointerdown', (ev) => {
    size = { x: ev.clientX, y: ev.clientY, w: el.offsetWidth, h: el.offsetHeight };
    grip.setPointerCapture(ev.pointerId);
    ev.stopPropagation();
  });
  grip.addEventListener('pointermove', (ev) => {
    if (!size) return;
    el.style.width = Math.max(260, size.w + ev.clientX - size.x) + 'px';
    el.style.height = Math.max(180, size.h + ev.clientY - size.y) + 'px';
    layoutFacets();
    ask();
  });
  grip.addEventListener('pointerup', () => { size = null; layoutFacets(); ask(); });
}

function popFacet(name) {
  if (popped.has(name)) { dockFacet(name); return; }
  const sec = $(name);
  if (!sec) return;
  const win = floatWindow(facetTitle(name), popped.size);
  const home = {
    next: sec.nextElementSibling,
    style: sec.getAttribute('style') || '',
    tree: JSON.parse(JSON.stringify(layoutTree)),
  };
  sec.classList.add('inwin');
  win.querySelector('.winbody').appendChild(sec);
  sec.removeAttribute('style');
  popped.set(name, { win, home });
  const button = sec.querySelector('h2 .fpop');
  if (button) button.hidden = true;
  // out of the grid means out of the TREE. Leaving it in left a TAB you
  // could click onto a surface that is not there — the column went blank
  // and the facet read as broken.
  layoutTree = removeLeaf(layoutTree, name) || layoutTree;
  facetOn[name] = false;
  applyFacets(true);
  win.querySelector('.x').addEventListener('click', () => dockFacet(name));
  ask();
}

function dockFacet(name) {
  const held = popped.get(name);
  if (!held) return;
  const sec = $(name);
  $('grid').insertBefore(sec, held.home.next);
  sec.classList.remove('inwin');
  const button = sec.querySelector('h2 .fpop');
  if (button) button.hidden = false;
  sec.setAttribute('style', held.home.style);
  held.win.remove();
  popped.delete(name);
  facetOn[name] = true;
  // back into the arrangement it left, exactly where it was
  layoutTree = held.home.tree;
  applyFacets(true);
  ask();
}

const twins = [];

function cloneFacet(name) {
  // the graph can hold a genuinely independent second view — its own camera,
  // its own mode. Everything else is mirrored live: the same surface, drawn
  // again, so two windows can sit at two places in the same document.
  if (name === 'graph' && typeof graphPin === 'function') { graphPin(); return; }
  if (name === 'chart') { cloneChart(); return; }
  const sec = $(name);
  if (!sec) return;
  const win = floatWindow(facetTitle(name) + ' — a second view', twins.length + popped.size);
  const body = win.querySelector('.winbody');
  body.classList.add('mirror');
  const twin = { name, win, body };
  twins.push(twin);
  win.querySelector('.x').addEventListener('click', () => {
    win.remove();
    twins.splice(twins.indexOf(twin), 1);
  });
  drawTwins();
  ask();
}

function drawTwins() {
  for (const twin of twins) {
    const sec = $(twin.name);
    if (!sec) continue;
    const source = sec.querySelector('canvas');
    if (source) {
      let cv = twin.body.querySelector('canvas');
      if (!cv) {
        cv = document.createElement('canvas');
        twin.body.textContent = '';
        twin.body.appendChild(cv);
      }
      const w = twin.body.clientWidth, h = twin.body.clientHeight;
      if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
      const cx = cv.getContext('2d');
      cx.clearRect(0, 0, w, h);
      if (source.width && source.height) {
        cx.drawImage(source, 0, 0, source.width, source.height, 0, 0, w, h);
      }
      continue;
    }
    const scroll = sec.querySelector('.scroll');
    if (scroll) twin.body.innerHTML = scroll.innerHTML;
  }
}


const chartTwins = [];

function cloneChart() {
  // a real second chart: its own window into the text and its own MOMENT,
  // pinned where you cloned it. Two moments of one parse, side by side —
  // which a picture of a picture could never give you.
  const win = floatWindow('THE DERIVATION — pinned at ' + Math.round(cur.t),
    chartTwins.length + popped.size);
  const body = win.querySelector('.winbody');
  const cv = document.createElement('canvas');
  cv.className = 'twinchart';
  body.classList.add('holds-canvas');
  body.appendChild(cv);
  const view = { cv, zoom: chartZoom, clock: chartClock, t: cur.t, at: view0, hit: null };
  const head = win.querySelector('header span');
  chartTwins.push({ view, win });
  // scrubbing INSIDE the clone moves only the clone
  cv.addEventListener('mousedown', (ev) => {
    const box = cv.getBoundingClientRect();
    const hit = view.hit;
    if (!hit) return;
    const x = ev.clientX - box.left;
    view.t = ev.clientY - box.top < hit.lanesY
      ? Math.max(0, Math.min((x - hit.pad) / (box.width - 2 * hit.pad), 1)) * S.doc.length
      : Math.max(0, Math.min(hit.at + (x - hit.pad) / hit.pitch, S.doc.length));
    head.textContent = 'THE DERIVATION — pinned at ' + Math.round(view.t);
    drawChart(view);
  });
  win.querySelector('.x').addEventListener('click', () => {
    win.remove();
    chartTwins.splice(chartTwins.findIndex((c) => c.view === view), 1);
  });
  drawChart(view);
  ask();
}

function drawChartTwins() {
  for (const twin of chartTwins) {
    drawChart(twin.view);  // the canvas fills the window; CSS sizes it
  }
}
