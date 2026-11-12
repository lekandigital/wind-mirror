"""Blender: render the capsule mannequin in the tunnel with streamlines.  blender -b -P blender_scene.py -- scene.json out.png [w h samples cam]"""
import bpy, sys, json, math
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index('--') + 1:]
scene_path, out_path = argv[0], argv[1]
W = int(argv[2]) if len(argv) > 2 else 1200
Hh = int(argv[3]) if len(argv) > 3 else 1350
SAMPLES = int(argv[4]) if len(argv) > 4 else 96
CAM = argv[5] if len(argv) > 5 else 'front34'
S = json.load(open(scene_path))

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'
prefs = bpy.context.preferences.addons['cycles'].preferences
for dev_type in ('OPTIX', 'CUDA'):
    try:
        prefs.compute_device_type = dev_type
        prefs.get_devices()
        if any(d.type == dev_type for d in prefs.devices):
            for d in prefs.devices:
                d.use = d.type == dev_type
            sc.cycles.device = 'GPU'
            break
    except Exception as e:
        pass
sc.cycles.samples = SAMPLES
sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = W, Hh
sc.render.film_transparent = False
sc.view_settings.view_transform = 'Standard'
sc.view_settings.look = 'None'


def mat(name, color, rough=0.55, emit=0.0, alpha=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (*color, 1)
    b.inputs['Roughness'].default_value = rough
    if emit > 0:
        b.inputs['Emission Color'].default_value = (*color, 1)
        b.inputs['Emission Strength'].default_value = emit
    return m


def lerp(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def srgb(h):
    h = h.lstrip('#')
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c)

# palette: cream studio, olive flow, amber-to-vermilion where the air is slow (the wake)
BG = srgb('#EFEAE0'); CLAY = srgb('#E9E2D3'); OLIVE = srgb('#6B7A2A'); AMBER = srgb('#E8A21A'); RED = srgb('#D2401E'); DEEP = srgb('#3F4A1A')

# world
w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
w.node_tree.nodes['Background'].inputs[0].default_value = (*BG, 1)
w.node_tree.nodes['Background'].inputs[1].default_value = 0.62

# floor
bpy.ops.mesh.primitive_plane_add(size=60, location=(2, 0, 0))
floor = bpy.context.object
floor.data.materials.append(mat('floor', BG, rough=0.7))

# body: one mesh per capsule, coloured by that part's share of the drag (darker = more drag) if given
part_drag = S.get('part_drag')
names = S['parts']
mx = max(part_drag.values()) if part_drag else 1.0
pmats = []
for i, n in enumerate(names):
    t = (max(part_drag[n], 0) / mx) ** 0.8 if part_drag else 0.0
    pmats.append(mat('part_' + n, lerp(CLAY, RED, 0.85 * t) if S.get('colour_parts', True) else CLAY, rough=0.5))
for c in S['capsules']:
    a, b, r = Vector(c['a']), Vector(c['b']), c['r']
    d = b - a
    L = d.length
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=32, ring_count=16, location=a)
    objs = [bpy.context.object]
    if L > 1e-4:
        bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=32, ring_count=16, location=b)
        objs.append(bpy.context.object)
        bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=L, vertices=32, location=(a + b) / 2)
        cyl = bpy.context.object
        cyl.rotation_mode = 'QUATERNION'
        cyl.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
        objs.append(cyl)
    for o in objs:
        o.data.materials.append(pmats[c['part']])
        for p in o.data.polygons:
            p.use_smooth = True

# streamlines, split into runs by speed bin so each bin can have its own colour
NB = 8
def bin_color(k):
    t = k / (NB - 1)                      # 0 = stalled air, 1 = fast
    if t < 0.5:
        return lerp(RED, AMBER, t / 0.5)
    return lerp(AMBER, OLIVE, (t - 0.5) / 0.5) if t < 0.8 else lerp(OLIVE, DEEP, (t - 0.8) / 0.2)
curves = []
for k in range(NB):
    cu = bpy.data.curves.new(f'flow{k}', 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = float(S.get('tube', 0.0034))
    cu.bevel_resolution = 2
    ob = bpy.data.objects.new(f'flow{k}', cu)
    sc.collection.objects.link(ob)
    cu.materials.append(mat(f'flowm{k}', bin_color(k), rough=0.6, emit=0.35))
    curves.append(cu)
for ln in S['lines']:
    P, Sp = ln['p'], ln['s']
    bins = [min(NB - 1, max(0, int(s / 1.25 * NB))) for s in Sp]
    i = 0
    while i < len(P) - 1:
        j = i
        while j < len(P) - 1 and bins[j] == bins[i]:
            j += 1
        seg = P[i:j + 1]
        if len(seg) >= 2:
            sp = curves[bins[i]].splines.new('POLY')
            sp.points.add(len(seg) - 1)
            for q, pt in zip(sp.points, seg):
                q.co = (pt[0], pt[1], pt[2], 1)
        i = j

# lights
def area(loc, size, power, rot):
    l = bpy.data.lights.new('a', 'AREA'); l.size = size; l.energy = power
    o = bpy.data.objects.new('a', l); o.location = loc; o.rotation_euler = rot
    sc.collection.objects.link(o)
area((-3.5, -2.5, 4.5), 4.0, 380, (math.radians(35), math.radians(-25), 0))
area((1.0, 3.5, 3.0), 3.0, 120, (math.radians(-60), 0, 0))

# camera
cam = bpy.data.cameras.new('c'); co = bpy.data.objects.new('c', cam); sc.collection.objects.link(co); sc.camera = co
views = dict(front34=((-3.0, -2.5, 1.45), (0.35, 0.0, 0.93), 42), side=((0.75, -5.6, 1.15), (0.75, 0, 0.95), 40), front=((-5.2, -0.6, 1.3), (0.2, 0, 0.92), 40),
             wide=((-3.4, -4.6, 2.2), (0.9, 0.0, 0.85), 34), hero=((-3.5, -3.0, 1.3), (1.9, 0.05, 1.2), 38))
loc, tgt, lens = views[CAM]
co.location = loc
co.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
cam.lens = lens
cam.sensor_width = 36
sc.render.filepath = out_path
sc.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(write_still=True)
print('rendered', out_path)
