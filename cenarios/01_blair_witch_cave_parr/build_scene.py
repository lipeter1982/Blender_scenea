"""
Cenário 01 — Cave de Rustin Parr (Blair Witch, anos 90, em ruína)

Gera o ficheiro .blend completo: cave de pedra com marcas de mãos, teto de
soalho partido, escada meio destruída, props, iluminação, atmosfera,
câmaras, marcadores para o personagem, variações de luz e look 16 mm.

Uso (dentro do Blender):
    blender -b -P build_scene.py -- --out cave_parr.blend
Uso (módulo bpy via pip):
    python build_scene.py --out cave_parr.blend --render previews --samples 64
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

SEED = 1994
rng = random.Random(SEED)
nrng = np.random.default_rng(SEED)

# ---------------------------------------------------------------------------
# Dimensões principais (metros, Z para cima)
# ---------------------------------------------------------------------------
ROOM_X = 2.5          # paredes interiores em x = ±2.5
ROOM_Y = 2.0          # paredes interiores em y = ±2.0
JOIST_BOTTOM = 2.10   # face inferior das vigas
FLOOR_TOP = 2.30      # topo das vigas / base do soalho de cima
WALL_TOP = 2.45
CORNER = Vector((ROOM_X, ROOM_Y, 0.0))   # o canto (nordeste)

# Abertura da escada no teto
STAIR_X0, STAIR_X1 = -2.5, -1.0
STAIR_Y0, STAIR_Y1 = -2.0, -0.2
# Buraco grande no soalho
HOLE_X0, HOLE_X1 = -0.4, 0.9
HOLE_Y0, HOLE_Y1 = 0.2, 1.3


# ---------------------------------------------------------------------------
# Utilitários gerais
# ---------------------------------------------------------------------------
def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="cave_parr.blend")
    p.add_argument("--render", default="", help="pasta para renders de pré-visualização")
    p.add_argument("--samples", type=int, default=64)
    p.add_argument("--res", type=int, default=1280, help="largura do preview")
    p.add_argument("--only", default="", help="renderizar só estes presets (separados por vírgula)")
    return p.parse_args(argv)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


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


def floor_height(x, y):
    """Altura do chão de terra (usada também para pousar objetos)."""
    h = noise.noise(Vector((x * 1.3, y * 1.3, 0.7))) * 0.018
    h += noise.noise(Vector((x * 5.0, y * 5.0, 3.1))) * 0.006
    h += noise.noise(Vector((x * 17.0, y * 17.0, 9.3))) * 0.0015
    # pegadas gastas em frente ao canto
    for fx, fy in FOOT_MARKS:
        d2 = ((x - fx) / 0.06) ** 2 + ((y - fy) / 0.06) ** 2
        h -= 0.012 * math.exp(-d2)
    # poças
    for px, py, pr, pd in PUDDLES:
        d2 = ((x - px) ** 2 + (y - py) ** 2) / (pr * pr)
        h -= pd * math.exp(-d2)
    return h


# personagem virado para o canto: pés a ~0.45 m de cada parede
_facing = Vector((1, 1, 0)).normalized()
_side = Vector((-_facing.y, _facing.x, 0))
_m1 = Vector((ROOM_X - 0.45, ROOM_Y - 0.45, 0))
FOOT_MARKS = [tuple((_m1 + _side * 0.1).xy), tuple((_m1 - _side * 0.1).xy)]
STICK_FLOOR = (1.1, 1.1)
PUDDLES = [(-0.9, 1.75, 0.35, 0.012), (2.2, -1.2, 0.3, 0.010), (0.4, 0.9, 0.45, 0.008)]


# ---------------------------------------------------------------------------
# Geometria: caixas, cilindros e UVs
# ---------------------------------------------------------------------------
class Builder:
    """Acumula geometria num bmesh com atributo 'rand' por face e UVs."""

    def __init__(self):
        self.bm = bmesh.new()
        self.rand = self.bm.faces.layers.float.new("rand")
        self.uv = self.bm.loops.layers.uv.new("UVMap")

    def _tag(self, faces, mat_index, value):
        for f in faces:
            f[self.rand] = value
            f.material_index = mat_index

    def box(self, center, axes, dims, mat=0, rand=None, uv_mode="long"):
        """Caixa orientada. axes = (u, v, w) ortonormados, dims = tamanhos."""
        u, v, w = (Vector(a).normalized() for a in axes)
        if u.cross(v).dot(w) < 0:
            w = -w  # manter a base direita (normais para fora)
        m = Matrix((
            (u.x * dims[0], v.x * dims[1], w.x * dims[2], center[0]),
            (u.y * dims[0], v.y * dims[1], w.y * dims[2], center[1]),
            (u.z * dims[0], v.z * dims[1], w.z * dims[2], center[2]),
            (0, 0, 0, 1),
        ))
        res = bmesh.ops.create_cube(self.bm, size=1.0, matrix=m)
        faces = {f for vv in res["verts"] for f in vv.link_faces}
        rv = rng.random() if rand is None else rand
        self._tag(faces, mat, rv)
        if uv_mode == "long":
            # u ao longo do eixo mais comprido (veio da madeira)
            longest = max(range(3), key=lambda i: dims[i])
            ax = (u, v, w)
            others = [i for i in range(3) if i != longest]
            c = Vector(center)
            for f in faces:
                f.normal_update()
                n = f.normal
                for loop in f.loops:
                    d = loop.vert.co - c
                    a = d.dot(ax[longest])
                    # escolher o eixo lateral que não é a normal da face
                    o = [i for i in others if abs(n.dot(ax[i])) < 0.5]
                    b = d.dot(ax[o[0]]) if o else 0.0
                    loop[self.uv].uv = (a + rv * 7.0, b + rv * 3.0)
        return faces

    def cylinder(self, p0, p1, r0, r1, segs=8, mat=0, rand=None):
        p0, p1 = Vector(p0), Vector(p1)
        d = p1 - p0
        q = d.to_track_quat("Z", "Y")
        m = Matrix.Translation((p0 + p1) / 2) @ q.to_matrix().to_4x4()
        res = bmesh.ops.create_cone(self.bm, cap_ends=True, cap_tris=False, segments=segs,
                                    radius1=r0, radius2=r1, depth=d.length, matrix=m)
        faces = {f for vv in res["verts"] for f in vv.link_faces}
        self._tag(faces, mat, rng.random() if rand is None else rand)
        return faces

    def ico(self, center, radius, scale=(1, 1, 1), subdiv=1, jitter=0.25, mat=0, rot=None):
        m = Matrix.Translation(center)
        if rot is not None:
            m = m @ Euler(rot).to_matrix().to_4x4()
        m = m @ Matrix.Diagonal((*scale, 1))
        res = bmesh.ops.create_icosphere(self.bm, subdivisions=subdiv, radius=radius, matrix=m)
        c = Vector(center)
        for vv in res["verts"]:
            vv.co = c + (vv.co - c) * (1 + (rng.random() - 0.5) * jitter)
        faces = {f for vv in res["verts"] for f in vv.link_faces}
        self._tag(faces, mat, rng.random())
        return faces

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
# Materiais (nós)
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

    # atalhos -------------------------------------------------------------
    def texcoord(self):
        if not hasattr(self, "_tc"):
            self._tc = self.node("ShaderNodeTexCoord")
        return self._tc

    def attr(self, name):
        n = self.node("ShaderNodeAttribute", attribute_name=name)
        return n

    def noise(self, vec, scale, detail=4.0, rough=0.55, dims="3D", w=None):
        n = self.node("ShaderNodeTexNoise", noise_dimensions=dims)
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        if vec is not None:
            self.link(vec, n.inputs["Vector"])
        if w is not None:
            n.inputs["W"].default_value = w
        return n

    def ramp(self, fac, stops):
        n = self.node("ShaderNodeValToRGB")
        els = n.color_ramp.elements
        while len(els) < len(stops):
            els.new(0.5)
        for el, (pos, col) in zip(els, stops):
            el.position = pos
            el.color = (*col, 1.0) if len(col) == 3 else col
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

    def math(self, op, a, b=None, clamp=False):
        n = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        self._set(n.inputs[0], a)
        if b is not None:
            self._set(n.inputs[1], b)
        return n.outputs[0]

    def maprange(self, val, a, b, c=0.0, d=1.0, clamp=True):
        n = self.node("ShaderNodeMapRange", clamp=clamp)
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

    def bump(self, height, strength=0.3, distance=0.02, normal=None):
        n = self.node("ShaderNodeBump")
        n.inputs["Strength"].default_value = strength
        n.inputs["Distance"].default_value = distance
        self._set(n.inputs["Height"], height)
        if normal is not None:
            self.link(normal, n.inputs["Normal"])
        return n.outputs["Normal"]

    def set(self, name, v):
        self._set(self.bsdf.inputs[name], v)


def sep_z(m):
    geo = m.node("ShaderNodeNewGeometry")
    sep = m.node("ShaderNodeSeparateXYZ")
    m.link(geo.outputs["Position"], sep.inputs[0])
    return sep.outputs["Z"]


def mat_stone(name, hand_img):
    """Alvenaria rústica: pedras irregulares (Voronoi) com deslocamento real."""
    m = Mat(name)
    tc = m.texcoord()
    obj = tc.outputs["Object"]
    mp = m.node("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, 1.0, 1.55)   # pedras mais largas que altas
    m.link(obj, mp.inputs["Vector"])
    warp = m.noise(mp.outputs["Vector"], 2.0, 2.0, 0.5)
    wv = m.node("ShaderNodeMix", data_type="VECTOR")
    sock(wv, "Factor_Float").default_value = 0.035
    m.link(mp.outputs["Vector"], sock(wv, "A_Vector"))
    m.link(warp.outputs["Color"], sock(wv, "B_Vector"))
    coord = sock(wv, "Result_Vector", out=True)

    edge = m.node("ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE")
    edge.inputs["Scale"].default_value = 4.6
    edge.inputs["Randomness"].default_value = 0.85
    m.link(coord, edge.inputs["Vector"])
    cell = m.node("ShaderNodeTexVoronoi", feature="F1")
    cell.inputs["Scale"].default_value = 4.6
    cell.inputs["Randomness"].default_value = 0.85
    m.link(coord, cell.inputs["Vector"])
    cell_sep = m.node("ShaderNodeSeparateColor")
    m.link(cell.outputs["Color"], cell_sep.inputs[0])
    crand = cell_sep.outputs[0]

    # perfil da pedra: junta funda, face abaulada e lascada
    prof = m.maprange(edge.outputs["Distance"], 0.01, 0.05, 0.0, 1.0)
    prof = m.math("POWER", prof, 0.4)
    chips = m.noise(obj, 11.0, 6.0, 0.6)
    fine = m.noise(obj, 55.0, 4.0, 0.55)
    face = m.math("ADD", m.math("MULTIPLY", chips.outputs["Fac"], 0.55),
                  m.math("MULTIPLY", fine.outputs["Fac"], 0.15))
    face = m.math("ADD", face, m.math("MULTIPLY", crand, 0.35))
    height = m.math("MULTIPLY", prof, face)
    mortar = m.maprange(edge.outputs["Distance"], 0.008, 0.022, 1.0, 0.0)
    mort_n = m.noise(obj, 30.0, 6.0, 0.6)
    height = m.math("ADD", height, m.math("MULTIPLY", mortar, m.math("MULTIPLY", mort_n.outputs["Fac"], 0.12)))

    disp = m.node("ShaderNodeDisplacement", loc=(100, -400))
    disp.inputs["Midlevel"].default_value = 0.0
    disp.inputs["Scale"].default_value = 0.055
    m.link(height, disp.inputs["Height"])
    m.link(disp.outputs["Displacement"], m.out.inputs["Displacement"])
    m.mat.displacement_method = "DISPLACEMENT"

    # cor
    base = m.ramp(crand, [(0.0, (0.1, 0.092, 0.08)), (0.45, (0.19, 0.175, 0.15)),
                          (0.8, (0.27, 0.245, 0.205)), (1.0, (0.2, 0.19, 0.17))]).outputs["Color"]
    grime = m.noise(obj, 6.0, 8.0, 0.62)
    grime_c = m.ramp(grime.outputs["Fac"], [(0.35, (0.55, 0.52, 0.48)), (0.7, (1.0, 1.0, 1.0))])
    col = m.mix(1.0, base, grime_c.outputs["Color"], "MULTIPLY")
    mort_c = m.ramp(mort_n.outputs["Fac"], [(0.3, (0.07, 0.064, 0.056)), (0.7, (0.13, 0.12, 0.1))])
    col = m.mix(mortar, col, mort_c.outputs["Color"])
    # escorrências verticais
    smp = m.node("ShaderNodeMapping")
    smp.inputs["Scale"].default_value = (9.0, 9.0, 0.6)
    m.link(obj, smp.inputs["Vector"])
    streak = m.noise(smp.outputs["Vector"], 3.0, 3.0, 0.5)
    col = m.mix(m.math("MULTIPLY", m.maprange(streak.outputs["Fac"], 0.55, 0.75), 0.55), col, (0.04, 0.036, 0.03))
    # salitre
    z = sep_z(m)
    salt = m.maprange(m.noise(obj, 2.2, 6.0, 0.7).outputs["Fac"], 0.58, 0.72)
    salt = m.math("MULTIPLY", salt, m.maprange(z, 0.05, 0.9, 1.0, 0.2))
    col = m.mix(m.math("MULTIPLY", salt, 0.5), col, (0.42, 0.40, 0.35))
    # humidade junto ao chão
    wet = m.maprange(z, 0.0, 0.55, 1.0, 0.0)
    wet = m.math("MULTIPLY", wet, m.maprange(m.noise(obj, 3.0, 4.0, 0.6).outputs["Fac"], 0.3, 0.7, 0.5, 1.0))
    col = m.mix(m.math("MULTIPLY", wet, 0.6), col, (0.03, 0.028, 0.025))
    # sujidade acumulada nas juntas e cavidades
    cav = m.math("SUBTRACT", 1.0, prof)
    col = m.mix(m.math("MULTIPLY", m.math("POWER", cav, 2.0), 0.3), col, (0.05, 0.045, 0.04))
    # marcas de mãos (R = lama, G = escuras) — mais fracas dentro das juntas
    img = m.node("ShaderNodeTexImage", image=hand_img, interpolation="Linear")
    m.link(tc.outputs["UV"], img.inputs["Vector"])
    sep = m.node("ShaderNodeSeparateColor")
    m.link(img.outputs["Color"], sep.inputs[0])
    reach = m.maprange(prof, 0.0, 0.5, 0.35, 1.0)
    mud = m.math("MULTIPLY", sep.outputs[0], reach)
    dark = m.math("MULTIPLY", sep.outputs[1], reach)
    col = m.mix(m.math("MULTIPLY", mud, 0.95), col, (0.05, 0.03, 0.017))
    col = m.mix(m.math("MULTIPLY", dark, 0.95), col, (0.011, 0.008, 0.007))
    m.set("Base Color", col)
    rough = m.mixf(wet, 0.88, 0.55)
    rough = m.mixf(m.math("MAXIMUM", mud, dark), rough, 0.6)
    m.set("Roughness", rough)
    m.set("Normal", m.bump(m.math("ADD", fine.outputs["Fac"], m.math("MULTIPLY", mud, 0.3)), 0.35, 0.005))
    return m.mat


def mat_wood(name, dark=1.0):
    m = Mat(name)
    tc = m.texcoord()
    uv = tc.outputs["UV"]
    rnd = m.attr("rand").outputs["Fac"]
    # veio: esticar ao longo de u
    mp = m.node("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.35, 9.0, 9.0)
    m.link(uv, mp.inputs["Vector"])
    grain = m.noise(mp.outputs["Vector"], 3.0, 12.0, 0.7)
    wave = m.node("ShaderNodeTexWave", wave_type="BANDS", bands_direction="Y")
    wave.inputs["Scale"].default_value = 1.2
    wave.inputs["Distortion"].default_value = 6.0
    wave.inputs["Detail"].default_value = 6.0
    m.link(mp.outputs["Vector"], wave.inputs["Vector"])
    g = m.math("ADD", m.math("MULTIPLY", wave.outputs["Fac"], 0.5), m.math("MULTIPLY", grain.outputs["Fac"], 0.5))
    k = 1.0 / dark
    base = m.ramp(g, [(0.25, (0.030 * k, 0.024 * k, 0.019 * k)), (0.6, (0.085 * k, 0.07 * k, 0.055 * k)),
                      (0.9, (0.15 * k, 0.13 * k, 0.105 * k))])
    tint = m.ramp(rnd, [(0.0, (0.8, 0.8, 0.82)), (0.5, (1.0, 0.96, 0.9)), (1.0, (1.15, 1.08, 0.98))])
    col = m.mix(1.0, base.outputs["Color"], tint.outputs["Color"], "MULTIPLY")
    # podridão / bolor escuro em manchas
    rot = m.noise(tc.outputs["Object"], 3.5, 6.0, 0.65)
    rotm = m.maprange(rot.outputs["Fac"], 0.55, 0.7)
    col = m.mix(m.math("MULTIPLY", rotm, 0.7), col, (0.018, 0.017, 0.014))
    m.set("Base Color", col)
    m.set("Roughness", 0.88)
    fine = m.noise(mp.outputs["Vector"], 40.0, 4.0, 0.6)
    h = m.math("ADD", g, m.math("MULTIPLY", fine.outputs["Fac"], 0.4))
    m.set("Normal", m.bump(h, 0.35, 0.01))
    return m.mat


def mat_dirt():
    m = Mat("M_Chao_Terra")
    tc = m.texcoord()
    obj = tc.outputs["Object"]
    wet = m.attr("wet").outputs["Fac"]
    wear = m.attr("wear").outputs["Fac"]
    n1 = m.noise(obj, 2.5, 6.0, 0.6)
    n2 = m.noise(obj, 35.0, 8.0, 0.65)
    g = m.math("ADD", m.math("MULTIPLY", n1.outputs["Fac"], 0.65), m.math("MULTIPLY", n2.outputs["Fac"], 0.35))
    col = m.ramp(g, [(0.25, (0.022, 0.016, 0.011)), (0.5, (0.055, 0.042, 0.03)),
                     (0.72, (0.095, 0.074, 0.052)), (0.9, (0.065, 0.055, 0.045))]).outputs["Color"]
    speck = m.noise(obj, 220.0, 2.0, 0.5)
    col = m.mix(m.math("MULTIPLY", m.maprange(speck.outputs["Fac"], 0.6, 0.72), 0.6), col, (0.16, 0.14, 0.12))
    col = m.mix(m.math("MULTIPLY", wet, 0.75), col, (0.022, 0.018, 0.014))
    col = m.mix(m.math("MULTIPLY", wear, 0.55), col, (0.03, 0.024, 0.018))
    m.set("Base Color", col)
    puddle = m.maprange(wet, 0.72, 0.82)
    rough = m.mixf(wet, 0.95, 0.45)
    rough = m.mixf(wear, rough, 0.55)
    rough = m.mixf(puddle, rough, 0.04)
    m.set("Roughness", rough)
    pebb = m.node("ShaderNodeTexVoronoi")
    pebb.inputs["Scale"].default_value = 60.0
    m.link(obj, pebb.inputs["Vector"])
    h = m.math("ADD", n2.outputs["Fac"], m.math("MULTIPLY", pebb.outputs["Distance"], 0.6))
    h = m.math("MULTIPLY", h, m.math("SUBTRACT", 1.0, puddle))
    m.set("Normal", m.bump(h, 0.9, 0.01))
    clumps = m.noise(obj, 9.0, 6.0, 0.7)
    dh = m.math("ADD", m.math("MULTIPLY", clumps.outputs["Fac"], 0.7), m.math("MULTIPLY", h, 0.3))
    dh = m.math("MULTIPLY", dh, m.math("SUBTRACT", 1.0, m.math("MULTIPLY", wear, 0.7)))
    disp = m.node("ShaderNodeDisplacement")
    disp.inputs["Midlevel"].default_value = 0.5
    disp.inputs["Scale"].default_value = 0.012
    m.link(dh, disp.inputs["Height"])
    m.link(disp.outputs["Displacement"], m.out.inputs["Displacement"])
    m.mat.displacement_method = "BOTH"
    return m.mat


def mat_simple(name, color, rough=0.8, metal=0.0, noise_scale=0.0, bump=0.0):
    m = Mat(name)
    if noise_scale:
        n = m.noise(m.texcoord().outputs["Object"], noise_scale, 6.0, 0.6)
        c = m.ramp(n.outputs["Fac"], [(0.3, tuple(v * 0.6 for v in color)), (0.8, color)])
        m.set("Base Color", c.outputs["Color"])
        if bump:
            m.set("Normal", m.bump(n.outputs["Fac"], bump, 0.01))
    else:
        m.set("Base Color", color)
    m.set("Roughness", rough)
    m.set("Metallic", metal)
    return m.mat


def mat_leaf():
    m = Mat("M_Folhas")
    rnd = m.attr("rand").outputs["Fac"]
    col = m.ramp(rnd, [(0.0, (0.025, 0.018, 0.012)), (0.35, (0.05, 0.034, 0.02)),
                       (0.7, (0.075, 0.05, 0.028)), (1.0, (0.045, 0.042, 0.032))])
    n = m.noise(m.texcoord().outputs["Object"], 40.0, 4.0, 0.6)
    c = m.mix(0.35, col.outputs["Color"], m.ramp(n.outputs["Fac"], [(0.3, (0.4, 0.4, 0.4)), (0.7, (1, 1, 1))]).outputs["Color"], "MULTIPLY")
    m.set("Base Color", c)
    m.set("Roughness", 0.75)
    return m.mat


def mat_volume(name, density, anisotropy=0.3, color=(0.8, 0.82, 0.86), noise_amt=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Color"].default_value = (*color, 1)
    vol.inputs["Anisotropy"].default_value = anisotropy
    if noise_amt:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 2.5
        nz.inputs["Detail"].default_value = 3.0
        nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["From Min"].default_value = 0.35
        mr.inputs["From Max"].default_value = 0.75
        mr.inputs["To Min"].default_value = density * (1 - noise_amt)
        mr.inputs["To Max"].default_value = density * (1 + noise_amt)
        nt.links.new(nz.outputs["Fac"], mr.inputs["Value"])
        # esbater para as bordas (esfera)
        grad = nt.nodes.new("ShaderNodeTexGradient")
        grad.gradient_type = "SPHERICAL"
        nt.links.new(tc.outputs["Object"], grad.inputs["Vector"])
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        nt.links.new(mr.outputs["Result"], mul.inputs[0])
        nt.links.new(grad.outputs["Fac"], mul.inputs[1])
        nt.links.new(mul.outputs[0], vol.inputs["Density"])
    else:
        vol.inputs["Density"].default_value = density
    nt.links.new(vol.outputs[0], out.inputs["Volume"])
    return mat


# ---------------------------------------------------------------------------
# Marcas de mãos (textura gerada)
# ---------------------------------------------------------------------------
HAND_RES = 800  # píxeis por metro


def value_noise(h, w, cell, seed):
    r = np.random.default_rng(seed)
    gh, gw = h // cell + 3, w // cell + 3
    g = r.random((gh, gw)).astype(np.float32)
    ys = np.arange(h) / cell
    xs = np.arange(w) / cell
    y0, x0 = ys.astype(int), xs.astype(int)
    fy, fx = ys - y0, xs - x0
    fy = (fy * fy * (3 - 2 * fy))[:, None]
    fx = (fx * fx * (3 - 2 * fx))[None, :]
    a = g[y0][:, x0]
    b = g[y0][:, x0 + 1]
    c = g[y0 + 1][:, x0]
    d = g[y0 + 1][:, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def hand_mask(size_px, scale, angle, mirror, seed):
    """Máscara 0..1 de uma mão de criança pequena, centrada no patch."""
    half = size_px / 2
    yy, xx = np.mgrid[0:size_px, 0:size_px].astype(np.float32)
    x = (xx - half) / HAND_RES
    y = (yy - half) / HAND_RES
    ca, sa = math.cos(-angle), math.sin(-angle)
    x, y = x * ca - y * sa, x * sa + y * ca
    x, y = x / scale, y / scale
    if mirror:
        x = -x
    edge = 0.0025 / scale
    a, b = 0.027, 0.031
    palm = np.clip((1 - np.sqrt((x / a) ** 2 + ((y + 0.004) / b) ** 2)) * (a / edge), 0, 1)
    mask = palm
    fingers = [  # (base_x, base_y, comprimento, ângulo em graus, raio)
        (0.019, 0.022, 0.028, -14, 0.0058),
        (0.008, 0.027, 0.036, -5, 0.0063),
        (-0.004, 0.028, 0.040, 1, 0.0065),
        (-0.016, 0.025, 0.035, 8, 0.0062),
        (-0.024, -0.006, 0.030, 52, 0.0075),
    ]
    for bx, by, ln, ang, r in fingers:
        t = math.radians(ang)
        dx, dy = -math.sin(t), math.cos(t)
        ex, ey = bx + dx * ln, by + dy * ln
        px, py = x - bx, y - by
        proj = np.clip((px * dx + py * dy) / ln, 0, 1)
        qx, qy = px - proj * dx * ln, py - proj * dy * ln
        d = np.sqrt(qx * qx + qy * qy)
        mask = np.maximum(mask, np.clip((r - d) / edge, 0, 1))
    # pressão irregular e falhas
    n1 = value_noise(size_px, size_px, 6, seed)
    n2 = value_noise(size_px, size_px, 2, seed + 1)
    pressure = np.clip(n1 * 1.2 + n2 * 0.4 - 0.15, 0, 1)
    mask = mask * np.clip(pressure * 1.6, 0, 1)
    return mask.astype(np.float32)


def stamp(canvas, patch, cx, cy):
    s = patch.shape[0]
    x0, y0 = int(cx - s / 2), int(cy - s / 2)
    h, w = canvas.shape
    xa, ya = max(x0, 0), max(y0, 0)
    xb, yb = min(x0 + s, w), min(y0 + s, h)
    if xa >= xb or ya >= yb:
        return
    canvas[ya:yb, xa:xb] = np.maximum(canvas[ya:yb, xa:xb], patch[ya - y0:yb - y0, xa - x0:xb - x0])


def smear(patch, direction, steps, step_px):
    out = patch.copy()
    dx, dy = direction
    for i in range(1, steps):
        sx, sy = int(round(dx * step_px * i)), int(round(dy * step_px * i))
        shifted = np.roll(np.roll(patch, sy, axis=0), sx, axis=1)
        out = np.maximum(out, shifted * (1 - i / steps) * 0.7)
    return out


def make_hand_image(name, length, height, count, corner_u, seed):
    """corner_u: posição (m) do canto ao longo da parede (ou None)."""
    w, h = int(length * HAND_RES), int(height * HAND_RES)
    mud = np.zeros((h, w), np.float32)
    dark = np.zeros((h, w), np.float32)
    r = random.Random(seed)
    placed = 0
    tries = 0
    while placed < count and tries < count * 20:
        tries += 1
        if corner_u is not None and r.random() < 0.65:
            # concentradas perto do canto
            u = corner_u + (r.random() ** 1.6) * 2.2 * (1 if corner_u < 0.5 else -1)
        else:
            u = r.uniform(0.15, length - 0.15)
        z = r.triangular(0.3, 1.85, 0.9)
        if corner_u is not None and abs(u - corner_u) < 0.32:
            continue  # o canto fica limpo
        scale = r.uniform(1.05, 1.35)
        angle = math.radians(r.gauss(0, 22))
        if r.random() < 0.12:
            angle += math.pi  # dedos para baixo (a escorregar)
        size = int(0.17 * scale * HAND_RES)
        patch = hand_mask(size, scale, angle, r.random() < 0.5, seed * 1000 + placed)
        if r.random() < 0.3:
            d = r.uniform(-0.4, 0.4)
            patch = smear(patch, (d, -1.0), r.randint(4, 10), r.uniform(2, 5))
        target = dark if r.random() < 0.5 else mud
        stamp(target, patch * r.uniform(0.6, 1.0), u * HAND_RES, z * HAND_RES)
        placed += 1
    img = bpy.data.images.new(name, w, h, alpha=False)
    px = np.zeros((h, w, 4), np.float32)
    px[..., 0] = mud
    px[..., 1] = dark
    px[..., 3] = 1.0
    img.pixels.foreach_set(px.ravel())
    img.file_format = "PNG"
    img.pack()
    img.colorspace_settings.name = "Non-Color"
    return img


# ---------------------------------------------------------------------------
# Construção
# ---------------------------------------------------------------------------
WALLS = {
    # nome: (origem, eixo u, normal para dentro, comprimento, posição do canto em u)
    "Norte": (Vector((-2.62, ROOM_Y, 0)), Vector((1, 0, 0)), Vector((0, -1, 0)), 5.24, 2.62 + ROOM_X),
    "Este": (Vector((ROOM_X, -2.12, 0)), Vector((0, 1, 0)), Vector((-1, 0, 0)), 4.24, 2.12 + ROOM_Y),
    "Sul": (Vector((-2.62, -ROOM_Y, 0)), Vector((1, 0, 0)), Vector((0, 1, 0)), 5.24, None),
    "Oeste": (Vector((-ROOM_X, -2.12, 0)), Vector((0, 1, 0)), Vector((1, 0, 0)), 4.24, None),
}
HAND_COUNTS = {"Norte": 70, "Este": 60, "Sul": 18, "Oeste": 14}


def build_walls(col):
    step = 0.012
    for i, (name, (origin, u, n, length, corner_u)) in enumerate(WALLS.items()):
        img = make_hand_image(f"IMG_Maos_{name}", length, WALL_TOP, HAND_COUNTS[name],
                              None if corner_u is None else min(corner_u, length), 50 + i)
        nu, nz = int(length / step) + 1, int((WALL_TOP + 0.05) / step) + 1
        uu = np.linspace(0, length, nu)
        zz = np.linspace(-0.05, WALL_TOP, nz)
        U, Z = np.meshgrid(uu, zz)
        co = np.array(origin)[None, None, :] + U[..., None] * np.array(u)[None, None, :]
        co[..., 2] = Z
        verts = co.reshape(-1, 3)
        idx = np.arange(nu * nz).reshape(nz, nu)
        a, b_, c, d = idx[:-1, :-1], idx[:-1, 1:], idx[1:, 1:], idx[1:, :-1]
        quads = np.stack([a, b_, c, d], -1).reshape(-1, 4)
        # a normal de (a, b, c, d) é u × z; virar se não apontar para dentro da sala
        if Vector(u).cross(Vector((0, 0, 1))).dot(n) < 0:
            quads = quads[:, ::-1]
        me = bpy.data.meshes.new(f"Parede_{name}")
        me.vertices.add(len(verts))
        me.vertices.foreach_set("co", verts.astype(np.float32).ravel())
        me.loops.add(quads.size)
        me.loops.foreach_set("vertex_index", quads.astype(np.int32).ravel())
        me.polygons.add(len(quads))
        me.polygons.foreach_set("loop_start", np.arange(0, quads.size, 4, dtype=np.int32))
        me.update(calc_edges=True)
        uv = me.uv_layers.new(name="UVMap")
        lv = verts[quads.ravel()]
        uvs = np.stack([(lv - np.array(origin)) @ np.array(u) / length, lv[:, 2] / WALL_TOP], -1)
        uv.data.foreach_set("uv", uvs.astype(np.float32).ravel())
        me.materials.append(mat_stone(f"M_Pedra_{name}", img))
        me.shade_smooth()
        new_object(f"Parede_{name}", me, col)


def build_floor(col):
    x0, x1, y0, y1 = -2.62, 2.62, -2.12, 2.12
    step = 0.01
    nx, ny = int((x1 - x0) / step) + 1, int((y1 - y0) / step) + 1
    verts, wet, wear = [], [], []
    for j in range(ny):
        y = y0 + j * step
        for i in range(nx):
            x = x0 + i * step
            verts.append((x, y, floor_height(x, y)))
            d = min(ROOM_X - abs(x), ROOM_Y - abs(y))
            nval = noise.noise(Vector((x * 2.0, y * 2.0, 5.5))) * 0.5 + 0.5
            wv = math.exp(-max(d, 0) / 0.28) * (0.5 + 0.6 * nval)
            for px, py, pr, _ in PUDDLES:
                wv += 1.1 * math.exp(-((x - px) ** 2 + (y - py) ** 2) / (pr * pr * 0.55))
            wet.append(min(wv, 1.0))
            we = 0.0
            for fx, fy in FOOT_MARKS:
                we += math.exp(-(((x - fx) / 0.075) ** 2 + ((y - fy) / 0.075) ** 2))
            wear.append(min(we, 1.0))
    faces = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            a = j * nx + i
            faces.append((a, a + 1, a + nx + 1, a + nx))
    me = bpy.data.meshes.new("Chao")
    me.from_pydata(verts, [], faces)
    for name, data in (("wet", wet), ("wear", wear)):
        at = me.attributes.new(name, "FLOAT", "POINT")
        at.data.foreach_set("value", data)
    me.materials.append(mat_dirt())
    me.shade_smooth()
    return new_object("Chao_Terra", me, col)


def build_ceiling(col, wood):
    b = Builder()
    # vigas ao longo de x
    ys = [-1.8 + 0.45 * k for k in range(9)]
    for y in ys:
        segs = [(-ROOM_X, ROOM_X)]
        if STAIR_Y0 <= y <= STAIR_Y1:
            segs = [(STAIR_X1, ROOM_X)]
        if HOLE_Y0 <= y <= HOLE_Y1:
            # viga partida no buraco
            new = []
            for a, c in segs:
                new += [(a, HOLE_X0 + rng.uniform(-0.1, 0.05)), (HOLE_X1 + rng.uniform(-0.05, 0.15), c)]
            segs = new
        for a, c in segs:
            ln = c - a
            cen = (a + c) / 2
            sag = Euler((rng.gauss(0, 0.004), rng.gauss(0, 0.006), rng.gauss(0, 0.01))).to_matrix()
            b.box((cen, y, JOIST_BOTTOM + 0.1), (sag @ Vector((1, 0, 0)), sag @ Vector((0, 1, 0)),
                                                  sag @ Vector((0, 0, 1))), (ln, 0.085, 0.2))
    # travessa da abertura da escada
    b.box((STAIR_X1 - 0.045, (STAIR_Y0 + STAIR_Y1) / 2, JOIST_BOTTOM + 0.1), ((0, 1, 0), (1, 0, 0), (0, 0, 1)),
          (STAIR_Y1 - STAIR_Y0, 0.09, 0.2))
    # viga caída, encostada do chão até ao teto
    p0 = Vector((0.55, 0.55, floor_height(0.55, 0.55) + 0.05))
    p1 = Vector((-0.35, 1.05, JOIST_BOTTOM - 0.05))
    d = (p1 - p0).normalized()
    side = d.cross(Vector((0, 0, 1))).normalized()
    b.box((p0 + p1) / 2, (d, side, side.cross(d)), ((p1 - p0).length, 0.085, 0.19))
    # tábuas do soalho ao longo de y
    x = -ROOM_X - 0.1
    k = 0
    while x < ROOM_X + 0.1:
        w = rng.uniform(0.13, 0.2)
        gap = rng.uniform(0.004, 0.02)
        cx = x + w / 2
        segs = [(-ROOM_Y - 0.1, ROOM_Y + 0.1)]
        if STAIR_X0 - 0.2 <= cx <= STAIR_X1:
            segs = [(STAIR_Y1, ROOM_Y + 0.1)]
        if HOLE_X0 <= cx <= HOLE_X1:
            a = HOLE_Y0 + rng.uniform(-0.25, 0.15)
            c = HOLE_Y1 + rng.uniform(-0.15, 0.3)
            new = []
            for s0, s1 in segs:
                if s0 < a:
                    new.append((s0, min(a, s1)))
                if c < s1:
                    new.append((max(c, s0), s1))
            segs = new
            # algumas tábuas penduradas no buraco
            if rng.random() < 0.35:
                ln = rng.uniform(0.5, 0.9)
                ang = math.radians(rng.uniform(40, 75))
                piv = Vector((cx, c, FLOOR_TOP))
                dvec = Vector((0, -math.cos(ang), -math.sin(ang)))
                b.box(piv + dvec * ln / 2, (dvec, (1, 0, 0), Vector((1, 0, 0)).cross(dvec)), (ln, w, 0.024))
        # buracos pequenos
        if 1.55 <= cx <= 1.95:
            segs = [(s0, s1) for s0, s1 in segs for s0, s1 in
                    [(s0, min(s1, -1.2)), (max(s0, -0.55), s1)] if s1 - s0 > 0.05]
        if -2.2 <= cx <= -1.95:
            segs = [(s0, s1) for s0, s1 in segs for s0, s1 in
                    [(s0, min(s1, 1.1)), (max(s0, 1.6), s1)] if s1 - s0 > 0.05]
        for s0, s1 in segs:
            tilt = Euler((0, rng.gauss(0, 0.01), rng.gauss(0, 0.004))).to_matrix()
            b.box((cx, (s0 + s1) / 2, FLOOR_TOP + 0.0125 + rng.uniform(-0.003, 0.003)),
                  (tilt @ Vector((0, 1, 0)), tilt @ Vector((1, 0, 0)), tilt @ Vector((0, 0, 1))),
                  (s1 - s0, w, 0.025))
        x += w + gap
        k += 1
    return b.to_object("Teto_Vigas_Soalho", col, [wood])


def build_stairs(col, wood):
    b = Builder()
    y_bot, y_top, z_top = 0.5, -1.85, FLOOR_TOP
    n = 9
    rise = z_top / n
    run = (y_bot - y_top) / n
    xl, xr = -2.44, -1.56
    # longarinas
    p0, p1 = Vector((0, y_bot + 0.1, 0.0)), Vector((0, y_top - 0.05, z_top + 0.05))
    d = (p1 - p0).normalized()
    for x in (xl, xr):
        a, c = p0.copy(), p1.copy()
        a.x = c.x = x
        b.box((a + c) / 2, (d, (1, 0, 0), Vector((1, 0, 0)).cross(d)), ((c - a).length, 0.05, 0.24))
    for i in range(n):
        if i in (2, 5):
            continue  # degraus em falta
        z = (i + 1) * rise
        y = y_bot - (i + 0.5) * run
        if i == 6:
            # degrau partido, pendurado de um lado
            piv = Vector((xr, y, z))
            ang = math.radians(58)
            dv = Vector((-math.cos(ang), 0, -math.sin(ang)))
            b.box(piv + dv * 0.44, (dv, (0, 1, 0), dv.cross(Vector((0, 1, 0)))), (0.88, 0.24, 0.035))
            continue
        b.box(((xl + xr) / 2, y, z - 0.0175), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (xr - xl + 0.06, 0.25, 0.035))
    # restos do degrau caído no chão
    b.box((-1.3, 0.8, 0.02), (Vector((0.9, 0.4, 0)).normalized(), Vector((-0.4, 0.9, 0)).normalized(), (0, 0, 1)),
          (0.45, 0.22, 0.034))
    return b.to_object("Escada", col, [wood])


def build_upper(col, wood):
    """Poço da escada no piso de cima, com porta entreaberta."""
    b = Builder()
    top = 4.4
    def boards(p0, p1, z0, z1, thick=0.03):
        """Parede de tábuas verticais entre p0 e p1 (planta)."""
        p0, p1 = Vector((*p0, 0)), Vector((*p1, 0))
        along = (p1 - p0).normalized()
        length = (p1 - p0).length
        t = 0.0
        while t < length - 0.01:
            wdt = min(rng.uniform(0.14, 0.21), length - t)
            c = p0 + along * (t + wdt / 2)
            zz1 = z1 - (rng.uniform(0, 0.35) if rng.random() < 0.25 else 0)
            b.box((c.x, c.y, (z0 + zz1) / 2), ((0, 0, 1), along, Vector((0, 0, 1)).cross(along)),
                  (zz1 - z0, wdt - rng.uniform(0.004, 0.015), thick))
            t += wdt

    boards((STAIR_X1 + 0.03, STAIR_Y0 - 0.05), (STAIR_X1 + 0.03, STAIR_Y1 + 0.05), FLOOR_TOP, top)
    boards((STAIR_X0, STAIR_Y1 + 0.03), (STAIR_X1, STAIR_Y1 + 0.03), FLOOR_TOP, top)
    boards((STAIR_X0 - 0.03, STAIR_Y0 - 0.05), (STAIR_X0 - 0.03, STAIR_Y1 + 0.05), WALL_TOP, top)
    # parede sul com a porta (vão x∈[-2.2,-1.4], z∈[2.3, 4.25])
    y = STAIR_Y0 - 0.05
    dz0, dz1, dx0, dx1 = FLOOR_TOP, 4.25, -2.2, -1.4
    boards((STAIR_X0, y), (dx0, y), WALL_TOP, top)
    boards((dx1, y), (STAIR_X1, y), WALL_TOP, top)
    b.box(((dx0 + dx1) / 2, y, (dz1 + top) / 2), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (dx1 - dx0, 0.03, top - dz1))
    # aro da porta
    for xx in (dx0 - 0.03, dx1 + 0.03):
        b.box((xx, y, (dz0 + dz1) / 2), ((0, 0, 1), (1, 0, 0), (0, 1, 0)), (dz1 - dz0, 0.06, 0.09))
    # patamar
    b.box(((STAIR_X0 + STAIR_X1) / 2, -1.95, FLOOR_TOP - 0.015), ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
          (STAIR_X1 - STAIR_X0, 0.3, 0.03))
    # folha da porta entreaberta (abre para fora, dobradiça em dx0)
    ang = math.radians(-58)
    dv = Vector((math.cos(ang), math.sin(ang), 0))
    hinge = Vector((dx0 + 0.01, y - 0.03, (dz0 + dz1) / 2))
    b.box(hinge + dv * 0.39, (dv, Vector((0, 0, 1)).cross(dv), (0, 0, 1)), (0.78, 0.04, dz1 - dz0 - 0.02))
    return b.to_object("Piso_Cima_Porta", col, [wood])


def build_props(col, wood, mats):
    objs = []
    # --- banco tombado ------------------------------------------------------
    b = Builder()
    base = Vector((-0.55, 1.45, 0.0))
    rot = Euler((math.radians(88), 0, math.radians(35))).to_matrix()
    seat_c = Vector((0, 0, 0.45))
    b.cylinder(base + rot @ (seat_c - Vector((0, 0, 0.015))), base + rot @ (seat_c + Vector((0, 0, 0.015))),
               0.16, 0.16, 16)
    for k in range(3):
        a = k * 2 * math.pi / 3
        top = seat_c + Vector((math.cos(a) * 0.1, math.sin(a) * 0.1, -0.01))
        foot = Vector((math.cos(a) * 0.19, math.sin(a) * 0.19, 0))
        b.cylinder(base + rot @ foot, base + rot @ top, 0.017, 0.02, 8)
    ob = b.to_object("Prop_Banco_Tombado", col, [wood])
    ob.location.z = floor_height(base.x, base.y) + 0.16 - base.z
    objs.append(ob)

    # --- restos de prateleiras (parede sul) ----------------------------------
    b = Builder()
    yw = -ROOM_Y + 0.12
    for x in (0.55, 1.55):
        b.box((x, yw, 0.8), ((0, 0, 1), (1, 0, 0), (0, 1, 0)), (1.6, 0.05, 0.07))
    b.box((1.05, yw + 0.02, 1.2), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (1.15, 0.24, 0.025))
    dv = Vector((1, 0, -0.55)).normalized()
    b.box(Vector((0.6, yw + 0.02, 0.62)) + dv * 0.3, (dv, (0, 1, 0), dv.cross(Vector((0, 1, 0)))), (0.62, 0.22, 0.025))
    b.box((0.95, yw + 0.05, 0.03), (Vector((1, 0.3, 0)).normalized(), Vector((-0.3, 1, 0)).normalized(), (0, 0, 1)),
          (0.7, 0.2, 0.025))
    objs.append(b.to_object("Prop_Prateleiras", col, [wood]))

    # --- mochila abandonada ---------------------------------------------------
    b = Builder()
    b.box((0, 0, 0.21), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.3, 0.16, 0.42), mat=0)
    b.box((0, -0.1, 0.14), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.22, 0.06, 0.18), mat=0)
    b.box((0, 0.0, 0.43), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.26, 0.15, 0.04), mat=0)
    for sx in (-0.08, 0.08):
        b.box((sx, 0.1, 0.24), ((0, 0, 1), (1, 0, 0), (0, 1, 0)), (0.36, 0.05, 0.02), mat=0)
    ob = b.to_object("Prop_Mochila", col, [mats["mochila"]])
    ob.location = (-1.2, 1.05, floor_height(-1.2, 1.05) + 0.07)
    ob.rotation_euler = (math.radians(74), math.radians(8), math.radians(-120))
    for mname, kw in (("Bevel", dict(width=0.03, segments=3)), ("Subdivisao", {})):
        md = ob.modifiers.new(mname, "BEVEL" if mname == "Bevel" else "SUBSURF")
        for k, v in kw.items():
            setattr(md, k, v)
    ob.data.shade_smooth()
    objs.append(ob)

    # --- lanterna de mão (caída no chão, ligeiramente inclinada) -------------
    b = Builder()
    b.cylinder((0, 0, 0), (0.2, 0, 0), 0.019, 0.019, 20, mat=0)
    b.cylinder((0.2, 0, 0), (0.235, 0, 0), 0.019, 0.028, 20, mat=0)
    b.cylinder((0.235, 0, 0), (0.262, 0, 0), 0.028, 0.028, 20, mat=0)
    b.cylinder((0.262, 0, 0), (0.266, 0, 0), 0.025, 0.025, 20, mat=1)
    b.cylinder((0.08, 0, 0.017), (0.11, 0, 0.017), 0.006, 0.006, 8, mat=0)
    fl = b.to_object("Lanterna_Mao", col, [mats["lanterna"], mats["lente"]])
    fl.location = (0.2, -0.6, floor_height(0.2, -0.6) + 0.024)
    yaw = math.atan2(2.0 - (-0.6), 1.35 - 0.2)
    fl.rotation_euler = (0, math.radians(-7), yaw)
    objs.append(fl)

    # --- bonecos de paus ------------------------------------------------------
    def stick_figure(name, height):
        b = Builder()
        hgt = height

        def stick(a, c, r=0.006):
            a, c = Vector(a), Vector(c)
            mid = (a + c) / 2 + Vector((rng.gauss(0, 0.004), rng.gauss(0, 0.004), 0))
            b.cylinder(a, mid, r, r * 0.9, 6)
            b.cylinder(mid, c, r * 0.9, r * 0.75, 6)

        stick((0, 0, 0.05 * hgt), (0, 0, hgt))                                  # tronco
        stick((-0.32 * hgt, 0, 0.72 * hgt), (0.34 * hgt, 0, 0.7 * hgt))         # braços
        stick((0, 0, 0.42 * hgt), (-0.28 * hgt, 0, -0.02 * hgt), 0.005)          # pernas
        stick((0, 0, 0.42 * hgt), (0.27 * hgt, 0, 0.0), 0.005)
        stick((-0.22 * hgt, 0, 0.9 * hgt), (0.2 * hgt, 0, 0.55 * hgt), 0.004)   # pau cruzado
        # atilhos (voltas de fio)
        for z in (0.71 * hgt, 0.42 * hgt):
            b.cylinder((0, 0, z - 0.01), (0, 0, z + 0.01), 0.0085, 0.0085, 10, mat=1)
        return b.to_object(name, col, [mats["galhos"], mats["fio"]])

    s1 = stick_figure("Prop_Boneco_Paus_Chao", 0.32)
    s1.location = (1.1, 1.1, floor_height(1.1, 1.1) + 0.008)
    s1.rotation_euler = (math.radians(90), 0, math.radians(-25))
    objs.append(s1)
    s2 = stick_figure("Prop_Boneco_Paus_Pendurado", 0.45)
    s2.location = (1.55, 0.44, 1.28)
    s2.rotation_euler = (0, math.radians(4), math.radians(25))
    objs.append(s2)
    b = Builder()
    b.cylinder((1.55, 0.44, 1.28 + 0.45), (1.55, 0.45, JOIST_BOTTOM), 0.0012, 0.0012, 6)
    objs.append(b.to_object("Prop_Fio_Boneco", col, [mats["fio"]]))

    # --- entulho sob o buraco: tábuas partidas, pedras, folhas ------------------
    b = Builder()
    for _ in range(9):
        cx = rng.uniform(HOLE_X0 + 0.3, HOLE_X1 + 0.6)
        cy = rng.uniform(HOLE_Y0 + 0.2, HOLE_Y1 + 0.5)
        if math.dist((cx, cy), STICK_FLOOR) < 0.6 or math.dist((cx, cy), (0.62, 1.5)) < 0.5:
            continue
        ln = rng.uniform(0.3, 0.9)
        yaw = rng.uniform(0, math.pi)
        pitch = rng.uniform(-0.25, 0.25)
        d = Vector((math.cos(yaw) * math.cos(pitch), math.sin(yaw) * math.cos(pitch), math.sin(pitch)))
        s = d.cross(Vector((0, 0, 1))).normalized()
        zc = floor_height(cx, cy) + 0.015 + abs(math.sin(pitch)) * ln / 2
        b.box((cx, cy, zc), (d, s, s.cross(d)), (ln, rng.uniform(0.12, 0.18), 0.024))
    objs.append(b.to_object("Entulho_Tabuas", col, [wood]))

    b = Builder()
    for _ in range(170):
        if rng.random() < 0.5:
            x, y = rng.uniform(-2.4, 2.4), rng.uniform(-1.9, 1.9)
        else:  # junto às paredes
            side = rng.choice("NSEW")
            t = rng.uniform(-1, 1)
            x, y = {"N": (t * 2.4, 1.85), "S": (t * 2.4, -1.85), "E": (2.35, t * 1.9), "W": (-2.35, t * 1.9)}[side]
            x += rng.gauss(0, 0.08)
            y += rng.gauss(0, 0.08)
        r = rng.uniform(0.012, 0.06) ** 1.0
        if math.dist((x, y), FOOT_MARKS[0]) < 0.3 or math.dist((x, y), STICK_FLOOR) < 0.3:
            continue
        b.ico((x, y, floor_height(x, y) + r * 0.3), r, (1, rng.uniform(0.6, 1), rng.uniform(0.4, 0.7)), 2, 0.35,
              rot=(0, 0, rng.uniform(0, 6.3)))
    for _ in range(900):
        x, y = rng.uniform(-2.42, 2.42), rng.uniform(-1.92, 1.92)
        if math.dist((x, y), FOOT_MARKS[0]) < 0.25 or math.dist((x, y), FOOT_MARKS[1]) < 0.25:
            continue
        r = rng.uniform(0.003, 0.011)
        b.ico((x, y, floor_height(x, y) + r * 0.2), r, (1, rng.uniform(0.6, 1), rng.uniform(0.4, 0.7)), 1, 0.4,
              rot=(0, 0, rng.uniform(0, 6.3)))
    ob = b.to_object("Entulho_Pedras", col, [mats["pedrinhas"]], smooth=True)
    objs.append(ob)

    # folhas secas (mais junto à escada e sob o buraco)
    b = Builder()
    for _ in range(420):
        roll = rng.random()
        if roll < 0.35:
            x, y = rng.gauss(-1.6, 0.45), rng.gauss(0.6, 0.5)
        elif roll < 0.7:
            x, y = rng.gauss(0.6, 0.5), rng.gauss(1.0, 0.45)
        else:
            x, y = rng.uniform(-2.4, 2.4), rng.uniform(-1.9, 1.9)
        x, y = max(-2.42, min(2.42, x)), max(-1.92, min(1.92, y))
        if math.dist((x, y), (CORNER.x - 0.3, CORNER.y - 0.3)) < 0.45:
            continue  # o canto fica limpo
        L = rng.uniform(0.035, 0.07)
        yaw = rng.uniform(0, 2 * math.pi)
        curl = rng.uniform(-25, 30)
        cy_, sy_ = math.cos(yaw), math.sin(yaw)
        z0 = floor_height(x, y) + 0.004
        n = 9
        pts = []
        for side in (1, -1):
            rng_pts = range(n + 1) if side == 1 else range(n - 1, 0, -1)
            for k in rng_pts:
                t = k / n
                wdt = math.sin(math.pi * t) ** 0.8 * 0.33 * L * side
                lx, ly = (t - 0.5) * L, wdt
                lz = curl * (ly * ly) + 2.5 * (lx * lx) * rng.uniform(0.5, 1.5) + rng.uniform(0, 0.004)
                pts.append(Vector((x + lx * cy_ - ly * sy_, y + lx * sy_ + ly * cy_, z0 + lz)))
        vs = [b.bm.verts.new(p) for p in pts]
        f = b.bm.faces.new(vs)
        f[b.rand] = rng.random()
    objs.append(b.to_object("Folhas_Secas", col, [mats["folhas"]]))
    return objs, fl


def build_cobwebs(col, mat):
    """Teias simples nos cantos junto ao teto."""
    objs = []
    corners = [(ROOM_X, ROOM_Y), (-ROOM_X, ROOM_Y), (ROOM_X, -ROOM_Y)]
    for ci, (cx, cy) in enumerate(corners):
        sx, sy = -math.copysign(1, cx), -math.copysign(1, cy)
        anchors = []
        for k in range(7):
            t = k / 6
            if t < 0.5:
                anchors.append(Vector((cx, cy + sy * rng.uniform(0.2, 0.5), JOIST_BOTTOM - t * 0.9)))
            else:
                anchors.append(Vector((cx + sx * rng.uniform(0.2, 0.5), cy, JOIST_BOTTOM - (1 - t) * 0.9)))
        anchors = [Vector((cx, cy, JOIST_BOTTOM - 0.02))] + anchors
        center = Vector((cx + sx * 0.08, cy + sy * 0.08, JOIST_BOTTOM - 0.12))
        cu = bpy.data.curves.new(f"Teia_{ci}", "CURVE")
        cu.dimensions = "3D"
        cu.bevel_depth = 0.00035
        for a in anchors:
            sp = cu.splines.new("POLY")
            sp.points.add(1)
            sp.points[0].co = (*center, 1)
            sp.points[1].co = (*a, 1)
        for ring in range(1, 6):
            sp = cu.splines.new("POLY")
            sp.points.add(len(anchors) - 1)
            f = ring / 6
            for i, a in enumerate(anchors):
                p = center.lerp(a, f) + Vector((0, 0, -0.01 * math.sin(f * math.pi)))
                sp.points[i].co = (*p, 1)
        cu.materials.append(mat)
        objs.append(new_object(f"Teia_Canto_{ci}", cu, col))
    return objs


def build_dust(col, mat):
    b = Builder()
    for _ in range(1400):
        p = (rng.uniform(-2.4, 2.4), rng.uniform(-1.9, 1.9), rng.uniform(0.2, 2.05))
        r = rng.uniform(0.0005, 0.0013)
        res = bmesh.ops.create_icosphere(b.bm, subdivisions=1, radius=r, matrix=Matrix.Translation(p))
    return b.to_object("Poeira_Particulas", col, [mat], smooth=True)


# ---------------------------------------------------------------------------
# Luzes, variantes, câmaras, marcadores
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


def build_lights(col_base, var_cols, flashlight, atmo_mat_presence):
    # luar (sol) — entra pelos buracos e frinchas do soalho
    d = Vector((0.33, 0.28, -1.0)).normalized()
    moon = light("LUZ_Luar", "SUN", col_base, (0, 0, 6), 2.2, (0.55, 0.68, 1.0), angle=math.radians(0.8))
    moon.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    # luar pela porta entreaberta
    door = light("LUZ_Luar_Porta", "AREA", col_base, (-1.8, -3.1, 3.4), 150.0, (0.5, 0.64, 1.0),
                 shape="RECTANGLE", size=1.2, size_y=2.2)
    door.rotation_euler = look_at_rotation(door.location, (-1.8, -1.0, 2.6))

    def flash_spot(col, energy, name):
        sp = light(name, "SPOT", col, (0, 0, 0), energy, (0.92, 0.96, 1.0),
                   spot_size=math.radians(48), spot_blend=0.45, shadow_soft_size=0.012)
        sp.parent = flashlight
        sp.location = (0.27, 0, 0)
        sp.rotation_euler = (0, math.radians(-90), 0)
        # pequeno brilho de enchimento à volta da lente
        return sp

    def corner_light(col, energy, color, name):
        cl = light(name, "AREA", col, (ROOM_X - 0.75, ROOM_Y - 0.2, JOIST_BOTTOM - 0.05), energy, color,
                   shape="DISK", size=0.35)
        cl.rotation_euler = look_at_rotation(cl.location, (ROOM_X, ROOM_Y - 0.45, 0.7))
        cl.visible_camera = False
        return cl

    v1, v2, v3 = var_cols
    # 1 — normal
    flash_spot(v1, 30.0, "LUZ_Lanterna_Normal")
    corner_light(v1, 9.0, (1.0, 0.9, 0.78), "LUZ_Canto_Normal")
    # 2 — luz a falhar (cintilação animada)
    sp = flash_spot(v2, 12.0, "LUZ_Lanterna_Falha")
    sp.data.keyframe_insert("energy", frame=1)
    fc = sp.data.animation_data.action.fcurves.find("energy") if hasattr(sp.data.animation_data.action, "fcurves") else None
    if fc is None:
        for layer in getattr(sp.data.animation_data.action, "layers", []):
            for strip in layer.strips:
                for cb in strip.channelbags:
                    fc = cb.fcurves.find("energy") or fc
    if fc is not None:
        mod = fc.modifiers.new("NOISE")
        mod.scale = 2.5
        mod.strength = 16.0
        mod.phase = 3.0
        mod.depth = 1
    corner_light(v2, 3.0, (1.0, 0.9, 0.78), "LUZ_Canto_Falha")
    # 3 — presença
    flash_spot(v3, 20.0, "LUZ_Lanterna_Presenca")
    corner_light(v3, 28.0, (0.62, 0.8, 1.0), "LUZ_Canto_Presenca")
    me = bpy.data.meshes.new("Nevoa_Canto")
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=3, radius=1.0)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(atmo_mat_presence)
    fog = new_object("ATMOS_Nevoa_Canto_Presenca", me, v3)
    fog.location = (ROOM_X - 0.35, ROOM_Y - 0.35, 0.9)
    fog.scale = (0.75, 0.75, 1.0)


def build_cameras(col, focus_stick, corner_focus):
    scn = bpy.context.scene
    cams = {}

    def cam(name, loc, target, lens, fstop=None, focus=None, shift_x=0.0):
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        cd.sensor_width = 36
        cd.clip_start = 0.02
        cd.shift_x = shift_x
        if fstop:
            cd.dof.use_dof = True
            cd.dof.aperture_fstop = fstop
            if isinstance(focus, bpy.types.Object):
                cd.dof.focus_object = focus
            elif focus is not None:
                cd.dof.focus_distance = focus
        ob = new_object(name, cd, col)
        ob.location = loc
        ob.rotation_euler = look_at_rotation(loc, target)
        cams[name] = ob
        return ob

    cam("CAM_1_Fixa_Estilo_Jogo", (2.3, 1.82, 2.02), (0.0, -0.6, 0.25), 18)
    cam("CAM_2_Costas_Para_Canto", (0.55, 0.05, 1.6), (2.45, 1.95, 0.55), 28, 2.8, corner_focus)
    cam("CAM_3_Topo_Escada", (-2.0, -1.98, 3.35), (-1.85, 0.9, 0.3), 35)
    cam("CAM_4_Detalhe_Boneco", (0.66, 1.46, 0.3), (1.1, 1.08, 0.02), 50, 2.8, focus_stick)
    cam("CAM_5_Fundo_Analise", (-1.0, -1.72, 1.3), (1.2, 1.7, 0.95), 24, shift_x=-0.08)
    scn.camera = cams["CAM_2_Costas_Para_Canto"]
    return cams


def build_markers(col):
    """Marcadores para o personagem (escala Mixamo, frente = -Y local)."""
    markers = []

    def marker(name, loc, facing):
        theta = math.atan2(facing[0], -facing[1])
        e = bpy.data.objects.new(name, None)
        e.empty_display_type = "SINGLE_ARROW"
        e.empty_display_size = 0.4
        col.objects.link(e)
        e.location = loc
        e.rotation_euler = (0, 0, theta)
        # silhueta de referência (1.75 m), não aparece no render
        me = bpy.data.meshes.new(name + "_Silhueta")
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.2, radius2=0.2, depth=1.45,
                              matrix=Matrix.Translation((0, 0, 0.725)))
        bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=0.12,
                                  matrix=Matrix.Translation((0, 0, 1.63)))
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0, -0.2, 1.63)) @
                              Matrix.Diagonal((0.06, 0.08, 0.04, 1)))
        bm.to_mesh(me)
        bm.free()
        sil = new_object(name + "_Silhueta", me, col)
        sil.parent = e
        sil.display_type = "WIRE"
        sil.hide_render = True
        sil.hide_select = True
        markers.append(e)
        return e

    m1 = Vector((ROOM_X - 0.45, ROOM_Y - 0.45, 0))
    marker("PERSONAGEM_1_Virado_Canto", (m1.x, m1.y, floor_height(m1.x, m1.y)), (1, 1))
    marker("PERSONAGEM_2_Fundo_Escada", (-1.95, 0.95, floor_height(-1.95, 0.95)), (0.45, 0.9))
    marker("PERSONAGEM_3_Com_Lanterna", (0.1, 0.1, floor_height(0.1, 0.1)), (0.35, 1.0))
    return markers


# ---------------------------------------------------------------------------
# Render, look 16 mm, mundo
# ---------------------------------------------------------------------------
def setup_world():
    w = bpy.data.worlds.new("Mundo_Noite")
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.006, 0.009, 0.02, 1)
    bg.inputs["Strength"].default_value = 1.0
    bpy.context.scene.world = w


def try_set(node, name, value):
    """Define uma entrada do nó (escolhendo o socket do tipo certo) ou a propriedade antiga."""
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


def setup_render(samples_final=512):
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.cycles.samples = samples_final
    scn.cycles.preview_samples = 32
    scn.cycles.use_adaptive_sampling = True
    scn.cycles.adaptive_threshold = 0.015
    scn.cycles.use_denoising = True
    scn.cycles.max_bounces = 8
    scn.cycles.diffuse_bounces = 3
    scn.cycles.glossy_bounces = 3
    scn.cycles.volume_bounces = 1
    scn.cycles.transparent_max_bounces = 8
    scn.cycles.volume_step_rate = 1.0
    scn.cycles.sample_clamp_indirect = 8.0
    scn.render.resolution_x = 1920
    scn.render.resolution_y = 1080
    scn.render.fps = 24
    scn.frame_start, scn.frame_end = 1, 240
    scn.view_settings.view_transform = "AgX"
    for look in ("AgX - Base Contrast", "None"):
        try:
            scn.view_settings.look = look
            break
        except TypeError:
            pass
    scn.view_settings.exposure = 0.6
    scn.render.film_transparent = False
    try:
        scn.eevee.use_volumetric_shadows = True
        scn.eevee.volumetric_tile_size = "4"
        scn.eevee.use_shadows = True
        scn.eevee.use_raytracing = True
    except AttributeError:
        pass


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
    """Look de película 16 mm: dessaturação, grading, vinheta, grão, halo."""
    film_look(glare=(1.2, 0.25), lens=(0.012, 0.006), sat=0.72, lift=(1.0, 1.035, 1.045), gamma=(1.0, 1.0, 0.975), gain=(1.04, 1.0, 0.93), vignette_min=0.45, grain=0.14)


README_TEXT = """CAVE DE RUSTIN PARR — como usar
================================

COLEÇÕES
  01_AMBIENTE      paredes, chão, teto, escada, piso de cima
  02_PROPS         banco, prateleiras, mochila, lanterna, bonecos, entulho, folhas
  03_LUZ_BASE      luar (sol) e luar pela porta
  04_VARIANTES     ative SÓ UMA:
                     VAR_1_Normal | VAR_2_Luz_a_Falhar | VAR_3_Presenca
  05_ATMOSFERA     nevoeiro volumétrico, poeira, teias
  06_CAMARAS       5 planos (Numpad 0 para ver pela câmara ativa)
  07_PERSONAGEM    marcadores (seta = para onde o personagem olha)

PERSONAGEM (FBX do Mixamo)
  1. File > Import > FBX.
  2. Selecione o armature, depois (Shift) o marcador PERSONAGEM_x.
  3. Object > Transform > "Align Objects" ou copie Location/Rotation
     do marcador (N > Item). A frente do marcador é -Y, igual ao Mixamo.
  4. As silhuetas cinzentas (wireframe) não aparecem no render;
     pode escondê-las no olho da coleção 07_PERSONAGEM.

LANTERNA
  As luzes da lanterna são filhas do objeto Lanterna_Mao.
  Para a pôr na mão do personagem: parent da Lanterna_Mao ao osso da mão
  (Child Of > armature > mixamorig:RightHand) e ajuste a posição.

RENDER
  Cycles, 512 amostras, denoise. O look 16 mm está no Compositor
  (grão, vinheta, grading, halo). Para desligar: Render > Post Processing > Compositing.
"""


def main():
    args = parse_args()
    reset_scene()
    scn = bpy.context.scene
    scn.name = "Cave_Rustin_Parr"
    scn.unit_settings.system = "METRIC"

    c_env = collection("01_AMBIENTE")
    c_props = collection("02_PROPS")
    c_lbase = collection("03_LUZ_BASE")
    c_var = collection("04_VARIANTES")
    v_cols = [collection(n, c_var) for n in ("VAR_1_Normal", "VAR_2_Luz_a_Falhar", "VAR_3_Presenca")]
    c_atmo = collection("05_ATMOSFERA")
    c_cam = collection("06_CAMARAS")
    c_char = collection("07_PERSONAGEM")

    wood = mat_wood("M_Madeira_Podre")
    wood_dark = mat_wood("M_Madeira_Vigas", dark=1.3)
    mats = {
        "mochila": mat_simple("M_Mochila_Nylon", (0.045, 0.07, 0.068), 0.7, noise_scale=30, bump=0.2),
        "lanterna": mat_simple("M_Lanterna_Aluminio", (0.03, 0.03, 0.032), 0.35, metal=1.0),
        "lente": mat_simple("M_Lanterna_Lente", (0.9, 0.9, 0.9), 0.05),
        "fio": mat_simple("M_Fio_Atilho", (0.12, 0.1, 0.07), 0.9),
        "pedrinhas": mat_simple("M_Pedrinhas", (0.13, 0.12, 0.1), 0.85, noise_scale=40, bump=0.3),
        "folhas": mat_leaf(),
        "galhos": mat_simple("M_Galhos_Casca", (0.075, 0.06, 0.045), 0.85, noise_scale=90, bump=0.8),
    }
    lens_mat = mats["lente"]
    lens_mat.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (0.95, 0.97, 1, 1)
    lens_mat.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 6.0

    print("> paredes e marcas de mãos")
    build_walls(c_env)
    print("> chão")
    build_floor(c_env)
    print("> teto, escada, piso de cima")
    build_ceiling(c_env, wood_dark)
    build_stairs(c_env, wood)
    build_upper(c_env, wood)
    print("> props")
    objs, flashlight = build_props(c_props, wood, mats)
    stick = bpy.data.objects.new("FOCO_Boneco", None)
    c_props.objects.link(stick)
    stick.location = (STICK_FLOOR[0] + 0.03, STICK_FLOOR[1] - 0.1, floor_height(*STICK_FLOOR) + 0.01)

    print("> atmosfera")
    vol_mat = mat_volume("M_Nevoeiro_Cave", 0.045, 0.3, noise_amt=0.0)
    me = bpy.data.meshes.new("Nevoeiro")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0, -0.1, 1.6)) @
                          Matrix.Diagonal((ROOM_X * 2 + 0.1, ROOM_Y * 2 + 0.3, 3.2, 1)))
    bm.to_mesh(me)
    bm.free()
    me.materials.append(vol_mat)
    new_object("ATMOS_Nevoeiro_Volume", me, c_atmo)
    dust_mat = mat_simple("M_Poeira", (0.7, 0.68, 0.64), 1.0)
    build_dust(c_atmo, dust_mat)
    web_mat = mat_simple("M_Teia", (0.55, 0.55, 0.52), 0.5)
    build_cobwebs(c_atmo, web_mat)

    print("> luzes, câmaras, marcadores")
    presence_mat = mat_volume("M_Nevoa_Presenca", 0.16, 0.2, (0.75, 0.85, 1.0), noise_amt=0.8)
    build_lights(c_lbase, v_cols, flashlight, presence_mat)
    corner_focus = bpy.data.objects.new("FOCO_Canto", None)
    c_cam.objects.link(corner_focus)
    corner_focus.location = (ROOM_X - 0.05, ROOM_Y - 0.05, 1.1)
    build_cameras(c_cam, stick, corner_focus)
    build_markers(c_char)

    setup_world()
    setup_render()
    setup_compositor()

    txt = bpy.data.texts.new("LEIA-ME")
    txt.write(README_TEXT)

    # só a variante normal ativa
    vl = bpy.context.view_layer
    var_layer = vl.layer_collection.children["04_VARIANTES"]
    for i, c in enumerate(v_cols):
        var_layer.children[c.name].exclude = i != 0

    out = os.path.abspath(args.out)
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    print(f"> guardado: {out}")

    if args.render:
        render_previews(args, v_cols)


PREVIEWS = [
    ("cam1_fixa_jogo", "CAM_1_Fixa_Estilo_Jogo", 0),
    ("cam2_costas_canto", "CAM_2_Costas_Para_Canto", 0),
    ("cam3_topo_escada", "CAM_3_Topo_Escada", 0),
    ("cam4_detalhe_boneco", "CAM_4_Detalhe_Boneco", 0),
    ("cam5_fundo_analise", "CAM_5_Fundo_Analise", 0),
    ("cam2_var2_luz_a_falhar", "CAM_2_Costas_Para_Canto", 1),
    ("cam2_var3_presenca", "CAM_2_Costas_Para_Canto", 2),
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
    vl = bpy.context.view_layer
    var_layer = vl.layer_collection.children["04_VARIANTES"]
    only = set(filter(None, args.only.split(",")))
    for fname, cam, var in PREVIEWS:
        if only and fname not in only:
            continue
        for i, c in enumerate(v_cols):
            var_layer.children[c.name].exclude = i != var
        scn.camera = bpy.data.objects[cam]
        scn.frame_set(12)
        scn.render.filepath = os.path.join(os.path.abspath(args.render), fname + ".jpg")
        print(f"> render {fname}")
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
