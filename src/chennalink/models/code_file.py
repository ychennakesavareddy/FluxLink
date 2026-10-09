import uuid
from datetime import datetime
from pydantic import BaseModel, Field

class CodeFile(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    language: str = "python"
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    direction: str = "sent" # "sent" or "received"
    status: str = "sent" # "queued", "sent", "received"
    sender: str = "LOCAL"
