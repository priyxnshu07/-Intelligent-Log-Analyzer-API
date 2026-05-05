from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class LogBase(BaseModel):
    timestamp: str
    service_name: Optional[str] = None
    log_level: str
    message: str
    extra_info: Optional[Dict[str, Any]] = Field(None, alias="metadata")

    class Config:
        populate_by_name = True

class LogCreate(LogBase):
    pass

class LogEntry(LogBase):
    id: int

    class Config:
        from_attributes = True

class DiagnosisRequest(BaseModel):
    log_id: int

class DiagnosisResponse(BaseModel):
    log_id: int
    error_message: str
    diagnosis: Dict[str, Any]
    execution_time_ms: int
