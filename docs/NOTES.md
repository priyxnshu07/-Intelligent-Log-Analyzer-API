# Universal Log Doctor: limits, known gaps and how to test

## 1. Limits (all can be changed with environment variables, see `.env.example`)

| What | Default | Env variable |
|---|---|---|
| Upload size | 5 MB | `LOGDOCTOR_MAX_UPLOAD_BYTES` |
| Pasted text | 1 MB | `LOGDOCTOR_MAX_PASTE_BYTES` |
| Lines analyzed (most recent kept) | 50,000 | `LOGDOCTOR_MAX_LINES` |
| Analyses at once (others get 503 + Retry-After) | 2 | `LOGDOCTOR_MAX_CONCURRENT` |
| Analyses per visitor per minute (429 + Retry-After) | 20 | `LOGDOCTOR_RATE_ANALYSES_PER_MIN` |
| AI calls per visitor per minute | 5 | `LOGDOCTOR_RATE_AI_PER_MIN` |
| Trust X-Forwarded-For for visitor IP | off locally, on in `render.yaml` | `LOGDOCTOR_TRUST_PROXY` |
| Browser origins allowed to call the API | none | `LOGDOCTOR_CORS_ORIGINS` |
| Line length / record text / message | 10,000 / 4,000 / 500 characters | fixed in code |
| Problem groups returned / diagnosed / in report | 500 / 100 (max 3 causes each) / 50 | fixed in code |
| ZIP: entries scanned / files read / per file / total unpacked | 1,000 / 20 / 10 MB / 20 MB | fixed in `app/ziputil.py` |
| AI: groups sent / prompt size / answer size / timeout / parallel calls | 5 / 9,000 chars / 6,000 chars / 30 s / 2 | fixed in `app/ai.py` |
| History in the browser | last 10, counts + 3 titles | fixed in `app/static/app.js` |

Free Render facts: the service sleeps after 15 minutes idle and takes about a
minute to wake (the page shows a "waking up" line), 750 free hours a month,
memory is wiped on every restart (nothing is stored anyway).

## 2. Known gaps

- Java `java.util.logging` two-line records are not read.
- Firefox/Safari `fn@file:line` JavaScript traces are not read.
- Go errors that are not panics are grouped by message only.
- C++ names are not demangled; Windows/MSVC crash formats are not read.
- JSON and CSV records that span several lines are not supported.
- The 35 probable-cause rules cover common problems with English messages only.
  They are hints, not proof.
- Reports are Markdown only (no PDF).
- Rate limits are per server process and reset on restart (no shared store, by design).
- **AI is not verified against the live providers.** The sandbox cannot reach them, so
  request shapes (Groq/OpenAI chat completions, Anthropic messages) come from
  long-stable documentation and the default model names
  (`llama-3.3-70b-versatile`, `gpt-4o-mini`, `claude-haiku-5-5`) may be outdated.
  The model box on the page is editable. Test with your own key (step 4 below).
- GitHub shows merge commits under your primary email. Commits have no Claude trailers.

## 3. How to test, in order

### A. Automated (2 minutes)

```bash
git clone https://github.com/priyxnshu07/universal-log-doctor && cd universal-log-doctor
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest -q                                              # expect 434 passed
```

### B. Run it locally

```bash
pip install -r requirements.txt
python -m app.main            # then open http://localhost:8000
```

Check on the page:
1. Paste `2024-05-01 10:00:01 ERROR db timeout after 30s` twice, press **Analyze**.
   Expect 1 problem group, count 2, a probable cause about timeouts.
2. Upload a real `.log` or `.json` file of yours. Expect grouped errors and a timeline.
3. Upload a `.zip` holding two log files. Expect a notice "Read 2 file(s) from the ZIP".
4. **Download report (.md)** and **Download JSON**: both files download and open.
5. Upload a `.exe` or a renamed binary: expect a clear error, not a crash.
6. Click **Analyze** 21 times quickly: the 21st shows "Too many requests".
7. Analyze twice, reload the page: "Recent analyses on this device" lists them;
   **Clear history** empties it.
8. Open `http://localhost:8000/docs` for the interactive API.

### C. Command line and GitHub Action

```bash
pip install .
logdoctor app.log                       # text report
logdoctor app.log --markdown > r.md     # Markdown
logdoctor app.log --fail-on error; echo $?   # 1 if an error group exists, else 0
```

In another repo's workflow:

```yaml
- uses: priyxnshu07/universal-log-doctor@main
  with: { log-path: app.log, fail-on: error }
```

Expect the report in the job summary, and the job to fail when errors exist.

### D. AI with your own key (the unverified part, do this first thing)

1. Analyze a log, scroll to **Optional: AI explanation**.
2. Pick a provider, paste your key, leave the model empty, press **Explain with AI**.
3. Expect a short explanation. If you see "check the model name", type a current
   model name from the provider's docs into the model box and retry.
4. If a provider fails with "the provider did not accept the request", the request
   shape needs a fix in `app/ai.py` (`PROVIDERS`). Open an issue or tell me which provider.
5. Confirm the key is gone: reload the page, the key box is empty; the key is never in
   localStorage (DevTools, Application tab).

### E. Deploy on Render (you do this, last)

1. Push is already on GitHub. In Render: **New, Blueprint**, pick this repo.
   `render.yaml` sets the free plan, health check `/health` and `LOGDOCTOR_TRUST_PROXY=true`.
2. Wait for the first deploy (a few minutes), open the `.onrender.com` URL.
3. Repeat the page checks from B on the live URL.
4. Wait 15+ minutes, reload: the page should say the server is waking up, then work.
5. Check the rate limit works per visitor: from your phone on mobile data, you should
   not be blocked by limits you used on your laptop.
