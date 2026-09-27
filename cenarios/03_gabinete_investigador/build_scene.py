"""
Cenário 03 — Gabinete do investigador de software de horror (a base do canal)

Gabinete noir dos anos 90, de noite: secretária de madeira, candeeiro de
banqueiro, monitores CRT, TV CRT, um portátil moderno no meio do retro,
quadro de provas com fio vermelho, prateleira de jogos em sacos de prova
etiquetados, persianas a cortar a luz néon da rua, porta de vidro fosco.

Pensado para ser reutilizado em todos os vídeos:
  - ECRA_Jogo (imagem ou vídeo) aparece no CRT da secretária e na TV;
  - FOTO_Prova_1..6 no quadro de provas;
  - CAPA_Caso_Atual na caixa do jogo em cima da secretária.

Uso (dentro do Blender):
    blender -b -P build_scene.py -- --out gabinete_investigador.blend
Uso (módulo bpy via pip):
    python build_scene.py --out gabinete_investigador.blend --render previews --samples 64
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

SEED = 1997
rng = random.Random(SEED)

# ---------------------------------------------------------------------------
# Dimensões (metros). A câmara frontal olha para +Y; a parede do fundo é y = RY.
# ---------------------------------------------------------------------------
RX, RY, RH = 2.25, 2.0, 2.8
DESK_C = Vector((0.0, 0.55, 0.0))
DESK_W, DESK_D, DESK_H = 1.7, 0.85, 0.76
CHAIR_C = Vector((0.0, 1.22, 0.0))
WIN_Y0, WIN_Y1, WIN_Z0, WIN_Z1 = -0.15, 1.25, 0.95, 2.3     # janela na parede esquerda (x = -RX)
DOOR_Y0, DOOR_Y1, DOOR_Z1 = -1.65, -0.75, 2.15              # porta na parede direita (x = +RX)
CRT_C = Vector((0.52, 0.5, DESK_H))                         # monitor CRT na secretária
TV_C = Vector((-1.35, 1.55, 0.0))                           # TV CRT no móvel ao fundo
BOARD_C = Vector((-0.25, RY - 0.03, 1.72))                  # quadro de provas
BOARD_W, BOARD_H = 1.7, 0.95
SHELF_X0, SHELF_X1 = 1.0, 2.12
DOOR_TEXT = ("INVESTIGAÇÃO", "SOFTWARE DE HORROR")          # letras no vidro da porta (editáveis)

def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="gabinete_investigador.blend")
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
# Materiais próprios do gabinete
# ---------------------------------------------------------------------------
def mat_wall():
    """Estuque pintado de verde-escuro, a descascar, com manchas de humidade."""
    m = Mat("M_Parede_Tinta_Velha")
    obj = m.texcoord().outputs["Object"]
    peel_n = m.noise(obj, 3.5, 10.0, 0.7)
    peel = m.maprange(peel_n.outputs["Fac"], 0.62, 0.66)
    paint_var = m.noise(obj, 1.5, 6.0, 0.6)
    paint = m.ramp(paint_var.outputs["Fac"], [(0.3, (0.028, 0.05, 0.042)), (0.7, (0.05, 0.08, 0.066))]).outputs["Color"]
    plaster = m.ramp(m.noise(obj, 20.0, 6.0, 0.6).outputs["Fac"], [(0.3, (0.2, 0.18, 0.15)), (0.7, (0.3, 0.28, 0.23))])
    col = m.mix(peel, paint, plaster.outputs["Color"])
    smp = m.node("ShaderNodeMapping")
    smp.inputs["Scale"].default_value = (7.0, 7.0, 0.5)
    m.link(obj, smp.inputs["Vector"])
    streak = m.maprange(m.noise(smp.outputs["Vector"], 2.0, 3.0, 0.5).outputs["Fac"], 0.55, 0.72)
    z = sep_z(m)
    top = m.maprange(z, 1.8, RH, 0.0, 1.0)
    stain = m.math("MULTIPLY", streak, m.math("ADD", top, 0.35))
    col = m.mix(m.math("MULTIPLY", stain, 0.6), col, (0.02, 0.022, 0.015))
    m.set("Base Color", col)
    m.set("Roughness", m.mixf(peel, 0.55, 0.9))
    h = m.math("ADD", m.math("MULTIPLY", peel, 0.5), m.math("MULTIPLY", m.noise(obj, 60.0, 4.0, 0.6).outputs["Fac"], 0.3))
    m.set("Normal", m.bump(h, 0.4, 0.005))
    return m.mat


def mat_ceiling():
    m = Mat("M_Teto_Estuque")
    obj = m.texcoord().outputs["Object"]
    n = m.noise(obj, 1.2, 6.0, 0.6)
    col = m.ramp(n.outputs["Fac"], [(0.35, (0.12, 0.11, 0.085)), (0.6, (0.3, 0.29, 0.26))])
    m.set("Base Color", col.outputs["Color"])
    m.set("Roughness", 0.95)
    return m.mat


def mat_floor_planks():
    m = Mat("M_Soalho_Envernizado")
    obj = m.texcoord().outputs["Object"]
    br = m.node("ShaderNodeTexBrick", offset=0.37, offset_frequency=1)
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Mortar Size"].default_value = 0.003
    br.inputs["Brick Width"].default_value = 1.3
    br.inputs["Row Height"].default_value = 0.13
    br.inputs["Color1"].default_value = (1, 1, 1, 1)
    br.inputs["Color2"].default_value = (0, 0, 0, 1)
    m.link(obj, br.inputs["Vector"])
    sp = m.node("ShaderNodeSeparateColor")
    m.link(br.outputs["Color"], sp.inputs[0])
    mp = m.node("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.8, 18.0, 1.0)
    m.link(obj, mp.inputs["Vector"])
    grain = m.noise(mp.outputs["Vector"], 4.0, 10.0, 0.7)
    g = m.math("ADD", m.math("MULTIPLY", grain.outputs["Fac"], 0.6), m.math("MULTIPLY", sp.outputs[0], 0.4))
    col = m.ramp(g, [(0.25, (0.03, 0.016, 0.009)), (0.55, (0.075, 0.042, 0.022)), (0.85, (0.13, 0.075, 0.04))])
    col = m.mix(br.outputs["Fac"], col.outputs["Color"], (0.01, 0.006, 0.004))
    wear = m.maprange(m.noise(obj, 1.0, 4.0, 0.5).outputs["Fac"], 0.45, 0.7)
    m.set("Base Color", col)
    m.set("Roughness", m.mixf(wear, 0.28, 0.65))
    m.set("Normal", m.bump(m.math("SUBTRACT", grain.outputs["Fac"], br.outputs["Fac"]), 0.25, 0.005))
    return m.mat


def mat_rug():
    """Tapete persa gasto (coordenadas Generated do objeto)."""
    m = Mat("M_Tapete_Persa_Gasto")
    gen = m.texcoord().outputs["Generated"]
    sep = m.node("ShaderNodeSeparateXYZ")
    m.link(gen, sep.inputs[0])
    dx = m.math("ABSOLUTE", m.math("SUBTRACT", sep.outputs["X"], 0.5))
    dy = m.math("ABSOLUTE", m.math("SUBTRACT", sep.outputs["Y"], 0.5))
    border = m.math("MAXIMUM", dx, dy)
    rings = m.math("SINE", m.math("MULTIPLY", border, 70.0))
    diamond = m.math("SINE", m.math("MULTIPLY", m.math("ADD", dx, dy), 45.0))
    pat = m.math("ADD", m.math("MULTIPLY", rings, 0.5), m.math("MULTIPLY", diamond, 0.5))
    band = m.maprange(border, 0.38, 0.4)
    field = m.ramp(pat, [(0.2, (0.12, 0.02, 0.015)), (0.5, (0.05, 0.012, 0.012)), (0.8, (0.2, 0.13, 0.07))])
    edge = m.ramp(pat, [(0.3, (0.02, 0.025, 0.05)), (0.7, (0.2, 0.15, 0.08))])
    col = m.mix(band, field.outputs["Color"], edge.outputs["Color"])
    wear = m.maprange(m.noise(m.texcoord().outputs["Object"], 2.0, 6.0, 0.6).outputs["Fac"], 0.5, 0.75)
    col = m.mix(m.math("MULTIPLY", wear, 0.7), col, (0.09, 0.07, 0.055))
    fib = m.noise(m.texcoord().outputs["Object"], 300.0, 2.0, 0.5)
    m.set("Base Color", col)
    m.set("Roughness", 0.95)
    m.set("Normal", m.bump(fib.outputs["Fac"], 0.3, 0.002))
    return m.mat


def mat_plastic(name, color, rough=0.45, noise_amt=0.15):
    m = Mat(name)
    n = m.noise(m.texcoord().outputs["Object"], 30.0, 4.0, 0.6)
    c = m.ramp(n.outputs["Fac"], [(0.3, tuple(v * (1 - noise_amt) for v in color)), (0.7, color)])
    m.set("Base Color", c.outputs["Color"])
    m.set("Roughness", rough)
    m.set("Normal", m.bump(m.noise(m.texcoord().outputs["Object"], 400.0, 2.0, 0.5).outputs["Fac"], 0.05, 0.002))
    return m.mat


def mat_glass(name, rough=0.03, drops=False):
    m = Mat(name)
    m.set("Base Color", (0.9, 0.93, 0.95))
    m.set("Transmission Weight", 1.0)
    m.set("Roughness", rough)
    m.set("IOR", 1.5)
    if drops:
        obj = m.texcoord().outputs["Object"]
        v = m.node("ShaderNodeTexVoronoi")
        v.inputs["Scale"].default_value = 60.0
        m.link(obj, v.inputs["Vector"])
        d = m.maprange(v.outputs["Distance"], 0.0, 0.25, 1.0, 0.0)
        mask = m.maprange(m.noise(obj, 8.0, 4.0, 0.6).outputs["Fac"], 0.45, 0.6)
        m.set("Normal", m.bump(m.math("MULTIPLY", d, mask), 0.6, 0.01))
    return m.mat


def mat_bag():
    """Saco de prova em plástico transparente, amarrotado."""
    m = Mat("M_Saco_Prova_Plastico")
    obj = m.texcoord().outputs["Object"]
    m.set("Base Color", (0.95, 0.95, 0.95))
    m.set("Transmission Weight", 1.0)
    m.set("IOR", 1.35)
    m.set("Roughness", m.maprange(m.noise(obj, 15.0, 6.0, 0.6).outputs["Fac"], 0.3, 0.7, 0.08, 0.35))
    m.set("Normal", m.bump(m.noise(obj, 25.0, 8.0, 0.7).outputs["Fac"], 0.35, 0.01))
    return m.mat


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


def make_image(name, px, colorspace="sRGB"):
    h, w = px.shape[:2]
    im = bpy.data.images.new(name, w, h, alpha=False)
    rgba = np.ones((h, w, 4), np.float32)
    rgba[..., :3] = px
    im.pixels.foreach_set(rgba.ravel())
    im.file_format = "PNG"
    im.pack()
    im.colorspace_settings.name = colorspace
    return im


def placeholder_signal():
    """Barras de cor com ruído: imagem provisória do ecrã (troque pelo jogo)."""
    W, H = 640, 480
    bars = [(0.75, 0.75, 0.75), (0.75, 0.75, 0), (0, 0.75, 0.75), (0, 0.75, 0), (0.75, 0, 0.75), (0.75, 0, 0), (0, 0, 0.75)]
    px = np.zeros((H, W, 3), np.float32)
    for i, c in enumerate(bars):
        px[H // 3:, i * W // 7:(i + 1) * W // 7] = c
    px[:H // 3] = 0.08
    r = np.random.default_rng(3)
    px += r.normal(0, 0.06, (H, W, 1)).astype(np.float32)
    return make_image("ECRA_Jogo", np.clip(px, 0, 1) ** 2.2)


def placeholder_photo(i):
    W, H = 400, 300
    r = np.random.default_rng(100 + i)
    base = fbm(H, W, 200 + i, cells=(60, 20, 6))
    yy, xx = np.mgrid[0:H, 0:W]
    shapes = np.zeros((H, W), np.float32)
    for _ in range(3):
        cx, cy = r.uniform(60, W - 60), r.uniform(50, H - 50)
        rx, ry = r.uniform(20, 90), r.uniform(20, 110)
        shapes += np.clip(1 - ((xx - cx) / rx) ** 2 - ((yy - cy) / ry) ** 2, 0, 1) * r.uniform(-0.5, 0.5)
    v = np.clip(0.25 + base * 0.4 + shapes, 0, 1)
    v = v + r.normal(0, 0.05, (H, W))
    px = np.stack([v * 1.0, v * 0.95, v * 0.85], -1)
    px[:8], px[-8:], px[:, :8], px[:, -8:] = 0.85, 0.85, 0.85, 0.85   # moldura branca da fotografia
    return make_image(f"FOTO_Prova_{i}", np.clip(px, 0, 1) ** 2.2)


def placeholder_cover():
    W, H = 300, 400
    base = fbm(H, W, 555, cells=(80, 20, 5))
    px = np.stack([0.25 + base * 0.3, 0.02 + base * 0.08, 0.02 + base * 0.05], -1)
    px[int(H * 0.72):int(H * 0.85)] = (0.85, 0.8, 0.7)
    return make_image("CAPA_Caso_Atual", np.clip(px, 0, 1) ** 2.2)


def mat_image(name, img, rough=0.5, emission=0.0, crt=False):
    """Material com imagem; em modo CRT: curvatura, scanlines, vinheta e emissão."""
    m = Mat(name)
    tc = m.texcoord()
    uv = tc.outputs["UV"]
    it = m.node("ShaderNodeTexImage", image=img)
    if crt:
        # UV curvada (barril)
        sub = m.node("ShaderNodeVectorMath", operation="SUBTRACT")
        m.link(uv, sub.inputs[0])
        sub.inputs[1].default_value = (0.5, 0.5, 0.0)
        ln = m.node("ShaderNodeVectorMath", operation="DOT_PRODUCT")
        m.link(sub.outputs[0], ln.inputs[0])
        m.link(sub.outputs[0], ln.inputs[1])
        k = m.math("ADD", 1.0, m.math("MULTIPLY", ln.outputs["Value"], 0.25))
        sc = m.node("ShaderNodeVectorMath", operation="SCALE")
        m.link(sub.outputs[0], sc.inputs[0])
        m.link(k, sc.inputs["Scale"])
        add = m.node("ShaderNodeVectorMath", operation="ADD")
        m.link(sc.outputs[0], add.inputs[0])
        add.inputs[1].default_value = (0.5, 0.5, 0.0)
        m.link(add.outputs[0], it.inputs["Vector"])
        sepv = m.node("ShaderNodeSeparateXYZ")
        m.link(add.outputs[0], sepv.inputs[0])
        inside = m.math("MULTIPLY",
                        m.math("MULTIPLY", m.math("GREATER_THAN", sepv.outputs["X"], 0.0), m.math("LESS_THAN", sepv.outputs["X"], 1.0)),
                        m.math("MULTIPLY", m.math("GREATER_THAN", sepv.outputs["Y"], 0.0), m.math("LESS_THAN", sepv.outputs["Y"], 1.0)))
        scan = m.math("ADD", 0.72, m.math("MULTIPLY", m.math("ABSOLUTE", m.math("SINE", m.math("MULTIPLY", sepv.outputs["Y"], 750.0))), 0.28))
        vig = m.math("SUBTRACT", 1.0, m.math("MULTIPLY", ln.outputs["Value"], 1.6))
        fac = m.math("MULTIPLY", m.math("MULTIPLY", inside, scan), vig)
        cc = m.node("ShaderNodeCombineColor")
        for i in range(3):
            m.link(fac, cc.inputs[i])
        col = m.mix(1.0, it.outputs["Color"], cc.outputs[0], "MULTIPLY")
        m.set("Base Color", (0.01, 0.012, 0.012))
        m.set("Emission Color", col)
        m.set("Emission Strength", emission)
        m.set("Roughness", 0.12)
        m.set("Coat Weight", 1.0)
    else:
        m.link(uv, it.inputs["Vector"])
        m.set("Base Color", it.outputs["Color"])
        m.set("Roughness", rough)
        if emission:
            m.set("Emission Color", it.outputs["Color"])
            m.set("Emission Strength", emission)
    return m.mat


def mat_laptop_screen():
    """Ambiente de trabalho moderno escuro com uma janela aberta."""
    m = Mat("M_Portatil_Ecra")
    gen = m.texcoord().outputs["UV"]
    sep = m.node("ShaderNodeSeparateXYZ")
    m.link(gen, sep.inputs[0])
    win = m.math("MULTIPLY",
                 m.math("MULTIPLY", m.math("GREATER_THAN", sep.outputs["X"], 0.12), m.math("LESS_THAN", sep.outputs["X"], 0.8)),
                 m.math("MULTIPLY", m.math("GREATER_THAN", sep.outputs["Y"], 0.15), m.math("LESS_THAN", sep.outputs["Y"], 0.85)))
    lines = m.math("GREATER_THAN", m.math("SINE", m.math("MULTIPLY", sep.outputs["Y"], 160.0)), 0.6)
    txt = m.math("MULTIPLY", m.math("MULTIPLY", win, lines), m.math("GREATER_THAN", m.noise(gen, 25.0, 1.0, 0.5).outputs["Fac"], 0.45))
    col = m.mix(win, (0.02, 0.04, 0.09), (0.08, 0.1, 0.13))
    col = m.mix(txt, col, (0.55, 0.75, 0.9))
    m.set("Base Color", (0.0, 0.0, 0.0))
    m.set("Emission Color", col)
    m.set("Emission Strength", 3.0)
    m.set("Roughness", 0.1)
    return m.mat


def mat_city():
    """Vista da rua à noite: janelas acesas, néons desfocados (só visível à câmara)."""
    m = Mat("M_Rua_Noite_Fundo")
    obj = m.texcoord().outputs["Object"]
    mp = m.node("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (0, math.pi / 2, 0)
    m.link(obj, mp.inputs["Vector"])
    br = m.node("ShaderNodeTexBrick")
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Brick Width"].default_value = 0.35
    br.inputs["Row Height"].default_value = 0.45
    br.inputs["Mortar Size"].default_value = 0.12
    br.inputs["Color1"].default_value = (1, 1, 1, 1)
    br.inputs["Color2"].default_value = (0, 0, 0, 1)
    m.link(mp.outputs["Vector"], br.inputs["Vector"])
    sp = m.node("ShaderNodeSeparateColor")
    m.link(br.outputs["Color"], sp.inputs[0])
    lit = m.math("MULTIPLY", m.math("GREATER_THAN", sp.outputs[0], 0.72), m.math("SUBTRACT", 1.0, br.outputs["Fac"]))
    warm = m.mix(lit, (0.0, 0.0, 0.0), (1.0, 0.6, 0.25))
    neon_n = m.noise(mp.outputs["Vector"], 0.6, 2.0, 0.5)
    neon = m.ramp(neon_n.outputs["Fac"], [(0.35, (0.0, 0.0, 0.0)), (0.5, (0.0, 0.5, 0.6)), (0.62, (0.0, 0.0, 0.0)),
                                          (0.7, (0.8, 0.02, 0.08)), (0.8, (0.0, 0.0, 0.0))])
    col = m.mix(1.0, warm, neon.outputs["Color"], "ADD")
    m.set("Base Color", (0, 0, 0))
    m.set("Emission Color", col)
    m.set("Emission Strength", 1.5)
    return m.mat


# ---------------------------------------------------------------------------
# Construção
# ---------------------------------------------------------------------------
def wall_pieces(b, axis, fixed, span, holes, th=0.15, mat=0):
    """Parede plana com aberturas retangulares. axis='x' → parede em x=fixed ao longo de y."""
    (s0, s1), (z0, z1) = span, (0.0, RH)
    cuts = sorted({s0, s1} | {h[0] for h in holes} | {h[1] for h in holes})
    for a, c in zip(cuts[:-1], cuts[1:]):
        zs = [(z0, z1)]
        for h in holes:
            if h[0] <= a and c <= h[1]:
                zs = [(z0, h[2]), (h[3], z1)]
        for za, zc in zs:
            if zc - za < 1e-3:
                continue
            if axis == "x":
                cen = (fixed + math.copysign(th / 2, fixed), (a + c) / 2, (za + zc) / 2)
                dims = (th, c - a, zc - za)
            else:
                cen = ((a + c) / 2, fixed + math.copysign(th / 2, fixed), (za + zc) / 2)
                dims = (c - a, th, zc - za)
            b.box(cen, ((1, 0, 0), (0, 1, 0), (0, 0, 1)), dims, mat=mat)


def build_room(col, mats):
    b = Builder()
    wall_pieces(b, "y", RY, (-RX - 0.15, RX + 0.15), [])
    wall_pieces(b, "y", -RY, (-RX - 0.15, RX + 0.15), [])
    wall_pieces(b, "x", -RX, (-RY, RY), [(WIN_Y0, WIN_Y1, WIN_Z0, WIN_Z1)])
    wall_pieces(b, "x", RX, (-RY, RY), [(DOOR_Y0, DOOR_Y1, 0.0, DOOR_Z1)])
    b.box((0, 0, RH + 0.05), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (2 * RX + 0.3, 2 * RY + 0.3, 0.1), mat=1)
    b.box((0, 0, -0.05), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (2 * RX + 0.3, 2 * RY + 0.3, 0.1), mat=2)
    room = b.to_object("Sala_Paredes_Teto_Chao", col, [mats["wall"], mats["ceiling"], mats["floor"]])

    # lambrim de madeira até 0,95 m, com rodapé e friso
    b = Builder()
    segs = [("y", RY, -RX, RX), ("y", -RY, -RX, RX), ("x", -RX, -RY, RY), ("x", RX, -RY, RY)]
    for axis, fixed, a0, a1 in segs:
        cuts = [(a0, a1)]
        if axis == "x" and fixed > 0:
            cuts = [(a0, DOOR_Y0 - 0.08), (DOOR_Y1 + 0.08, a1)]
        for a, c in cuts:
            for (zc, h, t) in ((0.48, 0.92, 0.02), (0.07, 0.14, 0.035), (0.95, 0.05, 0.045)):
                off = fixed - math.copysign(t / 2, fixed)
                if axis == "x":
                    b.box((off, (a + c) / 2, zc), ((0, 1, 0), (1, 0, 0), (0, 0, 1)), (c - a, t, h))
                else:
                    b.box(((a + c) / 2, off, zc), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (c - a, t, h))
            # painéis verticais
            n = max(1, int((c - a) / 0.6))
            for k in range(n + 1):
                s = a + (c - a) * k / n
                off = fixed - math.copysign(0.03, fixed)
                if axis == "x":
                    b.box((off, s, 0.5), ((0, 0, 1), (1, 0, 0), (0, 1, 0)), (0.8, 0.02, 0.06))
                else:
                    b.box((s, off, 0.5), ((0, 0, 1), (0, 1, 0), (1, 0, 0)), (0.8, 0.02, 0.06))
    b.to_object("Lambrim_Madeira", col, [mats["wood_dark"]])

    # tapete
    b = Builder()
    b.box((DESK_C.x, DESK_C.y + 0.2, 0.006), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (2.4, 1.8, 0.012))
    rug = b.to_object("Tapete", col, [mats["rug"]])
    return room


def build_window(col, mats, c_light):
    x = -RX
    ym, zm = (WIN_Y0 + WIN_Y1) / 2, (WIN_Z0 + WIN_Z1) / 2
    wy, wz = WIN_Y1 - WIN_Y0, WIN_Z1 - WIN_Z0
    b = Builder()
    # caixilho e cruzeta
    for (cy, cz, dy, dz) in ((ym, WIN_Z0 - 0.03, wy + 0.12, 0.08), (ym, WIN_Z1 + 0.03, wy + 0.12, 0.06),
                             (WIN_Y0 - 0.03, zm, 0.06, wz), (WIN_Y1 + 0.03, zm, 0.06, wz), (ym, zm, wy, 0.04),
                             (ym, zm, 0.04, wz)):
        b.box((x - 0.07, cy, cz), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.1, dy, dz))
    b.box((x + 0.07, ym, WIN_Z0 - 0.05), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.22, wy + 0.25, 0.04))   # parapeito
    b.to_object("Janela_Caixilho", col, [mats["wood_dark"]])
    glass = bpy.data.meshes.new("Janela_Vidro")
    glass.from_pydata([(x - 0.08, WIN_Y0, WIN_Z0), (x - 0.08, WIN_Y1, WIN_Z0), (x - 0.08, WIN_Y1, WIN_Z1),
                       (x - 0.08, WIN_Y0, WIN_Z1)], [], [(0, 1, 2, 3)])
    glass.materials.append(mats["glass_rain"])
    g = new_object("Janela_Vidro_Chuva", glass, col)
    g.visible_shadow = False
    # persianas venezianas
    b = Builder()
    n = int(wz / 0.042)
    tilt = math.radians(38)
    for k in range(n):
        z = WIN_Z0 + 0.03 + k * 0.042
        u = Vector((0, 1, 0))
        v = Vector((math.cos(tilt), 0, math.sin(tilt)))
        b.box((x + 0.1, ym, z), (u, v, u.cross(v)), (wy + 0.04, 0.045, 0.003))
    for yy in (WIN_Y0 + 0.2, WIN_Y1 - 0.2):
        b.cylinder((x + 0.1, yy, WIN_Z0), (x + 0.1, yy, WIN_Z1 + 0.05), 0.002, 0.002, 4)
    b.box((x + 0.1, ym, WIN_Z1 + 0.06), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.05, wy + 0.08, 0.04))
    b.cylinder((x + 0.13, WIN_Y1 - 0.08, WIN_Z1 + 0.04), (x + 0.13, WIN_Y1 - 0.08, WIN_Z0 + 0.3), 0.003, 0.003, 4)
    blinds = b.to_object("Persianas", col, [mats["blinds"]])
    # fundo da rua (emissivo, só para a câmara e reflexos)
    me = bpy.data.meshes.new("Rua_Fundo")
    xb = x - 3.5
    me.from_pydata([(xb, -4.5, -1.5), (xb, 5.5, -1.5), (xb, 5.5, 5.0), (xb, -4.5, 5.0)], [], [(0, 1, 2, 3)])
    me.materials.append(mat_city())
    bg = new_object("Rua_Noite_Fundo", me, col)
    bg.visible_diffuse = False
    bg.visible_shadow = False
    # luz néon da rua a atravessar as persianas
    cy = light("LUZ_Neon_Rua_Ciano", "SPOT", c_light, (x - 3.0, 1.1, 2.5), 6000.0, (0.25, 0.85, 1.0),
               spot_size=math.radians(26), spot_blend=0.25, shadow_soft_size=0.03)
    cy.rotation_euler = look_at_rotation(cy.location, (0.2, 1.1, 1.1))
    rd = light("LUZ_Neon_Rua_Vermelho", "SPOT", c_light, (x - 3.0, -0.2, 3.1), 4500.0, (1.0, 0.08, 0.15),
               spot_size=math.radians(24), spot_blend=0.3, shadow_soft_size=0.03)
    rd.rotation_euler = look_at_rotation(rd.location, (0.9, 1.7, 1.4))
    amb = light("LUZ_Noite_Janela_Ambiente", "AREA", c_light, (x - 0.3, ym, zm), 3.0, (0.35, 0.45, 0.8),
                shape="RECTANGLE", size=wy, size_y=wz)
    amb.rotation_euler = (0, math.radians(-90), 0)
    amb.visible_camera = False
    return blinds


def build_door(col, mats, c_light):
    x = RX
    ym = (DOOR_Y0 + DOOR_Y1) / 2
    w = DOOR_Y1 - DOOR_Y0
    b = Builder()
    for (cy, cz, dy, dz) in ((DOOR_Y0 - 0.04, DOOR_Z1 / 2, 0.08, DOOR_Z1 + 0.08), (DOOR_Y1 + 0.04, DOOR_Z1 / 2, 0.08, DOOR_Z1 + 0.08),
                             (ym, DOOR_Z1 + 0.04, w + 0.16, 0.08)):
        b.box((x - 0.02, cy, cz), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.06, dy, dz))
    # folha da porta: metade de baixo em madeira, metade de cima em vidro fosco
    gz0, gz1 = 1.05, 1.95
    for (cy, cz, dy, dz) in ((ym, gz0 / 2, w - 0.02, gz0), (ym, (gz1 + DOOR_Z1) / 2, w - 0.02, DOOR_Z1 - gz1),
                             (DOOR_Y0 + 0.06, (gz0 + gz1) / 2, 0.1, gz1 - gz0), (DOOR_Y1 - 0.06, (gz0 + gz1) / 2, 0.1, gz1 - gz0)):
        b.box((x + 0.02, cy, cz), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.045, dy, dz))
    b.to_object("Porta_Madeira", col, [mats["wood_dark"]])
    b = Builder()
    b.cylinder((x - 0.01, DOOR_Y0 + 0.1, 1.0), (x - 0.07, DOOR_Y0 + 0.1, 1.0), 0.012, 0.012, 10)
    b.ico((x - 0.08, DOOR_Y0 + 0.1, 1.0), 0.028, (1, 1, 1), 2, 0.0)
    b.to_object("Porta_Macaneta", col, [mats["brass"]], smooth=True)
    gl = bpy.data.meshes.new("Porta_Vidro")
    gl.from_pydata([(x + 0.02, DOOR_Y0 + 0.11, gz0), (x + 0.02, DOOR_Y1 - 0.11, gz0), (x + 0.02, DOOR_Y1 - 0.11, gz1),
                    (x + 0.02, DOOR_Y0 + 0.11, gz1)], [], [(0, 1, 2, 3)])
    gl.materials.append(mats["glass_frosted"])
    go = new_object("Porta_Vidro_Fosco", gl, col)
    go.visible_shadow = False
    # letras pintadas no vidro (vistas de dentro, por isso ao contrário)
    for i, (txt, size, z) in enumerate(((DOOR_TEXT[0], 0.07, 1.62), (DOOR_TEXT[1], 0.045, 1.5))):
        cu = bpy.data.curves.new(f"Porta_Letras_{i}", "FONT")
        cu.body = txt
        cu.size = size
        cu.align_x = "CENTER"
        cu.materials.append(mats["gold_leaf"])
        t = new_object(f"Porta_Letras_{i}", cu, col)
        t.location = (x + 0.012, ym, z)
        t.rotation_euler = (math.radians(90), 0, math.radians(-90))
        t.scale = (-1, 1, 1)
    # luz do corredor por trás do vidro fosco
    hall = light("LUZ_Corredor", "AREA", c_light, (x + 0.6, ym, 1.6), 40.0, (1.0, 0.75, 0.45), size=0.8)
    hall.rotation_euler = (0, math.radians(90), 0)


def build_desk(col, mats):
    b = Builder()
    cx, cy = DESK_C.x, DESK_C.y
    top = DESK_H
    b.box((cx, cy, top - 0.02), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (DESK_W, DESK_D, 0.04))
    for sx in (-1, 1):
        px = cx + sx * (DESK_W / 2 - 0.23)
        b.box((px, cy, (top - 0.04) / 2), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.44, DESK_D - 0.04, top - 0.04))
        for k in range(3):
            z = 0.12 + k * 0.21
            b.box((px, cy + DESK_D / 2 - 0.005, z + 0.09), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.4, 0.02, 0.18))
    b.box((cx, cy - DESK_D / 2 + 0.03, 0.45), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (DESK_W - 0.9, 0.025, 0.55))
    b.box((cx, cy - DESK_D / 2 + 0.01, top - 0.06), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (DESK_W, 0.02, 0.04))
    desk = b.to_object("Secretaria", col, [mats["wood_desk"]])
    bev = desk.modifiers.new("Bevel", "BEVEL")
    bev.width = 0.006
    bev.segments = 2
    # puxadores
    b = Builder()
    for sx in (-1, 1):
        px = cx + sx * (DESK_W / 2 - 0.23)
        for k in range(3):
            z = 0.21 + k * 0.21
            b.box((px, cy + DESK_D / 2 + 0.012, z), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.1, 0.015, 0.018))
    b.to_object("Secretaria_Puxadores", col, [mats["brass"]])
    # tampo de vidro verde/feltro na zona de escrita
    b = Builder()
    b.box((cx, cy + 0.08, top + 0.002), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.8, 0.45, 0.004))
    b.to_object("Secretaria_Pasta_Couro", col, [mats["leather_green"]])


def build_chair(col, mats):
    b = Builder()
    c = CHAIR_C
    b.box((c.x, c.y, 0.47), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.5, 0.48, 0.07), mat=0)
    back_axis = Vector((0, 0.18, 1)).normalized()
    b.box((c.x, c.y + 0.26, 0.85), ((1, 0, 0), back_axis.cross(Vector((1, 0, 0))), back_axis), (0.48, 0.06, 0.6), mat=0)
    b.cylinder((c.x, c.y, 0.1), (c.x, c.y, 0.44), 0.025, 0.025, 12, mat=1)
    for k in range(5):
        a = k * 2 * math.pi / 5 + 0.3
        p = Vector((c.x + math.cos(a) * 0.32, c.y + math.sin(a) * 0.32, 0.06))
        b.cylinder((c.x, c.y, 0.1), p, 0.02, 0.018, 8, mat=1)
        b.ico(p - Vector((0, 0, 0.03)), 0.025, (1, 1, 1), 1, 0.0, mat=1)
    for sx in (-1, 1):
        b.box((c.x + sx * 0.27, c.y + 0.03, 0.66), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.05, 0.4, 0.04), mat=0)
        b.cylinder((c.x + sx * 0.27, c.y - 0.1, 0.5), (c.x + sx * 0.27, c.y - 0.1, 0.65), 0.012, 0.012, 8, mat=1)
    ch = b.to_object("Cadeira_Couro", col, [mats["leather_brown"], mats["metal_dark"]])
    bev = ch.modifiers.new("Bevel", "BEVEL")
    bev.width = 0.02
    bev.segments = 3
    ch.data.shade_smooth()


def crt_monitor(col, name, center, yaw, mats, size=0.4, color="beige", screen_mat=None):
    """Monitor/TV CRT. Frente (ecrã) em -Y local antes da rotação yaw."""
    b = Builder()
    w, h, d = size, size * 0.92, size * 1.05
    M = Matrix.Translation(center) @ Euler((0, 0, yaw)).to_matrix().to_4x4()
    body = 0
    b.box((0, 0.02, h / 2), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (w, d * 0.45, h), mat=body, M=M)
    # traseira do tubo: dois volumes que vão estreitando
    b.box((0, d * 0.36, h * 0.5), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (w * 0.8, d * 0.3, h * 0.8), mat=body, M=M)
    b.box((0, d * 0.6, h * 0.48), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (w * 0.5, d * 0.22, h * 0.5), mat=body, M=M)
    b.box((0, -d * 0.2, h * 0.5), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (w * 0.84, 0.02, h * 0.74), mat=2, M=M)
    if color == "beige":
        b.box((0, 0.05, -0.012), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (w * 0.55, d * 0.45, 0.025), mat=body, M=M)
        b.box((w * 0.35, -d * 0.215, h * 0.08), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.03, 0.01, 0.015), mat=3, M=M)
    else:
        b.box((0, -d * 0.215, h * 0.08), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (w * 0.6, 0.01, h * 0.08), mat=2, M=M)
    mats_list = [mats["plastic_beige"] if color == "beige" else mats["plastic_black"], None, mats["plastic_black"],
                 mats["led_green"]]
    mats_list[1] = mats_list[0]
    obj = b.to_object(name, col, mats_list)
    bev = obj.modifiers.new("Bevel", "BEVEL")
    bev.width = 0.012
    bev.segments = 2
    # ecrã curvo
    sw, sh = w * 0.74, h * 0.6
    nx, ny = 16, 12
    verts, faces, uvs = [], [], []
    for j in range(ny + 1):
        for i in range(nx + 1):
            u, v = i / nx, j / ny
            bulge = 0.018 * size / 0.4 * (1 - (2 * u - 1) ** 2) * (1 - (2 * v - 1) ** 2)
            verts.append(M @ Vector(((u - 0.5) * sw, -d * 0.215 - 0.004 - bulge, h * 0.5 + (v - 0.5) * sh)))
    for j in range(ny):
        for i in range(nx):
            a = j * (nx + 1) + i
            faces.append((a, a + 1, a + nx + 2, a + nx + 1))
            uvs += [(i / nx, j / ny), ((i + 1) / nx, j / ny), ((i + 1) / nx, (j + 1) / ny), (i / nx, (j + 1) / ny)]
    me = bpy.data.meshes.new(name + "_Ecra")
    me.from_pydata([tuple(v) for v in verts], [], faces)
    uvl = me.uv_layers.new(name="UVMap")
    uvl.data.foreach_set("uv", [c for uv in uvs for c in uv])
    me.materials.append(screen_mat)
    me.shade_smooth()
    scr = new_object(name + "_Ecra", me, col)
    screen_center = M @ Vector((0, -d * 0.215 - 0.02, h * 0.5))
    return obj, scr, screen_center


def build_computers(col, mats):
    yaw_crt = math.atan2(-(CHAIR_C.x - CRT_C.x), CHAIR_C.y - CRT_C.y) + math.pi
    _, _, crt_center = crt_monitor(col, "CRT_Secretaria", CRT_C, yaw_crt, mats, 0.4, "beige", mats["screen_crt"])
    # teclado e rato beges
    b = Builder()
    kb = CRT_C + Vector((-0.2, 0.32, 0.012))
    kyaw = yaw_crt + math.pi
    rot = Euler((math.radians(4), 0, kyaw)).to_matrix()
    b.box(kb, (rot @ Vector((1, 0, 0)), rot @ Vector((0, 1, 0)), rot @ Vector((0, 0, 1))), (0.44, 0.16, 0.025))
    for r_ in range(5):
        for k in range(15):
            p = kb + rot @ Vector((-0.2 + k * 0.028, -0.055 + r_ * 0.027, 0.016))
            b.box(p, (rot @ Vector((1, 0, 0)), rot @ Vector((0, 1, 0)), rot @ Vector((0, 0, 1))), (0.024, 0.023, 0.012))
    b.ico(CRT_C + Vector((0.08, 0.36, 0.018)), 0.035, (0.9, 1.4, 0.45), 2, 0.0)
    kbo = b.to_object("Teclado_Rato", col, [mats["plastic_beige"]])
    kbo.modifiers.new("Bevel", "BEVEL").width = 0.003
    # torre/caixa PC no chão ao lado da secretária
    b = Builder()
    b.box((DESK_C.x + DESK_W / 2 + 0.16, DESK_C.y + 0.1, 0.24), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.2, 0.45, 0.48))
    b.box((DESK_C.x + DESK_W / 2 + 0.16, DESK_C.y - 0.126, 0.33), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.15, 0.005, 0.045),
          mat=1)
    tower = b.to_object("PC_Torre", col, [mats["plastic_beige"], mats["plastic_black"]])
    tower.modifiers.new("Bevel", "BEVEL").width = 0.005

    # portátil moderno, aberto, virado para a cadeira
    b = Builder()
    lp = DESK_C + Vector((-0.28, 0.12, DESK_H + 0.008))
    lyaw = math.radians(8)
    R = Euler((0, 0, lyaw)).to_matrix()
    b.box(lp, (R @ Vector((1, 0, 0)), R @ Vector((0, 1, 0)), (0, 0, 1)), (0.32, 0.22, 0.014))
    hinge = lp + R @ Vector((0, -0.11, 0.007))
    tilt = math.radians(18)   # a tampa sobe da dobradiça e inclina para longe da cadeira
    ldir = R @ Vector((0, -math.sin(tilt), math.cos(tilt)))
    lid_c = hinge + ldir * 0.105
    ax_u = R @ Vector((1, 0, 0))
    ax_n = R @ Vector((0, math.cos(tilt), math.sin(tilt)))
    b.box(lid_c, (ax_u, ldir, ax_n), (0.32, 0.21, 0.006))
    lap = b.to_object("Portatil_Moderno", col, [mats["aluminium"]])
    lap.modifiers.new("Bevel", "BEVEL").width = 0.003
    # ecrã do portátil (lado virado para a cadeira)
    face_c = lid_c + ax_n * 0.0035
    nrm = ax_n
    corners = [face_c + ax_u * sx * 0.145 + ldir * sy * 0.092 for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    me = bpy.data.meshes.new("Portatil_Ecra")
    me.from_pydata([tuple(c + nrm * 0.0005) for c in corners], [], [(0, 1, 2, 3)])
    uvl = me.uv_layers.new(name="UVMap")
    uvl.data.foreach_set("uv", [0, 0, 1, 0, 1, 1, 0, 1])
    me.materials.append(mats["laptop_screen"])
    new_object("Portatil_Ecra", me, col)
    glow = light("LUZ_Portatil_Brilho", "AREA", col, face_c + nrm * 0.05, 1.5, (0.55, 0.7, 1.0), size=0.3, size_y=0.2)
    glow.rotation_euler = (-nrm).to_track_quat("-Z", "Y").to_euler()
    glow.visible_camera = False
    return crt_center


def build_tv(col, mats):
    b = Builder()
    tv_yaw = math.atan2(-(0.0 - TV_C.x), -1.6 - TV_C.y) + math.pi
    R = Euler((0, 0, tv_yaw)).to_matrix()
    # móvel baixo com gravador VHS
    b.box(TV_C + Vector((0, 0, 0.28)), (R @ Vector((1, 0, 0)), R @ Vector((0, 1, 0)), (0, 0, 1)), (0.75, 0.45, 0.56))
    obj = b.to_object("Movel_TV", col, [mats["wood_desk"]])
    obj.modifiers.new("Bevel", "BEVEL").width = 0.006
    b = Builder()
    b.box(TV_C + R @ Vector((0, -0.05, 0.6)), (R @ Vector((1, 0, 0)), R @ Vector((0, 1, 0)), (0, 0, 1)), (0.42, 0.28, 0.08))
    for k in range(4):
        b.box(TV_C + R @ Vector((-0.22 + k * 0.035, 0.08, 0.66 + 0.0)), (R @ Vector((0, 1, 0)), R @ Vector((1, 0, 0)), (0, 0, 1)),
              (0.19, 0.028, 0.105))
    b.to_object("VHS_Gravador_Cassetes", col, [mats["plastic_black"]])
    _, _, tv_center = crt_monitor(col, "TV_CRT", TV_C + Vector((0, 0, 0.64)), tv_yaw, mats, 0.62, "black", mats["screen_crt"])
    glow = light("LUZ_TV_Brilho", "AREA", col, tv_center + R @ Vector((0, -0.12, 0)), 6.0, (0.7, 0.8, 1.0), size=0.45, size_y=0.35)
    glow.rotation_euler = (R @ Vector((0, -1, 0))).to_track_quat("-Z", "Y").to_euler()
    glow.visible_camera = False
    return tv_center


def build_lamp(col, mats):
    """Candeeiro de banqueiro (latão + abajur verde)."""
    base = DESK_C + Vector((-0.62, -0.08, DESK_H))
    b = Builder()
    b.cylinder(base, base + Vector((0, 0, 0.025)), 0.09, 0.085, 24, mat=0)
    b.cylinder(base + Vector((0, 0.03, 0.025)), base + Vector((0, 0.03, 0.34)), 0.011, 0.011, 10, mat=0)
    b.cylinder(base + Vector((-0.2, 0.03, 0.34)), base + Vector((0.2, 0.03, 0.34)), 0.008, 0.008, 8, mat=0)
    b.cylinder(base + Vector((0.06, -0.02, 0.02)), base + Vector((0.06, -0.02, 0.1)), 0.004, 0.004, 6, mat=0)
    lamp = b.to_object("Candeeiro_Banqueiro_Latao", col, [mats["brass"]], smooth=True)
    # abajur: meio cilindro verde
    me = bpy.data.meshes.new("Abajur")
    bm = bmesh.new()
    segs, L, r = 16, 0.46, 0.085
    verts_o, verts_i = [], []
    for s in (-1, 1):
        ro, ri = [], []
        for i in range(segs + 1):
            a = math.pi * i / segs
            ro.append(bm.verts.new((s * L / 2, math.cos(a) * r, math.sin(a) * r * 0.9)))
            ri.append(bm.verts.new((s * L / 2, math.cos(a) * (r - 0.004), math.sin(a) * (r - 0.004) * 0.9)))
        verts_o.append(ro)
        verts_i.append(ri)
    for i in range(segs):
        bm.faces.new((verts_o[0][i], verts_o[0][i + 1], verts_o[1][i + 1], verts_o[1][i]))
        bm.faces.new((verts_i[0][i], verts_i[1][i], verts_i[1][i + 1], verts_i[0][i + 1]))
    for s in (0, 1):
        for i in range(segs):
            f = bm.faces.new((verts_o[s][i], verts_i[s][i], verts_i[s][i + 1], verts_o[s][i + 1]))
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mats["shade_green"])
    me.shade_smooth()
    shade = new_object("Candeeiro_Abajur_Verde", me, col)
    shade.location = base + Vector((0, 0.03, 0.29))
    b = Builder()
    b.cylinder((-0.17, 0, 0), (0.17, 0, 0), 0.013, 0.013, 10)
    bulb = b.to_object("Candeeiro_Lampada", col, [mats["bulb"]], smooth=True)
    bulb.location = base + Vector((0, 0.03, 0.3))
    return base + Vector((0, 0.03, 0.29))


def build_desk_props(col, mats):
    top = DESK_H
    b = Builder()
    # caneca de café
    mug = DESK_C + Vector((0.12, -0.12, top))
    b.cylinder(mug, mug + Vector((0, 0, 0.1)), 0.042, 0.045, 20, mat=0, cap=True)
    b.ring(mug + Vector((0.055, 0, 0.05)), Matrix.Identity(3), 0.022, 0.007, 1.2, 10, 6, mat=0)
    b.cylinder(mug + Vector((0, 0, 0.085)), mug + Vector((0, 0, 0.086)), 0.038, 0.038, 20, mat=4)
    # cinzeiro com beatas
    ash = DESK_C + Vector((0.33, -0.25, top))
    b.cylinder(ash, ash + Vector((0, 0, 0.025)), 0.065, 0.075, 24, mat=1)
    for k in range(5):
        a = k * 1.3
        p = ash + Vector((math.cos(a) * 0.035, math.sin(a) * 0.035, 0.028))
        q = p + Vector((math.cos(a + 1.2) * 0.03, math.sin(a + 1.2) * 0.03, 0.004))
        b.cylinder(p, q, 0.004, 0.004, 6, mat=2)
    # bloco de notas e caneta
    b.box(DESK_C + Vector((0.02, 0.15, top + 0.006)), (Vector((1, 0.15, 0)).normalized(), Vector((-0.15, 1, 0)).normalized(), (0, 0, 1)),
          (0.15, 0.21, 0.012), mat=3)
    b.cylinder(DESK_C + Vector((0.1, 0.14, top + 0.015)), DESK_C + Vector((0.16, 0.26, top + 0.015)), 0.004, 0.004, 8, mat=5)
    # disquetes empilhadas
    for k in range(6):
        p = DESK_C + Vector((0.72, -0.2 + rng.uniform(-0.01, 0.01), top + 0.002 + k * 0.0035))
        b.box(p, (Euler((0, 0, rng.uniform(-0.3, 0.3))).to_matrix() @ Vector((1, 0, 0)),
                  Euler((0, 0, rng.uniform(-0.3, 0.3))).to_matrix() @ Vector((0, 1, 0)), (0, 0, 1)),
              (0.09, 0.094, 0.0033), mat=6 + (k % 3))
    # caixas de CD
    for k in range(5):
        p = DESK_C + Vector((-0.4 + rng.uniform(-0.01, 0.01), 0.33, top + 0.005 + k * 0.0105))
        R = Euler((0, 0, rng.uniform(-0.2, 0.2))).to_matrix()
        b.box(p, (R @ Vector((1, 0, 0)), R @ Vector((0, 1, 0)), (0, 0, 1)), (0.142, 0.125, 0.01), mat=2)
    # lupa
    lup = DESK_C + Vector((0.0, -0.22, top + 0.006))
    b.ring(lup, Euler((math.pi / 2, 0, 0)).to_matrix(), 0.045, 0.005, 1.0, 20, 6, mat=5)
    b.cylinder(lup + Vector((0.05, -0.02, 0)), lup + Vector((0.14, -0.06, 0)), 0.008, 0.009, 8, mat=9)
    props = b.to_object("Secretaria_Objetos", col, [mats["ceramic"], mats["glass_ash"], mats["cig"], mats["paper"],
                                                   mats["coffee"], mats["brass"], mats["floppy_black"], mats["floppy_blue"],
                                                   mats["floppy_red"], mats["wood_desk"]], smooth=True)
    # lente da lupa
    b = Builder()
    b.cylinder(lup - Vector((0, 0, 0.002)), lup + Vector((0, 0, 0.002)), 0.043, 0.043, 20)
    b.to_object("Lupa_Lente", col, [mats["glass_clear"]], smooth=True)
    # caixa do "caso atual" (capa trocável), de pé, virada para a câmara
    b = Builder()
    cc = DESK_C + Vector((-0.34, -0.27, top + 0.115))
    R = Euler((math.radians(-8), 0, math.radians(10))).to_matrix()
    b.box(cc, (R @ Vector((1, 0, 0)), R @ Vector((0, 1, 0)), R @ Vector((0, 0, 1))), (0.16, 0.035, 0.22))
    box = b.to_object("Caso_Atual_Caixa", col, [mats["plastic_black"]])
    box.modifiers.new("Bevel", "BEVEL").width = 0.003
    fc = cc + R @ Vector((0, -0.0185, 0))
    corners = [fc + R @ Vector((sx * 0.078, 0, sz * 0.108)) for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    me = bpy.data.meshes.new("Caso_Atual_Capa")
    me.from_pydata([tuple(c) for c in corners], [], [(0, 1, 2, 3)])
    me.uv_layers.new(name="UVMap").data.foreach_set("uv", [0, 0, 1, 0, 1, 1, 0, 1])
    me.materials.append(mats["cover"])
    new_object("Caso_Atual_Capa", me, col)
    # etiqueta de prova vermelha na caixa
    b = Builder()
    b.box(fc + R @ Vector((0, -0.001, -0.07)), (R @ Vector((1, 0, 0)), R @ Vector((0, 1, 0)), R @ Vector((0, 0, 1))),
          (0.165, 0.003, 0.022))
    b.to_object("Caso_Atual_Fita_Prova", col, [mats["tape_red"]])


def build_board(col, mats, photos):
    """Quadro de cortiça com fotografias, recortes, alfinetes e fio vermelho."""
    c = BOARD_C
    b = Builder()
    b.box(c + Vector((0, 0.01, 0)), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (BOARD_W, 0.02, BOARD_H), mat=0)
    for (dx, dz, w, h) in ((0, BOARD_H / 2 + 0.02, BOARD_W + 0.08, 0.04), (0, -BOARD_H / 2 - 0.02, BOARD_W + 0.08, 0.04),
                           (BOARD_W / 2 + 0.02, 0, 0.04, BOARD_H), (-BOARD_W / 2 - 0.02, 0, 0.04, BOARD_H)):
        b.box(c + Vector((dx, 0.0, dz)), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (w, 0.035, h), mat=1)
    b.to_object("Quadro_Cortica", col, [mats["cork"], mats["wood_dark"]])
    pins = []
    slots = [(-0.62, 0.2, 0.2, 0.15, -4), (-0.2, 0.26, 0.22, 0.16, 3), (0.28, 0.22, 0.2, 0.15, -2),
             (0.62, 0.12, 0.18, 0.135, 5), (-0.45, -0.2, 0.2, 0.15, 2), (0.35, -0.22, 0.22, 0.165, -6)]
    y = c.y - 0.003
    for i, (dx, dz, w, h, ang) in enumerate(slots):
        R = Euler((0, math.radians(ang), 0)).to_matrix()
        cen = c + Vector((dx, 0, dz))
        corners = [cen + R @ Vector((sx * w / 2, 0, sz * h / 2)) for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        me = bpy.data.meshes.new(f"Foto_{i + 1}")
        me.from_pydata([(p.x, y - i * 0.0005, p.z) for p in corners], [], [(0, 1, 2, 3)])
        me.uv_layers.new(name="UVMap").data.foreach_set("uv", [0, 0, 1, 0, 1, 1, 0, 1])
        me.materials.append(mat_image(f"M_Foto_Prova_{i + 1}", photos[i], rough=0.3))
        new_object(f"Quadro_Foto_{i + 1}", me, col)
        pins.append(cen + R @ Vector((0, 0, h / 2 - 0.015)) + Vector((0, -0.012, 0)))
    # papéis, recortes de jornal, post-its
    b = Builder()
    for _ in range(9):
        dx, dz = rng.uniform(-0.75, 0.75), rng.uniform(-0.4, 0.4)
        if any(abs(dx - s[0]) < 0.15 and abs(dz - s[1]) < 0.12 for s in slots):
            continue
        R = Euler((0, rng.uniform(-0.15, 0.15), 0)).to_matrix()
        w, h = rng.uniform(0.08, 0.2), rng.uniform(0.08, 0.26)
        m = rng.choice([0, 0, 1, 2])
        b.box(c + Vector((dx, -0.002 - rng.uniform(0, 0.002), dz)), (R @ Vector((1, 0, 0)), (0, 1, 0), R @ Vector((0, 0, 1))),
              (w, 0.001, h), mat=m)
        pins.append(c + Vector((dx, -0.012, dz + h / 2 - 0.02)))
    b.to_object("Quadro_Papeis", col, [mats["paper"], mats["newspaper"], mats["postit"]])
    # alfinetes
    b = Builder()
    for p in pins:
        b.ico(p, 0.008, (1, 1, 1), 1, 0.0)
        b.cylinder(p, p + Vector((0, 0.012, 0)), 0.001, 0.001, 4)
    b.to_object("Quadro_Alfinetes", col, [mats["pin_red"]], smooth=True)
    # fio vermelho entre alfinetes
    order = list(range(len(pins)))
    rng.shuffle(order)
    cu = bpy.data.curves.new("Fio_Vermelho", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.002
    for a_, b_ in zip(order[:-1], order[1:]):
        if rng.random() < 0.3:
            continue
        sp = cu.splines.new("POLY")
        sp.points.add(1)
        sp.points[0].co = (*pins[a_], 1)
        sp.points[1].co = (*pins[b_], 1)
    cu.materials.append(mats["string_red"])
    new_object("Quadro_Fio_Vermelho", cu, col)


def build_shelf(col, mats):
    """Estante metálica com jogos em sacos de prova etiquetados."""
    x0, x1 = SHELF_X0, SHELF_X1
    yb, depth, hgt = RY - 0.02, 0.42, 1.95
    yc = yb - depth / 2
    b = Builder()
    for x in (x0, x1):
        for y in (yb - 0.02, yb - depth + 0.02):
            b.box((x, y, hgt / 2), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.035, 0.035, hgt))
    levels = [0.12, 0.58, 1.04, 1.5, 1.93]
    for z in levels:
        b.box(((x0 + x1) / 2, yc, z), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (x1 - x0 + 0.04, depth, 0.025))
    b.to_object("Estante_Metalica", col, [mats["metal_shelf"]])
    items = Builder()
    bags = Builder()
    tags = Builder()
    labels = []
    num = 1
    for li, z in enumerate(levels[:-1]):
        x = x0 + 0.06
        while x < x1 - 0.12:
            kind = rng.random()
            if kind < 0.55:   # caixa grande de PC, de pé
                w, d, h = rng.uniform(0.045, 0.07), rng.uniform(0.19, 0.24), rng.uniform(0.24, 0.3)
            elif kind < 0.85:  # caixa de PS1/CD, de pé
                w, d, h = 0.012, 0.125, 0.142
            else:             # cartucho/manual
                w, d, h = 0.02, 0.17, 0.2
            lean = math.radians(rng.uniform(-6, 6))
            R = Euler((0, lean, 0)).to_matrix()
            cen = Vector((x + w / 2 + 0.012, yc + rng.uniform(-0.03, 0.03), z + 0.0125 + h / 2 + 0.005))
            items.box(cen, (R @ Vector((1, 0, 0)), R @ Vector((0, 1, 0)), R @ Vector((0, 0, 1))), (w, d, h),
                      mat=rng.randint(0, 3))
            # saco de prova à volta
            bags.box(cen + Vector((0, 0, 0.02)), (R @ Vector((1, 0, 0)), R @ Vector((0, 1, 0)), R @ Vector((0, 0, 1))),
                     (w + 0.02, d + 0.03, h + 0.06), mat=0)
            # fita vermelha de prova no topo do saco e etiqueta branca
            tags.box(cen + R @ Vector((0, 0, h / 2 + 0.045)), (R @ Vector((1, 0, 0)), R @ Vector((0, 1, 0)), R @ Vector((0, 0, 1))),
                     (w + 0.024, d + 0.034, 0.018), mat=0)
            tag_c = cen + R @ Vector((0, -(d / 2 + 0.017), -h * 0.15))
            tags.box(tag_c, (R @ Vector((1, 0, 0)), R @ Vector((0, 1, 0)), R @ Vector((0, 0, 1))),
                     (max(w + 0.01, 0.05), 0.002, 0.06), mat=1)
            labels.append((tag_c + Vector((0, -0.0015, 0)), f"PROVA\nNº {num:03d}", max(w + 0.01, 0.05)))
            num += 1
            x += w + 0.035 + rng.uniform(0, 0.03)
    items_obj = items.to_object("Jogos_Caixas", col, [mats["box_a"], mats["box_b"], mats["box_c"], mats["box_d"]])
    items_obj.modifiers.new("Bevel", "BEVEL").width = 0.002
    bag_obj = bags.to_object("Sacos_Prova", col, [mats["bag"]])
    tags.to_object("Sacos_Prova_Fitas_Etiquetas", col, [mats["tape_red"], mats["paper"]])
    sub = bag_obj.modifiers.new("Subdivisao", "SUBSURF")
    sub.levels, sub.render_levels = 1, 2
    tex = bpy.data.textures.new("T_Saco_Amarrotado", "CLOUDS")
    tex.noise_scale = 0.03
    disp = bag_obj.modifiers.new("Amarrotado", "DISPLACE")
    disp.texture = tex
    disp.strength = 0.006
    # etiquetas escritas
    for i, (p, txt, w) in enumerate(labels):
        cu = bpy.data.curves.new(f"Etiqueta_{i}", "FONT")
        cu.body = txt
        cu.size = min(0.013, w * 0.22)
        cu.align_x = "CENTER"
        cu.align_y = "CENTER"
        cu.materials.append(mats["ink"])
        t = new_object(f"Etiqueta_Prova_{i + 1:03d}", cu, col)
        t.location = p
        t.rotation_euler = (math.radians(90), 0, 0)
    # placa na estante
    cu = bpy.data.curves.new("Placa_Estante", "FONT")
    cu.body = "PROVAS — NÃO ABRIR"
    cu.size = 0.035
    cu.align_x = "CENTER"
    cu.materials.append(mats["tape_red"])
    t = new_object("Placa_Estante", cu, col)
    t.location = ((x0 + x1) / 2, yb - depth - 0.001, 1.93 - 0.035)
    t.rotation_euler = (math.radians(90), 0, 0)


def build_room_props(col, mats):
    # arquivador metálico (canto da frente, à esquerda)
    b = Builder()
    fc = Vector((-RX + 0.28, -RY + 0.45, 0))
    b.box(fc + Vector((0, 0, 0.66)), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.46, 0.6, 1.32), mat=0)
    for k in range(4):
        z = 0.17 + k * 0.32
        out = 0.22 if k == 1 else 0.0
        b.box(fc + Vector((0.23 + 0.012 + out, 0, z)), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.02, 0.5, 0.28), mat=0)
        b.box(fc + Vector((0.25 + 0.012 + out, 0, z + 0.06)), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.02, 0.12, 0.02), mat=1)
    for k in range(10):   # pastas na gaveta aberta
        b.box(fc + Vector((0.12 + k * 0.015, 0, 0.55)), ((0, 1, 0), (1, 0, 0), (0, 0, 1)), (0.42, 0.004, 0.24 + rng.uniform(0, 0.03)),
              mat=2)
    b.to_object("Arquivador_Metalico", col, [mats["metal_olive"], mats["brass"], mats["folder"]])
    # cabide com gabardina e chapéu (canto da frente, à direita)
    b = Builder()
    cr = Vector((RX - 0.3, -RY + 0.3, 0))
    b.cylinder(cr, cr + Vector((0, 0, 1.75)), 0.018, 0.015, 10, mat=0)
    for k in range(3):
        a = k * 2 * math.pi / 3
        b.cylinder(cr + Vector((0, 0, 0.05)), cr + Vector((math.cos(a) * 0.25, math.sin(a) * 0.25, 0.0)), 0.014, 0.012, 8, mat=0)
    b.ico(cr + Vector((0.0, 0.0, 1.2)), 0.2, (0.9, 0.7, 2.6), 3, 0.25, mat=1)        # gabardina pendurada
    b.ico(cr + Vector((0, 0, 1.78)), 0.16, (1.0, 1.0, 0.28), 3, 0.05, mat=2)         # aba do chapéu
    b.ico(cr + Vector((0, 0, 1.84)), 0.1, (1.0, 0.95, 0.65), 3, 0.05, mat=2)         # copa
    coat = b.to_object("Cabide_Gabardina_Chapeu", col, [mats["wood_dark"], mats["coat"], mats["hat"]], smooth=True)
    sub = coat.modifiers.new("Subdivisao", "SUBSURF")
    sub.levels, sub.render_levels = 1, 2
    # relógio de parede parado às 3:33
    b = Builder()
    ck = Vector((0.72, RY - 0.03, 2.3))
    b.cylinder(ck, ck + Vector((0, -0.04, 0)), 0.16, 0.16, 32, mat=0)
    b.cylinder(ck + Vector((0, -0.041, 0)), ck + Vector((0, -0.042, 0)), 0.145, 0.145, 32, mat=1)
    for ang, ln, wd in ((math.radians(90 - (3 * 30 + 33 * 0.5)), 0.08, 0.006), (math.radians(90 - 33 * 6), 0.12, 0.004)):
        p0 = ck + Vector((0, -0.046, 0))
        p1 = p0 + Vector((math.cos(ang) * ln, 0, math.sin(ang) * ln))
        b.box((p0 + p1) / 2, ((p1 - p0).normalized(), (0, 1, 0), (p1 - p0).normalized().cross(Vector((0, 1, 0)))), (ln, 0.002, wd), mat=2)
    for k in range(12):
        a = k * math.pi / 6
        p = ck + Vector((math.cos(a) * 0.125, -0.043, math.sin(a) * 0.125))
        b.box(p, ((math.cos(a), 0, math.sin(a)), (0, 1, 0), (-math.sin(a), 0, math.cos(a))), (0.02, 0.002, 0.005), mat=2)
    b.to_object("Relogio_Parado_333", col, [mats["wood_dark"], mats["paper"], mats["ink"]], smooth=True)
    # pilha de cassetes VHS e caixas de jogos no chão, junto à secretária
    b = Builder()
    for k in range(7):
        p = Vector((-1.0 + rng.uniform(-0.02, 0.02), 0.05, 0.013 + k * 0.026))
        R = Euler((0, 0, rng.uniform(-0.25, 0.25))).to_matrix()
        b.box(p, (R @ Vector((1, 0, 0)), R @ Vector((0, 1, 0)), (0, 0, 1)), (0.19, 0.105, 0.025), mat=k % 2)
    b.to_object("Cassetes_VHS_Pilha", col, [mats["plastic_black"], mats["paper"]])
    # ventoinha de teto (roda devagar)
    fan_c = Vector((DESK_C.x, DESK_C.y + 0.1, RH))
    b = Builder()
    b.cylinder(fan_c, fan_c - Vector((0, 0, 0.32)), 0.012, 0.012, 8, mat=0)
    b.cylinder(fan_c - Vector((0, 0, 0.3)), fan_c - Vector((0, 0, 0.42)), 0.09, 0.07, 20, mat=0)
    b.to_object("Ventoinha_Suporte", col, [mats["brass"]], smooth=True)
    b = Builder()
    for k in range(4):
        a = k * math.pi / 2
        d = Vector((math.cos(a), math.sin(a), 0))
        s = Vector((-math.sin(a), math.cos(a), 0))
        R = Matrix.Rotation(math.radians(12), 3, d)
        b.box(d * 0.38, (d, R @ s, R @ Vector((0, 0, 1))), (0.62, 0.12, 0.008), mat=0)
    blades = b.to_object("Ventoinha_Pas", col, [mats["wood_dark"]])
    blades.location = fan_c - Vector((0, 0, 0.4))
    blades.keyframe_insert("rotation_euler", frame=1, index=2)
    blades.rotation_euler.z = 2 * math.pi
    blades.keyframe_insert("rotation_euler", frame=73, index=2)
    for fc in iter_fcurves(blades.animation_data.action):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
        fc.modifiers.new("CYCLES")


def iter_fcurves(action):
    fcs = list(getattr(action, "fcurves", []) or [])
    if not fcs:
        for layer in getattr(action, "layers", []):
            for strip in layer.strips:
                for cb in strip.channelbags:
                    fcs += list(cb.fcurves)
    return fcs


# ---------------------------------------------------------------------------
# Luzes, variantes, câmaras, marcadores
# ---------------------------------------------------------------------------
def build_variants(v_cols, lamp_pos):
    v1, v2, v3 = v_cols

    def lamp_lights(col, tag):
        sp = light(f"LUZ_Candeeiro_{tag}", "SPOT", col, lamp_pos + Vector((0, 0, -0.02)), 30.0, (1.0, 0.72, 0.42),
                   spot_size=math.radians(120), spot_blend=0.6, shadow_soft_size=0.05)
        sp.rotation_euler = (0, 0, 0)
        glow = light(f"LUZ_Candeeiro_Abajur_{tag}", "POINT", col, lamp_pos + Vector((0, 0, 0.04)), 1.5, (0.3, 1.0, 0.45),
                     shadow_soft_size=0.02)
        bulb = new_object(f"Candeeiro_Lampada_Acesa_{tag}", bpy.data.objects["Candeeiro_Lampada"].data.copy(), col)
        bulb.location = bpy.data.objects["Candeeiro_Lampada"].location
        bulb.data.materials[0] = mat_emit(f"M_Lampada_Acesa_{tag}", (1.0, 0.75, 0.45), 25.0)
        return sp

    lamp_lights(v1, "Normal")
    # v2: só ecrãs — o candeeiro fica apagado
    lamp_lights(v3, "Relampago")
    flash = light("LUZ_Relampago", "AREA", v3, (-RX - 1.2, (WIN_Y0 + WIN_Y1) / 2, 2.6), 0.0, (0.75, 0.82, 1.0),
                  shape="RECTANGLE", size=2.5, size_y=2.0)
    flash.rotation_euler = look_at_rotation(flash.location, (0.5, 0.8, 0.8))
    flash.visible_camera = False
    for f, e in ((1, 0), (60, 0), (61, 4000), (62, 300), (63, 2500), (65, 0), (150, 0), (151, 3000), (153, 0)):
        flash.data.energy = e
        flash.data.keyframe_insert("energy", frame=f)
    for fc in iter_fcurves(flash.data.animation_data.action):
        for kp in fc.keyframe_points:
            kp.interpolation = "CONSTANT"


def build_cameras(col, crt_center, tv_center):
    cams = {}

    def cam(name, loc, target, lens, fstop=None, focus=None):
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        cd.sensor_width = 36
        cd.clip_start = 0.02
        if fstop:
            cd.dof.use_dof = True
            cd.dof.aperture_fstop = fstop
            cd.dof.focus_distance = focus
        ob = new_object(name, cd, col)
        ob.location = loc
        ob.rotation_euler = look_at_rotation(loc, target)
        cams[name] = ob

    head = CHAIR_C + Vector((0, -0.05, 1.22))
    cam("CAM_1_Frente_Apresentador", (0.0, -1.5, 1.22), head - Vector((0, 0, 0.12)), 32, 2.8, (head - Vector((0, -1.5, 1.22))).length)
    cam("CAM_2_Lado_Perfil", (1.95, 1.2, 1.18), (-0.6, 1.05, 1.05), 40, 2.8, 1.95)
    cam("CAM_3_Plano_Geral", (1.95, -1.75, 2.1), (-0.5, 0.95, 0.85), 20)
    eye = CHAIR_C + Vector((0.05, -0.1, 1.18))
    cam("CAM_4_Insert_Ecra_CRT", eye + (crt_center - eye) * 0.45, crt_center, 35, 4.0, ((crt_center - eye) * 0.55).length)
    cam("CAM_5_Insert_Quadro", (BOARD_C.x + 0.15, 0.55, 1.6), BOARD_C + Vector((0, 0, -0.02)), 30, 5.6, 1.45)
    cam("CAM_6_Insert_Provas", (0.85, 0.45, 1.2), ((SHELF_X0 + SHELF_X1) / 2, RY - 0.25, 0.95), 35, 4.0, 1.5)
    cam("CAM_7_Por_Cima_Ombro", CHAIR_C + Vector((-0.35, 0.45, 1.42)), crt_center, 32, 2.8, 1.0)
    cam("CAM_8_TV_Fundo_Analise", (0.35, -0.2, 1.2), tv_center + Vector((0.25, 0, 0.0)), 28, 4.0, 2.2)
    bpy.context.scene.camera = cams["CAM_1_Frente_Apresentador"]
    return cams


def build_markers(col):
    def marker(name, loc, facing, note):
        theta = math.atan2(facing[0], -facing[1])
        e = bpy.data.objects.new(name, None)
        e.empty_display_type = "SINGLE_ARROW"
        e.empty_display_size = 0.4
        col.objects.link(e)
        e.location = loc
        e.rotation_euler = (0, 0, theta)
        e["nota"] = note
        me = bpy.data.meshes.new(name + "_Silhueta")
        bm = bmesh.new()
        # silhueta sentada: tronco + cabeça + coxas
        bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.2, radius2=0.18, depth=0.62,
                              matrix=Matrix.Translation((0, 0, 0.8)))
        bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=0.11, matrix=Matrix.Translation((0, 0, 1.25)))
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0, -0.2, 0.52)) @ Matrix.Diagonal((0.36, 0.42, 0.14, 1)))
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0, -0.42, 0.25)) @ Matrix.Diagonal((0.3, 0.1, 0.5, 1)))
        bm.to_mesh(me)
        bm.free()
        sil = new_object(name + "_Silhueta", me, col)
        sil.parent = e
        sil.display_type = "WIRE"
        sil.hide_render = True
        sil.hide_select = True

    marker("PERSONAGEM_1_Sentado_Frente", (CHAIR_C.x, CHAIR_C.y, 0.0), (0, -1),
           "sentado, a falar para a CAM_1 (pose sentada do Mixamo, ex.: 'Sitting Talking')")
    to_crt = (CRT_C - CHAIR_C).normalized()
    marker("PERSONAGEM_2_Sentado_Ao_Computador", (CHAIR_C.x, CHAIR_C.y, 0.0), (to_crt.x, to_crt.y),
           "sentado virado para o CRT — ver de perfil na CAM_2 (ex.: 'Typing')")


def setup_world():
    w = bpy.data.worlds.new("Mundo_Noite")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.01, 0.012, 0.02, 1)
    bpy.context.scene.world = w


def setup_render():
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.cycles.samples = 384
    scn.cycles.preview_samples = 32
    scn.cycles.use_adaptive_sampling = True
    scn.cycles.adaptive_threshold = 0.02
    scn.cycles.use_denoising = True
    scn.cycles.max_bounces = 8
    scn.cycles.transmission_bounces = 8
    scn.cycles.sample_clamp_indirect = 6.0
    scn.cycles.caustics_reflective = False
    scn.cycles.caustics_refractive = False
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


def setup_compositor():
    scn = bpy.context.scene
    scn.use_nodes = True
    nt = scn.node_tree
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new
    rl = N("CompositorNodeRLayers")
    glare = N("CompositorNodeGlare")
    glare.glare_type = "FOG_GLOW"
    try_set(glare, "Threshold", 0.8)
    try_set(glare, "Strength", 0.35)
    L(rl.outputs["Image"], glare.inputs["Image"])
    lens = N("CompositorNodeLensdist")
    try_set(lens, "Distortion", 0.01)
    try_set(lens, "Dispersion", 0.006)
    L(glare.outputs["Image"], lens.inputs["Image"])
    hs = N("CompositorNodeHueSat")
    try_set(hs, "Saturation", 0.8)
    L(lens.outputs["Image"], hs.inputs["Image"])
    cb = N("CompositorNodeColorBalance")
    cb.correction_method = "LIFT_GAMMA_GAIN"
    try_set(cb, "Lift", (0.98, 1.0, 1.03))
    try_set(cb, "Gain", (1.04, 1.0, 0.95))
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
    lift.inputs["To Min"].default_value = 0.5
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


README_TEXT = """GABINETE DO INVESTIGADOR — como usar
======================================

TROCAR O QUE APARECE NOS ECRÃS (CRT da secretária + TV):
  Image Editor > imagem 'ECRA_Jogo' > Image > Replace... (imagem OU vídeo .mp4).
  Para vídeo: no nó Image Texture do material M_Ecra_CRT_Jogo, ative 'Auto Refresh'
  e ponha o número de frames.

FOTOS DO QUADRO: substitua as imagens FOTO_Prova_1 … FOTO_Prova_6.
CAPA DO CASO ATUAL: substitua a imagem CAPA_Caso_Atual.
LETRAS DA PORTA: edite os objetos de texto Porta_Letras_0 / Porta_Letras_1 (Tab).

VARIANTES (04_VARIANTES — ative só uma):
  VAR_1_Noite_Normal | VAR_2_So_Ecras (candeeiro apagado) | VAR_3_Relampago (frames 61 e 151)

PERSONAGEM: marcadores em 07_PERSONAGEM, frente = -Y (Mixamo). Use uma animação
sentada do Mixamo e copie Location/Rotation do marcador para o armature.
"""


def main():
    args = parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.name = "Gabinete_Investigador"
    c_room = collection("01_SALA")
    c_furn = collection("02_MOBILIARIO_EQUIPAMENTO")
    c_light = collection("03_LUZ_BASE")
    c_var = collection("04_VARIANTES")
    v_cols = [collection(n, c_var) for n in ("VAR_1_Noite_Normal", "VAR_2_So_Ecras", "VAR_3_Relampago")]
    c_cam = collection("05_CAMARAS")
    c_char = collection("06_PERSONAGEM")

    img_screen = placeholder_signal()
    photos = [placeholder_photo(i + 1) for i in range(6)]
    cover = placeholder_cover()
    mats = {
        "wall": mat_wall(), "ceiling": mat_ceiling(), "floor": mat_floor_planks(), "rug": mat_rug(),
        "wood_dark": mat_wood("M_Madeira_Escura", dark=1.4), "wood_desk": mat_wood("M_Madeira_Secretaria", dark=1.1),
        "brass": mat_simple("M_Latao", (0.45, 0.32, 0.12), 0.3, metal=1.0, noise_scale=25),
        "leather_green": mat_simple("M_Couro_Verde", (0.02, 0.06, 0.035), 0.5, noise_scale=80, bump=0.2),
        "leather_brown": mat_simple("M_Couro_Castanho", (0.07, 0.03, 0.015), 0.45, noise_scale=60, bump=0.3),
        "metal_dark": mat_simple("M_Metal_Escuro", (0.05, 0.05, 0.05), 0.35, metal=1.0),
        "metal_olive": mat_simple("M_Metal_Verde_Oliva", (0.08, 0.09, 0.055), 0.45, metal=0.6, noise_scale=12, bump=0.1),
        "metal_shelf": mat_simple("M_Metal_Estante", (0.12, 0.12, 0.12), 0.5, metal=0.8, noise_scale=20, bump=0.1),
        "plastic_beige": mat_plastic("M_Plastico_Bege_Amarelado", (0.42, 0.37, 0.27)),
        "plastic_black": mat_plastic("M_Plastico_Preto", (0.02, 0.02, 0.022), 0.4),
        "aluminium": mat_simple("M_Aluminio", (0.55, 0.56, 0.58), 0.3, metal=1.0),
        "led_green": mat_emit("M_LED_Verde", (0.2, 1.0, 0.3), 20.0),
        "screen_crt": mat_image("M_Ecra_CRT_Jogo", img_screen, emission=3.5, crt=True),
        "laptop_screen": mat_laptop_screen(),
        "shade_green": mat_simple("M_Abajur_Vidro_Verde", (0.02, 0.2, 0.06), 0.15),
        "bulb": mat_simple("M_Lampada_Apagada", (0.8, 0.78, 0.7), 0.2),
        "glass_rain": mat_glass("M_Vidro_Chuva", 0.02, drops=True),
        "glass_frosted": mat_glass("M_Vidro_Fosco", 0.45),
        "glass_clear": mat_glass("M_Vidro_Lupa", 0.0),
        "gold_leaf": mat_simple("M_Letras_Douradas", (0.6, 0.45, 0.15), 0.3, metal=1.0),
        "ceramic": mat_simple("M_Caneca_Ceramica", (0.35, 0.33, 0.3), 0.3),
        "coffee": mat_simple("M_Cafe", (0.02, 0.008, 0.003), 0.05),
        "glass_ash": mat_simple("M_Cinzeiro", (0.05, 0.06, 0.06), 0.1),
        "cig": mat_simple("M_Beatas", (0.6, 0.55, 0.45), 0.8),
        "paper": mat_simple("M_Papel", (0.62, 0.6, 0.53), 0.85, noise_scale=40),
        "newspaper": mat_simple("M_Jornal", (0.4, 0.38, 0.32), 0.9, noise_scale=300),
        "postit": mat_simple("M_PostIt", (0.7, 0.6, 0.12), 0.8),
        "floppy_black": mat_plastic("M_Disquete_Preta", (0.02, 0.02, 0.02)),
        "floppy_blue": mat_plastic("M_Disquete_Azul", (0.02, 0.05, 0.15)),
        "floppy_red": mat_plastic("M_Disquete_Vermelha", (0.2, 0.02, 0.02)),
        "cork": mat_simple("M_Cortica", (0.2, 0.12, 0.06), 0.95, noise_scale=150, bump=0.5),
        "pin_red": mat_plastic("M_Alfinete_Vermelho", (0.35, 0.01, 0.01), 0.3),
        "string_red": mat_simple("M_Fio_Vermelho", (0.4, 0.01, 0.01), 0.7),
        "bag": mat_bag(),
        "tape_red": mat_simple("M_Fita_Prova_Vermelha", (0.45, 0.01, 0.015), 0.4),
        "ink": mat_simple("M_Tinta_Preta", (0.01, 0.01, 0.01), 0.6),
        "box_a": mat_plastic("M_Caixa_Jogo_A", (0.12, 0.02, 0.02), 0.5, 0.5),
        "box_b": mat_plastic("M_Caixa_Jogo_B", (0.02, 0.03, 0.08), 0.5, 0.5),
        "box_c": mat_plastic("M_Caixa_Jogo_C", (0.06, 0.06, 0.05), 0.5, 0.5),
        "box_d": mat_plastic("M_Caixa_Jogo_D", (0.14, 0.1, 0.03), 0.5, 0.5),
        "cover": mat_image("M_Capa_Caso_Atual", cover, rough=0.25),
        "folder": mat_simple("M_Pasta_Kraft", (0.35, 0.25, 0.14), 0.8),
        "coat": mat_simple("M_Gabardina", (0.14, 0.11, 0.07), 0.85, noise_scale=90, bump=0.3),
        "hat": mat_simple("M_Chapeu_Feltro", (0.03, 0.028, 0.026), 0.9, noise_scale=120, bump=0.2),
        "blinds": mat_simple("M_Persianas", (0.45, 0.42, 0.36), 0.5, noise_scale=30),
    }

    print("> sala")
    build_room(c_room, mats)
    build_window(c_room, mats, c_light)
    build_door(c_room, mats, c_light)
    print("> mobiliário e equipamento")
    build_desk(c_furn, mats)
    build_chair(c_furn, mats)
    crt_center = build_computers(c_furn, mats)
    tv_center = build_tv(c_furn, mats)
    lamp_pos = build_lamp(c_furn, mats)
    build_desk_props(c_furn, mats)
    build_board(c_furn, mats, photos)
    build_shelf(c_furn, mats)
    build_room_props(c_furn, mats)
    print("> luzes, câmaras, marcadores")
    fill = light("LUZ_Preenchimento_Frio", "AREA", c_light, (0.6, -1.4, 2.5), 25.0, (0.5, 0.6, 0.85), size=1.5)
    fill.rotation_euler = look_at_rotation(fill.location, (0, 1.2, 1.0))
    fill.visible_camera = False
    build_variants(v_cols, lamp_pos)
    build_cameras(c_cam, crt_center, tv_center)
    build_markers(c_char)
    setup_world()
    setup_render()
    setup_compositor()
    bpy.data.texts.new("LEIA-ME").write(README_TEXT)

    var_layer = bpy.context.view_layer.layer_collection.children["04_VARIANTES"]
    for i, c in enumerate(v_cols):
        var_layer.children[c.name].exclude = i != 0
    scn.frame_set(1)
    out = os.path.abspath(args.out)
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    print(f"> guardado: {out}")
    if args.render:
        render_previews(args, v_cols)


PREVIEWS = [
    ("cam1_frente_apresentador", "CAM_1_Frente_Apresentador", 0, 1),
    ("cam2_lado_perfil", "CAM_2_Lado_Perfil", 0, 1),
    ("cam3_plano_geral", "CAM_3_Plano_Geral", 0, 1),
    ("cam4_insert_ecra_crt", "CAM_4_Insert_Ecra_CRT", 0, 1),
    ("cam5_insert_quadro", "CAM_5_Insert_Quadro", 0, 1),
    ("cam6_insert_provas", "CAM_6_Insert_Provas", 0, 1),
    ("cam7_por_cima_ombro", "CAM_7_Por_Cima_Ombro", 0, 1),
    ("cam8_tv_fundo_analise", "CAM_8_TV_Fundo_Analise", 0, 1),
    ("cam1_var2_so_ecras", "CAM_1_Frente_Apresentador", 1, 1),
    ("cam3_var3_relampago", "CAM_3_Plano_Geral", 2, 61),
]


def render_previews(args, v_cols):
    scn = bpy.context.scene
    os.makedirs(args.render, exist_ok=True)
    scn.cycles.samples = args.samples
    scn.cycles.adaptive_threshold = 0.05
    scn.render.resolution_x = args.res
    scn.render.resolution_y = int(args.res * 9 / 16)
    scn.render.image_settings.file_format = "JPEG"
    scn.render.image_settings.quality = 90
    var_layer = bpy.context.view_layer.layer_collection.children["04_VARIANTES"]
    only = set(filter(None, args.only.split(",")))
    for fname, cam, var, frame in PREVIEWS:
        if only and fname not in only:
            continue
        for i, c in enumerate(v_cols):
            var_layer.children[c.name].exclude = i != var
        scn.camera = bpy.data.objects[cam]
        scn.frame_set(frame)
        scn.render.filepath = os.path.join(os.path.abspath(args.render), fname + ".jpg")
        print(f"> render {fname}")
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
