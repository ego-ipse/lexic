/* opsis leaf — the two text planes — grammar and document.
   Carved verbatim from one file: order is load order, and every
   top-level binding stays in the global lexical environment the way it
   was, because the leaf is one program that lives in several files. */

'use strict';

/* ── build the two text facets ── */

function buildCode(host, textLines, gutter) {
  host.textContent = '';
  const frag = document.createDocumentFragment();
  textLines.forEach((line, i) => {
    const div = document.createElement('div');
    div.className = 'ln';
    div.dataset.l = i;
    if (gutter) {
      const g = document.createElement('span');
      g.className = 'g';
      g.textContent = i + 1;
      div.appendChild(g);
    }
    const t = document.createElement('span');
    t.className = 't';
    t.textContent = line;
    div.appendChild(t);
    frag.appendChild(div);
  });
  host.appendChild(frag);
}

function measure() {
  const doc = $('docText');
  const cs = getComputedStyle(doc);
  const probe = document.createElement('span');
  probe.textContent = 'M'.repeat(40);
  probe.style.position = 'absolute';
  probe.style.visibility = 'hidden';
  probe.style.whiteSpace = 'pre';
  probe.style.fontFamily = cs.fontFamily;
  probe.style.fontSize = cs.fontSize;
  probe.style.letterSpacing = cs.letterSpacing;
  document.body.appendChild(probe);
  M = { charW: probe.getBoundingClientRect().width / 40, gutterW: doc.offsetLeft };
  probe.remove();
}

function buildGutter(n) {
  const g = $('gutter');
  g.textContent = '';
  const frag = document.createDocumentFragment();
  for (let i = 1; i <= n; i++) {
    const d = document.createElement('div');
    d.textContent = i;
    frag.appendChild(d);
  }
  g.appendChild(frag);
}

function setStale(on) {
  for (const id of ['chart', 'spine', 'grammar']) $(id).classList.toggle('stale', on);
}

function sizeDocCanvases() {
  const wrap = $('docWrap');
  const w = wrap.scrollWidth, h = wrap.scrollHeight;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  for (const cv of [$('under'), $('over')]) {
    cv.width = w * dpr; cv.height = h * dpr;
    cv.style.width = w + 'px'; cv.style.height = h + 'px';
    cv.getContext('2d').setTransform(dpr, 0, 0, dpr, 0, 0);
  }
}

/* ── document plane drawing ── */

function segRects(s, e, l0, l1, fn) {
  for (let line = Math.max(lineOf(s), l0); line <= Math.min(lineOf(Math.max(s, e - 1)), l1); line++) {
    const a = Math.max(s, S.lineStarts[line]);
    const b = Math.min(e, (S.lineStarts[line + 1] ?? S.doc.length + 1) - 1);
    if (b < a) continue;
    const c0 = a - S.lineStarts[line], c1 = b - S.lineStarts[line];
    fn(M.gutterW + c0 * M.charW, PAD_TOP + line * LH, Math.max((c1 - c0) * M.charW, 3), LH);
  }
}

function visibleLines() {
  const sc = $('docScroll');
  const l0 = Math.max(0, Math.floor((sc.scrollTop - PAD_TOP) / LH) - 2);
  const l1 = Math.min(S.lineStarts.length - 1, Math.ceil((sc.scrollTop + sc.clientHeight) / LH) + 2);
  return [l0, l1];
}

function drawUnder() {
  const cx = $('under').getContext('2d');
  cx.clearRect(0, 0, 1e6, 1e6);
  if (dirty) return;
  const [l0, l1] = visibleLines();
  for (const i of openAt(cur.t)) {
    cx.fillStyle = 'rgba(111,195,201,0.045)';
    segRects(S.spans[i].s, S.spans[i].e, l0, l1, (x, y, w, h) => cx.fillRect(x, y, w, h));
  }
  if (markedRule()) {
    cx.strokeStyle = C.violet;
    for (const [i, s] of S.spans.entries()) {
      if (S.ruleNames[s.r] !== markedRule()) continue;
      segRects(s.s, s.e, l0, l1, (x, y, w, h) => cx.strokeRect(x + 0.5, y + 1.5, w - 1, h - 3));
    }
  }
  if (cur.hover >= 0 && cur.hover !== cur.sel) {
    const s = S.spans[cur.hover];
    cx.fillStyle = 'rgba(102,112,127,0.16)';
    segRects(s.s, s.e, l0, l1, (x, y, w, h) => cx.fillRect(x, y, w, h));
  }
  if (cur.sel >= 0) {
    const s = S.spans[cur.sel];
    cx.fillStyle = 'rgba(226,166,92,0.12)';
    cx.strokeStyle = C.warm;
    segRects(s.s, s.e, l0, l1, (x, y, w, h) => { cx.fillRect(x, y, w, h); cx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1); });
  }
}

function frontierMark(cx) {
  if (cur.frontier < 0) return;
  const sts = cur.fstarts || S.lineStarts;
  let lo = 0, hi = sts.length - 1;
  while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (sts[mid] <= cur.frontier) lo = mid; else hi = mid - 1; }
  const fx = M.gutterW + (cur.frontier - sts[lo]) * M.charW;
  const fy = PAD_TOP + lo * LH;
  cx.fillStyle = C.red;
  cx.shadowColor = C.red; cx.shadowBlur = 8;
  cx.fillRect(fx - 1, fy, 2, LH);
  cx.fillRect(fx - 4, fy + LH - 2, Math.max(M.charW + 8, 12), 2);
  cx.shadowBlur = 0;
}

function drawOver() {
  const cx = $('over').getContext('2d');
  cx.clearRect(0, 0, 1e6, 1e6);
  if (dirty) { frontierMark(cx); return; }
  const wrap = $('docWrap');
  const t = Math.min(cur.t, S.doc.length);
  const line = lineOf(Math.min(Math.floor(t), S.doc.length - 1));
  const x = M.gutterW + (Math.floor(t) - S.lineStarts[line]) * M.charW;
  const y = PAD_TOP + line * LH;
  cx.fillStyle = 'rgba(11,14,20,0.60)';
  cx.fillRect(x, y, wrap.scrollWidth - x, LH);
  if (y + LH < wrap.scrollHeight) cx.fillRect(0, y + LH, wrap.scrollWidth, wrap.scrollHeight - y - LH);
  cx.fillStyle = C.warm;
  cx.shadowColor = C.warm; cx.shadowBlur = 6;
  cx.fillRect(x - 1, y, 2, LH);
  cx.shadowBlur = 0;
  frontierMark(cx);
}
