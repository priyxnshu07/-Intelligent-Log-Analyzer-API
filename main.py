from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Optional
from database import engine, get_db, Base
from models import Log
from schemas import LogCreate, LogEntry
from agent_routes import router as agent_router
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Intelligent Log Analyzer API",
    description="A centralized logging server with AI-powered diagnostics.",
    version="2.0.0",
)

# Include agent routes
app.include_router(agent_router, prefix="/agent", tags=["agent"])

@app.get("/", response_class=HTMLResponse, summary="Root endpoint")
def read_root():
    try:
        with open("dashboard.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>Welcome to Intelligent Log Analyzer API</h1><p>Dashboard not found.</p>"

@app.post("/ingest/", response_model=LogEntry, summary="Ingest a new log entry")
def ingest_log(log: LogCreate, db: Session = Depends(get_db)):
    # Map extra_info field to metadata_json in model
    log_data = log.model_dump(by_alias=False)
    extra = log_data.pop("extra_info", None)
    
    db_log = Log(**log_data, metadata_json=extra)
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    
    # Return a dictionary to avoid Pydantic looking at ORM internal attributes
    return {
        "id": db_log.id,
        "timestamp": db_log.timestamp,
        "service_name": db_log.service_name,
        "log_level": db_log.log_level,
        "message": db_log.message,
        "metadata": db_log.metadata_json
    }

@app.get("/query/", response_model=List[LogEntry], summary="Query log entries")
def query_logs(level: Optional[str] = None, search: Optional[str] = None, limit: int = 100, db: Session = Depends(get_db)):
    query = db.query(Log)
    if level:
        query = query.filter(Log.log_level == level)
    if search:
        query = query.filter(Log.message.contains(search))
    
    logs = query.order_by(Log.id.desc()).limit(limit).all()
    
    # Map to list of dicts
    result = []
    for log in logs:
        result.append({
            "id": log.id,
            "timestamp": log.timestamp,
            "service_name": log.service_name,
            "log_level": log.log_level,
            "message": log.message,
            "metadata": log.metadata_json
        })
        
    return result

@app.get("/summary/", summary="Get a summary of log counts by level")
def get_summary(db: Session = Depends(get_db)):
    summary = (
        db.query(Log.log_level, func.count(Log.log_level).label("count"))
        .group_by(Log.log_level)
        .all()
    )
    return {level: count for level, count in summary}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
