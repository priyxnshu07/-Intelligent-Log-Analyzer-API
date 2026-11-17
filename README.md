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

Planned languages: Python, Java, JavaScript/Node.js, Go and C++, added one at a time.

## Limits

These protect a small free server. They can be changed with environment variables (see `.env.example`).

| Limit | Default |
|---|---|
| Upload size | 5 MB |
| Pasted text | 1 MB |
| Lines analyzed | 50,000 |
| Analyses running at once | 2 |
| Requests per minute per visitor | 20 analyses, 5 AI calls |

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
- [ ] **R1** Analysis engine: paste/upload, generic and Python parsing, grouping, severity, frequency, timeline
- [ ] **R2** Web page: paste, upload, sample logs, results, clear error messages
- [ ] **R2b** Instant landing page that loads even while the server is asleep
- [ ] **R3** Java, JavaScript/Node.js, Go and C++ parsers, plus JSON and CSV logs
- [ ] **R4** Probable causes, debugging steps and downloadable report
- [ ] **R5** Optional AI diagnosis with your own key (Groq, OpenAI, Anthropic)
- [ ] **R6** Rate limits, ZIP upload with safe-extraction limits, security hardening, live check
- [ ] **R7** Command-line tool and a GitHub Actions workflow to use it from your own project
