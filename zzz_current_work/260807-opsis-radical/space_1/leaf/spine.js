/* opsis leaf — the spine, and grammar co-selection.
   Carved verbatim from one file: order is load order, and every
   top-level binding stays in the global lexical environment the way it
   was, because the leaf is one program that lives in several files. */

'use strict';

/* ── spine facet ── */

let lastSpineKey = '';
let colCache = new Map();
let colWaiting = false;

async function fetchColumn(i) {
  if (colCache.has(i) || colWaiting) return;
  colWaiting = true;
  try {
    const text = await (await fetch('/column?i=' + i)).text();
    if (!text.startsWith('#COLUMN')) { colWaiting = false; return; }
    const items = [], expect = [];
    let section = 'c';
    for (const ln of text.split('\n').slice(1)) {
      if (ln.startsWith('#EXPECT')) { section = 'e'; continue; }
      if (section === 'c') {
        const m = ln.match(/^(\d+) (\S+) (.*)$/);
        if (m) items.push({ origin: +m[1], role: m[2], rule: m[3] });
      } else if (ln) expect.push(ln);
    }
    colCache.set(i, { items, expect });
  } catch { /* retry on next cursor move */ }
  colWaiting = false;
  ask();
}

function spineClock(head) {
  $('spineHead').textContent = head;
}

function drawPdaSpine() {
  const body = $('spineBody');
  const closedBody = $('closedBody');
  if (!clockReady()) {
    spineClock('the PDA at t — clock running…');
    body.innerHTML = '<div class="none">the pda clock is still running</div>';
    closedBody.textContent = '';
    return;
  }
  if (!clockData.frames.length) {
    spineClock('the PDA — no machine');
    body.innerHTML = '<div class="none">the PDA never ran'
      + (clockData.pdaWords ? ': ' + clockData.pdaWords : '')
      + (S.meta.resolver === '1' ? ' · the reading came from Earley + the supplied resolver' : '')
      + ' · the earley clock tells this subject\'s time</div>';
    $('closedHead').textContent = 'DECISIONS';
    closedBody.innerHTML = '<div class="none">none — there is no machine to decide</div>';
    return;
  }
  spineClock("the PDA's stack at t");
  const t = cur.t;
  const open = clockData.frames.filter((f) => f.s <= t && t < f.e && f.ok).sort((a, b) => a.d - b.d);
  const probing = clockData.frames.filter((f) => f.s <= t && t < f.e && !f.ok);
  body.textContent = '';
  if (!open.length) {
    body.innerHTML = '<div class="none">no frame open — a frameless leaf run carries this stretch</div>';
  }
  open.forEach((f, k) => {
    const row = document.createElement('div');
    row.className = 'row' + (k === open.length - 1 ? ' deep' : '');
    row.innerHTML = `<span class="d">d${f.d}</span>${f.name} <span class="f">${f.s.toLocaleString()}..${f.e.toLocaleString()}</span>`;
    body.appendChild(row);
  });
  if (probing.length) {
    const row = document.createElement('div');
    row.className = 'none';
    row.textContent = `+ ${probing.length} probe frame${probing.length === 1 ? '' : 's'} here — pushed by the attempt machinery, rolled back (red in the lanes)`;
    body.appendChild(row);
  }
  closedBody.textContent = '';
  $('closedHead').textContent = 'DECISIONS';
  const evs = clockData.events.filter((e) => e.pos <= t).slice(-7);
  if (!clockData.events.length) {
    closedBody.innerHTML = '<div class="none">none — the whole walk is deterministic descent;'
      + ' the automaton view shows where decisions COULD arise</div>';
  }
  for (const e of evs) {
    const row = document.createElement('div');
    row.className = 'row' + (Math.abs(e.pos - t) < 2 ? ' fresh' : '');
    row.innerHTML = `<span class="d">@${e.pos}</span>${e.kind} <span class="f">${e.detail}</span>`;
    closedBody.appendChild(row);
  }
}

function drawEarleySpine() {
  const i = Math.min(Math.floor(cur.t), S.doc.length);
  const col = colCache.get(i);
  const body = $('spineBody');
  const closedBody = $('closedBody');
  if (!col) {
    fetchColumn(i);
    spineClock(`Earley column ${i} — loading…`);
    return;
  }
  spineClock(`Earley column ${i} — ${col.items.length} items`);
  body.textContent = '';
  if (!col.items.length) {
    body.innerHTML = '<div class="none">empty — inside a lexical run; the kernel scanned past this column</div>';
  }
  for (const it of col.items.slice(0, 40)) {
    const row = document.createElement('div');
    row.className = 'row role-' + it.role;
    row.innerHTML = `<span class="d">@${it.origin}</span><span class="dr">${it.rule}</span>`
      + `<span class="f">${it.role}</span>`;
    body.appendChild(row);
  }
  if (col.items.length > 40) {
    const row = document.createElement('div');
    row.className = 'none';
    row.textContent = `+${col.items.length - 40} more items`;
    body.appendChild(row);
  }
  $('closedHead').textContent = 'CAN COME NEXT';
  closedBody.textContent = '';
  for (const term of col.expect) {
    const chip = document.createElement('span');
    chip.className = 'echip';
    chip.textContent = term;
    closedBody.appendChild(chip);
  }
  if (!col.expect.length) closedBody.innerHTML = '<div class="none">nothing — every item is complete</div>';
}

function drawSpine() {
  if (chartClock === 'pda') { lastSpineKey = ''; drawPdaSpine(); return; }
  if (chartClock === 'earley') { lastSpineKey = ''; drawEarleySpine(); return; }
  spineClock('open at the cursor');
  $('closedHead').textContent = 'JUST CLOSED';
  const open = openAt(cur.t);
  const key = open.join(',') + '|' + Math.floor(cur.t);
  if (key === lastSpineKey) return;
  lastSpineKey = key;
  const body = $('spineBody');
  body.textContent = '';
  if (!open.length) body.innerHTML = '<div class="none">nothing open — before the first span, or complete</div>';
  open.forEach((i, k) => {
    const s = S.spans[i];
    const row = document.createElement('div');
    row.className = 'row' + (k === open.length - 1 ? ' deep' : '');
    row.dataset.i = i;
    row.innerHTML = `<span class="d">d${s.d}</span>${S.ruleNames[s.r]} <span class="f">${s.s.toLocaleString()}..${s.e.toLocaleString()}</span>`;
    body.appendChild(row);
  });
  const closedBody = $('closedBody');
  closedBody.textContent = '';
  const done = S.byEnd.filter((i) => S.spans[i].e <= cur.t).slice(-7);
  done.forEach((i) => {
    const s = S.spans[i];
    const snip = S.doc.slice(s.s, s.e).replace(/\n/g, '↵');
    const row = document.createElement('div');
    row.className = 'row' + (cur.t - s.e < 3 ? ' fresh' : '');
    row.dataset.i = i;
    row.innerHTML = `<span class="d">d${s.d}</span>${S.ruleNames[s.r]}  '${snip.length > 22 ? snip.slice(0, 21) + '…' : snip}'`;
    closedBody.appendChild(row);
  });
}

/* ── grammar facet co-selection ── */

function litRules() {
  const selRule = cur.sel >= 0 ? S.ruleNames[S.spans[cur.sel].r] : null;
  const selDef = selRule ? ruleDef(selRule) : null;
  const curDef = cur.rule ? ruleDef(cur.rule) : null;
  const hotDef = hotRule() ? ruleDef(hotRule()) : null;
  document.querySelectorAll('#grammarBody .ln').forEach((ln) => {
    const i = +ln.dataset.l;
    const inDef = (d) => d && d.a <= i && i <= d.b;
    ln.classList.toggle('lit', inDef(selDef) || inDef(curDef));
    ln.classList.toggle('hot', inDef(hotDef));
  });
  const target = selDef || hotDef || curDef;
  if (target) {
    const ln = document.querySelector(`#grammarBody .ln[data-l="${target.a}"]`);
    if (ln) ln.scrollIntoView({ block: 'nearest' });
  }
}
