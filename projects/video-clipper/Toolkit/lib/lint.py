"""Fast pre-flight of one clip spec, BEFORE the slow steps (no whisper, runs in about a second).
Catches the mistakes that used to surface only after a full build (~10 min): bad cut points, quote graphics that are not
verbatim in YouTube's captions, missing pieces.  usage (via `clip lint`): lint.py   (needs JOB_DIR + CLIP_N)
Exit code 1 = at least one ERROR (the build refuses to start); warnings are printed but do not block."""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
import ytcaps
C = clip_spec(); CE = clip_spec_en(); job = load_job(); errs = []; warns = []
# ---- segments
segs = C.get("segments") or []
if not segs: errs.append("spec has no segments")
prev_b = None
hook = bool(segs and segs[0].get("hook"))      # cold open: segment 1 is the 4-8 s hook line, taken from anywhere in the source, shown first
for i, sg in enumerate(segs):
    a, b = sg.get("a"), sg.get("b")
    if a is None or b is None: errs.append(f"segment {i+1}: needs a and b (source seconds)"); continue
    if b <= a: errs.append(f"segment {i+1}: b ({b}) must be after a ({a})")
    if prev_b is not None and a < prev_b and not (hook and i == 1): warns.append(f"segment {i+1} starts before the previous one ends (out-of-order edit?)")
    prev_b = b
if hook:
    hl = segs[0].get("b", 0) - segs[0].get("a", 0)
    if not (2.0 <= hl <= 7.0): warns.append(f"hook segment is {hl:.1f}s; a cold open should be about 3-6s (one complete thought, first word inside the first second)")
    if len(segs) < 2: errs.append("a hook segment needs the rest of the clip after it")
    elif segs[1].get("x", 5) > 3: warns.append("segment 2 follows the hook: use a short dissolve (\"x\": 2-3) so the cold open reads as a hard cut")
elif C.get("cold_open") != "natural":      # "cold_open": "natural" = the passage itself opens on its strongest line, so no separate hook segment
    warns.append("no cold open: the first segment is not marked \"hook\": true. the strongest 3-6s line should come first, then the passage (see SPEC_REFERENCE.md 'Cold open')")
total = sum(max(0, sg.get("b", 0) - sg.get("a", 0)) for sg in segs)
clean = is_clean(C)
card = C.get("end_seconds", 1.5) if clean else C.get("card_seconds", 5.5)
if segs and not (30 <= total + card <= 46): warns.append(f"video is {total + card:.0f}s ({total:.0f}s of speech + {card:g}s end card); target is 30-45s (QA fails outside 25-55s)")
if not C.get("slug"): warns.append("spec has no 'slug'")
if not C.get("headline"): warns.append("spec has no 'headline' (it is only used on the thumbnail: the thumbnail will be the bare frame)")
if not (C.get("closing") or {}).get("src"): warns.append("no closing.src (\"Speaker x Interviewer\"): the end card will be empty")
if clean:
    pills = [e for e in C.get("schedule", []) if e.get("k") == "pill"]
    if not pills: warns.append("clean look: no pill in the schedule, so nothing on screen says who is speaking. Add the speaker pill during the hook (t_in about 0.3)")
    extra = sorted({e.get("k") for e in C.get("schedule", []) if e.get("k") != "pill"})
    if extra and C.get("style") != "full": warns.append(f"clean look ignores these schedule events: {extra} (only pills are drawn). For the old graphics set \"style\": \"full\" (16:9 only)")
# ---- 4:5 version: the crop must be told where the speaker is
if FMT == "tall":
    T_ = C.get("tall")
    if not T_: warns.append("no 'tall' block: the 4:5 crop is centred on the frame. Look at `clip preview NN --tall`; if the speaker is off-centre set \"tall\": {\"x\": 0.xx} (+ windows per shot)")
    else:
        if not (0 <= float(T_.get("x", 0.5)) <= 1): errs.append("tall.x must be between 0 and 1 (fraction of the frame width where the crop is centred)")
        for w_ in T_.get("windows", []):
            if len(w_) != 3 or w_[1] <= w_[0] or not (0 <= float(w_[2]) <= 1): errs.append(f"tall.windows entry {w_}: use [src_a, src_b, x] with src_b > src_a and x between 0 and 1")
if not C.get("thumb"): warns.append("no 'thumb' in the spec (no thumbnail will be made)")
# ---- quote graphics must be verbatim in YouTube's captions (the same rule QA enforces at the end)
vtt = job.get("captions")
if vtt and os.path.exists(f"{JOB}/{vtt}"):
    FILL = {"um", "uh", "uhm"}
    ws = [w for w in ytcaps.plain_stream(ytcaps.parse(f"{JOB}/{vtt}")) if w not in FILL]
    ytn = "".join(w for i, w in enumerate(ws) if i == 0 or w != ws[i - 1])
    words_of = lambda s: [norm(w) for w in re.split(r"[\s|*]+", s.replace("…", " ")) if norm(w)]
    items = [(k, c["text"]) for k, c in CE.get("cards", {}).items()]
    for k, h in CE.get("heroes", {}).items(): items.append((k, " ".join(h.get("pre") or []) + " " + " ".join(l[0] for l in h["lines"])))
    for k, text in items:
        for part in [p for p in re.split(r"…", text) if words_of(p)]:
            w = words_of(part); w = [x for i, x in enumerate(w) if i == 0 or x != w[i - 1]]
            if "".join(w) not in ytn:
                errs.append(f"quote '{k}' is not verbatim in the YouTube captions: \"{part.strip()}\"  (fix the wording, or split it with '…' into pieces that were each spoken as written)")
else:
    warns.append("no YouTube captions for this job: quote text can only be checked after whisper (at QA)")
# ---- Spanish variant (clip build ... --es): the "es" block must mirror the English graphics 1:1
if LANG == "es":
    E = CE.get("es")
    if not E: errs.append("no \"es\" block in the spec (headline, pills, cards, heroes, stats, closing, highlights, phrases_es)")
    else:
        if not CE.get("phrases"): errs.append("Spanish captions need reviewed English phrases (phrases must not be empty): they are what the Spanish lines are timed to")
        if len(E.get("phrases_es") or []) != len(CE.get("phrases") or []): errs.append(f"es.phrases_es has {len(E.get('phrases_es') or [])} entries, phrases has {len(CE.get('phrases') or [])}: they must match 1:1 (Spanish line i is shown while English phrase i is spoken)")
        for blk in ("cards", "heroes", "stats", "pills"):
            if set(CE.get(blk, {})) != set(E.get(blk, {})): errs.append(f"es.{blk} keys {sorted(E.get(blk, {}))} differ from the English {blk} keys {sorted(CE.get(blk, {}))}")
        for need in ("headline", "closing"):
            if CE.get(need) and not E.get(need): errs.append(f"es.{need} is missing (all on-screen text must be Spanish)")
        for i, ph in enumerate(E.get("phrases_es") or []):
            if len(ph.replace("|", " ")) > 70: warns.append(f"Spanish caption {i} is {len(ph)} chars (max about 68 for two lines): shorten or split it")
            if ph.count("|") > 1: errs.append(f"Spanish caption {i}: at most one | (two lines)")
    warns.append("Spanish quote cards are translations of verbatim English quotes: the author should read every Spanish line (Review.md lists them next to the English)")
for w in warns: print("WARN ", w)
for e in errs: print("ERROR", e)
print(f"lint clip {N}: {'FAIL' if errs else 'ok'} ({len(errs)} errors, {len(warns)} warnings)")
sys.exit(1 if errs else 0)
