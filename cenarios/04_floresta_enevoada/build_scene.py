"""
Cenário 04 — Floresta noturna enevoada com uma clareira (e um objeto fora de lugar)

Árvores altas e tortas com raízes expostas, névoa volumétrica densa rente ao
chão, folhas secas a cair (partículas com vento), brisa nos fetos. Na clareira,
objetos que não pertencem ali: um balanço vazio que baloiça sozinho, uma cadeira
de madeira virada para as árvores, uma lanterna de petróleo apagada.
Versão noturna (luar) e diurna (céu encoberto, nevoeiro branco) — ambas inquietantes.

Uso (dentro do Blender):
    blender -b -P build_scene.py -- --out floresta_enevoada.blend
Uso (módulo bpy via pip):
    python build_scene.py --out floresta_enevoada.blend --render previews --samples 64
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

SEED = 1313
rng = random.Random(SEED)

# ---------------------------------------------------------------------------
# Dimensões (metros). A clareira está na origem; a câmara principal olha para +Y.
# ---------------------------------------------------------------------------
CLEAR_R = 6.5            # raio da clareira
FOREST_R = 42.0          # raio da floresta
HERO_TREE = Vector((-4.6, 3.2, 0.0))
LIMB_Z = 4.3
SWING_C = Vector((0.2, 3.25, 0.0))
CHAIR_C = Vector((0.5, 0.9, 0.0))
LANTERN_C = Vector((-0.9, 0.4, 0.0))
MOON_DIR = Vector((0.25, -1.0, -0.42)).normalized()   # luar baixo, vindo de trás da clareira


def ground_height(x, y):
    h = noise.noise(Vector((x * 0.05, y * 0.05, 0.3))) * 1.2
    h += noise.noise(Vector((x * 0.25, y * 0.25, 2.1))) * 0.25
    h += noise.noise(Vector((x * 1.2, y * 1.2, 5.7))) * 0.04
    r = math.hypot(x, y)
    h *= min(1.0, 0.25 + r / 14.0)          # clareira mais plana
    return h

def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="floresta_enevoada.blend")
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



# ---------------------------------------------------------------------------
# Geometria e materiais (utilitários comuns aos cenários)
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


def mat_forest_floor():
    m = Mat("M_Chao_Floresta")
    obj = m.texcoord().outputs["Object"]
    n1 = m.noise(obj, 0.6, 6.0, 0.6)
    n2 = m.noise(obj, 9.0, 8.0, 0.65)
    g = m.math("ADD", m.math("MULTIPLY", n1.outputs["Fac"], 0.5), m.math("MULTIPLY", n2.outputs["Fac"], 0.5))
    soil = m.ramp(g, [(0.3, (0.012, 0.009, 0.007)), (0.55, (0.035, 0.026, 0.018)), (0.8, (0.06, 0.045, 0.03))])
    litter = m.ramp(m.noise(obj, 30.0, 4.0, 0.6).outputs["Fac"],
                    [(0.3, (0.05, 0.028, 0.012)), (0.6, (0.09, 0.055, 0.025)), (0.85, (0.03, 0.02, 0.012))])
    mask = m.maprange(n1.outputs["Fac"], 0.45, 0.6)
    col = m.mix(mask, soil.outputs["Color"], litter.outputs["Color"])
    moss = m.maprange(m.noise(obj, 1.8, 6.0, 0.6).outputs["Fac"], 0.6, 0.7)
    col = m.mix(m.math("MULTIPLY", moss, 0.8), col, (0.015, 0.03, 0.01))
    m.set("Base Color", col)
    m.set("Roughness", 0.9)
    m.set("Normal", m.bump(m.math("ADD", n2.outputs["Fac"], m.math("MULTIPLY", mask, 0.4)), 0.8, 0.03))
    return m.mat


def mat_leaf_dry():
    m = Mat("M_Folha_Seca")
    rnd = m.node("ShaderNodeObjectInfo").outputs["Random"]
    col = m.ramp(rnd, [(0.0, (0.035, 0.018, 0.008)), (0.3, (0.09, 0.045, 0.012)), (0.6, (0.13, 0.075, 0.02)),
                       (0.85, (0.06, 0.05, 0.02)), (1.0, (0.1, 0.03, 0.01))])
    veins = m.noise(m.texcoord().outputs["UV"], 40.0, 3.0, 0.6)
    c = m.mix(0.3, col.outputs["Color"], m.ramp(veins.outputs["Fac"], [(0.3, (0.5, 0.5, 0.5)), (0.7, (1, 1, 1))]).outputs["Color"],
              "MULTIPLY")
    m.set("Base Color", c)
    m.set("Roughness", 0.75)
    m.set("Subsurface Weight", 0.15)
    m.set("Normal", m.bump(veins.outputs["Fac"], 0.3, 0.002))
    return m.mat


def mat_fern():
    m = Mat("M_Feto_Seco")
    rnd = m.node("ShaderNodeObjectInfo").outputs["Random"]
    col = m.ramp(rnd, [(0.0, (0.02, 0.04, 0.012)), (0.5, (0.045, 0.05, 0.015)), (1.0, (0.08, 0.05, 0.015))])
    m.set("Base Color", col.outputs["Color"])
    m.set("Roughness", 0.7)
    m.set("Subsurface Weight", 0.2)
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


# ---------------------------------------------------------------------------
# Árvores (curvas com raio por ponto)
# ---------------------------------------------------------------------------
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


def make_hero_tree(col, bark):
    """Árvore da clareira, com um ramo grosso horizontal para o balanço."""
    r_ = random.Random(77)
    cu = bpy.data.curves.new("Arvore_Heroi", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 1.0
    cu.bevel_resolution = 3
    cu.use_fill_caps = True
    cu.resolution_u = 3
    base = HERO_TREE
    trunk, tr = grow(base + Vector((0, 0, -0.4)), (0.08, -0.05, 1), 17.0, 0.62, 0.08, 20, 0.07, r_, up_bias=0.1)
    spline(cu, trunk, tr)
    # ramo do balanço: sai a ~3.6 m e estende-se por cima da clareira, a descair
    i0 = 4
    limb = [trunk[i0]]
    lr = [0.3]
    target = Vector((SWING_C.x + 1.4, SWING_C.y + 0.05, LIMB_Z - 0.25))
    for i in range(1, 13):
        t = i / 12
        p = trunk[i0].lerp(target, t)
        p.z += math.sin(math.pi * t) * 0.55 + r_.gauss(0, 0.04)
        p.y += r_.gauss(0, 0.05)
        limb.append(p)
        lr.append(0.3 - 0.22 * t)
    spline(cu, limb, lr)
    # galhos e raízes
    for i in range(7, len(trunk) - 1):
        if r_.random() > 0.6:
            continue
        az = r_.uniform(0, 2 * math.pi)
        d = Vector((math.cos(az), math.sin(az), r_.uniform(0.1, 0.8)))
        br, brr = grow(trunk[i], d, 17 * (1 - i / 20) * 0.5 + 1, tr[i] * 0.55, 0.012, 9, 0.35, r_, droop=0.15)
        spline(cu, br, brr)
        for j in range(3, len(br) - 1):
            if r_.random() > 0.5:
                continue
            d2 = (br[j + 1] - br[j]).normalized() + Vector((r_.gauss(0, 1), r_.gauss(0, 1), r_.gauss(0.2, 1)))
            tw, twr = grow(br[j], d2, 1.8, brr[j] * 0.6, 0.006, 6, 0.45, r_)
            spline(cu, tw, twr)
    for j in range(4, len(limb) - 1, 2):
        d2 = Vector((r_.gauss(0, 0.5), r_.gauss(0, 1), r_.uniform(0.3, 1.0)))
        tw, twr = grow(limb[j], d2, r_.uniform(0.8, 2.0), lr[j] * 0.5, 0.006, 6, 0.45, r_)
        spline(cu, tw, twr)
    for k in range(9):
        az = 2 * math.pi * k / 9 + r_.uniform(-0.3, 0.3)
        reach = r_.uniform(2.0, 4.2)
        z0 = r_.uniform(0.5, 1.1)
        pts, rad = [], []
        for i in range(13):
            t = i / 12
            rr = reach * t
            z = z0 * (1 - t) ** 1.5 + 0.25 * math.sin(math.pi * min(1, t * 1.3)) - 0.3 * t ** 3
            p = base + Vector((math.cos(az) * (rr + 0.15), math.sin(az) * (rr + 0.15), z))
            p.z += ground_height(p.x, p.y) - ground_height(base.x, base.y)
            pts.append(p)
            rad.append(0.36 * (1 - t) + 0.025)
        spline(cu, pts, rad)
    cu.materials.append(bark)
    obj = new_object("Arvore_Heroi_Clareira", cu, col)
    obj.location.z = ground_height(base.x, base.y)
    return obj, limb


def scatter_trees(col, models):
    placed = []
    r_ = random.Random(5)
    tries = 0
    while len(placed) < 170 and tries < 6000:
        tries += 1
        a = r_.uniform(0, 2 * math.pi)
        r = CLEAR_R + 0.8 + (FOREST_R - CLEAR_R) * math.sqrt(r_.random()) ** 1.3
        x, y = math.cos(a) * r, math.sin(a) * r
        if math.hypot(x - HERO_TREE.x, y - HERO_TREE.y) < 3.0:
            continue
        # corredor livre para a câmara principal (vinda de -Y)
        if abs(x) < 1.6 and -16 < y < -CLEAR_R:
            continue
        mind = 2.2 if r < 16 else 2.8
        if any(math.hypot(x - px, y - py) < mind for px, py in placed):
            continue
        placed.append((x, y))
        e = bpy.data.objects.new(f"Arvore_{len(placed):03d}", None)
        e.instance_type = "COLLECTION"
        e.instance_collection = r_.choice(models)
        e.location = (x, y, ground_height(x, y))
        s = r_.uniform(0.8, 1.25)
        e.scale = (s, s, s * r_.uniform(0.9, 1.15))
        e.rotation_euler = (r_.gauss(0, 0.03), r_.gauss(0, 0.03), r_.uniform(0, 2 * math.pi))
        col.objects.link(e)
    return placed


# ---------------------------------------------------------------------------
# Chão, vegetação e folhas
# ---------------------------------------------------------------------------
def build_ground(col, mat):
    R = FOREST_R + 8
    n = 180
    xs = np.linspace(-R, R, n)
    verts, dens, leaves = [], [], []
    for y in xs:
        for x in xs:
            verts.append((x, y, ground_height(x, y)))
            r = math.hypot(x, y)
            fern = min(1.0, max(0.0, (r - CLEAR_R * 0.75) / 3.0)) * (1.0 if r < 24 else max(0.15, 1 - (r - 24) / 12))
            dens.append(fern)
            leaves.append((0.55 + 0.45 * min(1.0, r / 8.0)) * (1.0 if r < 20 else max(0.1, 1 - (r - 20) / 15)))
    faces = [(j * n + i, j * n + i + 1, (j + 1) * n + i + 1, (j + 1) * n + i) for j in range(n - 1) for i in range(n - 1)]
    me = bpy.data.meshes.new("Chao")
    me.from_pydata(verts, [], faces)
    me.materials.append(mat)
    me.shade_smooth()
    obj = new_object("Chao_Floresta", me, col)
    vg = obj.vertex_groups.new(name="densidade_fetos")
    vl = obj.vertex_groups.new(name="densidade_folhas")
    for i, (d, l_) in enumerate(zip(dens, leaves)):
        vg.add([i], d, "REPLACE")
        vl.add([i], l_, "REPLACE")
    sub = obj.modifiers.new("Subdivisao", "SUBSURF")
    sub.levels, sub.render_levels = 0, 1
    return obj


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


def make_fern_mesh(name, seed):
    """Tufo de fetos: frondes curvas (eixo +X = para cima, para as partículas)."""
    r_ = random.Random(seed)
    bm = bmesh.new()
    fronds = r_.randint(6, 9)
    for f in range(fronds):
        az = 2 * math.pi * f / fronds + r_.uniform(-0.2, 0.2)
        ln = r_.uniform(0.35, 0.65)
        out = Vector((0, math.cos(az), math.sin(az)))
        prev = None
        segs = 8
        for i in range(segs + 1):
            t = i / segs
            height = math.sin(t * math.pi * 0.55) * ln * 0.75
            p = out * (t * ln) + Vector((height - t * t * 0.12, 0, 0))
            side = out.cross(Vector((1, 0, 0))).normalized()
            w = (1 - t) * 0.07 + 0.01
            a = bm.verts.new(p + side * w)
            c = bm.verts.new(p - side * w)
            if prev:
                bm.faces.new((prev[0], a, c, prev[1]))
            prev = (a, c)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    return me


def build_vegetation(ground, models_col, c_veg, mats):
    leaf_col = collection("_MODELOS_FOLHAS", models_col)
    leaves = []
    for i in range(4):
        me = make_leaf_mesh(f"Folha_{i}", rng.uniform(0.08, 0.13), rng.uniform(0.05, 0.085), rng.uniform(0.008, 0.03), i)
        me.materials.append(mats["leaf"])
        leaves.append(new_object(f"Folha_Modelo_{i}", me, leaf_col))
    fern_col = collection("_MODELOS_FETOS", models_col)
    for i in range(3):
        me = make_fern_mesh(f"Feto_{i}", i)
        me.materials.append(mats["fern"])
        ob = new_object(f"Feto_Modelo_{i}", me, fern_col)
        # brisa: ondulação leve e animada
        wave = ob.modifiers.new("Brisa", "WAVE")
        wave.use_normal = False
        wave.use_x = False
        wave.use_y = True
        wave.height = 0.03
        wave.width = 0.6
        wave.speed = 0.012
        wave.narrowness = 1.0
    # partículas de cabelo: folhas no chão e tufos de fetos
    for name, colx, count, vg, size, rand, phase in (("Folhas_Chao", leaf_col, 110000, "densidade_folhas", 1.0, 0.5, 1.0),
                                                     ("Fetos", fern_col, 4500, "densidade_fetos", 1.0, 0.6, 1.0)):
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
        st.particle_size = size
        st.size_random = rand
        st.use_rotations = True
        st.rotation_mode = "NOR"
        st.phase_factor_random = 2.0 * phase
        st.rotation_factor_random = 0.08 if name == "Fetos" else 0.35
        st.use_emit_random = True
        st.emit_from = "FACE"
        ps.vertex_group_density = vg
        ps.seed = rng.randint(0, 9999)
    return leaves


def build_falling_leaves(col, leaves):
    """Folhas secas a cair devagar sobre a clareira, empurradas pelo vento."""
    me = bpy.data.meshes.new("Emissor_Folhas")
    s = 16
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    em = new_object("Emissor_Folhas_A_Cair", me, col)
    em.location = (0, 0, 13)
    em.hide_render = True
    em.display_type = "WIRE"
    mod = em.modifiers.new("Folhas_A_Cair", "PARTICLE_SYSTEM")
    ps = mod.particle_system
    st = ps.settings
    st.name = "PS_Folhas_A_Cair"
    st.type = "EMITTER"
    st.count = 500
    st.frame_start = -300
    st.frame_end = 240
    st.lifetime = 420
    st.emit_from = "FACE"
    st.normal_factor = 0.0
    st.use_rotations = True
    st.rotation_mode = "NONE"
    st.angular_velocity_mode = "RAND"
    st.angular_velocity_factor = 2.5
    st.use_dynamic_rotation = True
    st.brownian_factor = 0.35
    st.damping = 0.02
    st.effector_weights.gravity = 0.045
    st.render_type = "OBJECT"
    st.instance_object = leaves[0]
    st.particle_size = 1.0
    st.size_random = 0.4
    st.use_dead = False
    ps.point_cache.frame_start = -300
    ps.point_cache.frame_end = 250
    ps.seed = 11
    bpy.ops.object.effector_add(type="WIND", location=(-14, 0, 6), rotation=(0, math.radians(90), 0))
    wind = bpy.context.active_object
    wind.name = "VENTO_Brisa"
    for c in list(wind.users_collection):
        c.objects.unlink(wind)
    col.objects.link(wind)
    wind.field.strength = 0.55
    wind.field.noise = 1.2
    wind.field.flow = 0.3
    return em


# ---------------------------------------------------------------------------
# Objetos fora de lugar
# ---------------------------------------------------------------------------
def build_swing(col, wood, rope_mat, limb):
    # o ponto do ramo por cima do balanço
    best = min(limb, key=lambda p: abs(p.x - SWING_C.x))
    top_z = best.z + HERO_TREE.z + ground_height(HERO_TREE.x, HERO_TREE.y) - 0.24
    pivot = bpy.data.objects.new("BALANCO_Pivot", None)
    pivot.empty_display_type = "PLAIN_AXES"
    col.objects.link(pivot)
    pivot.location = (SWING_C.x, SWING_C.y, top_z)
    seat_z = ground_height(SWING_C.x, SWING_C.y) + 0.55
    L = top_z - seat_z
    b = Builder()
    b.box((0, 0, -L), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.62, 0.22, 0.035))
    for sx in (-0.26, 0.26):
        b.box((sx, 0, -L - 0.02), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.05, 0.24, 0.01))
    seat = b.to_object("Balanco_Assento", col, [wood])
    seat.parent = pivot
    seat.modifiers.new("Bevel", "BEVEL").width = 0.006
    cu = bpy.data.curves.new("Balanco_Cordas", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.011
    cu.bevel_resolution = 2
    for sx in (-0.26, 0.26):
        for sy in (-0.07, 0.07):
            spline(cu, [Vector((sx * 0.9, sy * 0.3, 0.02)), Vector((sx, sy, -L + 0.02))], [1, 1])
    cu.materials.append(rope_mat)
    ropes = new_object("Balanco_Cordas", cu, col)
    ropes.parent = pivot
    # nó à volta do ramo
    b = Builder()
    for sx in (-0.23, 0.23):
        b.ring((sx, 0, 0.08), Euler((0, math.pi / 2, 0)).to_matrix(), 0.13, 0.016, 1.0, 16, 6)
    knots = b.to_object("Balanco_Nos", col, [rope_mat], smooth=True)
    knots.parent = pivot
    # o balanço mexe sozinho, muito devagar
    pivot.rotation_euler = (math.radians(6), 0, 0)
    pivot.keyframe_insert("rotation_euler", frame=1, index=0)
    pivot.rotation_euler = (math.radians(-5), 0, 0)
    pivot.keyframe_insert("rotation_euler", frame=60, index=0)
    pivot.rotation_euler = (math.radians(4.5), 0, 0)
    pivot.keyframe_insert("rotation_euler", frame=120, index=0)
    pivot.rotation_euler = (math.radians(-4), 0, 0)
    pivot.keyframe_insert("rotation_euler", frame=180, index=0)
    pivot.rotation_euler = (math.radians(6), 0, 0)
    pivot.keyframe_insert("rotation_euler", frame=240, index=0)
    return pivot


def build_chair(col, wood):
    """Cadeira de madeira velha, virada para as árvores (de costas para quem chega)."""
    b = Builder()
    gz = ground_height(CHAIR_C.x, CHAIR_C.y)
    yaw = math.radians(8)
    M = Matrix.Translation((CHAIR_C.x, CHAIR_C.y, gz)) @ Euler((math.radians(1.5), math.radians(-2), yaw)).to_matrix().to_4x4()
    b.box((0, 0, 0.45), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.44, 0.42, 0.035), M=M)
    for sx in (-0.19, 0.19):
        for sy in (-0.18, 0.18):
            b.box((sx, sy, 0.22), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.035, 0.035, 0.45), M=M)
        b.box((sx, -0.185, 0.72), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.035, 0.035, 0.52), M=M)   # pés de trás sobem
    for z in (0.62, 0.78, 0.94):
        b.box((0, -0.185, z), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.38, 0.02, 0.05), M=M)
    for sy in (-0.18, 0.18):
        b.box((0, sy, 0.12), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.36, 0.02, 0.025), M=M)
    ch = b.to_object("Cadeira_Madeira", col, [wood])
    ch.modifiers.new("Bevel", "BEVEL").width = 0.005
    # o encosto fica do lado -Y, ou seja, a cadeira "olha" para +Y (para dentro da floresta)
    return ch


def build_lantern(col, mats):
    """Lanterna de petróleo, apagada, com o vidro enegrecido."""
    gz = ground_height(LANTERN_C.x, LANTERN_C.y)
    c = Vector((LANTERN_C.x, LANTERN_C.y, gz))
    b = Builder()
    b.cylinder(c, c + Vector((0, 0, 0.06)), 0.085, 0.08, 20, mat=0)
    b.cylinder(c + Vector((0, 0, 0.23)), c + Vector((0, 0, 0.27)), 0.07, 0.03, 20, mat=0)
    b.cylinder(c + Vector((0, 0, 0.27)), c + Vector((0, 0, 0.3)), 0.025, 0.02, 12, mat=0)
    for k in range(4):
        a = k * math.pi / 2 + 0.4
        p0 = c + Vector((math.cos(a) * 0.075, math.sin(a) * 0.075, 0.06))
        p1 = c + Vector((math.cos(a) * 0.065, math.sin(a) * 0.065, 0.23))
        b.cylinder(p0, p1, 0.004, 0.004, 6, mat=0)
    b.ring(c + Vector((0, 0, 0.36)), Matrix.Identity(3), 0.07, 0.004, 1.0, 20, 6, mat=0)
    lamp = b.to_object("Lanterna_Petroleo", col, [mats["rust"]], smooth=True)
    b = Builder()
    b.ico(c + Vector((0, 0, 0.145)), 0.06, (1.0, 1.0, 1.35), 3, 0.0)
    glass = b.to_object("Lanterna_Vidro_Enegrecido", col, [mats["soot_glass"]], smooth=True)
    lamp.rotation_euler = (0, 0, 0)
    return lamp


def build_debris(col, bark, stone):
    """Ramos caídos, troncos no chão e pedras."""
    cu = bpy.data.curves.new("Ramos_Caidos", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 1.0
    cu.bevel_resolution = 1
    cu.use_fill_caps = True
    r_ = random.Random(9)
    for _ in range(80):
        a = r_.uniform(0, 2 * math.pi)
        r = r_.uniform(2.5, 25)
        x, y = math.cos(a) * r, math.sin(a) * r
        az = r_.uniform(0, 2 * math.pi)
        ln = r_.uniform(0.6, 2.5)
        pts, rad = [], []
        for i in range(7):
            t = i / 6
            p = Vector((x + math.cos(az) * ln * t, y + math.sin(az) * ln * t, 0)) + Vector((r_.gauss(0, 0.04), r_.gauss(0, 0.04), 0))
            p.z = ground_height(p.x, p.y) + 0.02
            pts.append(p)
            rad.append(0.04 * (1 - t * 0.7) * r_.uniform(0.6, 1.6))
        spline(cu, pts, rad)
    # dois troncos tombados
    for (x, y, az, ln, rr) in ((6.5, 7.5, 0.6, 7.0, 0.35), (-9.0, -4.0, 2.2, 6.0, 0.3)):
        pts, rad = [], []
        for i in range(9):
            t = i / 8
            p = Vector((x + math.cos(az) * ln * t, y + math.sin(az) * ln * t, 0))
            p.z = ground_height(p.x, p.y) + rr * 0.8
            pts.append(p)
            rad.append(rr * (1 - 0.3 * t))
        spline(cu, pts, rad)
    cu.materials.append(bark)
    new_object("Ramos_E_Troncos_Caidos", cu, col)
    b = Builder()
    for _ in range(60):
        a = r_.uniform(0, 2 * math.pi)
        r = r_.uniform(3, 30)
        x, y = math.cos(a) * r, math.sin(a) * r
        s = r_.uniform(0.08, 0.5)
        b.ico((x, y, ground_height(x, y) + s * 0.2), s, (1, r_.uniform(0.6, 1), r_.uniform(0.4, 0.7)), 2, 0.35,
              rot=(0, 0, r_.uniform(0, 6)))
    rocks = b.to_object("Pedras_Musgo", col, [stone], smooth=True)
    return rocks


# ---------------------------------------------------------------------------
# Luz, variantes, câmaras
# ---------------------------------------------------------------------------
def make_worlds():
    night = bpy.data.worlds.new("Mundo_Noite")
    night.use_nodes = True
    bg = night.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.008, 0.012, 0.025, 1)
    bg.inputs["Strength"].default_value = 1.0
    day = bpy.data.worlds.new("Mundo_Dia_Encoberto")
    day.use_nodes = True
    nt = day.node_tree
    bg = nt.nodes["Background"]
    sky = nt.nodes.new("ShaderNodeTexGradient")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.45
    ramp.color_ramp.elements[0].color = (0.18, 0.19, 0.19, 1)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (0.62, 0.64, 0.65, 1)
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.6
    bpy.context.scene.world = night
    return night, day


def build_variants(v_night, v_day, mats):
    moon = light("LUZ_Luar", "SUN", v_night, (0, 20, 12), 3.2, (0.55, 0.67, 1.0), angle=math.radians(1.0))
    moon.rotation_euler = MOON_DIR.to_track_quat("-Z", "Y").to_euler()
    # luar suave na clareira (a abertura nas copas)
    cl = light("LUZ_Clareira_Ceu", "AREA", v_night, (0.5, 2.5, 14.0), 90.0, (0.5, 0.6, 0.95), shape="DISK", size=10.0)
    cl.visible_camera = False
    fog_n = mats["fog_night"]
    fog_d = mats["fog_day"]
    for tag, col, mat in (("Noite", v_night, fog_n), ("Dia", v_day, fog_d)):
        me = bpy.data.meshes.new(f"Nevoa_{tag}")
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0, 0, 6.5)) @
                              Matrix.Diagonal((2 * FOREST_R, 2 * FOREST_R, 15.0, 1)))
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mat)
        new_object(f"ATMOS_Nevoa_{tag}", me, col)
    # dia: sol difuso por trás das nuvens (sem sombras duras)
    sun = light("LUZ_Sol_Encoberto", "SUN", v_day, (0, 0, 20), 0.6, (0.85, 0.88, 0.9), angle=math.radians(35))
    sun.rotation_euler = Vector((0.3, -0.4, -1.0)).normalized().to_track_quat("-Z", "Y").to_euler()


def build_cameras(col):
    cams = {}

    def cam(name, loc, target, lens, fstop=None, focus=None):
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        cd.sensor_width = 36
        cd.clip_start = 0.05
        cd.clip_end = 300
        if fstop:
            cd.dof.use_dof = True
            cd.dof.aperture_fstop = fstop
            cd.dof.focus_distance = focus
        loc = Vector(loc)
        loc.z += ground_height(loc.x, loc.y)
        ob = new_object(name, cd, col)
        ob.location = loc
        ob.rotation_euler = look_at_rotation(loc, target)
        cams[name] = ob
        return ob

    gz = ground_height(SWING_C.x, SWING_C.y)
    cam("CAM_1_Chegada_Clareira", (0.35, -6.8, 1.55), (0.1, SWING_C.y, gz + 1.75), 45, 5.6, 10.3)
    cam("CAM_2_Balanco_Perto", (2.6, -0.9, 1.25), (SWING_C.x, SWING_C.y, gz + 0.8), 50, 2.8, 4.8)
    cam("CAM_3_Floresta_Profunda", (-2.5, -3.0, 1.6), (-16.0, -12.0, 1.8), 28, 8.0, 9.0)
    cam("CAM_4_Raizes_Rente_Chao", (-0.6, -0.9, 0.32), (HERO_TREE.x, HERO_TREE.y, 0.9), 26, 4.0, 5.3)
    cam("CAM_5_Alto_Observador", (3.2, -4.2, 6.8), (0.0, 2.2, 0.3), 24)
    cam("CAM_6_Cadeira_Costas", (0.3, -2.4, 1.1), (CHAIR_C.x + 0.2, CHAIR_C.y + 6.0, 1.0), 40, 4.0, 3.3)
    cam("CAM_7_Lanterna_Detalhe", (-0.35, -0.55, 0.35), (LANTERN_C.x, LANTERN_C.y, 0.18), 60, 2.8, 1.05)
    bpy.context.scene.camera = cams["CAM_1_Chegada_Clareira"]
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

    marker("PERSONAGEM_1_Beira_Clareira", (0.1, -4.2), (0, 1), "parado à entrada da clareira, a olhar para o balanço")
    marker("PERSONAGEM_2_Entre_Arvores", (-3.5, -8.5), (0.35, 1), "a caminhar entre as árvores, a chegar")
    marker("PERSONAGEM_3_Junto_Cadeira", (CHAIR_C.x - 0.7, CHAIR_C.y - 0.6), (0.6, 1), "ao lado da cadeira, sem se sentar")


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
    scn.cycles.glossy_bounces = 1
    scn.cycles.volume_bounces = 1
    scn.cycles.volume_step_rate = 1.0
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
    scn.view_settings.exposure = 1.0


def film_look(glare=(0.8, 0.35), lens=(0.01, 0.006), sat=0.8, lift=(1.0, 1.0, 1.0), gamma=(1.0, 1.0, 1.0),
              gain=(1.0, 1.0, 1.0), mask_size=(0.95, 0.85), blur=300, vignette_min=0.5, grain=0.1):
    """Look de película no Compositor (halo, lente, cor, vinheta, grão). Funciona no Blender 4.x e 5.x."""
    scn = bpy.context.scene
    v5 = not hasattr(scn, "node_tree")
    if v5:   # Blender 5: o compositor é um grupo de nós atribuído à cena
        nt = bpy.data.node_groups.new("Look_Pelicula", "CompositorNodeTree")
        nt.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        scn.compositing_node_group = nt
    else:
        scn.use_nodes = True
        nt = scn.node_tree
        nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new

    def menu(node, name, value, attr, attr_value):
        if hasattr(node, attr):
            setattr(node, attr, attr_value)
            return
        for s in node.inputs:
            if s.name == name and s.type == "MENU":
                s.default_value = value

    def mix(fac, a, b, blend):
        if v5:
            n = N("ShaderNodeMix")
            n.data_type = "RGBA"
            n.blend_type = blend
            sock(n, "Factor_Float").default_value = fac
            L(a, sock(n, "A_Color"))
            L(b, sock(n, "B_Color"))
            return sock(n, "Result_Color", out=True)
        n = N("CompositorNodeMixRGB")
        n.blend_type = blend
        n.inputs["Fac"].default_value = fac
        L(a, n.inputs[1])
        L(b, n.inputs[2])
        return n.outputs["Image"]

    rl = N("CompositorNodeRLayers")
    img = rl.outputs["Image"]
    if glare:
        g = N("CompositorNodeGlare")
        menu(g, "Type", "Fog Glow", "glare_type", "FOG_GLOW")
        try_set(g, "Threshold", glare[0])
        try_set(g, "Strength", glare[1])
        L(img, g.inputs["Image"])
        img = g.outputs["Image"]
    if lens:
        ld = N("CompositorNodeLensdist")
        try_set(ld, "Distortion", lens[0])
        try_set(ld, "Dispersion", lens[1])
        L(img, ld.inputs["Image"])
        img = ld.outputs["Image"]
    hs = N("CompositorNodeHueSat")
    try_set(hs, "Saturation", sat)
    L(img, hs.inputs["Image"])
    cb = N("CompositorNodeColorBalance")
    menu(cb, "Type", "Lift/Gamma/Gain", "correction_method", "LIFT_GAMMA_GAIN")
    try_set(cb, "Lift", lift)
    try_set(cb, "Gamma", gamma)
    try_set(cb, "Gain", gain)
    cb_out = cb.outputs["Image"]
    if v5:   # no 5.x o Lift/Gamma/Gain trabalha em linear; estes Gamma reproduzem o grading do 4.x
        g0, g1 = N("ShaderNodeGamma"), N("ShaderNodeGamma")
        g0.inputs["Gamma"].default_value = 1 / 2.2
        g1.inputs["Gamma"].default_value = 2.2
        L(hs.outputs["Image"], g0.inputs["Color"])
        L(g0.outputs["Color"], cb.inputs["Image"])
        L(cb.outputs["Image"], g1.inputs["Color"])
        cb_out = g1.outputs["Color"]
    else:
        L(hs.outputs["Image"], cb.inputs["Image"])
    # vinheta
    mk = N("CompositorNodeEllipseMask")
    if not try_set(mk, "Size", mask_size):
        mk.width, mk.height = mask_size
    bl = N("CompositorNodeBlur")
    menu(bl, "Type", "Fast Gaussian", "filter_type", "FAST_GAUSS")
    if not try_set(bl, "Size", (blur, blur)):
        bl.size_x = bl.size_y = blur
    L(mk.outputs["Mask"], bl.inputs["Image"])
    mr = N("ShaderNodeMapRange" if v5 else "CompositorNodeMapRange")
    mr.inputs["From Min"].default_value = 0.0
    mr.inputs["From Max"].default_value = 1.0
    mr.inputs["To Min"].default_value = vignette_min
    mr.inputs["To Max"].default_value = 1.0
    L(bl.outputs["Image"], mr.inputs["Value"])
    img = mix(1.0, cb_out, mr.outputs[0], "MULTIPLY")
    # grão
    if v5:
        co = N("CompositorNodeImageCoordinates")
        L(rl.outputs["Image"], co.inputs["Image"])
        wn = N("ShaderNodeTexWhiteNoise")
        L(co.outputs["Pixel"], wn.inputs["Vector"])
        noise_out = wn.outputs["Value"]
    else:
        tn = N("CompositorNodeTexture")
        tn.texture = bpy.data.textures.new("T_Grao", "NOISE")
        noise_out = tn.outputs["Value"]
    gb = N("CompositorNodeBlur")
    menu(gb, "Type", "Gaussian", "filter_type", "GAUSS")
    if not try_set(gb, "Size", (1, 1)):
        gb.size_x = gb.size_y = 1
    L(noise_out, gb.inputs["Image"])
    img = mix(grain, img, gb.outputs["Image"], "OVERLAY")
    if v5:
        go = N("NodeGroupOutput")
        L(img, go.inputs["Image"])
    else:
        L(img, N("CompositorNodeComposite").inputs["Image"])
    L(img, N("CompositorNodeViewer").inputs["Image"])
    for i, n in enumerate(nt.nodes):
        n.location = (i * 220 - 1400, 0)


def setup_compositor():
    film_look(glare=(0.9, 0.25), lens=None, sat=0.55, lift=(0.98, 1.0, 1.02), gain=(0.98, 1.0, 1.0), vignette_min=0.45, grain=0.12)


README_TEXT = """FLORESTA ENEVOADA — como usar
==============================

OBJETOS FORA DE LUGAR (04_OBJETOS — ligue um, dois ou os três):
  OBJ_1_Balanco (baloiça sozinho) | OBJ_2_Cadeira | OBJ_3_Lanterna

NOITE / DIA:
  05_LUZ: ative VAR_Noite OU VAR_Dia (só uma)
  e em World Properties escolha o mundo correspondente: Mundo_Noite / Mundo_Dia_Encoberto.
  Exposição recomendada: noite 1.0, dia 0.0 (Render > Color Management).

ANIMAÇÃO: frames 1-240 — névoa a derivar, folhas a cair (vento: VENTO_Brisa),
fetos a ondular, balanço a mexer. Para as folhas a cair, reproduza a animação
desde o início no viewport para a simulação ser calculada.
"""


def main():
    args = parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.name = "Floresta_Enevoada"
    c_models = collection("_MODELOS")
    c_forest = collection("01_FLORESTA")
    c_ground = collection("02_CHAO_VEGETACAO")
    c_fx = collection("03_FOLHAS_VENTO")
    c_obj = collection("04_OBJETOS")
    o_cols = [collection(n, c_obj) for n in ("OBJ_1_Balanco", "OBJ_2_Cadeira", "OBJ_3_Lanterna")]
    c_light = collection("05_LUZ")
    v_night = collection("VAR_Noite", c_light)
    v_day = collection("VAR_Dia", c_light)
    c_cam = collection("06_CAMARAS")
    c_char = collection("07_PERSONAGEM")

    mats = {
        "bark": mat_bark(), "floor": mat_forest_floor(), "leaf": mat_leaf_dry(), "fern": mat_fern(),
        "wood": mat_wood("M_Madeira_Velha_Cinzenta", dark=1.1),
        "rope": mat_simple("M_Corda_Velha", (0.16, 0.13, 0.09), 0.9, noise_scale=150, bump=0.5),
        "rust": mat_simple("M_Ferro_Ferrugem", (0.09, 0.045, 0.02), 0.7, metal=0.4, noise_scale=40, bump=0.4),
        "soot_glass": mat_simple("M_Vidro_Enegrecido", (0.02, 0.02, 0.02), 0.25),
        "stone": mat_simple("M_Pedra_Musgo", (0.05, 0.06, 0.04), 0.9, noise_scale=6, bump=0.6),
        "fog_night": mat_volume_fog("M_Nevoa_Noite", 0.075, 0.007, (0.75, 0.8, 0.9)),
        "fog_day": mat_volume_fog("M_Nevoa_Dia", 0.05, 0.014, (0.95, 0.96, 0.97), height=3.5),
    }
    print("> árvores")
    models = []
    for i in range(7):
        mc = collection(f"_ARVORE_{i}", c_models)
        make_tree(f"Arvore_Modelo_{i}", mc, mats["bark"], 100 + i, rng.uniform(13, 20), rng.uniform(0.28, 0.5),
                  twist=rng.uniform(0.08, 0.16), lean=rng.uniform(0.05, 0.2))
        models.append(mc)
    hero, limb = make_hero_tree(c_forest, mats["bark"])
    scatter_trees(c_forest, models)
    print("> chão e vegetação")
    ground = build_ground(c_ground, mats["floor"])
    leaves = build_vegetation(ground, c_models, c_ground, mats)
    build_debris(c_ground, mats["bark"], mats["stone"])
    build_falling_leaves(c_fx, leaves)
    print("> objetos, luz, câmaras")
    build_swing(o_cols[0], mats["wood"], mats["rope"], limb)
    build_chair(o_cols[1], mats["wood"])
    build_lantern(o_cols[2], mats)
    night, day = make_worlds()
    build_variants(v_night, v_day, mats)
    build_cameras(c_cam)
    build_markers(c_char)
    setup_render()
    setup_compositor()
    bpy.data.texts.new("LEIA-ME").write(README_TEXT)

    vl = bpy.context.view_layer
    vl.layer_collection.children["_MODELOS"].exclude = True
    ol = vl.layer_collection.children["04_OBJETOS"]
    for i, c in enumerate(o_cols):
        ol.children[c.name].exclude = i != 0
    ll = vl.layer_collection.children["05_LUZ"]
    ll.children["VAR_Dia"].exclude = True
    scn.frame_set(1)
    out = os.path.abspath(args.out)
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    print(f"> guardado: {out}")
    if args.render:
        render_previews(args, o_cols, night, day)


PREVIEWS = [   # (ficheiro, câmara, objetos ligados, dia?)
    ("cam1_chegada_clareira", "CAM_1_Chegada_Clareira", (0,), False),
    ("cam2_balanco_perto", "CAM_2_Balanco_Perto", (0,), False),
    ("cam3_floresta_profunda", "CAM_3_Floresta_Profunda", (0,), False),
    ("cam4_raizes_rente_chao", "CAM_4_Raizes_Rente_Chao", (0,), False),
    ("cam5_alto_observador", "CAM_5_Alto_Observador", (0, 1, 2), False),
    ("cam6_cadeira_costas", "CAM_6_Cadeira_Costas", (1,), False),
    ("cam7_lanterna_detalhe", "CAM_7_Lanterna_Detalhe", (2,), False),
    ("dia_cam1_chegada_clareira", "CAM_1_Chegada_Clareira", (0,), True),
    ("dia_cam6_cadeira_costas", "CAM_6_Cadeira_Costas", (1,), True),
]


def render_previews(args, o_cols, night, day):
    scn = bpy.context.scene
    os.makedirs(args.render, exist_ok=True)
    scn.cycles.samples = args.samples
    scn.cycles.adaptive_threshold = 0.05
    scn.cycles.volume_step_rate = 3.0
    scn.render.resolution_x = args.res
    scn.render.resolution_y = int(args.res * 9 / 16)
    scn.render.image_settings.file_format = "JPEG"
    scn.render.image_settings.quality = 90
    vl = bpy.context.view_layer
    ol = vl.layer_collection.children["04_OBJETOS"]
    ll = vl.layer_collection.children["05_LUZ"]
    # simular as folhas a cair até ao frame de render
    target = 90
    for f in range(-300, target + 1, 1):
        scn.frame_set(f)
    only = set(filter(None, args.only.split(",")))
    for fname, cam, objs, is_day in PREVIEWS:
        if only and fname not in only:
            continue
        for i, c in enumerate(o_cols):
            ol.children[c.name].exclude = i not in objs
        ll.children["VAR_Noite"].exclude = is_day
        ll.children["VAR_Dia"].exclude = not is_day
        scn.world = day if is_day else night
        scn.view_settings.exposure = 0.0 if is_day else 1.0
        scn.camera = bpy.data.objects[cam]
        scn.render.filepath = os.path.join(os.path.abspath(args.render), fname + ".jpg")
        print(f"> render {fname}")
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
