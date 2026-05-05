from sqlalchemy import Column, Integer, String, JSON
from database import Base

class Log(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(String, index=True)
    service_name = Column(String, index=True, nullable=True)
    log_level = Column('level', String, index=True)  # Map to existing 'level' column
    message = Column(String)
    metadata_json = Column('metadata', JSON, nullable=True) # Map to 'metadata' column
