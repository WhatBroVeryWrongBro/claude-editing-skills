#!/usr/bin/env python3
"""cartoon-explainer: scenes (SVG) + narration (ElevenLabs mp3) -> captioned 1080x1920 cartoon short.

    python build.py spec.json [--prepare-only]

Spec (paths relative to the spec file):
{
  "out": "out/brain.mp4",
  "voice_dir": "voice",                 # scene-01.mp3 ... (+ optional scene-01.words.json) from voice.py / ElevenLabs
  "music": true, "pad": 0.3,
  "scenes": [{"svg": "scenes/01.svg", "text": "narration line", "camera": "push|pull|pan-left|pan-right|still",
              "transition": "cut|whip|zoom", "sfx": ["pop@0.4", "squish@1.2"], "dur": 3.5}]   # dur only when no audio yet
}
SVG scenes are 1080x1920 and may <use href="#hero-happy|scared|think|dead" x= y=> from the built-in character library.
"""
import argparse, html, json, os, re, shutil, subprocess, sys, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK = HERE.parents[1]
FPS, W, H = 30, 1080, 1920
WPS = 2.6  # words per second used only when a scene has no audio yet

def sh(cmd, **kw): return subprocess.run([str(c) for c in cmd], check=True, **kw)
def dur_of(p): return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(p)]))

# ---- character library: a rounded white head, bean body, dot eyes, thick brows ----
def hero(mood):
    mouth = {'happy':'M-22 38 Q0 58 22 38','scared':'M-18 48 Q0 30 18 48','think':'M-18 42 L18 42','dead':'M-20 46 Q0 34 20 46'}[mood]
    eyes = '<path d="M-34 -8 l16 16 m0 -16 l-16 16 M18 -8 l16 16 m0 -16 l-16 16" stroke="#111" stroke-width="7" stroke-linecap="round"/>' if mood=='dead' else \
           '<circle cx="-26" cy="0" r="9" fill="#111"/><circle cx="26" cy="0" r="9" fill="#111"/>'
    brow = {'happy':(-40,-26,-14,-30,14,-30,40,-26),'scared':(-40,-34,-14,-24,14,-24,40,-34),'think':(-40,-24,-14,-30,14,-24,40,-32),'dead':(-40,-24,-14,-24,14,-24,40,-24)}[mood]
    return (f'<symbol id="hero-{mood}" overflow="visible" viewBox="-120 -120 240 560"><g stroke="#111" stroke-width="8" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M-40 130 Q-70 230 -30 330 L30 330 Q70 230 40 130 Z" fill="#7fb6e6"/>'
            '<path d="M-38 160 L-95 250 M38 160 L95 250 M-20 330 L-28 420 M20 330 L28 420" fill="none"/>'
            '<ellipse cx="0" cy="10" rx="85" ry="95" fill="#fff"/>'
            f'{eyes}<path d="M{brow[0]} {brow[1]} L{brow[2]} {brow[3]} M{brow[4]} {brow[5]} L{brow[6]} {brow[7]}" fill="none" stroke-width="9"/>'
            f'<path d="{mouth}" fill="none"/></g></symbol>')
LIB = '<svg width="0" height="0" style="position:absolute"><defs>' + ''.join(hero(m) for m in ('happy','scared','think','dead')) + '</defs></svg>'

# ---- synthesized SFX + music (all by ffmpeg, no assets needed) ----
SFX = {
 'pop':    'sine=f=720:d=0.1,afade=t=out:st=0.02:d=0.08',
 'beep':   'sine=f=1300:d=0.14,afade=t=out:st=0.08:d=0.06',
 'squish': 'sine=f=180:d=0.3,vibrato=f=18:d=0.9,afade=t=out:st=0.1:d=0.2',
 'thud':   'sine=f=70:d=0.25,afade=t=out:st=0.05:d=0.2',
 'whoosh': 'anoisesrc=d=0.45:c=pink:a=0.6,highpass=f=500,afade=t=in:d=0.18,afade=t=out:st=0.2:d=0.25',
 'ding':   'sine=f=1568:d=0.5,afade=t=out:st=0.05:d=0.45',
}
def make_sfx(work):
    d = work/'sfx'; d.mkdir(exist_ok=True)
    for k, f in SFX.items():
        if not (d/f'{k}.wav').exists():
            sh(['ffmpeg','-v','error','-y','-f','lavfi','-i',f,'-ar','44100','-ac','2',d/f'{k}.wav'])
    return d
def make_music(work, total):
    p = work/'music.wav'
    sh(['ffmpeg','-v','error','-y','-f','lavfi','-i',f'sine=f=220:d={total}','-f','lavfi','-i',f'sine=f=277.2:d={total}','-f','lavfi','-i',f'sine=f=329.6:d={total}',
        '-filter_complex','[0][1][2]amix=inputs=3:normalize=0,tremolo=f=0.35:d=0.5,lowpass=f=900,volume=0.5,afade=t=in:d=1,afade=t=out:st=%.2f:d=1.5[a]'%max(0,total-1.5),
        '-map','[a]','-ar','44100','-ac','2',p])
    return p

def clean(w): return re.sub(r'\s+', ' ', w).strip()
def scene_words(sc, vdir, i, dur):
    """[{w,s,e}] local to the scene: real ElevenLabs timings if present, else weighted by letters."""
    wj = vdir/f'scene-{i+1:02d}.words.json' if vdir else None
    if wj and wj.is_file(): return json.loads(wj.read_text())
    ws = clean(sc['text']).split(' '); tot = sum(len(w)+2 for w in ws); t = 0.05; out = []
    for w in ws:
        d = (dur-0.15)*(len(w)+2)/tot; out.append({'w': w, 's': round(t,3), 'e': round(t+d,3)}); t += d
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('spec', type=Path); ap.add_argument('--prepare-only', action='store_true')
    a = ap.parse_args(); spec = json.loads(a.spec.read_text()); base = a.spec.resolve().parent
    P = lambda v: (Path(v) if os.path.isabs(v) else base/v)
    out = P(spec.get('out', 'out/cartoon.mp4')).resolve(); comp = out.parent/(out.stem+'.composition'); comp.mkdir(parents=True, exist_ok=True)
    work = out.parent/(out.stem+'.work'); work.mkdir(exist_ok=True)
    vdir = P(spec['voice_dir']) if spec.get('voice_dir') else None; pad = spec.get('pad', 0.3)
    shutil.copytree(PACK/'kit/fonts', comp/'fonts', dirs_exist_ok=True)
    vendor = PACK/'kit/vendor/gsap-3.15.0.min.js'
    if not vendor.is_file():
        vendor.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen('https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js', timeout=30) as r: vendor.write_bytes(r.read())
    (comp/'vendor').mkdir(exist_ok=True); shutil.copyfile(vendor, comp/'vendor/gsap.min.js')

    scenes, t0, js, divs, caps, mix = spec['scenes'], 0.0, [], [], [], []
    sfxdir = make_sfx(work)
    for i, sc in enumerate(scenes):
        mp3 = vdir/f'scene-{i+1:02d}.mp3' if vdir else None
        have = bool(mp3 and mp3.is_file())
        d = (dur_of(mp3) if have else sc.get('dur') or len(sc['text'].split())/WPS) + pad
        svg = P(sc['svg']).read_text()
        divs.append(f'<div id="s{i}" class="scene" style="opacity:{1 if i==0 else 0};z-index:{i}"><div class="cam">{svg}</div></div>')
        cam, tr = sc.get('camera','push'), sc.get('transition','cut' if i==0 else 'whip')
        # camera move over the whole scene
        f = {'push':({'scale':1},{'scale':1.12}), 'pull':({'scale':1.12},{'scale':1}), 'pan-left':({'scale':1.1,'x':40},{'scale':1.1,'x':-40}),
             'pan-right':({'scale':1.1,'x':-40},{'scale':1.1,'x':40}), 'still':({'scale':1},{'scale':1})}[cam]
        js.append(f"tl.fromTo('#s{i} .cam',{json.dumps(f[0])},{{...{json.dumps(f[1])},duration:{d:.3f},ease:'none'}},{t0:.3f});")
        if i > 0:
            if tr == 'whip':
                js.append(f"tl.set('#s{i}',{{opacity:1,x:{W}}},{t0-0.001:.3f});tl.to('#s{i}',{{x:0,duration:0.22,ease:'power3.out'}},{t0:.3f});tl.to('#s{i-1}',{{x:-{W//2},duration:0.22,ease:'power3.out'}},{t0:.3f});tl.set('#s{i-1}',{{opacity:0}},{t0+0.23:.3f});")
                mix.append(('whoosh', t0-0.05))
            elif tr == 'zoom':
                js.append(f"tl.set('#s{i}',{{opacity:1}},{t0:.3f});tl.fromTo('#s{i}',{{scale:1.5}},{{scale:1,duration:0.25,ease:'power2.out'}},{t0:.3f});tl.set('#s{i-1}',{{opacity:0}},{t0+0.01:.3f});")
                mix.append(('pop', t0))
            else:
                js.append(f"tl.set('#s{i}',{{opacity:1}},{t0:.3f});tl.set('#s{i-1}',{{opacity:0}},{t0:.3f});")
        for tag in sc.get('sfx', []):
            n, _, at = tag.partition('@'); mix.append((n, t0+float(at or 0)))
        # captions: 2-3 word bursts
        ws = scene_words(sc, vdir if have else None, i, d-pad); k = 0
        while k < len(ws):
            g = ws[k:k+3 if len(clean(' '.join(x['w'] for x in ws[k:k+3]))) < 20 else k+2]; k += len(g)
            cid = f'c{i}_{k}'; caps.append(f'<div id="{cid}" class="cap">{html.escape(" ".join(x["w"] for x in g).upper())}</div>')
            js.append(f"tl.set('#{cid}',{{opacity:1,scale:0.85}},{t0+g[0]['s']:.3f});tl.to('#{cid}',{{scale:1,duration:0.12,ease:'back.out(3)'}},{t0+g[0]['s']:.3f});tl.set('#{cid}',{{opacity:0}},{t0+g[-1]['e']+0.12:.3f});")
        if have: mix.append((str(mp3), t0 + 0.0))
        t0 += d
    total = round(t0, 2)
    css = ("@font-face{font-family:Archivo;src:url(fonts/archivo-black-400-normal.woff2)}*{margin:0;box-sizing:border-box}html,body{width:1080px;height:1920px;overflow:hidden;background:#111}"
           "#root{position:relative;width:1080px;height:1920px;overflow:hidden}.scene,.cam{position:absolute;left:0;top:0;width:1080px;height:1920px}.cam{transform-origin:50% 55%}.cam svg{width:1080px;height:1920px;display:block}"
           ".cap{position:absolute;left:60px;width:960px;top:1330px;text-align:center;opacity:0;font:400 92px/1.05 Archivo,sans-serif;color:#fff;-webkit-text-stroke:14px #000;paint-order:stroke fill;z-index:99;text-shadow:0 8px 0 #000}")
    (comp/'index.html').write_text(f'<!doctype html><html><head><meta charset="utf-8"><title>cartoon-explainer</title><style>{css}</style></head><body>{LIB}'
        f'<div id="root" data-composition-id="main" data-width="{W}" data-height="{H}" data-duration="{total}" data-fps="{FPS}">{"".join(divs)}{"".join(caps)}</div>'
        f'<script src="vendor/gsap.min.js"></script><script>const tl=gsap.timeline({{paused:true}});{"".join(js)}window.__timelines=window.__timelines||{{}};window.__timelines.main=tl;</script></body></html>')
    (comp/'hyperframes.json').write_text(json.dumps({'media': {'autoProxy': False}}))
    print(comp, f'({total}s)', flush=True)
    if a.prepare_only: return
    cli = ['node', os.environ['HYPERFRAMES_CLI']] if os.environ.get('HYPERFRAMES_CLI') else ['npx','--yes','hyperframes@0.8.214']
    silent = work/'silent.mp4'
    sh(cli+['check', comp, '--json']); sh(cli+['render', comp, '-o', silent, '--fps', str(FPS), '--quality', 'looks', '--workers', '2'])
    # audio: narration + sfx + (optional) music, mixed with ffmpeg
    ins, filt, labels = [], [], []
    for n, (name, at) in enumerate(mix):
        ins += ['-i', name if name.endswith('.mp3') else sfxdir/f'{name}.wav']
        vol = '1.0' if name.endswith('.mp3') else '0.45'
        filt.append(f'[{n+1}:a]aresample=44100,aformat=channel_layouts=stereo,volume={vol},adelay={int(max(0,at)*1000)}|{int(max(0,at)*1000)}[a{n}]'); labels.append(f'[a{n}]')
    if spec.get('music', True):
        ins += ['-i', make_music(work, total)]; n = len(mix); filt.append(f'[{n+1}:a]volume=0.25[a{n}]'); labels.append(f'[a{n}]')
    if labels:
        filt.append(''.join(labels)+f'amix=inputs={len(labels)}:normalize=0:duration=longest,alimiter=limit=0.95,atrim=0:{total}[aout]')
        sh(['ffmpeg','-v','error','-y','-i',silent]+ins+['-filter_complex',';'.join(filt),'-map','0:v','-map','[aout]','-c:v','copy','-c:a','aac','-b:a','192k','-shortest',out])
    else: shutil.copyfile(silent, out)
    sh(['ffmpeg','-v','error','-i',out,'-f','null','-']); print(out)

if __name__ == '__main__': main()
