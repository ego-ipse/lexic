/* The probe — what can only be wrong IN a leaf, checked by the leaf.

   gate.py drives the composer and reads the frame; it cannot see whether a
   mark landed where the frame said, whether a text plane sits on the geometry
   it was given, or whether a character is the width the server believes.
   This can, because it is standing in the browser looking at the result.

   Two rules, both paid for:

   - Nothing is measured after a call that has not been awaited. An earlier
     harness scheduled through requestAnimationFrame, which headless Chrome
     does not fire under --virtual-time-budget, so every "verified"
     measurement read a stale canvas. `ask()` is awaited here, always.
   - A verdict goes in document.title, so --dump-dom reads it without
     screenshots or timing.

   Loaded only for ?probe=1. */

'use strict';

const said = [];

function fact(name, held, note) {
  said.push(`${held ? 'ok' : 'FAIL'} ${name}${note ? ` (${note})` : ''}`);
}

function near(a, b, slack) {
  return Math.abs(a - b) <= (slack === undefined ? 1.5 : slack);
}

/* the colour a tone actually paints, as the canvas holds it */
function at(x, y) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const d = paper.getContext('2d').getImageData(x * dpr, y * dpr, 1, 1).data;
  return `${d[0]},${d[1]},${d[2]}`;
}

function rgbOf(css) {
  const m = css.match(/^#(..)(..)(..)$/);
  return m ? `${parseInt(m[1], 16)},${parseInt(m[2], 16)},${parseInt(m[3], 16)}` : css;
}

async function probe() {
  await ask('');

  /* 1. the canvas is the size of its element — never stretched into it */
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  fact('the canvas is sized to its element',
       paper.width === Math.round(paper.clientWidth * dpr)
       && paper.height === Math.round(paper.clientHeight * dpr),
       `${paper.width}x${paper.height} for ${paper.clientWidth}x${paper.clientHeight}@${dpr}`);

  /* 1b. AND ITS BOX IS THE BOX IT WAS PUT IN. A canvas is a replaced element:
     it has an intrinsic size, so `inset: 0` does not stretch it and its
     LAYOUT size becomes its bitmap size. At 1× the two coincide and nothing
     looks wrong; at 2× the canvas lays out twice as large as the room it
     sits in, the drawing goes with it, and anything positioned in CSS pixels
     — every text plane, every chip — stays behind. This is measured against
     the window rather than against the canvas's own numbers, because its own
     numbers are exactly what is wrong when this breaks. */
  for (const [name, el] of [['paper', paper], ['over', over]]) {
    const box = el.getBoundingClientRect();
    fact(`the ${name} canvas lays out in the room it was put in`,
         Math.abs(box.width - window.innerWidth) < 2
         && Math.abs(box.height - window.innerHeight) < 2,
         `${Math.round(box.width)}x${Math.round(box.height)} `
         + `in ${window.innerWidth}x${window.innerHeight} @${dpr}`);
  }

  /* 2. every text plane sits exactly on the geometry it was given */
  let placed = 0, wrong = '';
  for (const plane of frame.planes) {
    const el = held.get(plane.name);
    if (!el) { wrong += `${plane.name} missing `; continue; }
    const box = el.getBoundingClientRect();
    if (near(box.left, plane.x) && near(box.top, plane.y)
        && near(box.width, plane.w) && near(box.height, plane.h)) placed += 1;
    else wrong += `${plane.name} at ${Math.round(box.left)},${Math.round(box.top)}`
      + ` not ${Math.round(plane.x)},${Math.round(plane.y)} `;
  }
  fact('every text plane sits on the geometry it was sent',
       placed === frame.planes.length && frame.planes.length > 0,
       wrong || `${placed} planes`);

  /* 3. THE GLYPH GEOMETRY IS THE SERVER'S BELIEF — is it true?
     Every highlight the frame draws under the text is placed with these two
     numbers. If the browser disagrees, the drawing is under the wrong
     characters and no amount of looking at it will say why. */
  const plane = frame.planes[0];
  const el = held.get(plane.name);
  const face = getComputedStyle(el).font;
  const cx = paper.getContext('2d');
  cx.font = face;
  const wide = cx.measureText('0'.repeat(100)).width / 100;
  fact('a character is the width the frame believes', near(wide, plane.cell, 0.25),
       `browser ${wide.toFixed(3)} · frame ${plane.cell}`);
  const line = parseFloat(getComputedStyle(el).lineHeight);
  fact('a line is the height the frame believes', near(line, plane.row, 0.5),
       `browser ${line} · frame ${plane.row}`);

  /* 4. a mark lands where the frame put it */
  const box = frame.marks.map((m) => m.split(' '))
    .find((p) => p[0] === 'box' && +p[3] > 30 && +p[4] > 8 && frame.fills[p[5]]
                 && frame.fills[p[5]].startsWith('#'));
  if (box) {
    const got = at(+box[1] + (+box[3]) / 2, +box[2] + (+box[4]) / 2);
    fact('a box paints where the frame put it, in the tone it named',
         got === rgbOf(frame.fills[box[5]]),
         `${box[5]} wanted ${rgbOf(frame.fills[box[5]])} got ${got}`);
  } else {
    fact('a box paints where the frame put it, in the tone it named', false, 'no box to sample');
  }

  /* 5. landing on a hit changes what is SHOWN — a count that could stay the
        same is a fact that cannot fail, which is worse than no fact */
  const named = () => frame.marks.filter((m) => m.startsWith('text ')
    && m.split(' ')[3] === 'ftitle').map((m) => m.split(' ').slice(6).join(' ')).join('|');
  /* a tab that is ALREADY showing is not a test of anything: take the last
     one in the strip, which is never the first one being shown */
  const tabs = (frame.hits || []).filter((h) => h.kind === 'tab');
  const tab = tabs.length > 1 ? tabs[tabs.length - 1] : null;
  const before = named();
  if (tab) {
    await ask(`at tab ${tab.goes}`);
    fact('landing on a tab changes which facet is shown', named() !== before,
         `${before} → ${named()}`);
    await ask(`at tab ${tab.goes.split(':')[0]}:0`);
  } else {
    fact('landing on a tab changes which facet is shown', false, 'no tab to land on');
  }

  /* 6. what must be read OVER the text is actually over it. The planes are
        real elements, so a canvas painted behind them is a banner nobody can
        read — which is exactly what a refusal was until this existed. */
  const planes = document.getElementById('planes');
  const lifted = +getComputedStyle(over).zIndex || 0;
  const under = +getComputedStyle(planes).zIndex || 0;
  fact('what is drawn over the text is above the text',
       lifted > under && over.compareDocumentPosition(planes) === 2,
       `over z=${lifted} · planes z=${under}`);
  fact('the over canvas takes no pointer of its own',
       getComputedStyle(over).pointerEvents === 'none');

  /* 7. the leaf keeps no answer of its own about what is running. It kept
        one, and starting playback from the transport — a gesture this never
        sees — drove nothing at all. */
  fact('the leaf holds no play state of its own',
       !/\blet playing\b/.test(paperSource) && /frame && frame\.running/.test(paperSource));

  /* 8. nothing is scheduled through a frame callback — the reason an earlier
        harness measured a canvas that had not been drawn yet */
  fact('the leaf paints without waiting for an animation frame',
       !/requestAnimationFrame/.test(paperSource), 'leaf.js');

  const bad = said.filter((s) => s.startsWith('FAIL')).length;
  document.title = `PROBE ${bad} failures :: ${said.join(' :: ')}`;
}

let paperSource = '';
fetch('/leaf.js').then((r) => r.text()).then((t) => { paperSource = t; return probe(); });
