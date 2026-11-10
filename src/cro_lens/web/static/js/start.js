// Start screen: POST /api/runs, then go to the run page. A refused URL stays here.
(() => {
  const form = document.getElementById("start-form");
  const err = document.getElementById("form-error");
  const url = document.getElementById("url");
  const button = form.querySelector("[data-testid=start-button]");

  const showError = (msg) => {
    err.textContent = msg;
    err.hidden = false;
    url.setAttribute("aria-invalid", "true");
    url.focus();
  };

  url.addEventListener("input", () => {
    err.hidden = true;
    url.removeAttribute("aria-invalid");
  });

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const value = url.value.trim();
    if (!/^https?:\/\/[^\s/]+/i.test(value)) {
      showError("Enter a full web address that starts with http:// or https://.");
      return;
    }
    const body = { url: value, model: form.model.value };
    for (const k of ["audience", "traffic", "goal"]) {
      const v = form[k].value.trim();
      if (v) body[k] = v;
    }
    if (form.feedback && !form.feedback.checked) body.feedback = false;
    button.disabled = true;
    button.textContent = "Starting…";
    try {
      const resp = await fetch("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await resp.json().catch(() => ({}));
      if (resp.status === 202 && data.run_id) {
        window.location.assign(`/runs/${encodeURIComponent(data.run_id)}`);
        return;
      }
      showError(data.error || `The server refused the run (HTTP ${resp.status}).`);
    } catch (e) {
      showError("Could not reach the cro-lens server. Is `cro-lens ui` still running?");
    }
    button.disabled = false;
    button.textContent = "Run the audit";
  });
})();
