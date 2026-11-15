"""Motion-graphics + subtitle overlay -> RGBA PNG sequence (1920x1080, or 1080x1350 for the 4:5 version).
Clean look (default): captions + pills + a short source card. "style": "full" (16:9 only) adds the headline, quote cards, heroes,
stats and the closing card.
Series look (palette, Helvetica Neue, teal accent, rule + stacked headline, kicker pills, caption style, closing card).
Data-driven: events come from the clip spec via events.py."""
import json, os, sys, re, math
from multiprocessing import Pool
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
from plan import *
import events as EVM

W, H = OUT_W, OUT_H
TALL = FMT == "tall"
NEED_HEAD = False          # thumb.py sets this: the headline is drawn on the thumbnail even in the clean look
NEAR_BLACK = (17, 19, 24); WHITE = (255, 255, 255); GRAY = (168, 173, 183); TEAL = (0, 217, 180)
FONT = "/System/Library/Fonts/HelveticaNeue.ttc"
def F(idx, size): return ImageFont.truetype(FONT, size, index=idx)
REG, BOLD, MED, LIGHT = 0, 1, 10, 7
OUT = sys.argv[1] if len(sys.argv) > 1 else "ov"
MARGIN = 60 if TALL else 100
PS = 1.2 if TALL else 1.0                                   # pill scale (the 4:5 frame is watched on a phone)
CAP_F = 64 if CLEAN else 52                                 # caption size: clean look is larger (64 px is ~23 px on a phone in 4:5, ~13 px in 16:9)
CAP_LH = 82 if CLEAN else 66                                # caption line height
CAP_YB = H - 150 if TALL else 1000                          # bottom of the caption block
CAP_MAXW = W - 2 * 70                                       # 4:5 only: captions are re-wrapped to this width (up to 3 lines)

# ---------------------------------------------------------------- helpers (shared with the earlier pipeline)
def ease_out(x): x = max(0.0, min(1.0, x)); return 1 - (1 - x) ** 3
def ease_io(x):  x = max(0.0, min(1.0, x)); return x * x * (3 - 2 * x)
def ease_back(x):
    x = max(0.0, min(1.0, x)); c1 = 1.9; c3 = c1 + 1
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2
def text_w(txt, font, tracking=0):
    if tracking == 0: return font.getlength(txt)
    return sum(font.getlength(c) for c in txt) + tracking * (len(txt) - 1)
def draw_text(d, xy, txt, font, fill, tracking=0):
    x, y = xy
    if tracking == 0: d.text((x, y), txt, font=font, fill=fill); return
    for c in txt:
        d.text((x, y), c, font=font, fill=fill); x += font.getlength(c) + tracking
def fit_size(txt, idx, max_w, max_size, tracking=0):
    s = max_size
    while s > 20 and text_w(txt, F(idx, s), tracking) > max_w: s -= 2
    return s
def make_sprite(spans, idx, size, tracking=0, shadow=True, pad=40, stroke=0):
    font = F(idx, size)
    w = int(sum(text_w(t, font, tracking) + (tracking if i < len(spans) - 1 else 0) for i, (t, c) in enumerate(spans))) + 2 * pad
    h = int(size * 1.5) + 2 * pad
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", (w, h), (0, 0, 0, 0)); sd = ImageDraw.Draw(sh); x = pad
        for t, c in spans:
            draw_text(sd, (x, pad + 4), t, font, (0, 0, 0, 210), tracking); x += text_w(t, font, tracking) + tracking
        sh = sh.filter(ImageFilter.GaussianBlur(max(6, size // 9)))
        img = Image.alpha_composite(img, sh)
    d = ImageDraw.Draw(img); x = pad
    for t, c in spans:
        if stroke:
            for dx in range(-stroke, stroke + 1):
                for dy in range(-stroke, stroke + 1):
                    if dx * dx + dy * dy <= stroke * stroke:
                        draw_text(d, (x + dx, pad + dy), t, font, (10, 11, 14, 235), tracking)
        draw_text(d, (x, pad), t, font, c + (255,), tracking); x += text_w(t, font, tracking) + tracking
    return img, pad
def scaled_alpha(img, a):
    if a >= 0.999: return img
    r, g, b, al = img.split(); al = al.point(lambda v: int(v * a))
    return Image.merge("RGBA", (r, g, b, al))
def paste(canvas, sprite, x, y, a):
    if a <= 0.003: return
    canvas.alpha_composite(scaled_alpha(sprite, a), (int(round(x)), int(round(y))))
def hgrad(w, h, a0, a1, color=NEAR_BLACK, power=1.6, vfade=False):
    img = Image.new("RGBA", (w, h)); col = Image.new("L", (w, h)); px = []
    for y in range(h):
        vy = math.sin(math.pi * y / (h - 1)) ** 0.8 if vfade else 1.0
        for x in range(w):
            px.append(int(255 * (a0 + (a1 - a0) * (x / (w - 1)) ** power) * vy))
    col.putdata(px)
    base = Image.new("RGBA", (w, h), color + (255,)); base.putalpha(col)
    return base
def parse_spans(s, base=WHITE, hi=TEAL):
    """'plain *teal* plain' -> [(text,color)]"""
    out = []; on = False
    for part in s.split("*"):
        if part: out.append((part, hi if on else base))
        on = not on
    return out
def spans_text(sp): return "".join(t for t, c in sp)

# ---------------------------------------------------------------- timeline helpers
def T(src_t): return src2frame(src_t) * FT
INT_T = INTERVIEW_FRAMES * FT; TOTAL_T = TOTAL * FT
def window(t, t_in, t_out, fi=0.45, fo=0.35):
    a_in = ease_out((t - t_in) / fi); a_out = 1 - ease_io((t - (t_out - fo)) / fo)
    if t < t_in or t > t_out: return 0.0, 0.0
    return a_in * a_out, a_in
def col_x(side, colw):  # left edge of a text column
    return MARGIN if side == "L" else W - MARGIN - colw

# ---------------------------------------------------------------- sprites (built once per process)
S = {}
def build_sprites():
    HC = EVM.HEAD if (EVM.HEAD and (not CLEAN or NEED_HEAD)) else None
    if HC: build_head_sprites(HC)
    build_pill_sprites()
    if not CLEAN:
        S["e_rule"] = Image.new("RGBA", (72, 6), TEAL + (255,))
        S["e_scrimL"] = hgrad(1000, 700, 0.66, 0.0, vfade=True); S["e_scrimR"] = ImageOps.mirror(S["e_scrimL"])
        S["e_scrimL2"] = hgrad(1000, 900, 0.78, 0.0, vfade=True); S["e_scrimR2"] = ImageOps.mirror(S["e_scrimL2"])
        S["cards"] = {key: build_card(c) for key, c in EVM.CARDS.items()}
        S["heroes"] = {key: build_hero(c) for key, c in EVM.HEROES.items()}
        S["stats"] = {key: build_stat(c) for key, c in EVM.STATS.items()}
    build_closing_sprites()
    build_caption_sprites()

def build_head_sprites(HC):
    side = HC.get("side", "L"); maxw = min(HC.get("maxw", 700), W - 2 * MARGIN - 60)
    S["hl"] = []
    for ln in HC["lines"]:
        txt, sty = ln[0], ln[1]; mx = ln[2] if len(ln) > 2 else None
        if sty == "t":
            sz = fit_size(txt, BOLD, maxw, mx or 54, tracking=14); sp = make_sprite([(txt, WHITE)], BOLD, sz, tracking=14); f = 1.1
        elif sty == "W":
            sz = fit_size(txt, BOLD, maxw, mx or 120); sp = make_sprite([(txt, WHITE)], BOLD, sz); f = 1.15
        elif sty == "w":
            sz = fit_size(txt, BOLD, maxw, mx or 62); sp = make_sprite([(txt, WHITE)], BOLD, sz); f = 1.1
        else:  # "T"
            sz = fit_size(txt, BOLD, maxw, mx or 150); sp = make_sprite([(txt, TEAL)], BOLD, sz); f = 1.15
        S["hl"].append((sp, sz, f))
    if HC.get("sub_style") == "white":
        S["hsub"] = make_sprite([(HC["sub"], WHITE)], BOLD, fit_size(HC["sub"], BOLD, maxw + 60, 44, tracking=4), tracking=4)
    else:
        S["hsub"] = make_sprite([(HC["sub"], GRAY)], MED, fit_size(HC["sub"], MED, maxw + 60, 38))
    S["hw"] = max(it[0][0].width - 80 for it in S["hl"])
    S["scrimL"] = hgrad(min(W, 1000), H, 0.80, 0.0); S["scrimR"] = ImageOps.mirror(S["scrimL"])
    S["rule"] = Image.new("RGBA", (96, 7), TEAL + (255,))

def build_pill_sprites():
    def kicker(txt):
        fs = int(28 * PS); f = F(BOLD, fs); tw = text_w(txt, f, 5); pad_x, pad_y = 30, 20
        w = int(tw + pad_x * 2 + 30); h = fs + pad_y * 2 + 6
        pill = Image.new("RGBA", (w + 80, h + 80), (0, 0, 0, 0))
        m = Image.new("RGBA", pill.size, (0, 0, 0, 0)); md = ImageDraw.Draw(m)
        md.rounded_rectangle((40, 40, 40 + w, 40 + h), radius=h // 2, fill=NEAR_BLACK + (205,))
        sh = m.filter(ImageFilter.GaussianBlur(10)); pill = Image.alpha_composite(pill, sh); pill = Image.alpha_composite(pill, m)
        d = ImageDraw.Draw(pill)
        d.ellipse((40 + pad_x, 40 + h // 2 - 7, 40 + pad_x + 14, 40 + h // 2 + 7), fill=TEAL + (255,))
        draw_text(d, (40 + pad_x + 32, 40 + pad_y - 1), txt, f, WHITE + (255,), 5)
        return pill
    S["pills"] = {}
    for key, (txt, sub) in EVM.PILLS.items():
        S["pills"][key] = (kicker(txt), make_sprite([(sub, (214, 218, 226))], MED, int(30 * PS), stroke=2) if sub else None)

def build_closing_sprites():
    CC = EVM.CARD
    if CLEAN:      # short source card: one line, nothing else
        src = CC.get("src", "")
        S["c_src"] = make_sprite([(src, (190, 195, 205))], MED, fit_size(src, MED, W - 2 * MARGIN - 40, 40, tracking=3), tracking=3, shadow=False) if src else None
        return
    cap_spans = [(t, WHITE if c == "W" else TEAL) for t, c in CC["main"]]
    s_cap = fit_size("".join(t for t, c in CC["main"]), BOLD, 1560, 92)
    S["c_main"] = make_sprite(cap_spans, BOLD, s_cap, shadow=False)
    S["c_sub"] = make_sprite([(CC["sub"], GRAY)], REG, 46, shadow=False)
    S["c_src"] = make_sprite([(CC["src"], (140, 146, 158))], MED, 30, tracking=3, shadow=False)
    S["c_rule"] = Image.new("RGBA", (140, 6), TEAL + (255,))

def rewrap(words, font, maxw):
    """4:5 captions: wrap by pixel width, then narrow the column until just before a line would be added (balanced lines)"""
    def wrap(mw):
        lines = [[]]
        for w in words:
            if lines[-1] and font.getlength(" ".join(lines[-1] + [w])) > mw: lines.append([w])
            else: lines[-1].append(w)
        return lines
    best = wrap(maxw); mw = maxw - 30
    while mw > maxw * 0.5:
        cand = wrap(mw)
        if len(cand) > len(best): break
        best = cand; mw -= 30
    return [" ".join(l) for l in best]

def build_caption_sprites():
    caps = json.load(open("captions.json")); hl = EVM.HL
    S["caps"] = []
    for c in caps:
        if TALL: c = dict(c, lines=rewrap(" ".join(c["lines"]).split(), F(MED, CAP_F), CAP_MAXW))
        full = " ".join(c["lines"]); low = full.lower(); mark = [False] * len(full)
        for h in hl:
            h2 = h.replace("|", " ").lower(); i = low.find(h2)
            while i >= 0:
                for k in range(i, i + len(h2)): mark[k] = True
                i = low.find(h2, i + 1)
        pos = 0; lines = []
        for ln in c["lines"]:
            words = ln.split(" "); spans = []
            for wi, wd in enumerate(words):
                col = TEAL if all(mark[pos + k] for k in range(len(wd))) else WHITE
                txt = wd + (" " if wi < len(words) - 1 else "")
                if spans and spans[-1][1] == col: spans[-1] = (spans[-1][0] + txt, col)
                else: spans.append((txt, col))
                pos += len(wd) + 1
            lines.append(spans)
        S["caps"].append(dict(start=c["start"], end=c["end"], sprites=[make_sprite(sp, MED, CAP_F, shadow=True, stroke=4 if CLEAN else 3) for sp in lines]))

def wrap_text(text, size, maxw):
    """text with *teal* marks and '|' forced breaks -> (lines of spans, first-word index of every line)"""
    font = F(BOLD, size); words = []; on = False
    for chunk in re.split(r"(\*)", text):
        if chunk == "*": on = not on; continue
        for part in re.split(r"(\|)", chunk):
            if part == "|": words.append(("|", on)); continue
            for w in part.split(): words.append((w, on))
    lines = [[]]
    for w, c in words:
        if w == "|": lines.append([]); continue
        trial = lines[-1] + [(w, c)]
        if lines[-1] and text_w(" ".join(x for x, _ in trial), font) > maxw: lines.append([(w, c)])
        else: lines[-1] = trial
    out = []; firsts = []; k = 0
    for ln in lines:
        spans = []
        for i, (w, c) in enumerate(ln):
            t = w + (" " if i < len(ln) - 1 else "")
            col = TEAL if c else WHITE
            if spans and spans[-1][1] == col: spans[-1] = (spans[-1][0] + t, col)
            else: spans.append((t, col))
        out.append(spans); firsts.append(k); k += len(ln)
    return out, firsts

def build_card(c):
    """verbatim quote card.  c: text (*teal* marks, | forced breaks), attrib, tag, maxw, size, maxlines"""
    maxw = c.get("maxw", 600); size_max = c.get("size", 64); maxl = c.get("maxlines", 6)
    for sz in range(size_max, 33, -2):
        lines, firsts = wrap_text(c["text"], sz, maxw - 2 * 0)
        lines[0] = [("\u201c", TEAL)] + lines[0]; lines[-1] = lines[-1] + [("\u201d", TEAL)]
        wd = [text_w(spans_text(sp), F(BOLD, sz)) for sp in lines]
        if len(lines) <= maxl and all(x <= maxw + 40 for x in wd) and all(x >= 0.42 * maxw for x in wd[:-1]): break
    sprites = [make_sprite(sp, BOLD, sz) for sp in lines]
    attrib = make_sprite([("\u2014 " + c["attrib"], GRAY)], MED, 28, tracking=4) if c.get("attrib") else None
    tag = make_sprite([(c["tag"], TEAL)], BOLD, 26, tracking=6) if c.get("tag") else None
    colw = max(s_[0].width - 80 for s_ in sprites)
    return dict(sprites=sprites, sz=sz, attrib=attrib, tag=tag, colw=colw, firsts=firsts, nwords=len([w for w in re.split(r"[\s|*]+", c["text"]) if w]), text=c["text"])

def build_hero(c):
    """big stacked slam text.  c: lines [(text,color 'W'/'T',max_size)], maxw, attrib, pre (small preface lines), side"""
    maxw = c.get("maxw", 600); out = []
    for txt, col, ms in c["lines"]:
        sz = fit_size(txt, BOLD, maxw, ms)
        out.append((make_sprite([(txt, WHITE if col == "W" else TEAL)], BOLD, sz), sz))
    pre = None
    if c.get("pre"):
        lines = [parse_spans(s) for s in c["pre"]]
        lines[0] = [("“", TEAL)] + lines[0]
        sz = min(fit_size(spans_text(sp), BOLD, maxw, 46) for sp in lines)
        pre = ([make_sprite(sp, BOLD, sz) for sp in lines], sz)
    attrib = make_sprite([("\u2014 " + c["attrib"], GRAY)], MED, 28, tracking=4) if c.get("attrib") else None
    tag = make_sprite([(c["tag"], TEAL)], BOLD, 26, tracking=6) if c.get("tag") else None
    return dict(lines=out, pre=pre, attrib=attrib, tag=tag, maxw=maxw)

def build_stat(c):
    """10-block share bar.  c: tag, big, big_color, label, states[10] in {'T','W','D'}, foot, maxw"""
    maxw = c.get("maxw", 560)
    big, _p = make_sprite([(c["big"], TEAL if c.get("big_color", "T") == "T" else WHITE)], BOLD, fit_size(c["big"], BOLD, maxw, 150))
    bigsz = fit_size(c["big"], BOLD, maxw, 150)
    label, _p = make_sprite([(c["label"], WHITE)], BOLD, fit_size(c["label"], BOLD, maxw, 52))
    labsz = fit_size(c["label"], BOLD, maxw, 52)
    tag = make_sprite([(c["tag"], GRAY)], MED, 26, tracking=5)
    foot = make_sprite([(c["foot"], GRAY)], MED, 30)
    bs = 44; gap = 12
    blocks = {}
    for st, col, al in (("T", TEAL, 255), ("W", (235, 238, 244), 255), ("D", (255, 255, 255), 54)):
        im = Image.new("RGBA", (bs + 8, bs + 8), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        d.rounded_rectangle((4, 4, 4 + bs, 4 + bs), radius=9, fill=col + (al,))
        blocks[st] = im
    colw = max(10 * (bs + gap) - gap, tag[0].width - 80, label.width - 80, foot[0].width - 80, big.width - 80)
    return dict(big=((big, 40), bigsz), label=((label, 40), labsz), tag=tag, foot=foot, blocks=blocks, states=c["states"], bs=bs, gap=gap, colw=colw)

# ---------------------------------------------------------------- per-frame composition
EV = None
def render_frame(n):
    t = n * FT
    cv = Image.new("RGBA", (W, H), (0, 0, 0, 0)); used = False
    if n < INTERVIEW_FRAMES:
        for e in EV:
            a, a_in = window(t, e["t_in"], e["t_out"], fi=e.get("fi", 0.45), fo=e.get("fo", 0.35))
            if a <= 0: continue
            used = True
            k = e["k"]
            if k == "headline": draw_headline(cv, e, t, a, a_in)
            elif k == "pill": draw_pill(cv, e, t, a, a_in)
            elif k == "card": draw_card(cv, e, t, a, a_in)
            elif k == "hero": draw_hero(cv, e, t, a, a_in)
            elif k == "stat": draw_stat(cv, e, t, a, a_in)
        # subtitles
        for c in S["caps"]:
            if c["start"] - 0.001 <= t < c["end"]:
                ai = ease_out((t - c["start"]) / 0.12); ao = 1 - ease_io((t - (c["end"] - 0.08)) / 0.08)
                used = True; a = min(ai, ao); lh = CAP_LH; nl = len(c["sprites"]); y_bot = CAP_YB
                for i, (sp, pad) in enumerate(c["sprites"]):
                    ycur = y_bot - (nl - i) * lh
                    x = (W - (sp.width - 2 * pad)) / 2 - pad
                    paste(cv, sp, x, ycur - pad + 6 + (1 - ai) * 6, a)
                break
    if INTERVIEW_FRAMES - 11 <= n < INTERVIEW_FRAMES:
        a = ease_io((n - (INTERVIEW_FRAMES - 11)) / 11)
        cv = Image.alpha_composite(cv, Image.new("RGBA", (W, H), NEAR_BLACK + (int(255 * a),))); used = True
    if n >= INTERVIEW_FRAMES:
        K = max(1.0, 132 / CARD); c = (n - INTERVIEW_FRAMES) * K; CARDs = CARD * K; used = True      # animations were timed for a 132-frame (5.5 s) card: a shorter card plays them faster
        cv = Image.new("RGBA", (W, H), NEAR_BLACK + (255,))
        if CLEAN:
            if S["c_src"] is not None:
                a3 = ease_out((c - 8) / 20); sp, pad = S["c_src"]
                paste(cv, sp, (W - (sp.width - 2 * pad)) / 2 - pad, H / 2 - 30 - pad, a3)
            fo = ease_io((c - (CARDs - 24)) / 22)
            if fo > 0: cv = Image.alpha_composite(cv, Image.new("RGBA", (W, H), (0, 0, 0, int(255 * min(1, fo)))))
            return cv
        a1 = ease_out((c - 10) / 14); sp, pad = S["c_main"]
        paste(cv, sp, (W - (sp.width - 2 * pad)) / 2 - pad, 440 + (1 - a1) * 24 - pad, a1)
        wr = int(140 * ease_out((c - 26) / 16))
        if wr > 0: paste(cv, S["c_rule"].crop((0, 0, wr, 6)), (W - 140) / 2, 590, 1)
        a2 = ease_out((c - 38) / 16); sp, pad = S["c_sub"]
        paste(cv, sp, (W - (sp.width - 2 * pad)) / 2 - pad, 634 + (1 - a2) * 14 - pad, a2)
        a3 = ease_out((c - 64) / 16); sp, pad = S["c_src"]
        paste(cv, sp, (W - (sp.width - 2 * pad)) / 2 - pad, 880 - pad, a3 * 0.9)
        fo = ease_io((c - (CARDs - 24)) / 22)
        if fo > 0: cv = Image.alpha_composite(cv, Image.new("RGBA", (W, H), (0, 0, 0, int(255 * min(1, fo)))))
    return cv if used else None

def draw_headline(cv, e, t, a, a_in):
    HC = EVM.HEAD; side = HC.get("side", "L"); colw = S["hw"]
    x0 = col_x(side, colw) - 40
    ys = []; y = 0.0
    for i, (sp, sz, f) in enumerate(S["hl"]):
        ys.append(y); y += sz * (1.38 if i == len(S["hl"]) - 1 else f)
    block = y + 80
    y1 = HC.get("y0", 500 - block / 2)
    paste(cv, S["scrimL"] if side == "L" else S["scrimR"], 0 if side == "L" else W - S["scrimL"].width, 0, a * 0.95)
    ao = 1 - ease_io((t - (e["t_out"] - 0.4)) / 0.4)
    delays = [0.00, 0.14, 0.34, 0.50, 0.60, 0.70]
    for i, (sp, sz, f) in enumerate(S["hl"]):
        d = delays[i]
        if t < e["t_in"] + d: continue
        off = (1 - ease_out((t - e["t_in"] - d) / 0.55)) * 34
        ai = ease_out((t - e["t_in"] - d) / 0.5)
        paste(cv, sp[0], x0, y1 + ys[i] + off - sp[1], max(0, min(1, ai)) * ao)
    yr = y1 + y
    if t >= e["t_in"] + 0.85:
        ai = ease_out((t - e["t_in"] - 0.85) / 0.5)
        wr = int(96 * ease_out((t - e["t_in"] - 0.85) / 0.5))
        if wr > 0: paste(cv, S["rule"].crop((0, 0, wr, 7)), x0 + 40, yr, ao)
        paste(cv, S["hsub"][0], x0, yr + 23 - S["hsub"][1] + 6, max(0, min(1, ai)) * ao)

def draw_pill(cv, e, t, a, a_in):
    pill, sub = S["pills"][e["key"]]; side = e.get("side", "L")
    # clean look: pills are lower-thirds (above the captions, never over a head); "y" is only honoured by style "full"
    y = e.get("y_clean", 800 if TALL else 690) if CLEAN else e.get("y", 130)
    off = (1 - a_in) * (-14 if side == "L" else 14)
    pw = pill.width - 80
    x = (MARGIN - 40 if side == "L" else W - MARGIN - pw - 40) + off
    paste(cv, pill, x, y - 40, a)
    if sub is not None:
        sp, pad = sub
        sx = (MARGIN + 8 - 40 if side == "L" else min(W - MARGIN - pw + 8, W - MARGIN - (sp.width - 2 * pad) - 8) - 40) + off   # right side: never past the margin
        paste(cv, sp, sx, y + int(84 * PS) - pad, a)

def card_layout(e, c):
    side = e.get("side", "L"); x0 = col_x(side, c["colw"]); return side, x0
def draw_card(cv, e, t, a, a_in):
    c = S["cards"][e["key"]]; side, x0 = card_layout(e, c); y = e["y"]; sz = c["sz"]
    paste(cv, S["e_scrimL"] if side == "L" else S["e_scrimR"], 0 if side == "L" else W - 1000, y - 230, a * 0.9)
    ao = 1 - ease_io((t - (e["t_out"] - 0.35)) / 0.35)
    rr = S["e_rule"].crop((0, 0, max(1, int(72 * ease_out((t - e["t_in"]) / 0.5))), 6))
    paste(cv, rr, x0, y - 36, a)
    ytag = y
    if c["tag"] is not None:
        sp, pad = c["tag"]; ai = ease_out((t - e["t_in"] - 0.05) / 0.4)
        paste(cv, sp, x0 - pad, y - 8 - pad + 6, min(ai, ao)); y += 40
    wt = e.get("words_t")
    lt = [wt[min(len(wt) - 1, f)] - 0.05 for f in c["firsts"]] if wt else None
    for i, (sp, pad) in enumerate(c["sprites"]):
        ts = max(e["t_in"] + 0.05 * i, lt[i]) if lt else e["t_in"] + 0.1 + 0.12 * i
        ai2 = ease_out((t - ts) / 0.5)
        if ai2 <= 0: continue
        paste(cv, sp, x0 - pad, y + i * (sz * 1.14) + (1 - ai2) * 26 - pad + 6, min(ai2, ao))
    if c["attrib"] is not None:
        sp, pad = c["attrib"]; ts = (lt[-1] if lt else e["t_in"] + 0.1 + 0.12 * len(c["sprites"])) + 0.15
        ai = ease_out((t - ts) / 0.5)
        paste(cv, sp, x0 - pad, y + len(c["sprites"]) * (sz * 1.14) + 10 - pad + (1 - ai) * 10, min(ai, ao) * 0.95)

def draw_hero(cv, e, t, a, a_in):
    c = S["heroes"][e["key"]]; side = e.get("side", "L"); x0 = col_x(side, c["maxw"]); y = e["y"]
    paste(cv, S["e_scrimL2"] if side == "L" else S["e_scrimR2"], 0 if side == "L" else W - 1000, y - 300, a * 0.95)
    ao = 1 - ease_io((t - (e["t_out"] - 0.4)) / 0.4)
    yy = y
    if c["tag"] is not None:
        sp, pad = c["tag"]; ai = ease_out((t - e["t_in"] - 0.05) / 0.4)
        paste(cv, sp, x0 - pad, yy - pad + 6, min(ai, ao)); yy += 44
    if c["pre"] is not None:
        sps, psz = c["pre"]
        for i, (sp, pad) in enumerate(sps):
            ai = ease_out((t - e["t_in"] - 0.1 - 0.12 * i) / 0.5)
            paste(cv, sp, x0 - pad, yy + i * (psz * 1.14) + (1 - ai) * 20 - pad + 6, min(ai, ao))
        yy += len(sps) * psz * 1.14 + 34
    hl = e.get("hero_t")
    ar = ease_out((t - (hl[0] if hl else e["t_in"]) + 0.15) / 0.5)
    paste(cv, S["e_rule"].crop((0, 0, max(1, int(72 * ar)), 6)), x0, yy, min(ar, ao)); yy += 22
    for i, ((sp, pad), sz) in enumerate(c["lines"]):
        ts = hl[i] if hl else e["t_in"] + 0.35 + 0.22 * i
        p = (t - ts) / 0.32
        if p > 0:
            sc = 1.0 + 0.16 * (1 - ease_out(p)); ai = ease_out(p * 1.6); im = sp
            if sc > 1.003: im = sp.resize((int(sp.width * sc), int(sp.height * sc)), Image.LANCZOS)
            dy = -(im.height - sp.height) / 2
            paste(cv, im, x0 - pad, yy + dy - pad + 6, min(ai, ao))
        yy += sz * 1.0 + 4
    if c["attrib"] is not None:
        sp, pad = c["attrib"]; ts = (hl[-1] if hl else e["t_in"] + 0.35) + 0.5
        ai = ease_out((t - ts) / 0.5)
        paste(cv, sp, x0 - pad, yy + 26 - pad + (1 - ai) * 10, min(ai, ao) * 0.95)

def draw_stat(cv, e, t, a, a_in):
    c = S["stats"][e["key"]]; side = e.get("side", "L"); x0 = col_x(side, c["colw"]); y = e["y"]
    paste(cv, S["e_scrimL2"] if side == "L" else S["e_scrimR2"], 0 if side == "L" else W - 1000, y - 250, a * 0.95)
    ao = 1 - ease_io((t - (e["t_out"] - 0.35)) / 0.35)
    ai = ease_out((t - e["t_in"]) / 0.5)
    paste(cv, S["e_rule"].crop((0, 0, max(1, int(72 * ai)), 6)), x0, y - 36, a)
    sp, pad = c["tag"]; paste(cv, sp, x0 - pad, y - 8 - pad + 6, min(ai, ao))
    (sp, pad), sz = c["big"]; ai = ease_out((t - e["t_in"] - 0.1) / 0.5)
    paste(cv, sp, x0 - pad, y + 34 + (1 - ai) * 24 - pad, min(ai, ao))
    ybar = y + 34 + sz * 1.05 + 14
    for i in range(10):
        ts = e["t_in"] + 0.35 + 0.06 * i
        p = ease_back((t - ts) / 0.35)
        if p <= 0: continue
        st = c["states"][i]; bl = c["blocks"][st]
        sc = max(0.01, p)
        im = bl if abs(sc - 1) < 0.02 else bl.resize((max(1, int(bl.width * sc)), max(1, int(bl.height * sc))), Image.LANCZOS)
        bx = x0 + i * (c["bs"] + c["gap"]) - 4 + (bl.width - im.width) / 2
        by = ybar - 4 + (bl.height - im.height) / 2
        paste(cv, im, bx, by, min(1.0, p * 1.5) * ao)
    (sp, pad), lsz = c["label"]; ai = ease_out((t - e["t_in"] - 0.55) / 0.5)
    paste(cv, sp, x0 - pad, ybar + c["bs"] + 20 + (1 - ai) * 16 - pad, min(ai, ao))
    sp, pad = c["foot"]; ai = ease_out((t - e["t_in"] - 0.8) / 0.5)
    paste(cv, sp, x0 - pad, ybar + c["bs"] + 20 + lsz * 1.2 + 4 - pad, min(ai, ao) * 0.95)

def work(n):
    cv = render_frame(n); path = f"{OUT}/f{n:05d}.png"
    if cv is None: return n, None
    cv.save(path, compress_level=1); return n, path

def init():
    global EV
    build_sprites(); EV = EVM.schedule(T)

if __name__ == "__main__":
    os.chdir(out_dir()); os.makedirs(OUT, exist_ok=True)
    frames = range(TOTAL)
    if len(sys.argv) > 2: frames = [int(x) for x in sys.argv[2].split(",")]
    init()
    blank = Image.new("RGBA", (W, H), (0, 0, 0, 0)); blank.save(f"{OUT}/blank.png")
    with Pool(8, initializer=init) as pool:
        res = pool.map(work, frames, chunksize=8)
    nb = 0
    for n, path in res:
        if path is None:
            dst = f"{OUT}/f{n:05d}.png"
            if os.path.lexists(dst): os.remove(dst)
            os.link(f"{OUT}/blank.png", dst); nb += 1
    print("frames", len(res), "blank", nb)
