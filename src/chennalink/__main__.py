from chennalink.app import main

import sys
import os
from chennalink.app import main, ChennaLinkApp

def cli():
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "send" and len(sys.argv) > 2:
            path = sys.argv[2]
            if os.path.isfile(path):
                # Start app with intent to send this file
                app = ChennaLinkApp(send_file_on_startup=path)
                app.run()
                return
            else:
                print(f"File not found: {path}")
                sys.exit(1)
                
    main()

if __name__ == "__main__":
    cli()
