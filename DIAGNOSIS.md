# Chennalink Diagnosis

## 1. Size Limit Cap
**Evidence:** 
- In `src/chennalink/app.py`, the client sets `max_size=max_bytes` based on `CHENNALINK_MAX_FILE_SIZE_MB`.
- In `src/chennalink/screens/send.py`, there is a strict check: `len(code.encode("utf-8")) > max_mb * 1024 * 1024`.
- However, the server backend (`backend/main.py`) does not enforce a chunking mechanism or a backend payload limit natively beyond Uvicorn's defaults. Sending a 10MB JSON string over a single WebSocket frame is risky and can block the event loop or hit Uvicorn's message size limit.
- **Proposed Fix:** Implement chunking for messages > 256 KB using `file_start`, `file_chunk`, `file_end` in both `src/chennalink/screens/send.py` (sender) and `src/chennalink/app.py` (receiver). Add backend support in `backend/main.py` to route these new chunk message types. Add backend validation for `CHENNALINK_MAX_FILE_SIZE_MB`.

## 2. SEND/RECEIVE Mixing & Storage
**Evidence:**
- The backend `backend/main.py` stores a single row per transfer in the `history` table: `INSERT INTO history (id, session_id, sender_device_id, receiver_device_id...)`.
- The `GET /api/history/{session_id}` route (`backend/routers/history.py`) fetches *all* messages for a session, which means both devices download the exact same rows, causing device A to see device B's internal states and vice versa if they rely on the backend.
- The client's `local_storage.py` dumps files locally but lacks a strict `owner_device_id` enforcement tied to backend confirmations (the client blindly writes to local storage before the backend confirms).
- **Proposed Fix:** 
  1. Update SQLite schema in `backend/database.py` to store one row per device (add `owner_device_id`, `direction`, `size_bytes`, `sha256`) and a `UNIQUE(owner_device_id, id)` constraint.
  2. Update `backend/main.py` to insert two rows per transfer (one for sender as `sent`, one for receiver as `received`).
  3. Update `GET /api/history/{session_id}` to filter by `owner_device_id` (passed via query param or headers).
  4. Ensure `send.py` only marks items as `sent` locally *after* a successful backend ACK, and `app.py` only marks items as `received` after all chunks are verified via SHA256.

## Files to touch:
- `backend/database.py` (Schema migration)
- `backend/main.py` (WebSocket routing, chunking support, 2-row insertion)
- `backend/routers/history.py` (Filter by owner)
- `src/chennalink/app.py` (Chunk assembly, WS chunk parsing)
- `src/chennalink/screens/send.py` (Chunk dispatch, wait for ACK)
- `src/chennalink/models/code_file.py` (Add sha256, size_bytes)
- `tests/*` (To verify chunking, limits, and separation)
