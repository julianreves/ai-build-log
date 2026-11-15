# STYLE GUIDE — the clean look

Design brief: the video is "not overcrowded with text and information… clean". The engine (`Toolkit/lib/overlays.py`) implements this page; the spec only chooses text, timing and where the speaker is.

## What is on screen
1. **The footage.**
2. **Captions**, large, lower centre: white with a dark outline, the few key words in teal (`highlights`). 64 px Helvetica Neue Medium. 16:9: up to 2 lines. 4:5: re-wrapped to the narrower frame, up to 3 lines.
3. **Pills** (lower-third, just above the captions): the speaker's name and role for the first seconds; the interviewer's name when they speak; a fairness label when one is needed (hypothetical, recollection, asked by the host). Dark rounded pill, teal dot, white tracked caps, grey sub-line.
4. **Source card**, 1.5 s at the end: one grey line ("Guest × Host · Channel") on #111318, then fade.

That is all. No headline animation, no quote cards, no slam text, no stat blocks, no closing slogan, no "≠" card, no music. If something feels missing, the fix is a better hook line or a better caption, not another graphic.

## Two versions of every clip
| | File | Size | Framing |
|---|---|---|---|
| 4:5 | `NN_Title_4x5.mp4` | 1080×1350 | a full-height window of the frame centred on whoever is speaking (spec `tall`) |
| 16:9 | `NN_Title.mp4` | 1920×1080 | the show's own framing, untouched |

Same cut, same audio, same captions, same pills. The 4:5 fills about 2.2 times more of a phone screen and its captions are about 23 px tall there (16:9: about 13 px). The author posts one of the two and alternates to compare.

## Technical
- Source frame rate (23.976 / 24 / 25 / 29.97 / 30; 50/60 are halved), x264 slow CRF 18 High, yuv420p, bt709, +faststart. AAC 192k 48 kHz stereo.
- Audio: highpass 70 Hz, two-pass loudnorm to **−16 LUFS**, true peak ≤ −1.5 dBFS, limiter. Speech only.
- Cuts only inside real pauses; 2-frame dissolve after the cold-open hook, 2–5 at other joins.
- **Length 30–45 s** including the source card. **Cold open:** the strongest 3–6 s first, first word inside the first second.
- Captions are burned in (Pillow; this ffmpeg has no text filters); an `.srt` is exported too.
- Sources must be 16:9. Anything else: stop and ask.

## Palette and type
Background #111318 · text white · grey #A8ADB7 · accent teal #00D9B4 · Helvetica Neue (Bold / Medium). Teal marks the word or number that carries the meaning: a few words per clip, never whole sentences.

## Placement
- Pills: `side` L or R = the side of the 16:9 frame where that person sits. They are lower-thirds, so they never touch a face; check they don't sit on a hand gesture that matters.
- The 4:5 crop must hold the speaker's whole head in every shot. Check `clip preview NN --tall` tile by tile.
- A pill naming the interviewer ends at the shot change back to the guest.

## Thumbnails
The only place the `headline` text appears. 16:9: stacked headline in a side column over a soft scrim, on a frame where that side is empty. 4:5: the same headline low on the frame, under the face. Headline = the claim the clip supports, 2–4 short lines, the key word in teal; never more than the speaker said.

## Spanish versions (optional; `clip build NN --es`)
Same look; captions and pills in Spanish, audio in English. Spanish runs about 20% longer: keep each caption ≤ ~68 characters and look at `clip preview NN --es` and `--es --tall`.

## Legacy look
`"style": "full"` in a spec brings back the earlier, busier graphics in 16:9 (headline animation, quote cards, hero, stats, closing card). Only for a specific clip that needs it. Details: SPEC_REFERENCE.md "Legacy".
