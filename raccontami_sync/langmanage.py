"""Managing the installed languages from the server's page: what each language takes, and what removing
one deletes. The page asks; app.py does the deleting and writes settings.txt.

Removing a language deletes its word-timing model and its narrator made on this computer, and offers the
voice models no remaining language needs. A model is deleted only in the server's own models folder: in a
Hugging Face cache shared with other programs (a HF_HOME set on the computer) the files are kept, and only
the language is switched off.

Standard library only (the GitHub check runs these tests without the server's packages).
"""

from __future__ import annotations

from pathlib import Path

from . import languages


def repo_dir(hub: Path, repo: str) -> Path:
    """Where Hugging Face keeps a downloaded model in its cache folder."""
    return Path(hub) / ("models--" + repo.replace("/", "--"))


def ours(hub: Path, models: Path) -> bool:
    """Whether the Hugging Face cache is inside the server's models folder (not shared with other programs)."""
    try:
        Path(hub).resolve().relative_to(Path(models).resolve())
        return True
    except ValueError:
        return False


def folder_bytes(path: Path) -> int:
    path = Path(path)
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.is_dir() else 0


def _narrator(data: Path, code: str) -> Path:
    return Path(data) / "narrators" / f"voxcpm2_{code}_ref.wav"


def status(enabled, installed_voices, hub: Path, models: Path, data: Path, samples: set[str] | None = None) -> list[dict]:
    """Every language of the catalogue: installed or not, its voice, the space it takes, and whether the page
    can add it ("here": its voice model is installed) or the installer must ("installer": it needs a voice
    model's environment, which only the installer makes)."""
    have = languages.samples(data) if samples is None else samples
    rows = []
    for code, lang in languages.LANGUAGES.items():
        planned = next(iter(languages.voices_needed([code], have)), None)
        voice = languages.voice_for(code, installed_voices, have) or planned
        installed = code in enabled
        narrator = _narrator(data, code)
        rows.append({
            "code": code, "name": lang["name"], "installed": installed, "tested": lang["tested"],
            "makesNarrator": bool(languages.narrators_to_make([code])) and not narrator.exists(),
            "voice": languages.VOICE_MODELS[voice]["label"] if voice else None,
            "narrator": "made" if narrator.exists() else ("shipped" if code in languages.samples() else None),
            "add": "here" if planned is None or planned in installed_voices else "installer",
            "bytes": folder_bytes(repo_dir(hub, lang["aligner"])) + folder_bytes(narrator) if installed else 0,
        })
    return rows


def remove_plan(code: str, enabled, installed_voices, hub: Path, models: Path, data: Path, tts: Path,
                samples: set[str] | None = None) -> dict:
    """What removing [code] does: the languages left, the files deleted, the space freed, and the voice
    models no remaining language needs (each with its files), offered separately. "refused" says why it
    cannot be removed, or is None."""
    have = languages.samples(data) if samples is None else samples
    remaining = [c for c in enabled if c != code]
    refused = None
    if code not in enabled:
        refused = f"{languages.name(code)} is not installed."
    elif not remaining:
        refused = "This is the server's only language. Add another one before removing it."
    own = ours(hub, models)
    delete = []
    if code in languages.LANGUAGES and own:
        delete.append(repo_dir(hub, languages.LANGUAGES[code]["aligner"]))
    if _narrator(data, code).exists():
        delete.append(_narrator(data, code))
    delete = [p for p in delete if p.exists()]
    needed = {languages.voice_for(c, installed_voices, have) for c in remaining if c in languages.LANGUAGES}
    unused = {}
    for voice in sorted(set(installed_voices) - needed):
        v = languages.VOICE_MODELS[voice]
        paths = [p for p in [Path(tts) / v["env"]] + ([repo_dir(hub, v["repo"])] if own else []) if p.exists()]
        unused[voice] = {"label": v["label"], "delete": paths, "bytes": sum(folder_bytes(p) for p in paths)}
    return {"code": code, "languages": remaining, "delete": delete, "bytes": sum(folder_bytes(p) for p in delete),
            "unusedVoices": unused, "shared": not own, "refused": refused}
