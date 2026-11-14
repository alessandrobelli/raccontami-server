"""The "Connect the phone" window, opened from the icon next to the clock (Windows).

It shows what the app asks for when it connects: the address, the token and, with the encrypted
link, the code to compare. Each value sits in a field of its own that can be selected, and has a
Copy button: a token is 32 characters, and nobody should have to retype it from a message box.

It uses tkinter, which comes with Python. Without it (some Linux Pythons leave it out), or without a
desktop, show() raises and the icon falls back to a plain message box with the same text.
"""

from __future__ import annotations

import threading

# the colours of the server's page (page.html), light and dark
LIGHT = {"page": "#eef1f4", "surface": "#f8f9fb", "line": "#cfd5dd", "text": "#1c2330", "muted": "#5a6474",
         "accent": "#1d4fbf", "on_accent": "#ffffff", "mark": "#fbe27a"}
DARK = {"page": "#14181f", "surface": "#1c222b", "line": "#333c49", "text": "#e6e9ee", "muted": "#9aa4b2",
        "accent": "#8fb0ff", "on_accent": "#0f1626", "mark": "#6b5a12"}

_one = threading.Lock()  # one window at a time: a second click on the menu does not open a second one


def facts(url: str | None, token: str | None, token_file, code: str | None,
          old_code: str | None = None) -> list[tuple[str, str, str]]:
    """(name, value, note) for each thing the app asks for, in the order the app asks.
    [old_code]: the same code as an app from before version 0.2 shows it."""
    out = [("Address", url or "this computer's address on your network, port 8765",
            "Or tap “Search local network” in the app: it finds this server by itself.")]
    out.append(("Token", token or f"in {token_file}", "The server's password. Paste it into the app, or type it."))
    if code:
        out.append(("Code", code, "The app shows a code when it connects. Confirm there only if it shows this one."
                     + (f" An app not yet updated shows it as {old_code}." if old_code else "")))
    else:
        out.append(("Code", "none", "The link is not encrypted (RACCONTAMI_TLS=0), so there is no code to compare."))
    return out


def as_text(rows: list[tuple[str, str, str]]) -> str:
    """The same as plain text, for a message box when the window cannot be shown."""
    lines = ["In the app: Settings, then the server's settings."]
    for name, value, note in rows:
        lines += ["", f"{name}:  {value}", note]
    return "\n".join(lines)


def _dark() -> bool:
    """Whether Windows is set to dark for apps; light when it cannot be told."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except Exception:  # noqa: BLE001  not Windows, or an older one
        return False


def show(rows: list[tuple[str, str, str]], server: str = "", icon=None) -> None:
    """Opens the window and returns when it is closed. Call it from a thread of its own.
    [icon]: a Pillow image for the window's corner, the same as the icon next to the clock."""
    if not _one.acquire(blocking=False):
        return
    try:
        _window(rows, server, icon)
    finally:
        _one.release()


def _window(rows, server, icon=None):
    import tkinter as tk

    try:  # sharp text on a screen set above 100 %; refused when already decided, which is fine
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        pass
    c = DARK if _dark() else LIGHT
    root = tk.Tk()
    root.title("Raccontami server")
    root.configure(bg=c["page"], padx=26, pady=22)
    root.resizable(False, False)
    if icon is not None:
        try:
            from PIL import ImageTk

            root.corner = ImageTk.PhotoImage(icon)  # kept on the window: tkinter does not keep it itself
            root.iconphoto(True, root.corner)
        except Exception:  # noqa: BLE001  the usual corner icon will do
            pass
    body, small = ("Segoe UI", 11), ("Segoe UI", 9)

    tk.Label(root, text="Connect the phone", font=("Georgia", 18, "bold"), bg=c["page"], fg=c["text"]).pack(anchor="w")
    tk.Label(root, text="In the app, open Settings and then the server's settings."
                        + (f" This is {server}." if server else ""),
             font=body, bg=c["page"], fg=c["muted"]).pack(anchor="w", pady=(2, 14))

    width = max(28, *(len(value) + 2 for _, value, _ in rows))
    first = None
    for name, value, note in rows:
        tk.Label(root, text=name.upper(), font=("Segoe UI", 8, "bold"), bg=c["page"], fg=c["muted"]).pack(anchor="w")
        line = tk.Frame(root, bg=c["page"])
        line.pack(anchor="w", fill="x", pady=(2, 0))
        # read-only, not disabled: the text can be selected with the mouse or the keyboard and copied
        box = tk.Frame(line, bg=c["surface"], highlightthickness=1, highlightbackground=c["line"])
        box.pack(side="left")
        field = tk.Entry(box, font=("Consolas", 12), width=width, relief="flat", bd=0, highlightthickness=0,
                         readonlybackground=c["surface"], fg=c["text"],
                         selectbackground=c["accent"], selectforeground=c["on_accent"])
        field.insert(0, value)
        field.configure(state="readonly")

        def focused(e, box=box):  # the whole value is selected at once, and the box shows where the keyboard is
            e.widget.selection_range(0, "end")
            box.configure(highlightbackground=c["accent"])

        field.bind("<FocusIn>", focused)
        field.bind("<FocusOut>", lambda e, box=box: box.configure(highlightbackground=c["line"]))
        field.pack(padx=10, pady=8)
        button = tk.Button(line, text="Copy", font=("Segoe UI", 10, "bold"), relief="flat", bd=0, cursor="hand2",
                           bg=c["page"], fg=c["accent"], activebackground=c["surface"], activeforeground=c["accent"],
                           padx=12, pady=4, takefocus=True)

        def copy(value=value, button=button):
            root.clipboard_clear()
            root.clipboard_append(value)
            root.update()  # hands the text to Windows now, so it is still there when this window is closed
            button.configure(text="Copied")
            root.after(1500, lambda: button.configure(text="Copy"))

        button.configure(command=copy)
        button.pack(side="left", padx=(8, 0))
        tk.Label(root, text=note, font=small, bg=c["page"], fg=c["muted"], wraplength=520, justify="left").pack(
            anchor="w", pady=(4, 14))
        first = first or button

    close = tk.Button(root, text="Close", font=("Segoe UI", 10, "bold"), relief="flat", bd=0, cursor="hand2",
                      bg=c["accent"], fg=c["on_accent"], activebackground=c["accent"], activeforeground=c["on_accent"],
                      padx=22, pady=6, command=root.destroy)
    close.pack(anchor="e", pady=(4, 0))
    root.bind("<Escape>", lambda e: root.destroy())

    # in the middle of the screen and in front: it was asked for from a menu, it must not open behind
    root.update_idletasks()
    w, h = root.winfo_reqwidth(), root.winfo_reqheight()
    root.geometry(f"+{(root.winfo_screenwidth() - w) // 2}+{(root.winfo_screenheight() - h) // 3}")
    root.attributes("-topmost", True)
    root.after(400, lambda: root.attributes("-topmost", False))
    root.lift()
    root.focus_force()
    if first is not None:
        first.focus_set()
    root.mainloop()
