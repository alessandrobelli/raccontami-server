"""Makes a VoxCPM2 narrator for a language that has none: VoxCPM2 designs a voice from a description
and reads the language's sample text (raccontami_sync/languages.py) with it; the recording becomes the
voice sample the narrations clone, so every chapter has the same narrator.

Run with the Python of the VoxCPM2 environment (<home>/tts/env-a) on a computer with the graphics card:

  python tools/make_narrator.py tr <out.wav> [--description "..."] [--seed 1]

The installer runs it for each chosen language VoxCPM2 narrates without a sample in voices/, and saves
the result as <data>/narrators/voxcpm2_<code>_ref.wav. Running it again makes another narrator.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from raccontami_sync import languages, settings  # noqa: E402

settings.load()  # the models folder may be named there
from raccontami_sync.paths import MODELS, model_homes  # noqa: E402

os.environ.update(model_homes(os.environ, MODELS))
for _name, _value in (("HF_HUB_DISABLE_SYMLINKS_WARNING", "1"), ("HF_HUB_VERBOSITY", "error"), ("TRANSFORMERS_VERBOSITY", "error"),
                      ("HF_HUB_DISABLE_TELEMETRY", "1")):  # no usage reports to Hugging Face (README, Privacy)
    os.environ.setdefault(_name, _value)


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description="Make a VoxCPM2 narrator for a language")
    a.add_argument("lang", choices=sorted(languages.SAMPLE_TEXT))
    a.add_argument("out")
    a.add_argument("--description", default=languages.NARRATOR)
    a.add_argument("--seed", type=int, default=None, help="the same seed gives the same narrator")
    args = a.parse_args(argv)

    import numpy as np
    import soundfile as sf
    import torch
    from voxcpm import VoxCPM

    if args.seed is not None:
        torch.manual_seed(args.seed)
    print(f"Making a narrator for {languages.name(args.lang)} (a few minutes the first time)...", flush=True)
    model = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False)
    # a description in brackets before the text makes VoxCPM2 design the voice (no sample to copy)
    wav = model.generate(text=f"({args.description}){languages.SAMPLE_TEXT[args.lang]}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), np.asarray(wav, dtype=np.float32), model.tts_model.sample_rate)
    print(f"Narrator saved: {out} ({len(wav) / model.tts_model.sample_rate:.1f} s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
