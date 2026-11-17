# Logging so Log Doctor can read your logs

Log Doctor needs two things on each line: a **timestamp** and a **level**. Then
repeated errors are grouped and put on a timeline. Stack traces are read in
detail for Python, Java, Node.js, Go and C/C++. These setups were checked
against the tool (see `tests/test_logging_guide.py`).

## Python

```python
import logging
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")
try:
    risky()
except Exception:
    log.exception("db call failed")   # keeps the full traceback with the line
```

Output: `2024-05-01 10:00:01,123 ERROR app: db timeout`

## Java (Logback)

```xml
<pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n</pattern>
```

```java
log.error("db call failed", exception);   // pass the exception to keep the stack trace
```

Output: `2024-05-01 10:00:01.123 ERROR [main] com.app.Db - db timeout`

## Node.js

Use JSON lines (pino, or winston's JSON format). Fields such as `level`, `time`,
`msg` and `err.stack` are read by name.

```js
const pino = require("pino");
const log = pino();
log.error({ err }, "db call failed");
```

Output: `{"level":50,"time":1714557601123,"msg":"db timeout"}`

## Go

Use `log/slog`. Panics (`panic:`, `fatal error:`) are recognized without any setup.

```go
logger := slog.New(slog.NewTextHandler(os.Stderr, nil))
logger.Error("db call failed", "err", err)
```

Output: `time=2024-05-01T10:00:01.123Z level=ERROR msg="db timeout"`

## C and C++

Use a logger with a level and time, for example spdlog:

```cpp
spdlog::set_pattern("%Y-%m-%d %H:%M:%S.%e [%l] %v");
spdlog::error("db call failed");
```

Output: `2024-05-01 10:00:01.123 [error] db timeout`

Crashes from uncaught exceptions, assertions, signals and AddressSanitizer /
ThreadSanitizer / LeakSanitizer / UBSan reports are recognized as they are. Build
with `-g` so frames show file names.

## Not supported

Java `java.util.logging` two-line records, Firefox/Safari `fn@file:line` JavaScript
traces, Windows/MSVC crash formats, and JSON or CSV records that span several lines.

## In GitHub Actions

```yaml
- uses: priyxnshu07/universal-log-doctor@main
  with:
    log-path: app.log
    fail-on: error        # optional: fail the job on error or above
```

The report appears in the job summary. Nothing is uploaded anywhere and no key is needed.
