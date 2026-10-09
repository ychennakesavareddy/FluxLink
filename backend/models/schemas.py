from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from uuid import UUID

class SessionCreate(BaseModel):
    email: str
    name: str
    device_id: str
    device_name: str
    session_code: str
    device_type: str = "TUI"

class SessionJoin(BaseModel):
    email: str
    name: str
    device_id: str
    device_name: str
    session_code: str
    device_type: str = "TUI"

class SessionResponse(BaseModel):
    session_id: str
    session_code: str
    device_id: str

class SessionEnd(BaseModel):
    session_code: str
    device_id: str

class FileContent(BaseModel):
    file_name: str
    content: str
    language: str = "python"

class WSMessage(BaseModel):
    type: str # 'code_file', 'file_bundle', 'ack', 'ping', 'pong'
    message_id: str
    session_id: str
    sender_device_id: str
    file_name: Optional[str] = None
    language: Optional[str] = None
    content: Optional[str] = None
    files: Optional[List[FileContent]] = None
    created_at: Optional[str] = None
