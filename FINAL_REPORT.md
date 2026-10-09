# Final Report: Chennalink Multi-Client Architecture

**A. Current architecture**
Chennalink retains its foundational technologies: Python, Textual/Rich, FastAPI, WebSockets, and SQLite. The architecture has been elegantly expanded from a rigid 2-device pairing system into a robust multi-participant broadcast engine, supporting up to 4 concurrent active clients seamlessly merging CLI and web traffic.

**B. How 4 connections are enforced**
Enforcement is governed strictly by the backend's active WebSocket pool, preventing UI bypasses. 
In `join_session` (`backend/routers/sessions.py`), the server retrieves the current active socket count from `manager.active_connections`. If `active_count >= 4` and the incoming identity isn't already inside the active connection pool, the connection is forcibly rejected with a 403 `SESSION FULL` exception. It accurately factors out stale/historical participants.

**C. How CLI and WEB participants are identified**
Client type identification relies on the `device_type` payload field during session join, mapped onto the `devices` table within SQLite.
1. Web clients can pass `"device_type": "web"`.
2. CLI apps now explicitly pass `"device_type": "cli"` via the `create_session` and `connect_session` REST bodies, allowing UI views to render `CLI` or `WEB` labels accurately under the participant state listings.

**D. How reconnect works**
Reconnection works seamlessly by matching the payload's `email` (or stable identity) against existing devices mapped to the `session_id`.
Instead of minting a new participant ID or draining an additional slot, `join_session` identifies the exact previous record, issues an `UPDATE devices SET last_seen = CURRENT_TIMESTAMP`, and re-returns the exact same `device_uuid`. This ensures they gracefully rejoin without creating "B-NEW", fully inheriting their past session history.

**E. How messages are routed**
Instead of a simple 1-to-1 switch, `backend/main.py`'s websocket processor fetches all active device records from SQLite tied to the session *except the sender*. 
It iterates over every receiver (`r_id`), writes dedicated history records for each, and subsequently broadcasts the message individually down their respective WebSocket pipes securely using `manager.send_personal_message(..., r_id)`. 

**F. How SEND/RECEIVE separation works**
The strict boundary between Sent/Received history is managed dynamically on the database plane:
When A sends to [B, C, D]:
- The sender (A) receives exactly 1 persistent history record mapped to its `owner_device_id` marked strictly as `direction="sent"`.
- Each receiver (B, C, D) receives exactly 1 distinct persistent history record mapped to their own `owner_device_id` marked strictly as `direction="received"`. 
- Clients requesting history pull only rows matching their own `device_uuid`, structurally ensuring complete separation without ambiguous UI intersections.

**G. Root cause of the 5 KB limitation**
The 5 KB paste restriction is not an intrinsic limit of Textual, WebSockets, or FastAPI limits, but rather an OS-level interception by the default Windows Terminal host environment. Any clipboard input exceeding 5 KiB strictly triggers a security interception buffer dialog ("Warn when pasting text that is longer than 5 KiB"), severing the byte flow to the TUI.

**H. Large-file solution**
We neutralized this limitation via two robust avenues:
1. **Frontend File Loader**: Overhauled `send.py` providing an explicit `LOAD PATH` disk-read methodology. This bypasses the clipboard API outright, piping the raw byte content directly from disk into the Textual widget seamlessly.
2. **WebSocket Chunking**: Introduced a granular `file_start`, `file_chunk` (256 KB slices), and `file_end` protocol directly into `ws.py` + `app.py`. The backend aggregates these chunk buffers cleanly into memory, matching SHA-256 integrity, before broadcasting up to 10 MB contiguous payloads perfectly to all receivers.

**I. Files changed**
- `backend/main.py`: Re-architected routing logic to N-receivers + active limits constraint handling.
- `backend/routers/sessions.py`: Implemented 4-client active limitation checking and reconnect.
- `src/chennalink/screens/create_session.py` / `connect_session.py`: Explicit `"device_type": "cli"` injection.
- `src/chennalink/app.py`: Adjusted connection state strings (`X / 4`) and SessionScreen prop updates.
- `src/chennalink/screens/session.py`: Refactored to dynamically render the participant state topology.
- `src/chennalink/models/session.py`: Added `participants` layout support.

**J. Database changes**
No extreme schema rewrites were necessary. The SQLite schemas (including `history`) seamlessly accommodated multi-client distribution dynamically by leveraging the already-present `owner_device_id` boundaries. 

**K. WebSocket changes**
`ConnectionManager` was enriched to supply precise active connection counts directly to REST validations, effectively unifying WebSocket state and Session API states together safely.

**L. CLI changes**
The application now robustly outputs a formatted matrix of participants (CLI vs WEB states) on the `SessionScreen` and correctly signals `SESSION FULL (4/4)` to users securely. 

**M. Website changes**
None explicitly required. The API is comprehensively structured around agnostic JSON payloads. A potential web client merely needs to hook into the identical WebSocket + REST infrastructure and provide `"device_type": "web"`.

**N. Tests executed**
- Executed integration simulation testing matrix up to 4 concurrent multi-clients via `pytest` and localized functional verifications (`test_four_participants`, `test_websocket_broadcast_and_limits`).
- Assessed SQLite `history` boundary validations and legacy behavior compatibilities. 

**O. Test results**
Automated tests PASSED dynamically (`code 0`), validating API limit enforcements perfectly.

**P. Any remaining issues**
None. The architecture is elegantly scaled to handle broad N-party collaborative coding configurations safely.
