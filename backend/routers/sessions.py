from fastapi import APIRouter, HTTPException
import json
from backend.models.schemas import SessionCreate, SessionJoin, SessionResponse, SessionEnd
from backend.repository import get_repository
from backend.ws import manager

router = APIRouter()

@router.post("/create", response_model=SessionResponse)
def create_session(data: SessionCreate):
    session_code = data.session_code.upper()
    if len(session_code) != 6 or not session_code.isalnum():
        raise HTTPException(status_code=400, detail="Code must be exactly 6 alphanumeric characters")

    repo = get_repository()
    session, participant = repo.create_session(
        session_code=session_code,
        host_device_id=data.device_id,
        host_display_name=data.device_name or data.name,
        host_email=data.email,
        host_device_type=data.device_type
    )

    return SessionResponse(
        session_id=session["id"],
        session_code=session["session_code"],
        device_id=participant["id"]
    )

@router.post("/join", response_model=SessionResponse)
def join_session(data: SessionJoin):
    session_code = data.session_code.upper()
    repo = get_repository()

    session_obj = repo.get_session(session_code)
    active_count = 0
    if session_obj:
        active_count = manager.get_active_count(session_obj["id"])

    session, participant = repo.join_session(
        session_code=session_code,
        device_id=data.device_id,
        display_name=data.device_name or data.name,
        email=data.email,
        device_type=data.device_type,
        active_count=active_count,
        max_limit=4
    )

    return SessionResponse(
        session_id=session["id"],
        session_code=session["session_code"],
        device_id=participant["id"]
    )

@router.post("/end")
async def end_session(data: SessionEnd):
    session_code = data.session_code.upper()
    repo = get_repository()

    session = repo.end_session(
        session_code=session_code,
        device_id=data.device_id
    )

    # Broadcast session_ended to all participants
    await manager.broadcast_to_session(json.dumps({
        "type": "session_ended",
        "message": "Host has ended the session."
    }), session["id"])

    return {"status": "ended"}
