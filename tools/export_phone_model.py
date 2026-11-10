"""Export wav2vec2 CTC models to ONNX with int8 weights, for on-phone sync.

  python tools/export_phone_model.py <hf-model-id> [<out-dir>]   (default out-dir: <home>/onnx)

The app downloads these (Settings > On-phone models):
  English  facebook/wav2vec2-base-960h
  Italian  jonatasgrosman/wav2vec2-large-xlsr-53-italian
Other languages: convert any wav2vec2-style CTC model the same way, see docs/phone-models.md.

Writes <name>.int8.onnx (input: float32 audio [1, samples] at 16 kHz,
normalised; output: logits [1, frames, vocab]) and <name>.vocab.json
(token -> id, plus "_blank" and "_sep" ids and "_norm" whether the model
expects zero-mean unit-variance input).
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from raccontami_sync.paths import MODELS, ONNX  # noqa: E402

os.environ.setdefault("HF_HOME", str(MODELS / "hf"))

import torch  # noqa: E402
from onnxruntime.quantization import QuantType, quantize_dynamic  # noqa: E402
from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor  # noqa: E402


def main(model_id: str, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    name = model_id.split("/")[-1]
    proc = Wav2Vec2Processor.from_pretrained(model_id)
    model = Wav2Vec2ForCTC.from_pretrained(model_id).eval()
    fp32 = out / f"{name}.fp32.onnx"
    dummy = torch.zeros(1, 16000 * 5)
    torch.onnx.export(
        model, (dummy,), str(fp32), input_names=["audio"], output_names=["logits"],
        dynamic_axes={"audio": {1: "samples"}, "logits": {1: "frames"}}, opset_version=17, dynamo=False,
    )
    int8 = out / f"{name}.int8.onnx"
    quantize_dynamic(str(fp32), str(int8), weight_type=QuantType.QInt8)
    fp32.unlink()
    vocab = proc.tokenizer.get_vocab()
    vocab["_blank"] = proc.tokenizer.pad_token_id
    vocab["_sep"] = vocab.get("|", -1)
    vocab["_norm"] = bool(getattr(proc.feature_extractor, "do_normalize", True))
    (out / f"{name}.vocab.json").write_text(json.dumps(vocab, ensure_ascii=False), encoding="utf-8")
    print(name, round(int8.stat().st_size / 1e6), "MB")


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]) if len(sys.argv) > 2 else ONNX)
