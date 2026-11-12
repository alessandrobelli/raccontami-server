"""Narration worker: reads <job>/plan.json and writes one WAV per text piece
into <job>/pieces/. Runs inside the voice's own Python environment (VoxCPM2
and Qwen3-TTS need different libraries than the sync server), so it imports
nothing from this package.

Pieces already on disk are skipped, so a job interrupted by a restart or a
power cut continues where it stopped. Each piece is written to a temporary
file and renamed, so a half-written piece never counts as done.

Prints one line per finished piece: "piece <index> <audio seconds> <generation seconds>".

  python narrate_worker.py <job dir>
"""

from __future__ import annotations

import json
import os
import sys
import time
import wave
from pathlib import Path

import numpy as np


def pcm16(wav: np.ndarray) -> bytes:
    return (np.clip(wav, -1.0, 1.0) * 32767).astype("<i2").tobytes()


def trim(wav: np.ndarray, sr: int, threshold: float = 0.006) -> np.ndarray:
    """Cuts the silence the voice leaves at both ends; the server adds its own pauses."""
    loud = np.flatnonzero(np.abs(wav) > threshold)
    if len(loud) == 0:
        return wav
    pad = int(0.04 * sr)
    return wav[max(0, loud[0] - pad): loud[-1] + pad]


PEAK_KNEE, PEAK_CEILING = 0.5, 0.8  # of full scale


def level(wav: np.ndarray, sr: int, target: float = 0.1) -> np.ndarray:
    """Brings a piece to the loudness of the others. Each voice speaks at its own volume (one
    designed voice came out much quieter than another), which is heard as soon as narrators take
    turns. The loudness is taken where there is speech, not over the pauses; the gain is kept
    within bounds and peaks are rounded off well below full scale."""
    frame = max(1, sr // 50)
    n = len(wav) // frame
    if n == 0:
        return wav
    rms = np.sqrt(np.mean(wav[:n * frame].reshape(n, frame).astype(np.float64) ** 2, axis=1))
    if rms.max() <= 0:
        return wav
    speech = rms[rms > 0.25 * rms.max()]
    loud = float(np.sqrt(np.mean(speech ** 2)))
    if loud < 1e-4:
        return wav
    out = (wav * min(max(target / loud, 0.1), 6.0)).astype(np.float32)
    # a soft voice has short bursts far above its level (one reached 0.9 of full scale where the
    # others stay near 0.5): they are rounded off above the knee, so nothing comes near clipping
    # and the loudness, which lies well below the knee, does not change
    over = np.abs(out) > PEAK_KNEE
    span = PEAK_CEILING - PEAK_KNEE
    out[over] = np.sign(out[over]) * (PEAK_KNEE + span * np.tanh((np.abs(out[over]) - PEAK_KNEE) / span))
    return out


def plausible(seconds: float, text: str) -> bool:
    """Rejects runaway or truncated takes: speech is roughly 8 to 25 characters a second."""
    chars = max(1, len(text))
    return chars / 30 <= seconds <= max(4.0, chars / 5)


class VoxCPM2Voice:
    def __init__(self, cfg: dict):
        from voxcpm import VoxCPM

        self.ref = cfg["voice"]
        self.model = VoxCPM.from_pretrained(cfg.get("model", "openbmb/VoxCPM2"), load_denoiser=False, optimize=True)
        self.sr = self.model.tts_model.sample_rate
        for _ in range(2):  # compiles the model; minutes the first time, then cached on disk
            self.model.generate(text="Prova di riscaldamento.", reference_wav_path=self.ref)

    def speak(self, text: str, clip: str | None = None) -> np.ndarray:
        """[clip]: another voice's reference clip, for a piece told by a narrator with a voice of their own."""
        return np.asarray(self.model.generate(text=text, reference_wav_path=clip or self.ref), dtype=np.float32)


class QwenVoice:
    def __init__(self, cfg: dict):
        from faster_qwen3_tts import FasterQwen3TTS

        self.speaker, self.language = cfg["speaker"], cfg["language"]
        self.model = FasterQwen3TTS.from_pretrained(cfg.get("model", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"))
        self.sr = 24000
        self.speak("Warm-up.")

    def speak(self, text: str, clip: str | None = None) -> np.ndarray:  # fixed speakers: no clips
        wavs, sr = self.model.generate_custom_voice(text=text, speaker=self.speaker, language=self.language)
        self.sr = sr
        return np.asarray(wavs[0], dtype=np.float32).squeeze()


VOICES = {"voxcpm2": VoxCPM2Voice, "qwen3": QwenVoice}


def main(job: Path) -> None:
    import torch

    torch.set_num_threads(2)
    plan = json.loads((job / "plan.json").read_text(encoding="utf-8"))
    out = job / "pieces"
    out.mkdir(exist_ok=True)
    todo = [p for p in plan["pieces"] if p.get("say") and not (out / f"{p['i']:05d}.wav").exists()]
    # counted over the pieces that are spoken: the silent ones (a narrator's mark) are never made
    print(f"todo {len(todo)} of {sum(1 for p in plan['pieces'] if p.get('say'))}", flush=True)
    if not todo:
        return
    cfg = plan["voice"]
    voice = VOICES[cfg["engine"]](cfg)
    clips = plan.get("voices") or {}
    print("ready", flush=True)
    for p in todo:
        t = time.perf_counter()
        wav = None
        for _attempt in range(3):
            take = voice.speak(p["say"], clips.get(p.get("voice")))
            if plausible(len(take) / voice.sr, p["say"]):
                wav = take
                break
            wav = take if wav is None else wav
        wav = trim(wav, voice.sr)
        if clips:  # several voices in one story: the same loudness for all
            wav = level(wav, voice.sr)
        tmp = out / f"{p['i']:05d}.tmp"
        with wave.open(str(tmp), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(voice.sr)
            w.writeframes(pcm16(wav))
        os.replace(tmp, out / f"{p['i']:05d}.wav")
        print(f"piece {p['i']} {len(wav) / voice.sr:.2f} {time.perf_counter() - t:.2f}", flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
