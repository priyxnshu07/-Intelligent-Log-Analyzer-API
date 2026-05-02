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

1.  **Log Ingestion**: A `POST /ingest/` endpoint to receive and store new log entries.
2.  **Log Querying**: A `GET /query/` endpoint that retrieves stored logs, with the ability to filter by log `level`.
3.  **Log Summarization**: A `GET /summary/` endpoint that provides a count of logs grouped by their `level`, demonstrating data aggregation.

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
    uvicorn main:app --reload
    ```
    The `--reload` flag means the server will automatically restart when you make changes to the code.

5.  **Access the API:**
    The API will be running at `http://127.0.0.1:8000`. You can access the interactive API documentation (provided by Swagger UI) at `http://127.0.0.1:8000/docs`.

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
