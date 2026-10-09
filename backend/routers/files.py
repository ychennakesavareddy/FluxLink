import hashlib
from fastapi import APIRouter, HTTPException, Query, Response
from typing import Optional
from backend.repository import get_repository
from backend.storage import get_storage_service

router = APIRouter()
storage_service = get_storage_service()

@router.get("/download/{session_id}/{identifier:path}")
def download_file(session_id: str, identifier: str, device_id: str = Query(...)):
    repo = get_repository()
    # 1. Authorize participant in session
    session = repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    participant = repo.get_participant(session["id"], device_id)
    if not participant:
        raise HTTPException(status_code=403, detail="Unauthorized device for this session")

    # 2. Retrieve file transfer record
    transfer = repo.get_file_transfer(session["id"], identifier)
    if not transfer:
        # Try finding by filename or raw path
        transfer = repo.get_file_transfer(session["id"], f"{session['id']}/{identifier}")
    
    if not transfer:
        raise HTTPException(status_code=404, detail="File transfer not found")

    # 3. Retrieve file bytes from private storage
    try:
        data = storage_service.download_file(transfer["storage_path"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve file from storage: {e}")

    # 4. Verify SHA-256 integrity
    if transfer.get("sha256"):
        actual_sha = hashlib.sha256(data).hexdigest()
        if actual_sha != transfer["sha256"]:
            raise HTTPException(status_code=500, detail="Downloaded file failed SHA-256 integrity verification")

    # 5. Return file stream with exact bytes preserved
    filename = transfer["file_name"]
    content_type = transfer.get("content_type") or "application/octet-stream"
    
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(data))
        }
    )

@router.get("/signed-url/{session_id}/{identifier:path}")
def get_signed_url(session_id: str, identifier: str, device_id: str = Query(...)):
    repo = get_repository()
    session = repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    participant = repo.get_participant(session["id"], device_id)
    if not participant:
        raise HTTPException(status_code=403, detail="Unauthorized device for this session")

    transfer = repo.get_file_transfer(session["id"], identifier)
    if not transfer:
        raise HTTPException(status_code=404, detail="File transfer not found")

    signed_url = storage_service.create_signed_url(transfer["storage_path"], expires_in=3600)
    return {
        "signed_url": signed_url,
        "file_name": transfer["file_name"],
        "size_bytes": transfer["size_bytes"],
        "sha256": transfer["sha256"],
        "expires_in": 3600
    }
