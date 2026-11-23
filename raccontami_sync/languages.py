"""The languages the server can offer, and the voice models that narrate them: the one place that says so.

The installer lists these languages and downloads only what the chosen ones need; the server reads the
choice from RACCONTAMI_LANGUAGES (settings.txt), English and Italian when it is not set.

Each language needs a model that times the words (a CTC model that writes letters, see aligners.py) and,
to be narrated, a voice model that speaks it. Qwen3-TTS speaks with fixed voices; VoxCPM2 copies a
narrator from a short sample, so it narrates a language only when voices/voxcpm2_<code>_ref.wav exists.
Chinese, Japanese and Korean are not here yet: their word-timing models write whole characters, which
the word timing does not handle yet.

Standard library only: the installer's build and the GitHub check read this without the server's packages.
"""

from __future__ import annotations

from pathlib import Path

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "voices"
DEFAULT = ("en", "it")  # a server installed before languages could be chosen

# code -> name, word-timing model, the voices that can narrate it (preferred first), Qwen3-TTS's name for
# it, Windows' primary language id (to tick it by default), and whether it was tried on whole books
LANGUAGES = {
    "en": {"name": "English", "aligner": "facebook/wav2vec2-large-960h-lv60-self",
           "voices": ["qwen3"], "qwen": "English", "windows": 0x09, "tested": True},
    "it": {"name": "Italian", "aligner": "jonatasgrosman/wav2vec2-large-xlsr-53-italian",
           "voices": ["voxcpm2", "qwen3"], "qwen": "Italian", "windows": 0x10, "tested": True},
    "es": {"name": "Spanish", "aligner": "jonatasgrosman/wav2vec2-large-xlsr-53-spanish",
           "voices": ["qwen3", "voxcpm2"], "qwen": "Spanish", "windows": 0x0A, "tested": False},
    "tr": {"name": "Turkish", "aligner": "mpoyraz/wav2vec2-xls-r-300m-cv7-turkish",
           "voices": ["voxcpm2"], "qwen": None, "windows": 0x1F, "tested": False},
    "de": {"name": "German", "aligner": "jonatasgrosman/wav2vec2-large-xlsr-53-german",
           "voices": ["qwen3", "voxcpm2"], "qwen": "German", "windows": 0x07, "tested": False},
    "fr": {"name": "French", "aligner": "jonatasgrosman/wav2vec2-large-xlsr-53-french",
           "voices": ["qwen3", "voxcpm2"], "qwen": "French", "windows": 0x0C, "tested": False},
    "pt": {"name": "Portuguese", "aligner": "jonatasgrosman/wav2vec2-large-xlsr-53-portuguese",
           "voices": ["qwen3", "voxcpm2"], "qwen": "Portuguese", "windows": 0x16, "tested": False},
    "ru": {"name": "Russian", "aligner": "jonatasgrosman/wav2vec2-large-xlsr-53-russian",
           "voices": ["qwen3", "voxcpm2"], "qwen": "Russian", "windows": 0x19, "tested": False},
    # narrated by VoxCPM2 only, with a narrator made on the user's computer; word-timing models chosen for
    # commercial-use licences and the lowest published error rate (Malay has none such yet)
    "ar": {"name": "Arabic", "aligner": "jonatasgrosman/wav2vec2-large-xlsr-53-arabic",
           "voices": ["voxcpm2"], "qwen": None, "windows": 0x01, "tested": False},
    "da": {"name": "Danish", "aligner": "Alvenir/wav2vec2-base-da-ft-nst",
           "voices": ["voxcpm2"], "qwen": None, "windows": 0x06, "tested": False},
    "nl": {"name": "Dutch", "aligner": "jonatasgrosman/wav2vec2-large-xlsr-53-dutch",
           "voices": ["voxcpm2"], "qwen": None, "windows": 0x13, "tested": False},
    "fi": {"name": "Finnish", "aligner": "Finnish-NLP/wav2vec2-xlsr-300m-finnish-lm",
           "voices": ["voxcpm2"], "qwen": None, "windows": 0x0B, "tested": False},
    "el": {"name": "Greek", "aligner": "lighteternal/wav2vec2-large-xlsr-53-greek",
           "voices": ["voxcpm2"], "qwen": None, "windows": 0x08, "tested": False},
    "he": {"name": "Hebrew", "aligner": "imvladikon/wav2vec2-xls-r-300m-lm-hebrew",
           "voices": ["voxcpm2"], "qwen": None, "windows": 0x0D, "tested": False},
    "hi": {"name": "Hindi", "aligner": "Harveenchadha/hindi_base_wav2vec2",
           "voices": ["voxcpm2"], "qwen": None, "windows": 0x39, "tested": False},
    "id": {"name": "Indonesian", "aligner": "indonesian-nlp/wav2vec2-indonesian-javanese-sundanese",
           "voices": ["voxcpm2"], "qwen": None, "windows": 0x21, "tested": False},
    "no": {"name": "Norwegian", "aligner": "NbAiLab/nb-wav2vec2-300m-bokmaal",
           "voices": ["voxcpm2"], "qwen": None, "windows": 0x14, "tested": False},
    "pl": {"name": "Polish", "aligner": "jonatasgrosman/wav2vec2-large-xlsr-53-polish",
           "voices": ["voxcpm2"], "qwen": None, "windows": 0x15, "tested": False},
    "sw": {"name": "Swahili", "aligner": "Akashpb13/Swahili_xlsr",
           "voices": ["voxcpm2"], "qwen": None, "windows": 0x41, "tested": False},
    "sv": {"name": "Swedish", "aligner": "KBLab/wav2vec2-large-voxrex-swedish",
           "voices": ["voxcpm2"], "qwen": None, "windows": 0x1D, "tested": False},
    "tl": {"name": "Tagalog", "aligner": "Khalsuu/filipino-wav2vec2-l-xls-r-300m-official",
           "voices": ["voxcpm2"], "qwen": None, "windows": 0x64, "tested": False},
    "vi": {"name": "Vietnamese", "aligner": "leduytan93/Fine-Tune-XLSR-Wav2Vec2-Speech2Text-Vietnamese",
           "voices": ["voxcpm2"], "qwen": None, "windows": 0x2A, "tested": False},
}

# voice model -> its environment (the libraries of the two clash), its model, sizes in GB
VOICE_MODELS = {
    "qwen3": {"label": "Qwen3-TTS", "env": "env-c", "requirements": "requirements-qwen.txt",
              "repo": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", "model_gb": 4.2, "env_gb": 5.1, "sample": False},
    "voxcpm2": {"label": "VoxCPM2", "env": "env-a", "requirements": "requirements-voxcpm.txt",
                "repo": "openbmb/VoxCPM2", "model_gb": 4.6, "env_gb": 5.7, "sample": True},
}
# What a generated VoxCPM2 narrator says (about ten seconds, the length a voice sample needs): it is only
# heard once, to give the narrator its voice. A language with a text here can get a narrator made on the
# user's computer when it has no sample in voices/ (tools/make_narrator.py).
SAMPLE_TEXT = {
    "en": "Once upon a time, in a small town by the sea, there lived a curious child who loved to read. "
          "Every evening, by the light of a lamp, they opened a new book and travelled far away.",
    "it": "C'era una volta, in un piccolo paese sul mare, un bambino curioso che amava leggere. "
          "Ogni sera, alla luce di una lampada, apriva un libro nuovo e viaggiava lontano.",
    "es": "Érase una vez, en un pequeño pueblo junto al mar, un niño curioso al que le encantaba leer. "
          "Cada noche, a la luz de una lámpara, abría un libro nuevo y viajaba muy lejos.",
    "tr": "Bir varmış, bir yokmuş. Deniz kenarındaki küçük bir kasabada, okumayı çok seven meraklı bir çocuk yaşarmış. "
          "Her akşam bir lambanın ışığında yeni bir kitap açar ve uzaklara yolculuk edermiş.",
    "de": "Es war einmal, in einer kleinen Stadt am Meer, ein neugieriges Kind, das sehr gern las. "
          "Jeden Abend öffnete es im Licht einer Lampe ein neues Buch und reiste in die Ferne.",
    "fr": "Il était une fois, dans une petite ville au bord de la mer, un enfant curieux qui adorait lire. "
          "Chaque soir, à la lumière d'une lampe, il ouvrait un nouveau livre et voyageait très loin.",
    "pt": "Era uma vez, numa pequena cidade à beira-mar, uma criança curiosa que adorava ler. "
          "Todas as noites, à luz de um candeeiro, abria um livro novo e viajava para muito longe.",
    "ru": "Жил-был в маленьком городке у моря любопытный ребёнок, который очень любил читать. "
          "Каждый вечер при свете лампы он открывал новую книгу и уносился далеко-далеко.",
    "ar": "كان يا ما كان، في بلدة صغيرة على شاطئ البحر، عاش طفل فضولي يحب القراءة. "
          "وفي كل مساء، على ضوء مصباح، كان يفتح كتابًا جديدًا ويسافر بعيدًا.",
    "da": "Der var engang, i en lille by ved havet, et nysgerrigt barn, som elskede at læse. "
          "Hver aften, i lyset fra en lampe, åbnede det en ny bog og rejste langt væk.",
    "nl": "Er was eens, in een klein stadje aan zee, een nieuwsgierig kind dat dol was op lezen. "
          "Elke avond, bij het licht van een lamp, opende het een nieuw boek en reisde ver weg.",
    "fi": "Olipa kerran pienessä kaupungissa meren rannalla utelias lapsi, joka rakasti lukemista. "
          "Joka ilta lampun valossa hän avasi uuden kirjan ja matkusti kauas.",
    "el": "Μια φορά κι έναν καιρό, σε μια μικρή πόλη δίπλα στη θάλασσα, ζούσε ένα περίεργο παιδί που αγαπούσε το διάβασμα. "
          "Κάθε βράδυ, στο φως μιας λάμπας, άνοιγε ένα καινούργιο βιβλίο και ταξίδευε μακριά.",
    "he": "היה היה פעם, בעיירה קטנה על שפת הים, ילד סקרן שאהב לקרוא. "
          "בכל ערב, לאור מנורה, הוא פתח ספר חדש ונסע למקומות רחוקים.",
    "hi": "एक समय की बात है, समुद्र के किनारे एक छोटे से शहर में एक जिज्ञासु बच्चा रहता था, जिसे पढ़ना बहुत पसंद था। "
          "हर शाम, एक दीपक की रोशनी में, वह एक नई किताब खोलता और दूर की यात्रा पर निकल जाता।",
    "id": "Pada suatu hari, di sebuah kota kecil di tepi laut, hiduplah seorang anak yang penuh rasa ingin tahu dan suka membaca. "
          "Setiap malam, di bawah cahaya lampu, ia membuka buku baru dan berkelana jauh.",
    "no": "Det var en gang, i en liten by ved havet, et nysgjerrig barn som elsket å lese. "
          "Hver kveld, i lyset fra en lampe, åpnet det en ny bok og reiste langt av gårde.",
    "pl": "Dawno, dawno temu, w małym miasteczku nad morzem, żyło ciekawskie dziecko, które uwielbiało czytać. "
          "Każdego wieczoru, przy świetle lampy, otwierało nową książkę i wyruszało w daleką podróż.",
    "sw": "Hapo zamani za kale, katika mji mdogo kando ya bahari, aliishi mtoto mdadisi aliyependa kusoma. "
          "Kila jioni, kwa mwanga wa taa, alifungua kitabu kipya na kusafiri mbali.",
    "sv": "Det var en gång, i en liten stad vid havet, ett nyfiket barn som älskade att läsa. "
          "Varje kväll, i ljuset från en lampa, öppnade det en ny bok och reste långt bort.",
    "tl": "Noong unang panahon, sa isang maliit na bayan sa tabi ng dagat, may isang batang mausisa na mahilig magbasa. "
          "Tuwing gabi, sa liwanag ng isang lampara, nagbubukas siya ng bagong aklat at naglalakbay nang malayo.",
    "vi": "Ngày xửa ngày xưa, ở một thị trấn nhỏ bên bờ biển, có một đứa trẻ tò mò rất thích đọc sách. "
          "Mỗi tối, dưới ánh đèn, em mở một cuốn sách mới và du hành đến những nơi xa xôi.",
}
NARRATOR = "A warm, calm adult narrator with clear diction, reading a story aloud at an even pace"

SHARED_GB = 6.3   # the server's own environment and Whisper
ALIGNER_GB = 1.3  # each language's word-timing model


def enabled(env) -> list[str]:
    """The languages chosen in RACCONTAMI_LANGUAGES ("en,es"), sorted; English and Italian without it."""
    value = env.get("RACCONTAMI_LANGUAGES", "")
    chosen = {c.strip().lower() for c in value.split(",") if c.strip()} if value.strip() else set(DEFAULT)
    return sorted(c for c in chosen if c in LANGUAGES)


def samples(data: Path | None = None) -> set[str]:
    """The languages VoxCPM2 has a narrator sample for: in voices/ (shipped), or in <data>/narrators/ (made
    on this computer by tools/make_narrator.py)."""
    out = {p.name[len("voxcpm2_"):-len("_ref.wav")] for p in SAMPLES_DIR.glob("voxcpm2_*_ref.wav")}
    if data is not None:
        out |= {p.name[len("voxcpm2_"):-len("_ref.wav")] for p in (Path(data) / "narrators").glob("voxcpm2_*_ref.wav")}
    return out


def _can_speak(lang: str, voice: str, have_samples: set[str]) -> bool:
    """Whether [voice] narrates [lang] now: a voice that copies a narrator needs its sample."""
    return not VOICE_MODELS[voice]["sample"] or lang in have_samples


def _can_install(lang: str, voice: str, have_samples: set[str]) -> bool:
    """Whether installing [voice] gives [lang] a narrator: a missing sample can be made from the sample text."""
    return _can_speak(lang, voice, have_samples) or lang in SAMPLE_TEXT


def voice_for(lang: str, installed, samples: set[str] | None = None) -> str | None:
    """The voice that narrates [lang]: the first of its voices that is installed and can speak it now."""
    have = globals()["samples"]() if samples is None else samples
    return next((v for v in LANGUAGES[lang]["voices"] if v in installed and _can_speak(lang, v, have)), None)


def _planned(lang: str, have: set[str]) -> str | None:
    return next((v for v in LANGUAGES[lang]["voices"] if _can_install(lang, v, have)), None)


def voices_needed(langs, samples: set[str] | None = None) -> set[str]:
    """The voice models to install for these languages: each language's preferred one that can speak it,
    with a narrator made on this computer if needed."""
    have = globals()["samples"]() if samples is None else samples
    return {v for v in (_planned(lang, have) for lang in langs) if v}


def narrators_to_make(langs, samples: set[str] | None = None) -> list[str]:
    """The languages whose narrator is made on this computer: VoxCPM2 narrates them and has no sample yet."""
    have = globals()["samples"]() if samples is None else samples
    return [lang for lang in langs if VOICE_MODELS.get(_planned(lang, have) or "", {}).get("sample") and lang not in have]


def voice_config(lang: str, voice: str, python: str, data: Path | None = None) -> dict:
    """What the narration worker needs to speak [lang] with [voice] (the same keys as before languages
    could be chosen, so finished English and Italian narrations are still recognised). A VoxCPM2 narrator
    is the shipped sample in voices/, or the one made on this computer in <data>/narrators/."""
    if voice == "qwen3":
        return {"engine": "qwen3", "python": python, "speaker": "aiden", "language": LANGUAGES[lang]["qwen"],
                "label": "Qwen3-TTS · Aiden"}
    shipped = SAMPLES_DIR / f"voxcpm2_{lang}_ref.wav"
    sample = shipped if shipped.exists() or data is None else Path(data) / "narrators" / f"voxcpm2_{lang}_ref.wav"
    return {"engine": "voxcpm2", "python": python, "voice": str(sample),
            "label": f"VoxCPM2 ({LANGUAGES[lang]['name']} narrator)"}


def voice_table(langs, installed, python_of, samples: set[str] | None = None, data: Path | None = None) -> dict:
    """Language -> what narrates it, for the languages that have an installed voice which can speak them."""
    have = globals()["samples"](data) if samples is None else samples
    out = {}
    for lang in langs:
        voice = voice_for(lang, installed, have)
        if voice:
            out[lang] = voice_config(lang, voice, python_of(voice), data)
    return out

def name(lang: str) -> str:
    return LANGUAGES.get(lang, {}).get("name", lang)


def missing(lang: str) -> str:
    """For the phone, in plain words, when it asks for a language this server does not have."""
    n = name(lang) if lang in LANGUAGES else f"the language “{lang}”"
    return (f"This server has no {n}. Add it by opening the server's installer again and ticking it, "
            "or sync this story on the phone.")


def no_voice(lang: str) -> str:
    """For the phone, in plain words, when this server syncs a language but cannot read it aloud."""
    return (f"This server syncs {name(lang)} but has no voice to read it aloud yet. The story can be synced "
            "with an audiobook instead.")


def downloads(langs, samples: set[str] | None = None) -> list[str]:
    """The Hugging Face models these languages need: their word-timing models, then their voice models."""
    return ([LANGUAGES[lang]["aligner"] for lang in langs]
            + [VOICE_MODELS[v]["repo"] for v in sorted(voices_needed(langs, samples))])


def size_gb(langs, samples: set[str] | None = None) -> float:
    """About how much a new install with these languages takes."""
    voices = voices_needed(langs, samples)
    return round(SHARED_GB + sum(VOICE_MODELS[v]["model_gb"] + VOICE_MODELS[v]["env_gb"] for v in voices)
                 + ALIGNER_GB * len(list(langs)), 1)
