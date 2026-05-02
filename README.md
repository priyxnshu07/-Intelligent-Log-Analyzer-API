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

## Example API Calls

You can use `curl` or any API client to interact with the endpoints.

*   **Ingest a new log:**
    ```bash
    curl -X POST "http://127.0.0.1:8000/ingest/" 
    -H "Content-Type: application/json" 
    -d '{"timestamp": "2026-05-02T14:00:00", "level": "error", "message": "Critical failure in subsystem."}'
    ```

*   **Query for 'error' logs:**
    ```bash
    curl -X GET "http://127.0.0.1:8000/query/?level=error"
    ```

*   **Get the summary of all logs:**
    ```bash
    curl -X GET "http://127.0.0.1:8000/summary/"
    ```
