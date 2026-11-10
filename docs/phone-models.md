# Speech models for on-phone sync

Raccontami can sync an audiobook with its text on the phone, without a server. For
that it needs a speech model for the book's language. English and Italian come
ready (Settings → On-phone models → Download). For any other language, or to try a
different model, you can add one from Hugging Face.

## Adding a model

1. In the app: **Settings → Other models → Add a model**.
2. Paste the model's name from Hugging Face, like
   `jonatasgrosman/wav2vec2-large-xlsr-53-french`, or its link.
3. The app checks it **before downloading** and shows what it found.
4. Pick the language of the books it is for and tap **Download**.
5. After the download it checks the model **runs on your phone** and how fast.
6. Tap **Test quality** with a story in that language that has its audiobook. The
   story does not need to be synced first.

Each language uses one model. A model you add for a new language is used straight
away. For English or Italian the standard model stays in use until you tap
**Use it**.

## What the checks mean

| Check | What it means |
|---|---|
| Speech model of the right kind | It is a CTC speech model (wav2vec2, HuBERT, WavLM…). Others, such as Whisper, cannot be used. |
| Phone-ready file | It has an ONNX file the phone can run. Compressed (int8) files are about 3–4× smaller, and usually faster. |
| Writes letters | It spells words letter by letter. Models that write word pieces cannot be lined up with the text. |
| License | How the author lets you use it. "Personal use only" is fine for your own books. "No license stated" means the author has not said. |
| Runs on this phone | It loads and gives output of the right shape. The speed shows how many times faster than real time it runs: 10× means a 10-hour book takes about an hour. |

## Quality test

The model listens to the first 2 minutes of the story. The app then counts how many
of the words it heard are found in the text, in order.

| Result | Meaning |
|---|---|
| **Good** (75 % or more) | The highlight follows the voice well. The standard Italian model scores 80 % on a human narrator. |
| **Usable** (50–75 %) | It works, with some places out of step. |
| **Poor** (under 50 %) | Not good enough for this book: try another model. |

A recording that opens with music or a long introduction scores a little lower than
the book itself.

## Finding a model

Search Hugging Face for
[wav2vec2 speech recognition models](https://huggingface.co/models?pipeline_tag=automatic-speech-recognition&search=wav2vec2)
and add your language, for example "wav2vec2 french".

Good signs:

- the name contains **wav2vec2**, **xlsr** or **hubert**, and your language;
- many downloads, and a model card that reports a low error rate (WER);
- a folder called **onnx** with a `model_int8.onnx` or `model_quantized.onnx` file:
  then it is phone-ready.

Models by `jonatasgrosman` cover many European languages, and `Xenova` /
`onnx-community` publish phone-ready (ONNX) conversions of popular ones.

## Converting a model that has no ONNX file

Most models are published only for PyTorch. You can convert one on a computer with
Python, using the tool in this repo:

```sh
git clone https://github.com/alessandrobelli/raccontami-server
cd raccontami-server
python -m venv env && . env/bin/activate      # on Windows: env\Scripts\activate
pip install torch transformers onnx onnxruntime
python tools/export_phone_model.py jonatasgrosman/wav2vec2-large-xlsr-53-french out
```

It writes two files to `out/`: `<name>.int8.onnx` and `<name>.vocab.json`. Then:

- **copy both to the phone** and use **Settings → On-phone models → Import from
  files**; or
- **upload both to your own Hugging Face model** and add that in the app. The app
  recognizes the pair and uses it as it is.

A graphics card is not needed. A large model takes a few minutes and a few GB of
memory to convert.

## Limits

- Narration (reading a text aloud) is in English and Italian only. Added languages
  sync your own audiobooks.
- Numbers written as digits are not matched, because the models write only letters.
  The words around them still are.
- Very large models (over 1.5 GB) are refused; over 450 MB they work, but slowly.
