# Log Diagnostician Agent

The Log Diagnostician Agent is an AI-powered extension for the Intelligent Log Analyzer. It connects your centralized logging infrastructure with advanced LLM diagnostics to automatically analyze errors and suggest fixes.

## Overview

When an error is detected in your logs, the Agent uses OpenAI's GPT models to provide a deep analysis of the failure. This bridges the gap between seeing an error and understanding its root cause.

## Why I Built It
This agent was developed to demonstrate the power of "System of Agents" architectures. By connecting a real-time logging database with AI diagnostics, we transform raw data into actionable insights, significantly reducing Mean Time to Resolution (MTTR).

## Architecture

```
Logs DB (SQLite) → Agent (Python/OpenAI) → LLM (GPT-4) → Structured Diagnosis
```

1. **Ingestion**: Microservices push logs to the `/ingest/` endpoint.
2. **Detection**: Errors are stored in the `test.db`.
3. **Diagnosis**: The Agent queries recent errors and sends them to the LLM with full context.
4. **Insight**: The system returns a structured JSON diagnosis including root cause, suggested fix, and prevention strategy.

## API Endpoints

### `GET /agent/diagnose/latest`
Fetches the most recent log entry with `ERROR` level and returns an AI-generated diagnosis.

**Example Response:**
```json
{
  "log_id": 123,
  "error_message": "ValueError: invalid literal for int()",
  "diagnosis": {
    "root_cause": "The code attempted to convert a non-numeric string to integer",
    "suggested_fix": "Add input validation: if not value.isdigit(): raise ValueError(...)",
    "prevention": "Implement type checking with Pydantic models at API boundaries",
    "confidence": "high"
  },
  "execution_time_ms": 1850
}
```

### `POST /agent/diagnose`
Diagnoses a specific log entry by ID.
- **Request Body**: `{"log_id": 123}`

## How to Run Locally

1. **Set up Environment Variables**:
   Create a `.env` file based on `.env.example`:
   ```bash
   cp .env.example .env
   # Add your OPENAI_API_KEY to .env
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Start the Server**:
   ```bash
   python main.py
   ```

4. **Test the Agent**:
   ```bash
   # Get diagnosis for latest error
   curl http://localhost:8000/agent/diagnose/latest
   ```

---
*Built in 2 hours using AI-assisted development.*
