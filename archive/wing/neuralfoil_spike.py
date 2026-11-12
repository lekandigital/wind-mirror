"""Bounded spike for the wing-agent alternative: how fast is open-source learned aerodynamics, and does it already report its own confidence?"""
import time, json
import numpy as np
import neuralfoil as nf
import aerosandbox as asb

rng = np.random.default_rng(0)
f = lambda x: float(np.asarray(x).ravel()[0])
af = asb.KulfanAirfoil('naca4412')
r = nf.get_aero_from_airfoil(af, alpha=4.0, Re=5e5, model_size='large')
print('one call keys:', sorted(r.keys())[:12])
print('naca4412 a=4 Re=5e5: CL=%.3f CD=%.4f confidence=%.3f' % (f(r['CL']), f(r['CD']), f(r['analysis_confidence'])))
# speed: many operating points on one airfoil, and many airfoils
alphas = np.linspace(-5, 15, 1000)
for size in ('xsmall', 'large'):
    nf.get_aero_from_airfoil(af, alpha=alphas, Re=5e5, model_size=size)
    t0 = time.perf_counter()
    for _ in range(5):
        nf.get_aero_from_airfoil(af, alpha=alphas, Re=5e5, model_size=size)
    dt = (time.perf_counter() - t0) / 5
    print(f'{size}: 1000 operating points in {dt*1000:.1f} ms -> {dt*1e6/1000:.1f} microseconds each (Mac CPU)')
# confidence on sane vs absurd shapes
base = af
conf = []
for scale in (0.0, 0.5, 1.0, 2.0, 4.0):
    u = base.upper_weights + scale * rng.normal(0, 0.15, base.upper_weights.shape)
    l = base.lower_weights + scale * rng.normal(0, 0.15, base.lower_weights.shape)
    a2 = asb.KulfanAirfoil(upper_weights=u, lower_weights=l, leading_edge_weight=base.leading_edge_weight, TE_thickness=base.TE_thickness)
    rr = nf.get_aero_from_airfoil(a2, alpha=4.0, Re=5e5, model_size='large')
    conf.append((scale, round(f(rr['analysis_confidence']), 3), round(f(rr['CL']), 3), round(f(rr['CD']), 4)))
print('shape noise scale -> (confidence, CL, CD):', conf)
