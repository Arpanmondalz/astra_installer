"""Entry point: ``python3 -m astra``."""

from __future__ import annotations

import logging
import signal
import sys

from waitress import serve

from . import config
from .camera import AstraCamera
from .web import create_app


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    log = logging.getLogger("astra")

    camera = AstraCamera()
    camera.start()

    def shutdown(signum, _frame):
        log.info("signal %s received, shutting down", signum)
        camera.close()
        sys.exit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, shutdown)

    app = create_app(camera)
    log.info("serving on http://%s:%s", config.HOST, config.PORT)
    try:
        serve(
            app,
            host=config.HOST,
            port=config.PORT,
            threads=config.SERVER_THREADS,
            channel_timeout=config.SERVER_CHANNEL_TIMEOUT,
            cleanup_interval=5,
            ident="astra",
        )
    finally:
        camera.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
