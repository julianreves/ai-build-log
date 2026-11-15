"""Chunk-wise whisper on the final cut's audio: each speech chunk (delimited by real pauses) is transcribed
separately, so word times cannot drift across pauses.  Run with the venv39 interpreter (-I).
Output: words_final.json in the clip work dir."""
import json, sys, wave, math, subprocess, os, hashlib
import numpy as np
from faster_whisper import WhisperModel
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import glossary_prompt
d = sys.argv[1]
# Measured on this M1 (8 GB): beam 1 + 4 threads is ~2.9x faster than beam 5 + 8 threads (the 4 efficiency cores only slow it down) and gives
# the same real words (the only differences were hallucinations in silence, which captions.py filters). Packing several chunks into one
# 30 s window was tried: no faster, and some word times moved by up to 3 s, so it is NOT used.
MODEL, BEAM, THREADS = "medium.en", int(os.environ.get("WHISPER_BEAM", 1)), int(os.environ.get("WHISPER_THREADS", 4))
PROMPT = glossary_prompt() or None
# Chunk results are cached by a hash of the chunk's exact audio + settings (Toolkit/cache/whisper/). Rebuilding a clip whose
# audio did not change (a graphics/caption/post tweak, a re-run after a failed step) therefore skips whisper entirely.
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache", "whisper"); os.makedirs(CACHE, exist_ok=True)
_m = None
def model():
    global _m
    if _m is None: _m = WhisperModel(MODEL, device="cpu", compute_type="int8", cpu_threads=THREADS)   # loaded only on a cache miss
    return _m
def key_of(path):
    h = hashlib.sha1(open(path, "rb").read()); h.update(f"|{MODEL}|{BEAM}|{PROMPT}".encode()); return h.hexdigest()
def env_of(path):
    w = wave.open(path); sr = w.getframerate(); n = w.getnframes()
    x = np.frombuffer(w.readframes(n), dtype=np.int16).reshape(-1, 2).astype(np.float64).mean(axis=1)
    hop = int(sr * 0.01); k = len(x) // hop
    rms = np.sqrt((x[:k * hop].reshape(k, hop) ** 2).mean(axis=1)) / 32768
    return (20 * np.log10(rms + 1e-9)).tolist()
def runs(env, th=-44, gap=0.30, minlen=0.08):
    rs = []; cur = None
    for i, dd in enumerate(env):
        t = i * 0.01
        if dd > th:
            if cur and t - cur[1] <= gap + 0.01: cur[1] = t + 0.01
            else:
                if cur: rs.append(cur)
                cur = [t, t + 0.01]
    if cur: rs.append(cur)
    return [r for r in rs if r[1] - r[0] >= minlen]
env = env_of(f"{d}/base_audio_raw.wav")
rs = runs(env)
fine = runs(env, gap=0.10)
chunks = []
for a, b in rs:          # split long chunks at their longest internal pauses
    if b - a <= 9.0: chunks.append([a, b]); continue
    inner = [r for r in fine if r[0] >= a - 0.01 and r[1] <= b + 0.01]
    cur = [inner[0][0], inner[0][1]]
    for r in inner[1:]:
        if r[1] - cur[0] > 7.0 and r[0] - cur[1] >= 0.10: chunks.append(cur); cur = [r[0], r[1]]
        else: cur[1] = r[1]
    chunks.append(cur)
out = []; hits = 0; tmp = f"{d}/_chunk.wav"
def transcribe_file(path):
    """-> [[word, start, end, prob], ...] for one wav, from the cache or whisper"""
    global hits
    cf = f"{CACHE}/{key_of(path)}.json"
    if os.path.exists(cf): hits += 1; return json.load(open(cf))
    segs, _ = model().transcribe(path, word_timestamps=True, language="en", vad_filter=False, condition_on_previous_text=False,
                                 beam_size=BEAM, initial_prompt=PROMPT)
    ws = [[w_.word.strip(), w_.start, w_.end, w_.probability] for s_ in segs for w_ in s_.words]
    json.dump(ws, open(cf + ".tmp", "w")); os.replace(cf + ".tmp", cf); return ws
def chunk_audio(a0, b0):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{a0:.3f}", "-t", f"{b0-a0:.3f}", "-i", f"{d}/base_audio_raw.wav", "-ac", "1", "-ar", "16000", tmp], check=True)
    w = wave.open(tmp); x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16); w.close(); return x
def emit(ws, a0, a, b):
    for w, st, en, pr in ws:
        out.append(dict(w=w, s=round(st + a0, 3), e=round(en + a0, 3), p=round(pr, 3), chunk=[round(a, 2), round(b, 2)]))
for a, b in chunks:             # one whisper call per chunk (each is padded to a 30 s window internally, so this dominates the build time)
    a0 = max(0, a - 0.20); b0 = b + 0.20; chunk_audio(a0, b0); emit(transcribe_file(tmp), a0, a, b)
ncalls = len(chunks)
os.remove(tmp)
json.dump(out, open(f"{d}/words_final.json", "w"))
print(len(chunks), "chunks;", len(out), "words", f"(whisper cache: {hits}/{ncalls} chunks reused)", flush=True)
