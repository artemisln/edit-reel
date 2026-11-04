#!/usr/bin/env python3
"""
trim-raw-video / analyze.py
Analysis pass for raw talking-head footage: probe + silence + volume + transcript.

Usage:
  python3 analyze.py VIDEO [VIDEO2 ...] [--lang en] [--model auto]
  python3 analyze.py --regions VIDEO@START-END [VIDEO@START-END ...] [--lang en]

Default mode  -> writes ./_trim_work/<tag>.transcript.json  and  ./_trim_work/report.txt
Region mode   -> re-transcribes exact time windows and prints precise word timings
                 (use this to nail cut boundaries for chosen takes).

Needs: ffmpeg/ffprobe on PATH, python packages `openai-whisper` and `numpy`.
"""
import sys, os, json, math, subprocess, wave

WORK = "_trim_work"


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def probe(path):
    """Return stored size, rotation, and TRUE display size (rotation applied)."""
    r = sh(["ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate",
            "-show_entries", "stream_side_data=rotation",
            "-show_entries", "stream_tags=rotate",
            "-show_entries", "format=duration", "-of", "json", path])
    info = json.loads(r.stdout or "{}")
    st = (info.get("streams") or [{}])[0]
    fmt = info.get("format", {})
    W, H = int(st.get("width") or 0), int(st.get("height") or 0)
    rot = 0
    for sd in st.get("side_data_list", []) or []:
        if sd.get("rotation") is not None:
            rot = int(sd["rotation"])
    if not rot:
        rot = int((st.get("tags", {}) or {}).get("rotate", 0) or 0)
    swap = (abs(rot) % 180) == 90          # 90/270 deg -> width & height swap on display
    dW, dH = (H, W) if swap else (W, H)
    n, d = (st.get("r_frame_rate", "0/1").split("/") + ["1"])[:2]
    fps = round(float(n) / float(d), 2) if float(d) else 0.0
    return dict(stored=(W, H), rotation=rot, display=(dW, dH),
                fps=fps, duration=round(float(fmt.get("duration", 0) or 0), 2))


def to_wav(path, wav, ss=None, t=None):
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    if ss is not None:
        cmd += ["-ss", str(ss)]
    cmd += ["-i", path]
    if t is not None:
        cmd += ["-t", str(t)]
    cmd += ["-vn", "-ac", "1", "-ar", "16000", wav]
    sh(cmd)


def silences(wav, noise="-30dB", d=0.4):
    r = sh(["ffmpeg", "-i", wav, "-af",
            f"silencedetect=noise={noise}:d={d}", "-f", "null", "-"])
    out, start = [], None
    for ln in r.stderr.splitlines():
        if "silence_start:" in ln:
            try:
                start = float(ln.split("silence_start:")[1].strip())
            except ValueError:
                start = None
        elif "silence_end:" in ln and start is not None:
            end = float(ln.split("silence_end:")[1].split("|")[0].strip())
            out.append((round(start, 2), round(end, 2)))
            start = None
    return out


def volume(wav):
    """Median voiced level + list of loud spikes (often crew banter / frustration)."""
    import numpy as np
    w = wave.open(wav, "rb")
    sr = w.getframerate()
    data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(float)
    w.close()
    win = int(sr * 0.25)
    prof = []
    for i in range(0, max(0, len(data) - win), win):
        seg = data[i:i + win]
        rms = math.sqrt(float(np.mean(seg ** 2))) + 1e-9
        prof.append((round(i / sr, 2), round(20 * math.log10(rms / 32768.0), 1)))
    voiced = [db for _, db in prof if db > -32]
    if not voiced:
        return 0.0, []
    med = float(np.median(voiced))
    spikes = [(t, db) for t, db in prof if db > med + 6]
    return round(med, 1), spikes


def transcribe(model, wav, lang, offset=0.0):
    r = model.transcribe(wav, language=lang, word_timestamps=True,
                         condition_on_previous_text=False)  # False = no hallucination bleed
    segs = []
    for s in r["segments"]:
        words = [dict(w=x["word"], s=round(x["start"] + offset, 2),
                      e=round(x["end"] + offset, 2)) for x in s.get("words", [])]
        segs.append(dict(start=round(s["start"] + offset, 2),
                         end=round(s["end"] + offset, 2),
                         logprob=round(s.get("avg_logprob", 0.0), 2),
                         text=s["text"].strip(), words=words))
    return segs


def aspect_name(w, h):
    if not w or not h:
        return "?"
    r = w / h
    for name, val in [("9:16", 9 / 16), ("3:4", 3 / 4), ("1:1", 1.0),
                      ("4:5", 4 / 5), ("4:3", 4 / 3), ("16:9", 16 / 9)]:
        if abs(r - val) < 0.04:
            return name
    return f"{r:.2f}:1"


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    lang, model_name, regions_mode, inputs = "en", "auto", False, []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--lang":
            lang = args[i + 1]; i += 2
        elif a == "--model":
            model_name = args[i + 1]; i += 2
        elif a == "--regions":
            regions_mode = True; i += 1
        else:
            inputs.append(a); i += 1
    if model_name == "auto":
        model_name = "medium.en" if lang == "en" else "medium"
    os.makedirs(WORK, exist_ok=True)

    import whisper
    print(f"[loading whisper model: {model_name} ... first run downloads it]", flush=True)
    model = whisper.load_model(model_name)

    if regions_mode:
        for spec in inputs:
            path, rng = spec.rsplit("@", 1)
            a, b = (float(x) for x in rng.split("-"))
            wav = os.path.join(WORK, "_region.wav")
            to_wav(path, wav, ss=a, t=b - a)
            segs = transcribe(model, wav, lang, offset=a)
            print(f"\n=== {os.path.basename(path)} @ {a}-{b} ===", flush=True)
            for s in segs:
                print(f"  [{s['start']:7.2f}-{s['end']:7.2f}] lp={s['logprob']:5.2f}  {s['text']}")
                for w in s["words"]:
                    print(f"      {w['w']:22s} {w['s']:7.2f} - {w['e']:7.2f}")
        return

    report = []
    for path in inputs:
        tag = os.path.splitext(os.path.basename(path))[0]
        info = probe(path)
        wav = os.path.join(WORK, f"{tag}.wav")
        to_wav(path, wav)
        sil = silences(wav)
        med, spikes = volume(wav)
        segs = transcribe(model, wav, lang)
        with open(os.path.join(WORK, f"{tag}.transcript.json"), "w") as f:
            json.dump(segs, f, indent=1)
        dw, dh = info["display"]
        L = report.append
        L(f"\n{'=' * 72}\nVIDEO: {path}   (tag: {tag})\n{'=' * 72}")
        L(f"  stored {info['stored'][0]}x{info['stored'][1]}  rotation {info['rotation']}deg"
          f"  ->  DISPLAY {dw}x{dh}  ({aspect_name(dw, dh)})   {info['fps']}fps  {info['duration']}s")
        if info["rotation"]:
            L("  NOTE: rotated source -- use the DISPLAY size above for any crop math.")
        L(f"  voiced median {med}dB | loud spikes >med+6dB (crew banter / blown takes?): {len(spikes)}")
        for t, db in spikes[:50]:
            L(f"      spike {t:7.2f}s  {db}dB")
        L(f"  silence gaps >0.4s: {len(sil)}")
        L("\n  --- FULL-FILE TRANSCRIPT (lp = avg_logprob; very negative = unclear/mumbled) ---")
        for s in segs:
            L(f"  [{s['start']:7.2f}-{s['end']:7.2f}] lp={s['logprob']:5.2f}  {s['text']}")
    text = "\n".join(report)
    with open(os.path.join(WORK, "report.txt"), "w") as f:
        f.write(text + "\n")
    print(text)
    print(f"\n[written {WORK}/report.txt + per-video <tag>.transcript.json]")


if __name__ == "__main__":
    main()
