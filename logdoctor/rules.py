"""Known problems: a pattern that appears in a log, and what usually causes it.

Everything here is plain data so it is easy to read, review and extend. A rule
matches when its pattern is found in the error's exception type, title or
first lines. Order matters: specific rules come before general ones, and the
first few matches are shown. The hints are common causes, not a verdict.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    id: str
    pattern: str  # regular expression, matched case-insensitively
    cause: str
    explanation: str
    steps: tuple[str, ...]
    languages: tuple[str, ...] = ()  # empty means any language


RULES: tuple[Rule, ...] = (
    # ---- language-specific crashes first ----
    Rule(
        "cpp-use-after-free",
        r"heap-use-after-free|stack-use-after-(?:return|scope)|use-after-free|double[- ]free|attempting double-free",
        "Memory is used after it was freed (or freed twice)",
        "Code kept a pointer or reference to memory that had already been released, so it reads or writes something that is no longer yours.",
        (
            "Open the first stack in the report: it is the line that touched the freed memory.",
            "Look at the 'freed by' stack in the full output to see who released it.",
            "Check ownership: use smart pointers or make one owner responsible for freeing.",
            "Keep running with AddressSanitizer on while you fix it.",
        ),
        ("cpp",),
    ),
    Rule(
        "cpp-buffer-overflow",
        r"buffer-overflow|stack-buffer|heap-buffer|global-buffer|out-of-bounds",
        "Code reads or writes past the end of a buffer",
        "An index or length went beyond the size of an array or buffer.",
        (
            "Open the first stack: the top frame is the access that went out of bounds.",
            "Check the index or length calculation just before that line.",
            "Use bounds-checked access (at(), std::span, std::string) where you can.",
        ),
        ("cpp",),
    ),
    Rule(
        "cpp-data-race",
        r"data race|ThreadSanitizer",
        "Two threads touch the same data without synchronization",
        "A data race gives unpredictable results that change from run to run.",
        (
            "Find the two accesses in the report (one is a write).",
            "Protect the shared data with a mutex or make it atomic.",
            "Re-run under ThreadSanitizer to confirm the race is gone.",
        ),
        ("cpp",),
    ),
    Rule(
        "cpp-uncaught-exception",
        r"terminate called|called without an active exception",
        "A C++ exception was thrown and nothing caught it",
        "An uncaught exception ends the program through std::terminate.",
        (
            "Read the what() text: it is the exception's own description.",
            "Find where that exception type is thrown and add a handler at a sensible level.",
            "In threads, catch exceptions inside the thread function, or they terminate the whole process.",
        ),
        ("cpp",),
    ),
    Rule(
        "cpp-assertion",
        r"assertion .{0,200}failed|^assertion\b",
        "A condition the code assumed to be true was false",
        "An assert() fired. The program checked a condition that must always hold, and it did not.",
        (
            "Read the condition in the message and find where it is checked.",
            "Work out which caller passed the bad value or got the program into that state.",
            "Decide whether the condition is a bug in the caller or the check itself is too strict.",
        ),
        ("cpp",),
    ),
    Rule(
        "cpp-segfault",
        r"SIGSEGV|segmentation fault|SIGBUS",
        "The program accessed memory it must not touch",
        "A null, dangling or wild pointer was dereferenced.",
        (
            "Use the top frame of the trace to find the exact line.",
            "Check that pointer for null and that the object it points to is still alive.",
            "Rebuild with -g and AddressSanitizer to get a precise report.",
        ),
        ("cpp",),
    ),
    Rule(
        "go-concurrent-map",
        r"concurrent map (?:writes|read and map write|iteration and map write)",
        "A Go map is used from several goroutines at once",
        "Maps are not safe for concurrent writes, and Go stops the program when it detects this.",
        (
            "Find the map named in the first frame of the trace.",
            "Guard it with a sync.Mutex or sync.RWMutex, or switch to sync.Map.",
            "Run tests with `go test -race` to find other places.",
        ),
        ("go",),
    ),
    Rule(
        "go-deadlock",
        r"all goroutines are asleep|deadlock!",
        "Every goroutine is blocked, so the program cannot continue",
        "Goroutines are waiting on channels or locks that nobody will release.",
        (
            "Look at the goroutine dump for what each goroutine is waiting on (chan receive, select, mutex).",
            "Check that every channel that is read from is eventually written to or closed.",
            "Check lock ordering and make sure every Lock has an Unlock on every path.",
        ),
        ("go",),
    ),
    Rule(
        "go-nil-map",
        r"assignment to entry in nil map",
        "A Go map was used before it was created",
        "A map variable that was never initialized with make() or a literal is nil, and writing to it panics.",
        (
            "Find the map in the first frame and see where it is declared.",
            "Initialize it with make(map[K]V) before the first write.",
        ),
        ("go",),
    ),
    # ---- memory, resources ----
    Rule(
        "out-of-memory",
        r"OutOfMemoryError|out of memory|\bMemoryError\b|heap out of memory|bad_alloc|Cannot allocate memory|OOMKilled|oom-kill",
        "The program ran out of memory",
        "It asked for more memory than the machine, container or runtime limit allows.",
        (
            "Compare the memory limit (container, JVM -Xmx, Node --max-old-space-size) with real usage.",
            "Look for data that grows without limit: caches, queues, lists that are only appended to.",
            "Check whether one request loads a very large file or result set into memory.",
            "Take a heap snapshot or memory profile shortly before the crash.",
        ),
    ),
    Rule(
        "stack-overflow",
        r"StackOverflowError|RecursionError|maximum recursion depth|Maximum call stack size exceeded|stack overflow",
        "Code calls itself without stopping",
        "Recursion went so deep that the call stack ran out.",
        (
            "Look at the repeating frames in the trace: that is the loop of calls.",
            "Check the stopping condition of that recursive function.",
            "Consider turning the recursion into a loop for deep inputs.",
        ),
    ),
    Rule(
        "disk-full",
        r"ENOSPC|No space left on device|disk (?:is )?full|not enough space",
        "The disk is full",
        "The program tried to write and there is no free space left on that volume.",
        (
            "Run `df -h` (and `df -i` for inodes) on the machine that logged this.",
            "Find the biggest directories, often logs, temp files or uploads.",
            "Set up log rotation and cleanup so it does not fill again.",
        ),
    ),
    Rule(
        "too-many-open-files",
        r"EMFILE|Too many open files|too many open files",
        "The process opened more files or sockets than it is allowed to",
        "Each file and network connection uses a file descriptor, and the per-process limit was reached.",
        (
            "Check the limit with `ulimit -n` for the running process.",
            "Look for files or connections that are opened but never closed.",
            "Raise the limit only after checking there is no leak.",
        ),
    ),
    # ---- network and services ----
    Rule(
        "address-in-use",
        r"EADDRINUSE|Address already in use|BindException|address already in use",
        "The port is already taken",
        "Another process (or an old copy of this one) is listening on the same port.",
        (
            "Find what holds the port: `lsof -i :PORT` or `ss -ltnp`.",
            "Stop the old process, or change the port.",
            "On restarts, make sure the previous instance has fully exited first.",
        ),
    ),
    Rule(
        "pool-exhausted",
        r"too many connections|connection pool|Connection is not available|pool (?:is )?exhausted|HikariPool|remaining connection slots|QueuePool limit",
        "The database connection pool ran out of connections",
        "More requests wanted a connection than the pool or the database allows, or connections are held and never returned.",
        (
            "Compare the pool size with the database's max connections.",
            "Look for code that gets a connection and does not release it on every path, including errors.",
            "Look for slow queries that hold connections for a long time.",
            "Check whether traffic or a retry loop spiked just before the first error.",
        ),
    ),
    Rule(
        "connection-refused",
        r"ECONNREFUSED|Connection refused|ConnectException|connect: connection refused|actively refused|refused the connection",
        "Nothing is listening at the address the program connected to",
        "The target host answered but no service accepted the connection: the service is down, still starting, or the host or port is wrong.",
        (
            "Check the host and port in the message against your configuration.",
            "Check that the target service is running and listening on that port.",
            "If both start together, make the client retry or wait until the service is ready.",
            "In containers, make sure you are not using localhost to reach another container.",
        ),
    ),
    Rule(
        "dns-failure",
        r"ENOTFOUND|EAI_AGAIN|Name or service not known|UnknownHostException|no such host|getaddrinfo|Temporary failure in name resolution|could not resolve host",
        "The host name could not be resolved",
        "DNS did not return an address for that name: a typo, a missing record, or the DNS server is unreachable.",
        (
            "Check the host name in the message for typos.",
            "Try resolving it from the same machine: `nslookup NAME` or `dig NAME`.",
            "Check the machine's DNS settings and network access.",
        ),
    ),
    Rule(
        "ssl-error",
        r"SSLHandshake|CERT_HAS_EXPIRED|certificate (?:has expired|verify failed|is not trusted)|unable to verify the first certificate|x509:|SSL: CERTIFICATE_VERIFY_FAILED|self[- ]signed certificate|PKIX path",
        "A TLS/SSL certificate problem",
        "The certificate is expired, not trusted, for a different host name, or the chain is incomplete.",
        (
            "Check the certificate's expiry date and host name for the address being called.",
            "Check that the intermediate certificates are served, and the CA is trusted on this machine.",
            "Do not turn verification off in production to hide it.",
        ),
    ),
    Rule(
        "connection-reset",
        r"ECONNRESET|Connection reset by peer|Broken pipe|EPIPE|connection reset|unexpected EOF",
        "The other side closed the connection unexpectedly",
        "A server, proxy or load balancer dropped the connection, often a timeout, a restart or a crash on the other end.",
        (
            "Check the logs of the service you were talking to at the same time.",
            "Check idle timeouts on proxies and load balancers against how long your connections stay open.",
            "Retry safe requests with a short backoff.",
        ),
    ),
    Rule(
        "http-5xx",
        r"\b50[234]\b.{0,40}(?:bad gateway|service unavailable|gateway time-?out)|bad gateway|service unavailable|gateway time-?out",
        "An upstream service failed or was unavailable",
        "A proxy or gateway got no good answer from the service behind it.",
        (
            "Check whether the upstream service was up and healthy at that time.",
            "Check timeouts between the gateway and the service.",
            "Check recent deploys or restarts of the upstream.",
        ),
    ),
    Rule(
        "rate-limited",
        r"(?:HTTP|status(?: code)?)[ =:/]{0,3}429|\b429 too many|too many requests|rate[- ]?limit",
        "The service is limiting how many requests are allowed",
        "The caller exceeded a quota or rate limit and was told to slow down.",
        (
            "Look at the Retry-After or rate-limit headers if they are logged.",
            "Add backoff and a cap on retries and parallel requests.",
            "Check the quota or plan on the service you call.",
        ),
    ),
    Rule(
        "timeout",
        r"timed? ?out|ETIMEDOUT|SocketTimeoutException|context deadline exceeded|TimeoutError|deadline exceeded|read timeout|connect timeout",
        "An operation took longer than its time limit",
        "A call to a database, API or other service did not answer in time: it is slow, overloaded, or unreachable.",
        (
            "Find which call timed out (the host or query in the message or trace).",
            "Check that service's own health and latency around the same time.",
            "Check the timeout value is realistic, and that retries are not piling up load.",
            "Check network path problems if only some machines are affected.",
        ),
    ),
    # ---- data and logic errors ----
    Rule(
        "cannot-connect",
        r"could not connect|couldn't connect|unable to connect|failed to connect|cannot connect|can't connect|connection (?:failed|error)|connect(?:ion)? to .{0,60} failed",
        "The program could not reach a service it depends on",
        "A database, API or queue could not be reached. The service may be down or overloaded, the address may be wrong, or the network blocks it.",
        (
            "Check the address in the message against your configuration.",
            "Check that the service is running and reachable from the machine that logged this.",
            "Look for the first failure in time: the problem may have started when a dependency restarted.",
            "Add retries with backoff so short outages do not become errors.",
        ),
    ),
    Rule(
        "null-reference",
        r"NullPointerException|Cannot read propert(?:y|ies) of (?:undefined|null)|'NoneType' object|nil pointer dereference|undefined is not|null is not an object|TypeError: .{0,60} is not a function",
        "Code used a value that was missing (null, None or undefined)",
        "A variable or field was empty when the code expected an object, so the access failed.",
        (
            "Open the top frame of the trace: the failing line uses the empty value.",
            "Work out why it was empty: a failed lookup, missing field in the input, or a step that did not run first.",
            "Add a check or a default at that point, and fix the source of the missing value.",
        ),
    ),
    Rule(
        "missing-key-or-index",
        r"\bKeyError\b|\bIndexError\b|index out of range|ArrayIndexOutOfBounds|IndexOutOfBounds|StringIndexOutOfBounds|list index out of range|NoSuchElementException",
        "Code looked up a key or position that does not exist",
        "A dictionary key, list index or collection element was not there.",
        (
            "Find the lookup in the top frame and the key or index that was used.",
            "Check the input data that produced it: was a field or item missing?",
            "Use a safe lookup (get(), contains check) or validate the input first.",
        ),
    ),
    Rule(
        "bad-input",
        r"\bValueError\b|NumberFormatException|ClassCastException|IllegalArgumentException|InvalidOperationException|invalid literal|could not convert",
        "A value had the wrong type or format",
        "Code received data it could not convert or accept, such as text where a number was expected.",
        (
            "Find the exact value from the message and where it came from (request, file, database).",
            "Validate and convert inputs at the edge before using them.",
            "Add a test with that value.",
        ),
    ),
    Rule(
        "parse-error",
        r"JSONDecodeError|Unexpected token|SyntaxError|JsonParseException|JsonProcessingException|parse error|invalid character|malformed|Unexpected end of (?:JSON|input)|Expecting value",
        "Text could not be parsed (invalid JSON or syntax)",
        "The data was cut off, is not the expected format, or contains a stray character.",
        (
            "Log or inspect the raw text that failed to parse.",
            "Check whether an error page (HTML) or empty body came back instead of JSON.",
            "Check for truncation, wrong encoding or a changed API response format.",
        ),
    ),
    Rule(
        "missing-module",
        r"ModuleNotFoundError|ImportError|Cannot find module|ClassNotFoundException|NoClassDefFoundError|cannot open shared object file|DLL load failed|No module named",
        "A library or module could not be found",
        "The code needs a package or class that is not installed or not on the search path in this environment.",
        (
            "Install the missing package in the environment that logged the error.",
            "Compare the dependency list with what is deployed: is the file or version missing?",
            "Check the Python/Node/Java path and virtual environment used to run it.",
        ),
    ),
    # ---- files, permissions, auth, config ----
    Rule(
        "file-not-found",
        r"FileNotFoundError|ENOENT|No such file or directory|NoSuchFileException|FileNotFoundException|cannot find the (?:file|path)",
        "A file or folder does not exist at that path",
        "The path is wrong, the file was never created or was deleted, or the program runs from a different directory than expected.",
        (
            "Check the full path in the message, and whether it is relative to the working directory.",
            "Check that the file exists on the machine that ran it (not only on yours).",
            "Check mounts and volumes if this runs in a container.",
        ),
    ),
    Rule(
        "permission-denied",
        r"EACCES|PermissionError|Permission denied|AccessDeniedException|EPERM|Operation not permitted",
        "The program is not allowed to access that file or resource",
        "The user running the program lacks permission on the path or resource.",
        (
            "Check which user the program runs as and the owner and mode of the path.",
            "Check read-only mounts and security policies (SELinux, containers).",
            "Grant the least permission needed instead of running as root.",
        ),
    ),
    Rule(
        "auth-failure",
        r"authentication failed|invalid (?:password|token|credentials|api key)|Access denied for user|(?:HTTP|status(?: code)?)[ =:/]{0,3}401|\b401 unauthorized|Unauthorized|password authentication failed|invalid_grant|token (?:has )?expired",
        "Credentials were rejected",
        "A password, token or key is wrong, expired, or lacks access.",
        (
            "Check that the right credentials are loaded in this environment (without printing them to logs).",
            "Check expiry and rotation of the token or key.",
            "Check that the account has access to the thing it is calling.",
        ),
    ),
    Rule(
        "missing-config",
        r"(?:missing|not set|undefined|required).{0,40}(?:environment variable|env var|config|setting)|(?:environment variable|env var|config(?:uration)?) .{0,40}(?:missing|not set|not found)|config file .{0,80}missing",
        "A required setting is missing",
        "A configuration value or environment variable the program needs was not provided in this environment.",
        (
            "Find the setting name in the message and check it is set where the program runs.",
            "Compare this environment's configuration with one that works.",
            "Fail early at startup with a clear message for required settings.",
        ),
    ),
    Rule(
        "deadlock-or-lock",
        r"deadlock|lock wait timeout|could not obtain lock|LockTimeout",
        "Two operations are waiting on each other, or a lock is held too long",
        "Database transactions or threads took locks in conflicting order, or one kept a lock while doing slow work.",
        (
            "Find the two operations from the database or thread dump.",
            "Take locks in the same order everywhere and keep transactions short.",
            "Retry the transaction that was chosen as the victim.",
        ),
    ),
    Rule(
        "unhandled-rejection",
        r"UnhandledPromiseRejection|Unhandled rejection|unhandledRejection",
        "A failed async operation was not handled",
        "A promise was rejected and nothing caught the error, so Node treats it as a crash.",
        (
            "Find the async call in the trace and add try/catch or .catch() there.",
            "Make sure every async function called from an event handler has its errors handled.",
        ),
        ("javascript",),
    ),
    Rule(
        "slow-operation",
        r"slow (?:query|request|response|operation)|took \d+(?:\.\d+)?\s?(?:ms|s|sec)|taking longer than|latency",
        "Something is slow",
        "An operation took longer than the warning threshold: a missing index, a large result, or an overloaded dependency.",
        (
            "Find the slowest examples by their time values in the log.",
            "For a database query, run EXPLAIN on it and check for missing indexes.",
            "Check load on the service or database at the same time.",
        ),
    ),
)
