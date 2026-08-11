/* opsis leaf — the painter.

   Five words, painted where they say. Everything about WHAT a picture is
   was decided by the reading; this decides nothing, which is the point: a
   surface that computes its own geometry is a surface no fact can reach.

   The register lives here because it is a look, not a meaning: a drawing
   names a tone, never a colour. */

'use strict';

const TONE = {
  rail: '#6fc3c9', loop: '#d98cf5', token: '#8fa3b8', ref: '#6fc3c9',
  class: '#d98cf5', name: '#e2a65c', dim: '#66707f', hot: '#e2a65c',
  cool: 'rgba(111,195,201,0.18)', seen: '#4a5568', dispatch: '#6fc3c9',
  span: '#2a3140', eps: '#3a4250', closed: '#6fc3c9', live: '#e2a65c',
  closedfill: '#10282e', livefill: '#3a2f18',
  alt: '#e2a65c', seq: '#8fa3b8', value_str: '#d98cf5', group: '#66707f',
};

const drawings = new Map();     // what → { marks, w, h }

function toneOf(name) { return TONE[name] || '#8fa3b8'; }

async function loadDrawing(key, query = '', what = key) {
  const text = await (await fetch(`/draw?what=${what}${query}`)).text();
  const lines = text.split('\n');
  const head = (lines[0] || '').split(' ');
  if (head[0] !== '#DRAW') return null;
  const said = {
    marks: lines.slice(1, 1 + (+head[1] || 0)),
    w: +head[3] || 0,
    h: +head[4] || 0,
  };
  drawings.set(key, said);
  ask();
  return said;
}

function doorAt(said, x, y, pan = { x: 0, y: 0 }, scale = 1) {
  // which door is under the pointer, in the drawing's own coordinates
  const dx = (x - pan.x) / scale, dy = (y - pan.y) / scale;
  return (said && said.hits || []).find(
    (h) => dx >= h.x && dx <= h.x + h.w && dy >= h.y && dy <= h.y + h.h);
}

function paint(cv, said, pan = { x: 0, y: 0 }, scale = 1, tint = null) {
  if (!cv || !said) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  // a canvas with no layout yet keeps its 300×150 default, and painting into
  // that silently cuts everything past the corner — which looks exactly like
  // a drawing that stops halfway
  // the ROOM decides, not the canvas: a canvas keeps its 300×150 default
  // until CSS lays it out, and reading that back (then writing it as an
  // inline style, as this did) locks the picture into the corner forever
  const host = cv.parentElement;
  const w = (host ? host.clientWidth : 0) || cv.clientWidth;
  const h = (host ? host.clientHeight : 0) || cv.clientHeight;
  if (!w || !h) return;
  if (cv.width !== w * dpr) { cv.width = w * dpr; cv.height = h * dpr; }
  const cx = cv.getContext('2d');
  cx.setTransform(dpr * scale, 0, 0, dpr * scale, dpr * pan.x, dpr * pan.y);
  cx.clearRect(-pan.x / scale, -pan.y / scale, w / scale, h / scale);
  cx.lineWidth = 1;
  const hits = [];
  said.hits = hits;
  cx.font = `11px ${getComputedStyle(document.documentElement)
    .getPropertyValue('--mono')}`;
  for (const mark of said.marks) {
    const p = mark.split(' ');
    if (p[0] === 'box') {
      const [x, y, bw, bh] = [+p[1], +p[2], +p[3], +p[4]];
      // a mark may be recoloured by the one thing the leaf owns — the
      // cursor it is moving. Where it IS never changes; what it is doing
      // right now does, and that is state, not derivation.
      const tone = tint ? tint(p[5], p[6]) : p[5];
      cx.strokeStyle = toneOf(tone);
      if (tone === 'closed' || tone === 'live') {
        cx.fillStyle = toneOf(tone === 'live' ? 'livefill' : 'closedfill');
        cx.fillRect(x, y, bw, bh);
      }
      cx.strokeRect(x + 0.5, y + 0.5, bw, bh);
      const label = p.slice(7).join(' ');
      if (label) {
        cx.fillStyle = toneOf(tone);
        cx.fillText(label, x + 5, y + bh / 2 + 4);
      }
      // a mark that carries an address is a DOOR: the leaf remembers where
      // it painted it and hit-tests rectangles. It knows nothing else.
      if (p[6] && p[6] !== '-') hits.push({ x, y, w: bw, h: bh, goes: p[6] });
    } else if (p[0] === 'line') {
      cx.strokeStyle = toneOf(p[5]);
      cx.beginPath();
      cx.moveTo(+p[1], +p[2]);
      cx.lineTo(+p[3], +p[4]);
      cx.stroke();
    } else if (p[0] === 'curve') {
      cx.strokeStyle = toneOf(p[7]);
      cx.beginPath();
      cx.moveTo(+p[1], +p[2]);
      cx.quadraticCurveTo(+p[3], +p[4], +p[5], +p[6]);
      cx.stroke();
    } else if (p[0] === 'bez') {
      cx.strokeStyle = toneOf(p[9]);
      cx.beginPath();
      cx.moveTo(+p[1], +p[2]);
      cx.bezierCurveTo(+p[3], +p[4], +p[5], +p[6], +p[7], +p[8]);
      cx.stroke();
    } else if (p[0] === 'arc') {
      cx.fillStyle = toneOf(p[4]);
      cx.beginPath();
      cx.arc(+p[1], +p[2], +p[3], 0, Math.PI * 2);
      cx.fill();
    } else if (p[0] === 'text') {
      cx.fillStyle = toneOf(p[3]);
      cx.fillText(p.slice(4).join(' '), +p[1], +p[2]);
    }
  }
}
