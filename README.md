# Universal Log Doctor

Paste or upload application logs and get the errors grouped, counted and explained. The goal is a free public tool that works for logs from any language, with no account and nothing to install.

> **Status: early work in progress.** Right now the repo contains only the deployment foundation (server, health check, Render config, tests). The log analysis itself is not built yet. See the roadmap below for what is done and what is next.

This project grew out of an earlier "Intelligent Log Analyzer API". That version stored logs in SQLite and sent them to an LLM using a server-side key. It was replaced because a free public host cannot keep a database, and the new design never uses the owner's API key.

## How it will work

- **Stateless.** Logs are processed in memory and thrown away. No database, no disk, no Redis, no background workers.
- **No account needed.** Open the site, paste or upload a log, read the result.
- **Deterministic analysis first.** Parsing, grouping repeated errors, severity, frequency, a failure timeline, probable causes and debugging steps all work without any AI.
- **AI is optional and bring-your-own-key.** If you add your own Groq, OpenAI or Anthropic key, you can ask for an AI diagnosis. The key is used for that one request and is never stored or logged. Your log excerpts are sent to the provider you choose, so don't send anything you wouldn't share with them.
- **Zero cost to run.** Designed for a free Render web service.

Languages: Python, Java, JavaScript/Node.js, Go and C/C++.

## The engine

The analysis lives in the `logdoctor/` package. It has no web code, so the website, the API and a command-line tool can all use it.

```python
from logdoctor import analyze

result = analyze(open("app.log").read())
print(result.summary.error_count)
for group in result.groups:          # most severe and most frequent first
    print(group.level, group.count, group.title, "lines", group.lines)
```

What it does today:
- Reads timestamps (ISO style, with time zones) and levels (INFO, WARN, ERROR, FATAL and common variants) from plain text, key=value and JSON-per-line logs.
- Keeps multi-line records together, including Python tracebacks and chained exceptions.
- Groups repeated problems by masking ids, numbers, IPs and paths, and keeps the line numbers as evidence.
- Counts failures over time in buckets sized to fit the log.
- If a log is longer than the line limit, it analyzes the most recent lines and says so.

Java traces are understood (the root `Caused by` is what gets grouped), except the two-line `java.util.logging` format. Node.js traces are understood (the last `[cause]` is what gets grouped); Firefox-style `fn@file:line` traces are not. Go panics and fatal errors are understood (the first goroutine, without `runtime` frames); plain Go error log lines are grouped by message. C/C++ crashes are understood: `terminate called` with `what()`, assertion failures, signal lines such as `Caught signal 11 (SIGSEGV)`, AddressSanitizer/ThreadSanitizer/UBSan reports, and frames from glibc `backtrace_symbols`, gdb and the sanitizers. C++ names are not demangled (`_ZN3Foo3barEv` stays as it is).

## The API

Interactive docs are at `/docs` when the server is running.

```bash
# Paste: send JSON
curl -s localhost:8000/api/analyze/text \
  -H 'content-type: application/json' \
  -d '{"text": "2024-05-01 10:00:01 ERROR db timeout"}'

# File: send the raw bytes (the name is only used to check the file type)
curl -s --data-binary @app.log "localhost:8000/api/analyze/file?filename=app.log"

# Current limits and accepted file types
curl -s localhost:8000/api/limits
```

Errors always look like `{"error": {"code": "...", "message": "..."}}`.
Too large is `413`, a wrong file type is `415`, and a busy server is `503`
with `Retry-After`. Responses are sent with `Cache-Control: no-store`.

## Command line

Runs locally and sends nothing anywhere.

```bash
pip install .                       # from a clone of this repo
logdoctor app.log                   # readable report
logdoctor app.log --json            # full analysis as JSON
cat app.log | logdoctor             # read standard input
logdoctor app.log --fail-on error   # exit 1 if an error group is found (for CI)
```

Exit codes: `0` ok, `1` the `--fail-on` level was reached, `2` bad input.

## Instant landing page (optional)

A status line tells visitors whether the server is awake. Free hosts sleep when
idle, so you can serve the page from a static host that is always on (for
example GitHub Pages) and let it call the API:

```bash
python scripts/build_site.py site https://your-api.onrender.com
# upload the site/ folder to the static host
```

On the API server, allow that page's address (nothing is allowed by default):

```
LOGDOCTOR_CORS_ORIGINS=https://yourname.github.io
```

## JSON and CSV logs

JSON-lines logs (one object per line) and CSV logs with a header row are read
field by field. The message, level and time are found under the usual names
(`msg`, `message`, `event`, `level`, `severity`, `time`, `ts`, `@timestamp`,
nested ECS fields like `log.level`, pino's numeric levels and epoch times).
Other fields such as request ids or durations are ignored when grouping, so
repeated errors still group. A stack trace inside a field (`stack`, `err.stack`,
`exception`, ...) is read by the same language detectors as plain text.

Limits: each line is read on its own, so pretty-printed multi-line JSON and CSV
values that contain line breaks are not supported. A CSV file needs a header
row with a message column plus a level or time column.

## Probable causes

For each problem group the tool suggests probable causes and debugging steps.
These come from a fixed list of rules in `logdoctor/rules.py` (connection
refused, timeouts, out of memory, null references, full disk, certificate
errors, C++ memory bugs, Go deadlocks and so on). The same log always gives
the same answer, and no AI is involved.

- A match in the error message ranks above a match that only appears in the
  stack trace, and the page says which one it was and which text matched.
- At most 3 causes per group, and only the 100 most important groups are checked.
- These are common causes, not a verdict. When nothing matches, no cause is shown.
- To add a rule, add an entry to `RULES` and an example for it in `tests/test_diagnose.py`;
  a test fails if a rule has no example.

## Reports

Download the result as a Markdown report (the **Download report** button), or
as JSON. From the command line:

```bash
logdoctor app.log --markdown > report.md
```

The API also has `POST /api/report`: send it the JSON that the analyze
endpoints returned and it answers with the report as a file. The report has a
summary, a timeline, every problem group with its probable causes and first
occurrence, and a short note on how to read it. Text from the log is escaped
and code-fenced so it cannot turn into links or HTML. The same analysis always
gives the same report (it contains no clock time).

## Limits

These protect a small free server. They can be changed with environment variables (see `.env.example`).

| Limit | Default |
|---|---|
| Upload size | 5 MB |
| Pasted text | 1 MB |
| Lines analyzed | 50,000 |
| Analyses running at once | 2 |
| Requests per minute per visitor | 20 analyses, 5 AI calls (planned for R6, not enforced yet) |
| Problem groups returned | 500 (the total is still reported) |
| Groups that get probable causes | 100, at most 3 causes each |
| Groups in a Markdown report | 50 in detail |

## Run locally

Needs Python 3.13.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m app.main
```

Then open http://127.0.0.1:8000. The health check is at `/health` and the API docs are at `/docs`.

## Run the tests

```bash
pytest
```

## Deploy on Render (free)

1. Push this repo to GitHub.
2. In Render, choose **New > Blueprint** and select the repo. It reads `render.yaml`.
3. Render builds it and uses `/health` to check that it is up.

A free Render service goes to sleep after 15 minutes without traffic, and the first visit afterwards takes about a minute to wake it. That is a limit of the free plan.

## Roadmap

- [x] **R0** Foundation: stateless FastAPI app, `/health`, `$PORT`, Render config, tests, CI
- [x] **R1a** Analysis engine (`logdoctor/` package): generic log parsing, Python tracebacks, grouping, severity, frequency, timeline
- [x] **R1b** API endpoints for pasted text and uploaded files, with the size limits
- [x] **R1c** `logdoctor` command-line tool using the same engine
- [x] **R2** Web page: paste, upload, results, clear error messages
- [x] **R2b** Static landing page option with a server wake-up status line
- [x] **R3** Java, JavaScript/Node.js, Go and C++ parsers, plus JSON and CSV logs
- [x] **R4** Probable causes, debugging steps and downloadable report
- [ ] **R5** Optional AI diagnosis with your own key (Groq, OpenAI, Anthropic)
- [ ] **R6** Rate limits, ZIP upload with safe-extraction limits, security hardening, live check
- [ ] **R7** Command-line tool and a GitHub Actions workflow to use it from your own project
