"""Writes the installer's list of languages (Inno Setup Pascal) from raccontami_sync/languages.py, so the
catalogue stays the one place that says which languages exist and which models they use. Run by
installer\\build.ps1:

  python installer/languages_iss.py > installer/build/languages.iss
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from raccontami_sync import languages as catalogue  # noqa: E402


def tenths(gb: float) -> int:
    return round(gb * 10)


def pascal(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


codes = list(catalogue.LANGUAGES)
made = set(catalogue.narrators_to_make(codes))
arrays = ("LangCode", "LangName", "LangVoice", "LangWindows", "LangTested", "LangMade", "LangAligner")
out = ["{ Made by installer\\languages_iss.py from raccontami_sync\\languages.py: do not edit. }",
       "procedure FillLanguages;", "begin"]
out += [f"  SetArrayLength({a}, {len(codes)});" for a in arrays]
for i, code in enumerate(codes):
    lang = catalogue.LANGUAGES[code]
    voice = next(iter(catalogue.voices_needed([code])), "")  # the voice model this language would install, or none
    out += [f"  LangCode[{i}] := {pascal(code)};", f"  LangName[{i}] := {pascal(lang['name'])};",
            f"  LangVoice[{i}] := {pascal(voice)};", f"  LangWindows[{i}] := {lang['windows']};",
            f"  LangTested[{i}] := {'True' if lang['tested'] else 'False'};",
            f"  LangMade[{i}] := {'True' if code in made else 'False'};",
            f"  LangAligner[{i}] := {pascal(lang['aligner'])};"]
voices = list(catalogue.VOICE_MODELS)
out += [f"  SetArrayLength(VoiceName, {len(voices)});", f"  SetArrayLength(VoiceLabel, {len(voices)});",
        f"  SetArrayLength(VoiceModel10, {len(voices)});", f"  SetArrayLength(VoiceEnv10, {len(voices)});"]
for i, v in enumerate(voices):
    m = catalogue.VOICE_MODELS[v]
    out += [f"  VoiceName[{i}] := {pascal(v)};", f"  VoiceLabel[{i}] := {pascal(m['label'] + ' (' + m['repo'] + ')')};",
            f"  VoiceModel10[{i}] := {tenths(m['model_gb'])};", f"  VoiceEnv10[{i}] := {tenths(m['env_gb'])};"]
out += [f"  Aligner10 := {tenths(catalogue.ALIGNER_GB)};", f"  DefaultNarrator := {pascal(catalogue.NARRATOR)};", "end;", ""]
sys.stdout.write("\n".join(out))
