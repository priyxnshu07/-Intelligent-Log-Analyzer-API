// All log-derived text is untrusted. It is only ever shown with textContent.
(function () {
  "use strict";
  const API = (window.LOGDOCTOR_API || "").replace(/\/$/, "");
  const $ = (id) => document.getElementById(id);
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const fmt = (iso) => (iso ? iso.replace("T", " ") : "unknown time");

  function showError(message) {
    const box = $("error");
    box.textContent = message;
    box.style.display = message ? "block" : "none";
  }

  function setBusy(busy) {
    $("analyze").disabled = busy;
    $("busy").textContent = busy ? "Analyzing..." : "";
  }

  async function send(url, init) {
    setBusy(true);
    showError("");
    try {
      const response = await fetch(url, init);
      let body = null;
      try { body = await response.json(); } catch (e) { /* not JSON */ }
      if (!response.ok) {
        showError(body && body.error ? body.error.message : "Something went wrong (" + response.status + ").");
        return;
      }
      render(body, true);
    } catch (e) {
      showError("Could not reach the server. If this is the free hosting, it may be waking up: wait a minute and try again.");
    } finally {
      setBusy(false);
    }
  }

  function analyzeText() {
    const text = $("text").value;
    if (!text.trim()) { showError("Paste a log first, or upload a file."); return; }
    send(API + "/api/analyze/text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text }),
    });
  }

  function analyzeFile(file) {
    send(API + "/api/analyze/file?filename=" + encodeURIComponent(file.name), { method: "POST", body: file });
  }

  function stat(label, value) {
    const box = el("div", "stat");
    box.appendChild(el("b", "", String(value)));
    box.appendChild(el("span", "muted", label));
    return box;
  }

  function renderTimeline(timeline) {
    const holder = $("timeline");
    holder.replaceChildren();
    const note = $("timeline-note");
    if (!timeline.has_timestamps || !timeline.buckets.length) {
      note.textContent = "No timestamps were found, so there is no timeline.";
      return;
    }
    const max = Math.max(1, ...timeline.buckets.map((b) => b.errors + b.warnings));
    for (const bucket of timeline.buckets) {
      const bar = el("div", "bar");
      bar.title = fmt(bucket.start) + ": " + bucket.errors + " errors, " + bucket.warnings + " warnings";
      const w = el("i", "w"); w.style.height = (bucket.warnings / max) * 90 + "px";
      const e = el("i", "e"); e.style.height = (bucket.errors / max) * 90 + "px";
      bar.append(w, e);
      holder.appendChild(bar);
    }
    note.textContent = "Each bar is " + timeline.bucket_seconds + " seconds. Orange = errors, yellow = warnings.";
  }

  function renderCauses(causes) {
    const holder = el("div", "causes");
    holder.appendChild(el("div", "causes-title", "Probable causes (hints from fixed rules, not proof)"));
    causes.forEach((cause, index) => {
      const item = el(index === 0 ? "div" : "details", "cause");
      const head = el(index === 0 ? "div" : "summary", "cause-head", cause.cause);
      item.appendChild(head);
      item.appendChild(el("div", "muted", cause.explanation));
      const list = el("ol", "steps");
      for (const step of cause.steps) list.appendChild(el("li", "", step));
      item.appendChild(list);
      item.appendChild(el("div", "muted small", 'Matched "' + cause.matched + '" in the ' + cause.where + "."));
      holder.appendChild(item);
    });
    return holder;
  }

  function renderGroup(group) {
    const box = el("div", "group");
    const head = el("div", "group-head");
    head.appendChild(el("span", "badge " + group.level, group.level));
    head.appendChild(el("span", "title", group.title));
    head.appendChild(el("span", "count", "x" + group.count));
    box.appendChild(head);
    let meta = "First " + fmt(group.first_seen) + ", last " + fmt(group.last_seen) + ". Line " + group.lines.join(", ");
    if (group.count > group.lines.length) meta += ", ...";
    if (group.exception_type) meta += ". Exception: " + group.exception_type;
    box.appendChild(el("div", "muted", meta));
    if (group.causes && group.causes.length) box.appendChild(renderCauses(group.causes));
    const details = el("details");
    details.appendChild(el("summary", "", "Show first occurrence"));
    details.appendChild(el("pre", "", group.sample));
    box.appendChild(details);
    return box;
  }

  let lastResult = null;

  function saveBlob(blob, name) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function downloadReport() {
    if (!lastResult) return;
    showError("");
    try {
      const response = await fetch(API + "/api/report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(lastResult),
      });
      if (!response.ok) {
        let body = null;
        try { body = await response.json(); } catch (e) { /* not JSON */ }
        showError(body && body.error ? body.error.message : "Could not make the report (" + response.status + ").");
        return;
      }
      saveBlob(await response.blob(), "log-report.md");
    } catch (e) {
      showError("Could not reach the server to make the report.");
    }
  }

  function downloadJson() {
    if (!lastResult) return;
    saveBlob(new Blob([JSON.stringify(lastResult, null, 2)], { type: "application/json" }), "log-analysis.json");
  }

  function render(data, scroll) {
    lastResult = data;
    const a = data.analysis;
    const s = a.summary;
    const stats = $("stats");
    stats.replaceChildren(
      stat("lines analyzed", s.lines_analyzed),
      stat("errors", s.error_count),
      stat("warnings", s.warning_count),
      stat("problem groups", s.group_count)
    );
    const notices = $("notices");
    notices.replaceChildren();
    if (s.truncated) notices.appendChild(el("div", "notice", "This log is long: only the most recent " + s.lines_analyzed + " of " + s.total_lines + " lines were analyzed."));
    for (const w of data.source.warnings) notices.appendChild(el("div", "notice", w));
    renderTimeline(a.timeline);
    const groups = $("groups");
    groups.replaceChildren();
    if (s.groups_omitted) notices.appendChild(el("div", "notice", "This log has " + s.group_count + " different problems. Only the " + a.groups.length + " most important are shown."));
    if (!a.groups.length) groups.appendChild(el("p", "muted", "No warnings or errors found in this log."));
    for (const g of a.groups) groups.appendChild(renderGroup(g));
    $("results").style.display = "block";
    if (scroll) $("results").scrollIntoView({ behavior: "smooth" });
  }

  // The API key lives only in this input while the request is sent. It is never stored.
  async function explainWithAi() {
    if (!lastResult) return;
    const box = $("ai-error");
    const answer = $("ai-answer");
    const keyInput = $("ai-key");
    box.style.display = "none";
    answer.replaceChildren();
    if (!keyInput.value.trim()) {
      box.textContent = "Enter your API key first. Nothing is sent without one.";
      box.style.display = "block";
      return;
    }
    $("ai-run").disabled = true;
    $("ai-run").textContent = "Asking...";
    try {
      const response = await fetch(API + "/api/ai/diagnose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: $("ai-provider").value,
          api_key: keyInput.value.trim(),
          model: $("ai-model").value.trim() || null,
          analysis: lastResult,
        }),
      });
      let body = null;
      try { body = await response.json(); } catch (e) { /* not JSON */ }
      if (!response.ok) {
        box.textContent = body && body.error ? body.error.message : "Something went wrong (" + response.status + ").";
        box.style.display = "block";
        return;
      }
      answer.appendChild(document.createTextNode(body.text));
      answer.appendChild(el("div", "ai-meta", "Written by " + body.provider + " (" + body.model + ") from " + body.groups_sent + " problem group(s). AI can be wrong: check it against the evidence above."));
    } catch (e) {
      box.textContent = "Could not reach the server.";
      box.style.display = "block";
    } finally {
      $("ai-run").disabled = false;
      $("ai-run").textContent = "Explain with AI";
    }
  }

  // Ask the server if it is up. A sleeping free server needs about a minute.
  async function watchServer(attempt) {
    const status = $("server-status");
    try {
      const response = await fetch(API + "/health", { cache: "no-store" });
      if (response.ok) { status.textContent = "Server: ready"; return; }
    } catch (e) { /* not reachable yet */ }
    if (attempt >= 24) {
      status.textContent = "Server: not responding. Try again in a minute.";
      return;
    }
    status.textContent = "Server: waking up (free hosting sleeps when idle, this can take a minute)...";
    setTimeout(() => watchServer(attempt + 1), 5000);
  }

  watchServer(0);

  $("analyze").addEventListener("click", analyzeText);
  $("dl-report").addEventListener("click", downloadReport);
  $("dl-json").addEventListener("click", downloadJson);
  $("ai-run").addEventListener("click", explainWithAi);
  $("file").addEventListener("change", (event) => {
    const file = event.target.files[0];
    if (file) analyzeFile(file);
    event.target.value = "";
  });
})();
