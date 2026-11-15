"""Exploration helpers used while choosing and verifying cut points.   (run via `clip <cmd>`, interpreter: venv)
  pauses  <a> <b> [th_db] [min_s]   quiet runs (real pauses) inside a source range
  snap    <t> [window_s]            nearest pauses around t (cut candidates), best first
  words   <a> <b>                   YouTube caption words with times for a range ('>>' = speaker change)
  look    <a> <b> [n]               contact sheet of n frames between a and b (verify who is on screen / who is speaking)
  frame   <t>                       one full-res frame
  cuts    <a> <b>                   shot changes (scene detect) in a range -> helps place crop windows
  silences                          (re)build the whole-source pause cache
  preview <video.mp4> [n] [t1,t2..] contact sheet of a RENDERED clip (n evenly spaced frames + extra times, e.g. the joins)"""
import json, os, re, subprocess, sys
import common
from common import *
sys.path.insert(0, LIB)
import ytcaps

def silences():
    p = f"{WORK}/silences.json"
    if os.path.exists(p): return json.load(open(p))
    os.makedirs(WORK, exist_ok=True)
    print("building pause cache (one pass over the audio, ~1 min per hour)...", file=sys.stderr)
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", SRC, "-vn", "-af", "silencedetect=n=-46dB:d=0.12", "-f", "null", "-"], capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [(float(a), float(b)) for a, b in re.findall(r"silence_end: ([\d.]+) \| silence_duration: ([\d.]+)", r.stderr)]
    runs = [[round(e - d, 3), round(e, 3)] for e, d in ends]
    json.dump(runs, open(p, "w")); return runs

def cmd_pauses(a, b, th=None, ml=None):
    if th is not None or ml is not None:   # custom threshold -> direct pass on the range
        th = th if th is not None else -46; ml = ml if ml is not None else 0.12
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-ss", str(a), "-t", str(b - a), "-i", SRC, "-vn", "-af", f"silencedetect=n={th}dB:d={ml}", "-f", "null", "-"], capture_output=True, text=True)
        ends = [(float(x), float(y)) for x, y in re.findall(r"silence_end: ([\d.]+) \| silence_duration: ([\d.]+)", r.stderr)]
        runs = [[a + e - d, a + e] for e, d in ends]
    else:
        runs = [r for r in silences() if r[1] >= a and r[0] <= b]
    for s, e in runs: print(f"{ts(s,2):>9} - {ts(e,2):>9}  ({e-s:.2f}s)  mid {ts((s+e)/2,2)}")

def cmd_snap(t, window=1.5):
    c = [r for r in silences() if r[1] >= t - window and r[0] <= t + window]
    c.sort(key=lambda r: abs((r[0] + r[1]) / 2 - t))
    print(f"pauses near {ts(t,2)} (best cut points: long pauses; a cut needs >= ~0.2 s of quiet on both sides):")
    for s, e in c: print(f"  {ts(s,2)} - {ts(e,2)}  len {e-s:.2f}s  mid {(s+e)/2:.2f}  ({(s+e)/2 - t:+.2f}s from target)")
    if not c: print("  none within the window - widen it, or choose a different sentence boundary")

def captions_words():
    cap = common._JOB.get("captions")
    if cap and os.path.exists(f"{JOB}/{cap}"): return ytcaps.parse(f"{JOB}/{cap}")
    p = f"{JOB}/source/words_whisper.json"
    if os.path.exists(p): return json.load(open(p))
    sys.exit("no transcript for this job: run `clip transcript` first")

def cmd_words(a, b):
    ws = [w for w in captions_words() if a - 0.01 <= w["s"] <= b]; line = []; t0 = None
    for w in ws:
        if t0 is None: t0 = w["s"]
        line.append(w["w"])
        if len(line) >= 10 or w["w"][-1:] in ".?!":
            print(f"[{ts(t0,2)}] " + " ".join(line)); line = []; t0 = None
    if line: print(f"[{ts(t0,2)}] " + " ".join(line))

def cmd_look(a, b, n=8):
    from PIL import Image, ImageDraw, ImageFont
    os.makedirs(f"{WORK}/looks", exist_ok=True); n = int(n)
    ts_ = [a + (b - a) * i / max(1, n - 1) for i in range(n)]; tiles = []
    for t in ts_:
        out = f"{WORK}/looks/_f.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", SRC, "-frames:v", "1", "-vf", "scale=640:-1", out], check=True)
        im = Image.open(out).convert("RGB"); d = ImageDraw.Draw(im)
        d.rectangle((0, 0, 150, 30), fill=(0, 0, 0)); d.text((8, 7), ts(t, 1), fill=(255, 255, 255)); tiles.append(im)
    cols = 3 if n > 4 else 2; rows = (n + cols - 1) // cols; w, h = tiles[0].size
    sheet = Image.new("RGB", (cols * w, rows * h), (0, 0, 0))
    for i, im in enumerate(tiles): sheet.paste(im, ((i % cols) * w, (i // cols) * h))
    out = f"{WORK}/looks/look_{int(a)}_{int(b)}.jpg"; sheet.save(out, quality=88); os.remove(f"{WORK}/looks/_f.png"); print(out)


def cmd_preview(path, n=12, extra=""):
    from PIL import Image, ImageDraw
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True).stdout)
    n = int(n); times = sorted(set([round(dur * (i + 0.5) / n, 2) for i in range(n)] + [float(x) for x in str(extra).split(",") if x]))
    tiles = []
    for t in times:
        out = f"{WORK}/looks/_p.png"; os.makedirs(f"{WORK}/looks", exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", "-vf", "scale='if(gt(ih,iw),400,640)':-1", out], check=True)
        im = Image.open(out).convert("RGB"); d = ImageDraw.Draw(im); d.rectangle((0, 0, 90, 28), fill=(0, 0, 0)); d.text((8, 7), f"{t:.1f}s", fill=(255, 255, 255)); tiles.append(im)
    cols = 4 if tiles[0].size[1] > tiles[0].size[0] else 3; rows = (len(tiles) + cols - 1) // cols; w, h = tiles[0].size
    sheet = Image.new("RGB", (cols * w, rows * h)); [sheet.paste(im, ((i % cols) * w, (i // cols) * h)) for i, im in enumerate(tiles)]
    out = f"{WORK}/looks/preview_{os.path.basename(path)[:-4]}.jpg"; sheet.save(out, quality=88); print(out)

def cmd_frame(t):
    os.makedirs(f"{WORK}/looks", exist_ok=True); out = f"{WORK}/looks/frame_{t:.1f}.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", SRC, "-frames:v", "1", out], check=True); print(out)

def cmd_cuts(a, b, thr=0.3):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-ss", str(a), "-t", str(b - a), "-i", SRC, "-vf", f"scale=320:-1,select='gt(scene,{thr})',showinfo", "-an", "-f", "null", "-"], capture_output=True, text=True)
    for m in re.findall(r"pts_time:([\d.]+)", r.stderr): print(ts(a + float(m), 2))

if __name__ == "__main__":
    c = sys.argv[1]
    if c == "preview": cmd_preview(*sys.argv[2:]); sys.exit(0)
    a = [float(x) for x in sys.argv[2:]]
    {"pauses": cmd_pauses, "snap": cmd_snap, "words": cmd_words, "look": cmd_look, "frame": cmd_frame, "cuts": cmd_cuts,
     "silences": lambda: print(len(silences()), "pauses cached")}[c](*a)
