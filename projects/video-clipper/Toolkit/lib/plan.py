"""Frame-exact timeline of one clip, from its spec (Jobs/<job>/clips/<NN>.json).
Imported by build_base / captions / overlays / render; run directly to print and store the plan."""
import json, os
from common import *
C = clip_spec()
X_DEF = 5                                     # default cross-dissolve length (frames)
CLEAN = is_clean(C)                           # clean look: no headline/cards/heroes/stats, and a short source card instead of the closing card
CARD = int(round((C.get("end_seconds", 1.5) if CLEAN else C.get("card_seconds", 5.5)) / FT))
segs = []; F = 0
for i, sg in enumerate(C["segments"]):
    k = int((sg["a"] / FT) + 0.5)
    n = int(((sg["b"] - sg["a"]) / FT))      # floor: never run past the requested out point
    x = 0 if i == 0 else sg.get("x", X_DEF)
    if i > 0: F = F - x
    d = dict(sg); d.update(k=k, n=n, x=x, src_in=k * FT, src_out=(k + n) * FT, F=F)
    segs.append(d); F += n
INTERVIEW_FRAMES = F
TOTAL = INTERVIEW_FRAMES + CARD
def src2frame(s):
    for sg in segs:
        if sg["src_in"] - 1e-6 <= s <= sg["src_out"] + 1e-6:
            return sg["F"] + (s - sg["src_in"]) / FT
    raise ValueError(s)
def out_dir(): return clip_work()
if __name__ == "__main__":
    json.dump(dict(N=N, FT=FT, CARD=CARD, segs=segs, INTERVIEW_FRAMES=INTERVIEW_FRAMES, TOTAL=TOTAL),
              open(out_dir() + "/plan.json", "w"), indent=1)
    for s in segs:
        print(s["name"], f"src {s['src_in']:.3f}-{s['src_out']:.3f}", f"final {s['F']*FT:.2f}-{(s['F']+s['n'])*FT:.2f}", "x", s["x"])
    print(f"clip {N}: interview {INTERVIEW_FRAMES*FT:.2f}s  total {TOTAL*FT:.2f}s  frames {TOTAL}")
