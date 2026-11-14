"""The server's icon next to the clock (Windows).

It says what the server is doing, opens the server's page, puts all the work on hold or continues
it, and stops the server without leaving a narration marked as failed. It is an extra: on Linux, in
Docker, without the two small packages it needs (pystray, Pillow), without a desktop, or with
RACCONTAMI_TRAY=0, the server runs exactly as before and says in one line why there is no icon.

This file knows nothing about jobs: app.py hands it a few functions (see start()).
"""

from __future__ import annotations

import os
import sys
import threading
import webbrowser

OFF = ("0", "off", "no", "false")
COLOURS = {"working": (29, 79, 191), "hold": (138, 109, 20), "idle": (107, 116, 132)}


def own_port(argv=None, env=None) -> int:
    """The port this server listens on: asked of what started it, since the app itself is not told."""
    argv, env = sys.argv if argv is None else argv, os.environ if env is None else env
    for i, arg in enumerate(argv):
        if arg == "--port" and i + 1 < len(argv) and argv[i + 1].isdigit():
            return int(argv[i + 1])
        if arg.startswith("--port=") and arg[7:].isdigit():
            return int(arg[7:])
    value = env.get("RACCONTAMI_PORT", "")
    return int(value) if value.isdigit() else 8765


def own_url(argv=None, env=None) -> str:
    """This server's page on this computer: https when serve.py started it with the encrypted link."""
    env = os.environ if env is None else env
    scheme = "https" if env.get("RACCONTAMI_TLS_CODE") else "http"
    return f"{scheme}://localhost:{own_port(argv, env)}/"


def lan_address() -> str | None:
    """This computer's address on the network it reaches others through: what a phone on the same
    Wi-Fi types. Nothing is sent: the system is only asked which address it would use."""
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # an address reserved for examples (RFC 5737)
            return s.getsockname()[0]
    except OSError:
        return None


def _show_connect(rows, server: str, log) -> None:
    """The window with what the app asks for (connect_window.py); a plain box with the same text
    when that window cannot be shown."""
    from . import connect_window

    try:
        connect_window.show(rows, server, icon=image("working"))
    except Exception as e:  # noqa: BLE001  no tkinter in this Python, or no desktop
        log(f"  icon: the Connect window could not be shown ({type(e).__name__}: {e}); a plain box instead")
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, connect_window.as_text(rows), "Raccontami server", 0x40 | 0x10000)


def why_not(platform=None, env=None) -> str | None:
    """None when an icon can be tried here; otherwise the reason there is none, for the log."""
    platform, env = sys.platform if platform is None else platform, os.environ if env is None else env
    if env.get("RACCONTAMI_TRAY", "1").strip().lower() in OFF:
        return "switched off (RACCONTAMI_TRAY)"
    if platform != "win32":
        return "it is for Windows; use the server's page"
    return None


def image(kind: str):
    """A page with lines of text and one lit word, on the colour of what the server is doing."""
    from PIL import Image, ImageDraw

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, size - 3, size - 3), radius=14, fill=COLOURS.get(kind, COLOURS["idle"]) + (255,))
    for y, (x0, x1) in zip((18, 30, 42), ((14, 50), (14, 44), (14, 38))):
        d.rounded_rectangle((x0, y, x1, y + 5), radius=2, fill=(255, 255, 255, 235))
    d.rounded_rectangle((26, 28, 44, 37), radius=3, fill=(251, 226, 122, 255))  # the word being read
    return img


class Tray:
    def __init__(self, name: str, port: int, summary, can, hold_all, continue_all, quit_server, log, folder=None,
                 connect=None):
        self.url = own_url(env={**os.environ, "RACCONTAMI_PORT": str(port)}, argv=[])
        self.name, self.summary, self.can = name, summary, can
        self.hold_all, self.continue_all, self.quit_server, self.log = hold_all, continue_all, quit_server, log
        self.folder = folder  # where the token and the log are
        self.connect = connect  # () -> what the app asks for, as connect_window.facts() gives it
        self.done = threading.Event()
        self.icon = None
        self.kind = None
        self.to_say = None  # a message waiting for the icon to be there

    def announce(self, message: str) -> None:
        """A notification from the icon, now or as soon as it is shown."""
        self.to_say = message
        self._say()

    def _say(self):
        icon, message = self.icon, self.to_say
        if icon is None or not message or not icon.visible:
            return
        self.to_say = None
        try:
            if icon.HAS_NOTIFICATION:
                icon.notify(message, "Raccontami server")
        except Exception as e:  # noqa: BLE001  the menu and the page say the same
            self.log(f"  icon: could not show a notification ({type(e).__name__}: {e})")

    def _menu(self):
        import pystray
        from pystray import MenuItem as Item

        def act(work):
            def clicked(icon, item):
                message = work()
                if message and icon.HAS_NOTIFICATION:
                    icon.notify(message, "Raccontami server")
                self._refresh()
            return clicked

        return pystray.Menu(
            Item(lambda item: self.summary()[1], None, enabled=False),
            pystray.Menu.SEPARATOR,
            Item("Open the server's page", lambda icon, item: webbrowser.open(self.url), default=True),
            # in a thread of its own: the window stays open as long as the reader needs it, and the icon goes on
            Item("Connect the phone (address, token, code)",
                 lambda icon, item: threading.Thread(target=_show_connect, args=(self.connect(), self.name, self.log),
                                                     daemon=True).start(),
                 visible=self.connect is not None),
            Item("Put everything on hold", act(self.hold_all), enabled=lambda item: self.can()["hold"]),
            Item("Continue what is on hold", act(self.continue_all), enabled=lambda item: self.can()["continue"]),
            pystray.Menu.SEPARATOR,
            Item("Open the server's folder (token, log)", lambda icon, item: os.startfile(self.folder),  # noqa: S606
                 visible=self.folder is not None),
            Item("Stop the server", lambda icon, item: self.quit_server()),
        )

    def _refresh(self):
        kind, text = self.summary()
        if kind != self.kind:
            self.kind = kind
            self.icon.icon = image(kind)
        self.icon.title = f"Raccontami server ({self.name}): {text}"[:120]  # Windows cuts long tips
        self.icon.update_menu()

    def _run(self):
        try:
            import pystray

            kind, text = self.summary()
            self.kind = kind
            self.icon = pystray.Icon("raccontami-server", icon=image(kind), title="Raccontami server", menu=self._menu())

            def keep_current(icon):
                icon.visible = True
                self._say()
                while not self.done.wait(3):
                    try:
                        self._refresh()
                    except Exception as e:  # noqa: BLE001  a wrong tip is not worth the icon
                        self.log(f"  icon: could not be refreshed ({type(e).__name__}: {e})")

            self.icon.run(keep_current)  # on Windows this may run outside the main thread (pystray's documentation)
        except Exception as e:  # noqa: BLE001  no desktop, a service, a missing package: the server does not need it
            if not self.done.is_set():
                self.log(f"  icon next to the clock: none ({type(e).__name__}: {e}). The server's page does the same")

    def start(self):
        threading.Thread(target=self._run, name="tray", daemon=True).start()

    def stop(self):
        self.done.set()
        try:
            if self.icon is not None:
                self.icon.stop()
        except Exception:  # noqa: BLE001  the process is ending anyway
            pass


def start(name: str, summary, can, hold_all, continue_all, quit_server, log, port: int | None = None,
          folder=None, connect=None) -> Tray | None:
    """Shows the icon, or says in one line why not. Never raises: the server starts either way.

    summary()      -> (kind, text): kind is "working", "hold" or "idle"; text is one short line
    can()          -> {"hold": bool, "continue": bool}
    hold_all()     -> a message for the reader, or None
    continue_all() -> the same
    quit_server()  -> stops the server, leaving unfinished work to be asked about at the next start
    """
    reason = why_not()
    if reason is None:
        try:
            import PIL  # noqa: F401
            import pystray  # noqa: F401
        except ImportError:
            reason = 'the packages "pystray" and "Pillow" are not installed (run the installer again)'
    if reason:
        log(f"  icon next to the clock: none, {reason}")
        return None
    tray = Tray(name, own_port() if port is None else port, summary, can, hold_all, continue_all, quit_server, log,
                folder=folder, connect=connect)
    tray.start()
    log("  icon next to the clock: yes (Windows may keep it behind the small arrow there). It opens the page, "
        "puts the work on hold and stops the server")
    return tray
