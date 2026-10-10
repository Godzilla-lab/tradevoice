# The TradeVoice film

A 60 to 70 second brand film in 16:9 (1920x1080, 60 fps), built in code so it can be remade when the app changes.
It is not the NAIC demo video: that one stays a real screen recording with a real trader (docs/naic/VIDEO_SCRIPT.md).

## How it is made
| Step | Command | What it does |
|---|---|---|
| 1 | `python film/make_lines.py` | The spoken lines, written by the app's own reply code (`src/tts.py`) |
| 2 | on the server: see the top of `film/voices.sh` | Spitch makes the voice clips; the key stays on the server |
| 3 | `python film/prep_voices.py` | Downloads the clips, picks a take per line (`voices/picks.json`), trims, measures loudness |
| 4 | `NODE_PATH=$(npm root -g) node film/capture.cjs` | The real app, run here with made-up names, captured at 3x |
| 5 | `python film/prep_shots.py` | Cuts the captures into layers (sheets, toast) |
| 6 | `NODE_PATH=$(npm root -g) node film/render.cjs --info` | Timing: shots in bars of 112 BPM, sound cues -> `out/film.json` |
| 7 | `python film/sound.py` | Music, product sounds, the market, voices, ducking, -14 LUFS -> `out/mix.wav` |
| 8 | `NODE_PATH=$(npm root -g) node film/render.cjs --video --fps 120` | Frames (blended to 60 fps for motion blur) + mix -> `out/TradeVoice-film.mp4` |

Checks while working: `render.cjs --sheet 30` (a contact sheet), `render.cjs --stills 12.5,30` (single frames).
Setup once: `cd film && npm install` (GSAP and the fonts, exact versions) and `pip install scipy`.

## Rules the film keeps
Made-up names only, no phone numbers, no emojis, no long dashes. Every claim is true today. The N-ATLaS attribution is
on screen with the N-ATLaS numbers and on the end card. Credits for the sounds: `film/CREDITS.md`.
The Yorùbá, Hausa and Igbo lines and subtitles need the native-speaker check before the film is published.
