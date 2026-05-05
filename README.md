# Intelligent Log Analyzer API

This is a simple, powerful demonstration API built to showcase backend development skills using Python, FastAPI, and SQLAlchemy. It provides a basic system for ingesting, querying, and summarizing log data.

This project was built in a few hours as a key part of a strategic job application process to demonstrate the ability to quickly learn and apply new technologies.

## Core Technologies

*   **Python 3.9+**
*   **FastAPI**: For the high-performance API framework.
*   **SQLAlchemy**: For database interaction and ORM capabilities.
*   **SQLite**: As the simple, file-based database.
*   **Uvicorn**: As the ASGI server to run the application.

## Features

1.  **Visual Dashboard**: A real-time, auto-refreshing UI accessible at the root (`/`) to monitor incoming logs and view system health summaries.
2.  **Log Ingestion**: A `POST /ingest/` endpoint to receive and store new log entries from connected microservices or client apps.
3.  **Advanced Querying**: A `GET /query/` endpoint that retrieves stored logs. Supports filtering by severity `level` and full-text `search` within log messages.
4.  **Log Summarization**: A `GET /summary/` endpoint providing aggregated counts of logs grouped by severity.

## Integration Example

This API is designed to act as a **Centralized Logging Server** for other applications in a microservices architecture. For example, a Node.js Express application can use middleware to automatically push traffic data and error reports to this API via HTTP POST requests using libraries like `axios`.

## How to Run This Project

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd intelligent_log_analyzer_api
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install the dependencies:**
    ```bash
    pip install "fastapi[all]" sqlalchemy
    ```

4.  **Run the server:**
    ```bash
    python3 main.py
    ```

5.  **Access the Dashboard & API:**
    *   **Live Dashboard:** `http://127.0.0.1:8000/`
    *   **Swagger API Docs:** `http://127.0.0.1:8000/docs`

## 🤖 AI-Powered Log Diagnostician (NEW)

This project now includes an intelligent agent that automatically diagnoses errors using LLMs.

### How It Works
1. Agent queries the database for ERROR-level logs
2. Sends error context to OpenAI GPT-4 / Groq Llama-3
3. Returns root cause analysis, suggested fixes, and prevention strategies

### Why I Built This
I wanted to demonstrate "System of Agents" — where AI doesn't just assist development, 
but becomes part of the production infrastructure. This agent turns raw error logs into 
actionable debugging insights.

### Try It
```bash
# Get diagnosis for latest error
curl http://localhost:8000/agent/diagnose/latest

# Diagnose a specific log
curl -X POST http://localhost:8000/agent/diagnose -d '{"log_id": 123}'
```

See [README_AGENT.md](./README_AGENT.md) for full documentation.

---

**Architecture: Distributed Microservices + AI Agent**
```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐      ┌─────────┐
│ Client Apps │─────>│ Log Analyzer │─────>│  Database   │<────>│  Agent  │
│ (Node.js)   │      │  (FastAPI)   │      │ (SQLite)    │      │ (LLM)   │
└─────────────┘      └──────────────┘      └─────────────┘      └─────────┘
```
  ## Architectural Decisions

**Why Two Services (Node.js + Python)?**
I designed this as a polyglot microservices system to demonstrate cross-language integration patterns 
common in production environments. The Node.js middleware handles lightweight request routing and 
client-side interactions, while the Python/FastAPI backend manages compute-heavy log processing and 
database operations. This mirrors real-world architectures where you choose the right tool per workload.

**Why FastAPI for the Backend?**
Async I/O and Pydantic validation make FastAPI ideal for high-throughput log ingestion. The automatic 
OpenAPI docs also serve as a contract for frontend integration.

**Why SQLAlchemy ORM?**
I wanted type-safe database interactions while maintaining flexibility to optimize raw SQL queries 
for analytics endpoints if needed.
