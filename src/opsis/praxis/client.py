"""The session's own gestures, as the script the page runs.

Window chrome, wires, folding and deixis belong to the camera
(:mod:`opsis.opsis.draw.space`); neither script registers the other's
listeners. What is here is everything about READINGS — opening a file,
typing into one, dropping one on another, running a deed, and the
refresh that puts the answer back on screen.

Kept beside the routes it calls rather than inside them: a route and
the gesture that fires it are two halves of one thing.
"""

from __future__ import annotations

__all__ = ["CLIENT"]

CLIENT = r"""
"use strict";
function toast(message) {
  const old = document.querySelector(".toast");
  if (old) old.remove();
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = message;
  t.addEventListener("click", () => t.remove());
  document.body.appendChild(t);
}
let framed = true;
// A window's body is built when it opens, not when the page is drawn:
// a self-grammar's predictive tables cost fifty seconds, and nobody
// should pay that for a window they never opened.
function fill(frame) {
  const slot = frame.querySelector("[data-pane], [data-rail]");
  if (!slot || slot.dataset.filled) return;
  slot.dataset.filled = "1";
  slot.textContent = "…";
  const where = slot.dataset.pane
    ? "/pane/" + slot.dataset.pane
    : "/rail/" + encodeURIComponent(slot.dataset.rail);
  fetch(where)
    .then(r => r.text().then(t => {
      if (r.ok) { slot.innerHTML = t; return; }
      slot.innerHTML = "";
      const bad = document.createElement("div");
      bad.className = "refusal";
      bad.textContent = t;
      slot.appendChild(bad);
    }))
    .catch(e => { slot.textContent = String(e); });
}
window.opsisFill = fill;
function refresh() {
  // Swapping #world throws every window body away, because bodies are
  // built when they open. So what was open is re-opened and re-filled,
  // and the caret is put back only once its field exists again —
  // otherwise typing into a text window would delete the text window.
  const a = document.activeElement;
  const held = a && a.id && (a.tagName === "TEXTAREA" || a.tagName === "INPUT")
    ? {id: a.id, s: a.selectionStart, e: a.selectionEnd, top: a.scrollTop} : null;
  const open = [...document.querySelectorAll("#world .frame")]
    .filter(f => f.style.display !== "none")
    .map(f => ({name: f.dataset.frame, geo: f.getAttribute("style"),
                placed: f.dataset.placed}));
  return fetch("/world").then(r => r.text()).then(w => {
    const cam = window.opsisCamera.snapshot();
    document.getElementById("world").innerHTML = w;
    window.opsisCamera.restore(cam);
    if (!framed) { framed = true; window.opsisCamera.fit(90); }
    open.forEach(was => {
      const f = document.querySelector(
        `#world .frame[data-frame="${CSS.escape(was.name)}"]`);
      if (!f) return;
      if (was.placed) { f.setAttribute("style", was.geo); f.dataset.placed = "1"; }
      f.style.display = "flex";
      fill(f);
    });
    window.opsisCamera.draw();
    if (held) restore(held);
  });
}
// The field is only there once its window has been filled, and filling
// is a fetch — so this waits for it rather than assuming.
function restore(held, tries = 20) {
  const el = document.getElementById(held.id);
  if (!el) {
    if (tries) setTimeout(() => restore(held, tries - 1), 25);
    return;
  }
  el.focus();
  if (el.setSelectionRange) el.setSelectionRange(held.s, held.e);
  el.scrollTop = held.top;
}
const posted = r => r.ok ? refresh() : r.text().then(toast);
function browse(at) {
  fetch("/files?at=" + encodeURIComponent(at)).then(r => r.text()).then(text => {
    const rows = document.getElementById("rows");
    const where = document.getElementById("where");
    rows.textContent = "";
    where.textContent = at ? at + "/" : "the workspace";
    text.split("\n").filter(Boolean).forEach(line => {
      const [kind, path, name, size] = line.split("\t");
      const row = document.createElement("div");
      row.className = "prow" + (kind === "dir" ? " dir" : "");
      row.appendChild(document.createTextNode(name));
      if (size) {
        const tag = document.createElement("em");
        tag.textContent = size;
        row.appendChild(tag);
      }
      row.addEventListener("click", () => {
        if (kind === "dir") { browse(path); return; }
        fetch("/open", {method: "POST", body: path}).then(r => {
          if (!r.ok) return r;
          framed = false;
          document.querySelector('.frame[data-frame="picker"]').style.display = "none";
          return r;
        }).then(posted);
      });
      rows.appendChild(row);
    });
  });
}
// ── reading as you type ──
const pending = new Map();
// The width slider is a control, not a setting: it re-renders the one
// document it belongs to, live, and each document keeps its own.
document.addEventListener("input", e => {
  const slider = e.target.closest("[data-width]");
  if (!slider) return;
  const win = slider.closest(".frame");
  const slot = win.querySelector("[data-pane]");
  if (!slot) return;
  const ident = slot.dataset.pane.split("/")[0];
  clearTimeout(pending.get("width" + ident));
  pending.set("width" + ident, setTimeout(() => {
    fetch("/width/" + ident, {method: "POST", body: slider.value})
      .then(() => { delete slot.dataset.filled; fill(win); });
  }, 60));
});
document.addEventListener("input", e => {
  const field = e.target.closest("[data-post]");
  if (!field) return;
  const win = field.closest(".frame");
  const area = win.querySelector("textarea[data-post]");
  if (!area) return;
  const route = area.dataset.post;
  clearTimeout(pending.get(route));
  pending.set(route, setTimeout(() => {
    pending.delete(route);
    const start = win.querySelector('input[id^="c-start-"]');
    const ns = win.querySelector('input[id^="c-ns-"]');
    const q = new URLSearchParams();
    const res = document.querySelector('input[id^="c-res-"]');
    if (res && res.value.trim()) q.set("resolver", res.value.trim());
    if (start && start.value.trim()) q.set("start", start.value.trim());
    if (ns && ns.value.trim()) q.set("non_semantic", ns.value.trim());
    const qs = q.toString();
    fetch(route + (qs ? "?" + qs : ""), {method: "POST", body: area.value})
      .then(posted);
  }, 450));
});
// ── the bar: a picker, new texts, a frozen artifact ──
let ghost = null;
document.addEventListener("pointerdown", e => {
  const src = e.target.closest(".bnode[data-spawn]");
  if (!src) return;
  e.preventDefault();
  ghost = src.cloneNode(true);
  ghost.classList.add("ghost");
  ghost.dataset.kind = src.dataset.spawn;
  document.body.appendChild(ghost);
  ghost.style.left = (e.clientX - 30) + "px";
  ghost.style.top = (e.clientY - 20) + "px";
});
addEventListener("pointermove", e => {
  if (!ghost) return;
  ghost.style.left = (e.clientX - 30) + "px";
  ghost.style.top = (e.clientY - 20) + "px";
});
addEventListener("pointerup", e => {
  if (!ghost) return;
  const kind = ghost.dataset.kind;
  ghost.remove(); ghost = null;
  if (e.target.closest(".frame, .bar")) { toast("drop it on the canvas"); return; }
  fetch("/new", {method: "POST", body: kind}).then(posted);
});
document.addEventListener("click", e => {
  const go = e.target.closest("[data-do]");
  if (go) {
    go.disabled = true;
    go.textContent = "…";
    const win = go.closest(".frame");
    const field = win.querySelector("[data-push]");
    const sh = win.querySelector('input[id^="sh-"]');
    const sp = win.querySelector('textarea[id^="sp-"]');
    let where = go.dataset.do;
    if (sh || sp) {
      const q = new URLSearchParams();
      if (sh) q.set("shape", sh.value);
      if (sp) q.set("spec", sp.value);
      where += "?" + q.toString();
    }
    fetch(where, {method: "POST", body: field ? field.value : ""})
      .then(r => r.text().then(t => { toast(t); return r.ok ? refresh() : null; }));
    return;
  }
  const act = e.target.closest("[data-act]");
  if (act) {
    if (act.dataset.act === "picker") {
      const f = window.opsisCamera.toggle("picker");
      if (f && f.style.display !== "none") browse("");
    }
    if (act.dataset.act === "freeze") freeze();
    if (act.dataset.act === "reflect") {
      fetch("/reflect", {method: "POST", body: ""}).then(posted);
    }
    return;
  }
  const ring = e.target.closest(".nd.ring[data-reading]");
  const off = e.target.closest(".act.unplug");
  const gone = e.target.closest(".act.remove");
  if (off && ring) {
    fetch("/unplug/" + ring.dataset.reading, {method: "POST", body: ""}).then(posted);
  } else if (gone && ring) {
    fetch("/remove/" + ring.dataset.reading, {method: "POST", body: ""}).then(posted);
  }
});
// ── dropping one node on another ──
window.opsisLanding = (el, cx, cy) => {
  for (const hit of document.elementsFromPoint(cx, cy)) {
    const node = hit.closest(".nd.ring[data-reading]");
    if (node && node !== el) return node;
  }
  return null;
};
window.opsisDrop = (el, cx, cy) => {
  const onto = window.opsisLanding(el, cx, cy);
  if (!onto) return;
  fetch(`/drop/${el.dataset.reading}/${onto.dataset.reading}`,
        {method: "POST", body: ""}).then(posted);
};
// ── freezing: the page as it stands, and the session that made it ──
function save(text, name, type) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], {type}));
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}
function freeze() {
  const clone = document.documentElement.cloneNode(true);
  clone.querySelector("body").classList.add("frozen");
  save("<!DOCTYPE html>" + clone.outerHTML, "opsis.html", "text/html");
  // The picture and the session are different artifacts: one is what
  // it looked like, one is what it WAS. Opening the second thaws.
  fetch("/freeze", {method: "POST", body: ""}).then(r => r.text()).then(text => {
    save(text, "opsis.session.ir", "text/plain");
    toast("froze · the page, and the session file that reads back");
  });
}
// ── text ↔ tree: a node lights the span it covers ──
document.addEventListener("pointerover", e => {
  const row = e.target.closest(".twig[data-from]");
  if (!row) return;
  const pane = row.closest(".twin");
  const target = pane && pane.querySelector(".target");
  if (!target) return;
  if (target.dataset.plain === undefined) target.dataset.plain = target.textContent;
  const text = target.dataset.plain;
  const a = +row.dataset.from, b = +row.dataset.to;
  target.textContent = "";
  target.appendChild(document.createTextNode(text.slice(0, a)));
  const lit = document.createElement("mark");
  lit.textContent = text.slice(a, b);
  target.appendChild(lit);
  target.appendChild(document.createTextNode(text.slice(b)));
});
// ── trees open and shut ──
document.addEventListener("click", e => {
  const twig = e.target.closest(".twig.kids b");
  if (!twig) return;
  const row = twig.closest(".twig");
  const shut = !row.classList.contains("shut");
  row.classList.toggle("shut", shut);
  twig.textContent = shut ? "▸" : "▾";
  const prefix = row.dataset.path + ".";
  row.parentElement.querySelectorAll(".twig").forEach(other => {
    if (!other.dataset.path.startsWith(prefix)) return;
    if (shut) { other.classList.add("hide"); return; }
    const rest = other.dataset.path.slice(prefix.length).split(".");
    let path = row.dataset.path, visible = true;
    for (const step of rest.slice(0, -1)) {
      path += "." + step;
      const mid = row.parentElement.querySelector(`.twig[data-path="${path}"]`);
      if (mid && mid.classList.contains("shut")) { visible = false; break; }
    }
    other.classList.toggle("hide", !visible);
  });
});
// ── the bar itself drags ──
const bar = document.getElementById("bar");
bar.addEventListener("pointerdown", e => {
  if (e.target.closest("[data-act], [data-spawn]")) return;
  const r = bar.getBoundingClientRect();
  bar.style.left = r.left + "px"; bar.style.top = r.top + "px";
  bar.style.bottom = "auto"; bar.style.transform = "none";
  const sx = e.clientX - r.left, sy = e.clientY - r.top;
  const move = ev => {
    bar.style.left = (ev.clientX - sx) + "px";
    bar.style.top = (ev.clientY - sy) + "px";
  };
  const up = () => {
    removeEventListener("pointermove", move);
    removeEventListener("pointerup", up);
  };
  addEventListener("pointermove", move);
  addEventListener("pointerup", up);
});
"""
"""The session's own gestures. Window chrome, wires, folding and deixis
belong to the camera; neither script registers the other's listeners."""
