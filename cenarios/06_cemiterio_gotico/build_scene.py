"""
Cenário 06 — Cemitério gótico e decadente (estilo Tim Burton)

70×70 m: portão de ferro forjado com espirais, estrada de calçada em S a subir até
um mausoléu principal numa colina, mausoléus altos e estreitos, ~200 campas tortas
e partidas, anjos chorões e figuras encapuzadas, candeeiros vitorianos escassos
(uns acesos, um a piscar, um morto, um tombado), árvores negras com ramos em espiral,
corvos, erva seca e nevoeiro baixo. Noite (luar pálido atrás das nuvens) e dia
(céu encoberto) — ambos inquietantes.

Uso (dentro do Blender):
    blender -b -P build_scene.py -- --out cemiterio_gotico.blend
Uso (módulo bpy via pip):
    python build_scene.py --out cemiterio_gotico.blend --render previews --samples 64
"""

import argparse
import math
import os
import random
import sys

import bpy  # noqa: I001 — bpy tem de ser importado antes de bmesh/mathutils
import bmesh
import numpy as np
from mathutils import Euler, Matrix, Vector, noise

SEED = 1993
rng = random.Random(SEED)

HALF = 35.0                                 # 70 × 70 m
GATE_Y = -33.0
MAUSO_MAIN = Vector((0.0, 28.5, 0.0))       # mausoléu principal no alto da colina
HILL_TREE = Vector((-11.5, 27.0, 0.0))      # a árvore retorcida da colina
MOON_DIR = Vector((-0.35, -0.8, -0.5)).normalized()   # luar fraco, vindo de trás, atrás das nuvens
ROAD_CTRL = [(0.0, -40.0), (0.0, -30.0), (-1.5, -22.0), (-7.0, -14.0), (-5.5, -5.0), (2.0, 2.0), (7.0, 10.0),
             (5.0, 17.0), (0.5, 22.0), (0.0, 25.8)]
ROAD_W = 3.2


def catmull(pts, n=12):
    out = []
    P = [pts[0]] + pts + [pts[-1]]
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = (Vector((*P[j], 0)) for j in (i - 1, i, i + 1, i + 2))
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(Vector((*pts[-1], 0)))
    return out


ROAD = catmull(ROAD_CTRL, 14)


def road_dist(x, y):
    best = 1e9
    p = Vector((x, y, 0))
    for a, b in zip(ROAD[:-1], ROAD[1:]):
        ab = b - a
        t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-9)))
        d = (p - (a + ab * t)).length
        if d < best:
            best = d
    return best


def ground_height(x, y):
    h = noise.noise(Vector((x * 0.06, y * 0.06, 0.4))) * 0.7
    h += noise.noise(Vector((x * 0.3, y * 0.3, 2.2))) * 0.12
    h += 3.4 * math.exp(-((x / 15.0) ** 2 + ((y - 30.0) / 9.5) ** 2))   # a colina do mausoléu
    return h

def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="cemiterio_gotico.blend")
    p.add_argument("--render", default="")
    p.add_argument("--samples", type=int, default=64)
    p.add_argument("--res", type=int, default=1280)
    p.add_argument("--only", default="")
    return p.parse_args(argv)


def collection(name, parent=None):
    col = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(col)
    return col


def new_object(name, data, col):
    obj = bpy.data.objects.new(name, data)
    col.objects.link(obj)
    return obj


def look_at_rotation(loc, target):
    return (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()



def pointed_arch(w, zs, za, n=16):
    """Perfil de arco ogival de meia-largura w: lista (x, z) da direita para a esquerda."""
    h = za - zs
    c = (h * h - w * w) / (2 * w)
    r = w + c
    phi_a = math.acos(c / r)
    right = [(-c + r * math.cos(phi_a * i / n), zs + r * math.sin(phi_a * i / n)) for i in range(n + 1)]
    left = [(-x, z) for x, z in reversed(right[:-1])]
    return right + left


# ---------------------------------------------------------------------------
# Utilitários comuns
# ---------------------------------------------------------------------------
class Builder:
    def __init__(self):
        self.bm = bmesh.new()
        self.rand = self.bm.faces.layers.float.new("rand")
        self.uv = self.bm.loops.layers.uv.new("UVMap")

    def _faces(self, verts):
        return {f for v in verts for f in v.link_faces}

    def _tag(self, faces, mat, value=None):
        value = rng.random() if value is None else value
        for f in faces:
            f[self.rand] = value
            f.material_index = mat

    def box(self, center, axes, dims, mat=0, rand=None, M=None):
        u, v, w = (Vector(a).normalized() for a in axes)
        if u.cross(v).dot(w) < 0:
            w = -w
        center = Vector(center)
        if M is not None:
            rot = M.to_3x3().normalized()
            u, v, w = rot @ u, rot @ v, rot @ w
            center = M @ center
        m = Matrix((
            (u.x * dims[0], v.x * dims[1], w.x * dims[2], center.x),
            (u.y * dims[0], v.y * dims[1], w.y * dims[2], center.y),
            (u.z * dims[0], v.z * dims[1], w.z * dims[2], center.z),
            (0, 0, 0, 1)))
        res = bmesh.ops.create_cube(self.bm, size=1.0, matrix=m)
        faces = self._faces(res["verts"])
        rv = rng.random() if rand is None else rand
        self._tag(faces, mat, rv)
        # UV em metros ao longo do eixo mais comprido (veio da madeira / pedra)
        ax = (u, v, w)
        longest = max(range(3), key=lambda i: dims[i])
        for f in faces:
            f.normal_update()
            o = [i for i in range(3) if i != longest and abs(f.normal.dot(ax[i])) < 0.5]
            for loop in f.loops:
                d = loop.vert.co - center
                loop[self.uv].uv = (d.dot(ax[longest]) + rv * 7, (d.dot(ax[o[0]]) if o else 0) + rv * 3)
        return faces

    def cylinder(self, p0, p1, r0, r1, segs=12, mat=0, rand=None, cap=True):
        p0, p1 = Vector(p0), Vector(p1)
        d = p1 - p0
        q = d.to_track_quat("Z", "Y")
        m = Matrix.Translation((p0 + p1) / 2) @ q.to_matrix().to_4x4()
        res = bmesh.ops.create_cone(self.bm, cap_ends=cap, cap_tris=False, segments=segs,
                                    radius1=r0, radius2=r1, depth=d.length, matrix=m)
        faces = self._faces(res["verts"])
        self._tag(faces, mat, rand)
        inv = m.inverted()
        for f in faces:
            for loop in f.loops:
                lc = inv @ loop.vert.co
                loop[self.uv].uv = (math.atan2(lc.y, lc.x) * max(r0, r1), lc.z)
        return faces

    def ico(self, center, radius, scale=(1, 1, 1), subdiv=1, jitter=0.25, mat=0, rot=(0, 0, 0)):
        m = Matrix.Translation(center) @ Euler(rot).to_matrix().to_4x4() @ Matrix.Diagonal((*scale, 1))
        res = bmesh.ops.create_icosphere(self.bm, subdivisions=subdiv, radius=radius, matrix=m)
        c = Vector(center)
        for vv in res["verts"]:
            vv.co = c + (vv.co - c) * (1 + (rng.random() - 0.5) * jitter)
        faces = self._faces(res["verts"])
        self._tag(faces, mat)
        return faces

    def prism(self, pts, to3d, depth_vec, mat=0, rand=None):
        """Extruda um polígono 2D (s, z). to3d(s, z) -> Vector; depth_vec: espessura."""
        vs = [self.bm.verts.new(to3d(s, z)) for s, z in pts]
        f = self.bm.faces.new(vs)
        ext = bmesh.ops.extrude_face_region(self.bm, geom=[f])
        new_v = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
        bmesh.ops.translate(self.bm, verts=new_v, vec=Vector(depth_vec))
        faces = self._faces(vs + new_v)
        bmesh.ops.recalc_face_normals(self.bm, faces=list(faces))
        self._tag(faces, mat, rand)
        return faces

    def ring(self, center, rot, R, r, stretch=1.0, segs=12, sides=6, mat=0):
        """Elo de corrente (toro esticado ao longo de Z local)."""
        rot = Matrix(rot) if not isinstance(rot, Matrix) else rot
        grid = []
        for i in range(segs):
            a = 2 * math.pi * i / segs
            row = []
            for j in range(sides):
                b = 2 * math.pi * j / sides
                x = (R + r * math.cos(b)) * math.cos(a)
                z = (R + r * math.cos(b)) * math.sin(a) * stretch
                y = r * math.sin(b)
                row.append(self.bm.verts.new(Vector(center) + rot @ Vector((x, y, z))))
            grid.append(row)
        faces = []
        for i in range(segs):
            for j in range(sides):
                a, b_ = grid[i][j], grid[(i + 1) % segs][j]
                c, d = grid[(i + 1) % segs][(j + 1) % sides], grid[i][(j + 1) % sides]
                faces.append(self.bm.faces.new((a, b_, c, d)))
        self._tag(faces, mat)
        return faces

    def uv_project(self, faces, fn):
        for f in faces:
            for loop in f.loops:
                loop[self.uv].uv = fn(loop.vert.co)

    def to_object(self, name, col, materials, smooth=False):
        me = bpy.data.meshes.new(name)
        self.bm.normal_update()
        self.bm.to_mesh(me)
        self.bm.free()
        for mat in materials:
            me.materials.append(mat)
        if smooth:
            me.shade_smooth()
        return new_object(name, me, col)


def sock(node, ident, out=False):
    coll = node.outputs if out else node.inputs
    for s in coll:
        if s.identifier == ident:
            return s
    return coll[ident]


class Mat:
    def __init__(self, name):
        self.mat = bpy.data.materials.new(name)
        self.mat.use_nodes = True
        self.nt = self.mat.node_tree
        self.nt.nodes.clear()
        self.x = -1400
        self.out = self.node("ShaderNodeOutputMaterial", loc=(400, 0))
        self.bsdf = self.node("ShaderNodeBsdfPrincipled", loc=(100, 0))
        self.link(self.bsdf.outputs[0], self.out.inputs["Surface"])

    def node(self, kind, loc=None, **props):
        n = self.nt.nodes.new(kind)
        for k, v in props.items():
            setattr(n, k, v)
        if loc is None:
            loc = (self.x, rng.uniform(-600, 600))
            self.x += 60
        n.location = loc
        return n

    def link(self, a, b):
        self.nt.links.new(a, b)

    def texcoord(self):
        if not hasattr(self, "_tc"):
            self._tc = self.node("ShaderNodeTexCoord")
        return self._tc

    def attr(self, name):
        return self.node("ShaderNodeAttribute", attribute_name=name)

    def noise(self, vec, scale, detail=4.0, rough=0.55):
        n = self.node("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        if vec is not None:
            self.link(vec, n.inputs["Vector"])
        return n

    def ramp(self, fac, stops):
        n = self.node("ShaderNodeValToRGB")
        els = n.color_ramp.elements
        while len(els) < len(stops):
            els.new(0.5)
        for el, (pos, col) in zip(els, stops):
            el.position = pos
            el.color = (*col, 1.0)
        self.link(fac, n.inputs["Fac"])
        return n

    def mix(self, fac, a, b, blend="MIX"):
        n = self.node("ShaderNodeMix", data_type="RGBA", blend_type=blend)
        self._set(sock(n, "Factor_Float"), fac)
        self._set(sock(n, "A_Color"), a)
        self._set(sock(n, "B_Color"), b)
        return sock(n, "Result_Color", out=True)

    def mixf(self, fac, a, b):
        n = self.node("ShaderNodeMix", data_type="FLOAT")
        self._set(sock(n, "Factor_Float"), fac)
        self._set(sock(n, "A_Float"), a)
        self._set(sock(n, "B_Float"), b)
        return sock(n, "Result_Float", out=True)

    def math(self, op, a, b=None):
        n = self.node("ShaderNodeMath", operation=op)
        self._set(n.inputs[0], a)
        if b is not None:
            self._set(n.inputs[1], b)
        return n.outputs[0]

    def maprange(self, val, a, b, c=0.0, d=1.0):
        n = self.node("ShaderNodeMapRange", clamp=True)
        self._set(n.inputs["Value"], val)
        n.inputs["From Min"].default_value = a
        n.inputs["From Max"].default_value = b
        n.inputs["To Min"].default_value = c
        n.inputs["To Max"].default_value = d
        return n.outputs["Result"]

    def _set(self, s, v):
        if isinstance(v, bpy.types.NodeSocket):
            self.link(v, s)
        elif isinstance(v, (tuple, list)):
            s.default_value = (*v, 1.0) if len(v) == 3 and len(s.default_value) == 4 else v
        else:
            s.default_value = v

    def bump(self, height, strength=0.3, distance=0.02):
        n = self.node("ShaderNodeBump")
        n.inputs["Strength"].default_value = strength
        n.inputs["Distance"].default_value = distance
        self._set(n.inputs["Height"], height)
        return n.outputs["Normal"]

    def set(self, name, v):
        self._set(self.bsdf.inputs[name], v)


def sep_z(m):
    geo = m.node("ShaderNodeNewGeometry")
    sep = m.node("ShaderNodeSeparateXYZ")
    m.link(geo.outputs["Position"], sep.inputs[0])
    return sep.outputs["Z"]


def mat_wood(name, dark=1.0):
    m = Mat(name)
    tc = m.texcoord()
    rnd = m.attr("rand").outputs["Fac"]
    mp = m.node("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.35, 9.0, 9.0)
    m.link(tc.outputs["UV"], mp.inputs["Vector"])
    grain = m.noise(mp.outputs["Vector"], 3.0, 12.0, 0.7)
    wave = m.node("ShaderNodeTexWave", wave_type="BANDS", bands_direction="Y")
    wave.inputs["Scale"].default_value = 1.2
    wave.inputs["Distortion"].default_value = 6.0
    wave.inputs["Detail"].default_value = 6.0
    m.link(mp.outputs["Vector"], wave.inputs["Vector"])
    g = m.math("ADD", m.math("MULTIPLY", wave.outputs["Fac"], 0.5), m.math("MULTIPLY", grain.outputs["Fac"], 0.5))
    k = 1.0 / dark
    base = m.ramp(g, [(0.25, (0.028 * k, 0.021 * k, 0.016 * k)), (0.6, (0.075 * k, 0.058 * k, 0.043 * k)),
                      (0.9, (0.13 * k, 0.105 * k, 0.08 * k))])
    tint = m.ramp(rnd, [(0.0, (0.75, 0.75, 0.78)), (0.5, (1.0, 0.95, 0.9)), (1.0, (1.15, 1.05, 0.95))])
    col = m.mix(1.0, base.outputs["Color"], tint.outputs["Color"], "MULTIPLY")
    rot = m.noise(tc.outputs["Object"], 3.0, 6.0, 0.65)
    col = m.mix(m.math("MULTIPLY", m.maprange(rot.outputs["Fac"], 0.55, 0.7), 0.7), col, (0.015, 0.014, 0.012))
    m.set("Base Color", col)
    m.set("Roughness", 0.85)
    fine = m.noise(mp.outputs["Vector"], 40.0, 4.0, 0.6)
    m.set("Normal", m.bump(m.math("ADD", g, m.math("MULTIPLY", fine.outputs["Fac"], 0.4)), 0.4, 0.01))
    return m.mat


def mat_simple(name, color, rough=0.8, metal=0.0, noise_scale=0.0, bump=0.0):
    m = Mat(name)
    if noise_scale:
        n = m.noise(m.texcoord().outputs["Object"], noise_scale, 6.0, 0.6)
        c = m.ramp(n.outputs["Fac"], [(0.3, tuple(v * 0.55 for v in color)), (0.8, color)])
        m.set("Base Color", c.outputs["Color"])
        if bump:
            m.set("Normal", m.bump(n.outputs["Fac"], bump, 0.01))
    else:
        m.set("Base Color", color)
    m.set("Roughness", rough)
    m.set("Metallic", metal)
    return m.mat


def light(name, kind, col, loc, energy, color, **kw):
    ld = bpy.data.lights.new(name, kind)
    ld.energy = energy
    ld.color = color
    for k, v in kw.items():
        setattr(ld, k, v)
    ob = new_object(name, ld, col)
    ob.location = loc
    return ob


def try_set(node, name, value):
    want_vec = isinstance(value, (tuple, list))
    for s in node.inputs:
        if s.name != name:
            continue
        if want_vec == (s.type in ("RGBA", "VECTOR")):
            dv = s.default_value
            if want_vec and len(dv) != len(value):
                value = tuple(value) + (1.0,) * (len(dv) - len(value))
            s.default_value = value
            return True
    attr = name.lower().replace(" ", "_")
    if hasattr(node, attr):
        setattr(node, attr, value)
        return True
    return False



# ---------------------------------------------------------------------------
# Materiais
# ---------------------------------------------------------------------------
def mat_bark():
    """Casca escura e rugosa, líquenes pálidos e musgo junto à base."""
    m = Mat("M_Casca_Arvore")
    obj = m.texcoord().outputs["Object"]
    mp = m.node("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (7.0, 7.0, 0.9)
    m.link(obj, mp.inputs["Vector"])
    ridges = m.node("ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE")
    ridges.inputs["Scale"].default_value = 3.0
    m.link(mp.outputs["Vector"], ridges.inputs["Vector"])
    fine = m.noise(mp.outputs["Vector"], 12.0, 10.0, 0.7)
    rid = m.maprange(ridges.outputs["Distance"], 0.0, 0.08)
    base = m.ramp(fine.outputs["Fac"], [(0.3, (0.018, 0.015, 0.013)), (0.7, (0.075, 0.066, 0.056))]).outputs["Color"]
    col = m.mix(m.math("SUBTRACT", 1.0, rid), base, (0.006, 0.005, 0.005))
    world = m.texcoord().outputs["Object"]
    lich = m.maprange(m.noise(world, 2.5, 8.0, 0.7).outputs["Fac"], 0.6, 0.68)
    col = m.mix(m.math("MULTIPLY", lich, 0.8), col, (0.2, 0.22, 0.18))
    z = sep_z(m)
    moss = m.math("MULTIPLY", m.maprange(z, 0.0, 1.4, 1.0, 0.0),
                  m.maprange(m.noise(world, 4.0, 6.0, 0.6).outputs["Fac"], 0.4, 0.6))
    col = m.mix(moss, col, (0.02, 0.035, 0.012))
    m.set("Base Color", col)
    m.set("Roughness", 0.92)
    h = m.math("ADD", rid, m.math("MULTIPLY", fine.outputs["Fac"], 0.5))
    m.set("Normal", m.bump(h, 0.9, 0.03))
    return m.mat


def mat_volume_fog(name, ground_density, haze, color, height=2.6, anisotropy=0.25, drift=True):
    """Névoa densa junto ao chão que se desfaz com a altura, com manchas e deriva lenta."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new
    out = N("ShaderNodeOutputMaterial")
    vol = N("ShaderNodeVolumePrincipled")
    vol.inputs["Color"].default_value = (*color, 1)
    vol.inputs["Anisotropy"].default_value = anisotropy
    geo = N("ShaderNodeNewGeometry")
    sep = N("ShaderNodeSeparateXYZ")
    L(geo.outputs["Position"], sep.inputs[0])
    hz = N("ShaderNodeMapRange")
    hz.inputs["From Min"].default_value = 0.0
    hz.inputs["From Max"].default_value = height
    hz.inputs["To Min"].default_value = 1.0
    hz.inputs["To Max"].default_value = 0.0
    L(sep.outputs["Z"], hz.inputs["Value"])
    pw = N("ShaderNodeMath")
    pw.operation = "POWER"
    L(hz.outputs["Result"], pw.inputs[0])
    pw.inputs[1].default_value = 1.8
    mp = N("ShaderNodeMapping")
    mp.name = "Deriva_Nevoa"
    L(geo.outputs["Position"], mp.inputs["Vector"])
    mp.inputs["Scale"].default_value = (0.12, 0.12, 0.35)
    nz = N("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 1.0
    nz.inputs["Detail"].default_value = 4.0
    nz.inputs["Roughness"].default_value = 0.6
    L(mp.outputs["Vector"], nz.inputs["Vector"])
    patch = N("ShaderNodeMapRange")
    patch.inputs["From Min"].default_value = 0.3
    patch.inputs["From Max"].default_value = 0.7
    patch.inputs["To Min"].default_value = 0.25
    patch.inputs["To Max"].default_value = 1.4
    L(nz.outputs["Fac"], patch.inputs["Value"])
    mul = N("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    L(pw.outputs[0], mul.inputs[0])
    L(patch.outputs["Result"], mul.inputs[1])
    dens = N("ShaderNodeMath")
    dens.operation = "MULTIPLY_ADD"
    L(mul.outputs[0], dens.inputs[0])
    dens.inputs[1].default_value = ground_density
    dens.inputs[2].default_value = haze
    L(dens.outputs[0], vol.inputs["Density"])
    L(vol.outputs[0], out.inputs["Volume"])
    if drift:   # a névoa desliza devagar ao longo da animação
        mp.inputs["Location"].default_value = (0, 0, 0)
        mp.inputs["Location"].keyframe_insert("default_value", frame=1)
        mp.inputs["Location"].default_value = (0.35, 0.1, 0.05)
        mp.inputs["Location"].keyframe_insert("default_value", frame=240)
    return mat


def spline(cu, pts, radii):
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for i, (p, r) in enumerate(zip(pts, radii)):
        sp.points[i].co = (*p, 1)
        sp.points[i].radius = r
    return sp


def grow(start, direction, length, r0, r1, n, gnarl, r_, droop=0.0, up_bias=0.0):
    """Polilinha torta: direção vai derivando com ruído (galho retorcido)."""
    pts, radii = [Vector(start)], [r0]
    d = Vector(direction).normalized()
    step = length / n
    for i in range(1, n + 1):
        t = i / n
        jitter = Vector((r_.gauss(0, 1), r_.gauss(0, 1), r_.gauss(0, 1))) * gnarl
        d = (d + jitter + Vector((0, 0, up_bias - droop * t))).normalized()
        pts.append(pts[-1] + d * step)
        radii.append(r0 + (r1 - r0) * t)
    return pts, radii


def make_tree(name, col, bark, seed, height, trunk_r, twist=0.12, lean=0.12):
    r_ = random.Random(seed)
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 1.0
    cu.bevel_resolution = 2
    cu.use_fill_caps = True
    cu.resolution_u = 2
    lean_dir = Vector((r_.uniform(-1, 1), r_.uniform(-1, 1), 0)).normalized() * lean
    trunk, tr = grow((0, 0, -0.4), Vector((0, 0, 1)) + lean_dir, height, trunk_r, trunk_r * 0.12, 18, twist, r_, up_bias=0.08)
    spline(cu, trunk, tr)
    # galhos
    for i in range(6, len(trunk) - 1):
        if r_.random() > 0.55:
            continue
        t = i / len(trunk)
        az = r_.uniform(0, 2 * math.pi)
        d = Vector((math.cos(az), math.sin(az), r_.uniform(0.1, 0.9)))
        ln = height * (1 - t) * r_.uniform(0.35, 0.6) + 0.8
        br, brr = grow(trunk[i], d, ln, tr[i] * 0.55, 0.012, 9, 0.35, r_, droop=r_.uniform(0.0, 0.25))
        spline(cu, br, brr)
        for j in range(3, len(br) - 1):
            if r_.random() > 0.45:
                continue
            az2 = r_.uniform(0, 2 * math.pi)
            d2 = (br[j + 1] - br[j]).normalized() + Vector((math.cos(az2), math.sin(az2), r_.uniform(-0.2, 0.6))) * 0.9
            ln2 = ln * r_.uniform(0.25, 0.45)
            tw, twr = grow(br[j], d2, ln2, brr[j] * 0.6, 0.006, 6, 0.45, r_)
            spline(cu, tw, twr)
            for k in range(2, len(tw) - 1):
                if r_.random() > 0.5:
                    continue
                d3 = (tw[k + 1] - tw[k]).normalized() + Vector((r_.gauss(0, 1), r_.gauss(0, 1), r_.gauss(0.3, 1))) * 0.8
                tt, ttr = grow(tw[k], d3, ln2 * 0.35, twr[k] * 0.6, 0.004, 4, 0.5, r_)
                spline(cu, tt, ttr)
    # raízes expostas
    nroots = r_.randint(6, 9)
    for k in range(nroots):
        az = 2 * math.pi * k / nroots + r_.uniform(-0.3, 0.3)
        reach = r_.uniform(1.4, 3.2) * (trunk_r / 0.4)
        z0 = r_.uniform(0.35, 0.9)
        pts, rad = [], []
        n = 10
        for i in range(n + 1):
            t = i / n
            rr = reach * t
            wob = Vector((r_.gauss(0, 0.05), r_.gauss(0, 0.05), 0))
            z = z0 * (1 - t) ** 1.6 + 0.18 * math.sin(math.pi * min(1, t * 1.3)) - 0.25 * t ** 3
            pts.append(Vector((math.cos(az) * (rr + 0.1), math.sin(az) * (rr + 0.1), z)) + wob)
            rad.append(trunk_r * 0.55 * (1 - t) + 0.02)
        spline(cu, pts, rad)
    cu.materials.append(bark)
    return new_object(name, cu, col)


def make_leaf_mesh(name, length, width, curl, seed):
    """Folha seca amarrotada, deitada no plano YZ (a normal é +X, como as partículas esperam)."""
    r_ = random.Random(seed)
    n = 8
    verts, faces = [], []
    for i in range(n + 1):
        t = i / n
        w = math.sin(math.pi * t) ** 0.7 * width * 0.5
        for s in (-1, 0, 1):
            y = s * w
            z = (t - 0.5) * length
            x = curl * (y / max(width, 1e-4)) ** 2 * width + 0.3 * curl * t * t * length + r_.uniform(-0.002, 0.002)
            if s == 0:
                x -= 0.004
            verts.append((x, y, z))
    for i in range(n):
        a = i * 3
        faces += [(a, a + 1, a + 4, a + 3), (a + 1, a + 2, a + 5, a + 4)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    uv = me.uv_layers.new(name="UVMap")
    uvs = []
    for f in me.polygons:
        for li in f.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            uvs += [v.y / width + 0.5, v.z / length + 0.5]
    uv.data.foreach_set("uv", uvs)
    me.shade_smooth()
    return me


def mat_emit(name, color, strength):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return mat


def iter_fcurves(action):
    fcs = list(getattr(action, "fcurves", []) or [])
    if not fcs:
        for layer in getattr(action, "layers", []):
            for strip in layer.strips:
                for cb in strip.channelbags:
                    fcs += list(cb.fcurves)
    return fcs



# ---------------------------------------------------------------------------
# Materiais
# ---------------------------------------------------------------------------
def mat_grave_stone(name, tone=1.0):
    """Pedra de campa: gasta, manchas escuras de chuva, líquen claro, musgo em baixo."""
    m = Mat(name)
    obj = m.texcoord().outputs["Object"]
    rnd = m.node("ShaderNodeObjectInfo").outputs["Random"]
    k = tone
    base = m.ramp(rnd, [(0.0, (0.1 * k, 0.1 * k, 0.1 * k)), (0.5, (0.2 * k, 0.195 * k, 0.185 * k)), (1.0, (0.28 * k, 0.27 * k, 0.25 * k))])
    n = m.noise(obj, 5.0, 8.0, 0.65)
    col = m.mix(1.0, base.outputs["Color"], m.ramp(n.outputs["Fac"], [(0.3, (0.5, 0.5, 0.5)), (0.7, (1, 1, 1))]).outputs["Color"],
                "MULTIPLY")
    smp = m.node("ShaderNodeMapping")
    smp.inputs["Scale"].default_value = (8.0, 8.0, 0.8)
    m.link(obj, smp.inputs["Vector"])
    streak = m.maprange(m.noise(smp.outputs["Vector"], 3.0, 3.0, 0.5).outputs["Fac"], 0.5, 0.7)
    col = m.mix(m.math("MULTIPLY", streak, 0.7), col, (0.02, 0.02, 0.022))
    lich = m.maprange(m.noise(obj, 9.0, 6.0, 0.7).outputs["Fac"], 0.64, 0.7)
    col = m.mix(m.math("MULTIPLY", lich, 0.8), col, (0.38, 0.4, 0.33))
    z = sep_z(m)
    moss = m.math("MULTIPLY", m.maprange(z, 0.0, 0.5, 1.0, 0.0), m.maprange(m.noise(obj, 4.0, 6.0, 0.6).outputs["Fac"], 0.4, 0.62))
    col = m.mix(moss, col, (0.02, 0.035, 0.012))
    m.set("Base Color", col)
    m.set("Roughness", 0.9)
    chips = m.noise(obj, 22.0, 8.0, 0.7)
    m.set("Normal", m.bump(m.math("ADD", chips.outputs["Fac"], m.math("MULTIPLY", n.outputs["Fac"], 0.5)), 0.7, 0.02))
    return m.mat


def mat_cobbles():
    m = Mat("M_Calcada_Estrada")
    obj = m.texcoord().outputs["Object"]
    v = m.node("ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE")
    v.inputs["Scale"].default_value = 5.5
    m.link(obj, v.inputs["Vector"])
    cell = m.node("ShaderNodeTexVoronoi")
    cell.inputs["Scale"].default_value = 5.5
    m.link(obj, cell.inputs["Vector"])
    sp = m.node("ShaderNodeSeparateColor")
    m.link(cell.outputs["Color"], sp.inputs[0])
    stone = m.ramp(sp.outputs[0], [(0.0, (0.05, 0.05, 0.05)), (1.0, (0.16, 0.155, 0.15))]).outputs["Color"]
    joint = m.maprange(v.outputs["Distance"], 0.0, 0.06, 1.0, 0.0)
    mud = m.ramp(m.noise(obj, 3.0, 6.0, 0.6).outputs["Fac"], [(0.3, (0.02, 0.016, 0.012)), (0.7, (0.05, 0.04, 0.03))]).outputs["Color"]
    col = m.mix(joint, stone, mud)
    moss = m.maprange(m.noise(obj, 1.3, 6.0, 0.6).outputs["Fac"], 0.55, 0.7)
    col = m.mix(m.math("MULTIPLY", moss, 0.7), col, (0.02, 0.03, 0.01))
    puddle = m.maprange(m.noise(obj, 0.5, 4.0, 0.5).outputs["Fac"], 0.62, 0.66)
    m.set("Base Color", col)
    m.set("Roughness", m.mixf(puddle, m.mixf(joint, 0.55, 0.95), 0.05))
    h = m.math("SUBTRACT", m.math("POWER", m.maprange(v.outputs["Distance"], 0.0, 0.25), 0.5), 0.0)
    h = m.math("MULTIPLY", h, m.math("SUBTRACT", 1.0, puddle))
    m.set("Normal", m.bump(h, 0.9, 0.05))
    return m.mat


def mat_grave_ground():
    m = Mat("M_Chao_Cemiterio")
    obj = m.texcoord().outputs["Object"]
    n1 = m.noise(obj, 0.5, 6.0, 0.6)
    n2 = m.noise(obj, 12.0, 8.0, 0.65)
    g = m.math("ADD", m.math("MULTIPLY", n1.outputs["Fac"], 0.5), m.math("MULTIPLY", n2.outputs["Fac"], 0.5))
    col = m.ramp(g, [(0.3, (0.012, 0.012, 0.008)), (0.55, (0.03, 0.03, 0.018)), (0.8, (0.055, 0.05, 0.03))])
    m.set("Base Color", col.outputs["Color"])
    m.set("Roughness", 0.95)
    m.set("Normal", m.bump(n2.outputs["Fac"], 0.7, 0.03))
    return m.mat


def mat_iron():
    m = Mat("M_Ferro_Forjado")
    obj = m.texcoord().outputs["Object"]
    rust = m.maprange(m.noise(obj, 18.0, 8.0, 0.7).outputs["Fac"], 0.5, 0.68)
    m.set("Base Color", m.mix(rust, (0.012, 0.012, 0.014), (0.07, 0.03, 0.015)))
    m.set("Metallic", m.mixf(rust, 0.85, 0.2))
    m.set("Roughness", m.mixf(rust, 0.45, 0.9))
    return m.mat


def mat_dry_grass():
    m = Mat("M_Erva_Seca")
    rnd = m.node("ShaderNodeObjectInfo").outputs["Random"]
    col = m.ramp(rnd, [(0.0, (0.05, 0.045, 0.025)), (0.5, (0.09, 0.075, 0.035)), (1.0, (0.035, 0.045, 0.02))])
    m.set("Base Color", col.outputs["Color"])
    m.set("Roughness", 0.8)
    m.set("Subsurface Weight", 0.1)
    return m.mat


# ---------------------------------------------------------------------------
# Campas (modelos instanciados)
# ---------------------------------------------------------------------------
def profile_round(w, h, n=12):
    pts = [(-w / 2, 0), (w / 2, 0), (w / 2, h - w / 2)]
    for i in range(1, n):
        a = math.pi * i / n
        pts.append((w / 2 * math.cos(a), h - w / 2 + w / 2 * math.sin(a)))
    pts.append((-w / 2, h - w / 2))
    return pts


def profile_gothic(w, h):
    arch = pointed_arch(w / 2, h - w * 0.9, h, 10)
    return [(-w / 2, 0), (w / 2, 0)] + arch[:-1] + [(-w / 2, h - w * 0.9)]


def profile_broken(w, h, r_):
    pts = [(-w / 2, 0), (w / 2, 0), (w / 2, h * r_.uniform(0.35, 0.6))]
    n = 6
    for i in range(1, n):
        x = w / 2 - w * i / n
        pts.append((x, h * r_.uniform(0.35, 0.75)))
    pts.append((-w / 2, h * r_.uniform(0.5, 0.8)))
    return pts


def slab(b, pts, thick, mat=0):
    """Laje vertical a partir de um perfil (x, z), espessura ao longo de Y."""
    b.prism(pts, lambda s, z: Vector((s, -thick / 2, z)), (0, thick, 0), mat=mat)


def make_grave_models(parent_col, stone):
    models = []
    r_ = random.Random(3)

    def model(name):
        c = collection(f"_CAMPA_{name}", parent_col)
        models.append(c)
        return c

    def finish(b, name, col, bevel=0.012):
        # plinto
        b.box((0, 0, 0.06), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (1.0, 0.4, 0.12), mat=0)
        ob = b.to_object(name, col, [stone])
        bv = ob.modifiers.new("Bevel", "BEVEL")
        bv.width = bevel
        bv.segments = 2
        return ob

    # 0 arredondada, alta (proporções Burton)
    b = Builder()
    slab(b, [(x, z + 0.12) for x, z in profile_round(0.62, 1.35)], 0.12)
    finish(b, "Campa_Arredondada", model("Arredondada"))
    # 1 gótica pontiaguda
    b = Builder()
    slab(b, [(x, z + 0.12) for x, z in profile_gothic(0.55, 1.55)], 0.12)
    finish(b, "Campa_Gotica", model("Gotica"))
    # 2 cruz alta e fina
    b = Builder()
    b.box((0, 0, 0.12 + 0.85), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.11, 0.1, 1.7))
    b.box((0, 0, 0.12 + 1.3), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.62, 0.1, 0.11))
    finish(b, "Campa_Cruz", model("Cruz"), 0.008)
    # 3 cruz celta
    b = Builder()
    b.box((0, 0, 0.12 + 0.7), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.14, 0.12, 1.4))
    b.box((0, 0, 0.12 + 1.05), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.7, 0.12, 0.14))
    b.ring((0, 0, 0.12 + 1.05), Euler((math.pi / 2, 0, 0)).to_matrix() @ Euler((0, 0, 0)).to_matrix(), 0.2, 0.035, 1.0, 24, 6)
    finish(b, "Campa_Cruz_Celta", model("Celta"), 0.008)
    # 4 obelisco
    b = Builder()
    b.cylinder((0, 0, 0.12), (0, 0, 1.9), 0.17, 0.1, 4)
    b.cylinder((0, 0, 1.9), (0, 0, 2.15), 0.1, 0.0, 4)
    b.box((0, 0, 0.25), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.45, 0.45, 0.26))
    ob = finish(b, "Campa_Obelisco", model("Obelisco"), 0.006)
    # 5 lápide estreita e altíssima com volute enrolada no topo
    b = Builder()
    slab(b, [(x, z + 0.12) for x, z in profile_round(0.34, 1.9)], 0.1)
    b.ring((0, 0, 2.02 + 0.12), Euler((math.pi / 2, 0, 0)).to_matrix(), 0.1, 0.03, 1.0, 16, 6)
    finish(b, "Campa_Estreita_Volute", model("Estreita"))
    # 6 partida
    b = Builder()
    slab(b, [(x, z + 0.12) for x, z in profile_broken(0.66, 1.3, r_)], 0.13)
    b.box((0.35, -0.35, 0.05), (Vector((1, 0.4, 0)).normalized(), Vector((-0.4, 1, 0)).normalized(), (0, 0, 1)), (0.5, 0.35, 0.1))
    finish(b, "Campa_Partida", model("Partida"))
    # 7 laje deitada com pequena cabeceira
    b = Builder()
    b.box((0, -0.9, 0.1), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.85, 1.9, 0.2))
    slab(b, [(x, z + 0.12) for x, z in profile_round(0.7, 0.75)], 0.12)
    finish(b, "Campa_Laje", model("Laje"))
    return models


def scatter_graves(col, models):
    r_ = random.Random(21)
    placed = []
    for gx in np.arange(-32.0, 32.1, 2.1):
        for gy in np.arange(-29.0, 24.0, 2.7):
            if r_.random() < 0.3:
                continue
            x, y = gx + r_.gauss(0, 0.35), gy + r_.gauss(0, 0.3)
            if road_dist(x, y) < 2.8:
                continue
            if any(math.hypot(x - mx, y - my) < rr for mx, my, rr in MAUSO_ZONES):
                continue
            if math.hypot(x - HILL_TREE.x, y - HILL_TREE.y) < 3.5:
                continue
            m = r_.choice(models)
            e = bpy.data.objects.new(f"Campa_{len(placed):03d}", None)
            e.instance_type = "COLLECTION"
            e.instance_collection = m
            lean = r_.random()
            tilt = r_.gauss(0, 0.06) if lean < 0.55 else r_.gauss(0, 0.2)
            roll = r_.gauss(0, 0.05) if lean < 0.55 else r_.gauss(0, 0.16)
            yaw = math.pi + r_.gauss(0, 0.2)   # viradas para quem vem do portão (-Y)
            e.location = (x, y, ground_height(x, y) - r_.uniform(0.0, 0.18))
            e.rotation_euler = (tilt, roll, yaw)
            s = r_.uniform(0.85, 1.15)
            e.scale = (s, s, s * r_.uniform(0.95, 1.35))
            col.objects.link(e)
            placed.append((x, y))
    return placed


# ---------------------------------------------------------------------------
# Mausoléus
# ---------------------------------------------------------------------------
def build_mausoleum(name, col, stone, stone_dark, iron, center, w, d, h, roof_h, yaw, lean, door_open=0.0, spire=False):
    # assentar no ponto mais baixo do terreno sob a planta (a colina é inclinada)
    gz = min(ground_height(center.x + dx, center.y + dy) for dx in (-w / 2, 0, w / 2) for dy in (-d / 2 - 1.2, 0, d / 2))
    M = Matrix.Translation((center.x, center.y, gz - 0.1)) @ Euler((lean[0], lean[1], yaw)).to_matrix().to_4x4()
    b = Builder()
    b.box((0, 0, -0.8), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (w + 0.4, d + 0.4, 1.6), M=M, mat=1)   # fundação
    # degraus
    for k in range(3):
        b.box((0, -d / 2 - 0.25 - k * 0.3 + 0.3, 0.1 + k * 0.0), ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
              (w + 0.6 - k * 0.2, 0.6 + k * 0.3, 0.2 + 0.15 * (2 - k)), M=M, mat=1)
    # paredes laterais e traseira
    t = 0.3
    for sx in (-1, 1):
        b.box((sx * (w / 2 - t / 2), 0, 0.4 + h / 2), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (t, d, h), M=M)
    b.box((0, d / 2 - t / 2, 0.4 + h / 2), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (w, t, h), M=M)
    # fachada com porta ogival
    dw, dh = w * 0.42, h * 0.72
    arch = sorted([(x, z + 0.4) for x, z in pointed_arch(dw / 2, 0.4 + dh - dw * 0.8 - 0.4, 0.4 + dh - 0.4, 12)], key=lambda p: p[0])
    front = [(-w / 2, 0.4), (-dw / 2, 0.4)] + [(-dw / 2, arch[0][1])] + arch + [(dw / 2, 0.4), (w / 2, 0.4), (w / 2, 0.4 + h), (-w / 2, 0.4 + h)]
    faces = b.prism(front, lambda s, z: M @ Vector((s, -d / 2, z)), M.to_3x3() @ Vector((0, t, 0)))
    # pilastras e cornija
    for sx in (-1, 1):
        b.box((sx * (w / 2 + 0.05), -d / 2 - 0.05, 0.4 + h / 2), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.35, 0.35, h + 0.1), M=M, mat=1)
    b.box((0, 0, 0.4 + h + 0.1), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (w + 0.5, d + 0.5, 0.2), M=M, mat=1)
    # telhado de duas águas, íngreme
    roof = [(-w / 2 - 0.3, 0.0), (w / 2 + 0.3, 0.0), (0.0, roof_h)]
    b.prism(roof, lambda s, z: M @ Vector((s, -d / 2 - 0.3, 0.4 + h + 0.2 + z)), M.to_3x3() @ Vector((0, d + 0.6, 0)), mat=1)
    # pináculos nos cantos (pontiagudos, à Burton)
    for sx in (-1, 1):
        for sy in (-1, 1):
            base_p = M @ Vector((sx * (w / 2 + 0.1), sy * (d / 2 + 0.1), 0.4 + h + 0.2))
            b.cylinder(base_p, base_p + M.to_3x3() @ Vector((0, 0, roof_h * 0.55 + 0.4)), 0.13, 0.0, 6, mat=1)
    # óculo no frontão
    b.ring(M @ Vector((0, -d / 2 - 0.34, 0.4 + h + 0.2 + roof_h * 0.38)), M.to_3x3() @ Matrix.Identity(3), min(w, roof_h) * 0.14,
           0.05, 1.0, 20, 6, mat=1)
    # frontão com cruz no topo
    top = M @ Vector((0, -d / 2 - 0.3, 0.4 + h + 0.2 + roof_h))
    if spire:
        b.cylinder(M @ Vector((0, 0, 0.4 + h + 0.2 + roof_h * 0.6)), M @ Vector((0, 0, 0.4 + h + 0.2 + roof_h + 2.6)), 0.35, 0.02, 8, mat=1)
    b.box(top + M.to_3x3() @ Vector((0, 0, 0.45)), (M.to_3x3() @ Vector((1, 0, 0)), M.to_3x3() @ Vector((0, 1, 0)), M.to_3x3() @ Vector((0, 0, 1))),
          (0.09, 0.09, 0.9), mat=1)
    b.box(top + M.to_3x3() @ Vector((0, 0, 0.6)), (M.to_3x3() @ Vector((1, 0, 0)), M.to_3x3() @ Vector((0, 1, 0)), M.to_3x3() @ Vector((0, 0, 1))),
          (0.45, 0.09, 0.09), mat=1)
    ob = b.to_object(name, col, [stone, stone_dark])
    ob.modifiers.new("Bevel", "BEVEL").width = 0.02
    # interior escuro
    b = Builder()
    b.box((0, 0, 0.4 + h / 2), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (w - 2 * t - 0.02, d - t - 0.3, h - 0.05), M=M)
    b.to_object(name + "_Interior", col, [bpy.data.materials["M_Preto_Abismo"]])
    # porta de ferro em grade, com espirais (entreaberta ou fechada)
    hinge = M @ Vector((-dw / 2 + 0.03, -d / 2 - 0.02, 0.4))
    R = M.to_3x3() @ Euler((0, 0, -door_open)).to_matrix()
    cu = bpy.data.curves.new(name + "_Porta", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.012
    bars = 7
    hh = dh - dw * 0.4
    for k in range(bars):
        x = (k + 0.5) * (dw - 0.06) / bars
        spline(cu, [hinge + R @ Vector((x, 0, 0.02)), hinge + R @ Vector((x, 0, hh))], [1, 1])
    for z in (0.1, hh * 0.5, hh):
        spline(cu, [hinge + R @ Vector((0, 0, z)), hinge + R @ Vector((dw - 0.06, 0, z))], [1, 1])
    for k in range(2):   # espirais
        c = hinge + R @ Vector(((k + 0.5) * (dw - 0.06) / 2, 0, hh * 0.75))
        pts = []
        for i in range(30):
            a = i * 0.45
            r = 0.02 + 0.006 * a
            pts.append(c + R @ Vector((math.cos(a) * r, 0, math.sin(a) * r)))
        spline(cu, pts, [1] * len(pts))
    cu.materials.append(iron)
    new_object(name + "_Porta_Grade", cu, col)
    return ob


# ---------------------------------------------------------------------------
# Estátuas
# ---------------------------------------------------------------------------
def skin_figure(name, col, joints, edges, radii, mat, M):
    keys = list(joints.keys())
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(M @ Vector(joints[k])) for k in keys], [(keys.index(a), keys.index(b)) for a, b in edges], [])
    ob = new_object(name, me, col)
    ob.modifiers.new("Pele", "SKIN")
    sv = me.skin_vertices[0].data
    for i, k in enumerate(keys):
        sv[i].radius = radii[k]
    sv[0].use_root = True
    me.materials.append(mat)
    sub = ob.modifiers.new("Subdivisao", "SUBSURF")
    sub.levels, sub.render_levels = 1, 2
    me.shade_smooth()
    return ob


def build_weeping_angel(name, col, stone, pos, yaw):
    gz = ground_height(pos.x, pos.y)
    M = Matrix.Translation((pos.x, pos.y, gz)) @ Euler((0, 0, yaw)).to_matrix().to_4x4()
    b = Builder()
    b.box((0, 0, 0.55), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.8, 0.8, 1.1), M=M)
    b.box((0, 0, 1.13), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.95, 0.95, 0.08), M=M)
    # manto até aos pés
    b.cylinder(M @ Vector((0, 0, 1.17)), M @ Vector((0, 0, 2.35)), 0.36, 0.2, 18)
    ob = b.to_object(name + "_Pedestal_Manto", col, [stone])
    # corpo: cabeça curvada, mãos na cara
    J = {"pelvis": (0, 0, 2.2), "chest": (0, -0.02, 2.62), "neck": (0, -0.08, 2.78), "head": (0, -0.2, 2.86),
         "sh_l": (-0.19, -0.02, 2.7), "sh_r": (0.19, -0.02, 2.7), "el_l": (-0.14, -0.22, 2.55), "el_r": (0.14, -0.22, 2.55),
         "ha_l": (-0.05, -0.28, 2.83), "ha_r": (0.05, -0.28, 2.83)}
    E = [("pelvis", "chest"), ("chest", "neck"), ("neck", "head"), ("chest", "sh_l"), ("chest", "sh_r"), ("sh_l", "el_l"),
         ("el_l", "ha_l"), ("sh_r", "el_r"), ("el_r", "ha_r")]
    Rr = {"pelvis": (0.2, 0.15), "chest": (0.18, 0.12), "neck": (0.05, 0.05), "head": (0.1, 0.11), "sh_l": (0.06, 0.06),
          "sh_r": (0.06, 0.06), "el_l": (0.045, 0.045), "el_r": (0.045, 0.045), "ha_l": (0.04, 0.035), "ha_r": (0.04, 0.035)}
    skin_figure(name + "_Corpo", col, J, E, Rr, stone, M)
    # asas: perfil de pena, finas, abertas para trás e para cima
    for s in (-1, 1):
        wing = [(0.0, 0.0), (0.25, 0.35), (0.55, 0.9), (0.75, 1.35), (0.7, 1.1), (0.62, 0.7), (0.58, 0.55), (0.5, 0.3),
                (0.45, 0.1), (0.36, -0.1), (0.3, -0.3), (0.2, -0.5), (0.12, -0.2)]
        wb = Builder()
        Mw = M @ Matrix.Translation((s * 0.12, 0.12, 2.55)) @ Euler((0, 0, s * 0.35)).to_matrix().to_4x4()
        wb.prism([(s * x, z) for x, z in wing], lambda u, z, Mw=Mw: Mw @ Vector((u, 0, z)), Mw.to_3x3() @ Vector((0, 0.05, 0)))
        wo = wb.to_object(f"{name}_Asa_{'E' if s < 0 else 'D'}", col, [stone])
        sub = wo.modifiers.new("Subdivisao", "SUBSURF")
        sub.levels, sub.render_levels = 1, 2
    return ob


def build_hooded(name, col, stone, pos, yaw):
    gz = ground_height(pos.x, pos.y)
    M = Matrix.Translation((pos.x, pos.y, gz)) @ Euler((0, 0, yaw)).to_matrix().to_4x4()
    b = Builder()
    b.box((0, 0, 0.35), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.75, 0.75, 0.7), M=M)
    b.cylinder(M @ Vector((0, 0, 0.7)), M @ Vector((0, 0, 2.3)), 0.4, 0.2, 20)
    b.ico(M @ Vector((0, -0.02, 2.42)), 0.24, (0.9, 1.0, 1.25), 3, 0.05)          # capuz
    b.ico(M @ Vector((0, -0.12, 2.36)), 0.15, (0.8, 0.5, 1.0), 3, 0.0, mat=1)      # vazio do capuz (sem rosto)
    ob = b.to_object(name, col, [stone, bpy.data.materials["M_Preto_Abismo"]], smooth=True)
    ob.modifiers.new("Subdivisao", "SUBSURF").levels = 1
    return ob


# ---------------------------------------------------------------------------
# Portão, vedação, candeeiros, árvores, corvos
# ---------------------------------------------------------------------------
def spiral(c, R, turns=2.2, r0=0.18, n=40, flip=1):
    pts = []
    for i in range(n):
        t = i / (n - 1)
        a = flip * t * turns * 2 * math.pi
        r = r0 * (1 - t * 0.85)
        pts.append(c + R @ Vector((math.cos(a) * r, 0, math.sin(a) * r)))
    return pts


def build_gate_fence(col, stone, iron):
    y = GATE_Y
    b = Builder()
    for sx in (-1, 1):
        x = sx * (ROAD_W / 2 + 0.6)
        gz = ground_height(x, y)
        b.box((x, y, gz + 1.5), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.7, 0.7, 3.0))
        b.box((x, y, gz + 3.08), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.85, 0.85, 0.16))
        b.ico((x, y, gz + 3.45), 0.28, (1, 1, 1.15), 2, 0.05)
    b.to_object("Portao_Pilares", col, [stone]).modifiers.new("Bevel", "BEVEL").width = 0.02
    cu = bpy.data.curves.new("Portao_Folhas", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.016
    gw = ROAD_W / 2 + 0.25
    for sx, ang in ((-1, 0.0), (1, math.radians(-38))):
        hinge = Vector((sx * gw, y, ground_height(sx * gw, y)))
        R = Euler((0, 0, ang * sx)).to_matrix()
        dirx = -sx
        for k in range(9):
            x = dirx * (k + 0.5) * gw / 9
            top = 2.3 + 0.35 * math.sin(math.pi * (k + 0.5) / 9)
            spline(cu, [hinge + R @ Vector((x, 0, 0.05)), hinge + R @ Vector((x, 0, top))], [1, 1])
            spline(cu, [hinge + R @ Vector((x, 0, top)), hinge + R @ Vector((x, 0, top + 0.18))], [1.4, 0.1])
        for z in (0.25, 1.2, 2.1):
            spline(cu, [hinge + R @ Vector((0, 0, z)), hinge + R @ Vector((dirx * gw, 0, z))], [1, 1])
        for k in range(3):
            c = hinge + R @ Vector((dirx * (k + 0.5) * gw / 3, 0, 1.65))
            spline(cu, spiral(c, R, 2.0, 0.2, 40, flip=dirx), [1] * 40)
    cu.materials.append(iron)
    new_object("Portao_Ferro_Espirais", cu, col)
    # vedação de lanças
    cu = bpy.data.curves.new("Vedacao", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.012
    r_ = random.Random(8)
    for side in (-1, 1):
        x = side * (ROAD_W / 2 + 1.0)
        while abs(x) < HALF:
            if r_.random() > 0.06:
                gz = ground_height(x, y)
                lean = Vector((r_.gauss(0, 0.04), r_.gauss(0, 0.06), 1)).normalized()
                if r_.random() < 0.05:
                    lean = Vector((r_.gauss(0, 0.3), r_.gauss(0, 0.3), 1)).normalized()
                base = Vector((x, y, gz - 0.1))
                top = base + lean * 2.0
                spline(cu, [base, top], [1, 1])
                spline(cu, [top, top + lean * 0.16], [1.6, 0.1])
            x += side * 0.16
        for z in (0.3, 1.75):
            a = Vector((side * (ROAD_W / 2 + 1.0), y, ground_height(0, y) + z))
            bb = Vector((side * HALF, y, ground_height(side * HALF, y) + z))
            spline(cu, [a, bb], [1.3, 1.3])
    cu.materials.append(iron)
    new_object("Vedacao_Lancas", cu, col)


def build_road(col, mat):
    verts, faces = [], []
    n = 7
    for i, p in enumerate(ROAD):
        a = ROAD[max(i - 1, 0)]
        c = ROAD[min(i + 1, len(ROAD) - 1)]
        tng = (c - a).normalized()
        side = Vector((-tng.y, tng.x, 0))
        for k in range(n):
            s = (k / (n - 1) - 0.5) * ROAD_W
            q = p + side * s
            verts.append((q.x, q.y, ground_height(q.x, q.y) + 0.035 - 0.02 * (2 * abs(s) / ROAD_W) ** 2))
    for i in range(len(ROAD) - 1):
        for k in range(n - 1):
            a = i * n + k
            faces.append((a, a + 1, a + n + 1, a + n))
    me = bpy.data.meshes.new("Estrada")
    me.from_pydata(verts, [], faces)
    me.materials.append(mat)
    me.shade_smooth()
    ob = new_object("Estrada_Calcada", me, col)
    sub = ob.modifiers.new("Subdivisao", "SUBSURF")
    sub.levels, sub.render_levels = 1, 2
    return ob


def build_lamps(col, iron, glass_on, glass_off, c_light_night):
    """Candeeiros vitorianos ao longo da estrada: estados variados."""
    states = ["aceso", "aceso", "pisca", "morto", "aceso", "fraco", "tombado", "aceso"]
    # posições ao longo da estrada, alternando lados
    cum = [0.0]
    for a, bb in zip(ROAD[:-1], ROAD[1:]):
        cum.append(cum[-1] + (bb - a).length)
    total = cum[-1]
    lamps = []
    for i, st in enumerate(states):
        dist = 8 + i * (total - 14) / (len(states) - 1)
        j = next(k for k in range(len(cum)) if cum[k] >= dist)
        p = ROAD[j]
        tng = (ROAD[min(j + 1, len(ROAD) - 1)] - ROAD[max(j - 1, 0)]).normalized()
        side = Vector((-tng.y, tng.x, 0)) * (1 if i % 2 == 0 else -1)
        base = p + side * (ROAD_W / 2 + 0.55)
        base.z = ground_height(base.x, base.y)
        up = Vector((0, 0, 1))
        if st == "tombado":
            up = Vector((side.x * 0.5, side.y * 0.5, 0.85)).normalized()
        H = 3.3
        top = base + up * H
        b = Builder()
        b.cylinder(base, base + up * 0.4, 0.13, 0.1, 10)
        b.cylinder(base + up * 0.4, top, 0.055, 0.04, 10)
        # braço curvo com espiral, virado para a estrada
        arm_dir = -side.normalized()
        arm_end = top + arm_dir * 0.55 + up * 0.1
        b.cylinder(top, arm_end, 0.03, 0.03, 8)
        lamp_c = arm_end - up * 0.35
        R = Matrix.Rotation(math.atan2(arm_dir.y, arm_dir.x), 3, "Z")
        # lanterna: base, vidro, chapéu pontiagudo
        b.cylinder(lamp_c - up * 0.18, lamp_c - up * 0.14, 0.13, 0.13, 6)
        b.cylinder(lamp_c + up * 0.16, lamp_c + up * 0.2, 0.17, 0.17, 6)
        b.cylinder(lamp_c + up * 0.2, lamp_c + up * 0.55, 0.16, 0.0, 6)
        b.cylinder(arm_end, lamp_c + up * 0.55, 0.012, 0.012, 6)
        ob = b.to_object(f"Candeeiro_{i}_{st}", col, [iron], smooth=False)
        cu = bpy.data.curves.new(f"Candeeiro_{i}_Espiral", "CURVE")
        cu.dimensions = "3D"
        cu.bevel_depth = 0.012
        spline(cu, spiral(top + arm_dir * 0.2 - up * 0.2, Matrix.Rotation(math.atan2(arm_dir.y, arm_dir.x), 3, "Z"), 1.8, 0.16, 36),
               [1] * 36)
        cu.materials.append(iron)
        new_object(f"Candeeiro_{i}_Espiral", cu, col)
        gb = Builder()
        gb.cylinder(lamp_c - up * 0.14, lamp_c + up * 0.16, 0.12, 0.15, 6)
        lit = st in ("aceso", "pisca", "fraco")
        gm = glass_on if lit else glass_off
        gob = gb.to_object(f"Candeeiro_{i}_Vidro", col, [gm], smooth=False)
        if lit:
            e = {"aceso": 45.0, "pisca": 45.0, "fraco": 14.0}[st]
            ld = light(f"LUZ_Candeeiro_{i}", "POINT", c_light_night, lamp_c, e, (1.0, 0.55, 0.22), shadow_soft_size=0.08)
            if st == "pisca":
                r_ = random.Random(i)
                f = 1
                ld.data.keyframe_insert("energy", frame=1)
                while f < 240:
                    f += r_.randint(6, 30)
                    for _ in range(r_.randint(1, 3)):
                        ld.data.energy = e * r_.uniform(0.0, 0.3)
                        ld.data.keyframe_insert("energy", frame=f)
                        f += r_.randint(1, 3)
                        ld.data.energy = e
                        ld.data.keyframe_insert("energy", frame=f)
                for fc in iter_fcurves(ld.data.animation_data.action):
                    for kp in fc.keyframe_points:
                        kp.interpolation = "CONSTANT"
        lamps.append((base, st))
    return lamps


def make_burton_tree(name, col, bark, seed, height, trunk_r):
    """Árvore negra, escanzelada, com pontas de ramos enroladas em espiral."""
    ob = make_tree(name, col, bark, seed, height, trunk_r, twist=0.2, lean=0.25)
    cu = ob.data
    r_ = random.Random(seed * 7)
    ends = []
    for sp in list(cu.splines)[1:]:
        pts = sp.points
        if len(pts) >= 4 and pts[-1].radius < 0.02 and r_.random() < 0.35:
            p = Vector(pts[-1].co[:3])
            d = (p - Vector(pts[-2].co[:3])).normalized()
            ends.append((p, d, pts[-1].radius))
    for p, d, r in ends:
        side = d.cross(Vector((0, 0, 1)))
        if side.length < 1e-3:
            side = Vector((1, 0, 0))
        side.normalize()
        up = side.cross(d)
        pts, rad = [], []
        n = 26
        R0 = r_.uniform(0.12, 0.3)
        flip = 1 if r_.random() < 0.5 else -1
        for i in range(n):
            t = i / (n - 1)
            a = flip * t * 2.4 * math.pi
            rr = R0 * (1 - 0.85 * t)
            q = p + d * (math.sin(a) * rr) + up * ((1 - math.cos(a)) * rr * 0.9)
            pts.append(q)
            rad.append(max(0.003, r * (1 - t)))
        spline(cu, pts, rad)
    return ob


def build_crow_model(col, mat):
    b = Builder()
    b.ico((0, 0, 0.12), 0.08, (0.85, 1.6, 0.9), 2, 0.05)         # corpo (frente = -Y)
    b.ico((0, -0.13, 0.2), 0.05, (1, 1.1, 1), 2, 0.0)            # cabeça
    b.cylinder((0, -0.17, 0.2), (0, -0.25, 0.19), 0.018, 0.0, 6)  # bico
    b.box((0, 0.17, 0.1), ((1, 0, 0), Vector((0, 1, -0.4)).normalized(), Vector((0, 0.4, 1)).normalized()), (0.07, 0.14, 0.01))  # cauda
    for s in (-1, 1):
        b.box((s * 0.07, 0.02, 0.13), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.02, 0.2, 0.08))   # asas fechadas
        b.cylinder((s * 0.025, -0.01, 0.05), (s * 0.025, 0.0, -0.02), 0.005, 0.004, 4)       # patas
    return b.to_object("Corvo_Modelo", col, [mat], smooth=True)


# ---------------------------------------------------------------------------
# Céu, luz, câmaras, render
# ---------------------------------------------------------------------------
def make_sky(name, day):
    """Céu nublado: nuvens escuras com uma zona mais clara onde a lua (ou o sol) está escondida."""
    w = bpy.data.worlds.new(name)
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new
    out = N("ShaderNodeOutputWorld")
    bg = N("ShaderNodeBackground")
    tc = N("ShaderNodeTexCoord")
    nz = N("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 2.2
    nz.inputs["Detail"].default_value = 8.0
    nz.inputs["Roughness"].default_value = 0.62
    mp = N("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, 1.0, 3.0)
    L(tc.outputs["Generated"], mp.inputs["Vector"])
    L(mp.outputs["Vector"], nz.inputs["Vector"])
    clouds = N("ShaderNodeValToRGB")
    if day:
        clouds.color_ramp.elements[0].position = 0.35
        clouds.color_ramp.elements[0].color = (0.32, 0.33, 0.34, 1)
        clouds.color_ramp.elements[1].position = 0.7
        clouds.color_ramp.elements[1].color = (0.62, 0.63, 0.64, 1)
    else:
        clouds.color_ramp.elements[0].position = 0.35
        clouds.color_ramp.elements[0].color = (0.006, 0.008, 0.014, 1)
        clouds.color_ramp.elements[1].position = 0.72
        clouds.color_ramp.elements[1].color = (0.05, 0.06, 0.085, 1)
    L(nz.outputs["Fac"], clouds.inputs["Fac"])
    # brilho difuso onde a lua está escondida
    dot = N("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    L(tc.outputs["Generated"], dot.inputs[0])
    dot.inputs[1].default_value = tuple(-MOON_DIR)
    glow = N("ShaderNodeMapRange")
    glow.inputs["From Min"].default_value = 0.8
    glow.inputs["From Max"].default_value = 1.0
    glow.inputs["To Min"].default_value = 0.0
    glow.inputs["To Max"].default_value = 0.25 if not day else 0.3
    L(dot.outputs["Value"], glow.inputs["Value"])
    pw = N("ShaderNodeMath")
    pw.operation = "POWER"
    L(glow.outputs["Result"], pw.inputs[0])
    pw.inputs[1].default_value = 1.5
    add = N("ShaderNodeMix")
    add.data_type = "RGBA"
    add.blend_type = "ADD"
    sock(add, "Factor_Float").default_value = 1.0
    L(clouds.outputs["Color"], sock(add, "A_Color"))
    col_moon = N("ShaderNodeCombineColor")
    for i, k in enumerate((0.75, 0.82, 1.0)):
        mm = N("ShaderNodeMath")
        mm.operation = "MULTIPLY"
        L(pw.outputs[0], mm.inputs[0])
        mm.inputs[1].default_value = k
        L(mm.outputs[0], col_moon.inputs[i])
    L(col_moon.outputs[0], sock(add, "B_Color"))
    L(sock(add, "Result_Color", out=True), bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.6 if day else 1.0
    L(bg.outputs[0], out.inputs["Surface"])
    return w


def build_light_variants(v_night, v_day, fog_n, fog_d):
    moon = light("LUZ_Luar_Palido", "SUN", v_night, (0, 0, 30), 0.35, (0.62, 0.7, 0.95), angle=math.radians(12))
    moon.rotation_euler = MOON_DIR.to_track_quat("-Z", "Y").to_euler()
    sun = light("LUZ_Sol_Encoberto", "SUN", v_day, (0, 0, 30), 0.7, (0.85, 0.87, 0.9), angle=math.radians(40))
    sun.rotation_euler = MOON_DIR.to_track_quat("-Z", "Y").to_euler()
    for tag, col, mat in (("Noite", v_night, fog_n), ("Dia", v_day, fog_d)):
        me = bpy.data.meshes.new(f"Nevoa_{tag}")
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0, 0, 4.0)) @ Matrix.Diagonal((2 * HALF + 10, 2 * HALF + 10, 10.0, 1)))
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mat)
        new_object(f"ATMOS_Nevoa_{tag}", me, col)


def build_cameras(col):
    cams = {}

    def cam(name, loc, target, lens, fstop=None, focus=None):
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        cd.sensor_width = 36
        cd.clip_start = 0.05
        cd.clip_end = 400
        if fstop:
            cd.dof.use_dof = True
            cd.dof.aperture_fstop = fstop
            cd.dof.focus_distance = focus
        loc = Vector(loc)
        loc.z += ground_height(loc.x, loc.y)
        tgt = Vector(target)
        tgt.z += ground_height(tgt.x, tgt.y)
        ob = new_object(name, cd, col)
        ob.location = loc
        ob.rotation_euler = look_at_rotation(loc, tgt)
        cams[name] = ob

    cam("CAM_1_Portao", (0.6, -39.0, 1.7), (-2.0, -14.0, 1.6), 30, 8.0, 7.0)
    cam("CAM_2_Estrada_Candeeiros", (-6.5, -19.0, 1.6), (4.0, 6.0, 1.4), 35)
    cam("CAM_3_Mausoleu_Principal", (1.8, 17.0, 0.7), (0.0, 28.5, 4.8), 22)
    cam("CAM_4_Campas_Tortas", (11.5, -3.0, 0.45), (17.5, 6.5, 0.7), 35, 4.0, 5.0)
    cam("CAM_5_Anjo_Choroso", (-10.3, 1.9, 1.7), (-12.0, -2.0, 2.45), 45, 2.8, 4.3)
    cam("CAM_6_Colina_Silhueta", (-20.0, 6.0, 1.2), (-9.0, 27.0, 4.5), 30)
    cam("CAM_7_Fundo_Analise", (14.0, -18.0, 2.2), (2.0, 4.0, 1.6), 28)
    bpy.context.scene.camera = cams["CAM_1_Portao"]
    return cams


def build_markers(col):
    def marker(name, loc, facing, note):
        theta = math.atan2(facing[0], -facing[1])
        e = bpy.data.objects.new(name, None)
        e.empty_display_type = "SINGLE_ARROW"
        e.empty_display_size = 0.5
        col.objects.link(e)
        e.location = (loc[0], loc[1], ground_height(loc[0], loc[1]))
        e.rotation_euler = (0, 0, theta)
        e["nota"] = note
        me = bpy.data.meshes.new(name + "_Silhueta")
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.2, radius2=0.2, depth=1.45,
                              matrix=Matrix.Translation((0, 0, 0.725)))
        bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=0.12, matrix=Matrix.Translation((0, 0, 1.63)))
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0, -0.2, 1.63)) @ Matrix.Diagonal((0.06, 0.08, 0.04, 1)))
        bm.to_mesh(me)
        bm.free()
        sil = new_object(name + "_Silhueta", me, col)
        sil.parent = e
        sil.display_type = "WIRE"
        sil.hide_render = True
        sil.hide_select = True

    marker("PERSONAGEM_1_Portao", (0.2, -31.0), (0, 1), "a entrar pelo portão (plano da CAM_1)")
    marker("PERSONAGEM_2_Estrada", (-5.8, -10.0), (0.1, 1), "a caminhar pela estrada, entre os candeeiros")
    marker("PERSONAGEM_3_Porta_Mausoleu", (0.0, 24.3), (0, 1), "diante da porta entreaberta do mausoléu principal")


def setup_render():
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.cycles.samples = 384
    scn.cycles.preview_samples = 24
    scn.cycles.use_adaptive_sampling = True
    scn.cycles.adaptive_threshold = 0.02
    scn.cycles.use_denoising = True
    scn.cycles.max_bounces = 6
    scn.cycles.diffuse_bounces = 2
    scn.cycles.volume_bounces = 1
    scn.cycles.sample_clamp_indirect = 5.0
    scn.render.resolution_x, scn.render.resolution_y = 1920, 1080
    scn.render.fps = 24
    scn.frame_start, scn.frame_end = 1, 240
    scn.view_settings.view_transform = "AgX"
    for look in ("AgX - Medium High Contrast", "None"):
        try:
            scn.view_settings.look = look
            break
        except TypeError:
            pass
    scn.view_settings.exposure = 1.3


def setup_compositor():
    """Paleta Burton: fria, dessaturada, azul-violeta nas sombras, silhuetas negras."""
    scn = bpy.context.scene
    scn.use_nodes = True
    nt = scn.node_tree
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new
    rl = N("CompositorNodeRLayers")
    glare = N("CompositorNodeGlare")
    glare.glare_type = "FOG_GLOW"
    try_set(glare, "Threshold", 0.7)
    try_set(glare, "Strength", 0.45)
    L(rl.outputs["Image"], glare.inputs["Image"])
    hs = N("CompositorNodeHueSat")
    try_set(hs, "Saturation", 0.5)
    L(glare.outputs["Image"], hs.inputs["Image"])
    cb = N("CompositorNodeColorBalance")
    cb.correction_method = "LIFT_GAMMA_GAIN"
    try_set(cb, "Lift", (1.0, 0.99, 1.04))
    try_set(cb, "Gamma", (0.98, 0.99, 1.03))
    try_set(cb, "Gain", (1.02, 1.0, 1.0))
    L(hs.outputs["Image"], cb.inputs["Image"])
    mask = N("CompositorNodeEllipseMask")
    try_set(mask, "Size", (0.95, 0.85))
    blur = N("CompositorNodeBlur")
    blur.filter_type = "FAST_GAUSS"
    try_set(blur, "Size", (300, 300))
    L(mask.outputs["Mask"], blur.inputs["Image"])
    lift = N("CompositorNodeMapRange")
    lift.inputs["From Min"].default_value = 0.0
    lift.inputs["From Max"].default_value = 1.0
    lift.inputs["To Min"].default_value = 0.4
    lift.inputs["To Max"].default_value = 1.0
    L(blur.outputs["Image"], lift.inputs["Value"])
    vig = N("CompositorNodeMixRGB")
    vig.blend_type = "MULTIPLY"
    L(cb.outputs["Image"], vig.inputs[1])
    L(lift.outputs["Value"], vig.inputs[2])
    tn = N("CompositorNodeTexture")
    tn.texture = bpy.data.textures.new("T_Grao", "NOISE")
    gb = N("CompositorNodeBlur")
    gb.filter_type = "GAUSS"
    try_set(gb, "Size", (1, 1))
    L(tn.outputs["Value"], gb.inputs["Image"])
    grain = N("CompositorNodeMixRGB")
    grain.blend_type = "OVERLAY"
    grain.inputs["Fac"].default_value = 0.1
    L(vig.outputs["Image"], grain.inputs[1])
    L(gb.outputs["Image"], grain.inputs[2])
    comp = N("CompositorNodeComposite")
    L(grain.outputs["Image"], comp.inputs["Image"])
    view = N("CompositorNodeViewer")
    L(grain.outputs["Image"], view.inputs["Image"])
    for i, n in enumerate(nt.nodes):
        n.location = (i * 220 - 1400, 0)


README_TEXT = """CEMITÉRIO GÓTICO (estilo Tim Burton) — como usar
==================================================
NOITE / DIA: em 05_LUZ ative VAR_Noite OU VAR_Dia e em World escolha
Ceu_Noite_Nublado / Ceu_Dia_Encoberto. Exposição: noite 1.3, dia 0.0.
As luzes dos candeeiros estão na VAR_Noite (de dia não iluminam).
Candeeiro a piscar: LUZ_Candeeiro_2 (animado, frames 1-240).
"""


MAUSO_ZONES = []


def main():
    args = parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.name = "Cemiterio_Gotico"
    c_models = collection("_MODELOS")
    c_ground = collection("01_TERRENO_ESTRADA")
    c_graves = collection("02_CAMPAS")
    c_mauso = collection("03_MAUSOLEUS_ESTATUAS")
    c_props = collection("04_PORTAO_CANDEEIROS_ARVORES")
    c_light = collection("05_LUZ")
    v_night = collection("VAR_Noite", c_light)
    v_day = collection("VAR_Dia", c_light)
    c_cam = collection("06_CAMARAS")
    c_char = collection("07_PERSONAGEM")

    stone = mat_grave_stone("M_Pedra_Campas")
    stone_m = mat_grave_stone("M_Pedra_Mausoleu", tone=0.85)
    stone_dark = mat_grave_stone("M_Pedra_Escura", tone=0.55)
    statue = mat_grave_stone("M_Pedra_Estatua", tone=1.25)
    iron = mat_iron()
    mat_simple("M_Preto_Abismo", (0.0, 0.0, 0.0), 1.0)
    bark = mat_bark()
    bark.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.01, 0.01, 0.012, 1)
    glass_on = mat_emit("M_Candeeiro_Aceso", (1.0, 0.6, 0.25), 18.0)
    glass_off = mat_simple("M_Candeeiro_Apagado", (0.05, 0.05, 0.045), 0.2)
    fog_n = mat_volume_fog("M_Nevoa_Noite", 0.07, 0.004, (0.72, 0.76, 0.9), height=1.6)
    fog_d = mat_volume_fog("M_Nevoa_Dia", 0.05, 0.012, (0.92, 0.93, 0.95), height=2.2)

    print("> terreno e estrada")
    ground = build_terrain(c_ground, mat_grave_ground())
    build_road(c_ground, mat_cobbles())
    print("> mausoléus e estátuas")
    maus = [
        ("Mausoleu_Principal", MAUSO_MAIN, 5.2, 6.5, 5.2, 4.2, 0.0, (0.0, 0.015), 0.5, True),
        ("Mausoleu_A", Vector((-7.5, -24.0, 0)), 2.6, 3.4, 3.6, 3.0, math.radians(20), (0.03, -0.02), 0.0, False),
        ("Mausoleu_B", Vector((6.0, -12.5, 0)), 2.4, 3.0, 4.2, 3.4, math.radians(-25), (-0.02, 0.04), 0.9, False),
        ("Mausoleu_C", Vector((-14.0, 4.0, 0)), 3.0, 3.6, 3.4, 2.6, math.radians(30), (0.02, 0.03), 0.0, False),
        ("Mausoleu_D", Vector((14.0, 13.5, 0)), 2.8, 3.2, 4.6, 3.8, math.radians(-35), (0.04, -0.03), 0.3, False),
    ]
    for name, c, w, d, h, rh, yaw, lean, door, spire in maus:
        MAUSO_ZONES.append((c.x, c.y, max(w, d) * 0.9 + 1.2))
        build_mausoleum(name, c_mauso, stone_m, stone_dark, iron, c, w, d, h, rh, yaw, lean, door, spire)
    build_weeping_angel("Anjo_Choroso_1", c_mauso, statue, Vector((-12.0, -2.0, 0)), math.radians(160))
    build_weeping_angel("Anjo_Choroso_2", c_mauso, statue, Vector((9.5, 20.5, 0)), math.radians(210))
    build_hooded("Figura_Encapuzada_1", c_mauso, statue, Vector((4.2, -27.0, 0)), math.radians(190))
    build_hooded("Figura_Encapuzada_2", c_mauso, statue, Vector((-4.2, 22.0, 0)), math.radians(150))
    for x, y in ((-12.0, -2.0), (9.5, 20.5), (4.2, -27.0), (-4.2, 22.0)):
        MAUSO_ZONES.append((x, y, 1.6))
    print("> campas")
    models = make_grave_models(c_models, stone)
    graves = scatter_graves(c_graves, models)
    print(f"  {len(graves)} campas")
    print("> portão, candeeiros, árvores, corvos")
    build_gate_fence(c_props, stone_m, iron)
    build_lamps(c_props, iron, glass_on, glass_off, v_night)
    tcol = collection("_ARVORES", c_models)
    tmods = []
    for i in range(5):
        mc = collection(f"_ARVORE_BURTON_{i}", tcol)
        make_burton_tree(f"Arvore_Burton_{i}", mc, bark, 400 + i, rng.uniform(8, 12), rng.uniform(0.18, 0.3))
        tmods.append(mc)
    r_ = random.Random(17)
    spots = []
    tries = 0
    while len(spots) < 26 and tries < 3000:
        tries += 1
        x, y = r_.uniform(-HALF + 2, HALF - 2), r_.uniform(-30, HALF - 2)
        if road_dist(x, y) < 4.0 or any(math.hypot(x - a, y - b) < rr + 1.5 for a, b, rr in MAUSO_ZONES):
            continue
        if any(math.hypot(x - a, y - b) < 6.0 for a, b in spots):
            continue
        spots.append((x, y))
        e = bpy.data.objects.new(f"Arvore_{len(spots):02d}", None)
        e.instance_type = "COLLECTION"
        e.instance_collection = r_.choice(tmods)
        e.location = (x, y, ground_height(x, y))
        s = r_.uniform(0.8, 1.3)
        e.scale = (s, s, s)
        e.rotation_euler = (0, 0, r_.uniform(0, 6.3))
        c_props.objects.link(e)
    hero = make_burton_tree("Arvore_Colina_Retorcida", c_props, bark, 777, 15.0, 0.55)
    hero.location = (HILL_TREE.x, HILL_TREE.y, ground_height(HILL_TREE.x, HILL_TREE.y))
    crow = build_crow_model(c_models, mat_simple("M_Corvo", (0.004, 0.004, 0.006), 0.35))
    # (x, y, altura acima do chão de referência, rotação, ponto de referência do chão)
    perches = ((ROAD_W / 2 + 0.6, GATE_Y, 3.72, 0.3, None), (4.2, -27.02, 2.68, 3.4, (4.2, -27.0)),
               (-11.75, -1.75, 1.17, 1.2, (-12.0, -2.0)), (-0.9, -18.2, 0.0, 2.2, None), (0.7, -17.5, 0.0, 4.0, None),
               (3.6, 5.2, 0.0, 1.0, None))
    for i, (x, y, z_off, yaw, ref) in enumerate(perches):
        c = bpy.data.objects.new(f"Corvo_{i}", crow.data)
        c_props.objects.link(c)
        gz = ground_height(*ref) if ref else ground_height(x, y)
        c.location = (x, y, gz + z_off)
        c.rotation_euler = (0, 0, yaw)
        c.scale = (1.3, 1.3, 1.3)
    print("> vegetação")
    build_ground_cover(ground, c_models)
    print("> luz, câmaras")
    night = make_sky("Ceu_Noite_Nublado", False)
    day = make_sky("Ceu_Dia_Encoberto", True)
    scn.world = night
    build_light_variants(v_night, v_day, fog_n, fog_d)
    build_cameras(c_cam)
    build_markers(c_char)
    setup_render()
    setup_compositor()
    bpy.data.texts.new("LEIA-ME").write(README_TEXT)
    vl = bpy.context.view_layer
    vl.layer_collection.children["_MODELOS"].exclude = True
    vl.layer_collection.children["05_LUZ"].children["VAR_Dia"].exclude = True
    scn.frame_set(1)
    out = os.path.abspath(args.out)
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    print(f"> guardado: {out}")
    if args.render:
        render_previews(args, night, day)


def build_terrain(col, mat):
    n = 170
    R = HALF + 5
    xs = np.linspace(-R, R, n)
    verts, dens = [], []
    for y in xs:
        for x in xs:
            verts.append((x, y, ground_height(x, y)))
            d = road_dist(x, y) if abs(x) < 16 else 99
            dens.append(0.0 if d < ROAD_W / 2 + 0.2 else min(1.0, (d - ROAD_W / 2) / 1.5))
    faces = [(j * n + i, j * n + i + 1, (j + 1) * n + i + 1, (j + 1) * n + i) for j in range(n - 1) for i in range(n - 1)]
    me = bpy.data.meshes.new("Terreno")
    me.from_pydata(verts, [], faces)
    me.materials.append(mat)
    me.shade_smooth()
    ob = new_object("Terreno_Cemiterio", me, col)
    vg = ob.vertex_groups.new(name="densidade_erva")
    for i, dv in enumerate(dens):
        vg.add([i], dv, "REPLACE")
    return ob


def make_grass_tuft(name, seed):
    r_ = random.Random(seed)
    bm = bmesh.new()
    for k in range(r_.randint(9, 15)):
        az = r_.uniform(0, 2 * math.pi)
        ln = r_.uniform(0.15, 0.4)
        lean = r_.uniform(0.1, 0.6)
        d = Vector((1.0, math.cos(az) * lean, math.sin(az) * lean)).normalized()   # eixo +X = para cima
        side = Vector((0, -math.sin(az), math.cos(az)))
        prev = None
        for i in range(5):
            t = i / 4
            p = d * (t * ln) + Vector((0, math.cos(az), math.sin(az))) * (t * t * ln * 0.3)
            w = 0.008 * (1 - t) + 0.001
            a, c = bm.verts.new(p + side * w), bm.verts.new(p - side * w)
            if prev:
                bm.faces.new((prev[0], a, c, prev[1]))
            prev = (a, c)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def build_ground_cover(ground, models_col):
    gcol = collection("_ERVA", models_col)
    gm = mat_dry_grass()
    for i in range(3):
        me = make_grass_tuft(f"Tufo_{i}", i)
        me.materials.append(gm)
        new_object(f"Tufo_Erva_{i}", me, gcol)
    lcol = collection("_FOLHAS", models_col)
    lm = mat_simple("M_Folha_Morta", (0.05, 0.035, 0.02), 0.75)
    for i in range(3):
        me = make_leaf_mesh(f"Folha_{i}", rng.uniform(0.07, 0.11), rng.uniform(0.045, 0.07), rng.uniform(0.01, 0.03), i)
        me.materials.append(lm)
        new_object(f"Folha_Morta_{i}", me, lcol)
    for name, colx, count, rot in (("Erva_Seca", gcol, 60000, 0.12), ("Folhas_Mortas", lcol, 40000, 0.35)):
        mod = ground.modifiers.new(name, "PARTICLE_SYSTEM")
        ps = mod.particle_system
        st = ps.settings
        st.name = f"PS_{name}"
        st.type = "HAIR"
        st.use_advanced_hair = True
        st.count = count
        st.hair_length = 1.0
        st.render_type = "COLLECTION"
        st.instance_collection = colx
        st.use_collection_pick_random = True
        st.particle_size = 1.0
        st.size_random = 0.5
        st.use_rotations = True
        st.rotation_mode = "NOR"
        st.phase_factor_random = 2.0
        st.rotation_factor_random = rot
        st.emit_from = "FACE"
        ps.vertex_group_density = "densidade_erva"
        ps.seed = rng.randint(0, 9999)


PREVIEWS = [   # (ficheiro, câmara, dia?)
    ("cam1_portao", "CAM_1_Portao", False),
    ("cam2_estrada_candeeiros", "CAM_2_Estrada_Candeeiros", False),
    ("cam3_mausoleu_principal", "CAM_3_Mausoleu_Principal", False),
    ("cam4_campas_tortas", "CAM_4_Campas_Tortas", False),
    ("cam5_anjo_choroso", "CAM_5_Anjo_Choroso", False),
    ("cam6_colina_silhueta", "CAM_6_Colina_Silhueta", False),
    ("cam7_fundo_analise", "CAM_7_Fundo_Analise", False),
    ("dia_cam1_portao", "CAM_1_Portao", True),
    ("dia_cam3_mausoleu_principal", "CAM_3_Mausoleu_Principal", True),
    ("dia_cam6_colina_silhueta", "CAM_6_Colina_Silhueta", True),
]


def render_previews(args, night, day):
    scn = bpy.context.scene
    os.makedirs(args.render, exist_ok=True)
    scn.cycles.samples = args.samples
    scn.cycles.adaptive_threshold = 0.05
    scn.cycles.volume_step_rate = 3.0
    scn.render.resolution_x = args.res
    scn.render.resolution_y = int(args.res * 9 / 16)
    scn.render.image_settings.file_format = "JPEG"
    scn.render.image_settings.quality = 90
    ll = bpy.context.view_layer.layer_collection.children["05_LUZ"]
    only = set(filter(None, args.only.split(",")))
    for fname, cam, is_day in PREVIEWS:
        if only and fname not in only:
            continue
        ll.children["VAR_Noite"].exclude = is_day
        ll.children["VAR_Dia"].exclude = not is_day
        scn.world = day if is_day else night
        scn.view_settings.exposure = 0.0 if is_day else 1.3
        scn.camera = bpy.data.objects[cam]
        scn.frame_set(20)
        scn.render.filepath = os.path.join(os.path.abspath(args.render), fname + ".jpg")
        print(f"> render {fname}")
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
