"""The Windows installer's work once its files are in place: the Python environments, PyTorch, the
packages, the models, settings.txt and start-server.bat. Run by the installer (installer/raccontami.iss)
with the Python it brings, in a window of its own so pip and the model download can show progress.
Safe to run again: what is there is kept and only what is missing is added; an environment that exists
is never made anew (it belongs to the Python that made it).

  python install.py --home C:\\Users\\me\\raccontami [--models E:\\models] [--skip-models] [--phone-models] [--dry-run]
"""

from __future__ import annotations

import argparse
import ntpath
import os
import re
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from raccontami_sync import settings  # noqa: E402

TORCH_INDEX = "https://download.pytorch.org/whl/cu128"
TORCH = ["torch==2.11.0", "torchaudio==2.11.0"]
TORCH_CHECK = "import torch, sys; sys.exit(0 if torch.cuda.is_available() and torch.__version__.startswith('2.11') else 1)"
PORT = 8765
PHONE_MODELS = ["facebook/wav2vec2-base-960h", "jonatasgrosman/wav2vec2-large-xlsr-53-italian"]

TEMPLATE = """\
# Settings of the Raccontami server: one per line, NAME=value. Lines starting with # are notes.
# The installer only adds the models folder chosen when installing; it changes nothing else here.
# The README lists every setting.
# The server reads it when it starts: stop the server and start it again after a change.

# How the app names this server
# RACCONTAMI_NAME=My PC

# Plain HTTP instead of the encrypted link (behind a proxy, or for an older app)
# RACCONTAMI_TLS=0

# GPU under 12 GB: run syncs and narrations one at a time
# RACCONTAMI_ONE_JOB=1
"""
MODELS_NOTE = "# Where the models are, chosen when installing. To move them: stop the server, move the folder, change this line."


def full_folder(path: str) -> str:
    """A folder as a full Windows path without its last backslash (a drive's root keeps it). A quote left in
    by the command line ("D:\\my folder\\" loses its closing quote to the backslash) is dropped."""
    path = path.strip().strip('"')
    path = ntpath.normpath(path if ntpath.isabs(path) else ntpath.abspath(path))
    return path if len(path) <= 3 else path.rstrip("\\")


def same_folder(a: str, b: str) -> bool:
    return full_folder(a).lower() == full_folder(b).lower()


@dataclass
class Models:
    folder: str
    chosen: bool      # a folder was chosen: it then holds every model (raccontami_sync/paths.py, model_homes)
    from_env: bool    # set on the computer (RACCONTAMI_MODELS): not written to settings.txt
    note: str | None  # something to tell the user


def resolve_models(home: str, chosen: str, settings_text: str | None, env) -> Models:
    """The server's order: RACCONTAMI_MODELS set on the computer, then settings.txt, then the folder chosen
    now, then <home>\\models. The models download into the folder the server will read."""
    usual = ntpath.join(home, "models")
    if env.get("RACCONTAMI_MODELS"):
        folder = env["RACCONTAMI_MODELS"]
        return Models(folder, True, True, f"RACCONTAMI_MODELS is set on this computer, so the models go to {folder}, where the server looks for them.")
    named = settings.parse(settings_text or "").get("RACCONTAMI_MODELS")
    if named:
        note = None
        if chosen and not same_folder(chosen, named):
            note = (f"settings.txt already puts the models in {named}, so they stay there. To move them, stop the "
                    "server, move the folder and change RACCONTAMI_MODELS in settings.txt.")
        return Models(named, True, False, note)
    if chosen and not same_folder(chosen, usual):
        return Models(full_folder(chosen), True, False, None)
    return Models(usual, False, False, None)


def settings_text(existing: str | None, start_bat: str | None, models: Models, usual: str) -> str | None:
    """settings.txt as it should be, or None when it needs no change. A new file is the template, plus the
    settings an earlier start-server.bat held; a chosen models folder is added when the file names none."""
    text = existing
    if text is None:
        text = TEMPLATE
        kept = [m.group(1).strip() for m in re.finditer(r"(?im)^\s*set\s+(RACCONTAMI_(?!HOME=)\w+=.+)$", start_bat or "")]
        if kept:
            text += "\n# Kept from the earlier start file\n" + "\n".join(kept) + "\n"
    if models.chosen and not models.from_env and not same_folder(models.folder, usual) \
            and not settings.parse(text).get("RACCONTAMI_MODELS"):
        text = text.rstrip("\n") + f"\n\n{MODELS_NOTE}\nRACCONTAMI_MODELS={models.folder}\n"
    return None if text == existing else text


def batch_bytes(text: str) -> bytes:
    """A .bat that may hold a folder name with an accent: UTF-8 without the mark (cmd would take it for a
    command), its window switched to UTF-8 on the second line, before any path is read; Windows line ends."""
    body = "@echo off\nchcp 65001 > nul\n" + text.replace("\r\n", "\n").rstrip("\n") + "\n"
    return body.replace("\n", "\r\n").encode("utf-8")


def start_file_text(home: str, repo: str, server_py: str) -> str:
    return f"""\
rem Starts the Raccontami server (port {PORT}). Made by the installer, which writes it anew at
rem every run: settings go in settings.txt beside this file, not here.
title Raccontami server
set RACCONTAMI_HOME={home}
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
cd /d "{repo}"
"{server_py}" -m raccontami_sync.serve
echo.
echo The server stopped. Press a key to close this window.
pause > nul
"""


@dataclass
class Step:
    label: str
    argv: list
    unless: list | None = None  # a check: when it succeeds, the step is not needed


def plan(home: str, repo: str, python: str, skip_models: bool, phone_models: bool, exists=os.path.exists) -> list:
    """The programs to run, in order. Environments that exist are kept."""
    steps = []
    envs = [(ntpath.join(home, "env"), "requirements.txt", "server"),
            (ntpath.join(home, "tts", "env-a"), "requirements-voxcpm.txt", "Italian voice (VoxCPM2)"),
            (ntpath.join(home, "tts", "env-c"), "requirements-qwen.txt", "English voice (Qwen3-TTS)")]
    for folder, requirements, label in envs:
        py = ntpath.join(folder, "Scripts", "python.exe")
        if not exists(py):
            steps.append(Step(f"Python environment: {label}", [python, "-m", "venv", folder]))
        steps.append(Step(f"PyTorch with CUDA for the {label} (about 3 GB the first time)",
                          [py, "-m", "pip", "install", *TORCH, "--index-url", TORCH_INDEX], unless=[py, "-c", TORCH_CHECK]))
        steps.append(Step(f"The other packages for the {label} (a few minutes, nothing is shown meanwhile)",
                          [py, "-m", "pip", "install", "-q", "-r", ntpath.join(repo, requirements)]))
    server_py = ntpath.join(home, "env", "Scripts", "python.exe")
    if not skip_models:
        steps.append(Step("The models (about 20 GB the first time)", [server_py, ntpath.join(repo, "tools", "prefetch.py")]))
    if phone_models:
        for model in PHONE_MODELS:
            name = model.split("/")[1]
            if not exists(ntpath.join(home, "onnx", f"{name}.int8.onnx")):
                steps.append(Step(f"Phone model {name}", [server_py, ntpath.join(repo, "tools", "export_phone_model.py"),
                                                         model, ntpath.join(home, "onnx")]))
    return steps


def step_environment(base, home: str, models: Models) -> dict:
    """The environment the steps run in. The models folder is passed on only when one was chosen, so that
    without one the download follows a HF_HOME set on the computer, as the server does."""
    env = dict(base)
    env.update({"PIP_DISABLE_PIP_VERSION_CHECK": "1", "PIP_CACHE_DIR": ntpath.join(home, "pip-cache"),
                "RACCONTAMI_HOME": home, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
    if models.chosen:
        env["RACCONTAMI_MODELS"] = models.folder
    else:
        env.pop("RACCONTAMI_MODELS", None)
    return env


def port_in_use(port: int = PORT) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8-sig")
    except OSError:
        return None


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description="Raccontami server: the installer's steps")
    a.add_argument("--home", required=True)
    a.add_argument("--models", default="")
    a.add_argument("--skip-models", action="store_true")
    a.add_argument("--phone-models", action="store_true")
    a.add_argument("--dry-run", action="store_true", help="say what would run, run nothing")
    a.add_argument("--pause-on-error", action="store_true", help="keep the window open after a failure (the installer's window)")
    args = a.parse_args(argv)
    code = _run(args)
    if code and args.pause_on_error:
        input("\nPress Enter to close this window.")
    return code


def _run(args) -> int:
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW("Raccontami server setup")

    home = full_folder(args.home)
    repo = str(REPO)
    usual = ntpath.join(home, "models")
    settings_file = ntpath.join(home, settings.FILE)
    start = ntpath.join(home, "start-server.bat")
    models = resolve_models(home, args.models, _read(settings_file), os.environ)
    print(f"Home folder: {home}\nModels:      {models.folder}")
    if models.note:
        print(models.note)
    if os.environ.get("HF_HOME") and not models.chosen:
        print(f"             (the Hugging Face models go to {os.environ['HF_HOME']} instead: HF_HOME is set on this computer)")
    if port_in_use():
        print(f"\nA server seems to be running (port {PORT} is in use). Stop it first: its icon next to the clock, "
              "Stop the server. Then run the installer again.")
        return 1

    steps = plan(home, repo, sys.executable, args.skip_models, args.phone_models)
    if args.dry_run:
        for s in steps:
            print(f"\n== {s.label}\n   " + (f"unless {s.unless[-1][:40]}...: " if s.unless else "") + subprocess.list2cmdline(s.argv))
        print("\n(dry run: nothing was run or written)")
        return 0

    # written before anything downloads, so a run stopped halfway and started again finds the folder it chose
    for folder in (ntpath.join(home, "server-data"), ntpath.join(home, "onnx"), ntpath.join(home, "tts"), models.folder):
        os.makedirs(folder, exist_ok=True)
    text = settings_text(_read(settings_file), _read(start), models, usual)
    if text is not None:
        Path(settings_file).write_text(text, encoding="utf-8")
    env = step_environment(os.environ, home, models)
    for s in steps:
        print(f"\n== {s.label}", flush=True)
        if s.unless and subprocess.run(s.unless, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            print("already there")
            continue
        # not captured: pip and the model download write straight to the window and draw their progress
        if subprocess.run(s.argv, env=env).returncode != 0:
            print(f"\nThis step failed: {s.label}. The lines above say why. Run the installer again to continue: "
                  "what is done is kept.")
            return 1

    Path(start).write_bytes(batch_bytes(start_file_text(home, repo, ntpath.join(home, "env", "Scripts", "python.exe"))))
    shutil.rmtree(ntpath.join(home, "pip-cache"), ignore_errors=True)
    print(f"\nDone.\nSettings:   {settings_file}\nStart file: {start}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
