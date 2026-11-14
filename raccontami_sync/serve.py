"""Starts the server:  python -m raccontami_sync.serve

Encrypted by default, with the server's own certificate (see tls.py), on the same port as before.
Settings, in <home>/settings.txt (see settings.py) or as environment variables:
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


def quiet_drops(loop, context) -> None:
    """Keeps one harmless error out of the server's window (Windows).

    A phone that only looks at the server's certificate (the app's search of the network, pairing,
    a browser at the certificate warning) hangs up without a goodbye. Python on Windows then prints
    "Exception in callback _ProactorBasePipeTransport._call_connection_lost" with a traceback and
    "ConnectionResetError: [WinError 10054]" for each one: nothing is wrong, the connection is
    already gone, and the lines look like a crash. Only that case is dropped; everything else is
    shown as before."""
    gone = isinstance(context.get("exception"), (ConnectionResetError, ConnectionAbortedError))
    if gone and "_call_connection_lost" in str(context.get("message", "")):
        return
    loop.default_exception_handler(context)


def use_own_tools(env=None) -> str | None:
    """Puts the ffmpeg that the one-file setup brought (<home>/tools/ffmpeg/bin) first on the PATH
    of this server and of what it starts, and returns that folder; None when there is none, and the
    computer's own ffmpeg is used as before. Done here and not in a start file, so that it also
    holds for the start without a window."""
    from . import settings

    env = os.environ if env is None else env
    folder = settings.home(env) / "tools" / "ffmpeg" / "bin"
    if not folder.is_dir():
        return None
    env["PATH"] = str(folder) + os.pathsep + env.get("PATH", "")
    return str(folder)


def main() -> None:
    from . import settings

    settings.load()  # before anything reads a setting: paths.py does when it is imported
    use_own_tools()
    from .paths import DATA

    start = options()
    if wants_tls():
        from . import tls

        try:
            cert, key = tls.ensure_certificate(DATA)
            start.update(ssl_certfile=str(cert), ssl_keyfile=str(key))
            # app.py prints them in its start-up lines: the code, and how older apps show the same code
            mark = tls.fingerprint(cert)
            os.environ["RACCONTAMI_TLS_CODE"] = tls.digit_code(mark)
            os.environ["RACCONTAMI_TLS_CODE_OLD"] = tls.short_code(mark)
        except ImportError:
            # an install from before the encrypted link, updated without its new package
            print('          NOT ENCRYPTED: the "cryptography" package is missing. Run the installer again '
                  "(or: pip install cryptography), or set RACCONTAMI_TLS=0 to silence this.", flush=True)
    import uvicorn

    uvicorn.run("raccontami_sync.app:app", **start)


if __name__ == "__main__":
    main()
