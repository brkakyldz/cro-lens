// Run page: follow the SSE stream, update the step rail and log, then swap the
// server-rendered report in place when the run ends (no reload).
(() => {
  const root = document.getElementById("run");
  if (!root || root.dataset.status !== "running") return;
  const runId = root.dataset.runId;
  const log = document.getElementById("log");
  const errBox = document.getElementById("run-error");
  const liveH = document.getElementById("live-h");
  let finished = false;

  const stepEl = (name) => document.querySelector(`[data-testid="step-${name}"]`);

  function onStep(d) {
    const el = stepEl(d.step);
    if (el) {
      el.dataset.status = d.status;
      if (d.seconds !== undefined) el.querySelector(".step-t").textContent = `${Number(d.seconds).toFixed(1)} s`;
      if (d.detail) el.querySelector(".step-detail").textContent = d.detail;
    }
    if (d.status === "started") return;
    const li = document.createElement("li");
    li.className = `log-${d.status}`;
    const parts = [
      ["log-step", d.step],
      ["log-d", d.detail || d.status],
      ["log-t", d.seconds !== undefined ? `${Number(d.seconds).toFixed(1)} s` : ""],
    ];
    for (const [cls, text] of parts) {
      const s = document.createElement("span");
      s.className = cls;
      s.textContent = text;
      li.appendChild(s);
    }
    log.appendChild(li);
  }

  async function showReport() {
    const resp = await fetch(`/runs/${encodeURIComponent(runId)}/report-fragment`, { cache: "no-store" });
    if (!resp.ok) throw new Error(`report fragment HTTP ${resp.status}`);
    const main = document.getElementById("run-main");
    main.innerHTML = await resp.text();
    document.getElementById("toc").hidden = false;
    const box = document.getElementById("steps-box");
    if (box) box.open = false;
    const done = document.getElementById("steps-done");
    if (done) done.textContent = " · all done";
    root.dataset.status = "done";
    const title = document.querySelector(".report-title");
    if (title) document.title = `${title.textContent} · cro-lens`;
    main.querySelector("#summary")?.scrollIntoView({ block: "start" });
  }

  const STEP_LABEL = { understand: "understand", analyse: "analyse", check: "self-check", hypotheses: "hypotheses", report: "report" };

  function showDelete() {
    const del = document.querySelector('.masthead [data-action="delete"]');
    if (del) del.hidden = false;
  }

  function showError(text, code, resumeFrom) {
    root.dataset.status = "failed";
    showDelete();
    if (liveH) liveH.hidden = true;
    errBox.innerHTML = "";
    const h = document.createElement("p");
    h.className = "run-error-h";
    h.textContent = `The run stopped${code ? ` (exit ${code})` : ""}.`;
    const line = document.createElement("p");
    line.className = "mono";
    line.textContent = text || "The run failed without an error line.";
    errBox.append(h, line);
    if (resumeFrom) {
      const actions = document.createElement("p");
      actions.className = "run-error-actions";
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-ink";
      btn.setAttribute("data-testid", "resume-button");
      btn.dataset.action = "resume";
      btn.dataset.runId = runId;
      btn.textContent = `Continue from ${STEP_LABEL[resumeFrom] || resumeFrom}`;
      const hint = document.createElement("span");
      hint.className = "hint";
      hint.textContent = "Uses the capture already taken; the page is not visited again.";
      actions.append(btn, hint);
      const actionErr = document.createElement("p");
      actionErr.className = "action-error form-error";
      actionErr.setAttribute("data-testid", "action-error");
      actionErr.setAttribute("role", "alert");
      actionErr.hidden = true;
      errBox.append(actions, actionErr);
    }
    const again = document.createElement("p");
    again.innerHTML = '<a href="/">Start another audit</a>';
    errBox.append(again);
    errBox.hidden = false;
  }

  async function onEnd(d) {
    finished = true;
    source.close();
    if (d.status === "done") {
      showDelete();
      try {
        await showReport();
      } catch (e) {
        showError(`The run finished but the report could not be loaded: ${e.message}`);
      }
      return;
    }
    let text = d.error;
    let code = d.exit_code;
    let resumeFrom = null;
    try {
      const resp = await fetch(`/api/runs/${encodeURIComponent(runId)}`, { cache: "no-store" });
      const body = await resp.json();
      if (body.error) text = body.error;
      if (body.exit_code) code = body.exit_code;
      resumeFrom = body.resume_from || null;
    } catch (e) {
      /* keep what the stream said */
    }
    showError(text, code, resumeFrom);
  }

  // Replayed events arrive again after a reconnect; the rail is idempotent, the log is reset.
  const source = new EventSource(`/api/runs/${encodeURIComponent(runId)}/events`);
  source.addEventListener("open", () => {
    log.innerHTML = "";
  });
  source.addEventListener("step", (e) => onStep(JSON.parse(e.data)));
  source.addEventListener("end", (e) => onEnd(JSON.parse(e.data)));
  source.addEventListener("error", () => {
    if (finished) source.close();
  });
})();
