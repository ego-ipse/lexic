"""CLI — ``python -m opsis [port]`` serves the current directory."""

from __future__ import annotations

import sys
from pathlib import Path

from opsis.praxis.serve import serve


def main() -> None:
    """Serve the current directory as the workspace; block until interrupted."""
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    server = serve(Path.cwd(), port)
    address = server.server_address
    print(f"opsis serving at http://{address[0]}:{address[1]}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
