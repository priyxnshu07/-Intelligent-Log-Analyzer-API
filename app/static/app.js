// All log-derived text is untrusted. It is only ever shown with textContent.
(function () {
  "use strict";
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
      render(body);
    } catch (e) {
      showError("Could not reach the server. If this is the free hosting, it may be waking up: wait a minute and try again.");
    } finally {
      setBusy(false);
    }
  }

  function analyzeText() {
    const text = $("text").value;
    if (!text.trim()) { showError("Paste a log first, or upload a file."); return; }
    send("/api/analyze/text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text }),
    });
  }

  function analyzeFile(file) {
    send("/api/analyze/file?filename=" + encodeURIComponent(file.name), { method: "POST", body: file });
  }

  async function loadSample() {
    const response = await fetch("/static/samples/python-web-app.txt");
    $("text").value = await response.text();
    analyzeText();
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
    const details = el("details");
    details.appendChild(el("summary", "", "Show first occurrence"));
    details.appendChild(el("pre", "", group.sample));
    box.appendChild(details);
    return box;
  }

  function render(data) {
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
    if (!a.groups.length) groups.appendChild(el("p", "muted", "No warnings or errors found in this log."));
    for (const g of a.groups) groups.appendChild(renderGroup(g));
    $("results").style.display = "block";
    $("results").scrollIntoView({ behavior: "smooth" });
  }

  $("analyze").addEventListener("click", analyzeText);
  $("sample").addEventListener("click", loadSample);
  $("file").addEventListener("change", (event) => {
    const file = event.target.files[0];
    if (file) analyzeFile(file);
    event.target.value = "";
  });
})();
