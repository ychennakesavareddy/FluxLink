try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FastAPI = None
    WebSocket = None
    WebSocketDisconnect = None
    HTTPException = None
    uvicorn = None
    FASTAPI_AVAILABLE = False

from pydantic import BaseModel
import random
import string
import json
import uuid
from typing import Dict, Optional, List

if FASTAPI_AVAILABLE:
    app = FastAPI(title="Chennalink Local Server")
else:
    app = None

# In-memory storage
# sessions = { "SESSION_CODE": { "id": "uuid", "devices": { "device_id": {"name": "...", "ws": websocket_or_none} } } }
sessions = {}

def generate_code():
    chars = "ABCDEFGHJKMNPQRSTUVWXYZ23456789" # Exclude O, 0, 1, I, L
    return "".join(random.choices(chars, k=6))

class CreateSessionReq(BaseModel):
    email: str
    name: str
    device_id: str
    device_name: str
    session_code: str

class JoinSessionReq(BaseModel):
    email: str
    name: str
    device_id: str
    device_name: str
    session_code: str

@app.post("/api/sessions/create")
def create_session(req: CreateSessionReq):
    code = req.session_code.upper()
    if len(code) != 6 or not code.isalnum():
        raise HTTPException(status_code=400, detail="Code must be exactly 6 alphanumeric characters")
        
    if code in sessions:
        raise HTTPException(status_code=400, detail="Session code already in use")
        
    session_id = str(uuid.uuid4())
    sessions[code] = {
        "id": session_id,
        "devices": {
            req.device_id: {"name": req.name, "email": req.email, "ws": None}
        },
        "history": []
    }
    return {"session_id": session_id, "session_code": code, "device_id": req.device_id}

@app.post("/api/sessions/join")
def join_session(req: JoinSessionReq):
    code = req.session_code.upper()
    if code not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
        
    session = sessions[code]
    
    if req.device_id not in session["devices"]:
        if len(session["devices"]) >= 2:
            raise HTTPException(status_code=403, detail="SESSION FULL")
        session["devices"][req.device_id] = {"name": req.name, "email": req.email, "ws": None}
        
    return {"session_id": session["id"], "session_code": code, "device_id": req.device_id}

@app.get("/api/history/{session_id}")
def get_history(session_id: str, limit: int = 50, offset: int = 0):
    for code, sess in sessions.items():
        if sess["id"] == session_id:
            # Sort desc, paginate
            hist = sorted(sess["history"], key=lambda x: x["created_at"], reverse=True)
            return {"items": hist[offset:offset+limit], "total": len(hist)}
    return {"items": [], "total": 0}

async def broadcast_status(code: str):
    session = sessions[code]
    active_devices = sum(1 for d in session["devices"].values() if d["ws"] is not None)
    
    msg = {
        "type": "status_update",
        "active_devices": active_devices,
        "total_devices": len(session["devices"])
    }
    
    for device_id, data in session["devices"].items():
        ws = data["ws"]
        if ws:
            try:
                await ws.send_text(json.dumps(msg))
            except:
                pass

@app.websocket("/ws/{session_code}/{device_id}")
async def websocket_endpoint(websocket: WebSocket, session_code: str, device_id: str):
    session_code = session_code.upper()
    if session_code not in sessions:
        await websocket.close(code=1008)
        return
        
    session = sessions[session_code]
    if device_id not in session["devices"]:
        await websocket.close(code=1008)
        return
        
    await websocket.accept()
    session["devices"][device_id]["ws"] = websocket
    
    # Broadcast join
    await broadcast_status(session_code)
    
    try:
        while True:
            data = await websocket.receive_text()
            msg_dict = json.loads(data)
            msg_type = msg_dict.get("type")
            
            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue
                
            if msg_type in ["code_file", "file_bundle"]:
                from datetime import datetime
                created_at = datetime.now().isoformat()
                
                # Forward to other device(s)
                for d_id, d_data in session["devices"].items():
                    if d_id != device_id:
                        out_msg = msg_dict.copy()
                        out_msg["created_at"] = created_at
                        out_msg["sender_device_id"] = device_id
                        
                        # Store in history
                        # We extract single files if bundle for history
                        if msg_type == "code_file":
                            hist_msg = {
                                "id": msg_dict.get("message_id", str(uuid.uuid4())),
                                "session_id": session["id"],
                                "sender_device_id": device_id,
                                "receiver_device_id": d_id,
                                "file_name": msg_dict.get("file_name"),
                                "language": msg_dict.get("language", "python"),
                                "content": msg_dict.get("content"),
                                "created_at": created_at,
                                "status": "delivered"
                            }
                            session["history"].append(hist_msg)
                        
                        # Send to WS
                        if d_data["ws"]:
                            await d_data["ws"].send_text(json.dumps(out_msg))
                            
                # Send ack back
                ack_msg = {"type": "ack", "message_id": msg_dict.get("message_id")}
                await websocket.send_text(json.dumps(ack_msg))
                
    except WebSocketDisconnect:
        session["devices"][device_id]["ws"] = None
        await broadcast_status(session_code)

if __name__ == "__main__":
    uvicorn.run("chennalink.server:app", host="127.0.0.1", port=8000, reload=True)
