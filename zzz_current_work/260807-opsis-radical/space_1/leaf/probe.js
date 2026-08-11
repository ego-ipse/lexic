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
    await openPlace('ir:reducer', false);
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
    // leave the rooms ENTIRELY before testing the layout: a seam drag inside
    // a room measures the room's grid, which has no seams, and reads as a
    // regression in the instrument rather than a mistake in the probe
    for (let i = 0; i < 6 && currentPlace; i++) {
      click($('placeBack'));
      await wait(320);
    }
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
    // the relations: nothing may hang off the edge of its own facet
    const wrap = $('graphWrap');
    if (wrap) {
      const box = wrap.getBoundingClientRect();
      const chips = [...$('graphChips').children].filter((c) => c.style.display !== 'none');
      const out_ = chips.filter((c) => {
        const r = c.getBoundingClientRect();
        return r.left < box.left - 1 || r.right > box.right + 1
          || r.top < box.top - 1 || r.bottom > box.bottom + 1;
      });
      out.push(`graphChips=${chips.length} clipped=${out_.length}`
        + (out_.length ? ` first=${out_[0].dataset.name}` : ''));
    }
    // ... and in every mode, not just the one it booted in
    for (const mode of ['flat', 'arcs']) {
      gView = mode;
      if (gViews[0]) { switchViewMode(gViews[0], 'depth3d', mode); }
      drawGraph();
      await wait(400);
      const box2 = $('graphWrap').getBoundingClientRect();
      const bad = [...$('graphChips').children].filter((c) => {
        if (c.style.display === 'none') return false;
        const r = c.getBoundingClientRect();
        return r.right > box2.right + 1 || r.bottom > box2.bottom + 1
          || r.left < box2.left - 1 || r.top < box2.top - 1;
      });
      out.push(`${mode}Clipped=${bad.length}`);
    }
    gView = 'depth3d';
    drawGraph();
    // the strata, clicked TWICE: up then back down. One card's worth of
    // missing stats used to throw mid-render and everything after the first
    // stratum vanished, which reads as "only the first layer is shown".
    await openStrata();
    await wait(700);
    const cards = () => [...document.querySelectorAll('#strata .stCard[data-i]')];
    out.push(`strataCards=${cards().length}`);
    click(cards()[1]);
    await wait(2600);
    await openStrata();
    await wait(700);
    out.push(`afterClimb=${cards().length} focus=${
      (document.querySelector('#strata .stCard.on') || {}).dataset?.i}`,
      `stats=${cards().map((c) => (c.querySelector('.stK') || {}).textContent
        ? 'has' : 'NONE').join('+')}`);
    click(cards()[0]);
    await wait(2200);
    await openStrata();
    await wait(700);
    out.push(`afterDescend=${cards().length} focus=${
      (document.querySelector('#strata .stCard.on') || {}).dataset?.i}`);
    closeStrata();
    await wait(300);
    // the chart's hand: what is UNDER the pointer must be what lights. The
    // hit test and the draw compute the same geometry twice, so they can
    // disagree — and a picture that highlights the wrong thing is worse
    // than one that highlights nothing.
    const cv = $('chartCv');
    if (cv && S.chartHit) {
      const r = cv.getBoundingClientRect(), H = S.chartHit;
      const seen = S.spans.filter((s) => s.s >= view0 && s.e <= view0 + H.win
        && s.e > s.s + 2 && s.d >= 2);
      const want = seen[Math.floor(seen.length / 2)];
      if (want) {
        const px = r.left + H.pad + ((want.s + want.e) / 2 - view0) * H.pitch;
        const py = r.top + H.lanesY + want.d * H.laneH + H.laneH / 2;
        cv.dispatchEvent(new MouseEvent('mousemove',
          { clientX: px, clientY: py, bubbles: true }));
        await wait(250);
        const got = S.spans[cur.hover];
        out.push(`chartHover=${got === want ? 'same'
          : `MISMATCH want d${want.d} ${want.s}..${want.e} got `
            + (got ? `d${got.d} ${got.s}..${got.e}` : 'NONE')}`);
      }
    }
    // and again right after the layout MOVES: a hit test reading geometry
    // the draw has since recomputed points at where things used to be
    if (cv && S.chartHit) {
      facetOn['grammar'] = !facetOn['grammar'];
      applyFacets();
      const r2 = cv.getBoundingClientRect(), H2 = S.chartHit;
      const seen2 = S.spans.filter((s) => s.s >= view0 && s.e <= view0 + H2.win
        && s.e > s.s + 2 && s.d >= 3);
      const want2 = seen2[Math.floor(seen2.length / 3)];
      if (want2) {
        cv.dispatchEvent(new MouseEvent('mousemove', {
          clientX: r2.left + H2.pad + ((want2.s + want2.e) / 2 - view0) * H2.pitch,
          clientY: r2.top + H2.lanesY + want2.d * H2.laneH + H2.laneH / 2,
          bubbles: true }));
        await wait(250);
        const got2 = S.spans[cur.hover];
        out.push(`afterResize=${got2 === want2 ? 'same'
          : `MISMATCH want d${want2.d} ${want2.s}..${want2.e} got `
            + (got2 ? `d${got2.d} ${got2.s}..${got2.e}` : 'NONE')}`);
      }
      facetOn['grammar'] = !facetOn['grammar'];
      applyFacets();
    }
    // a rule's own room: reached the way a person reaches it — through the
    // rules list — and it must carry BOTH its graph and its value
    await openPlace('rules', false);
    await wait(600);
    const rlink = document.querySelector('#placeGrid .paddr[data-place^="rule:"]');
    out.push(`rulesRoom=${currentPlace} first=${rlink ? rlink.dataset.place : 'NONE'}`);
    click(rlink);
    await wait(1100);
    const gv = document.querySelector('.gview canvas');
    out.push(`ruleRoom=${currentPlace}`,
             `ruleGraph=${gv ? gv.width + 'x' + gv.height : 'NONE'}`,
             `ruleIr=${document.querySelectorAll('.irv .irrow').length}`);
    // the value room: the IR surface must actually DRAW, and zoom must move
    await openPlace('ir:grammar', false);
    await wait(900);
    const irv = document.querySelector('.irv');
    const rows = irv ? irv.querySelectorAll('.irrow').length : 0;
    out.push(`irRoom=${currentPlace} rows=${rows}`,
             `irHead=${irv ? (irv.querySelector('.irhead b') || {}).textContent : 'NONE'}`);
    const kid = irv && [...irv.querySelectorAll('.irrow')][1];
    if (kid) {
      click(kid);
      await wait(700);
      out.push(`irZoom=${(irv.querySelector('.irhead b') || {}).textContent}`);
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
