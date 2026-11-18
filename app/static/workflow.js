// Builds the GitHub workflow file text. Pure functions, no page access, so it can be tested with Node.
(function (root) {
  "use strict";
  const ACTION = "priyxnshu07/universal-log-doctor@main";
  const REPO_RE = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
  const BRANCH_RE = /^[A-Za-z0-9._\/-]+$/;

  const LANGUAGES = {
    python: {
      label: "Python (pytest)",
      setup: ["- uses: actions/setup-python@v5", "  with:", "    python-version: \"3.12\"",
              "- run: pip install -r requirements.txt || true   # change if you install differently"],
      command: "pytest 2>&1 | tee app.log",
    },
    node: {
      label: "Node.js / React (npm test)",
      setup: ["- uses: actions/setup-node@v4", "  with:", "    node-version: 20",
              "- run: npm ci || npm install"],
      command: "npm test 2>&1 | tee app.log",
    },
    java: {
      label: "Java (Maven)",
      setup: ["- uses: actions/setup-java@v4", "  with:", "    distribution: temurin", "    java-version: 17"],
      command: "mvn test 2>&1 | tee app.log",
    },
    go: {
      label: "Go",
      setup: ["- uses: actions/setup-go@v5", "  with:", "    go-version: stable"],
      command: "go test ./... 2>&1 | tee app.log",
    },
    other: {
      label: "Other (type my own command)",
      setup: [],
      command: "",
    },
  };

  function validRepo(repo) {
    return REPO_RE.test(repo || "") && repo.split("/").every((part) => !/^\.+$/.test(part));  // no "." or ".." parts
  }
  function validBranch(branch) { return BRANCH_RE.test(branch || "") && branch.indexOf("..") === -1; }
  function cleanCommand(command) {
    // One line only, so nobody ends up with a broken or surprising workflow file.
    return String(command || "").replace(/[\r\n]+/g, " ").trim();
  }

  function build(options) {
    const language = LANGUAGES[options.language] || LANGUAGES.python;
    let command = language.command;
    if (options.language === "other") {
      command = cleanCommand(options.command);
      if (command && !/\|\s*tee\s+app\.log\s*$/.test(command)) command += " 2>&1 | tee app.log";
    }
    const failOn = options.failOn === "error" || options.failOn === "warning" || options.failOn === "critical" ? options.failOn : "";
    const lines = [
      "name: Log Doctor",
      "on: [push, pull_request]",
      "",
      "jobs:",
      "  check-logs:",
      "    runs-on: ubuntu-latest",
      "    steps:",
      "      - uses: actions/checkout@v4",
    ];
    for (const step of language.setup) lines.push("      " + step);
    if (command) {
      lines.push("      - name: Run the project and keep its output");
      lines.push("        run: " + JSON.stringify(command));
      lines.push("        continue-on-error: true   # so the log is still analyzed when tests fail");
    }
    lines.push("      - uses: " + ACTION);
    lines.push("        with:");
    lines.push("          log-path: app.log");
    if (failOn) lines.push("          fail-on: " + failOn);
    return lines.join("\n") + "\n";
  }

  function newFileUrl(repo, branch, text) {
    return "https://github.com/" + repo + "/new/" + branch.split("/").map(encodeURIComponent).join("/") +
      "?filename=" + encodeURIComponent(".github/workflows/log-doctor.yml") + "&value=" + encodeURIComponent(text);
  }

  const api = { build, newFileUrl, validRepo, validBranch, LANGUAGES, ACTION };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.LogDoctorWorkflow = api;
})(typeof window !== "undefined" ? window : this);
