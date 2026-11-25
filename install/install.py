"""The Windows installer's work once its files are in place: the Python environments, PyTorch, the
packages, the models, settings.txt and start-server.bat. Run by the installer (installer/raccontami.iss)
with the Python it brings, in a window of its own: the setup window (raccontami_sync/console95.py) shows each step and how
far it is, and <home>\\setup-log.txt keeps everything the steps printed.
Safe to run again: what is there is kept and only what is missing is added; an environment that exists
is never made anew (it belongs to the Python that made it).

  python install.py --home C:\\Users\\me\\raccontami [--models E:\\models] [--port 8766] [--languages en,es] [--gpus 0]
                    [--narrator "a calm voice"] [--remake-narrators] [--skip-models] [--phone-models] [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
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
from raccontami_sync import console95, langmanage  # noqa: E402
from raccontami_sync import languages as catalogue  # noqa: E402
from raccontami_sync import settings  # noqa: E402
from raccontami_sync.paths import model_homes  # noqa: E402

TORCH_INDEX = "https://download.pytorch.org/whl/cu128"
TORCH = ["torch==2.11.0", "torchaudio==2.11.0"]
TORCH_CHECK = "import torch, sys; sys.exit(0 if torch.cuda.is_available() and torch.__version__.startswith('2.11') else 1)"
PORT = 8765
PIP_PROGRESS = ["--progress-bar", "raw"]  # "Progress N of M" lines, which the setup window turns into its bar
LOG = "setup-log.txt"  # in the home folder: every line the steps printed
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
GPUS_NOTE = "# The graphics cards the server uses (their numbers in nvidia-smi): the installer sets this line."
LANGUAGES_NOTE = ("# The languages installed: the installer sets this line. To add or remove one, open the installer "
                  "again (it downloads what a new language needs).")
PORT_NOTE = ("# The server's port: 8765 was taken by another program when installing. The phone's search looks on 8765, "
             "so type the address the server's window shows.")


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


@dataclass
class Port:
    number: int
    chosen: bool    # not the usual 8765: chosen by the installer (8765 was taken) or by the user
    from_env: bool  # set on the computer (RACCONTAMI_PORT): not written to settings.txt


def _port(value) -> int | None:
    value = str(value or "").strip()
    return int(value) if value.isdigit() and 0 < int(value) < 65536 else None


def resolve_port(chosen, settings_text_: str | None, env) -> Port:
    """The server's order: RACCONTAMI_PORT set on the computer, then settings.txt, then the port the
    installer chose now (8765 was taken by another program), then 8765."""
    if _port(env.get("RACCONTAMI_PORT")):
        return Port(_port(env["RACCONTAMI_PORT"]), True, True)
    named = _port(settings.parse(settings_text_ or "").get("RACCONTAMI_PORT"))
    if named:
        return Port(named, named != PORT, False)
    if _port(chosen) and _port(chosen) != PORT:
        return Port(_port(chosen), True, False)
    return Port(PORT, False, False)


def resolve_languages(chosen: str, settings_text_: str | None, env) -> list[str]:
    """The languages to install: set on the computer (RACCONTAMI_LANGUAGES), then the installer's choice now
    (it replaces the line in settings.txt), then that line, then English and Italian as before."""
    for value in (env.get("RACCONTAMI_LANGUAGES"), chosen, settings.parse(settings_text_ or "").get("RACCONTAMI_LANGUAGES")):
        if value and value.strip():
            return catalogue.enabled({"RACCONTAMI_LANGUAGES": value})
    return list(catalogue.DEFAULT)


def settings_text(existing: str | None, start_bat: str | None, models: Models, usual: str, port: Port | None = None,
                  langs=None, gpus: str | None = None) -> str | None:
    """settings.txt as it should be, or None when it needs no change. A new file is the template, plus the
    settings an earlier start-server.bat held; a chosen models folder and another port than 8765 are added
    when the file names none; the languages chosen in the installer set its RACCONTAMI_LANGUAGES line."""
    text = existing
    if text is None:
        text = TEMPLATE
        kept = [m.group(1).strip() for m in re.finditer(r"(?im)^\s*set\s+(RACCONTAMI_(?!HOME=)\w+=.+)$", start_bat or "")]
        if kept:
            text += "\n# Kept from the earlier start file\n" + "\n".join(kept) + "\n"
    if models.chosen and not models.from_env and not same_folder(models.folder, usual) \
            and not settings.parse(text).get("RACCONTAMI_MODELS"):
        text = text.rstrip("\n") + f"\n\n{MODELS_NOTE}\nRACCONTAMI_MODELS={models.folder}\n"
    if port and port.chosen and not port.from_env and port.number != PORT and not settings.parse(text).get("RACCONTAMI_PORT"):
        text = text.rstrip("\n") + f"\n\n{PORT_NOTE}\nRACCONTAMI_PORT={port.number}\n"
    if langs is not None and settings.parse(text).get("RACCONTAMI_LANGUAGES", "").replace(" ", "") != ",".join(langs):
        text = settings.set_line(text, "RACCONTAMI_LANGUAGES", ",".join(langs), LANGUAGES_NOTE)
    if gpus and settings.parse(text).get("RACCONTAMI_GPUS", "").replace(" ", "") != gpus:
        text = settings.set_line(text, "RACCONTAMI_GPUS", gpus, GPUS_NOTE)
    return None if text == existing else text


def batch_bytes(text: str) -> bytes:
    """A .bat that may hold a folder name with an accent: UTF-8 without the mark (cmd would take it for a
    command), its window switched to UTF-8 on the second line, before any path is read; Windows line ends."""
    body = "@echo off\nchcp 65001 > nul\n" + text.replace("\r\n", "\n").rstrip("\n") + "\n"
    return body.replace("\n", "\r\n").encode("utf-8")


def start_file_text(home: str, repo: str, server_py: str, port: int = PORT) -> str:
    return f"""\
rem Starts the Raccontami server (port {port}). Made by the installer, which writes it anew at
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
    stamp: tuple | None = None  # (file, text) written once the step succeeded: an update skips it while unchanged


def _read_stamp(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _requirements_print(path: str) -> str:
    """What an environment's packages depend on: the requirements file and the PyTorch version."""
    try:
        content = Path(path).read_bytes()
    except OSError:
        content = path.encode("utf-8")
    return hashlib.sha256(content + " ".join(TORCH).encode("utf-8")).hexdigest()


def plan(home: str, repo: str, python: str, skip_models: bool, phone_models: bool, exists=os.path.exists,
         langs=catalogue.DEFAULT, samples=None, narrator=None, remake_narrators=False, read=_read_stamp) -> list:
    """The programs to run, in order: the server's environment, those of the voice models the languages
    need (languages.py), the models, a narrator for each language VoxCPM2 narrates without a shipped
    sample. Environments that exist are kept; packages whose requirements did not change since the last
    run are not installed again; a narrator already made is kept unless a new one is asked for."""
    steps = []
    envs = [(ntpath.join(home, "env"), "requirements.txt", "server")]
    for voice in sorted(catalogue.voices_needed(langs, samples)):
        v = catalogue.VOICE_MODELS[voice]
        envs.append((ntpath.join(home, "tts", v["env"]), v["requirements"], f"voice {v['label']}"))
    for folder, requirements, label in envs:
        py = ntpath.join(folder, "Scripts", "python.exe")
        if not exists(py):
            steps.append(Step(f"Python environment: {label}", [python, "-m", "venv", folder]))
        steps.append(Step(f"PyTorch with CUDA for the {label} (about 3 GB the first time)",
                          [py, "-m", "pip", "install", *TORCH, "--index-url", TORCH_INDEX, *PIP_PROGRESS],
                          unless=[py, "-c", TORCH_CHECK]))
        stamp = (ntpath.join(folder, ".raccontami-packages"), _requirements_print(ntpath.join(repo, requirements)))
        if read(stamp[0]) != stamp[1]:
            steps.append(Step(f"The other packages for the {label} (a few minutes)",
                              [py, "-m", "pip", "install", "-r", ntpath.join(repo, requirements), *PIP_PROGRESS], stamp=stamp))
    server_py = ntpath.join(home, "env", "Scripts", "python.exe")
    if not skip_models:
        names = ", ".join(catalogue.name(lang) for lang in langs)
        steps.append(Step(f"The models for {names}", [server_py, ntpath.join(repo, "tools", "prefetch.py")]))
    voxcpm_py = ntpath.join(home, "tts", catalogue.VOICE_MODELS["voxcpm2"]["env"], "Scripts", "python.exe")
    for lang in catalogue.narrators_to_make(langs, samples):
        out = ntpath.join(home, "server-data", "narrators", f"voxcpm2_{lang}_ref.wav")
        if remake_narrators or not exists(out):
            steps.append(Step(f"A narrator for {catalogue.name(lang)}",
                              [voxcpm_py, ntpath.join(repo, "tools", "make_narrator.py"), lang, out,
                               "--description", narrator or catalogue.NARRATOR]))
    if phone_models:
        for model in PHONE_MODELS:
            name = model.split("/")[1]
            if not exists(ntpath.join(home, "onnx", f"{name}.int8.onnx")):
                steps.append(Step(f"Phone model {name}", [server_py, ntpath.join(repo, "tools", "export_phone_model.py"),
                                                         model, ntpath.join(home, "onnx")]))
    return steps

def removal_paths(previous, langs, home: str, models_folder: str, hub) -> list[Path]:
    """What goes when languages installed before are unticked now (and the user said yes): their word-timing
    models and narrators made here, and the voice models no language left needs. The same rules as the
    server's page (langmanage.py): models only in the server's own models folder, never in a shared one."""
    removed = [c for c in previous if c not in langs and c in catalogue.LANGUAGES]
    if not removed:
        return []
    root = Path(home)
    installed = {v for v, m in catalogue.VOICE_MODELS.items() if (root / "tts" / m["env"] / "Scripts" / "python.exe").exists()}
    out: list[Path] = []
    for code in removed:
        plan = langmanage.remove_plan(code, list(langs) + [code], installed, Path(hub), Path(models_folder),
                                      root / "server-data", root / "tts")
        for p in plan["delete"] + [p for u in plan["unusedVoices"].values() for p in u["delete"]]:
            if p not in out:
                out.append(p)
    return out


def step_environment(base, home: str, models: Models, langs=catalogue.DEFAULT, gpus: str | None = None) -> dict:
    """The environment the steps run in. The models folder is passed on only when one was chosen, so that
    without one the download follows a HF_HOME set on the computer, as the server does. The languages tell
    the download which models to fetch."""
    env = dict(base)
    env.update({"PIP_DISABLE_PIP_VERSION_CHECK": "1", "PIP_CACHE_DIR": ntpath.join(home, "pip-cache"),
                "RACCONTAMI_HOME": home, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1",
                "RACCONTAMI_LANGUAGES": ",".join(langs)})
    if gpus:
        env["CUDA_VISIBLE_DEVICES"] = gpus  # the narrators are made on the chosen card
    if models.chosen:
        env["RACCONTAMI_MODELS"] = models.folder
    else:
        env.pop("RACCONTAMI_MODELS", None)
    return env


def raccontami_answers(port: int) -> bool:
    """Whether a Raccontami server answers on this port of this computer (its /v1/hello needs no token).
    Its certificate is its own, so it is not checked: only "is this ours" is asked, nothing is sent."""
    import json
    import ssl
    import urllib.request
    unverified = ssl.create_default_context()
    unverified.check_hostname = False
    unverified.verify_mode = ssl.CERT_NONE
    for url in (f"https://127.0.0.1:{port}/v1/hello", f"http://127.0.0.1:{port}/v1/hello"):
        try:
            with urllib.request.urlopen(url, timeout=2, context=unverified if url.startswith("https") else None) as r:
                if json.loads(r.read(4096).decode("utf-8")).get("app") == "raccontami":
                    return True
        except Exception:  # noqa: BLE001  not this scheme, or not a Raccontami server
            continue
    return False


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
    a.add_argument("--port", default="", help="the port the installer chose because 8765 was taken (kept in settings.txt)")
    a.add_argument("--languages", default="", help="the languages chosen in the installer, e.g. en,es (kept in settings.txt)")
    a.add_argument("--narrator", default="", help="how a narrator made here should sound (VoxCPM2 voice design)")
    a.add_argument("--remake-narrators", action="store_true", help="make the narrators again, with --narrator")
    a.add_argument("--gpus", default="", help="the graphics cards to use, e.g. 0 or 0,1 (kept in settings.txt)")
    a.add_argument("--remove-unticked", action="store_true", help="delete the files of languages installed before and not chosen now")
    a.add_argument("--skip-models", action="store_true")
    a.add_argument("--phone-models", action="store_true")
    a.add_argument("--dry-run", action="store_true", help="say what would run, run nothing")
    a.add_argument("--pause-on-error", action="store_true", help="keep the window open after a failure (the installer's window)")
    args = a.parse_args(argv)
    try:
        code = _run(args)
    except KeyboardInterrupt:  # Ctrl+C, or the window closing
        print("\nStopped. Run the installer again to continue: what is done is kept.")
        code = 1
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
    notes = []  # shown in the setup window too, which covers these lines while the steps run
    print(f"Home folder: {home}\nModels:      {models.folder}")
    if models.note:
        print(models.note)
        notes.append(models.note)
    if os.environ.get("HF_HOME") and not models.chosen:
        print(f"             (the Hugging Face models go to {os.environ['HF_HOME']} instead: HF_HOME is set on this computer)")
        notes.append(f"The Hugging Face models go to {os.environ['HF_HOME']}: HF_HOME is set on this computer.")
    port = resolve_port(args.port, _read(settings_file), os.environ)
    print(f"Port:        {port.number}")
    previous = resolve_languages("", _read(settings_file), {})  # installed before this run
    langs = resolve_languages(args.languages, _read(settings_file), os.environ)
    print(f"Languages:   {', '.join(catalogue.name(lang) for lang in langs)}")
    made = catalogue.narrators_to_make(langs)
    if made:
        print(f"             (a narrator is made on this computer for: {', '.join(catalogue.name(lang) for lang in made)})")
    gpus = args.gpus.replace(" ", "") or settings.parse(_read(settings_file) or "").get("RACCONTAMI_GPUS", "")
    if gpus:
        print(f"Graphics:    card {gpus}")
    if port_in_use(port.number):
        if raccontami_answers(port.number):
            print(f"\nThe Raccontami server is running (port {port.number}). Stop it first: its icon next to the clock, "
                  "Stop the server. Then run the installer again.")
            return 1
        print(f"\nPort {port.number} is used by another program, so the server cannot start until that program stops. "
              f"Or give the server another port: RACCONTAMI_PORT in {settings_file}.")
        notes.append(f"Port {port.number} is used by another program: the server cannot start until it stops.")

    steps = plan(home, repo, sys.executable, args.skip_models, args.phone_models, langs=langs,
                 narrator=args.narrator or None, remake_narrators=args.remake_narrators)
    removing = []
    if args.remove_unticked and args.languages:
        hf = model_homes({**os.environ, **({"RACCONTAMI_MODELS": models.folder} if models.chosen else {})}, Path(models.folder))["HF_HOME"]
        removing = removal_paths(previous, langs, home, models.folder, Path(hf) / "hub")
        if removing:
            print("\nThe files of the languages unticked:\n" + "\n".join(f"  {p}" for p in removing))
    if args.dry_run:
        for s in steps:
            print(f"\n== {s.label}\n   " + (f"unless {s.unless[-1][:40]}...: " if s.unless else "") + subprocess.list2cmdline(s.argv))
        print("\n(dry run: nothing was run or written)")
        return 0

    # written before anything downloads, so a run stopped halfway and started again finds the folder it chose
    for folder in (ntpath.join(home, "server-data"), ntpath.join(home, "onnx"), ntpath.join(home, "tts"), models.folder):
        os.makedirs(folder, exist_ok=True)
    # the languages line is written when the installer chose them (a language set on the computer is not)
    chosen_now = bool(args.languages) and not os.environ.get("RACCONTAMI_LANGUAGES")
    text = settings_text(_read(settings_file), _read(start), models, usual, port, langs if chosen_now else None,
                         args.gpus.replace(" ", "") or None)
    if text is not None:
        Path(settings_file).write_text(text, encoding="utf-8")
    for p in removing:
        shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
    if removing:
        print("deleted")
    env = step_environment(os.environ, home, models, langs, gpus or None)
    log = ntpath.join(home, LOG)
    info = [f"Installing to {home}", f"Languages: {', '.join(catalogue.name(lang) for lang in langs)}   Port: {port.number}",
            *(f"Note: {n}" for n in notes)]
    # the steps' output is read by the setup window (console95.py): it shows what they do, the log keeps every line
    with console95.Screen(info, [s.label for s in steps], log) as screen:
        for i, s in enumerate(steps):
            screen.begin(i, "Checking what is already there" if s.unless else "Starting")
            if s.unless and subprocess.run(s.unless, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                screen.end(i, "skip")
                continue
            if console95.run(s.argv, env, screen) != 0:
                screen.end(i, "fail")
                drawn = screen.fancy  # a plain window already shows these lines
                screen.close()
                print(f"\nThis step failed: {s.label}")
                if drawn:
                    print("Its last lines:\n" + "\n".join("  " + x for x in screen.last_lines()))
                print(f"\nEverything it printed is in {log}\nRun the installer again to continue: what is done is kept.")
                return 1
            if s.stamp:  # an update skips this step while what it depends on is unchanged
                Path(s.stamp[0]).write_text(s.stamp[1], encoding="utf-8")
            screen.end(i, "done")
        Path(start).write_bytes(batch_bytes(start_file_text(home, repo, ntpath.join(home, "env", "Scripts", "python.exe"), port.number)))
        shutil.rmtree(ntpath.join(home, "pip-cache"), ignore_errors=True)
        screen.finish()
    print(f"\nDone.\nSettings:   {settings_file}\nStart file: {start}\nLog:        {log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
