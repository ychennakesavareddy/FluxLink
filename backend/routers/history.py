from fastapi import APIRouter, HTTPException
from typing import Optional
from backend.repository import get_repository

router = APIRouter()

@router.get("/{session_id}")
def get_history(
    session_id: str,
    device_id: str,
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None
):
    repo = get_repository()
    return repo.get_history(
        session_code_or_id=session_id,
        device_id=device_id,
        limit=limit,
        offset=offset,
        search=search
    )

@router.delete("/{session_id}/{message_id}")
def delete_message(session_id: str, message_id: str, device_id: str):
    repo = get_repository()
    success = repo.delete_message(
        session_code_or_id=session_id,
        message_id=message_id,
        device_id=device_id
    )
    if not success:
        raise HTTPException(status_code=404, detail="Message not found or already deleted")
    return {"status": "deleted"}

@router.get("/{session_id}/{message_id}")
def get_message(session_id: str, message_id: str, device_id: str):
    repo = get_repository()
    msg = repo.get_message(
        session_code_or_id=session_id,
        message_id=message_id,
        device_id=device_id
    )
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    return msg
