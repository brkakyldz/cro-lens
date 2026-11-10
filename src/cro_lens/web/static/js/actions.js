// Run actions shared by the start and run pages: delete, continue (resume) and run again.
// Buttons carry data-action; clicks are delegated so buttons added later by run.js work too.
(() => {
  const errorBox = (btn) =>
    btn.closest(".run-error")?.querySelector("[data-testid=action-error]") ||
    document.getElementById("form-error");

  const showError = (btn, msg) => {
    const box = errorBox(btn);
    if (box) {
      box.textContent = msg;
      box.hidden = false;
    } else {
      window.alert(msg);
    }
  };

  async function send(method, url, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const resp = await fetch(url, opts);
    const data = resp.status === 204 ? {} : await resp.json().catch(() => ({}));
    return { resp, data };
  }

  // Two clicks on the button itself instead of window.confirm(): embedded browsers (an IDE or app
  // pane) can suppress native dialogs, and confirm() then returns false, so the button did nothing.
  function disarm(btn) {
    if (!btn.dataset.armed) return;
    delete btn.dataset.armed;
    btn.textContent = btn.dataset.label;
    btn.removeAttribute("aria-live");
    clearTimeout(Number(btn.dataset.timer));
  }

  async function onDelete(btn) {
    if (!btn.dataset.armed) {
      btn.dataset.label = btn.textContent;
      btn.dataset.armed = "1";
      btn.setAttribute("aria-live", "polite");
      btn.textContent = "Click again to delete for good";
      btn.title = "Removes the report, screenshots and crops from disk. This cannot be undone.";
      btn.dataset.timer = String(setTimeout(() => disarm(btn), 5000));
      return;
    }
    disarm(btn);
    btn.disabled = true;
    const { resp, data } = await send("DELETE", `/api/runs/${encodeURIComponent(btn.dataset.runId)}`);
    if (resp.status === 204) {
      if (btn.dataset.after) {
        window.location.assign(btn.dataset.after);
        return;
      }
      const row = btn.closest("tr");
      const body = row?.parentElement;
      row?.remove();
      if (body && !body.children.length) window.location.reload();
      return;
    }
    btn.disabled = false;
    showError(btn, data.error || `Could not delete the audit (HTTP ${resp.status}).`);
  }

  async function onResume(btn) {
    btn.disabled = true;
    const label = btn.textContent;
    btn.textContent = "Continuing…";
    const id = btn.dataset.runId;
    const { resp, data } = await send("POST", `/api/runs/${encodeURIComponent(id)}/resume`, {});
    if (resp.status === 202) {
      window.location.assign(`/runs/${encodeURIComponent(id)}`);
      return;
    }
    btn.disabled = false;
    btn.textContent = label;
    showError(btn, data.error || `Could not continue the audit (HTTP ${resp.status}).`);
  }

  async function onRerun(btn) {
    btn.disabled = true;
    const body = { url: btn.dataset.url, model: btn.dataset.model || "sonnet" };
    for (const k of ["audience", "traffic", "goal"]) if (btn.dataset[k]) body[k] = btn.dataset[k];
    const { resp, data } = await send("POST", "/api/runs", body);
    if (resp.status === 202 && data.run_id) {
      window.location.assign(`/runs/${encodeURIComponent(data.run_id)}`);
      return;
    }
    btn.disabled = false;
    showError(btn, data.error || `Could not start the audit (HTTP ${resp.status}).`);
  }

  const handlers = { delete: onDelete, resume: onResume, rerun: onRerun };
  document.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-action]");
    if (!btn || !handlers[btn.dataset.action]) return;
    ev.preventDefault();
    handlers[btn.dataset.action](btn).catch(() => {
      btn.disabled = false;
      showError(btn, "Could not reach the cro-lens server. Is `cro-lens ui` still running?");
    });
  });

  // One sign-in notice: what happened, whether it matters, and the steps that make it go away.
  function noticeEl(n) {
    const el = (tag, cls, text) => {
      const e = document.createElement(tag);
      if (cls) e.className = cls;
      if (text != null) e.textContent = text;
      return e;
    };
    const wrap = el("section", "notice-item");
    if (n.code) wrap.dataset.code = n.code;
    wrap.appendChild(el("p", "notice-h", n.title || "Before you run an audit"));
    wrap.appendChild(el("p", "notice-text", n.text || ""));
    if ((n.steps || []).length || (n.commands || []).length) {
      const how = el("details", "notice-fix");
      how.open = true;
      how.appendChild(el("summary", null, "How to fix it"));
      if ((n.steps || []).length) {
        const ol = el("ol", "notice-steps");
        for (const s of n.steps) ol.appendChild(el("li", null, s));
        how.appendChild(ol);
      }
      if ((n.commands || []).length) {
        const dl = el("dl", "notice-cmds");
        for (const c of n.commands) {
          dl.appendChild(el("dt", null, c.label));
          const dd = el("dd");
          dd.appendChild(el("code", "mono", c.command));
          dl.appendChild(dd);
        }
        how.appendChild(dl);
      }
      const more = el("p", "notice-more");
      more.append("Details: ");
      const a = el("a", null, "README → Signing in");
      a.href = "https://github.com/brkakyldz/cro-lens#signing-in";
      a.target = "_blank";
      a.rel = "noopener";
      more.appendChild(a);
      how.appendChild(more);
      wrap.appendChild(how);
    }
    return wrap;
  }

  // Start page: say up front when the model provider (Claude Code) is not signed in.
  const warn = document.getElementById("provider-warning");
  if (warn) {
    fetch("/api/provider", { cache: "no-store" })
      .then((r) => r.json())
      .then((d) => {
        if (d.ready) {
          // e.g. an API key that bills every call, or a rejected token cro-lens worked around
          const box = document.getElementById("provider-notice");
          const list = document.getElementById("provider-notices");
          if (!box || !list || !(d.notices || []).length) return;
          for (const n of d.notices) list.appendChild(noticeEl(n));
          box.hidden = false;
          return;
        }
        document.getElementById("provider-error").textContent = d.error || "The model provider is not ready.";
        warn.hidden = false;
      })
      .catch(() => {});
  }
})();
