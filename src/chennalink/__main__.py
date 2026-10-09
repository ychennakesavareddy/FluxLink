import sys
import os
import argparse
from chennalink.app import main, ChennaLinkApp

CLI_HELP_TEXT = """
FluxLink CLI — Real-time lossless source-code and file transfer bridge

USAGE:
    fluxlink [COMMAND] [OPTIONS]

COMMANDS:
    (no command)         Launch interactive TUI
    send <filepath>      Launch TUI and preload file for immediate transfer
    receive              Launch TUI directly in the incoming Receive queue
    history              Launch TUI directly in the Transfer History screen
    session              Launch TUI directly in the Active Session details screen
    help                 Show this usage information

OPTIONS:
    --backend, -b <url>  Override backend server URL
                         (Default: https://fluxlinkbackend.chennareddy.in)
    --version, -v        Show FluxLink version

KEYBOARD SHORTCUTS IN TUI:
    Ctrl + T             WhatsApp-style Real-time Chat Timeline
    Ctrl + 1             Send File / Source Code Screen
    Ctrl + 2             Receive Files Queue
    Ctrl + 3             Transfer History
    Ctrl + 4             Active Session Details
    Ctrl + H             In-app Help & Cheatsheet
    Ctrl + Q             Quit Application
"""

def cli():
    args = sys.argv[1:]
    
    backend_url = None
    initial_screen = None
    send_file = None

    # Parse --backend / -b flag if present
    i = 0
    clean_args = []
    while i < len(args):
        if args[i] in ("--backend", "-b") and i + 1 < len(args):
            backend_url = args[i + 1]
            i += 2
        elif args[i].startswith("--backend="):
            backend_url = args[i].split("=", 1)[1]
            i += 1
        elif args[i] in ("--help", "-h", "help"):
            print(CLI_HELP_TEXT)
            return
        elif args[i] in ("--version", "-v"):
            print("FluxLink CLI v0.1.0")
            return
        else:
            clean_args.append(args[i])
            i += 1

    if clean_args:
        cmd = clean_args[0].lower()
        if cmd == "send":
            if len(clean_args) > 1:
                path = clean_args[1]
                if os.path.isfile(path):
                    send_file = path
                    initial_screen = "send"
                else:
                    print(f"Error: File not found: {path}")
                    sys.exit(1)
            else:
                initial_screen = "send"
        elif cmd == "receive":
            initial_screen = "receive"
        elif cmd == "history":
            initial_screen = "history"
        elif cmd == "session":
            initial_screen = "session"
        elif os.path.isfile(clean_args[0]):
            # Directly called with a file path: fluxlink script.py
            send_file = clean_args[0]
            initial_screen = "send"

    app = ChennaLinkApp(
        send_file_on_startup=send_file,
        backend_url=backend_url,
        initial_screen=initial_screen
    )
    app.run()

if __name__ == "__main__":
    cli()
