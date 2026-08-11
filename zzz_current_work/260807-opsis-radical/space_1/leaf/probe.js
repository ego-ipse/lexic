/* opsis leaf — the gesture probe — driving the real handlers.
   Carved verbatim from one file: order is load order, and every
   top-level binding stays in the global lexical environment the way it
   was, because the leaf is one program that lives in several files. */

'use strict';

/* ── the gesture probe: this instrument has never had one, so "does it
   work" was always the user's hand. ?probe drives the real handlers and
   writes the verdict into document.title, which dump-dom can read. */
async function probeGestures() {
  const out = [];
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const click = (el) => el && el.dispatchEvent(
    new MouseEvent('click', { bubbles: true, cancelable: true }));
  try {
    // the USER's path first: open the menu and click a room link there
    await openStrata();
    await wait(600);
    const link = document.querySelector('#strata .stRoom');
    out.push(`menuLink=${link ? link.textContent : 'MISSING'}`);
    click(link);
    await wait(700);
    out.push(`fromMenu room=${roomId} place=${currentPlace}`,
             `menuClosed=${!$('strata') || !$('strata').classList.contains('on')}`);
    await openPlace('v1i', false);
    await wait(400);
    out.push(`room=${roomId}`, `facets=${FACETS.join('+')}`,
             `placed=${[...document.querySelectorAll('#placeGrid > .facet')]
               .filter((e) => e.style.width).length}`,
             `seams=${seamEdges.length}`);
    const cand = document.querySelector('#placeGrid .paddr[data-place]');
    click(cand);
    await wait(500);
    out.push(`candidate->${currentPlace}`);
    const chip = [...document.querySelectorAll('#dock .fnode-chip')][1];
    click(chip);
    await wait(200);
    out.push(`dockToggle=${chip ? chip.dataset.name + ':' + facetOn[chip.dataset.name] : 'none'}`);
    click(chip);
    await wait(150);
    click($('placeBack'));
    await wait(500);
    out.push(`back->${currentPlace}`);
    const before = JSON.stringify(layoutTree);
    if (seamEdges.length) {
      const sm = seamEdges[0];
      const g = $(GRID).getBoundingClientRect();
      const px = g.left + (sm.axis === 'x' ? sm.at : (sm.from + sm.to) / 2);
      const py = g.top + (sm.axis === 'x' ? (sm.from + sm.to) / 2 : sm.at);
      // dispatch on the ELEMENT under the seam: a window-targeted event has
      // no .closest, which is the probe's bug, not the instrument's
      const target = document.elementFromPoint(px, py) || document.body;
      target.dispatchEvent(new PointerEvent('pointerdown',
        { clientX: px, clientY: py, bubbles: true, cancelable: true }));
      target.dispatchEvent(new PointerEvent('pointermove',
        { clientX: px + (sm.axis === 'x' ? 90 : 0),
          clientY: py + (sm.axis === 'x' ? 0 : 90), buttons: 1, bubbles: true }));
      target.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
      out.push(`seamTarget=${target.id || target.className || target.tagName}`);
      await wait(200);
      out.push(`seamDrag=${JSON.stringify(layoutTree) !== before}`);
    } else {
      out.push('seamDrag=NO-SEAMS');
    }
    // the ⧉ marks: each must open the surface that ASKED, not the graph
    const marks = [...document.querySelectorAll('.wantsWindow')];
    out.push(`marks=${marks.map((m) => m.textContent.trim().split(' ')[1]).join('+')
      || 'NONE'}`);
    const wm = marks.find((m) => m.textContent.includes('machine'));
    if (wm) {
      click(wm);
      await wait(700);
      out.push(`machineMark->${currentPlace}`);
    }
  } catch (err) {
    out.push(`THREW ${err && err.message}`);
  }
  document.title = 'PROBE ' + out.join(' | ');
}
if (new URLSearchParams(location.search).has('probe')) setTimeout(probeGestures, 1500);
