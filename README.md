# FluxLink

FluxLink is a high-speed developer tool and real-time collaboration bridge designed for instant, lossless source-code and file transfers across devices (Web and Terminal/CLI).

## Features

- **Exact Code Formatting**: Preserves 100% byte-for-byte exact indentation, spaces, and formatting for Python and all codebases.
- **WhatsApp-Style Chat UI**: Interactive, responsive modern interface across both Web browser and Python Textual terminal CLI.
- **Real-Time WebSockets**: Instant synchronization between Web clients and CLI terminals.
- **Production-Ready Storage**: Backed by Supabase PostgreSQL for session persistence and private Supabase Storage for secure, chunked file transfers.
- **End-to-End Reliability**: Chunked streaming, checksum validation (SHA-256), and deduplication.

## Installation

```bash
pip install -e .
```

## Running

### CLI Application
```bash
chennalink
# or
python -m chennalink
```

### Backend Server
```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

## Configuration

Copy `.env.example` to `.env` and fill in your Supabase database and storage credentials:

```bash
cp .env.example .env
```

