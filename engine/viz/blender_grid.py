"""Blender: many mannequins on a floor, clay if the model is sure, orange if it asks the solver.
blender -b -P blender_grid.py -- scene.json out.png [w h samples]"""
import bpy, sys, json, math
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
S = json.load(open(argv[0])); out = argv[1]
W = int(argv[2]) if len(argv) > 2 else 1600; Hh = int(argv[3]) if len(argv) > 3 else 900; SAMPLES = int(argv[4]) if len(argv) > 4 else 64
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'
prefs = bpy.context.preferences.addons['cycles'].preferences
for dev_type in ('OPTIX', 'CUDA'):
    try:
        prefs.compute_device_type = dev_type; prefs.get_devices()
        if any(d.type == dev_type for d in prefs.devices):
            for d in prefs.devices: d.use = d.type == dev_type
            sc.cycles.device = 'GPU'; break
    except Exception: pass
sc.cycles.samples = SAMPLES; sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = W, Hh
sc.view_settings.view_transform = 'Standard'

def srgb(h):
    h = h.lstrip('#'); c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c)
def mat(name, color, rough=0.55):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes.get('Principled BSDF'); b.inputs['Base Color'].default_value = (*color, 1); b.inputs['Roughness'].default_value = rough
    return m
BG = srgb('#EFEAE0')
w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
w.node_tree.nodes['Background'].inputs[0].default_value = (*BG, 1); w.node_tree.nodes['Background'].inputs[1].default_value = 0.55
bpy.ops.mesh.primitive_plane_add(size=400, location=(10, 0, 0)); bpy.context.object.data.materials.append(mat('floor', BG, 0.8))
M_SURE, M_ASK = mat('sure', srgb('#CFC6B2'), 0.5), mat('ask', srgb('#E08A1E'), 0.5)
D_SURE, D_ASK = mat('dsure', srgb('#6B7A2A'), 0.7), mat('dask', srgb('#E08A1E'), 0.7)

# one mesh per colour, built from arrays in one go (adding primitives one at a time gets slower with every primitive)
import numpy as np
NS, NR = 12, 6
def unit_sphere():
    v = [(0, 0, 1.0)]
    for i in range(1, NR):
        th = math.pi * i / NR
        for j in range(NS):
            ph = 2 * math.pi * j / NS
            v.append((math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), math.cos(th)))
    v.append((0, 0, -1.0))
    f = [(0, 1 + j, 1 + (j + 1) % NS) for j in range(NS)]
    for i in range(NR - 2):
        for j in range(NS):
            a_, b_ = 1 + i * NS + j, 1 + i * NS + (j + 1) % NS
            f.append((a_, a_ + NS, b_ + NS)); f.append((a_, b_ + NS, b_))
    last = len(v) - 1; base = 1 + (NR - 2) * NS
    f += [(last, base + (j + 1) % NS, base + j) for j in range(NS)]
    return np.array(v), np.array(f)
def unit_tube():
    v = [(math.cos(2 * math.pi * j / NS), math.sin(2 * math.pi * j / NS), z) for z in (-0.5, 0.5) for j in range(NS)]
    f = []
    for j in range(NS):
        a_, b_ = j, (j + 1) % NS
        f.append((a_, b_, b_ + NS)); f.append((a_, b_ + NS, a_ + NS))
    return np.array(v), np.array(f)
SV, SF = unit_sphere(); TV, TF = unit_tube()
def build(items, m, name):
    V, F, n = [], [], 0
    for it in items:
        for c in it['caps']:
            a, b_, r = np.array(c['a']), np.array(c['b']), c['r']
            d = b_ - a; L = float(np.linalg.norm(d))
            for p in ((a, b_) if L > 1e-4 else (a,)):
                V.append(SV * r + p); F.append(SF + n); n += len(SV)
            if L > 1e-4:
                R = np.array(Vector((0, 0, 1)).rotation_difference(Vector(d / L)).to_matrix())
                V.append((TV * np.array([r, r, L])) @ R.T + (a + b_) / 2); F.append(TF + n); n += len(TV)
    me = bpy.data.meshes.new(name)
    me.from_pydata(np.concatenate(V).tolist(), [], np.concatenate(F).tolist()); me.update()
    for p in me.polygons: p.use_smooth = True
    ob = bpy.data.objects.new(name, me); sc.collection.objects.link(ob); me.materials.append(m)
def discs(items, m, name):
    V, F, n = [], [], 0
    ring = np.array([(0.55 * math.cos(2 * math.pi * j / 28), 0.55 * math.sin(2 * math.pi * j / 28), 0.004) for j in range(28)])
    for it in items:
        V.append(ring + np.array([it['base'][0], it['base'][1], 0])); F.append(list(range(n, n + 28))); n += 28
    me = bpy.data.meshes.new(name); me.from_pydata(np.concatenate(V).tolist(), [], F); me.update()
    ob = bpy.data.objects.new(name, me); sc.collection.objects.link(ob); me.materials.append(m)
sure = [it for it in S['items'] if it['sure']]; ask = [it for it in S['items'] if not it['sure']]
build(sure, M_SURE, 'sure'); build(ask, M_ASK, 'ask'); discs(sure, D_SURE, 'dsure'); discs(ask, D_ASK, 'dask')

def area(loc, size, power, rot):
    l = bpy.data.lights.new('a', 'AREA'); l.size = size; l.energy = power
    o = bpy.data.objects.new('a', l); o.location = loc; o.rotation_euler = rot; sc.collection.objects.link(o)
depth = S['nr'] * 2.3
area((-6, -8, 14), 14, 2600, (math.radians(35), math.radians(-25), 0)); area((depth, 10, 10), 12, 800, (math.radians(-50), 0, 0))
cam = bpy.data.cameras.new('c'); co = bpy.data.objects.new('c', cam); sc.collection.objects.link(co); sc.camera = co
loc = Vector((-9.5, 0.0, 7.2)); tgt = Vector((depth * 0.36, 0, 0.6))
co.location = loc; co.rotation_euler = (tgt - loc).to_track_quat('-Z', 'Y').to_euler(); cam.lens = 30
sc.render.filepath = out; sc.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(write_still=True); print('rendered', out)
