// Grading findings on a finished report (ui@2 § Grading, eval@2).
// Event delegation: the report is injected into the page when a live run ends.
(() => {
  "use strict";

  const runId = () => {
    const el = document.querySelector('[data-testid="grade-progress"]');
    return el ? el.dataset.runId : null;
  };

  function progress() {
    const box = document.querySelector('[data-testid="grade-progress"] [data-graded]');
    if (!box) return;
    const n = document.querySelectorAll('[data-testid="finding-card"]:not([data-grade=""])').length;
    box.textContent = String(n);
  }

  function show(card, verdict) {
    card.dataset.grade = verdict || "";
    card.querySelectorAll(".grade-btn").forEach((b) => {
      b.setAttribute("aria-pressed", b.dataset.verdict === verdict ? "true" : "false");
    });
    progress();
  }

  function status(card, text) {
    const s = card.querySelector(".grade-status");
    if (s) s.textContent = text;
  }

  async function save(card, verdict) {
    const id = runId();
    const fid = card.dataset.findingId;
    if (!id || !fid) return;
    const url = `/api/runs/${encodeURIComponent(id)}/grades/${encodeURIComponent(fid)}`;
    const note = (card.querySelector(".grade-note") || {}).value || "";
    const before = card.dataset.grade || "";
    card.setAttribute("aria-busy", "true");
    try {
      const resp = verdict
        ? await fetch(url, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ verdict, note }),
          })
        : await fetch(url, { method: "DELETE" });
      if (!resp.ok && !(resp.status === 404 && !verdict)) {
        let msg = `HTTP ${resp.status}`;
        try {
          msg = (await resp.json()).error || msg;
        } catch (_) {}
        throw new Error(msg);
      }
      show(card, verdict);
      status(card, verdict ? "Saved" : "Cleared");
    } catch (e) {
      show(card, before);
      status(card, `Not saved: ${e.message}`);
    } finally {
      card.removeAttribute("aria-busy");
    }
  }

  document.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".grade-btn");
    if (!btn) return;
    const card = btn.closest('[data-testid="finding-card"]');
    if (!card) return;
    // a second click on the selected verdict removes the grade
    save(card, card.dataset.grade === btn.dataset.verdict ? null : btn.dataset.verdict);
  });

  document.addEventListener(
    "change",
    (ev) => {
      const input = ev.target.closest(".grade-note");
      if (!input) return;
      const card = input.closest('[data-testid="finding-card"]');
      if (card && card.dataset.grade) save(card, card.dataset.grade);
    },
    true,
  );

  document.addEventListener("keydown", (ev) => {
    if (ev.key !== "Enter") return;
    const input = ev.target.closest && ev.target.closest(".grade-note");
    if (input) input.blur(); // blur fires "change" when the text changed
  });
})();
