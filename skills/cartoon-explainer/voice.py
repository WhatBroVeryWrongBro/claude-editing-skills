#!/usr/bin/env python3
"""Narrate every scene with ElevenLabs. Writes voice/scene-NN.mp3 and scene-NN.words.json (exact word timings).

    ELEVENLABS_API_KEY=... python voice.py spec.json [--voice VOICE_ID] [--model eleven_multilingual_v2]

No API key? In Claude Code use the ElevenLabs connector instead (creative_list_voices -> creative_generate_speech, one call per
scene's "text"), download each result to voice/scene-NN.mp3, and build.py will time captions from the audio length.
"""
import argparse, base64, json, os, sys, urllib.request
from pathlib import Path

ap = argparse.ArgumentParser(); ap.add_argument('spec', type=Path); ap.add_argument('--voice', default=os.environ.get('ELEVENLABS_VOICE_ID', 'JBFqnCBsd6RMkjVDRZzb'))
ap.add_argument('--model', default='eleven_multilingual_v2'); a = ap.parse_args()
key = os.environ.get('ELEVENLABS_API_KEY') or sys.exit('Set ELEVENLABS_API_KEY (or use the ElevenLabs connector, see this file).')
spec = json.loads(a.spec.read_text()); base = a.spec.resolve().parent; vd = base/spec.get('voice_dir', 'voice'); vd.mkdir(parents=True, exist_ok=True)
for i, sc in enumerate(spec['scenes'], 1):
    req = urllib.request.Request(f'https://api.elevenlabs.io/v1/text-to-speech/{a.voice}/with-timestamps',
        data=json.dumps({'text': sc['text'], 'model_id': a.model, 'voice_settings': {'stability': .4, 'similarity_boost': .75, 'style': .35}}).encode(),
        headers={'xi-api-key': key, 'Content-Type': 'application/json'})
    r = json.load(urllib.request.urlopen(req, timeout=120))
    (vd/f'scene-{i:02d}.mp3').write_bytes(base64.b64decode(r['audio_base64']))
    al = r['alignment']; words, cur, st = [], '', None
    for ch, s, e in zip(al['characters'], al['character_start_times_seconds'], al['character_end_times_seconds']):
        if ch.isspace():
            if cur: words.append({'w': cur, 's': round(st, 3), 'e': round(pe, 3)}); cur = ''
        else:
            if not cur: st = s
            cur += ch; pe = e
    if cur: words.append({'w': cur, 's': round(st, 3), 'e': round(pe, 3)})
    (vd/f'scene-{i:02d}.words.json').write_text(json.dumps(words)); print('scene', i, 'ok')
