# Find the Photo

**Find one hidden photograph. Make it genuinely unexpected.**

`find-the-photo` is a small executable Agent Skill that looks for a compelling local photograph inside an ordinary, cluttered, or badly framed image. A visual agent proposes bold source-aspect framings, the scripts render exact raw crops, a blind photography-editor pass checks standalone quality, and a second Discovery Gate rejects crops that are merely closer versions of the original.

The result is exactly one `unexpected` crop—or none when the source cannot produce a convincing discovery. Every final crop occupies less than 50% of the source area. Small crops can receive conservative local Resolution Recovery, while the raw crop is always preserved.

## Conditional processing

- Every crop keeps the source photograph's aspect ratio and occupies less than 50% of the source area.
- A crop using less than 20% of source area gets a raw PNG plus a processed PNG restored to the source pixel dimensions.
- A visibly tilted or mildly distorted crop may receive up to ±5° rotation or 8% perspective correction.
- A tiny simple distraction may be locally inpainted only when masks total no more than 1% of the crop and avoid people, text, plates, and defining subject edges.
- Processing uses fixed, disclosed local operations. It does not reconstruct factual detail.

There is no generative fill, neural image synthesis, hosted backend, external image API, or separate API key. The scripts do not upload the image; image handling still follows the privacy terms of the agent platform you use.

## Supported input

- JPG / JPEG
- PNG, including transparency
- WebP still images

Animated images and mislabeled file extensions are rejected. EXIF orientation is applied before crop coordinates are interpreted.

## Requirements

- Python 3.10+
- A visual-capable agent runtime that can execute local commands
- Pillow 10–12, NumPy, and OpenCV Headless

## Install

```bash
cd find-the-photo
python -m pip install -r requirements.txt
```

Download or clone this repository before running the commands above.

Install the folder as a local skill using the method supported by your agent runtime. Codex-compatible runtimes can discover personal skills from `~/.agents/skills/find-the-photo/`.

## Use

Attach one supported photograph and ask:

```text
Use $find-the-photo on this image. Find one genuinely unexpected photograph hidden inside it.
```

The skill creates an oriented preview, 6–10 same-aspect candidate crops, a blind critic scorecard, a source-comparison Discovery Gate, and one final composition. Run artifacts retain coordinates and technical manifests so every crop and optional processed companion is reproducible.

## Test

```bash
python -m unittest discover -s tests -v
python scripts/prepare_photo.py --help
python scripts/crop_photo.py --help
python scripts/process_crop.py --help
```

Use [`tests/manual-evaluation.md`](tests/manual-evaluation.md) for real-photo taste testing. The evaluation sheet deliberately separates proposer, critic, selection, coordinate, and rendering failures so later prompt changes stay narrow.

## How it works

1. Normalize EXIF orientation into a lossless preview.
2. Propose 6–10 bold source-aspect crop boxes, all below 50% of the source area and all intended as unexpected discoveries.
3. Render the boxes locally as untouched raw PNGs.
4. Ask a critic who sees only the candidates whether each works as a standalone photograph.
5. Compare blind keepers with the source, then re-render exactly one qualified Discovery-Gate winner from the source.
6. Process only sub-20% winners or crops with an approved gentle correction, then show raw before processed.

## License

MIT
