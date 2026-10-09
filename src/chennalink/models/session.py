from pydantic import BaseModel
from typing import Optional

class Session(BaseModel):
    session_id: Optional[str] = None
    session_code: str = ""
    device_id: Optional[str] = None
    device_name: str = ""
    email: str = ""
    status: str = "OFFLINE"
    participants: list = []
    is_host: bool = False
