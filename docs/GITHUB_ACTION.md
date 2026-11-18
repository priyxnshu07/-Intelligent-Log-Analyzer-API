# Use Log Doctor in your own GitHub project

No account, no key, no AI. It runs on GitHub's runner, reads your log, and puts a
report with **probable causes and fix steps** on the run page. Your log is not
uploaded anywhere.

## Step 1: add the workflow

In your project create the file `.github/workflows/log-doctor.yml`:

```yaml
name: Log Doctor
on: [push, pull_request]

jobs:
  check-logs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # 1. Produce a log. Use whatever your project already runs. For example:
      - name: Run tests and keep the output
        run: pytest 2>&1 | tee app.log          # npm test 2>&1 | tee app.log, mvn test | tee app.log, go test ./... 2>&1 | tee app.log
        continue-on-error: true                 # so the log is still analyzed when tests fail

      # 2. Analyze it
      - uses: priyxnshu07/universal-log-doctor@main
        with:
          log-path: app.log
          fail-on: error                        # optional, see below
```

Commit and push. That is all.

## Step 2: read the result (this is where the fixes are)

1. Open your repository on GitHub, then the **Actions** tab, then the latest run.
2. Click the run. The **Summary** page shows a **Log Doctor** report:
   - how many errors and warnings, and a timeline,
   - every problem **grouped** (repeated errors counted once, with the line numbers),
   - for each one a **probable cause** and numbered **steps to fix it**.
3. The same report is under **Artifacts** as `log-doctor-report` (a `.md` file you can download).

Example of what one problem looks like (from the sample in this repo):

```
[ERROR] KeyError: 'user_id'  (x2)   at line(s): 3, 9
probable cause: Code looked up a key or position that does not exist
  1. Find the lookup in the top frame and the key or index that was used.
  2. Check the input data that produced it: was a field or item missing?
  3. Use a safe lookup (get(), contains check) or validate the input first.
```

The causes come from fixed rules (35 common problems: timeouts, connection
refused, out of memory, missing files, permissions, null pointers, and so on).
They are hints, not proof: check them against the lines shown.

## Options

| Input | Meaning | Default |
|---|---|---|
| `log-path` | the log file (txt, log, json, jsonl, csv) | required |
| `fail-on` | fail the job at this level or above: `warning`, `error`, `critical` | never fail |
| `max-lines` | analyze only the most recent N lines | 50000 |
| `report-path` | where the report file is written | `log-report.md` |
| `upload-report` | attach the report as an artifact | `true` |
| `artifact-name` | artifact name (change it if you use the action twice in one job) | `log-doctor-report` |

- With no `fail-on` the job never fails because of the log; you only get the report.
- With `fail-on: error` the job goes red if any group at ERROR or CRITICAL exists. The
  report is still written first, so you can see why.

## Make your own logs easy to read

Each line needs a timestamp and a level. See [LOGGING.md](LOGGING.md) for Python,
Java, Node.js, Go and C/C++.

## Troubleshooting

- **"log file not found"**: the path is relative to the repository root. Make sure the
  step that creates the log ran before the action (and in the same job).
- **Nothing in the summary**: the action writes it at the end of its step; open the step
  log to see the text report too.
- **Two runs in one job fail on the artifact**: give the second one a different
  `artifact-name`, or set `upload-report: "false"`.
- **Pin a version** instead of `@main` once you rely on it, for example a tag or commit id.
