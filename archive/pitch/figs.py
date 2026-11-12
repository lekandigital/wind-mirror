"""Inline-SVG charts for the pitch page. Colours were checked with a colour-blindness validator
(olive #5E6E1F vs orange #E08A1E on the page surface); the two series also differ in marker shape and are labelled directly."""
import json, math
import numpy as np

OLIVE, ORANGE, INK, MUTED, GRID, SURFACE = '#5E6E1F', '#E08A1E', '#26281E', '#6E6F62', '#D9D3C4', '#F6F2E9'
FONT = "font-family:'Helvetica Neue',Helvetica,Arial,sans-serif"


def _axes(w, h, ml, mr, mt, mb, xt, yt, xmap, ymap, xl, yl, xfmt=str, yfmt=str):
    o = [f'<rect x="0" y="0" width="{w}" height="{h}" fill="{SURFACE}" rx="14"/>']
    for v in yt:
        y = ymap(v)
        o.append(f'<line x1="{ml}" x2="{w - mr}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        o.append(f'<text x="{ml - 8}" y="{y + 4:.1f}" text-anchor="end" font-size="12" fill="{MUTED}">{yfmt(v)}</text>')
    for v in xt:
        x = xmap(v)
        o.append(f'<text x="{x:.1f}" y="{h - mb + 18}" text-anchor="middle" font-size="12" fill="{MUTED}">{xfmt(v)}</text>')
    o.append(f'<line x1="{ml}" x2="{w - mr}" y1="{h - mb}" y2="{h - mb}" stroke="{MUTED}" stroke-width="1"/>')
    o.append(f'<text x="{(ml + w - mr) / 2:.0f}" y="{h - 8}" text-anchor="middle" font-size="13" fill="{INK}">{xl}</text>')
    o.append(f'<text x="14" y="{mt - 14}" font-size="13" fill="{INK}">{yl}</text>')
    return o


def doubt_scatter(doubt, err, known, tau, fam=None, w=720, h=430):
    """x: doubt score (log), y: actual error against the solver (%). known: True for pose families in the training data."""
    ml, mr, mt, mb = 56, 24, 44, 46
    d = np.clip(np.asarray(doubt, float), 0.05, None); e = np.clip(np.asarray(err, float) * 100, 0.2, None)
    x0, x1 = math.log10(0.05), math.log10(max(d.max() * 1.3, 20))
    y0, y1 = math.log10(0.2), math.log10(max(e.max() * 1.3, 100))
    xmap = lambda v: ml + (math.log10(v) - x0) / (x1 - x0) * (w - ml - mr)
    ymap = lambda v: h - mb - (math.log10(v) - y0) / (y1 - y0) * (h - mt - mb)
    xt = [v for v in (0.1, 0.3, 1, 3, 10, 30, 100) if x0 <= math.log10(v) <= x1]
    yt = [v for v in (0.3, 1, 3, 10, 30, 100, 300) if y0 <= math.log10(v) <= y1]
    o = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Doubt score against actual error" style="{FONT};max-width:{w}px">']
    o += _axes(w, h, ml, mr, mt, mb, xt, yt, xmap, ymap, 'doubt score (log scale; the gate opens below the line)', 'actual error against the solver, % (log scale)',
               xfmt=lambda v: f'{v:g}', yfmt=lambda v: f'{v:g}%')
    xtau = xmap(tau)
    o.append(f'<rect x="{ml}" y="{mt}" width="{xtau - ml:.1f}" height="{h - mt - mb}" fill="{OLIVE}" opacity="0.07"/>')
    o.append(f'<line x1="{xtau:.1f}" x2="{xtau:.1f}" y1="{mt}" y2="{h - mb}" stroke="{INK}" stroke-width="1.5" stroke-dasharray="5 4"/>')
    o.append(f'<text x="{xtau - 8:.1f}" y="{mt + 16}" text-anchor="end" font-size="12.5" fill="{INK}">answered instantly</text>')
    o.append(f'<text x="{xtau + 8:.1f}" y="{mt + 16}" font-size="12.5" fill="{INK}">sent to the solver</text>')
    y5 = ymap(5)
    o.append(f'<line x1="{ml}" x2="{w - mr}" y1="{y5:.1f}" y2="{y5:.1f}" stroke="{MUTED}" stroke-width="1" stroke-dasharray="2 4"/>')
    o.append(f'<text x="{w - mr - 4}" y="{y5 - 5:.1f}" text-anchor="end" font-size="11.5" fill="{MUTED}">5% error</text>')
    for i in np.argsort(~np.asarray(known)):          # draw never-seen on top
        x, y = xmap(d[i]), ymap(e[i])
        tip = f'{"familiar pose" if known[i] else "never-seen: " + (fam[i] if fam is not None else "")} · doubt {doubt[i]:.2f} · error {err[i] * 100:.1f}%'
        if known[i]:
            o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.6" fill="{OLIVE}" stroke="{SURFACE}" stroke-width="1.5"><title>{tip}</title></circle>')
        else:
            o.append(f'<rect x="{x - 4.6:.1f}" y="{y - 4.6:.1f}" width="9.2" height="9.2" transform="rotate(45 {x:.1f} {y:.1f})" fill="{ORANGE}" stroke="{SURFACE}" stroke-width="1.5"><title>{tip}</title></rect>')
    lx = ml + 12
    o.append(f'<circle cx="{lx}" cy="{h - mb - 34}" r="4.6" fill="{OLIVE}"/><text x="{lx + 10}" y="{h - mb - 30}" font-size="12.5" fill="{INK}">poses like the training data (held out)</text>')
    o.append(f'<rect x="{lx - 4.6}" y="{h - mb - 20.6}" width="9.2" height="9.2" transform="rotate(45 {lx} {h - mb - 16})" fill="{ORANGE}"/><text x="{lx + 10}" y="{h - mb - 12}" font-size="12.5" fill="{INK}">pose families it never trained on</text>')
    o.append('</svg>')
    return '\n'.join(o)


def clip_lines(t_solver, y_solver, t_live, y_live, sure_live, ylabel, w=720, h=330, y_base=None, label_model='learned model, every frame', label_solver='real solver, 3 frames per second'):
    ml, mr, mt, mb = 56, 24, 44, 46
    ys = np.concatenate([y_solver, y_live]); lo, hi = min(0.0, float(ys.min())), float(ys.max()) * 1.15
    xmap = lambda v: ml + v / max(float(t_live.max()), 1e-6) * (w - ml - mr)
    ymap = lambda v: h - mb - (v - lo) / (hi - lo) * (h - mt - mb)
    step = 0.2 if hi > 0.5 else 0.1
    yt = [round(i * step, 2) for i in range(int(lo / step), int(hi / step) + 1)]
    xt = list(range(0, int(t_live.max()) + 1, 5))
    o = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{ylabel} over the clip" style="{FONT};max-width:{w}px">']
    o += _axes(w, h, ml, mr, mt, mb, xt, yt, xmap, ymap, 'seconds into her clip', ylabel, yfmt=lambda v: f'{v:.1f}')
    # shade where the model was not sure
    run = None
    for i in range(len(t_live) + 1):
        ns = i < len(t_live) and not sure_live[i]
        if ns and run is None: run = i
        if (not ns) and run is not None:
            xa, xb = xmap(t_live[run]), xmap(t_live[min(i, len(t_live) - 1)])
            o.append(f'<rect x="{xa:.1f}" y="{mt}" width="{max(xb - xa, 1.5):.1f}" height="{h - mt - mb}" fill="{ORANGE}" opacity="0.16"><title>model not sure here: these frames go to the solver</title></rect>')
            run = None
    pts = ' '.join(f'{xmap(a):.1f},{ymap(b):.1f}' for a, b in zip(t_live, y_live))
    o.append(f'<polyline points="{pts}" fill="none" stroke="{OLIVE}" stroke-width="2" stroke-linejoin="round"/>')
    for a, b in zip(t_solver, y_solver):
        o.append(f'<circle cx="{xmap(a):.1f}" cy="{ymap(b):.1f}" r="3.6" fill="{INK}" stroke="{SURFACE}" stroke-width="1.5"><title>solver at {a:.1f} s: {b:.3f} m²</title></circle>')
    ly = h - mb - 64          # legend sits in the empty band at the bottom of the plot
    o.append(f'<line x1="{ml + 10}" x2="{ml + 34}" y1="{ly}" y2="{ly}" stroke="{OLIVE}" stroke-width="2"/><text x="{ml + 40}" y="{ly + 4}" font-size="12.5" fill="{INK}">{label_model}</text>')
    o.append(f'<circle cx="{ml + 22}" cy="{ly + 18}" r="3.6" fill="{INK}"/><text x="{ml + 40}" y="{ly + 22}" font-size="12.5" fill="{INK}">{label_solver}</text>')
    o.append(f'<rect x="{ml + 12}" y="{ly + 30}" width="20" height="12" fill="{ORANGE}" opacity="0.3"/><text x="{ml + 40}" y="{ly + 40}" font-size="12.5" fill="{INK}">model not sure: frame goes to the solver</text>')
    o.append('</svg>')
    return '\n'.join(o)


def learning_curve(ns, errs, base=None, w=520, h=300):
    ml, mr, mt, mb = 56, 24, 44, 46
    hi = max(max(errs), base or 0) * 1.2
    xmap = lambda v: ml + (math.log10(v) - math.log10(ns[0])) / max(math.log10(ns[-1]) - math.log10(ns[0]), 1e-6) * (w - ml - mr)
    ymap = lambda v: h - mb - v / hi * (h - mt - mb)
    yt = [v for v in (0, 2, 4, 6, 8, 10, 15, 20, 30) if v <= hi]
    o = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Error against number of solver runs" style="{FONT};max-width:{w}px">']
    o += _axes(w, h, ml, mr, mt, mb, ns, yt, xmap, ymap, 'solver runs used for training', 'error on held-out familiar poses, %', yfmt=lambda v: f'{v:g}%')
    if base:
        o.append(f'<line x1="{ml}" x2="{w - mr}" y1="{ymap(base):.1f}" y2="{ymap(base):.1f}" stroke="{MUTED}" stroke-dasharray="4 4"/><text x="{w - mr - 4}" y="{ymap(base) - 6:.1f}" text-anchor="end" font-size="12" fill="{MUTED}">rule of thumb: frontal area × constants ({base:.1f}%)</text>')
    o.append(f'<polyline points="{" ".join(f"{xmap(a):.1f},{ymap(b):.1f}" for a, b in zip(ns, errs))}" fill="none" stroke="{OLIVE}" stroke-width="2"/>')
    for a, b in zip(ns, errs):
        o.append(f'<circle cx="{xmap(a):.1f}" cy="{ymap(b):.1f}" r="4.2" fill="{OLIVE}" stroke="{SURFACE}" stroke-width="1.5"><title>{a} runs: {b:.1f}%</title></circle>')
    o.append(f'<text x="{xmap(ns[-1]) - 6:.1f}" y="{ymap(errs[-1]) - 10:.1f}" text-anchor="end" font-size="12.5" fill="{INK}">{errs[-1]:.1f}% at {ns[-1]} runs</text>')
    o.append('</svg>')
    return '\n'.join(o)
