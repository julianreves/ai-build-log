"""QA of one finished clip (run with the venv39 interpreter -I).   usage: check.py <final.mp4> [--deep]
Checks: video spec, loudness / true peak, black frames, every caption sits on speech, no uncaptioned speech,
every quoted graphic is verbatim speech (vs the clip's own whisper words AND YouTube's captions),
and with --deep an independent whisper transcription of the rendered file vs the caption token times.
Writes Jobs/<job>/clips/<NN>.check.json (tiny, survives cleanup) and prints a PASS/FAIL table."""
import json, os, re, subprocess, sys, wave, difflib
import numpy as np
from plan import *
sys.path.insert(0, LIB)
import ytcaps
final = os.path.abspath(sys.argv[1]); deep = "--deep" in sys.argv
os.chdir(out_dir())
res = {}; fails = []
def rec(name, ok, detail):
    res[name] = dict(ok=bool(ok), detail=detail); print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    if not ok: fails.append(name)
# ---- 1. video / audio spec
p = probe(final); st = p["streams"][0]; num, den = [int(x) for x in st["r_frame_rate"].split("/")]
fps_ok = abs(num / den - int(FPS.split("/")[0]) / int((FPS.split("/") + ["1"])[1])) < 0.01
a = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name,sample_rate,channels,duration", "-of", "json", final], capture_output=True, text=True)
au = json.loads(a.stdout)["streams"][0]
dur_v = float(st["duration"]); dur_a = float(au["duration"])
rec("format", st["width"] == OUT_W and st["height"] == OUT_H and fps_ok and st["codec_name"] == "h264" and au["codec_name"] == "aac" and abs(dur_v - dur_a) < 0.3,
    f"{st['width']}x{st['height']} {num}/{den} {st['codec_name']}+{au['codec_name']} {au['sample_rate']}Hz, video {dur_v:.2f}s audio {dur_a:.2f}s")
res["duration"] = round(dur_v, 2)
rec("length", 25 <= dur_v <= 55, f"{dur_v:.1f}s total (interview {INTERVIEW_FRAMES*FT:.1f}s + {CARD*FT:.1f}s end card); target 30-45s")
# ---- 2. loudness
r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", final, "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"], capture_output=True, text=True)
g = lambda k: float(re.search(r'"%s"\s*:\s*"([-\d.inf]+)"' % k, r.stderr).group(1))
I, TP = g("input_i"), g("input_tp")
rec("loudness", abs(I + 16) <= 1.0 and TP <= -1.0, f"{I:.1f} LUFS, true peak {TP:.1f} dBFS (target -16 / <= -1.5)")
# ---- 3. black frames (only the designed final fade is allowed)
r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", final, "-vf", "blackdetect=d=0.2:pic_th=0.98", "-an", "-f", "null", "-"], capture_output=True, text=True)
blacks = [(float(a_), float(b_)) for a_, b_ in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", r.stderr)]
int_end = INTERVIEW_FRAMES * FT        # designed: fade to near-black into the closing card (+ the card's own fade-out at the very end)
bad = [b for b in blacks if not (int_end - 0.8 <= b[0] and b[1] <= dur_v + 0.1)]
rec("black_frames", not bad, "only the designed fades (into the closing card, and at the very end)" if not bad else f"unexpected black at {bad}")
# ---- 4. captions vs audio energy
w = wave.open("base_audio_raw.wav"); sr = w.getframerate(); n = w.getnframes()
x = np.frombuffer(w.readframes(n), dtype=np.int16).reshape(-1, 2).astype(np.float64).mean(axis=1)
hop = int(sr * 0.01); k = len(x) // hop
ENV = (20 * np.log10(np.sqrt((x[:k * hop].reshape(k, hop) ** 2).mean(axis=1)) / 32768 + 1e-9)).tolist()
def dens(a_, b_):
    seg = ENV[int(a_ * 100):int(b_ * 100)]; return sum(1 for d in seg if d > -44) / max(1, len(seg))
caps = json.load(open("captions.json")); low = []
for i, c in enumerate(caps, 1):
    if dens(c["start"], c["end"]) < 0.35 or dens(c["start"], min(c["start"] + 0.35, c["end"])) < 0.2: low.append(i)
cap_iv = [(c["start"], c["end"]) for c in caps]; t = 0.0; gaps = []; INT = INTERVIEW_FRAMES * FT
while t < INT - 0.2:
    if dens(t, t + 0.2) > 0.6 and not any(a_ - 0.05 <= t + 0.1 <= b_ + 0.05 for a_, b_ in cap_iv): gaps.append(t)
    t += 0.2
runs = []
for gt in gaps:
    if runs and gt - runs[-1][1] < 0.45: runs[-1][1] = gt + 0.2
    else: runs.append([gt, gt + 0.2])
runs = [(round(a_, 2), round(b_, 2)) for a_, b_ in runs if b_ - a_ >= 0.45]
rec("captions_on_speech", not low and not runs, f"{len(caps)} captions; low-density/late captions {low or 'none'}; uncaptioned speech >=0.45s: {runs or 'none'}")
# ---- 5. quoted graphics are verbatim speech
def collapse(ws): return [w_ for i_, w_ in enumerate(ws) if i_ == 0 or w_ != ws[i_ - 1]]   # drop stutters (word repeated)
cut_words = " ".join(collapse([t_["n"] for t_ in json.load(open("tokens.json"))]))
job = load_job(); yt = None
vtt = job.get("captions")
if vtt and os.path.exists(f"{JOB}/{vtt}"):
    FILL = {"um", "uh", "uhm"}
    ws = [w_ for w_ in ytcaps.plain_stream(ytcaps.parse(f"{JOB}/{vtt}")) if w_ not in FILL]
    yt = " ".join(w_ for i_, w_ in enumerate(ws) if i_ == 0 or w_ != ws[i_ - 1]); ytn = yt.replace(" ", "")
words_of = lambda s_: [norm(w_) for w_ in re.split(r"[\s|*]+", s_.replace("…", " ")) if norm(w_)]
CE_ = clip_spec_en()      # quotes are always checked against the English speech (Spanish cards are translations of these)
items = [(k_, c["text"]) for k_, c in CE_.get("cards", {}).items()]
for k_, h in CE_.get("heroes", {}).items(): items.append((k_, " ".join(h.get("pre") or []) + " " + " ".join(l[0] for l in h["lines"])))
badq = []
for k_, text in items:
    for part in [p_ for p_ in re.split(r"…", text) if words_of(p_)]:
        ws = words_of(part); ws = [w_ for i_, w_ in enumerate(ws) if i_ == 0 or w_ != ws[i_ - 1]]; q = " ".join(ws)
        a_ok = q in cut_words; b_ok = (q.replace(' ', '') in ytn) if yt else None     # spaces ignored vs YouTube: 'chatbots' = 'chat bots'
        if not a_ok or b_ok is False: badq.append((k_, "clip-transcript" if not a_ok else "youtube-captions", part.strip()))
rec("quotes_verbatim", not badq, f"{len(items)} quote graphics checked against the clip transcript" + (" and YouTube captions" if yt else " (no YouTube captions for this job)") + (f"; NOT FOUND: {badq}" if badq else ""))
# ---- 6. optional independent timing check
if deep:
    from faster_whisper import WhisperModel
    m = WhisperModel("medium.en", device="cpu", compute_type="int8", cpu_threads=8)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", final, "-ac", "1", "-ar", "16000", "_deep.wav"], check=True)
    segs_, _ = m.transcribe("_deep.wav", word_timestamps=True, language="en", vad_filter=True, beam_size=5, initial_prompt=glossary_prompt() or None)
    full = [dict(w=w_.word.strip(), s=w_.start, e=w_.end) for s_ in segs_ for w_ in s_.words]; os.remove("_deep.wav")
    tok = json.load(open("tokens.json")); Wn = [norm(x_["w"]) for x_ in full]; Pn = [x_["n"] for x_ in tok]
    sm = difflib.SequenceMatcher(None, Pn, Wn, autojunk=False); diffs = []
    for a_, b_, sz in sm.get_matching_blocks():
        for j in range(sz): diffs.append(abs(((tok[a_ + j]["s"] + tok[a_ + j]["e"]) / 2) - ((full[b_ + j]["s"] + full[b_ + j]["e"]) / 2)))
    diffs.sort(); med = diffs[len(diffs) // 2]; p90 = diffs[int(len(diffs) * .9)]
    rec("caption_timing_independent", med < 0.35 and len(diffs) > 0.7 * len(Pn), f"median {med:.2f}s, p90 {p90:.2f}s over {len(diffs)}/{len(Pn)} matched words")
res["status"] = "PASS" if not fails else "FAIL: " + ", ".join(fails)
res["format_name"] = "4:5" if FMT == "tall" else "16:9"
json.dump(res, open(f"{JOB}/clips/{N}.check{VSFX}.json", "w"), indent=1)
print("\nRESULT:", res["status"])
sys.exit(1 if fails else 0)
