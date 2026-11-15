"""Shared paths + job/clip context for every Toolkit module.
The `clip` CLI sets JOB_DIR (and CLIP_N for per-clip steps) before it runs a module."""
import os, json, re, subprocess

TOOLKIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(TOOLKIT)
LIB = f"{TOOLKIT}/lib"
PY = f"{TOOLKIT}/env/venv/bin/python"          # Pillow, numpy-free image work
V39 = f"{TOOLKIT}/env/venv39/bin/python"       # faster-whisper + numpy (run with -I)
YTDLP = f"{TOOLKIT}/bin/yt-dlp"
JOBS = f"{ROOT}/Jobs"

JOB = os.environ.get("JOB_DIR", "")
N = os.environ.get("CLIP_N", "")               # clip number, e.g. "01"
LANG = "es" if os.environ.get("CLIP_LANG") == "es" else "en"   # "es" = Spanish-subtitled variant (clip build ... --es); the audio is never translated
FMT = "tall" if os.environ.get("CLIP_FMT") == "tall" else "wide"   # "tall" = the 4:5 version (1080x1350, cropped on the speaker); "wide" = 16:9 (1920x1080)
OUT_W, OUT_H = (1080, 1350) if FMT == "tall" else (1920, 1080)
TALL_SRC_W = 2400                                # the 16:9 frame scaled to 1350 px high is 2400 px wide; the 4:5 crop is a 1080-px window of it
VSFX = ("_4x5" if FMT == "tall" else "") + ("_es" if LANG == "es" else "")     # suffix of work folders and check files for this variant

def is_clean(spec):
    """clean look (default since 2026-11-13): captions + pills + a short source card, nothing else. "style": "full" keeps the old
    headline / quote cards / heroes / stats / closing card, and exists only in 16:9 (the 4:5 version is always clean)."""
    return FMT == "tall" or spec.get("style", "clean") != "full"

def load_job():
    return json.load(open(f"{JOB}/job.json"))

def save_job(j):
    json.dump(j, open(f"{JOB}/job.json", "w"), indent=2)

_JOB = load_job() if JOB and os.path.exists(f"{JOB}/job.json") else {}
SRC = f"{JOB}/{_JOB['source']}" if _JOB.get("source") else ""
WORK = f"{JOB}/work"
FPS = _JOB.get("fps", "24000/1001")            # output/ source frame rate as an ffmpeg rational
_n, _d = (FPS.split("/") + ["1"])[:2]
FT = int(_d) / int(_n)                          # frame time in seconds

def clip_spec_path(n=None):
    n = n or N
    return f"{JOB}/clips/{n}.json"

def clip_spec_en(n=None):
    """the spec exactly as written (English): quotes, phrases and anchors are always checked against the English speech"""
    return json.load(open(clip_spec_path(n)))

def clip_spec(n=None):
    """the spec for the language being built. In Spanish mode the spec's "es" block replaces headline / pills / cards / heroes /
    stats / closing / highlights (all on-screen text) and adds "phrases_es" (captions); everything else (cuts, schedule, anchors) is shared."""
    s = clip_spec_en(n)
    if LANG == "es":
        for k, v in (s.get("es") or {}).items(): s[k] = v
    return s

def clip_work(n=None):
    d = f"{WORK}/clips/{n or N}" + VSFX
    os.makedirs(d, exist_ok=True)
    return d

def ts(sec, frac=1):
    sec = max(0.0, sec); m, s = divmod(sec, 60); h, m = divmod(int(m), 60)
    w = 3 + frac if frac else 2
    return (f"{h}:{m:02d}:{s:0{w}.{frac}f}" if h else f"{m}:{s:0{w}.{frac}f}")

def norm(t):
    return re.sub(r"[^a-z0-9]", "", t.lower())

def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)

def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate,codec_name,duration:format=duration", "-of", "json", path],
                       capture_output=True, text=True)
    return json.loads(r.stdout)

def glossary_prompt():
    """short vocabulary prompt for whisper (AI names it often mishears)"""
    p = f"{TOOLKIT}/glossary.json"
    terms = json.load(open(p)).get("terms", []) if os.path.exists(p) else []
    return ", ".join(terms)
