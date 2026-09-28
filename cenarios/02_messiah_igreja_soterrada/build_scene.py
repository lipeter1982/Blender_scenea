"""
Cenário 02 — Igreja gótica soterrada (para o vídeo de Messiah, 2000)

Igreja gótica enterrada, profanada, noir: salão com colunas e arcos ogivais,
abóbada com um buraco escavado por onde entra o luar, cruz invertida pendurada
por uma corrente em frente ao altar partido, bancos virados, santos
decapitados, fresco com os olhos riscados, velas. Inspirado na igreja
enterrada de "Exorcist: The Beginning".

Uso (dentro do Blender):
    blender -b -P build_scene.py -- --out igreja_soterrada.blend
Uso (módulo bpy via pip):
    python build_scene.py --out igreja_soterrada.blend --render previews --samples 64
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

SEED = 2000
rng = random.Random(SEED)

# ---------------------------------------------------------------------------
# Dimensões (metros, Z para cima, a nave corre ao longo de +Y até ao altar)
# ---------------------------------------------------------------------------
NAVE_X = 3.8           # linha das colunas
AISLE_X = 6.2          # paredes exteriores das naves laterais
LENGTH = 26.0
COL_Y = [LENGTH / 6 * k for k in range(1, 6)]   # 4.33 … 21.67
COL_R = 0.42
ARCH_SPRING, ARCH_APEX = 5.0, 7.4
NAVE_WALL_TOP = 10.0
VAULT_APEX = 14.0
AISLE_ROOF = 6.5
DAIS_Y0 = 21.9
ALTAR_Y = 23.6
CROSS_Y = 21.25
CROSS_BOTTOM = 1.2      # ponta de baixo da cruz invertida (lado da cabeça)
CROSS_LEN = 4.2
SUN_DIR = Vector((0.1, 0.3, -1.0)).normalized()
HOLE_C = Vector((-1.05, 17.9))   # centro do buraco na abóbada (planta)
HOLE_R = 1.15
FRESCO_Y = LENGTH - 0.06


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="igreja_soterrada.blend")
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


def floor_height(x, y):
    h = noise.noise(Vector((x * 0.8, y * 0.8, 1.3))) * 0.01
    h += noise.noise(Vector((x * 6.0, y * 6.0, 4.1))) * 0.003
    return h


# ---------------------------------------------------------------------------
# Geometria
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


# ---------------------------------------------------------------------------
# Materiais
# ---------------------------------------------------------------------------
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


def mat_ashlar(name, brick_w=0.62, row_h=0.31, tone=1.0):
    """Cantaria gótica: blocos regulares com juntas, sujidade, humidade e salitre."""
    m = Mat(name)
    tc = m.texcoord()
    uv = tc.outputs["UV"]
    obj = tc.outputs["Object"]
    br = m.node("ShaderNodeTexBrick", offset=0.5, offset_frequency=2, squash=1.0, squash_frequency=2)
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Mortar Size"].default_value = 0.012
    br.inputs["Mortar Smooth"].default_value = 0.3
    br.inputs["Brick Width"].default_value = brick_w
    br.inputs["Row Height"].default_value = row_h
    br.inputs["Color1"].default_value = (1, 1, 1, 1)
    br.inputs["Color2"].default_value = (0.0, 0.0, 0.0, 1)
    br.inputs["Bias"].default_value = 0.0
    warp = m.noise(uv, 1.3, 2.0, 0.5)
    wv = m.node("ShaderNodeMix", data_type="VECTOR")
    sock(wv, "Factor_Float").default_value = 0.045
    m.link(uv, sock(wv, "A_Vector"))
    m.link(warp.outputs["Color"], sock(wv, "B_Vector"))
    m.link(sock(wv, "Result_Vector", out=True), br.inputs["Vector"])
    per_block = m.node("ShaderNodeSeparateColor")
    m.link(br.outputs["Color"], per_block.inputs[0])
    k = tone
    base = m.ramp(per_block.outputs[0], [(0.0, (0.07 * k, 0.066 * k, 0.06 * k)), (0.35, (0.14 * k, 0.13 * k, 0.115 * k)),
                                          (0.7, (0.2 * k, 0.19 * k, 0.17 * k)), (1.0, (0.28 * k, 0.26 * k, 0.23 * k))]).outputs["Color"]
    # arestas dos blocos lascadas
    chipm = m.maprange(m.noise(obj, 9.0, 6.0, 0.7).outputs["Fac"], 0.6, 0.68)
    mortar_wide = m.maprange(br.outputs["Fac"], 0.0, 0.2)
    grime = m.noise(obj, 1.8, 8.0, 0.65)
    gc = m.ramp(grime.outputs["Fac"], [(0.3, (0.35, 0.34, 0.32)), (0.7, (1, 1, 1))])
    col = m.mix(1.0, base, gc.outputs["Color"], "MULTIPLY")
    mortar = br.outputs["Fac"]
    col = m.mix(m.math("MULTIPLY", mortar, 0.8), col, (0.05, 0.047, 0.042))
    # escorrências verticais
    smp = m.node("ShaderNodeMapping")
    smp.inputs["Scale"].default_value = (6.0, 6.0, 0.35)
    m.link(obj, smp.inputs["Vector"])
    streak = m.noise(smp.outputs["Vector"], 2.5, 3.0, 0.5)
    col = m.mix(m.math("MULTIPLY", m.maprange(streak.outputs["Fac"], 0.55, 0.75), 0.6), col, (0.03, 0.028, 0.025))
    # terra/humidade em baixo
    z = sep_z(m)
    wet = m.math("MULTIPLY", m.maprange(z, 0.0, 1.2, 1.0, 0.0),
                 m.maprange(m.noise(obj, 2.0, 4.0, 0.6).outputs["Fac"], 0.3, 0.7, 0.4, 1.0))
    col = m.mix(m.math("MULTIPLY", wet, 0.7), col, (0.035, 0.028, 0.02))
    m.set("Base Color", col)
    m.set("Roughness", m.mixf(wet, 0.9, 0.6))
    chips = m.noise(obj, 14.0, 8.0, 0.65)
    fine = m.noise(obj, 70.0, 4.0, 0.6)
    h = m.math("ADD", m.math("MULTIPLY", chips.outputs["Fac"], 0.6), m.math("MULTIPLY", fine.outputs["Fac"], 0.3))
    h = m.math("SUBTRACT", h, m.math("MULTIPLY", mortar, 0.8))
    h = m.math("SUBTRACT", h, m.math("MULTIPLY", m.math("MULTIPLY", chipm, mortar_wide), 0.6))
    m.set("Normal", m.bump(h, 0.8, 0.02))
    return m.mat


def mat_floor():
    m = Mat("M_Chao_Lajes_Terra")
    tc = m.texcoord()
    obj = tc.outputs["Object"]
    br = m.node("ShaderNodeTexBrick", offset=0.3, offset_frequency=1)
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Mortar Size"].default_value = 0.01
    br.inputs["Brick Width"].default_value = 0.9
    br.inputs["Row Height"].default_value = 0.7
    br.inputs["Color1"].default_value = (1, 1, 1, 1)
    br.inputs["Color2"].default_value = (0, 0, 0, 1)
    m.link(obj, br.inputs["Vector"])
    sp = m.node("ShaderNodeSeparateColor")
    m.link(br.outputs["Color"], sp.inputs[0])
    slab = m.ramp(sp.outputs[0], [(0.0, (0.07, 0.066, 0.06)), (1.0, (0.15, 0.14, 0.125))]).outputs["Color"]
    slab = m.mix(m.math("MULTIPLY", br.outputs["Fac"], 0.85), slab, (0.03, 0.026, 0.022))
    # terra e areia por cima
    dirt_attr = m.attr("dirt").outputs["Fac"]
    dn = m.noise(obj, 1.2, 6.0, 0.6)
    dirt = m.math("ADD", dirt_attr, m.maprange(dn.outputs["Fac"], 0.45, 0.75, 0.0, 0.7))
    dirt = m.math("MINIMUM", dirt, 1.0)
    earth = m.ramp(m.noise(obj, 25.0, 6.0, 0.6).outputs["Fac"],
                   [(0.3, (0.04, 0.032, 0.024)), (0.7, (0.1, 0.082, 0.062))]).outputs["Color"]
    col = m.mix(dirt, slab, earth)
    m.set("Base Color", col)
    m.set("Roughness", m.mixf(dirt, 0.6, 0.95))
    cracks = m.node("ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE")
    cracks.inputs["Scale"].default_value = 3.0
    m.link(obj, cracks.inputs["Vector"])
    h = m.math("ADD", m.noise(obj, 40.0, 6.0, 0.6).outputs["Fac"], m.maprange(cracks.outputs["Distance"], 0, 0.01, -0.5, 0))
    h = m.math("SUBTRACT", h, m.math("MULTIPLY", br.outputs["Fac"], 0.6))
    m.set("Normal", m.bump(h, 0.5, 0.01))
    return m.mat


def mat_earth(name="M_Terra"):
    m = Mat(name)
    obj = m.texcoord().outputs["Object"]
    n1 = m.noise(obj, 3.0, 8.0, 0.65)
    n2 = m.noise(obj, 40.0, 6.0, 0.6)
    g = m.math("ADD", m.math("MULTIPLY", n1.outputs["Fac"], 0.6), m.math("MULTIPLY", n2.outputs["Fac"], 0.4))
    col = m.ramp(g, [(0.3, (0.025, 0.02, 0.015)), (0.55, (0.065, 0.052, 0.04)), (0.8, (0.11, 0.09, 0.07))])
    m.set("Base Color", col.outputs["Color"])
    m.set("Roughness", 0.97)
    m.set("Normal", m.bump(g, 0.9, 0.03))
    return m.mat


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


def mat_statue_wood():
    """Madeira velha e rachada da imagem de Cristo."""
    m = Mat("M_Cristo_Madeira_Velha")
    obj = m.texcoord().outputs["Object"]
    mp = m.node("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (14.0, 14.0, 1.2)   # veio ao longo do corpo
    m.link(obj, mp.inputs["Vector"])
    grain = m.noise(mp.outputs["Vector"], 2.0, 10.0, 0.7)
    cracks = m.node("ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE")
    cracks.inputs["Scale"].default_value = 3.0
    m.link(mp.outputs["Vector"], cracks.inputs["Vector"])
    crack = m.maprange(cracks.outputs["Distance"], 0.0, 0.03, 1.0, 0.0)
    col = m.ramp(grain.outputs["Fac"], [(0.3, (0.035, 0.026, 0.02)), (0.7, (0.11, 0.085, 0.065))]).outputs["Color"]
    # restos de policromia (tinta velha a descascar)
    paint_n = m.noise(obj, 4.0, 8.0, 0.7)
    paint = m.maprange(paint_n.outputs["Fac"], 0.52, 0.6)
    col = m.mix(m.math("MULTIPLY", paint, 0.8), col, (0.2, 0.17, 0.14))
    col = m.mix(crack, col, (0.008, 0.006, 0.005))
    m.set("Base Color", col)
    m.set("Roughness", m.mixf(paint, 0.8, 0.6))
    h = m.math("SUBTRACT", grain.outputs["Fac"], m.math("MULTIPLY", crack, 0.8))
    m.set("Normal", m.bump(h, 0.6, 0.01))
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


def mat_iron():
    m = Mat("M_Ferro_Corrente")
    obj = m.texcoord().outputs["Object"]
    n = m.noise(obj, 30.0, 8.0, 0.65)
    rust = m.maprange(n.outputs["Fac"], 0.45, 0.65)
    m.set("Base Color", m.mix(rust, (0.04, 0.04, 0.042), (0.09, 0.045, 0.02)))
    m.set("Metallic", m.mixf(rust, 0.9, 0.1))
    m.set("Roughness", m.mixf(rust, 0.45, 0.9))
    m.set("Normal", m.bump(n.outputs["Fac"], 0.5, 0.005))
    return m.mat


def mat_wax():
    m = Mat("M_Cera_Velas")
    m.set("Base Color", (0.55, 0.5, 0.4))
    m.set("Roughness", 0.5)
    m.set("Subsurface Weight", 0.6)
    m.bsdf.inputs["Subsurface Radius"].default_value = (0.05, 0.03, 0.015)
    m.bsdf.inputs["Subsurface Scale"].default_value = 0.05
    return m.mat


def mat_flame():
    mat = bpy.data.materials.new("M_Chama")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (1.0, 0.55, 0.18, 1)
    em.inputs["Strength"].default_value = 60.0
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return mat


def mat_volume(name, density, anisotropy=0.3, color=(0.8, 0.82, 0.86)):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Color"].default_value = (*color, 1)
    vol.inputs["Density"].default_value = density
    vol.inputs["Anisotropy"].default_value = anisotropy
    nt.links.new(vol.outputs[0], out.inputs["Volume"])
    return mat


# ---------------------------------------------------------------------------
# Fresco com os olhos riscados (textura gerada)
# ---------------------------------------------------------------------------
def value_noise(h, w, cell, seed):
    r = np.random.default_rng(seed)
    gh, gw = h // cell + 3, w // cell + 3
    g = r.random((gh, gw)).astype(np.float32)
    ys, xs = np.arange(h) / cell, np.arange(w) / cell
    y0, x0 = ys.astype(int), xs.astype(int)
    fy, fx = ys - y0, xs - x0
    fy = (fy * fy * (3 - 2 * fy))[:, None]
    fx = (fx * fx * (3 - 2 * fx))[None, :]
    a, b = g[y0][:, x0], g[y0][:, x0 + 1]
    c, d = g[y0 + 1][:, x0], g[y0 + 1][:, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def fbm(h, w, seed, cells=(96, 32, 8), weights=(0.55, 0.3, 0.15)):
    out = np.zeros((h, w), np.float32)
    for i, (c, wt) in enumerate(zip(cells, weights)):
        out += value_noise(h, w, c, seed + i) * wt
    return out


def make_fresco_image(w_m=4.4, h_m=2.8, res=460):
    """Três santos bizantinos com auréolas; os olhos foram arrancados do reboco à faca."""
    W, H = int(w_m * res), int(h_m * res)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    X, Y = xx / res, yy / res           # metros; Y = 0 em baixo (convenção do Blender)
    img = np.ones((H, W, 3), np.float32) * np.array([0.58, 0.5, 0.38], np.float32)
    img *= (0.8 + 0.35 * fbm(H, W, 11))[..., None]
    outline = np.zeros((H, W), np.float32)
    holes = np.zeros((H, W), np.float32)     # reboco arrancado (olhos)

    def paint(mask, color, alpha=1.0, line=True):
        m = np.clip(mask, 0, 1).astype(np.float32)
        a = m[..., None] * alpha
        img[:] = img * (1 - a) + np.array(color, np.float32) * a
        if line:   # contorno escuro à maneira dos ícones
            gy, gx = np.gradient(m)
            outline[:] = np.maximum(outline, np.clip(np.sqrt(gx * gx + gy * gy) * 2.2, 0, 1))

    def ellipse(cx, cy, rx, ry, soft=40):
        return np.clip((1 - ((X - cx) / rx) ** 2 - ((Y - cy) / ry) ** 2) * soft, 0, 1)

    paint(((Y > 0.3) & (Y < 2.42)).astype(np.float32), (0.3, 0.35, 0.38), 0.9)
    for y0, y1 in ((2.42, 2.58), (0.14, 0.3)):
        paint(((Y > y0) & (Y < y1)).astype(np.float32), (0.45, 0.2, 0.12), 0.9)
    # estrelas/rosetas na faixa
    for k in range(12):
        paint(ellipse(0.2 + k * 0.37, 2.5, 0.03, 0.03), (0.7, 0.62, 0.45), 0.9)
    saints = [(0.95, (0.5, 0.18, 0.12), 1.0), (2.2, (0.22, 0.28, 0.42), 1.1), (3.45, (0.42, 0.34, 0.16), 1.0)]
    r = np.random.default_rng(7)
    slashes = np.zeros((H, W), np.float32)
    for cx, robe, sc in saints:
        hy = 1.85 + (sc - 1) * 0.6
        paint(ellipse(cx, hy + 0.02, 0.34 * sc, 0.34 * sc), (0.72, 0.56, 0.24), 0.95)       # auréola
        paint(ellipse(cx, hy + 0.02, 0.31 * sc, 0.31 * sc), (0.66, 0.5, 0.2), 0.6, line=False)
        # manto: ombros arredondados + corpo que alarga para baixo
        top, bot = hy - 0.27 * sc, 0.32
        t = np.clip((top - Y) / (top - bot), 0, 1)
        half = (0.3 + 0.14 * t) * sc
        body = ((np.abs(X - cx) < half) & (Y < top - 0.08) & (Y > bot)).astype(np.float32)
        body = np.maximum(body, ellipse(cx, top - 0.1, 0.3 * sc, 0.12 * sc))
        paint(body, robe, 0.95)
        folds = (np.sin((X - cx) * 30 / sc + np.sin(Y * 4) * 1.5) * 0.5 + 0.5) ** 5
        paint(folds * body, tuple(c * 0.45 for c in robe), 0.6, line=False)
        # estola/pálio com cruzes
        paint(((np.abs(X - cx) < 0.05 * sc) & (Y < top - 0.05) & (Y > bot + 0.2)).astype(np.float32),
              (0.75, 0.7, 0.58), 0.9)
        # mãos: uma a abençoar, outra a segurar um livro
        paint(ellipse(cx - 0.13 * sc, hy - 0.6 * sc, 0.055 * sc, 0.08 * sc), (0.62, 0.45, 0.32), 0.95)
        paint(((np.abs(X - (cx + 0.14 * sc)) < 0.11 * sc) & (np.abs(Y - (hy - 0.75 * sc)) < 0.15 * sc)).astype(
            np.float32), (0.5, 0.14, 0.1), 0.95)
        # pescoço e rosto
        paint(((np.abs(X - cx) < 0.05 * sc) & (Y < hy - 0.15 * sc) & (Y > top - 0.12)).astype(np.float32),
              (0.6, 0.44, 0.31), 0.95)
        paint(ellipse(cx, hy, 0.135 * sc, 0.19 * sc), (0.64, 0.47, 0.33), 0.95)
        paint(ellipse(cx, hy + 0.14 * sc, 0.14 * sc, 0.08 * sc), (0.25, 0.16, 0.1), 0.9)    # cabelo
        paint(np.clip((0.01 - np.abs(X - cx)) * 200, 0, 1) * ((Y < hy + 0.02) & (Y > hy - 0.08)), (0.35, 0.2, 0.12),
              0.7, line=False)
        paint(ellipse(cx, hy - 0.115 * sc, 0.04 * sc, 0.008), (0.4, 0.14, 0.1), 0.8, line=False)
        for sx in (-1, 1):
            ex, ey = cx + sx * 0.055 * sc, hy + 0.03 * sc
            paint(ellipse(ex, ey + 0.03, 0.045, 0.006), (0.2, 0.12, 0.08), 0.8, line=False)   # sobrancelha
            paint(ellipse(ex, ey, 0.04, 0.017), (0.9, 0.85, 0.75), 0.9, line=False)
            paint(ellipse(ex, ey, 0.015, 0.015), (0.06, 0.04, 0.03), 0.95, line=False)
            # olho arrancado: buraco irregular no reboco
            n = value_noise(H, W, 9, int(ex * 1000))
            d = np.sqrt(((X - ex) / 0.05) ** 2 + ((Y - ey) / 0.032) ** 2) + (n - 0.5) * 0.7
            holes = np.maximum(holes, np.clip((1 - d) * 6, 0, 1))
        # golpes de faca por cima dos olhos
        for _ in range(r.integers(4, 8)):
            a = r.normal(0, 0.35) + (math.pi / 2 if r.random() < 0.25 else 0)
            ln = r.uniform(0.12, 0.3)
            ox, oy = cx + r.normal(0, 0.04), hy + 0.03 + r.normal(0, 0.025)
            dx, dy = math.cos(a), math.sin(a)
            px, py = X - ox, Y - oy
            proj = np.clip(px * dx + py * dy, -ln / 2, ln / 2)
            dist = np.sqrt((px - proj * dx) ** 2 + (py - proj * dy) ** 2)
            taper = 1 - np.abs(proj) / (ln / 2) * 0.7
            slashes = np.maximum(slashes, np.clip((0.004 * taper - dist) * 600, 0, 1))
    img *= (1 - outline * 0.45)[..., None]
    img = img * (1 - slashes[..., None]) + np.array([0.8, 0.76, 0.68]) * slashes[..., None]
    # envelhecimento: desbotado, sujidade, reboco a cair
    grime = fbm(H, W, 91, cells=(64, 16, 4))
    img = img * (0.62 + 0.5 * grime)[..., None]
    img = img * 0.75 + img.mean(-1, keepdims=True) * 0.25
    img = 0.3 * np.array([0.72, 0.66, 0.55], np.float32) + 0.7 * img   # pigmento gasto, a puxar para o reboco
    flake = fbm(H, W, 77, cells=(120, 30, 8))
    edge = np.minimum.reduce([X, w_m - X, Y, h_m - Y])
    loss = flake + np.clip(0.3 - edge, 0, 0.3) * 2.0
    plaster = np.clip((0.78 - loss) * 14, 0, 1) * (1 - holes)
    img = np.clip(img, 0, 1)
    px = np.zeros((H, W, 4), np.float32)
    px[..., :3] = np.clip(img * 1.2, 0, 1) ** 2.2
    px[..., 3] = plaster
    im = bpy.data.images.new("IMG_Fresco_Santos", W, H, alpha=True)
    im.pixels.foreach_set(px.ravel())
    im.file_format = "PNG"
    im.pack()
    gm = np.zeros((H, W, 4), np.float32)
    gm[..., 0] = np.maximum(slashes, holes)
    gm[..., 3] = 1
    im2 = bpy.data.images.new("IMG_Fresco_Raspagens", W, H, alpha=False)
    im2.pixels.foreach_set(gm.ravel())
    im2.file_format = "PNG"
    im2.pack()
    im2.colorspace_settings.name = "Non-Color"
    return im, im2


def mat_fresco(img, gouge):
    m = Mat("M_Fresco_Olhos_Riscados")
    tc = m.texcoord()
    it = m.node("ShaderNodeTexImage", image=img)
    m.link(tc.outputs["UV"], it.inputs["Vector"])
    ig = m.node("ShaderNodeTexImage", image=gouge)
    m.link(tc.outputs["UV"], ig.inputs["Vector"])
    it.image.alpha_mode = "STRAIGHT"
    raw = m.ramp(m.noise(tc.outputs["Object"], 18.0, 6.0, 0.6).outputs["Fac"],
                 [(0.3, (0.012, 0.011, 0.01)), (0.7, (0.035, 0.032, 0.028))]).outputs["Color"]
    col = m.mix(it.outputs["Alpha"], raw, it.outputs["Color"])
    m.set("Base Color", col)
    m.set("Roughness", 0.85)
    h = m.math("ADD", m.math("MULTIPLY", it.outputs["Alpha"], 0.5),
               m.math("MULTIPLY", ig.outputs["Color"], -0.6))
    h = m.math("ADD", h, m.math("MULTIPLY", m.noise(tc.outputs["Object"], 60.0, 4.0, 0.6).outputs["Fac"], 0.2))
    m.set("Normal", m.bump(h, 0.7, 0.01))
    return m.mat


# ---------------------------------------------------------------------------
# Construção da arquitetura
# ---------------------------------------------------------------------------
def build_architecture(col, stone, stone_dark):
    b = Builder()
    th = 0.5
    # --- arcadas (paredes da nave sobre as colunas) --------------------------
    ys = [0.0] + COL_Y + [LENGTH]
    for side in (-1, 1):
        x0 = side * NAVE_X
        for y0, y1 in zip(ys[:-1], ys[1:]):
            w = (y1 - y0 - 2 * 0.45) / 2
            mid = (y0 + y1) / 2
            arch = [(mid - x, z) for x, z in pointed_arch(w, ARCH_SPRING, ARCH_APEX, 14)]
            # arco ordenado da esquerda (y0) para a direita (y1)
            arch_lr = sorted(arch, key=lambda p: p[0])
            pts = [(y0, ARCH_SPRING)] + arch_lr + [(y1, ARCH_SPRING), (y1, NAVE_WALL_TOP), (y0, NAVE_WALL_TOP)]
            faces = b.prism(pts, lambda s, z, x0=x0: Vector((x0 - th / 2, s, z)), (th, 0, 0))
            b.uv_project(faces, lambda co: (co.y, co.z))
    # --- paredes exteriores das naves laterais, com janelas ------------------
    for side in (-1, 1):
        xo = side * AISLE_X
        for y0, y1 in zip(ys[:-1], ys[1:]):
            mid = (y0 + y1) / 2
            ww, sill, spr, apex = 0.65, 2.2, 4.4, 5.6
            t = 0.6
            to3d = (lambda s, z, xo=xo: Vector((xo, s, z)))
            dv = (side * t, 0, 0)
            pieces = [
                [(y0, 0), (mid - ww, 0), (mid - ww, AISLE_ROOF), (y0, AISLE_ROOF)],
                [(mid + ww, 0), (y1, 0), (y1, AISLE_ROOF), (mid + ww, AISLE_ROOF)],
                [(mid - ww, 0), (mid + ww, 0), (mid + ww, sill), (mid - ww, sill)],
            ]
            arch = sorted([(mid - x, z) for x, z in pointed_arch(ww, spr, apex, 10)], key=lambda p: p[0])
            pieces.append([(mid - ww, spr)] + arch + [(mid + ww, spr), (mid + ww, AISLE_ROOF), (mid - ww, AISLE_ROOF)])
            for pts in pieces:
                faces = b.prism(pts, to3d, dv)
                b.uv_project(faces, lambda co: (co.y, co.z))
    # --- parede da entrada e parede do altar (empena ogival) -----------------
    vault = pointed_arch(NAVE_X, NAVE_WALL_TOP, VAULT_APEX, 20)
    gable = [(-AISLE_X, 0), (AISLE_X, 0), (AISLE_X, AISLE_ROOF + 0.3), (NAVE_X, AISLE_ROOF + 0.3)] + \
        [(x, z) for x, z in vault] + [(-NAVE_X, AISLE_ROOF + 0.3), (-AISLE_X, AISLE_ROOF + 0.3)]
    for yw, sgn in ((0.0, -1), (LENGTH, 1)):
        faces = b.prism(gable, lambda s, z, yw=yw: Vector((s, yw, z)), (0, sgn * 0.7, 0))
        b.uv_project(faces, lambda co: (co.x, co.z))
    # --- tetos das naves laterais --------------------------------------------
    for side in (-1, 1):
        cx = side * (NAVE_X + AISLE_X) / 2
        faces = b.box((cx, LENGTH / 2, AISLE_ROOF + 0.15), ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
                      (AISLE_X - NAVE_X, LENGTH, 0.3), mat=1)
        b.uv_project(faces, lambda co: (co.x, co.y))
    # --- estrado do altar (2 degraus) ----------------------------------------
    for k, (y0, zt) in enumerate(((DAIS_Y0, 0.18), (DAIS_Y0 + 0.45, 0.36))):
        faces = b.box((0, (y0 + LENGTH) / 2, zt / 2), ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
                      (2 * NAVE_X - 0.2, LENGTH - y0, zt), mat=1)
        b.uv_project(faces, lambda co: (co.x + co.z, co.y + co.z))
    arch_obj = b.to_object("Arquitetura_Paredes_Arcos", col, [stone, stone_dark])

    # --- colunas (pilares com colunelos) --------------------------------------
    b = Builder()
    for side in (-1, 1):
        for y in COL_Y:
            x = side * NAVE_X
            b.cylinder((x, y, 0.0), (x, y, 0.35), 0.62, 0.58, 16, mat=0)
            b.cylinder((x, y, 0.35), (x, y, 4.55), COL_R, COL_R * 0.97, 20, mat=0)
            for k in range(4):
                a = k * math.pi / 2 + math.pi / 4
                cx, cy = x + math.cos(a) * 0.45, y + math.sin(a) * 0.45
                b.cylinder((cx, cy, 0.35), (cx, cy, 4.6), 0.1, 0.1, 10, mat=0)
            b.cylinder((x, y, 4.55), (x, y, 4.88), COL_R, 0.66, 16, mat=0)
            b.box((x, y, 4.94), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (1.3, 1.3, 0.14), mat=0)
    cols = b.to_object("Colunas", col, [stone])
    bev = cols.modifiers.new("Bevel", "BEVEL")
    bev.width = 0.02
    bev.segments = 2
    bev.limit_method = "ANGLE"
    for p in cols.data.polygons:
        p.use_smooth = True

    # --- abóbada com o buraco escavado ----------------------------------------
    prof = pointed_arch(NAVE_X, NAVE_WALL_TOP, VAULT_APEX, 60)
    arcl = [0.0]
    for (xa, za), (xb, zb) in zip(prof[:-1], prof[1:]):
        arcl.append(arcl[-1] + math.hypot(xb - xa, zb - za))
    ny = int(LENGTH / 0.1) + 1
    verts = []
    for j in range(ny):
        y = LENGTH * j / (ny - 1)
        for (x, z) in prof:
            verts.append((x, y, z))
    npf = len(prof)
    faces, uvs = [], []
    for j in range(ny - 1):
        for i in range(npf - 1):
            x = (prof[i][0] + prof[i + 1][0]) / 2
            y = LENGTH * (j + 0.5) / (ny - 1)
            d = math.hypot(x - HOLE_C.x, (y - HOLE_C.y) * 0.85)
            ang = math.atan2(y - HOLE_C.y, x - HOLE_C.x)
            rr = HOLE_R * (1 + 0.28 * noise.noise(Vector((math.cos(ang) * 1.5, math.sin(ang) * 1.5, 3.3)))
                           + 0.1 * noise.noise(Vector((x * 6, y * 6, 1.1))))
            if d < rr:
                continue
            a = j * npf + i
            faces.append((a, a + npf, a + npf + 1, a + 1))
            uvs.append([(verts[k][1], arcl[k % npf]) for k in (a, a + npf, a + npf + 1, a + 1)])
    me = bpy.data.meshes.new("Abobada")
    me.from_pydata(verts, [], faces)
    uvl = me.uv_layers.new(name="UVMap")
    flat = [c for f in uvs for uv in f for c in uv]
    uvl.data.foreach_set("uv", flat)
    me.materials.append(stone)
    vault_obj = new_object("Abobada_Com_Buraco", me, col)
    for p in me.polygons:
        p.use_smooth = True
    me.validate()
    # normais para baixo (para dentro da igreja)
    bm = bmesh.new()
    bm.from_mesh(me)
    for f in bm.faces:
        f.normal_update()
    down = sum(1 for f in bm.faces if f.normal.z < 0)
    if down < len(bm.faces) / 2:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    bm.free()
    sol = vault_obj.modifiers.new("Espessura", "SOLIDIFY")
    sol.thickness = 0.45
    sol.offset = -1.0
    sol.use_even_offset = True

    # --- nervuras (arcos transversais) ----------------------------------------
    ribs = []
    for y in [0.35] + COL_Y + [LENGTH - 0.35]:
        cu = bpy.data.curves.new(f"Nervura_{y:.1f}", "CURVE")
        cu.dimensions = "3D"
        cu.bevel_depth = 0.16
        cu.bevel_resolution = 1
        sp = cu.splines.new("POLY")
        pr = pointed_arch(NAVE_X - 0.05, NAVE_WALL_TOP - 0.3, VAULT_APEX - 0.12, 40)
        sp.points.add(len(pr) - 1)
        for i, (x, z) in enumerate(pr):
            sp.points[i].co = (x, y, z, 1)
        cu.materials.append(stone)
        ribs.append(new_object(f"Nervura_{len(ribs)}", cu, col))
    # --- poço da escavação por cima do buraco ---------------------------------
    b = Builder()
    center = Vector((HOLE_C.x, HOLE_C.y, VAULT_APEX - 0.3))
    up = -SUN_DIR
    ring_pts = 20
    rings = []
    for k in range(5):
        cen = center + up * (k * 0.9)
        rad = HOLE_R * 1.25 + k * 0.12
        ring = []
        for i in range(ring_pts):
            a = 2 * math.pi * i / ring_pts
            rj = rad * (1 + 0.15 * noise.noise(Vector((math.cos(a) * 2, math.sin(a) * 2, k * 0.7))))
            ring.append(b.bm.verts.new(cen + Vector((math.cos(a) * rj, math.sin(a) * rj, 0))))
        rings.append(ring)
    fs = []
    for k in range(len(rings) - 1):
        for i in range(ring_pts):
            fs.append(b.bm.faces.new((rings[k][i], rings[k][(i + 1) % ring_pts],
                                      rings[k + 1][(i + 1) % ring_pts], rings[k + 1][i])))
    b._tag(fs, 0)
    pit = b.to_object("Poco_Escavacao", col, [bpy.data.materials["M_Terra"]])
    pit.modifiers.new("Espessura", "SOLIDIFY").thickness = 0.3
    return arch_obj


def build_floor(col):
    x0, x1, y0, y1 = -AISLE_X, AISLE_X, 0.0, LENGTH
    step = 0.1
    nx, ny = int((x1 - x0) / step) + 1, int((y1 - y0) / step) + 1
    verts, dirt = [], []
    for j in range(ny):
        y = y0 + j * step
        for i in range(nx):
            x = x0 + i * step
            verts.append((x, y, floor_height(x, y)))
            dw = AISLE_X - abs(x)
            dval = math.exp(-dw / 0.8) * 0.8
            dval += math.exp(-((x - HOLE_C.x) ** 2 + (y - HOLE_C.y) ** 2) / 4.0)
            dirt.append(min(dval, 1.0))
    faces = [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i)
             for j in range(ny - 1) for i in range(nx - 1)]
    me = bpy.data.meshes.new("Chao")
    me.from_pydata(verts, [], faces)
    at = me.attributes.new("dirt", "FLOAT", "POINT")
    at.data.foreach_set("value", dirt)
    me.materials.append(mat_floor())
    me.shade_smooth()
    return new_object("Chao_Lajes", me, col)


def earth_mound(b, center, radii, rough=0.25, subdiv=4):
    m = Matrix.Translation(center) @ Matrix.Diagonal((*radii, 1))
    res = bmesh.ops.create_icosphere(b.bm, subdivisions=subdiv, radius=1.0, matrix=m)
    c = Vector(center)
    for v in res["verts"]:
        d = v.co - c
        n = noise.noise(v.co * 1.8) * rough + noise.noise(v.co * 6.0) * rough * 0.3
        v.co = c + d * (1 + n)
        if v.co.z < -0.05:
            v.co.z = -0.05
    b._tag(b._faces(res["verts"]), 0)


def build_earth(col, earth):
    """Terra a entrar pelas janelas e monte de terra sob o buraco."""
    b = Builder()
    ys = [0.0] + COL_Y + [LENGTH]
    wins = [((ya + yb) / 2, s) for ya, yb in zip(ys[:-1], ys[1:]) for s in (-1, 1)]
    for mid, side in wins:
        if rng.random() < 0.7:
            # rampa de terra desde o parapeito até ao chão
            earth_mound(b, (side * (AISLE_X - 0.2), mid + rng.uniform(-0.3, 0.3), 0.3),
                        (rng.uniform(1.0, 1.6), rng.uniform(1.0, 1.6), rng.uniform(1.4, 2.3)))
        # terra que enche a janela por fora
        b.box((side * (AISLE_X + 0.75), mid, 3.5), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.5, 2.0, 4.0))
    earth_mound(b, (HOLE_C.x + 0.2, HOLE_C.y + 0.3, 0.0), (1.5, 1.7, 0.75), 0.3)
    obj = b.to_object("Terra_Montes", col, [earth], smooth=True)
    return obj


def build_rubble(col, stone):
    b = Builder()
    for _ in range(70):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(0.3, 2.3) ** 1.2
        x, y = HOLE_C.x + math.cos(a) * r, HOLE_C.y + math.sin(a) * r * 1.2
        s = rng.uniform(0.06, 0.28)
        b.box((x, y, floor_height(x, y) + s * 0.3 + (0.5 if r < 1.2 else 0)),
              (Euler((rng.uniform(0, 1), rng.uniform(0, 1), rng.uniform(0, 6))).to_matrix() @ Vector((1, 0, 0)),
               Euler((0, 0, 0)).to_matrix() @ Vector((0, 1, 0)), (0, 0, 1)),
              (s * rng.uniform(1, 2), s * rng.uniform(0.8, 1.4), s * rng.uniform(0.5, 1)))
    for _ in range(140):
        x, y = rng.uniform(-AISLE_X + 0.3, AISLE_X - 0.3), rng.uniform(0.5, LENGTH - 0.5)
        s = rng.uniform(0.02, 0.1)
        b.ico((x, y, floor_height(x, y) + s * 0.3), s, (1, rng.uniform(0.6, 1), rng.uniform(0.4, 0.7)), 1, 0.4,
              rot=(0, 0, rng.uniform(0, 6)))
    obj = b.to_object("Entulho_Pedra", col, [stone])
    bev = obj.modifiers.new("Bevel", "BEVEL")
    bev.width = 0.015
    return obj


# ---------------------------------------------------------------------------
# Mobiliário e props
# ---------------------------------------------------------------------------
def pew(b, M, broken=False):
    """Banco de igreja em coordenadas locais (frente = +Y, largura ao longo de X)."""
    L = 2.5
    b.box((0, 0, 0.45), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (L if not broken else L * 0.6, 0.42, 0.05), M=M)
    b.box((0, -0.22, 0.72), ((1, 0, 0), (0, 0.15, 1), Vector((0, 1, -0.15)).normalized()), (L, 0.6, 0.04), M=M)
    b.box((0, -0.18, 0.5), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (L, 0.04, 0.12), M=M)
    for sx in (-L / 2, L / 2):
        if broken and sx > 0:
            continue
        b.box((sx, -0.02, 0.5), ((0, 1, 0), (0, 0, 1), (1, 0, 0)), (0.55, 1.0, 0.06), M=M)
    # genuflexório
    b.box((0, 0.42, 0.15), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (L * 0.95, 0.14, 0.05), M=M)


def build_pews(col, wood):
    b = Builder()
    for row in range(14):
        y = 3.0 + row * 1.15
        for side in (-1, 1):
            cx = side * 2.35
            if rng.random() < 0.08:
                continue
            state = rng.random()
            yaw = rng.gauss(0, 0.06)
            loc = Vector((cx + rng.gauss(0, 0.08), y + rng.gauss(0, 0.06), 0))
            if abs(loc.x - HOLE_C.x) < 2.2 and abs(loc.y - HOLE_C.y) < 2.2:
                state = 0.0   # os do buraco foram esmagados/virados
            if state < 0.3:
                # virado para trás, deitado no chão
                M = Matrix.Translation(loc + Vector((0, 0.35, 0.05))) @ Euler((math.radians(rng.uniform(80, 100)), 0,
                                                                                yaw * 3)).to_matrix().to_4x4()
                pew(b, M, broken=rng.random() < 0.4)
            elif state < 0.45:
                # tombado de lado
                M = Matrix.Translation(loc + Vector((0, 0, 0.02))) @ Euler((0, math.radians(side * rng.uniform(15, 30)),
                                                                             yaw * 4)).to_matrix().to_4x4()
                pew(b, M, broken=rng.random() < 0.5)
            else:
                M = Matrix.Translation(loc) @ Euler((0, 0, yaw)).to_matrix().to_4x4()
                pew(b, M, broken=rng.random() < 0.15)
    # tábuas partidas soltas
    for _ in range(25):
        x, y = rng.uniform(-4.0, 4.0), rng.uniform(2.0, 20.0)
        a = rng.uniform(0, math.pi)
        d = Vector((math.cos(a), math.sin(a), rng.uniform(-0.1, 0.15))).normalized()
        s = d.cross(Vector((0, 0, 1))).normalized()
        b.box((x, y, 0.03), (d, s, s.cross(d)), (rng.uniform(0.4, 1.5), rng.uniform(0.1, 0.25), 0.04))
    return b.to_object("Bancos_Igreja", col, [wood])


def build_altar(col, stone):
    b = Builder()
    z0 = 0.36
    # parte esquerda de pé, parte direita partida e deslizada
    b.box((-0.6, ALTAR_Y, z0 + 0.48), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (1.35, 0.95, 0.96))
    rot = Euler((0, math.radians(-9), math.radians(12))).to_matrix()
    b.box((0.75, ALTAR_Y - 0.15, z0 + 0.43), (rot @ Vector((1, 0, 0)), rot @ Vector((0, 1, 0)), rot @ Vector((0, 0, 1))),
          (1.05, 0.95, 0.9))
    # mesa (tampo) partida: metade sobre o altar, metade encostada ao degrau
    b.box((-0.55, ALTAR_Y, z0 + 1.02), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (1.55, 1.15, 0.12))
    d = Vector((1, 0, -0.62)).normalized()
    b.box((1.25, ALTAR_Y - 0.9, 0.55), (d, (0, 1, 0), Vector((0, 1, 0)).cross(d)), (1.4, 1.1, 0.12))
    # lascas
    for _ in range(18):
        x, y = rng.uniform(0.2, 2.2), rng.uniform(ALTAR_Y - 1.8, ALTAR_Y + 0.4)
        zz = z0 if y > DAIS_Y0 + 0.45 else (0.18 if y > DAIS_Y0 else 0.0)
        s = rng.uniform(0.04, 0.16)
        b.ico((x, y, zz + s * 0.3), s, (1, 0.8, 0.5), 1, 0.3, rot=(0, 0, rng.uniform(0, 6)))
    obj = b.to_object("Altar_Partido", col, [stone])
    bev = obj.modifiers.new("Bevel", "BEVEL")
    bev.width = 0.02
    bev.segments = 2
    return obj


def build_statues(col, marble):
    b = Builder()
    spots = [(-5.55, COL_Y[1] + 0.3, 0.6), (5.55, COL_Y[3] - 0.2, -0.4), (-5.55, COL_Y[3] + 0.4, 0.2)]
    for x, y, yaw in spots:
        b.box((x, y, 0.5), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.75, 0.75, 1.0))
        b.box((x, y, 1.03), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.85, 0.85, 0.07))
        # corpo com manto
        b.cylinder((x, y, 1.06), (x, y, 2.3), 0.3, 0.22, 16)
        b.ico((x, y, 2.35), 0.25, (1.0, 0.7, 0.45), 2, 0.1)
        # braços cruzados/orando (blocos)
        b.box((x + math.sin(yaw) * 0.18, y - math.cos(yaw) * 0.18, 1.95),
              (Vector((math.cos(yaw), math.sin(yaw), 0)), Vector((-math.sin(yaw), math.cos(yaw), 0)), (0, 0, 1)),
              (0.3, 0.14, 0.32))
        # pescoço partido
        b.cylinder((x, y, 2.45), (x, y, 2.55), 0.075, 0.07, 10)
        # cabeça caída no chão
        hx, hy = x + rng.uniform(-0.9, 0.9) * (-1 if x > 0 else 1) + (-0.6 if x > 0 else 0.6), y + rng.uniform(-0.8, 0.8)
        b.ico((hx, hy, floor_height(hx, hy) + 0.1), 0.115, (0.9, 1.0, 1.15), 2, 0.1, rot=(1.2, 0.3, rng.uniform(0, 6)))
    obj = b.to_object("Santos_Decapitados", col, [marble])
    sub = obj.modifiers.new("Subdivisao", "SUBSURF")
    sub.levels = 1
    sub.render_levels = 2
    obj.data.shade_smooth()
    return obj


def build_cross(col, wood, christ_mat, iron):
    """Cruz invertida com Cristo, pendurada numa corrente. Construída 'direita' e virada 180°."""
    pivot = bpy.data.objects.new("CRUZ_Pivot_Corrente", None)
    pivot.empty_display_type = "SPHERE"
    pivot.empty_display_size = 0.2
    col.objects.link(pivot)
    top_attach = VAULT_APEX - 0.3
    pivot.location = (0.0, CROSS_Y, top_attach)

    # --- cruz (coordenadas 'direitas': u ao longo do madeiro, 0 = pé) --------
    b = Builder()
    b.box((0, 0, CROSS_LEN / 2), ((0, 0, 1), (1, 0, 0), (0, 1, 0)), (CROSS_LEN, 0.26, 0.2))
    b.box((0, 0, CROSS_LEN - 0.95), ((1, 0, 0), (0, 0, 1), (0, 1, 0)), (2.3, 0.22, 0.18))
    b.box((0, 0.02, 0.62), ((1, 0, 0), (0, 0, 1), (0, 1, 0)), (0.42, 0.08, 0.24))   # supedâneo
    # placa INRI
    b.box((0, -0.06, CROSS_LEN - 0.25), ((1, 0, 0), (0, 0, 1), (0, 1, 0)), (0.5, 0.26, 0.03))
    cross = b.to_object("Cruz_Invertida", col, [wood])
    bev = cross.modifiers.new("Bevel", "BEVEL")
    bev.width = 0.012
    cross.rotation_euler = (0, math.pi, 0)
    cross.parent = pivot
    cross.location = (0, 0, -(top_attach - (CROSS_BOTTOM + CROSS_LEN)))
    # a origem da cruz está no pé; virada, o pé fica em cima, em z = CROSS_BOTTOM + CROSS_LEN

    # --- Cristo estilizado (frente = -Y): esqueleto + modificador Skin ---------
    fy = -0.13
    bar = CROSS_LEN - 0.95
    J = [  # (x, y, z, raio_x, raio_y)
        (0.0, fy - 0.08, bar - 0.95, 0.13, 0.09),    # 0 bacia
        (0.0, fy - 0.09, bar - 0.72, 0.12, 0.085),   # 1 abdómen
        (0.0, fy - 0.1, bar - 0.45, 0.16, 0.1),      # 2 peito
        (0.02, fy - 0.1, bar - 0.22, 0.06, 0.055),   # 3 base do pescoço
        (0.08, fy - 0.15, bar - 0.07, 0.085, 0.09),  # 4 cabeça (tombada)
        (0.11, fy - 0.14, bar + 0.08, 0.08, 0.085),  # 5 alto da cabeça
        (-0.19, fy - 0.08, bar - 0.24, 0.065, 0.06), # 6 ombro esq.
        (0.19, fy - 0.08, bar - 0.24, 0.065, 0.06),  # 7 ombro dir.
        (-0.52, fy - 0.06, bar - 0.08, 0.048, 0.045),  # 8 cotovelo esq.
        (-0.74, fy - 0.05, bar + 0.0, 0.042, 0.04),  # 9 antebraço partido
        (0.29, fy - 0.08, bar - 0.2, 0.058, 0.055),  # 10 coto do braço dir.
        (-0.08, fy - 0.08, bar - 1.05, 0.085, 0.08), # 11 anca esq.
        (-0.06, fy - 0.14, bar - 1.6, 0.058, 0.058), # 12 joelho esq.
        (-0.025, fy - 0.07, bar - 2.1, 0.038, 0.04), # 13 tornozelo esq.
        (-0.01, fy - 0.12, bar - 2.2, 0.035, 0.05),  # 14 pé esq.
        (0.08, fy - 0.08, bar - 1.05, 0.085, 0.08),  # 15 anca dir.
        (0.07, fy - 0.14, bar - 1.58, 0.058, 0.058), # 16 joelho dir.
        (0.025, fy - 0.09, bar - 2.06, 0.038, 0.04), # 17 tornozelo dir.
        (0.02, fy - 0.15, bar - 2.17, 0.035, 0.05),  # 18 pé dir.
    ]
    E = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (3, 6), (3, 7), (6, 8), (8, 9), (7, 10),
         (0, 11), (11, 12), (12, 13), (13, 14), (0, 15), (15, 16), (16, 17), (17, 18)]
    me = bpy.data.meshes.new("Cristo_Esqueleto")
    me.from_pydata([j[:3] for j in J], E, [])
    christ = new_object("Cristo_Madeira_Partido", me, col)
    christ.modifiers.new("Pele", "SKIN")
    sv = me.skin_vertices[0].data
    for i, j in enumerate(J):
        sv[i].radius = (j[3], j[4])
    sv[0].use_root = True
    me.materials.append(christ_mat)
    sub = christ.modifiers.new("Subdivisao", "SUBSURF")
    sub.levels = 1
    sub.render_levels = 2
    tex = bpy.data.textures.new("T_Cristo_Desgaste", "CLOUDS")
    tex.noise_scale = 0.06
    disp = christ.modifiers.new("Desgaste", "DISPLACE")
    disp.texture = tex
    disp.strength = 0.012
    christ.parent = cross
    # perizónio (pano) e prego que sobrou na ponta direita da trave
    b = Builder()
    b.ico((0.01, fy - 0.08, bar - 0.97), 0.19, (1.05, 0.68, 0.55), 3, 0.3)
    b.ico((0.12, fy - 0.12, bar - 0.9), 0.08, (1.0, 0.8, 1.2), 2, 0.3)
    b.ico((1.02, fy + 0.01, bar + 0.02), 0.06, (1.3, 0.6, 1.0), 2, 0.2)
    cloth = b.to_object("Cristo_Perizonio_Mao", col, [christ_mat], smooth=True)
    cloth.parent = cross
    cs = cloth.modifiers.new("Subdivisao", "SUBSURF")
    cs.levels, cs.render_levels = 1, 2
    marker = bpy.data.objects.new("MARCADOR_Cristo_Substituir", None)
    marker.empty_display_type = "PLAIN_AXES"
    marker.empty_display_size = 0.3
    col.objects.link(marker)
    marker.parent = cross
    marker.location = (0, fy - 0.1, bar - 0.8)

    # --- corrente --------------------------------------------------------------
    b = Builder()
    z = CROSS_BOTTOM + CROSS_LEN + 0.05
    k = 0
    link_len = 0.13
    while z < top_attach:
        rot = Euler((0, 0, (math.pi / 2) * (k % 2))).to_matrix() @ Euler((math.pi / 2, 0, 0)).to_matrix()
        b.ring((0, 0, z - top_attach + link_len / 2), rot, 0.035, 0.011, stretch=1.7, segs=12, sides=6)
        z += link_len * 0.78
        k += 1
    # argola na nervura
    b.ring((0, 0, 0.02), Euler((math.pi / 2, 0, 0)).to_matrix(), 0.07, 0.015, segs=16, sides=6)
    chain = b.to_object("Corrente", col, [iron], smooth=True)
    chain.parent = pivot
    return pivot, cross


def build_candles(col, wax, brass, lit_positions_out):
    b = Builder()
    spots = []
    # no estrado, junto ao altar, junto ao fresco, e aos pés da cruz
    for _ in range(9):
        spots.append((rng.uniform(-2.8, 2.8), rng.uniform(DAIS_Y0 + 0.6, LENGTH - 0.4), 0.36))
    for _ in range(4):
        spots.append((rng.uniform(-0.9, 0.9), rng.uniform(ALTAR_Y - 0.3, ALTAR_Y + 0.3), 0.36 + 1.08))
    for k in range(6):
        spots.append((-1.6 + k * 0.62 + rng.uniform(-0.15, 0.15), FRESCO_Y - rng.uniform(0.15, 0.4), 0.36))
    for _ in range(6):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(0.9, 1.6)
        spots.append((math.cos(a) * r, CROSS_Y + math.sin(a) * r * 0.5, 0.0 if CROSS_Y + math.sin(a) * r * 0.5 < DAIS_Y0 else 0.18))
    for x, y, z0 in spots:
        h = rng.uniform(0.06, 0.35)
        r = rng.uniform(0.018, 0.04)
        toppled = rng.random() < 0.2
        if toppled:
            a = rng.uniform(0, 2 * math.pi)
            b.cylinder((x, y, z0 + r), (x + math.cos(a) * h, y + math.sin(a) * h, z0 + r), r, r * 0.95, 12)
            continue
        b.cylinder((x, y, z0), (x, y, z0 + h), r * 1.05, r, 14)
        # cera escorrida na base
        b.ico((x, y, z0 + 0.005), r * 1.8, (1, 1, 0.25), 2, 0.4)
        b.cylinder((x, y, z0 + h), (x, y, z0 + h + 0.012), 0.0015, 0.0012, 4)   # pavio
        if rng.random() < 0.8:
            lit_positions_out.append(Vector((x, y, z0 + h + 0.03)))
    wax_obj = b.to_object("Velas", col, [wax], smooth=True)
    # castiçais de latão tombados
    b = Builder()
    for x, y, z0, a in ((1.6, ALTAR_Y - 1.1, 0.36, 0.4), (-1.9, ALTAR_Y - 0.9, 0.36, 2.1), (0.6, CROSS_Y - 0.9, 0.0, 1.0)):
        d = Vector((math.cos(a), math.sin(a), 0))
        base = Vector((x, y, z0 + 0.09))
        b.cylinder(base, base + d * 0.04, 0.09, 0.09, 16)
        b.cylinder(base + d * 0.04, base + d * 0.7, 0.018, 0.015, 10)
        b.cylinder(base + d * 0.7, base + d * 0.76, 0.05, 0.06, 12)
    brass_obj = b.to_object("Castical_Tombados", col, [brass], smooth=True)
    return wax_obj


def build_flames(col, positions, flame_mat, tag):
    b = Builder()
    lights = []
    for i, p in enumerate(positions):
        b.ico(p, 0.009, (0.8, 0.8, 2.4), 2, 0.1)
        ld = bpy.data.lights.new(f"LUZ_Vela_{tag}_{i:02d}", "POINT")
        ld.energy = rng.uniform(2.0, 4.5)
        ld.color = (1.0, 0.5, 0.17)
        ld.shadow_soft_size = 0.01
        ob = new_object(ld.name, ld, col)
        ob.location = p + Vector((0, 0, 0.01))
        lights.append(ob)
    b.to_object(f"Chamas_{tag}", col, [flame_mat], smooth=True)
    glow = light(f"LUZ_Velas_Fresco_{tag}", "POINT", col, (0.0, FRESCO_Y - 0.7, 0.8), 45.0, (1.0, 0.52, 0.2),
                 shadow_soft_size=0.4)
    glow.visible_camera = False
    lights.append(glow)
    return lights


def build_roots_rope(col, root_mat, rope_mat):
    objs = []
    for i in range(22):
        a = rng.uniform(0, 2 * math.pi)
        r = HOLE_R * rng.uniform(0.85, 1.15)
        p = Vector((HOLE_C.x + math.cos(a) * r, HOLE_C.y + math.sin(a) * r / 0.85, VAULT_APEX - 0.25))
        ln = rng.uniform(0.4, 2.6)
        cu = bpy.data.curves.new(f"Raiz_{i}", "CURVE")
        cu.dimensions = "3D"
        cu.bevel_depth = rng.uniform(0.004, 0.018)
        cu.bevel_resolution = 1
        sp = cu.splines.new("POLY")
        n = 12
        sp.points.add(n - 1)
        for k in range(n):
            t = k / (n - 1)
            off = Vector((noise.noise(Vector((i, t * 3, 0.5))) * 0.25 * t, noise.noise(Vector((i, t * 3, 7.5))) * 0.25 * t, 0))
            q = p + off + Vector((0, 0, -ln * t))
            sp.points[k].co = (*q, 1)
            sp.points[k].radius = 1.0 - 0.8 * t
        cu.materials.append(root_mat)
        objs.append(new_object(f"Raiz_{i}", cu, col))
    # corda dos exploradores, do bordo do buraco ao chão
    cu = bpy.data.curves.new("Corda_Exploradores", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.014
    cu.bevel_resolution = 2
    sp = cu.splines.new("POLY")
    top = Vector((HOLE_C.x - 0.7, HOLE_C.y - 0.6, VAULT_APEX + 0.6))
    bot = Vector((HOLE_C.x - 0.3, HOLE_C.y - 1.2, 0.02))
    n = 30
    sp.points.add(n + 6 - 1)
    for k in range(n):
        t = k / (n - 1)
        q = top.lerp(bot, t) + Vector((0.12 * math.sin(t * 9), 0, 0))
        sp.points[k].co = (*q, 1)
    for k in range(6):   # sobra enrolada no chão
        a = k * 1.1
        q = bot + Vector((math.cos(a) * 0.25, math.sin(a) * 0.25 + 0.2, 0.0))
        sp.points[n + k].co = (*q, 1)
    cu.materials.append(rope_mat)
    objs.append(new_object("Corda_Exploradores", cu, col))
    return objs


def build_fresco(col):
    img, gouge = make_fresco_image()
    me = bpy.data.meshes.new("Fresco")
    w, h, z0 = 4.4, 2.8, 1.75
    verts = [(-w / 2, FRESCO_Y, z0), (w / 2, FRESCO_Y, z0), (w / 2, FRESCO_Y, z0 + h), (-w / 2, FRESCO_Y, z0 + h)]
    me.from_pydata(verts, [], [(0, 3, 2, 1)])
    uv = me.uv_layers.new(name="UVMap")
    uv.data.foreach_set("uv", [0, 0, 0, 1, 1, 1, 1, 0])
    me.materials.append(mat_fresco(img, gouge))
    obj = new_object("Fresco_Olhos_Riscados", me, col)
    sub = obj.modifiers.new("Subdivisao", "SUBSURF")
    sub.subdivision_type = "SIMPLE"
    sub.levels = 0
    sub.render_levels = 0
    return obj


def build_dust(col, mat):
    b = Builder()
    for _ in range(2600):
        t = rng.uniform(0, 1)
        base = Vector((HOLE_C.x, HOLE_C.y, VAULT_APEX)) + SUN_DIR * (t * (VAULT_APEX - 0.2) / -SUN_DIR.z)
        a = rng.uniform(0, 2 * math.pi)
        r = HOLE_R * 1.1 * math.sqrt(rng.random())
        p = base + Vector((math.cos(a) * r, math.sin(a) * r, 0))
        bmesh.ops.create_icosphere(b.bm, subdivisions=1, radius=rng.uniform(0.0008, 0.002),
                                   matrix=Matrix.Translation(p))
    return b.to_object("Poeira_No_Feixe", col, [mat], smooth=True)


# ---------------------------------------------------------------------------
# Luzes, câmaras, marcadores, render
# ---------------------------------------------------------------------------
def light(name, kind, col, loc, energy, color, **kw):
    ld = bpy.data.lights.new(name, kind)
    ld.energy = energy
    ld.color = color
    for k, v in kw.items():
        setattr(ld, k, v)
    ob = new_object(name, ld, col)
    ob.location = loc
    return ob


def moon(col, name, energy):
    ob = light(name, "SUN", col, (0, 0, 20), energy, (0.62, 0.72, 1.0), angle=math.radians(0.6))
    ob.rotation_euler = SUN_DIR.to_track_quat("-Z", "Y").to_euler()
    return ob


def add_noise_anim(id_data, path, strength, scale, index=-1):
    id_data.keyframe_insert(path, frame=1, index=index)
    act = id_data.animation_data.action
    fcs = list(getattr(act, "fcurves", []) or [])
    if not fcs:
        for layer in getattr(act, "layers", []):
            for strip in layer.strips:
                for cb in strip.channelbags:
                    fcs += list(cb.fcurves)
    for fc in fcs:
        if fc.data_path == path:
            mod = fc.modifiers.new("NOISE")
            mod.scale = scale
            mod.strength = strength
            mod.phase = rng.uniform(0, 10)


def build_cameras(col, focus_marker):
    cams = {}

    def cam(name, loc, target, lens, fstop=None, focus=None, shift_y=0.0):
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        cd.sensor_width = 36
        cd.clip_start = 0.05
        cd.clip_end = 200
        cd.shift_y = shift_y
        if fstop:
            cd.dof.use_dof = True
            cd.dof.aperture_fstop = fstop
            if isinstance(focus, bpy.types.Object):
                cd.dof.focus_object = focus
            else:
                cd.dof.focus_distance = focus
        ob = new_object(name, cd, col)
        ob.location = loc
        ob.rotation_euler = look_at_rotation(loc, target)
        cams[name] = ob
        return ob

    cam("CAM_1_Entrada_Nave", (0.35, 1.0, 1.65), (0.0, CROSS_Y, 3.6), 32)
    cam("CAM_2_Contrapicado_Cruz", (1.5, CROSS_Y - 2.3, 0.3), (0.0, CROSS_Y, 5.2), 18)
    cam("CAM_3_Personagem_Costas", (0.95, 11.2, 1.75), (0.0, CROSS_Y, 2.9), 50, 4.0, focus_marker)
    cam("CAM_4_Detalhe_Fresco", (1.1, LENGTH - 3.9, 2.1), (0.15, FRESCO_Y, 2.95), 35, 4.0, 4.0)
    cam("CAM_5_Fundo_Analise", (-2.7, 7.5, 1.9), (0.9, CROSS_Y, 3.3), 26)
    cam("CAM_6_Alto_Flutuante", (2.6, 12.5, 11.0), (0.0, CROSS_Y, 1.6), 24)
    bpy.context.scene.camera = cams["CAM_1_Entrada_Nave"]
    return cams


def build_markers(col):
    def marker(name, loc, facing, note):
        theta = math.atan2(facing[0], -facing[1])
        e = bpy.data.objects.new(name, None)
        e.empty_display_type = "SINGLE_ARROW"
        e.empty_display_size = 0.5
        col.objects.link(e)
        e.location = loc
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
        return e

    m1 = marker("PERSONAGEM_1_Corredor_Olha_Cruz", (0.15, 15.2, 0.0), (0, 1), "de pé no corredor, a olhar para a cruz")
    marker("PERSONAGEM_2_Ajoelhado_Cruz", (0.25, CROSS_Y - 1.6, 0.0), (0, 1), "ajoelhado diante da cruz invertida")
    marker("PERSONAGEM_3_Entrada", (-0.4, 2.2, 0.0), (0.05, 1), "a entrar, com o fundo da nave à frente")
    marker("PERSONAGEM_4_Sob_O_Buraco", (HOLE_C.x - 0.3, HOLE_C.y - 1.0, 0.0), (0.3, 1),
           "acabou de descer pela corda")
    return m1


def setup_world():
    w = bpy.data.worlds.new("Mundo_Noite")
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.02, 0.028, 0.055, 1)
    bpy.context.scene.world = w


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


def setup_render():
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.cycles.samples = 512
    scn.cycles.preview_samples = 32
    scn.cycles.use_adaptive_sampling = True
    scn.cycles.adaptive_threshold = 0.015
    scn.cycles.use_denoising = True
    scn.cycles.max_bounces = 8
    scn.cycles.diffuse_bounces = 3
    scn.cycles.glossy_bounces = 2
    scn.cycles.volume_bounces = 1
    scn.cycles.sample_clamp_indirect = 6.0
    scn.cycles.volume_step_rate = 1.0
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
    scn.view_settings.exposure = 1.1


def setup_compositor():
    """Look noir: quase monocromático, pretos profundos, halo nas velas, grão pesado."""
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
    lens = N("CompositorNodeLensdist")
    try_set(lens, "Distortion", 0.015)
    try_set(lens, "Dispersion", 0.008)
    L(glare.outputs["Image"], lens.inputs["Image"])
    hs = N("CompositorNodeHueSat")
    try_set(hs, "Saturation", 0.32)
    L(lens.outputs["Image"], hs.inputs["Image"])
    cb = N("CompositorNodeColorBalance")
    cb.correction_method = "LIFT_GAMMA_GAIN"
    try_set(cb, "Lift", (0.97, 0.99, 1.03))
    try_set(cb, "Gamma", (1.0, 1.0, 1.0))
    try_set(cb, "Gain", (1.05, 1.0, 0.95))
    L(hs.outputs["Image"], cb.inputs["Image"])
    mask = N("CompositorNodeEllipseMask")
    try_set(mask, "Size", (0.9, 0.78))
    blur = N("CompositorNodeBlur")
    blur.filter_type = "FAST_GAUSS"
    try_set(blur, "Size", (320, 320))
    L(mask.outputs["Mask"], blur.inputs["Image"])
    lift = N("CompositorNodeMapRange")
    lift.inputs["From Min"].default_value = 0.0
    lift.inputs["From Max"].default_value = 1.0
    lift.inputs["To Min"].default_value = 0.3
    lift.inputs["To Max"].default_value = 1.0
    L(blur.outputs["Image"], lift.inputs["Value"])
    vig = N("CompositorNodeMixRGB")
    vig.blend_type = "MULTIPLY"
    vig.inputs["Fac"].default_value = 1.0
    L(cb.outputs["Image"], vig.inputs[1])
    L(lift.outputs["Value"], vig.inputs[2])
    tex = bpy.data.textures.new("T_Grao_Noir", "NOISE")
    tn = N("CompositorNodeTexture")
    tn.texture = tex
    gblur = N("CompositorNodeBlur")
    gblur.filter_type = "GAUSS"
    try_set(gblur, "Size", (1, 1))
    L(tn.outputs["Value"], gblur.inputs["Image"])
    grain = N("CompositorNodeMixRGB")
    grain.blend_type = "OVERLAY"
    grain.inputs["Fac"].default_value = 0.2
    L(vig.outputs["Image"], grain.inputs[1])
    L(gblur.outputs["Image"], grain.inputs[2])
    comp = N("CompositorNodeComposite")
    L(grain.outputs["Image"], comp.inputs["Image"])
    view = N("CompositorNodeViewer")
    L(grain.outputs["Image"], view.inputs["Image"])
    for i, n in enumerate(nt.nodes):
        n.location = (i * 220 - 1400, 0)


README_TEXT = """IGREJA GÓTICA SOTERRADA — como usar
====================================

COLEÇÕES
  01_ARQUITETURA   paredes, arcos, colunas, abóbada com buraco, nervuras, poço, chão
  02_TERRA_ENTULHO terra das janelas, monte sob o buraco, pedras, raízes, corda
  03_MOBILIARIO    bancos, altar partido, santos decapitados, fresco, velas, castiçais
  04_CRUZ          cruz invertida + Cristo + corrente (mexa no CRUZ_Pivot_Corrente)
  05_VARIANTES     ative SÓ UMA:
                     VAR_1_Normal | VAR_2_So_Luar | VAR_3_Nuvens
  06_ATMOSFERA     nevoeiro volumétrico e poeira no feixe
  07_CAMARAS       6 planos
  08_PERSONAGEM    marcadores (seta = para onde olha; ver propriedade 'nota')

A CRUZ BALANÇA: o pivot tem ruído animado na rotação (frames 1-240).
Para uma imagem parada, escolha o frame ou apague os modificadores das F-curves.

TROCAR O CRISTO: MARCADOR_Cristo_Substituir marca o centro do corpo.
Esconda Cristo_Madeira_Partido e ponha lá a sua figura (filha de Cruz_Invertida).
"""


def main():
    args = parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.name = "Igreja_Soterrada"

    c_arch = collection("01_ARQUITETURA")
    c_earth = collection("02_TERRA_ENTULHO")
    c_furn = collection("03_MOBILIARIO")
    c_cross = collection("04_CRUZ")
    c_var = collection("05_VARIANTES")
    v_cols = [collection(n, c_var) for n in ("VAR_1_Normal", "VAR_2_So_Luar", "VAR_3_Nuvens")]
    c_atmo = collection("06_ATMOSFERA")
    c_cam = collection("07_CAMARAS")
    c_char = collection("08_PERSONAGEM")

    stone = mat_ashlar("M_Cantaria")
    stone_dark = mat_ashlar("M_Cantaria_Escura", tone=0.7)
    earth = mat_earth()
    wood = mat_wood("M_Madeira_Velha")
    cross_wood = mat_wood("M_Madeira_Cruz", dark=1.4)
    marble = mat_simple("M_Marmore_Sujo", (0.3, 0.29, 0.27), 0.6, noise_scale=8, bump=0.3)
    iron = mat_iron()
    wax = mat_wax()
    brass = mat_simple("M_Latao_Oxidado", (0.25, 0.18, 0.08), 0.45, metal=1.0, noise_scale=20)
    root_mat = mat_simple("M_Raizes", (0.05, 0.035, 0.025), 0.9, noise_scale=40, bump=0.4)
    rope_mat = mat_simple("M_Corda", (0.2, 0.16, 0.11), 0.9, noise_scale=120, bump=0.6)
    flame = mat_flame()

    print("> arquitetura")
    build_architecture(c_arch, stone, stone_dark)
    build_floor(c_arch)
    print("> terra e entulho")
    build_earth(c_earth, earth)
    build_rubble(c_earth, stone)
    build_roots_rope(c_earth, root_mat, rope_mat)
    print("> mobiliário")
    build_pews(c_furn, wood)
    build_altar(c_furn, stone)
    build_statues(c_furn, marble)
    build_fresco(c_furn)
    lit = []
    build_candles(c_furn, wax, brass, lit)
    print("> cruz")
    pivot, cross = build_cross(c_cross, cross_wood, mat_statue_wood(), iron)
    add_noise_anim(pivot, "rotation_euler", 0.035, 60, index=2)
    add_noise_anim(pivot, "rotation_euler", 0.01, 45, index=0)

    print("> atmosfera e luzes")
    fog = mat_volume("M_Nevoeiro_Igreja", 0.011, 0.4)
    me = bpy.data.meshes.new("Nevoeiro")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0, LENGTH / 2, 7.3)) @
                          Matrix.Diagonal((2 * AISLE_X, LENGTH, 14.6, 1)))
    bm.to_mesh(me)
    bm.free()
    me.materials.append(fog)
    new_object("ATMOS_Nevoeiro_Volume", me, c_atmo)
    build_dust(c_atmo, mat_simple("M_Poeira", (0.7, 0.7, 0.68), 1.0))

    v1, v2, v3 = v_cols
    moon(v1, "LUZ_Luar_Normal", 14.0)
    build_flames(v1, lit, flame, "Normal")
    moon(v2, "LUZ_Luar_So", 14.0)
    m3 = moon(v3, "LUZ_Luar_Nuvens", 12.0)
    add_noise_anim(m3.data, "energy", 10.0, 30)
    build_flames(v3, lit, flame, "Nuvens")
    # contraluz muito fraco ao fundo da nave, para a silhueta das colunas
    back = light("LUZ_Recorte_Fundo", "AREA", c_atmo, (0, LENGTH - 0.8, 9.0), 160.0, (0.55, 0.65, 1.0),
                 shape="RECTANGLE", size=6.0, size_y=2.0)
    back.rotation_euler = look_at_rotation(back.location, (0, 8, 1))
    back.visible_camera = False
    # preenchimento frio muito suave: a luz do céu que entra pelo buraco e ressalta
    fill = light("LUZ_Preenchimento_Ceu", "AREA", c_atmo, (HOLE_C.x, HOLE_C.y, VAULT_APEX - 1.0), 220.0,
                 (0.5, 0.6, 0.9), shape="DISK", size=2.2)
    fill.rotation_euler = (0, 0, 0)
    fill.visible_camera = False
    fill.visible_glossy = False
    # luz lateral fria rasante ao longo das colunas (lado esquerdo), sem fonte visível
    side = light("LUZ_Rasante_Colunas", "AREA", c_atmo, (-5.8, 3.0, 5.8), 180.0, (0.55, 0.65, 1.0),
                 shape="RECTANGLE", size=0.6, size_y=3.0)
    side.rotation_euler = look_at_rotation(side.location, (0.0, 14.0, 1.0))
    side.visible_camera = False

    focus = bpy.data.objects.new("FOCO_Personagem", None)
    c_cam.objects.link(focus)
    focus.location = (0.15, 15.2, 1.5)
    build_cameras(c_cam, focus)
    build_markers(c_char)
    setup_world()
    setup_render()
    setup_compositor()
    bpy.data.texts.new("LEIA-ME").write(README_TEXT)

    vl = bpy.context.view_layer
    var_layer = vl.layer_collection.children["05_VARIANTES"]
    for i, c in enumerate(v_cols):
        var_layer.children[c.name].exclude = i != 0
    scn.frame_set(1)
    out = os.path.abspath(args.out)
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    print(f"> guardado: {out}")
    if args.render:
        render_previews(args, v_cols)


PREVIEWS = [
    ("cam1_entrada_nave", "CAM_1_Entrada_Nave", 0),
    ("cam2_contrapicado_cruz", "CAM_2_Contrapicado_Cruz", 0),
    ("cam3_personagem_costas", "CAM_3_Personagem_Costas", 0),
    ("cam4_detalhe_fresco", "CAM_4_Detalhe_Fresco", 0),
    ("cam5_fundo_analise", "CAM_5_Fundo_Analise", 0),
    ("cam6_alto_flutuante", "CAM_6_Alto_Flutuante", 0),
    ("cam1_var2_so_luar", "CAM_1_Entrada_Nave", 1),
]


def render_previews(args, v_cols):
    scn = bpy.context.scene
    os.makedirs(args.render, exist_ok=True)
    scn.cycles.samples = args.samples
    scn.cycles.adaptive_threshold = 0.05
    scn.cycles.volume_step_rate = 2.0
    scn.render.resolution_x = args.res
    scn.render.resolution_y = int(args.res * 9 / 16)
    scn.render.image_settings.file_format = "JPEG"
    scn.render.image_settings.quality = 90
    var_layer = bpy.context.view_layer.layer_collection.children["05_VARIANTES"]
    only = set(filter(None, args.only.split(",")))
    for fname, cam, var in PREVIEWS:
        if only and fname not in only:
            continue
        for i, c in enumerate(v_cols):
            var_layer.children[c.name].exclude = i != var
        scn.camera = bpy.data.objects[cam]
        scn.frame_set(1)
        scn.render.filepath = os.path.join(os.path.abspath(args.render), fname + ".jpg")
        print(f"> render {fname}")
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
