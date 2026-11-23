"""Which speech model times the words of each language: a CTC model that writes letters
(wav2vec2, HuBERT, WavLM), as the phone uses for its own syncs (docs/phone-models.md).

English and Italian come with tried models. A setting adds a language or changes its model:
  RACCONTAMI_ALIGN_MODEL_FR=jonatasgrosman/wav2vec2-large-xlsr-53-french
The language is the end of the name; the value is a Hugging Face model id or a model folder.
The languages here are the ones the server syncs and narrates.

Nothing outside the standard library is imported at the top: the GitHub check runs these
tests without the server's Python environment.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from . import languages

PREFIX = "RACCONTAMI_ALIGN_MODEL_"
DEFAULTS = {code: lang["aligner"] for code, lang in languages.LANGUAGES.items()}


def letter_ids(word: str, vocab: dict) -> list[int]:
    """The model's ids for the letters of [word]: each letter as written, in upper case, or without its
    accent. A letter the model lacks entirely may have a spelled-out form (German ß -> ss); a letter with
    no match at all is left out."""
    import unicodedata

    def plain(c):
        return "".join(x for x in unicodedata.normalize("NFD", c) if unicodedata.category(x) != "Mn")

    def one(c):
        for cand in (c, c.upper(), plain(c), plain(c).upper()):
            if cand in vocab:
                return vocab[cand]
        return None

    out = []
    for c in word:
        found = one(c)
        if found is not None:
            out.append(found)
        elif len(c.casefold()) > 1:
            out.extend(i for i in (one(x) for x in c.casefold()) if i is not None)
    return out


def fetch(model_id: str) -> None:
    """Downloads a word-timing model the way the server loads it, so exactly those files are there: its
    repository may also hold copies for other frameworks and a language model the server never uses.
    Loaded once on the processor, only to fetch its files, then dropped."""
    from transformers import AutoModelForCTC, Wav2Vec2Processor

    Wav2Vec2Processor.from_pretrained(model_id)
    AutoModelForCTC.from_pretrained(model_id)


def align_models(env) -> dict[str, str]:
    """Language -> model: those of the installed languages (RACCONTAMI_LANGUAGES, English and Italian
    without it), with what the settings add or change."""
    models = {code: DEFAULTS[code] for code in languages.enabled(env)}
    for name, value in env.items():
        if name.startswith(PREFIX) and value.strip():
            models[name[len(PREFIX):].lower()] = value.strip()
    return models


def refusal(config: dict, vocab: dict | None) -> str | None:
    """Why a model cannot time words, from its config.json and vocab.json; None when it can.
    The same rules as the phone's check of a model (HfModels.kt in the app)."""
    arch = config.get("architectures") or []
    if arch and not any(a.endswith("ForCTC") for a in arch):
        return f"it is a {', '.join(arch)}, not a CTC speech model (wav2vec2, HuBERT, WavLM)"
    if vocab is None or not all(isinstance(v, int) for v in vocab.values()):
        return "it has no vocab.json of letters, so the letters it writes are unknown"
    tokens = [t for t in vocab if not (t.startswith("<") and t.endswith(">")) and t != "|"]
    single = sum(len(t) == 1 for t in tokens)
    if not tokens or single < 0.8 * len(tokens) or len(tokens) > 300:
        return f"it writes word pieces, not letters ({len(tokens)} tokens)"
    return None


def _json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def read_files(model_id: str) -> tuple[dict, dict | None]:
    """The model's config.json and vocab.json (None when it has none), from its folder or from
    Hugging Face (a few kilobytes, kept in the models folder). ConnectionError when Hugging Face
    cannot be reached and the files were never downloaded; LookupError for a name it does not have."""
    folder = Path(model_id)
    if folder.is_dir():
        return _json(folder / "config.json") or {}, _json(folder / "vocab.json")

    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import EntryNotFoundError, LocalEntryNotFoundError, RepositoryNotFoundError

    def get(name: str) -> dict | None:
        try:
            return _json(Path(hf_hub_download(model_id, name)))
        except LocalEntryNotFoundError as e:  # before EntryNotFoundError: it is one
            raise ConnectionError(str(e)) from e
        except EntryNotFoundError:
            return None

    try:
        return get("config.json") or {}, get("vocab.json")
    except RepositoryNotFoundError as e:  # also a model one must ask access for
        raise LookupError("there is no public model with that name on Hugging Face") from e


def check(models: dict[str, str], languages: set[str], log: Callable[[str], None] = print) -> None:
    """Stops the server at start, with the reason, for a model in the settings that cannot time
    words, so it is not found out at the first sync. The models that come with the server are
    not looked up. [languages]: the ones Whisper knows, which places the anchors."""
    for lang, model_id in models.items():
        if DEFAULTS.get(lang) == model_id:
            continue
        name = PREFIX + lang.upper()
        if lang not in languages:
            raise ValueError(f"{name}: Whisper does not know the language {lang!r}; "
                             f"the end of the name is a language code, such as {PREFIX}FR")
        try:
            config, vocab = read_files(model_id)
        except ConnectionError:
            log(f"  {name}: {model_id} could not be checked (Hugging Face cannot be reached); "
                f"it is downloaded at the first sync in that language")
            continue
        except LookupError as e:
            raise ValueError(f"{name}={model_id}: {e}") from e
        reason = refusal(config, vocab)
        if reason:
            raise ValueError(f"{name}={model_id} cannot time words: {reason}")
