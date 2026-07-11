"""Spike S-3 — code-switched Hindi/Marathi/English STT benchmark.

Runs a candidate STT model over a manifest of (audio, reference) pairs and
reports WER, CER, and realtime factor. The realtime factor matters as much as
accuracy: for live voice (Milestone 3) transcription must run faster than
realtime on Aditya's CPU, or the ≤1.2 s voice budget (PRD Section 24) is dead on
arrival.

Manifest format (spikes/s3_testset/manifest.tsv), tab-separated:
    <audio_filename>\t<reference transcript>

Usage:
    python spikes/s3_stt_probe.py [--model small] [--testset spikes/s3_testset]

Real accuracy requires Aditya's own recordings (his accent + code-switching are
the point). See spikes/s3_testset/README.md for the recording protocol. Until
those exist, --synth generates SAPI English samples to smoke-test the pipeline.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aero.eval.wer import cer, wer  # noqa: E402
from aero.perception.stt import FasterWhisperBackend  # noqa: E402

# Realtime-factor bar for live voice; accuracy bars are judged with real audio.
RTF_BAR = 1.0
WER_TARGET = 0.25  # pragmatic target for usable code-switched transcripts


def load_manifest(testset: Path) -> list[tuple[Path, str]]:
    manifest = testset / "manifest.tsv"
    if not manifest.exists():
        return []
    pairs = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fn, _, ref = line.partition("\t")
        audio = testset / fn.strip()
        if audio.exists():
            pairs.append((audio, ref.strip()))
    return pairs


def run(model_name: str, pairs: list[tuple[Path, str]]) -> int:
    stt = FasterWhisperBackend(model_name)
    if not stt.health_check():
        print("faster-whisper not installed. pip install faster-whisper")
        return 1
    print(f"STT model: {model_name} ({stt.compute_type}, {stt.device})\n")

    wers, cers, rtfs = [], [], []
    for audio, ref in pairs:
        t = stt.transcribe(str(audio))
        w, c = wer(ref, t.text), cer(ref, t.text)
        wers.append(w); cers.append(c); rtfs.append(t.realtime_factor)
        print(f"  {audio.name}  [{t.language}]  WER={w:.2f} CER={c:.2f} RTF={t.realtime_factor:.2f}")
        print(f"    ref: {ref}")
        print(f"    hyp: {t.text}\n")

    if not wers:
        print("No audio pairs found. Add recordings per spikes/s3_testset/README.md")
        return 1

    print("=" * 60)
    print(f"  mean WER : {statistics.mean(wers):.2f}  (target < {WER_TARGET})")
    print(f"  mean CER : {statistics.mean(cers):.2f}")
    print(f"  mean RTF : {statistics.mean(rtfs):.2f}  (need < {RTF_BAR} for live voice)")
    ok = statistics.mean(wers) < WER_TARGET and statistics.mean(rtfs) < RTF_BAR
    print(f"  verdict  : {'PASS' if ok else 'REVIEW (see per-item + protocol)'}")
    return 0 if ok else 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="small")
    ap.add_argument("--testset", default=str(Path(__file__).parent / "s3_testset"))
    args = ap.parse_args()
    pairs = load_manifest(Path(args.testset))
    return run(args.model, pairs)


if __name__ == "__main__":
    raise SystemExit(main())
