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
    // AN EDIT MOVES EVERYTHING. Every derived surface is a function of the
    // text; after a re-read only the model used to come back new, so the
    // clocks, the automaton and the graph kept answering for the old text.
    await loadClock();
    await fetchAutomaton();
    await wait(900);
    const was = {
      gen: S.meta.generation,
      spans: S.spans.length,
      frames: (clockData && clockData.frames.length) || 0,
      clones: (autoData && autoData.clones.length) || 0,
      len: S.doc.length,
    };
    const put = '\n  "opsis-probe": [1, 2, 3],';
    const reply = await (await fetch('/edit', { method: 'POST',
      body: `1 1\n${put}` })).text();
    await boot(true);
    await wait(900);
    await loadClock();
    await fetchAutomaton();
    await wait(1800);
    const now = {
      gen: S.meta.generation,
      spans: S.spans.length,
      frames: (clockData && clockData.frames.length) || 0,
      clones: (autoData && autoData.clones.length) || 0,
      len: S.doc.length,
    };
    out.push(`edit=${reply.split('\n')[0]}`,
      `docLen ${was.len}->${now.len}`,
      `gen ${was.gen}->${now.gen}`,
      `spans ${was.spans}->${now.spans}`,
      `pdaFrames ${was.frames}->${now.frames}`,
      `clones ${was.clones}->${now.clones}`);
    // put the document back the way it was found
    // put the document back EXACTLY: an off-by-one here leaves a character
    // behind on every run, and the fixture drifts
    await (await fetch('/edit', { method: 'POST',
      body: `1 ${1 + put.length}\n` })).text();
    await boot(true);
    await wait(700);
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
    // the painter: what did it actually receive, and how big is its canvas
    const tabForPaint = [...document.querySelectorAll('#grid .tabbar .tab')]
      .find((el) => el.textContent === 'relations');
    click(tabForPaint);
    await wait(700);
    gView = 'rails';
    if (gViews[0]) switchViewMode(gViews[0], 'depth3d', 'rails');
    await loadDrawing('rails');
    await wait(600);
    drawGraph();
    await wait(300);
    const railSaid = drawings.get('rails');
    out.push(`railMarks=${railSaid ? railSaid.marks.length : 'NONE'}`,
      `railSize=${railSaid ? railSaid.w + 'x' + railSaid.h : '-'}`,
      `railCanvas=${$('graphCv').clientWidth}x${$('graphCv').clientHeight}`,
      `railBitmap=${$('graphCv').width}x${$('graphCv').height}`,
      `railWrap=${$('graphWrap').clientWidth}x${$('graphWrap').clientHeight}`);
    gView = 'depth3d';
    if (gViews[0]) switchViewMode(gViews[0], 'rails', 'depth3d');
    // the relations must be the ACTIVE tab or there is nothing to measure:
    // a hidden facet has no size, and a view with no size draws nothing
    const relFirst = [...document.querySelectorAll('#grid .tabbar .tab')]
      .find((el) => el.textContent === 'relations');
    click(relFirst);
    await wait(700);
    // a slider is configuration: dragging it must change what the READING
    // sends back, not something the leaf keeps to itself
    const dial = $('gt-ringscale');
    const wasPlaces = gNodes ? [...gNodes.values()][1] : null;
    if (dial && wasPlaces) {
      dial.value = String(Math.min(2, (parseFloat(dial.value) || 1) + 0.5));
      dial.dispatchEvent(new Event('input', { bubbles: true }));
      await wait(1200);
      const nowPlaces = [...gNodes.values()][1];
      out.push(`tuneMoved=${Math.abs(nowPlaces.x - wasPlaces.x) > 1
        || Math.abs(nowPlaces.y - wasPlaces.y) > 1}`);
      dial.value = '1';
      dial.dispatchEvent(new Event('input', { bubbles: true }));
      await wait(1000);
    }
    // ROTATING MUST NOT RESIZE. The scale is the layout's and the room's;
    // the camera's angle is not allowed a vote.
    gView = 'depth3d';
    if (gViews[0]) {
      const v3 = gViews[0];
      const scales = [], offAt = [], drawnAt = [];
      for (const yaw of [0, 0.6, 1.2, 2.0, 3.1]) {
        v3.yaw = yaw;
        drawGraph();
        await wait(120);
        scales.push(+(v3.fitScale || 0).toFixed(4));
        // what the EYE sees: the drawn extent of the labels, which is what
        // "the image zooms in and out" is actually about
        const boxes = [...$('graphChips').children]
          .filter((c) => c.style.display !== 'none')
          .map((c) => c.getBoundingClientRect());
        if (boxes.length) {
          const wSpan = Math.max(...boxes.map((r) => r.right))
            - Math.min(...boxes.map((r) => r.left));
          const hSpan = Math.max(...boxes.map((r) => r.bottom))
            - Math.min(...boxes.map((r) => r.top));
          drawnAt.push(Math.round(Math.max(wSpan, hSpan)));
        }
        const b = $('graphWrap').getBoundingClientRect();
        offAt.push([...$('graphChips').children].filter((c) => {
          if (c.style.display === 'none') return false;
          const r = c.getBoundingClientRect();
          return r.right > b.right + 1 || r.left < b.left - 1
            || r.bottom > b.bottom + 1 || r.top < b.top - 1;
        }).length);
      }
      const spread = Math.max(...scales) - Math.min(...scales);
      out.push(`rotateScale=${scales.join('/')} spread=${spread.toFixed(4)}`,
        `rotateClipped=${offAt.join('/')}`,
        `rotateDrawn=${drawnAt.join('/')} swing=${
          drawnAt.length ? Math.round(100 * (Math.max(...drawnAt) - Math.min(...drawnAt))
            / Math.max(...drawnAt)) : 0}%`);
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
    // playing, in the automaton view: the transport must work wherever you
    // are standing, and time must light every view, not only this one
    // first in the DEFAULT view, so a frozen clock here means the harness,
    // not the instrument
    cur.t = 0;
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true }));
    await wait(700);
    out.push(`plainPlay=${cur.playing} t=${Math.round(cur.t)}`);
    cur.playing = false;
    gView = 'automaton';
    if (gViews[0]) switchViewMode(gViews[0], 'depth3d', 'automaton');
    drawGraph();
    await wait(600);
    cur.t = 0;
    document.body.dispatchEvent(new KeyboardEvent('keydown',
      { key: ' ', bubbles: true }));
    await wait(900);
    const ticks = [];
    for (let i = 0; i < 4; i++) { await wait(300); ticks.push(Math.round(cur.t)); }
    out.push(`autoPlay=${cur.playing} t=${ticks.join('/')}`);
    cur.playing = false;
    cur.t = 4000;
    ask();
    await wait(400);
    // the relations must be the ACTIVE tab before its chips can light: a
    // hidden facet has no width, and a view with no width draws nothing
    const relTab = [...document.querySelectorAll('#grid .tabbar .tab')]
      .find((el) => el.textContent === 'relations');
    click(relTab);
    await wait(700);
    drawGraph();
    await wait(300);
    out.push(`tab=${relTab ? relTab.textContent : 'NONE'}`,
      `liveAtT=${[...liveRules()].length} rules`,
      `chips=${document.querySelectorAll('#graphChips .gchip').length}`,
      `graphBox=${$('graphWrap').clientWidth}x${$('graphWrap').clientHeight}`,
      `mode=${gView} t=${Math.round(cur.t)}`,
      `litChips=${document.querySelectorAll('#graphChips .gchip.live').length}`,
      `litRules=${document.querySelectorAll('#grammarBody .ln.live').length}`);
    gView = 'depth3d';
    if (gViews[0]) switchViewMode(gViews[0], 'automaton', 'depth3d');
    drawGraph();
    // pop a facet out, and clone one: both must be REAL — the section moves
    // into the window, and the clone keeps drawing what its source draws
    // a TABBED facet is the hard case: popping it must take its tab with it
    popFacet('graph');
    await wait(600);
    const tabsNow = [...document.querySelectorAll('#grid .tabbar .tab')]
      .map((el) => el.textContent);
    out.push(`poppedTab=${!!document.querySelector('.facetwin #graph')}`,
      `tabsLeft=${tabsNow.join('+') || 'none'}`,
      `readerBox=${Math.round($('grammar').getBoundingClientRect().width)}`);
    document.querySelector('.facetwin .x').dispatchEvent(
      new PointerEvent('pointerdown', { bubbles: true }));
    document.querySelector('.facetwin .x').click();
    await wait(700);
    // and again: a facet that came back must be able to leave again
    popFacet('graph');
    await wait(500);
    const twice = !!document.querySelector('.facetwin #graph');
    if (twice) document.querySelector('.facetwin .x').click();
    await wait(600);
    out.push(`popTwice=${twice}`,
      `popBtnHidden=${(($('graph').querySelector('h2 .fpop')) || {}).hidden}`,
      `tabsBack=${[...document.querySelectorAll('#grid .tabbar .tab')]
      .map((el) => el.textContent).join('+') || 'none'}`,
      `graphBack=${!!document.querySelector('#grid > #graph')}`);
    popFacet('chart');
    await wait(600);
    const inWin = document.querySelector('.facetwin .winbody > #chart');
    out.push(`popped=${!!inWin} visible=${inWin
      ? getComputedStyle(inWin).display !== 'none' : false}`);
    // a cloned chart is a REAL second view: its own moment, drawing on its own
    cur.t = 3000;
    cloneFacet('chart');
    await wait(700);
    const twinView = chartTwins[chartTwins.length - 1];
    cur.t = 9000;
    ask();
    await wait(500);
    drawChartTwins();
    out.push(`chartTwin=${!!twinView}`,
      `twinT=${twinView ? Math.round(twinView.view.t) : -1} mainT=${Math.round(cur.t)}`,
      `twinCanvas=${twinView ? twinView.view.cv.width + 'x' + twinView.view.cv.height : 'NONE'}`,
      `mainHit=${S.chartHit ? Math.round(S.chartHit.at) : -1} twinHit=${
        twinView && twinView.view.hit ? Math.round(twinView.view.hit.at) : -1}`);
    cloneFacet('spine');
    await wait(500);
    drawTwins();
    out.push(`cloned=${document.querySelectorAll('.facetwin').length}`,
      `mirror=${(document.querySelector('.winbody.mirror') || {}).textContent
        ? 'has content' : 'EMPTY'}`);
    // closing the window is the SAME as docking it: the facet must come
    // back whole — in the grid, sized by the layout, drawing again
    document.querySelector('.facetwin .x').click();
    await wait(700);
    const back = $('chart');
    const box = back.getBoundingClientRect();
    const cv2 = $('chartCv');
    out.push(`docked=${!!document.querySelector('#grid > #chart')}`,
      `backBox=${Math.round(box.width)}x${Math.round(box.height)}`,
      `backCanvas=${cv2.width}x${cv2.height}`,
      `backStyle=${back.style.display || 'shown'}`,
      `inTree=${JSON.stringify(layoutTree).includes('chart')}`,
      `stillInWin=${back.classList.contains('inwin')}`);
    for (const win of document.querySelectorAll('.facetwin')) win.remove();
    twins.length = 0;
    await wait(300);
    // the pipeline room: a step must actually SEND the reader to that form
    await openPlace('pipeline', false);
    await wait(700);
    const steps = [...document.querySelectorAll('#placeGrid .paddr[data-form]')];
    const wasText = S.reader.length;
    out.push(`pipeline=${steps.map((el) => el.dataset.form).join('+') || 'NONE'}`);
    const codegenStep = steps.find((el) => el.dataset.form === 'codegen');
    click(codegenStep);
    await wait(1600);
    out.push(`formNow=${S.policy['form']} readerChars ${wasText}->${S.reader.length}`,
      `hasArm=${/-arm\d/.test(S.reader)}`);
    const sourceStep = [...document.querySelectorAll('#placeGrid .paddr[data-form]')]
      .find((el) => el.dataset.form === 'source');
    click(sourceStep);
    await wait(1600);
    out.push(`formBack=${S.policy['form']}`);
    if (currentPlace) click($('placeBack'));
    await wait(400);
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
    // every facet carries its own doors: float it, or open a second one.
    // This replaced the "x needs a window" marks, which diagnosed a problem
    // and then sent every surface to the same place.
    const doors = (S.facets || []).map((f) => {
      const head = document.querySelector(`#${f.name} h2`);
      return head ? head.querySelectorAll('.fpop').length : 0;
    });
    out.push(`doors=${doors.join('/')} on ${(S.facets || []).length} facets`);
  } catch (err) {
    out.push(`THREW ${err && err.message}`);
  }
  document.title = 'PROBE ' + out.join(' | ');
}
if (new URLSearchParams(location.search).has('probe')) setTimeout(probeGestures, 1500);
