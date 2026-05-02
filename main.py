
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, Column, Integer, String, func
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
from pydantic import BaseModel
from typing import List, Optional
import os

# --- Configuration ---
DATABASE_URL = "sqlite:///./test.db"

# --- Database Setup ---
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- SQLAlchemy Models ---
class Log(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(String, index=True)
    level = Column(String, index=True)
    message = Column(String)

Base.metadata.create_all(bind=engine)

# --- Pydantic Models ---
class LogBase(BaseModel):
    timestamp: str
    level: str
    message: str

class LogCreate(LogBase):
    pass

class LogEntry(LogBase):
    id: int

    class Config:
        from_attributes = True

# --- FastAPI Application ---
app = FastAPI(
    title="Intelligent Log Analyzer API",
    description="A demonstration API to ingest, query, and summarize log data. Built with Python, FastAPI, and SQLAlchemy.",
    version="1.0.0",
)

# --- Dependency Injection ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- API Endpoints ---
@app.get("/", response_class=HTMLResponse, summary="Root endpoint")
def read_root():
    with open("dashboard.html", "r") as f:
        return f.read()

@app.post("/ingest/", response_model=LogEntry, summary="Ingest a new log entry")
def ingest_log(log: LogCreate, db: Session = Depends(get_db)):
    db_log = Log(**log.dict())
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return db_log

@app.get("/query/", response_model=List[LogEntry], summary="Query log entries")
def query_logs(level: Optional[str] = None, search: Optional[str] = None, limit: int = 100, db: Session = Depends(get_db)):
    query = db.query(Log)
    if level:
        query = query.filter(Log.level == level)
    if search:
        query = query.filter(Log.message.contains(search))
    return query.limit(limit).all()

@app.get("/summary/", summary="Get a summary of log counts by level")
def get_summary(db: Session = Depends(get_db)):
    summary = (
        db.query(Log.level, func.count(Log.level).label("count"))
        .group_by(Log.level)
        .all()
    )
    return {level: count for level, count in summary}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
