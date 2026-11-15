"""Align caption phrases (spec "phrases", or auto-built from the chunk-wise whisper words) to the audio energy of the FINAL cut.
Outputs in the clip work dir: captions.json, subs.srt, tokens.json (+ phrases_auto.json when phrases were auto-built)."""
import json, re, wave, struct, math, difflib, os
from plan import *
os.chdir(out_dir())
W0 = json.load(open("words_final.json"))
W = []
for x in W0:
    if x["w"].startswith("-") and W: W[-1]["w"] += x["w"]; W[-1]["e"] = x["e"]
    elif re.sub(r"[^a-z0-9]", "", x["w"].lower()) == "": continue
    else: W.append(dict(x))
def auto_phrases(words):
    """simple phrase builder: split on sentence ends, commas, pauses and length; applies spec glossary fixes"""
    # whisper hallucinates tiny low-confidence words ("Thank you.", "it.") inside very short chunks: drop them
    keep = []; skip_you = False
    for x in words:
        dur = x["e"] - x["s"]; p = x.get("p", 1.0)
        if p < 0.30 and (dur < 0.10 or norm(x["w"]) in ("thank", "you", "it", "thats")):
            skip_you = norm(x["w"]) == "thank"; continue
        if skip_you and norm(x["w"]) == "you": skip_you = False; continue
        skip_you = False; keep.append(x)
    words = keep
    out = []; cur = []; L = 0
    for i, x in enumerate(words):
        cur.append(x["w"]); L += len(x["w"]) + 1
        nxt = words[i + 1]["s"] - x["e"] if i + 1 < len(words) else 9
        end = x["w"][-1:] in ".?!"
        if (end and L >= 14) or (x["w"][-1:] in ",;:" and L >= 30) or (nxt > 0.45 and L >= 18) or L >= 46:
            out.append(" ".join(cur)); cur = []; L = 0
    if cur: out.append(" ".join(cur))
    gl = C.get("glossary", {})
    res = []
    for p in out:
        for a, b in gl.items(): p = re.sub(re.escape(a), b, p, flags=re.I)
        res.append(p)
    return res
PHR = C.get("phrases")
if not PHR:
    PHR = auto_phrases(W)
    json.dump(PHR, open("phrases_auto.json", "w"), indent=1)
    print("NOTE: spec has no 'phrases' -> auto-built captions (review phrases_auto.json, then paste into the spec)")
def norm(t): return re.sub(r"[^a-z0-9]", "", t.lower())
# ---- energy envelope of the final audio
w = wave.open("base_audio_raw.wav"); sr = w.getframerate(); n = w.getnframes()
raw = struct.unpack("<%dh" % (n * 2), w.readframes(n))
hop = int(sr * 0.01); ENV = []
for i in range(0, n - hop, hop):
    s = 0.0
    for j in range(i, i + hop, 2):
        v = (raw[2*j] + raw[2*j+1]) / 2; s += v * v
    ENV.append(20 * math.log10(math.sqrt(s / (hop / 2)) / 32768 + 1e-9))
def speech_runs(th=-44, gap=0.12, minlen=0.06):
    runs = []; cur = None
    for i, d in enumerate(ENV):
        t = i * 0.01
        if d > th:
            if cur and t - cur[1] <= gap + 0.01: cur[1] = t + 0.01
            else:
                if cur: runs.append(cur)
                cur = [t, t + 0.01]
    if cur: runs.append(cur)
    return [r for r in runs if r[1] - r[0] >= minlen]
RUNS = speech_runs()
# ---- token alignment
toks = []        # (phrase_index, token)
for pi, ph in enumerate(PHR):
    for t in ph.replace("|", " ").split(): toks.append((pi, t))
Pn = [norm(t) for _, t in toks]; Wn = [norm(x["w"]) for x in W]
sm = difflib.SequenceMatcher(None, Pn, Wn, autojunk=False)
tm = [None] * len(Pn)
for a, b, sz in sm.get_matching_blocks():
    for k in range(sz): tm[a + k] = (W[b + k]["s"], W[b + k]["e"])
miss = [i for i, x in enumerate(tm) if x is None]
# interpolate unmatched tokens between matched neighbours
i = 0
while i < len(tm):
    if tm[i] is None:
        j = i
        while j < len(tm) and tm[j] is None: j += 1
        left = tm[i-1][1] if i > 0 else (tm[j][0] - 0.3 * (j - i) if j < len(tm) else 0)
        right = tm[j][0] if j < len(tm) else left + 0.3 * (j - i)
        for k in range(i, j):
            f0 = (k - i) / (j - i); f1 = (k - i + 1) / (j - i)
            tm[k] = (left + (right - left) * f0, left + (right - left) * f1)
        i = j
    else: i += 1
print("tokens", len(Pn), "unmatched(interpolated):", [toks[i][1] for i in miss])
# ---- energy-constrained alignment: assign the (known, ordered) tokens to the real speech runs with a DP,
#      using syllable weights (speech rate) + whisper times as weak evidence; then distribute inside each run.
def weight(t):
    if re.search(r"\d", t):
        return 1.6 + 2.0 * t.count("%") + (2.5 if "GPT" in t else 0)
    letters = re.sub(r"[^a-z]", "", t.lower()); syl = max(1, len(re.findall(r"[aeiouy]+", letters)))
    return syl + 0.12 * len(letters)
RR = [r for r in speech_runs(th=-44, gap=0.17, minlen=0.12)]
# force a run boundary at every edit join (speech may continue across it without any pause)
for sg in segs[1:]:
    J = (sg["F"] + sg["x"] / 2) * FT; new = []
    for a, b in RR:
        if a < J - 0.05 and b > J + 0.05: new += [[a, J], [J, b]]
        else: new.append([a, b])
    RR = new
TOTW = [weight(t) for _, t in toks]
CUM = [0.0]
for x in TOTW: CUM.append(CUM[-1] + x)
D = sum(b - a for a, b in RR); rate = CUM[-1] / D
Tn = len(toks); K = len(RR)
mid = [None if (tm[i] is None or i in miss) else (tm[i][0] + tm[i][1]) / 2 for i in range(Tn)]
PUNCT = set(",.;:?!")
def run_dist(m, a, b): return 0.0 if a <= m <= b else (a - m if m < a else m - b)
INF = 1e18
f = [[INF] * (Tn + 1) for _ in range(K + 1)]; bp = [[0] * (Tn + 1) for _ in range(K + 1)]
f[0][0] = 0.0
for k in range(1, K + 1):
    a, b = RR[k - 1]; dur = b - a
    wd = [0.0]
    for i in range(Tn): wd.append(wd[-1] + (0.0 if mid[i] is None else 8.0 * min(run_dist(mid[i], a, b), 6.0) + 4.0 * min(run_dist(mid[i], a, b), 6.0) ** 2))
    for i in range(0, Tn + 1):
        best = f[k - 1][i]; bj = i                       # empty run
        for j in range(max(0, i - 130), i):
            if f[k - 1][j] >= INF: continue
            syl = CUM[i] - CUM[j]
            c = ((syl - rate * dur) ** 2) / (rate * dur + 1.0) * 0.5 + (wd[i] - wd[j])
            if i < Tn and toks[i - 1][1][-1] not in PUNCT and i - j > 0: c += 0.5      # prefer run ends after punctuation
            tot = f[k - 1][j] + c + 0.05
            if tot < best: best = tot; bj = j
        f[k][i] = best; bp[k][i] = bj
# backtrack
groups = [None] * K; i = Tn
for k in range(K, 0, -1):
    j = bp[k][i]; groups[k - 1] = (j, i); i = j
tt = [None] * Tn
for (a, b), (j, i) in zip(RR, groups):
    if i <= j: continue
    wsum = sum(TOTW[j:i]); cum = 0.0
    for t_ in range(j, i):
        s_ = a + (b - a) * cum / wsum; cum += TOTW[t_]; e_ = a + (b - a) * cum / wsum
        tt[t_] = (s_, e_)
miss_set = set(miss)
dev = [abs((tt[i][0] + tt[i][1]) / 2 - mid[i]) for i in range(Tn) if tt[i] and mid[i] is not None]
print("aligned %d tokens in %d runs; whisper-vs-aligned deviation: median %.2fs  p95 %.2fs  max %.2fs" % (Tn, K, sorted(dev)[len(dev)//2], sorted(dev)[int(len(dev)*.95)], max(dev)))
tm = tt
# ---- per phrase times
phr = []; idx = 0
for pi, ph in enumerate(PHR):
    k = len(ph.replace("|", " ").split())
    s = tm[idx][0]; e = tm[idx + k - 1][1]
    phr.append(dict(i=pi, s=s, e=e, k0=idx, k1=idx + k, s2=s, e2=e, ds=0.0, de=0.0)); idx += k
tokens = []
for p in phr:
    for k in range(p["k0"], p["k1"]):
        tokens.append(dict(t=toks[k][1], n=norm(toks[k][1]), s=tm[k][0], e=tm[k][1], ph=p["i"]))
json.dump(tokens, open("tokens.json", "w"))
# ---- captions
def split_lines(text, maxline=34):
    if len(text) <= maxline: return [text]
    words = text.split(" "); best = None
    for k in range(1, len(words)):
        l1 = " ".join(words[:k]); l2 = " ".join(words[k:])
        sc = abs(len(l1) - len(l2))
        if best is None or sc < best[0]: best = (sc, [l1, l2])
    return best[1]
# Spanish variant: the English phrases above are still what is ALIGNED to the audio; the Spanish phrase i is simply shown during
# the time span of English phrase i (spec es.phrases_es must have exactly as many entries as phrases).
if LANG == "es":
    PES = C.get("phrases_es") or []
    if len(PES) != len(PHR): raise SystemExit(f"Spanish captions: phrases_es has {len(PES)} entries but phrases has {len(PHR)} (they must match 1:1)")
caps = []
for p in phr:
    ph = (PES if LANG == "es" else PHR)[p["i"]]
    parts = ph.split("|")
    ta, tb = tm[p["k0"]][0], tm[p["k1"] - 1][1]
    chunks = [(ph.replace("|", " "), parts if len(parts) > 1 else split_lines(ph), ta, tb)]
    dur = tb - ta; nch = len(ph.replace("|", " "))
    if len(parts) == 2 and (dur > 3.9 or nch > 68):
        if LANG == "es":
            # Spanish word order differs, so split where the length says, then snap to the nearest real gap between spoken words
            # (a caption must never start in silence: QA 'captions_on_speech')
            if p["k1"] - p["k0"] >= 2:
                tprop = ta + dur * len(parts[0]) / max(1, len(parts[0]) + len(parts[1])); best = None
                for j in range(p["k0"], p["k1"] - 1):
                    gap = tm[j + 1][0] - tm[j][1]; sc = abs(tm[j + 1][0] - tprop) - 3.0 * max(0.0, gap)
                    if best is None or sc < best[0]: best = (sc, j)
                j = best[1]; chunks = [(parts[0], [parts[0]], ta, tm[j][1]), (parts[1], [parts[1]], tm[j + 1][0], tb)]
        else:
            tmid = tm[p["k0"] + len(parts[0].split()) - 1][1]; tmid2 = tm[p["k0"] + len(parts[0].split())][0]
            chunks = [(parts[0], [parts[0]], ta, tmid), (parts[1], [parts[1]], tmid2, tb)]
    for text, lines, t0_, t1_ in chunks:
        s_ = max(0.0, t0_ - 0.04); e_ = t1_ + 0.22
        caps.append(dict(start=s_, end=e_, text=text, lines=lines))
for i in range(len(caps) - 1):
    if caps[i]["end"] > caps[i+1]["start"] - 0.04:
        caps[i]["end"] = max(caps[i]["start"] + 0.5, caps[i+1]["start"] - 0.04)
caps[-1]["end"] = min(caps[-1]["end"], INTERVIEW_FRAMES * FT - 0.1)
json.dump(caps, open("captions.json", "w"), indent=1)
def ts(t):
    ms = int(round(t * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
with open("subs.srt", "w") as f:
    for i, c in enumerate(caps, 1):
        f.write(f"{i}\n{ts(c['start'])} --> {ts(c['end'])}\n" + "\n".join(c["lines"]) + "\n\n")
for i, c in enumerate(caps, 1):
    print(f"{i:3d} {c['start']:6.2f}-{c['end']:6.2f} | " + " / ".join(c["lines"]))
if os.environ.get("DBG"):
    print("RUNS/GROUPS")
    for (a, b), (j, i) in zip(RR, groups):
        if a > float(os.environ["DBG"]): break
        print(f"  run {a:6.2f}-{b:6.2f} ({b-a:.2f}s) -> tokens {j}:{i} " + " ".join(toks[x][1] for x in range(j, i)))
