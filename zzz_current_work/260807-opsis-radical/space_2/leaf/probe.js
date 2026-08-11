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

/* A GESTURE IS APPLIED WHEN THE FRAME ANSWERING IT HAS BEEN PAINTED, and
   `ask` resolves as soon as it has QUEUED — which is not the same thing, and
   is not the same thing in exactly the case a probe creates: a control that
   fires its own un-awaited ask, followed by one of ours. The queue runs
   detached, so waiting on our own call proves nothing. Wait for quiet. */
async function settle() {
  for (let i = 0; i < 400 && (asking || queued); i += 1) {
    await new Promise((go) => setTimeout(go, 5));
  }
  await ask('');
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

  /* 1c. AND IT FOLLOWS ITS BOX. A canvas that keeps yesterday's bitmap is a
     picture CSS is stretching: space_1's chart sits in a 431px box holding a
     503px bitmap — 14% squashed — because only its pinned windows observe
     their size. Here every layout change arrives as a FRAME, so the size is
     re-measured on the way in. This shrinks the page and checks that. */
  paper.style.height = '520px';
  await ask('');
  const after = paper.getBoundingClientRect();
  fact('a canvas follows its box when the box changes',
       Math.abs(after.height - 520) < 2
       && paper.height === Math.round(after.height * dpr),
       `box ${Math.round(after.height)} · bitmap ${paper.height} @${dpr}`);
  paper.style.height = '';
  await ask('');

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

  /* 9. a dropdown is a REAL control, on the geometry it was sent, showing
        what it is on. A chip that cycles cannot be arrowed through, cannot
        show what else there is, and cannot be got back from without going
        all the way round — which is why these are selects. */
  let picked = 0, off = '';
  for (const pick of frame.picks) {
    const el = document.querySelector(`.pick[data-key="${pick.key}"]`);
    if (!el) { off += `${pick.key} missing `; continue; }
    const box = el.getBoundingClientRect();
    if (el.tagName === 'SELECT' && el.value === pick.on
        && el.options.length === pick.options.length
        && near(box.left, pick.x) && near(box.top, pick.y)) picked += 1;
    else off += `${pick.key} ${el.tagName} ${el.value}/${pick.on} `
      + `${Math.round(box.left)},${Math.round(box.top)} not ${pick.x},${pick.y} `;
  }
  fact('every dropdown is a real select, where it was placed, on its value',
       picked === frame.picks.length && frame.picks.length > 0,
       off || `${picked} picks`);

  /* 9b. AND CHANGING ONE CHANGES THE INSTRUMENT. A control that reports
         nowhere is a picture of a control. */
  const clock = document.querySelector('.pick[data-key="chart.clock"]');
  if (clock && clock.options.length > 1) {
    const was = clock.value;
    const other = [...clock.options].map((o) => o.value).find((v) => v !== was);
    clock.value = other;
    clock.dispatchEvent(new Event('change'));
    await settle();
    const now = document.querySelector('.pick[data-key="chart.clock"]');
    fact('changing a dropdown changes what the instrument shows',
         now && now.value === other, `${was} → ${now ? now.value : 'gone'}`);
    now.value = was;
    now.dispatchEvent(new Event('change'));
    await settle();
  } else {
    fact('changing a dropdown changes what the instrument shows', false, 'no clock pick');
  }

  /* 10. a window is IN the page: a rectangle over the arrangement, not a
         browser window, which is a different document and cannot overlap
         the thing it was torn from. */
  const head = (frame.hits || []).find((h) => h.kind === 'pop');
  if (head) {
    const opened = window.open;
    let asked = false;
    window.open = () => { asked = true; return null; };
    await ask(`pop ${head.goes}`);
    await settle();
    window.open = opened;
    fact('popping a facet opens no browser window',
         !asked && frame.hits.some((h) => h.kind === 'winhead'),
         `${frame.hits.filter((h) => h.kind === 'winhead').length} windows in the page`);
    /* and put it back: this probe runs twice, and a fact that only passes
       because the run before it left something behind is not a fact */
    const shut = frame.hits.find((h) => h.kind === 'shut');
    if (shut) { await ask(`at shut ${shut.goes}`); await settle(); }
    await ask(`at facet ${head.goes}`);
    await settle();
  } else {
    fact('popping a facet opens no browser window', false, 'nothing to pop');
  }

  /* EVERY OTHER FACE. The mono plane is checked above because a highlight
     sits under its characters; nothing has ever checked the sans faces, and
     the frame wraps the hint, right-aligns the verdict and packs every head
     from what it believes they measure. Too wide and a line wraps early; too
     narrow and two things overlap.

     Guarded, because a fact that throws takes the whole harness down with it
     and a probe that says nothing is worse than a gap it names. */
  try {
    /* each face measured on what it actually SETS: a title is uppercase and
       tracked out, a subtitle is a sentence, a chip is one word */
    const samples = { fsub: 'the chart scrubs and select text to co-select',
                      ftitle: 'THE DERIVATION THE DOCUMENT THE READER',
                      chip: 'derivation relations document' };
    const gauge = paper.getContext('2d');
    let off = '';
    const measured = [];
    for (const name of ['fsub', 'ftitle', 'chip']) {
      const sample = samples[name];
      const believed = +(frame.advance || {})[name];
      if (!believed || !frame.fonts[name]) continue;
      gauge.font = frame.fonts[name];
      gauge.letterSpacing = (frame.tracks || {})[name] || '0px';
      const real = gauge.measureText(sample).width / sample.length;
      gauge.letterSpacing = '0px';
      /* REPORTED EVERY TIME, not only when it fails. A tolerance wide
         enough to pass is still wide enough to move a wrap by a dozen
         characters, and the only way to set these exactly is to see them. */
      measured.push(`${name} ${real.toFixed(2)}/${believed}`);
      if (Math.abs(real - believed) > 0.7) off += `${name} ${real.toFixed(2)}/${believed} `;
    }
    fact('every face is the width the frame believes', !off, measured.join(' · '));
  } catch (e) {
    fact('every face is the width the frame believes', false, `threw: ${e.message}`);
  }

  const bad = said.filter((s) => s.startsWith('FAIL')).length;
  document.title = `PROBE ${bad} failures :: ${said.join(' :: ')}`;
}

let paperSource = '';
fetch('/leaf.js').then((r) => r.text()).then((t) => { paperSource = t; return probe(); });
