/* The map and the rooms — the level above any one reading. The strata
   draws relation instances as cards and their rooms as doors; a place
   draws one room's facets. Carved together because they share the door
   vocabulary and share nothing with the planes, the chart or the spine. */

/* ── the strata: a GRID — rows are strata and bands, columns are things ── */

const stEsc = (s) => s.replace(/[&<>"]/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

async function openStrata() {
  const text = await (await fetch('/strata')).text();
  drawStrata(parseStrata(text));
}

function parseStrata(text) {
  const cards = new Map(); const lanes = new Map(); const places = [];
  const ghosts = []; const sibs = []; let focus = 0;
  for (const ln of text.split('\n')) {
    if (ln.startsWith('#STRATA')) focus = +ln.split(' ')[2];
    else if (ln.startsWith('L ')) {
      const m = ln.match(/^L (\d+) (.*)$/);
      if (m) lanes.set(+m[1], m[2]);
    } else if (ln.startsWith('c ')) {
      const m = ln.match(/^c (\d+) (-?\d+) (\d+) (\w) (\d) (.*)$/);
      if (m) cards.set(+m[1], { i: +m[1], level: +m[2], lane: +m[3],
                                kind: m[4], visited: m[5] === '1', label: m[6] });
    } else if (ln.startsWith('k ')) {
      const p = ln.split(' '); const c = cards.get(+p[1]);
      if (c) { c.chars = +p[2]; c.spans = +p[3]; c.rules = +p[4];
               c.secs = p[5]; c.faithful = p[6] === '1'; c.plugged = p[7] === '1'; }
    } else if (ln.startsWith('b ')) {
      const p = ln.split(' '); const c = cards.get(+p[1]);
      if (c) c.band = p.slice(2).map(Number);
    } else if (ln.startsWith('p ')) {
      const m = ln.match(/^p (\d+) (.*)$/); const c = m && cards.get(+m[1]);
      if (c) c.plugs = m[2];
    } else if (ln.startsWith('s ')) {
      const m = ln.match(/^s (\d+) (\S+) (.*)$/);
      if (m) sibs.push({ i: +m[1], pid: m[2], label: m[3] });
    } else if (ln.startsWith('P ')) {
      const m = ln.match(/^P (\S+) (\d+) (-?\d+) (\w+) (ok|no) ([^\t]*)\t?(.*)$/);
      if (m) places.push({ pid: m[1], lane: +m[2], band: +m[3], kind: m[4],
                           ok: m[5] === 'ok', label: m[6], facts: m[7] || '' });
    } else if (ln.startsWith('g ')) {
      const m = ln.match(/^g (\w+) (ok|no) (.*)$/);
      if (m) ghosts.push({ flavour: m[1], ok: m[2] === 'ok', words: m[3] });
    }
  }
  return { cards: [...cards.values()], lanes, places, ghosts, sibs, focus };
}

function stReadingCard(c, focus, sibs) {
  const counts = c.visited
    ? `<div class="stK">${c.chars.toLocaleString()} chars · `
      + `${c.spans.toLocaleString()} spans · ${c.rules} rules · ${c.secs}s`
      + `${c.faithful ? '' : ' · UNFAITHFUL'}</div>`
      + (c.plugs ? `<div class="stK stPlugs">${stEsc(c.plugs.replaceAll('=', ' = ').replaceAll(' ', ' '))}</div>` : '')
    : '<div class="stK stDim">not yet visited — travel builds it</div>';
  const band = c.visited && c.band
    ? `<canvas class="stBand" data-band="${c.band.join(',')}"></canvas>` : '';
  const sibHtml = sibs.filter((s) => s.i === c.i).map((s) =>
    `<div class="stSib" data-place="${stEsc(s.pid)}">${stEsc(s.label)}</div>`).join('');
  return `<div class="stCard k-${c.kind}${c.i === focus ? ' on' : ''}`
    + `${c.visited ? '' : ' unvisited'}" data-i="${c.i}">`
    + `<div class="stL">${stEsc(c.label)}</div>${band}${counts}</div>` + sibHtml;
}

function stRooms(st, lane) {
  // the rooms a thing has, as ONE line — the menu stays a chain, and the
  // values / compiler / artefacts keep a visible door
  const mine = st.places.filter((p) => p.lane === lane);
  if (!mine.length) return '';
  const kinds = [['value', 'values'], ['compiler', 'the compiler'],
                 ['artefacts', 'artefacts']];
  const links = kinds.map(([kind, word]) => {
    const hit = mine.filter((p) => p.kind === kind);
    if (!hit.length) return '';
    const n = kind === 'value' && hit.length > 1 ? ` ${hit.length}` : '';
    return `<span class="stRoom" data-place="${stEsc(hit[0].pid)}">`
      + `${word}${n}</span>`;
  }).filter(Boolean).join('<i>·</i>');
  return links ? `<div class="stRooms">${links}</div>` : '';
}

function stPlaceCard(p) {
  return `<div class="stPlace k-${p.kind}${p.ok ? '' : ' no'}" data-place="${stEsc(p.pid)}">`
    + `<span class="stTag">${stEsc(p.kind)}</span>`
    + `<div class="stL">${stEsc(p.label)}</div>`
    + (p.facts ? `<div class="stK">${stEsc(p.facts)}</div>` : '')
    + '</div>';
}

function drawStrata(st) {
  let layer = $('strata');
  if (!layer) {
    layer = document.createElement('div');
    layer.id = 'strata';
    document.body.appendChild(layer);
  }
  // The menu is the CHAIN, and nothing else: one column per thing in true
  // reading order, its readings inside. Values, the compiler and the
  // artefacts are rooms — they live in the instrument, not in the menu.
  const level = new Map();
  for (const c of st.cards) {
    if (c.level < 0) continue;                       // outward is not a place in the chain
    if (!level.has(c.lane) || c.level < level.get(c.lane)) level.set(c.lane, c.level);
  }
  const laneIds = [...st.lanes.keys()].filter((l) => st.cards.some((c) => c.lane === l))
    .sort((a, b) => (level.has(a) ? level.get(a) : 999) - (level.has(b) ? level.get(b) : 999)
                    || a - b);
  const chain = laneIds.filter((l) => level.has(l) && level.get(l) < 90);
  const cells = [];
  laneIds.forEach((lane, li) => {
    const rank = chain.indexOf(lane);
    const tag = rank < 0 ? 'the instrument' : `stratum ${rank}`;
    cells.push(`<div class="stCol"><div class="stHead">`
      + `<span class="stTag">${tag}</span>${stEsc(st.lanes.get(lane))}</div>`
      + st.cards.filter((c) => c.lane === lane)
        .sort((a, b) => a.level - b.level)
        .map((c) => stReadingCard(c, st.focus, st.sibs)).join('')
      + stRooms(st, lane)
      + '</div>');
  });
  layer.innerHTML = '<div class="stTitle">the chain — one column per thing, in '
    + 'reading order · click a reading to travel · the rooms live in the '
    + 'instrument, under ROOMS · Esc returns</div>'
    + `<div class="stChain">${cells.join('')}</div>`;
  strataWanted = true;
  // the add is deferred a frame; if a room opened in the meantime the menu
  // must NOT come back over it — the intent decides, not the timer
  requestAnimationFrame(() => { if (strataWanted) layer.classList.add('on'); });
  for (const el of layer.querySelectorAll('.stCard[data-i]')) {
    el.addEventListener('click', async () => {
      closeStrata();
      if (+el.dataset.i !== st.focus) await travel(+el.dataset.i);
    });
  }
  for (const el of layer.querySelectorAll('[data-place]')) {
    el.addEventListener('click', (ev) => {
      ev.stopPropagation();
      openPlace(el.dataset.place);
    });
  }
  for (const el of layer.querySelectorAll('.stGhost.ok')) {
    el.addEventListener('click', async () => {
      const reply = await (await fetch('/cast', {
        method: 'POST', body: 'transpile ' + el.dataset.flavour })).text();
      const m = reply.match(/^rung (\d+)/);
      if (m) { closeStrata(); await travel(+m[1]); }
    });
  }
  for (const cv of layer.querySelectorAll('canvas.stBand')) {
    const vals = cv.dataset.band.split(',').map(Number);
    const w = 258, h = 24;
    cv.width = w; cv.height = h;
    const ctx = cv.getContext('2d');
    ctx.fillStyle = 'rgba(110,168,254,.7)';
    vals.forEach((v, i) => {
      const bh = (v / 9) * (h - 2);
      ctx.fillRect(i * w / vals.length, h - bh, Math.max(1, w / vals.length - 1), bh);
    });
  }
}

let strataWanted = false;

function closeStrata() {
  strataWanted = false;                 // cancels any frame still pending
  const layer = $('strata');
  if (layer) layer.classList.remove('on');
}

/* ── the place room: a subject seen as what it IS — never the parser ── */

let placeStack = [];

async function openPlace(pid, remember = true) {
  closeStrata();
  if (remember && currentPlace && currentPlace !== pid) placeStack.push(currentPlace);
  currentPlace = pid;
  const text = await (await fetch(`/place?id=${encodeURIComponent(pid)}`)).text();
  drawPlace(parsePlace(text));            // drawPlace enters the room
}

function leaveRoom() {
  currentPlace = null;
  placeStack = [];
  enterRoom('parse');
}

let currentPlace = null;

function parsePlace(text) {
  const lines = text.split('\n');
  const place = { pid: '', kind: '', title: '', sections: [] };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith('#PLACE ')) {
      const [pid, kind, ...rest] = line.slice(7).split(' ');
      Object.assign(place, { pid, kind, title: rest.join(' ') });
    } else if (line.startsWith('#SEC ')) {
      const [kind, count] = line.slice(5).split(' ');
      const n = parseInt(count, 10);
      place.sections.push({ kind, body: lines.slice(i + 1, i + 1 + n) });
      i += n;
    }
  }
  return place;
}

function renderPlaceSection(sec) {
  if (sec.kind === 'kv') {
    const rows = sec.body.map((line) => {
      const [k, v] = line.split('\t');
      return `<tr><td class="k">${stEsc(k)}</td><td>${stEsc(v || '')}</td></tr>`;
    });
    return `<table class="pkv">${rows.join('')}</table>`;
  }
  if (sec.kind === 'list') {
    return sec.body.map((line) => {
      const [text, addr] = line.split('\t');
      if (addr && addr.startsWith('place:')) {
        return `<div class="prow paddr" data-place="${stEsc(addr.slice(6))}">`
          + `${stEsc(text)}</div>`;
      }
      if (addr && addr.startsWith('cast:')) {
        return `<div class="prow paddr" data-cast="${stEsc(addr.slice(5))}">`
          + `${stEsc(text)}</div>`;
      }
      if (addr && addr.startsWith('artefact:')) {
        return `<div class="prow paddr" data-place="a${addr.split(':')[1]}">`
          + `${stEsc(text)}</div>`;
      }
      return `<div class="prow">${stEsc(text)}</div>`;
    }).join('');
  }
  if (sec.kind === 'tree') {
    return `<div class="ptree">${sec.body.map((line) => {
      const [depth, text] = line.split('\t');
      return '  '.repeat(+depth || 0) + stEsc(text);
    }).join('\n')}</div>`;
  }
  if (sec.kind === 'textlines') {
    const body = sec.body.map((line) => line.slice(1)).join('\n');
    return `<pre class="pplane">${stEsc(body)}</pre>`;
  }
  if (sec.kind === 'graphview') {
    const pid = sec.body[0] || '';
    return `<div class="gview" data-place="${stEsc(pid)}"><div class="gtabs">`
      + ['flat', 'arcs', '3d'].map((v, i) =>
        `<button class="gtab${i === 0 ? ' on' : ''}" data-view="${v}">${v}</button>`
      ).join('') + '</div><canvas class="gcanvas"></canvas></div>';
  }
  if (sec.kind === 'irvalue') {
    return `<div class="irv" data-place="${stEsc(sec.body[0] || '')}" data-path="">`
      + '<div class="irhead"></div><div class="irbody"></div></div>';
  }
  if (sec.kind === 'facet') return '';
  if (sec.kind === 'title') return `<div class="ptitle">${stEsc(sec.body[0] || '')}</div>`;
  if (sec.kind === 'refusal') return `<div class="pwords">${stEsc(sec.body[0] || '')}</div>`;
  return '';
}

function placeFacets(sections) {
  const groups = [];
  let cur = null;
  for (const sec of sections) {
    if (sec.kind === 'facet') {
      cur = { title: sec.body[0] || '', secs: [] };
      groups.push(cur);
    } else {
      if (!cur) { cur = { title: '', secs: [] }; groups.push(cur); }
      cur.secs.push(sec);
    }
  }
  return groups;
}

function wireRoomSeams(deck) {
  for (const seam of deck.querySelectorAll('.pseam')) {
    seam.addEventListener('pointerdown', (ev) => {
      const a = seam.previousElementSibling, b = seam.nextElementSibling;
      if (!a || !b) return;
      const x0 = ev.clientX;
      const wa = a.getBoundingClientRect().width, wb = b.getBoundingClientRect().width;
      seam.setPointerCapture(ev.pointerId);
      const move = (e) => {
        const dx = e.clientX - x0;
        a.style.flex = `${Math.max(140, wa + dx)} 1 0`;
        b.style.flex = `${Math.max(140, wb - dx)} 1 0`;
        for (const v of deck.querySelectorAll('.gview')) if (v._g) pvDrawView(v);
      };
      seam.addEventListener('pointermove', move);
      seam.addEventListener('pointerup', () => seam.removeEventListener('pointermove', move));
      ev.preventDefault();
    });
  }
}

function drawPlace(place) {
  placeStack = place.pid === 'index' ? [] : placeStack;
  $('placeKind').textContent = place.kind;
  $('placeTitle').textContent = place.title;
  $('placeBack').hidden = place.pid === 'index';
  const groups = placeFacets(place.sections);
  const grid = $('placeGrid');
  grid.textContent = '';
  const names = groups.map((_g, i) => `pf${i}`);
  groups.forEach((g, i) => {
    const el = document.createElement('section');
    el.className = 'facet';
    el.id = names[i];
    el.innerHTML = `<h2>${stEsc(g.title)}</h2><div class="pinner">`
      + g.secs.map((s) => `<div class="psec">${renderPlaceSection(s)}</div>`).join('')
      + '</div>';
    grid.appendChild(el);
    FACET_WORD[names[i]] = g.title.split(/[—·]/)[0].trim().slice(0, 22) || `facet ${i}`;
  });
  const on = {};
  for (const n of names) on[n] = true;
  let tree = names[names.length - 1];
  for (let i = names.length - 2; i >= 0; i--) {
    tree = ['h', 1 / (names.length - i), names[i], tree];
  }
  enterRoom('place', { grid: 'placeGrid', facets: names, on, tree });
  const body = $('placeGrid');
  for (const el of body.querySelectorAll('.paddr[data-place]')) {
    el.addEventListener('click', () => openPlace(el.dataset.place));
  }
  for (const el of body.querySelectorAll('.paddr[data-cast]')) {
    el.addEventListener('click', async () => {
      const reply = await (await fetch('/cast', {
        method: 'POST', body: el.dataset.cast })).text();
      const m = reply.match(/^rung (\d+)/);
      if (m) { closeStrata(); await travel(+m[1]); }
    });
  }
  bootGraphViews(body);
  bootIrViews(body);
}


function closePlace() {
  if (placeStack.length) { openPlace(placeStack.pop(), false); return; }
  leaveRoom();
}

