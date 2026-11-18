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

  // Recent analyses: counts and a few titles, kept in this browser only. The log itself is never stored.
  const HISTORY_KEY = "logdoctor.history.v1";
  const HISTORY_MAX = 10;
  function loadHistory() {
    try {
      const list = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
      return Array.isArray(list) ? list.filter((x) => x && typeof x === "object").slice(0, HISTORY_MAX) : [];
    } catch (e) { return []; }
  }
  function saveHistory(list) {
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify(list)); } catch (e) { /* storage blocked or full: skip */ }
  }
  function addHistory(data) {
    const s = data.analysis.summary;
    const entry = {
      at: new Date().toISOString(),
      name: data.source.filename || (data.source.type === "paste" ? "pasted text" : "log"),
      lines: s.lines_analyzed, errors: s.error_count, warnings: s.warning_count, groups: s.group_count,
      top: data.analysis.groups.slice(0, 3).map((g) => String(g.title).slice(0, 120)),
    };
    saveHistory([entry].concat(loadHistory()).slice(0, HISTORY_MAX));
    renderHistory();
  }
  function renderHistory() {
    const list = loadHistory();
    const holder = $("history");
    holder.replaceChildren();
    $("history-card").hidden = list.length === 0;
    for (const item of list) {
      const row = el("div", "history-item");
      const when = String(item.at || "").replace("T", " ").slice(0, 16);
      row.appendChild(el("strong", "", String(item.name || "log")));
      row.appendChild(el("span", "muted", "  " + when + " UTC  -  " + Number(item.errors) + " errors, " + Number(item.warnings) + " warnings, " + Number(item.groups) + " problem groups"));
      if (Array.isArray(item.top) && item.top.length) row.appendChild(el("div", "muted", item.top.map(String).join("  |  ")));
      holder.appendChild(row);
    }
  }

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
    if (scroll) addHistory(data);
    $("results").style.display = "block";
    if (scroll) $("results").scrollIntoView({ behavior: "smooth" });
  }

  // AI box. The key is sent with each request and is never stored by the server.
  // Only if the visitor ticks the box is it kept, in this tab's sessionStorage, until the tab closes.
  const PREF_KEY = "logdoctor.ai.prefs.v1";
  const keyStore = (provider) => "logdoctor.ai.key." + provider;
  const OTHER = "__other__";

  function readPrefs() {
    try { const p = JSON.parse(localStorage.getItem(PREF_KEY) || "{}"); return p && typeof p === "object" ? p : {}; } catch (e) { return {}; }
  }
  function writePrefs(update) {
    try { localStorage.setItem(PREF_KEY, JSON.stringify(Object.assign(readPrefs(), update))); } catch (e) { /* ignore */ }
  }
  function remembered(provider) {
    try { return sessionStorage.getItem(keyStore(provider)) || ""; } catch (e) { return ""; }
  }
  function setRemembered(provider, key) {
    try {
      if (key) sessionStorage.setItem(keyStore(provider), key); else sessionStorage.removeItem(keyStore(provider));
    } catch (e) { /* storage blocked: the key simply is not kept */ }
  }

  function aiError(message) {
    const box = $("ai-error");
    box.textContent = message || "";
    box.style.display = message ? "block" : "none";
  }

  function setModelOptions(models, defaultModel, selected) {
    const select = $("ai-model");
    select.replaceChildren();
    const first = el("option", "", defaultModel ? "Default (" + defaultModel + ")" : "Default model");
    first.value = "";
    select.appendChild(first);
    for (const name of models) {
      const option = el("option", "", name);
      option.value = name;
      select.appendChild(option);
    }
    const other = el("option", "", "Other (type a name)...");
    other.value = OTHER;
    select.appendChild(other);
    select.value = selected && (models.includes(selected) || selected === OTHER) ? selected : "";
    $("ai-model-custom").hidden = select.value !== OTHER;
  }

  function currentModel() {
    const value = $("ai-model").value;
    if (value === OTHER) return $("ai-model-custom").value.trim() || null;
    return value || null;
  }

  function loadProviderState() {
    const provider = $("ai-provider").value;
    const saved = remembered(provider);
    $("ai-key").value = saved;
    $("ai-remember").checked = Boolean(saved);
    const prefs = readPrefs();
    const list = (prefs.models && prefs.models[provider]) || [];
    setModelOptions(Array.isArray(list) ? list.filter((m) => typeof m === "string") : [], "", (prefs.chosen || {})[provider]);
    aiError("");
  }

  async function postJson(path, payload) {
    const response = await fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    let body = null;
    try { body = await response.json(); } catch (e) { /* not JSON */ }
    if (!response.ok) {
      throw new Error(body && body.error ? body.error.message : "Something went wrong (" + response.status + ").");
    }
    return body;
  }

  function keyOrComplain() {
    const key = $("ai-key").value.trim();
    if (!key) { aiError("Enter your API key first. Nothing is sent without one."); return null; }
    setRemembered($("ai-provider").value, $("ai-remember").checked ? key : "");
    return key;
  }

  async function loadModels() {
    const key = keyOrComplain();
    if (!key) return;
    const provider = $("ai-provider").value;
    aiError("");
    $("ai-load").disabled = true;
    $("ai-load").textContent = "Loading...";
    try {
      const data = await postJson("/api/ai/models", { provider: provider, api_key: key });
      const prefs = readPrefs();
      const chosen = (prefs.chosen || {})[provider];
      setModelOptions(data.models, data.default, chosen);
      writePrefs({ models: Object.assign({}, prefs.models || {}, { [provider]: data.models }) });
      $("ai-note").textContent = data.models.length + " chat model(s) available to your key. The first is a good default.";
    } catch (e) {
      aiError(e.message || "Could not reach the server.");
    } finally {
      $("ai-load").disabled = false;
      $("ai-load").textContent = "Load my models";
    }
  }

  async function explainWithAi() {
    if (!lastResult) return;
    const answer = $("ai-answer");
    answer.replaceChildren();
    aiError("");
    const key = keyOrComplain();
    if (!key) return;
    const provider = $("ai-provider").value;
    const model = currentModel();
    $("ai-run").disabled = true;
    $("ai-run").textContent = "Asking...";
    try {
      const body = await postJson("/api/ai/diagnose", { provider: provider, api_key: key, model: model, analysis: lastResult });
      writePrefs({ chosen: Object.assign({}, readPrefs().chosen || {}, { [provider]: $("ai-model").value }) });
      answer.appendChild(document.createTextNode(body.text));
      answer.appendChild(el("div", "ai-meta", "Written by " + body.provider + " (" + body.model + ") from " + body.groups_sent + " problem group(s). AI can be wrong: check it against the evidence above."));
    } catch (e) {
      aiError(e.message || "Could not reach the server.");
    } finally {
      $("ai-run").disabled = false;
      $("ai-run").textContent = "Explain with AI";
    }
  }

  // "Add to GitHub": builds the workflow file in the browser and links to GitHub's new-file page.
  function setupGithubBox() {
    const W = window.LogDoctorWorkflow;
    if (!W) return;
    const select = $("gh-language");
    for (const key of Object.keys(W.LANGUAGES)) {
      const option = el("option", "", W.LANGUAGES[key].label);
      option.value = key;
      select.appendChild(option);
    }
    function refresh() {
      const language = select.value;
      $("gh-command").hidden = language !== "other";
      const text = W.build({ language: language, command: $("gh-command").value, failOn: $("gh-fail").checked ? "error" : "" });
      $("gh-yaml").textContent = text;
      const repo = $("gh-repo").value.trim();
      const branch = $("gh-branch").value.trim() || "main";
      const link = $("gh-open");
      const note = $("gh-note");
      if (W.validRepo(repo) && W.validBranch(branch) && (language !== "other" || $("gh-command").value.trim())) {
        link.href = W.newFileUrl(repo, branch, text);
        link.setAttribute("aria-disabled", "false");
        note.textContent = "";
      } else {
        link.removeAttribute("href");
        link.setAttribute("aria-disabled", "true");
        note.textContent = language === "other" && !$("gh-command").value.trim() ? "Type the command that runs your project." : "Enter the repo as owner/name.";
      }
    }
    for (const id of ["gh-repo", "gh-branch", "gh-command"]) $(id).addEventListener("input", refresh);
    select.addEventListener("change", refresh);
    $("gh-fail").addEventListener("change", refresh);
    $("gh-copy").addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText($("gh-yaml").textContent);
        $("gh-note").textContent = "Copied. In your repo: Add file, Create new file, name it .github/workflows/log-doctor.yml, paste, Commit.";
      } catch (e) {
        $("gh-note").textContent = "Could not copy automatically. Select the text above and copy it.";
      }
    });
    refresh();
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
  setupGithubBox();
  renderHistory();
  $("history-clear").addEventListener("click", () => {
    try { localStorage.removeItem(HISTORY_KEY); } catch (e) { /* ignore */ }
    renderHistory();
  });

  $("analyze").addEventListener("click", analyzeText);
  $("dl-report").addEventListener("click", downloadReport);
  $("dl-json").addEventListener("click", downloadJson);
  $("ai-run").addEventListener("click", explainWithAi);
  $("ai-load").addEventListener("click", loadModels);
  $("ai-provider").addEventListener("change", loadProviderState);
  $("ai-model").addEventListener("change", () => { $("ai-model-custom").hidden = $("ai-model").value !== OTHER; });
  $("ai-remember").addEventListener("change", () => {
    const provider = $("ai-provider").value;
    setRemembered(provider, $("ai-remember").checked ? $("ai-key").value.trim() : "");
  });
  loadProviderState();
  $("file").addEventListener("change", (event) => {
    const file = event.target.files[0];
    if (file) analyzeFile(file);
    event.target.value = "";
  });
})();
