"""The launcher — ``python -m opsis [port]`` serves the cwd as workspace."""

from __future__ import annotations

import sys
from pathlib import Path

from opsis.praxis.serve import serve


def main() -> None:
    """Bind, announce, serve until interrupted."""
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = serve(Path.cwd(), port)
    host, bound = server.server_address[:2]
    print(f"opsis · http://{host}:{bound}/ · workspace {Path.cwd()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


main()
