"""Starts the server:  python -m raccontami_sync.serve

Encrypted by default, with the server's own certificate (see tls.py), on the same port as before.
Settings, as environment variables:
  RACCONTAMI_TLS=0     plain HTTP: behind a proxy that does the encryption (Caddy, tailscale serve),
                       or for an app that is older than the encrypted link
  RACCONTAMI_HOST      address to listen on (default 0.0.0.0, every network of this computer)
  RACCONTAMI_PORT      port (default 8765)
"""

from __future__ import annotations

import os

OFF = ("0", "off", "no", "false")


def options(env=os.environ) -> dict:
    """What uvicorn is started with; TLS files are added by main() when the link is encrypted."""
    return {"host": env.get("RACCONTAMI_HOST", "0.0.0.0"), "port": int(env.get("RACCONTAMI_PORT", "8765")),
            "access_log": False, "log_level": "warning"}


def wants_tls(env=os.environ) -> bool:
    return env.get("RACCONTAMI_TLS", "1").strip().lower() not in OFF


def main() -> None:
    from .paths import DATA

    start = options()
    if wants_tls():
        from . import tls

        try:
            cert, key = tls.ensure_certificate(DATA)
            start.update(ssl_certfile=str(cert), ssl_keyfile=str(key))
            # app.py prints it in its start-up lines
            os.environ["RACCONTAMI_TLS_CODE"] = tls.short_code(tls.fingerprint(cert))
        except ImportError:
            # an install from before the encrypted link, updated without its new package
            print('          NOT ENCRYPTED: the "cryptography" package is missing. Run the installer again '
                  "(or: pip install cryptography), or set RACCONTAMI_TLS=0 to silence this.", flush=True)
    import uvicorn

    uvicorn.run("raccontami_sync.app:app", **start)


if __name__ == "__main__":
    main()
