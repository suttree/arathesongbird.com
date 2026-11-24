# arathesongbird.com

The player chooses five songs from 33 generated birdsong clips. The clips use
the voice on the `codex/birdsong-voice-prototype` branch of `suttree/araduino`,
at commit `75c9848190cfe24f39da840ebc71b79c79e596ed`.

To recreate them, check out that source commit in `../araduino`, then run:

```sh
python3 tools/render-birdsong.py
```

This requires Python 3, a C++ compiler and ffmpeg. Use `--source /path/to/araduino`
for another source location. The renderer keeps complete phrases and adds
120 ms of silence before each song and 600 ms after it. The AAC files have
3 dB of encoding headroom. `assets/media/birdsong.json` records the source
commit, seeds, song details and file hashes.
