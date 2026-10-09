# Running Chennalink (CLI + Web Together)

Chennalink is a real-time peer-to-peer code transfer tool with support for **both terminal (Textual TUI) and browser (Web)** clients connected to the same session backend.

---

## ⚡ Option 1: Automatic One-Click Startup (Recommended)

### A. Via Double-Click / Command Prompt:
Simply double-click or run:
```cmd
.\start_all.bat
```
*(Does not require PowerShell script execution permissions!)*

### B. Via PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File .\run_chennalink.ps1
```

This script automatically:
1. Detects if the backend is already running on port `8000`.
2. Starts the **FastAPI backend** in its own PowerShell window (if not already running).
3. Waits for the backend to be healthy.
4. Opens the **interactive CLI interface** in a dedicated PowerShell window.
5. Launches the **Web interface** in your default web browser (`http://127.0.0.1:8000/web/`).

---

## 🛠 Option 2: Manual Startup (Step-by-Step)

If you prefer to start each component manually in separate terminal tabs/windows:

### Step 1: Start the Backend (Terminal 1)
Activate the virtual environment and start Uvicorn:

```powershell
cd C:\Users\yenug\OneDrive\Desktop\p2p\chennalink
.\.venv\Scripts\Activate.ps1
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```
*Backend is accessible at: `http://127.0.0.1:8000`*

### Step 2: Start the CLI Client (Terminal 2)
In a second terminal window, run the CLI:

```powershell
cd C:\Users\yenug\OneDrive\Desktop\p2p\chennalink
.\.venv\Scripts\Activate.ps1
chennalink
```
*(Alternatively: `python -m chennalink`)*

### Step 3: Open the Web Client (Browser)
The FastAPI backend serves the web interface directly at:

👉 **[http://127.0.0.1:8000/web/](http://127.0.0.1:8000/web/)**

Simply open this link in any browser (Chrome, Edge, Firefox).

*(Optional: If you wish to serve the `web/` folder with a separate static server on port 8080)*:
```powershell
python -m http.server 8080 --directory web
```
*Then visit `http://127.0.0.1:8080/`.*

---

## 🔄 Using CLI and Web Together in a Session

1. **Create Session**:
   - In either the **CLI** or **Web client**, click **Create Session**.
   - Choose a 6-character alphanumeric code (e.g. `ABC123`).
   - The status will show `● WAITING FOR SECOND DEVICE (1 / 4)`.

2. **Join Session**:
   - On the other client, select **Connect Session** / **Join Session**.
   - Enter the same 6-character code `ABC123`.
   - Once connected, both interfaces immediately update to `● CONNECTED (2 / 4)`.

3. **Transfer Code**:
   - **CLI to Web**: Paste or load code into the CLI editor and press `SEND`. The file appears immediately in the Web client's **Received Files** section with full fidelity.
   - **Web to CLI**: Paste or type code into the Web client and click **Send to All**. The file arrives in real-time in the CLI's **RECEIVE** tab with full notification.

4. **Multi-Client Capacity**:
   - Up to 4 active participants can join simultaneously (any mix of CLI and Web clients, e.g. 2 CLI + 2 Web).
   - Reconnections reuse existing device slots without consuming additional capacity.
