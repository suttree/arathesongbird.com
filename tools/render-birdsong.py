#!/usr/bin/env python3
"""Recreate the website clips from the Arduino birdsong branch."""
import argparse
import array
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = '75c9848190cfe24f39da840ebc71b79c79e596ed'
SEEDS = [2026112411, 2026112412, 2026112413, 2026112414]
CLIP_COUNT = 33


def run(*command):
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT.parent / 'araduino')
    parser.add_argument('--output', type=Path, default=ROOT / 'assets/media')
    args = parser.parse_args()
    source = args.source.resolve()
    if run('git', '-C', str(source), 'rev-parse', 'HEAD') != SOURCE_COMMIT:
        parser.error(f'The source checkout must be at {SOURCE_COMMIT}')
    if run('git', '-C', str(source), 'status', '--porcelain', '--', 'tools/audio', 'sketches'):
        parser.error('The source audio tools and sketches must have no local changes')
    args.output.mkdir(parents=True, exist_ok=True)
    clips = []
    with tempfile.TemporaryDirectory(prefix='ara-website-audio-') as temporary:
        for seed in SEEDS:
            reel = Path(temporary) / str(seed)
            print(run('python3', str(source / 'tools/audio/render.py'), '--session',
                      '--seed', str(seed), '--output', str(reel)), flush=True)
            with (reel / 'melody-session.csv').open() as report:
                songs = list(csv.DictReader(report))
            for song in songs:
                if len(clips) == CLIP_COUNT:
                    break
                destination = args.output / f'ara{len(clips) + 1}.m4a'
                # Keep the complete phrase, including its internal breaths and answer.
                # Add a short lead and tail; the player supplies the inter-song pause.
                run('ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                    '-i', str(reel / 'ara-melody-session.wav'), '-af',
                    f"atrim=start={song['start_seconds']}:duration={song['duration_seconds']},"
                    'asetpts=PTS-STARTPTS,volume=-3dB,adelay=120:all=1,apad=pad_dur=0.6',
                    '-ar', '48000', '-ac', '1', '-c:a', 'aac',
                    '-aac_coder', 'fast', '-b:a', '96k',
                    '-movflags', '+faststart', str(destination))
                decoded = subprocess.run(
                    ['ffmpeg', '-v', 'error', '-i', str(destination), '-f', 'f32le', '-'],
                    check=True, capture_output=True)
                samples = array.array('f', decoded.stdout)
                if (not samples or decoded.stderr or
                        not all(math.isfinite(sample) for sample in samples) or
                        not 0 < max(abs(sample) for sample in samples) < 1):
                    raise RuntimeError(f'Invalid or clipped audio in {destination}')
                clips.append({
                    'file': destination.name, 'seed': seed,
                    'song': int(song['song']),
                    'profile': int(song['profile']), 'motif': int(song['motif']),
                    'register': int(song['register']),
                    'held_duration_seconds': float(song['held_duration_seconds']),
                    'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
                })
    manifest = {
        'source_repository': 'https://github.com/suttree/araduino',
        'source_commit': SOURCE_COMMIT,
        'gain_percent': 350, 'encoding_gain_db': -3, 'aac_coder': 'fast',
        'lead_seconds': 0.12, 'tail_seconds': 0.6,
        'clips': clips,
    }
    (args.output / 'birdsong.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Rendered {len(clips)} clips into {args.output}')


if __name__ == '__main__':
    main()
