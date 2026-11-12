"""Assemble PITCH.html: templates + numbers.json + charts from the saved arrays + images embedded as base64.
Usage: build.py <numbers.json> <box_out_dir> <out.html>"""
import sys, json, re, io, base64, os
import numpy as np
from PIL import Image
import figs

HERE = os.path.dirname(os.path.abspath(__file__))
numbers, box, out = sys.argv[1], sys.argv[2], sys.argv[3]
V = json.load(open(numbers))


def img(path, width=1500, q=82):
    im = Image.open(path).convert('RGB')
    if im.width > width:
        im = im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
    b = io.BytesIO(); im.save(b, 'JPEG', quality=q, optimize=True)
    return 'data:image/jpeg;base64,' + base64.b64encode(b.getvalue()).decode()


for k, spec in V.pop('_images').items():
    V[k] = img(spec['path'], spec.get('width', 1500), spec.get('q', 82))

# chart 1: doubt against actual error, held-out familiar poses and never-seen families
E = np.load(f'{box}/trust/eval.npz', allow_pickle=True)
ev = np.concatenate([E['te'], E['ood']])
known = np.array([True] * len(E['te']) + [False] * len(E['ood']))
tau = json.load(open(f'{box}/trust/summary.json'))['tau']
V['svg_scatter'] = figs.doubt_scatter(E['doubt'][ev], E['err'][ev], known, tau, fam=[str(f) for f in E['fam'][ev]])

# chart 2: her second clip. Learned model (after her first clip) on every frame, against the solver's 12 key frames
L = np.load(f'{box}/trust/live_puppet.npz'); C = np.load(f'{box}/trust/heldout_after.npz')
tp, yp = C['t'][:12], C['y'][:12, 0]
o = np.argsort(tp)
V['svg_clip'] = figs.clip_lines(tp[o], yp[o], L['t'], L['CdA'], L['sure'], 'drag area, m²',
                                label_model='learned model, all 572 frames', label_solver='real solver, 12 frames')

# the gate as a table
S = json.load(open(f'{box}/trust/summary.json'))
rows = [('Familiar poses, held out', S['gate']['test'])] + [(n, S['gate']['ood_' + k]) for k, n in
        (('prone', 'Never seen: lying head-first'), ('side', 'Never seen: side-on'), ('back', 'Never seen: back to the wind'), ('inverted', 'Never seen: upside down'))]
tb = '<table><thead><tr><th>Poses</th><th class="num">How many</th><th class="num">Answered instantly</th><th class="num">Their mean error</th><th class="num">Mean error of all</th><th class="num">More than 10% wrong</th><th class="num">Of those, answered</th></tr></thead><tbody>'
for name, g in rows:
    n_ans = round(g['answered_instantly_pct'] * g['n'] / 100)
    tb += f"<tr><td>{name}</td><td class='num'>{g['n']}</td><td class='num'>{n_ans}</td><td class='num'>{'%.1f%%' % g['err_of_answered_mean_pct'] if n_ans else '–'}</td><td class='num'>{g['err_if_no_gate_mean_pct']:.1f}%</td><td class='num'>{g['bad_answers_gt10pct_total']}</td><td class='num'>{g['bad_answers_gt10pct_let_through']}</td></tr>"
V['gate_table'] = tb + '</tbody></table>'

html = open(f'{HERE}/template_head.html').read() + open(f'{HERE}/template_mid.html').read() + open(f'{HERE}/static_tail.html').read() + open(f'{HERE}/template_appendix.html').read()
missing = sorted(set(re.findall(r'\{\{(\w+)\}\}', html)) - set(V))
if missing:
    sys.exit('missing values: ' + ', '.join(missing))
for k, v in V.items():
    html = html.replace('{{' + k + '}}', str(v))
open(out, 'w').write(html)
words = len(re.sub(r'<svg.*?</svg>|<style.*?</style>|<[^>]+>|data:image[^"]+', ' ', html, flags=re.S).split())
print(f'wrote {out}: {len(html) / 1e6:.2f} MB, about {words} words')
