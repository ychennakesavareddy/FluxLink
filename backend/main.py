from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import json
import logging
import os
import hashlib
from uuid import uuid4
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import List, Optional

from backend.routers import sessions, history, files
from backend.ws import manager
from backend.repository import get_repository
from backend.storage import get_storage_service
from backend.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("chennalink.server")

storage_service = get_storage_service()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Validate production environment
    settings.validate_production()
    repo = get_repository()
    repo.init_schema()
    logger.info(f"Initialized database schema and repository ({repo.__class__.__name__}) in {settings.chennalink_env} mode.")
    yield

from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

app = FastAPI(title="Chennalink API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return RedirectResponse(url="/web/")

@app.get("/api/health")
def health_check():
    repo = get_repository()
    db_type = repo.__class__.__name__
    return {
        "status": "healthy",
        "database": db_type,
        "database_backend": settings.db_backend,
        "storage_backend": settings.storage_backend,
        "storage_bucket": settings.supabase_storage_bucket,
        "max_file_size_mb": settings.chennalink_max_file_size_mb,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(history.router, prefix="/api/history", tags=["history"])
app.include_router(files.router, prefix="/api/files", tags=["files"])

web_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
if os.path.isdir(web_dir):
    app.mount("/web", StaticFiles(directory=web_dir, html=True), name="web")

async def broadcast_status(session_id: str, session_code: str):
    repo = get_repository()
    all_participants = repo.get_participants(session_id)
    
    active_count = manager.get_active_count(session_id)
    session_conns = manager.active_connections.get(session_id, {})
    
    participants = []
    for d in all_participants:
        is_connected = (d["id"] in session_conns) or (d["device_id"] in session_conns)
        participants.append({
            "device_id": d["device_id"],
            "device_name": d["display_name"],
            "device_type": d.get("device_type", "cli"),
            "status": "CONNECTED" if is_connected else "DISCONNECTED"
        })
        
    msg = {
        "type": "status_update",
        "active_devices": active_count,
        "total_devices": 4, # Maximum capacity is 4
        "participants": participants
    }
    await manager.broadcast_to_session(json.dumps(msg), session_id)

@app.websocket("/ws/{session_code}/{device_id}")
async def websocket_endpoint(websocket: WebSocket, session_code: str, device_id: str):
    await websocket.accept()
    
    session_code = session_code.upper()
    repo = get_repository()
    
    # 1. Validate Session
    session_row = repo.get_session(session_code)
    if not session_row:
        logger.warning(f"WebSocket rejected: Invalid session code {session_code}")
        await websocket.close(code=1008, reason="INVALID SESSION")
        return
    if session_row["status"].lower() == "ended":
        logger.warning(f"WebSocket rejected: Session {session_code} has ended")
        await websocket.close(code=1008, reason="SESSION ENDED")
        return
    session_id = session_row["id"]
    
    # 2. Validate Participant/Device
    device_row = repo.get_participant(session_id, device_id)
    if not device_row:
        logger.warning(f"WebSocket rejected: Unregistered device {device_id} in session {session_code}")
        await websocket.close(code=1008, reason="UNREGISTERED DEVICE")
        return
        
    canonical_id = device_row["id"]
    client_dev_id = device_row["device_id"]
    device_name = device_row["display_name"]

    # 3. Connection count & Reconnection
    active_count = manager.get_active_count(session_id)
    is_reconnecting = manager.get_socket(session_id, [canonical_id, client_dev_id]) is not None
    
    if active_count >= 4 and not is_reconnecting:
        logger.warning(f"WebSocket rejected: Session {session_code} is full (4 active connections)")
        await websocket.close(code=1008, reason="SESSION FULL")
        return

    # Connect device with both canonical_id and client_dev_id as aliases
    device_keys = list(set([device_id, canonical_id, client_dev_id]))
    await manager.connect(websocket, session_id, device_keys)
    repo.update_participant_status(session_id, canonical_id, "connected")
    logger.info(f"WebSocket connected: {device_name} (ID: {canonical_id}) in session {session_code}. Active count: {manager.get_active_count(session_id)}")
    
    # Broadcast status to everyone in session
    await broadcast_status(session_id, session_code)

    try:
        while True:
            data = await websocket.receive_text()
            msg_dict = json.loads(data)
            msg_type = msg_dict.get("type")
            
            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue
                
            if msg_type in ["code_file", "file_bundle"]:
                created_at = datetime.now(timezone.utc).isoformat()
                
                files_to_send = []
                if msg_type == "code_file":
                    files_to_send = [{
                        "file_name": msg_dict.get("file_name") or "message.txt", 
                        "content": msg_dict.get("content", ""), 
                        "language": msg_dict.get("language", "python")
                    }]
                elif msg_type == "file_bundle":
                    files_to_send = msg_dict.get("files", [])
                
                # Determine receivers: all other participants in session
                all_participants = repo.get_participants(session_id)
                receivers = [
                    p for p in all_participants
                    if p["id"] not in [canonical_id, client_dev_id] and p["device_id"] not in [canonical_id, client_dev_id]
                ]
                logger.info(f"Routing {msg_type} from {device_name} ({canonical_id}) to {len(receivers)} registered peer(s)")
                
                for f in files_to_send:
                    # CRITICAL: Preserve exact bytes and text without stripping
                    raw_content = f["content"]
                    content_bytes = raw_content.encode("utf-8")
                    size_bytes = len(content_bytes)
                    
                    max_mb = int(os.environ.get("CHENNALINK_MAX_FILE_SIZE_MB", "10"))
                    max_bytes = max_mb * 1024 * 1024
                    if size_bytes > max_bytes:
                        err_msg = {"type": "error", "message": f"✗ FILE TOO LARGE: Maximum allowed size: {max_mb} MB"}
                        await websocket.send_text(json.dumps(err_msg))
                        logger.warning(f"File {f.get('file_name')} rejected: {size_bytes} bytes exceeds {max_bytes} bytes")
                        continue
                        
                    sha256 = hashlib.sha256(content_bytes).hexdigest()
                    msg_id = msg_dict.get("message_id", str(uuid4()))
                    
                    # Persist message in PostgreSQL / Supabase
                    metadata = {
                        "file_name": f["file_name"],
                        "language": f.get("language", "python"),
                        "peer_name": device_name,
                        "size_bytes": size_bytes,
                        "sha256": sha256,
                        "created_at": created_at
                    }
                    try:
                        repo.save_message(
                            session_id=session_id,
                            sender_device_id=canonical_id,
                            client_message_id=msg_id,
                            message_type="code" if msg_type == "code_file" else "file",
                            content=raw_content,
                            metadata=metadata,
                            recipient_device_id=None,
                            delivery_status="stored"
                        )
                    except Exception as e:
                        logger.error(f"Failed to persist message {msg_id}: {e}")
                        err_msg = {"type": "error", "message": f"✗ Message persistence failed: {e}"}
                        await websocket.send_text(json.dumps(err_msg))
                        continue
                    
                    out_msg = {
                        "type": "code_file",
                        "message_id": msg_id,
                        "session_id": session_id,
                        "sender_device_id": device_name,
                        "file_name": f["file_name"],
                        "content": raw_content,
                        "language": f.get("language", "python"),
                        "created_at": created_at,
                        "size_bytes": size_bytes,
                        "sha256": sha256
                    }
                    
                    delivered_count = 0
                    for r in receivers:
                        r_canonical = r["id"]
                        r_client = r["device_id"]
                        r_name = r["display_name"]
                        
                        target_ws = manager.get_socket(session_id, [r_canonical, r_client])
                        if target_ws:
                            try:
                                await target_ws.send_text(json.dumps(out_msg))
                                delivered_count += 1
                                logger.info(f"Delivered {f['file_name']} to recipient {r_name} ({r_canonical})")
                            except Exception as e:
                                logger.error(f"Failed to send to recipient {r_name} ({r_canonical}): {e}")
                        else:
                            logger.info(f"Recipient {r_name} ({r_canonical}) is registered but not actively connected via WebSocket")

                    if delivered_count > 0:
                        repo.update_message_delivery(session_id, msg_id, "delivered")
                            
                # Send ACK back to sender
                ack_msg = {"type": "ack", "message_id": msg_dict.get("message_id")}
                await websocket.send_text(json.dumps(ack_msg))
                
            elif msg_type == "file_start":
                file_size = msg_dict.get("file_size", 0)
                max_mb = int(os.environ.get("CHENNALINK_MAX_FILE_SIZE_MB", "10"))
                max_bytes = max_mb * 1024 * 1024
                if file_size > max_bytes:
                    err_msg = {"type": "error", "message": f"✗ FILE TOO LARGE: Maximum allowed size: {max_mb} MB"}
                    await websocket.send_text(json.dumps(err_msg))
                    logger.warning(f"File transfer rejected: {file_size} bytes exceeds limit of {max_bytes} bytes")
                    continue

                if not hasattr(manager, 'chunk_buffers'):
                    manager.chunk_buffers = {}
                transfer_id = msg_dict.get("transfer_id")
                manager.chunk_buffers[transfer_id] = {
                    "file_name": msg_dict.get("file_name"),
                    "file_size": msg_dict.get("file_size"),
                    "total_chunks": msg_dict.get("total_chunks"),
                    "sha256": msg_dict.get("sha256"),
                    "language": msg_dict.get("language", "python"),
                    "chunks": {}
                }
                await websocket.send_text(json.dumps({"type": "ack", "message_id": transfer_id}))
                logger.info(f"Started chunked transfer {transfer_id} for file {msg_dict.get('file_name')} ({file_size} bytes, {msg_dict.get('total_chunks')} chunks)")
                
            elif msg_type == "file_chunk":
                transfer_id = msg_dict.get("transfer_id")
                if hasattr(manager, 'chunk_buffers') and transfer_id in manager.chunk_buffers:
                    manager.chunk_buffers[transfer_id]["chunks"][msg_dict.get("index")] = msg_dict.get("chunk")
                await websocket.send_text(json.dumps({"type": "ack", "message_id": f"{transfer_id}_{msg_dict.get('index')}"}))
                
            elif msg_type == "file_end":
                transfer_id = msg_dict.get("transfer_id")
                if hasattr(manager, 'chunk_buffers') and transfer_id in manager.chunk_buffers:
                    buf = manager.chunk_buffers[transfer_id]
                    import base64
                    assembled_bytes = b"".join([base64.b64decode(buf["chunks"][i]) for i in range(buf["total_chunks"])])
                    actual_sha256 = hashlib.sha256(assembled_bytes).hexdigest()
                    
                    if actual_sha256 == buf["sha256"] and len(assembled_bytes) == buf["file_size"]:
                        content = assembled_bytes.decode("utf-8", errors="replace")
                        logger.info(f"Chunked transfer {transfer_id} ({buf['file_name']}) assembled successfully. Size: {buf['file_size']} bytes. SHA256 matches.")
                        
                        created_at = datetime.now(timezone.utc).isoformat()
                        
                        try:
                            # Upload to private Supabase Storage bucket
                            storage_path, storage_bucket = storage_service.upload_file(
                                session_id=session_id,
                                filename=buf["file_name"],
                                data=assembled_bytes
                            )

                            # Record in file_transfers
                            ft_record = repo.save_file_transfer(
                                session_id=session_id,
                                sender_device_id=canonical_id,
                                file_name=buf["file_name"],
                                size_bytes=buf["file_size"],
                                sha256=actual_sha256,
                                storage_path=storage_path,
                                storage_bucket=storage_bucket,
                                transfer_status="completed"
                            )
                            
                            # Record in messages
                            metadata = {
                                "file_name": buf["file_name"],
                                "language": buf["language"],
                                "peer_name": device_name,
                                "size_bytes": buf["file_size"],
                                "sha256": actual_sha256,
                                "storage_path": storage_path,
                                "storage_bucket": storage_bucket,
                                "transfer_id": transfer_id
                            }
                            repo.save_message(
                                session_id=session_id,
                                sender_device_id=canonical_id,
                                client_message_id=transfer_id,
                                message_type="file",
                                content=content,
                                metadata=metadata,
                                recipient_device_id=None,
                                delivery_status="stored"
                            )
                        except Exception as e:
                            logger.error(f"Failed to persist chunked file {transfer_id}: {e}")
                            err_msg = {"type": "error", "message": f"✗ File persistence failed: {e}"}
                            await websocket.send_text(json.dumps(err_msg))
                            if transfer_id in manager.chunk_buffers:
                                del manager.chunk_buffers[transfer_id]
                            continue

                        # Clean up buffer after successful upload
                        if transfer_id in manager.chunk_buffers:
                            del manager.chunk_buffers[transfer_id]

                        all_participants = repo.get_participants(session_id)
                        receivers = [
                            p for p in all_participants
                            if p["id"] not in [canonical_id, client_dev_id] and p["device_id"] not in [canonical_id, client_dev_id]
                        ]
                        logger.info(f"Routing assembled file {buf['file_name']} to {len(receivers)} peer(s)")
                        
                        out_msg = {
                            "type": "code_file",
                            "message_id": transfer_id,
                            "session_id": session_id,
                            "sender_device_id": device_name,
                            "file_name": buf["file_name"],
                            "content": content,
                            "language": buf["language"],
                            "created_at": created_at,
                            "size_bytes": buf["file_size"],
                            "sha256": buf["sha256"],
                            "storage_path": storage_path
                        }
                        
                        delivered_count = 0
                        for r in receivers:
                            r_canonical = r["id"]
                            r_client = r["device_id"]
                            r_name = r["display_name"]
                            
                            target_ws = manager.get_socket(session_id, [r_canonical, r_client])
                            if target_ws:
                                try:
                                    await target_ws.send_text(json.dumps(out_msg))
                                    delivered_count += 1
                                    logger.info(f"Delivered chunked file {buf['file_name']} to recipient {r_name} ({r_canonical})")
                                except Exception as e:
                                    logger.error(f"Failed to send to recipient {r_name} ({r_canonical}): {e}")
                            else:
                                logger.info(f"Recipient {r_name} ({r_canonical}) is registered but not actively connected via WebSocket")
                                
                        if delivered_count > 0:
                            repo.update_message_delivery(session_id, transfer_id, "delivered")
                    else:
                        logger.error(f"Chunked transfer {transfer_id} verification failed: expected SHA {buf['sha256']}, got {actual_sha256}")
                        err_msg = {"type": "error", "message": "✗ Transfer verification failed: SHA-256 hash mismatch"}
                        await websocket.send_text(json.dumps(err_msg))
                        
            elif msg_type == "ack":
                ack_msg_id = msg_dict.get("message_id")
                repo.update_message_delivery(session_id, ack_msg_id, "delivered")
                logger.info(f"ACK received from {device_name} ({canonical_id}) for message {ack_msg_id}")

            elif msg_type == "end_session":
                try:
                    repo.end_session(session_code, canonical_id)
                    await manager.broadcast_to_session(json.dumps({
                        "type": "session_ended",
                        "message": "Host has ended the session."
                    }), session_id)
                    logger.info(f"Host {device_name} ({canonical_id}) ended session {session_code}")
                except Exception as e:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"Could not end session: {e}"
                    }))

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {device_name} ({canonical_id}) from session {session_code}")
    except Exception as e:
        logger.error(f"WebSocket error for {device_name} ({canonical_id}): {e}")
    finally:
        manager.disconnect(session_id, websocket)
        repo.update_participant_status(session_id, canonical_id, "disconnected")
        await broadcast_status(session_id, session_code)
