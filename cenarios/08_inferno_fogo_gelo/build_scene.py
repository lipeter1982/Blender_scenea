"""
Cenário 08 — Inferno: fogo e gelo (estilo Tim Burton)

Descida pelos círculos, inspirada em Dante: as Portas do Inferno (arco gigante e torcido,
com a inscrição), a descida entre fendas de lava, gaiolas penduradas, um relógio parado às
3:33 e uma placa de boas-vindas derretida; o rio Aqueronte com o barco de Caronte à espera;
um abismo com lava no fundo, atravessado por uma ponte de pedra estreita e torta; uma
colina em espiral enrolada sobre o abismo e, ao fundo, a Cidade de Dis em silhueta.

Duas versões com a MESMA geometria, trocadas por um único interruptor (propriedade
"gelo" da cena: 0 = Brasas, 1 = Gelo):
  Brasas — lava, fumo iluminado por baixo, fagulhas e cinza a cair.
  Gelo   — o Cocito: lava apagada e gelada, geada, nevoeiro azul, neve; o único calor é a
           lanterna de Caronte. As chamas dos braseiros ficam congeladas.

Uso (dentro do Blender):
    blender -b -P build_scene.py -- --out inferno_fogo_gelo.blend
Uso (módulo bpy via pip):
    python build_scene.py --out inferno_fogo_gelo.blend --render previews --samples 64
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

SEED = 666
rng = random.Random(SEED)

X_HALF = 42.0                                # terreno detalhado: x ∈ [-42, 42]
Y_MIN, Y_MAX = -50.0, 46.0                   #                    y ∈ [-50, 46]
GATE_Y = -28.0                               # Portas do Inferno
GATE_H = 13.0
PATH_CTRL = [(0.0, -52.0), (0.0, -34.0), (0.3, -27.0), (-1.6, -21.5), (1.8, -16.0), (-0.8, -12.0), (-5.0, -9.4)]
PATH2_CTRL = [(-2.2, -1.3), (-0.3, 1.2), (1.2, 3.6)]    # da outra margem do rio até à ponte
RIVER_Z = -4.4                               # superfície do Aqueronte
LAVA_Z = -29.0                               # lava no fundo do abismo
DIS_DIR = Vector((0.0, 1.0, 0.0))
SUN_BRASAS = Vector((0.15, -1.0, -0.12)).normalized()    # contraluz vermelho, rasante, vindo de Dis
SUN_GELO = Vector((-0.3, -0.7, -0.65)).normalized()      # luz pálida de céu encoberto


def smooth(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


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


PATH = catmull(PATH_CTRL, 10)
PATH2 = catmull(PATH2_CTRL, 8)


def poly_dist(poly, x, y):
    best = 1e9
    p = Vector((x, y, 0))
    for a, b in zip(poly[:-1], poly[1:]):
        ab = b - a
        t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-9)))
        best = min(best, (p - (a + ab * t)).length)
    return best


def path_dist(x, y):
    if abs(x) > 12 or y > 8:
        return 99.0
    return min(poly_dist(PATH, x, y), poly_dist(PATH2, x, y))


def river_y(x):
    return -4.5 + 1.5 * math.sin(0.08 * x)


def abyss_y(x):
    return 11.0 + 1.2 * math.sin(0.06 * x + 1.0)


def abyss_hw(x):
    return 5.0 + 0.9 * noise.noise(Vector((x * 0.15, 3.3, 0.7)))


def ground_height(x, y):
    base = -3.0 * smooth(-28.0, -9.0, y) + 9.0 * smooth(16.0, 48.0, y)
    n = noise.noise(Vector((x * 0.05, y * 0.05, 0.4))) * 0.9
    n += noise.noise(Vector((x * 0.22, y * 0.22, 2.2))) * 0.25
    n += noise.noise(Vector((x * 0.9, y * 0.9, 4.1))) * 0.05
    pd = path_dist(x, y)
    n *= 0.35 + 0.65 * smooth(1.2, 4.0, pd)
    if abs(y - GATE_Y) < 6 and abs(x) < 9:          # plataforma das portas, mais plana
        n *= 0.3 + 0.7 * smooth(3.0, 6.0, max(abs(y - GATE_Y), abs(x) - 3))
    h = base + n
    # rio Aqueronte: um canal de margens suaves
    dr = abs(y - river_y(x))
    h -= 1.9 * (1 - smooth(2.2, 3.4, dr))
    # abismo: paredes quase verticais com rebordo recortado
    da = abs(y - abyss_y(x))
    hw = abyss_hw(x) + 0.45 * noise.noise(Vector((x * 0.6, y * 0.6, 5.0)))
    t = 1 - smooth(hw - 1.3, hw + 0.3, da)
    if t > 0:
        floor = -32.0 + 2.5 * noise.noise(Vector((x * 0.1, y * 0.1, 7.0)))
        ledge = 1.6 * noise.noise(Vector((x * 0.35, y * 0.2, 9.0)))
        h = h * (1 - t) + (floor + ledge * (1 - t)) * t
    return h


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="inferno_fogo_gelo.blend")
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



def spline(cu, pts, radii):
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for i, (p, r) in enumerate(zip(pts, radii)):
        sp.points[i].co = (*p, 1)
        sp.points[i].radius = r
    return sp


def new_curve(name, bevel, res=2, caps=True):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = bevel
    cu.bevel_resolution = res
    cu.use_fill_caps = caps
    cu.resolution_u = 2
    return cu


def grow(start, direction, length, r0, r1, n, gnarl, r_, droop=0.0, up_bias=0.0):
    """Polilinha torta: a direção vai derivando com ruído (galho retorcido)."""
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


def curl_pts(p, d, R0, turns, n, r_):
    """Ponta enrolada em espiral (a assinatura Burton), a partir de p na direção d."""
    side = d.cross(Vector((0, 0, 1)))
    if side.length < 1e-3:
        side = Vector((1, 0, 0))
    side.normalize()
    up = side.cross(d)
    flip = 1 if r_.random() < 0.5 else -1
    pts = []
    for i in range(n):
        t = i / (n - 1)
        a = flip * t * turns * 2 * math.pi
        rr = R0 * (1 - 0.85 * t)
        pts.append(p + d * (math.sin(a) * rr) + up * ((1 - math.cos(a)) * rr * 0.9))
    return pts


def spiral(c, R, turns=2.2, r0=0.18, n=40, flip=1):
    pts = []
    for i in range(n):
        t = i / (n - 1)
        a = flip * t * turns * 2 * math.pi
        r = r0 * (1 - t * 0.85)
        pts.append(c + R @ Vector((math.cos(a) * r, 0, math.sin(a) * r)))
    return pts


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


# ---------------------------------------------------------------------------
# O interruptor Brasas / Gelo
# ---------------------------------------------------------------------------
# Tudo o que muda entre as versões lê a propriedade "gelo" da cena através de um nó
# Attribute do tipo View Layer (procura na view layer e depois na cena). Assim um único
# valor troca materiais, céu, nevoeiro, partículas e luzes, sem drivers nem scripts.
def gelo(m):
    if not hasattr(m, "_gelo"):
        m._gelo = m.node("ShaderNodeAttribute", attribute_type="VIEW_LAYER", attribute_name="gelo").outputs["Fac"]
    return m._gelo


def gelo_node(nt):
    n = nt.nodes.new("ShaderNodeAttribute")
    n.attribute_type = "VIEW_LAYER"
    n.attribute_name = "gelo"
    return n.outputs["Fac"]


def frost(m, col, rough, amount=1.0, up=0.3, scale=3.0):
    """Geada nas faces viradas para cima (só na versão Gelo)."""
    geo = m.node("ShaderNodeNewGeometry")
    sep = m.node("ShaderNodeSeparateXYZ")
    m.link(geo.outputs["Normal"], sep.inputs[0])
    top = m.maprange(sep.outputs["Z"], up, up + 0.45, 0.15, 1.0)
    patch = m.maprange(m.noise(m.texcoord().outputs["Object"], scale, 6.0, 0.6).outputs["Fac"], 0.36, 0.52)
    f = m.math("MULTIPLY", m.math("MULTIPLY", gelo(m), top), m.math("MULTIPLY", patch, amount))
    col = m.mix(f, col, (0.62, 0.7, 0.8))
    rough = m.mixf(f, rough, 0.4)
    return col, rough, f


# ---------------------------------------------------------------------------
# Materiais
# ---------------------------------------------------------------------------
def mat_basalt(name, tone=1.0, cracks=False, crack_scale=0.25, ash=0.5, glow=3.0):
    """Basalto negro com cinza clara; com cracks=True tem fendas de lava (Brasas) ou gelo azul (Gelo)."""
    m = Mat(name)
    obj = m.texcoord().outputs["Object"]
    k = tone
    n1 = m.noise(obj, 0.6, 6.0, 0.6)
    n2 = m.noise(obj, 7.0, 8.0, 0.65)
    g = m.math("ADD", m.math("MULTIPLY", n1.outputs["Fac"], 0.55), m.math("MULTIPLY", n2.outputs["Fac"], 0.45))
    col = m.ramp(g, [(0.3, (0.012 * k, 0.011 * k, 0.012 * k)), (0.55, (0.035 * k, 0.032 * k, 0.033 * k)),
                     (0.8, (0.07 * k, 0.064 * k, 0.062 * k))]).outputs["Color"]
    ash_m = m.math("MULTIPLY", m.maprange(m.noise(obj, 0.35, 5.0, 0.6).outputs["Fac"], 0.5, 0.62), ash)
    col = m.mix(ash_m, col, (0.13 * k, 0.12 * k, 0.115 * k))
    rough = m.mixf(ash_m, 0.75, 0.95)
    h = m.math("ADD", n2.outputs["Fac"], m.math("MULTIPLY", n1.outputs["Fac"], 0.4))
    if cracks:
        v = m.node("ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE")
        v.inputs["Scale"].default_value = crack_scale
        warp = m.node("ShaderNodeVectorMath", operation="ADD")
        m.link(obj, warp.inputs[0])
        m.link(m.noise(obj, 0.8, 3.0, 0.5).outputs["Color"], warp.inputs[1])
        m.link(warp.outputs["Vector"], v.inputs["Vector"])
        line = m.maprange(v.outputs["Distance"], 0.0, 0.022, 1.0, 0.0)
        region = m.maprange(m.noise(obj, 0.07, 3.0, 0.5).outputs["Fac"], 0.54, 0.6)
        crack = m.math("MULTIPLY", line, region)
        g_ = gelo(m)
        col = m.mix(crack, col, m.mix(g_, (0.02, 0.004, 0.0), (0.5, 0.65, 0.78)))
        pulse = m.maprange(m.noise(obj, 1.5, 2.0, 0.5).outputs["Fac"], 0.3, 0.7, 0.4, 1.0)
        m.set("Emission Color", m.mix(g_, (1.0, 0.5, 0.09), (0.35, 0.75, 1.0)))
        m.set("Emission Strength", m.math("MULTIPLY", m.math("MULTIPLY", crack, pulse), m.mixf(g_, glow, 0.5)))
        h = m.math("SUBTRACT", h, m.math("MULTIPLY", crack, 0.8))
    col, rough, _ = frost(m, col, rough)
    m.set("Base Color", col)
    m.set("Roughness", rough)
    m.set("Normal", m.bump(h, 0.8, 0.04))
    return m.mat


def mat_gate_stone():
    """Pedra das Portas: mais clara (cor de osso sujo), com fuligem nas reentrâncias."""
    m = Mat("M_Pedra_Portas")
    obj = m.texcoord().outputs["Object"]
    n = m.noise(obj, 2.5, 8.0, 0.65)
    col = m.ramp(n.outputs["Fac"], [(0.3, (0.07, 0.062, 0.055)), (0.75, (0.2, 0.18, 0.16))]).outputs["Color"]
    soot = m.maprange(m.noise(obj, 0.9, 5.0, 0.6).outputs["Fac"], 0.45, 0.65)
    col = m.mix(m.math("MULTIPLY", soot, 0.8), col, (0.01, 0.009, 0.009))
    col, rough, _ = frost(m, col, 0.85, 1.0, 0.2, 5.0)
    m.set("Base Color", col)
    m.set("Roughness", rough)
    fine = m.noise(obj, 18.0, 8.0, 0.7)
    m.set("Normal", m.bump(m.math("ADD", fine.outputs["Fac"], n.outputs["Fac"]), 0.6, 0.02))
    return m.mat


def mat_lava_ice():
    """Lava (Brasas) ou gelo com fendas azuis (Gelo) — o rio e o fundo do abismo."""
    m = Mat("M_Lava_Gelo")
    obj = m.texcoord().outputs["Object"]
    g_ = gelo(m)
    mp = m.node("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, 1.6, 1.0)
    m.link(obj, mp.inputs["Vector"])
    warp = m.noise(mp.outputs["Vector"], 0.25, 3.0, 0.5)
    wv = m.node("ShaderNodeVectorMath", operation="ADD")
    m.link(mp.outputs["Vector"], wv.inputs[0])
    m.link(warp.outputs["Color"], wv.inputs[1])
    v = m.node("ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE")
    v.inputs["Scale"].default_value = 0.55
    m.link(wv.outputs["Vector"], v.inputs["Vector"])
    crust = m.maprange(v.outputs["Distance"], 0.02, 0.14)             # 1 = crosta, 0 = fenda incandescente
    flow = m.noise(wv.outputs["Vector"], 1.2, 6.0, 0.6).outputs["Fac"]
    molten = m.math("MULTIPLY", m.math("SUBTRACT", 1.0, crust), m.maprange(flow, 0.2, 0.7, 0.6, 1.0))
    open_lava = m.maprange(m.noise(obj, 0.12, 3.0, 0.5).outputs["Fac"], 0.42, 0.56)   # zonas sem crosta
    heat = m.math("MAXIMUM", molten, m.math("MULTIPLY", open_lava, m.maprange(flow, 0.3, 0.7, 0.5, 1.0)))
    lava_col = m.ramp(heat, [(0.0, (0.12, 0.02, 0.0)), (0.45, (0.9, 0.28, 0.02)), (0.8, (1.0, 0.58, 0.12)),
                             (1.0, (1.0, 0.82, 0.45))]).outputs["Color"]
    ice_line = m.maprange(v.outputs["Distance"], 0.0, 0.03, 1.0, 0.0)
    ice_col = m.ramp(flow, [(0.2, (0.12, 0.2, 0.28)), (0.8, (0.45, 0.58, 0.68))]).outputs["Color"]
    ice_col = m.mix(ice_line, ice_col, (0.8, 0.9, 1.0))
    m.set("Base Color", m.mix(g_, (0.015, 0.01, 0.01), ice_col))
    m.set("Roughness", m.mixf(g_, 0.85, m.mixf(ice_line, 0.06, 0.5)))
    m.set("Coat Weight", m.mixf(g_, 0.0, 0.6))
    m.set("Emission Color", m.mix(g_, lava_col, (0.3, 0.72, 1.0)))
    m.set("Emission Strength", m.mixf(g_, m.math("MULTIPLY", heat, 4.0), m.math("MULTIPLY", ice_line, 0.8)))
    m.set("Normal", m.bump(m.mixf(g_, crust, m.math("SUBTRACT", 1.0, ice_line)), 0.6, 0.05))
    return m.mat


def mat_fire_ice(name="M_Chama_Congelada"):
    """Chama (Brasas) que na versão Gelo fica congelada: cristal azul-pálido."""
    m = Mat(name)
    g_ = gelo(m)
    z = m.node("ShaderNodeSeparateXYZ")
    m.link(m.texcoord().outputs["Generated"], z.inputs[0])
    fire = m.ramp(z.outputs["Z"], [(0.0, (1.0, 0.68, 0.22)), (0.45, (1.0, 0.38, 0.05)), (1.0, (0.6, 0.1, 0.01))]).outputs["Color"]
    m.set("Base Color", m.mix(g_, (0.0, 0.0, 0.0), (0.6, 0.8, 0.92)))
    m.set("Roughness", m.mixf(g_, 1.0, 0.05))
    m.set("Transmission Weight", m.mixf(g_, 0.0, 0.85))
    m.set("Emission Color", m.mix(g_, fire, (0.35, 0.75, 1.0)))
    m.set("Emission Strength", m.mixf(g_, 0.8, 0.35))
    m.set("Specular IOR Level", m.mixf(g_, 0.0, 0.5))
    return m.mat


def mat_iron():
    m = Mat("M_Ferro_Negro")
    obj = m.texcoord().outputs["Object"]
    rust = m.maprange(m.noise(obj, 18.0, 8.0, 0.7).outputs["Fac"], 0.5, 0.68)
    col = m.mix(rust, (0.012, 0.012, 0.014), (0.07, 0.025, 0.012))
    col, rough, f = frost(m, col, m.mixf(rust, 0.45, 0.9), 1.0, 0.1, 12.0)
    m.set("Base Color", col)
    m.set("Metallic", m.mixf(f, m.mixf(rust, 0.85, 0.2), 0.0))
    m.set("Roughness", rough)
    return m.mat


def mat_charred():
    """Madeira carbonizada: pele de crocodilo negra; nas Brasas as gretas ainda estão em brasa."""
    m = Mat("M_Madeira_Carbonizada")
    obj = m.texcoord().outputs["Object"]
    mp = m.node("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (4.0, 4.0, 1.4)
    m.link(obj, mp.inputs["Vector"])
    v = m.node("ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE")
    v.inputs["Scale"].default_value = 3.0
    m.link(mp.outputs["Vector"], v.inputs["Vector"])
    line = m.maprange(v.outputs["Distance"], 0.0, 0.05, 1.0, 0.0)
    col = m.mix(line, (0.012, 0.01, 0.009), (0.002, 0.001, 0.001))
    ember = m.math("MULTIPLY", line, m.maprange(m.noise(obj, 1.2, 3.0, 0.5).outputs["Fac"], 0.6, 0.68))
    g_ = gelo(m)
    col, rough, _ = frost(m, col, 0.9, 1.0, 0.3, 6.0)
    m.set("Base Color", col)
    m.set("Roughness", rough)
    m.set("Emission Color", (1.0, 0.22, 0.03))
    m.set("Emission Strength", m.math("MULTIPLY", ember, m.mixf(g_, 1.5, 0.0)))
    m.set("Normal", m.bump(m.math("SUBTRACT", 1.0, line), 0.9, 0.02))
    return m.mat


def mat_windows():
    """Janelas de Dis: fornalhas nas Brasas, quase apagadas e frias no Gelo."""
    m = Mat("M_Janelas_Dis")
    rnd = m.node("ShaderNodeObjectInfo").outputs["Random"]
    g_ = gelo(m)
    fl = m.maprange(m.noise(m.texcoord().outputs["Object"], 0.3, 2.0, 0.5).outputs["Fac"], 0.3, 0.7, 0.5, 1.3)
    m.set("Base Color", (0.0, 0.0, 0.0))
    m.set("Emission Color", m.mix(g_, (1.0, 0.32, 0.06), (0.45, 0.7, 1.0)))
    m.set("Emission Strength", m.mixf(g_, m.math("MULTIPLY", fl, 18.0), m.math("MULTIPLY", rnd, 0.6)))
    return m.mat


def mat_letters():
    """Letras da inscrição: gravadas a fogo (Brasas) / cheias de gelo (Gelo)."""
    m = Mat("M_Inscricao")
    g_ = gelo(m)
    m.set("Base Color", m.mix(g_, (0.05, 0.01, 0.0), (0.7, 0.8, 0.9)))
    m.set("Roughness", 0.4)
    m.set("Emission Color", m.mix(g_, (1.0, 0.3, 0.05), (0.4, 0.75, 1.0)))
    m.set("Emission Strength", m.mixf(g_, 6.0, 0.6))
    return m.mat


def mat_robe():
    m = Mat("M_Manto_Caronte")
    obj = m.texcoord().outputs["Object"]
    n = m.noise(obj, 6.0, 6.0, 0.6)
    col = m.ramp(n.outputs["Fac"], [(0.3, (0.004, 0.004, 0.005)), (0.7, (0.02, 0.018, 0.02))]).outputs["Color"]
    col, rough, _ = frost(m, col, 0.8, 0.7, 0.4, 8.0)
    m.set("Base Color", col)
    m.set("Roughness", rough)
    m.set("Sheen Weight", 0.12)
    return m.mat


def mat_show_only(name, gelo_on, color, emit=0.0, emit_color=(1, 1, 1)):
    """Material que só aparece numa das versões (transparente na outra)."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new
    out = N("ShaderNodeOutputMaterial")
    if emit:
        sh = N("ShaderNodeEmission")
        sh.inputs["Color"].default_value = (*emit_color, 1)
        sh.inputs["Strength"].default_value = emit
    else:
        sh = N("ShaderNodeBsdfPrincipled")
        sh.inputs["Base Color"].default_value = (*color, 1)
        sh.inputs["Roughness"].default_value = 0.6
    tr = N("ShaderNodeBsdfTransparent")
    mix = N("ShaderNodeMixShader")
    g = gelo_node(nt)
    if gelo_on:
        L(g, mix.inputs[0])
        L(tr.outputs[0], mix.inputs[1])
        L(sh.outputs[0], mix.inputs[2])
    else:
        L(g, mix.inputs[0])
        L(sh.outputs[0], mix.inputs[1])
        L(tr.outputs[0], mix.inputs[2])
    L(mix.outputs[0], out.inputs["Surface"])
    return mat


def mat_icicles():
    """Sincelos: só existem na versão Gelo."""
    mat = bpy.data.materials.new("M_Sincelos")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new
    out = N("ShaderNodeOutputMaterial")
    ice = N("ShaderNodeBsdfPrincipled")
    ice.inputs["Base Color"].default_value = (0.7, 0.85, 0.95, 1)
    ice.inputs["Roughness"].default_value = 0.08
    ice.inputs["Transmission Weight"].default_value = 0.7
    ice.inputs["Emission Color"].default_value = (0.35, 0.7, 1.0, 1)
    ice.inputs["Emission Strength"].default_value = 0.15
    tr = N("ShaderNodeBsdfTransparent")
    mix = N("ShaderNodeMixShader")
    L(gelo_node(nt), mix.inputs[0])
    L(tr.outputs[0], mix.inputs[1])
    L(ice.outputs[0], mix.inputs[2])
    L(mix.outputs[0], out.inputs["Surface"])
    return mat


def mat_atmosphere():
    """Fumo (Brasas) / névoa (Gelo): neblina geral, névoa baixa sobre o rio e fumo espesso a subir do abismo."""
    mat = bpy.data.materials.new("M_Atmosfera")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new
    out = N("ShaderNodeOutputMaterial")
    vol = N("ShaderNodeVolumePrincipled")
    vol.inputs["Anisotropy"].default_value = 0.35
    g = gelo_node(nt)

    def mr(val, a, b, c=0.0, d=1.0):
        n = N("ShaderNodeMapRange")
        L(val, n.inputs["Value"])
        n.inputs["From Min"].default_value, n.inputs["From Max"].default_value = a, b
        n.inputs["To Min"].default_value, n.inputs["To Max"].default_value = c, d
        return n.outputs["Result"]

    def op(kind, a, b):
        n = N("ShaderNodeMath")
        n.operation = kind
        for i, v in enumerate((a, b)):
            if isinstance(v, bpy.types.NodeSocket):
                L(v, n.inputs[i])
            else:
                n.inputs[i].default_value = v
        return n.outputs[0]

    def mixf(fac, a, b):
        n = N("ShaderNodeMix")
        n.data_type = "FLOAT"
        L(fac, sock(n, "Factor_Float"))
        sock(n, "A_Float").default_value = a
        sock(n, "B_Float").default_value = b
        return sock(n, "Result_Float", out=True)

    geo = N("ShaderNodeNewGeometry")
    sep = N("ShaderNodeSeparateXYZ")
    L(geo.outputs["Position"], sep.inputs[0])
    z = sep.outputs["Z"]
    mp = N("ShaderNodeMapping")
    mp.name = "Deriva_Fumo"
    mp.inputs["Scale"].default_value = (0.08, 0.08, 0.2)
    L(geo.outputs["Position"], mp.inputs["Vector"])
    nz = N("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 1.0
    nz.inputs["Detail"].default_value = 4.0
    L(mp.outputs["Vector"], nz.inputs["Vector"])
    patch = mr(nz.outputs["Fac"], 0.35, 0.7, 0.15, 1.3)
    low = op("MULTIPLY", op("POWER", mr(z, -4.6, -0.5, 1.0, 0.0), 1.6), patch)     # névoa baixa (rio, planalto baixo)
    deep = op("MULTIPLY", op("POWER", mr(z, -30.0, -4.0, 1.0, 0.0), 1.3), patch)   # fumo do abismo
    dens = op("ADD", op("ADD", mixf(g, 0.0018, 0.005), op("MULTIPLY", low, mixf(g, 0.03, 0.09))),
              op("MULTIPLY", deep, mixf(g, 0.01, 0.005)))
    L(dens, vol.inputs["Density"])
    cm = N("ShaderNodeMix")
    cm.data_type = "RGBA"
    L(g, sock(cm, "Factor_Float"))
    sock(cm, "A_Color").default_value = (0.42, 0.36, 0.35, 1)
    sock(cm, "B_Color").default_value = (0.8, 0.86, 0.95, 1)
    L(sock(cm, "Result_Color", out=True), vol.inputs["Color"])
    L(vol.outputs[0], out.inputs["Volume"])
    mp.inputs["Location"].default_value = (0, 0, 0)
    mp.inputs["Location"].keyframe_insert("default_value", frame=1)
    mp.inputs["Location"].default_value = (0.05, 0.1, -0.5)     # o fumo sobe devagar
    mp.inputs["Location"].keyframe_insert("default_value", frame=240)
    return mat


# ---------------------------------------------------------------------------
# Terreno, rio, abismo, caminho
# ---------------------------------------------------------------------------
def grid_mesh(name, x0, x1, y0, y1, step, zfn):
    xs = np.arange(x0, x1 + 1e-6, step)
    ys = np.arange(y0, y1 + 1e-6, step)
    nx = len(xs)
    verts = [(x, y, zfn(x, y)) for y in ys for x in xs]
    faces = [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i) for j in range(len(ys) - 1) for i in range(nx - 1)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.shade_smooth()
    return me


def build_terrain(col, mat):
    me = grid_mesh("Terreno", -X_HALF, X_HALF, Y_MIN, Y_MAX, 0.35, ground_height)
    me.materials.append(mat)
    ob = new_object("Terreno_Inferno", me, col)

    def outer(x, y):   # anel distante, mais grosseiro; por baixo do terreno detalhado
        inside = abs(x) < X_HALF - 0.1 and Y_MIN + 0.1 < y < Y_MAX - 0.1
        return ground_height(x, y) - (0.5 if inside else 0.0)

    me2 = grid_mesh("Terreno_Distante", -160, 160, -120, 170, 2.0, outer)
    me2.materials.append(mat)
    new_object("Terreno_Distante", me2, col)
    return ob


def build_lava(col, mat):
    for name, y0, y1, z in (("Lava_Abismo", -2.0, 26.0, LAVA_Z), ("Rio_Aqueronte", -10.0, 1.0, RIVER_Z)):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=64, y_segments=8, size=1.0,
                              matrix=Matrix.Translation((0, (y0 + y1) / 2, z)) @ Matrix.Diagonal((160, (y1 - y0) / 2, 1, 1)))
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mat)
        new_object(name, me, col)


def build_path_stones(col, mat):
    """Lajes irregulares ao longo do caminho, das portas até ao cais, e da outra margem até à ponte."""
    b = Builder()
    r_ = random.Random(5)
    for poly in (PATH, PATH2):
        cum = [0.0]
        for a, c in zip(poly[:-1], poly[1:]):
            cum.append(cum[-1] + (c - a).length)
        s = 0.3
        while s < cum[-1]:
            j = next(k for k in range(1, len(cum)) if cum[k] >= s)
            t = (s - cum[j - 1]) / max(cum[j] - cum[j - 1], 1e-6)
            p = poly[j - 1].lerp(poly[j], t)
            tng = (poly[j] - poly[j - 1]).normalized()
            side = Vector((-tng.y, tng.x, 0))
            for k in range(r_.randint(2, 3)):
                if r_.random() < 0.1:
                    continue
                q = p + side * r_.uniform(-0.9, 0.9) + tng * r_.uniform(-0.2, 0.2)
                sz = r_.uniform(0.45, 0.85)
                yaw = r_.uniform(0, math.pi)
                gz = ground_height(q.x, q.y)
                dx = ground_height(q.x + 0.3, q.y) - ground_height(q.x - 0.3, q.y)
                dy = ground_height(q.x, q.y + 0.3) - ground_height(q.x, q.y - 0.3)
                nrm = Vector((-dx / 0.6, -dy / 0.6, 1)).normalized()
                u = Vector((math.cos(yaw), math.sin(yaw), 0))
                u = (u - nrm * u.dot(nrm)).normalized()
                v = nrm.cross(u)
                tilt = Vector((r_.gauss(0, 0.05), r_.gauss(0, 0.05), 0))
                b.box((q.x, q.y, gz + 0.02), (u, v, nrm + tilt), (sz, sz * r_.uniform(0.6, 1.0), 0.14))
            s += r_.uniform(0.75, 0.95)
    ob = b.to_object("Caminho_Lajes", col, [mat])
    bv = ob.modifiers.new("Bevel", "BEVEL")
    bv.width = 0.04
    bv.segments = 2
    return ob


# ---------------------------------------------------------------------------
# Portas do Inferno
# ---------------------------------------------------------------------------
def gate_axis(n=60):
    """Eixo das Portas: pilar esquerdo → ogiva torta → pilar direito (alongado, Burton)."""
    pts = []
    y = GATE_Y
    for i in range(n + 1):
        t = i / n
        s = 2 * t - 1                              # -1 … 1
        side = -1 if s < 0 else 1
        a = abs(s)
        if a > 0.42:                               # pilares, a inclinar para dentro
            k = (a - 0.42) / 0.58                  # 1 na base
            x = side * (3.3 + 0.6 * k ** 1.5)
            z = 8.2 * (1 - k)
        else:                                      # ogiva
            k = a / 0.42
            x = side * 3.3 * math.sin(k * math.pi / 2) ** 0.8
            z = 8.2 + (GATE_H - 8.2) * (1 - k ** 1.7)
        x += 0.35 * math.sin(3.0 * s + 0.5)        # nada está direito
        pts.append(Vector((x, y + 0.25 * math.sin(4 * s), z - 0.3)))
    return pts


def build_gate(col, stone, iron, letters, icicle_mat):
    axis = gate_axis()
    n = len(axis)
    # núcleo + 3 cordões entrançados à volta do eixo
    cu = new_curve("Portas_Cordoes", 1.0, 3)
    rad = [0.75 - 0.35 * (1 - abs(2 * i / (n - 1) - 1)) for i in range(n)]
    spline(cu, axis, rad)
    for k in range(3):
        pts, rr = [], []
        for i, p in enumerate(axis):
            t = i / (n - 1)
            tng = (axis[min(i + 1, n - 1)] - axis[max(i - 1, 0)]).normalized()
            nrm = tng.cross(Vector((0, 1, 0))).normalized()
            bi = tng.cross(nrm)
            a = 2 * math.pi * (k / 3 + t * 5.0)
            R = rad[i] * 0.95
            pts.append(p + nrm * math.cos(a) * R + bi * math.sin(a) * R)
            rr.append(rad[i] * 0.42)
        spline(cu, pts, rr)
    # cornos em espiral no topo e nos ombros
    r_ = random.Random(66)
    apex = max(axis, key=lambda p: p.z)
    for sx in (-1, 1):
        d = Vector((sx * 0.8, 0, 0.6)).normalized()
        base = apex + Vector((sx * 0.3, 0, 0.2))
        stem, sr = grow(base, d, 2.2, 0.35, 0.18, 8, 0.05, r_, up_bias=0.1)
        spline(cu, stem, sr)
        cp = curl_pts(stem[-1], (stem[-1] - stem[-2]).normalized(), 0.9, 1.8, 30, r_)
        spline(cu, cp, [0.18 * (1 - i / 30) + 0.02 for i in range(30)])
    for p in (axis[int(n * 0.26)], axis[int(n * 0.74)]):
        sx = 1 if p.x > 0 else -1
        stem, sr = grow(p, Vector((sx, -0.2, 0.5)), 1.5, 0.28, 0.14, 6, 0.05, r_)
        spline(cu, stem, sr)
        cp = curl_pts(stem[-1], (stem[-1] - stem[-2]).normalized(), 0.6, 1.6, 26, r_)
        spline(cu, cp, [0.14 * (1 - i / 26) + 0.02 for i in range(26)])
    cu.materials.append(stone)
    new_object("Portas_do_Inferno", cu, col)
    # plintos
    b = Builder()
    for sx in (-1, 1):
        x = axis[0].x if sx < 0 else axis[-1].x
        gz = ground_height(x, GATE_Y)
        b.box((x, GATE_Y, gz + 0.4), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (2.2, 2.2, 1.2))
        b.box((x, GATE_Y, gz + 1.1), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (1.8, 1.8, 0.3))
    # lintel com a inscrição, ligeiramente torto
    M = Matrix.Translation((0.1, GATE_Y - 0.1, 8.3)) @ Euler((0, math.radians(-2.5), 0)).to_matrix().to_4x4()
    b.box((0, 0, 0), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (8.4, 0.5, 1.5), M=M)
    b.box((0, 0, -0.85), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (8.8, 0.62, 0.22), M=M)
    b.box((0, 0, 0.85), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (8.8, 0.62, 0.22), M=M)
    ob = b.to_object("Portas_Lintel_Plintos", col, [stone])
    ob.modifiers.new("Bevel", "BEVEL").width = 0.03
    for i, line in enumerate(("DEIXAI TODA A ESPERANÇA,", "VÓS QUE ENTRAIS")):
        td = bpy.data.curves.new(f"Inscricao_{i}", "FONT")
        td.body = line
        td.align_x = "CENTER"
        td.align_y = "CENTER"
        td.size = 0.4 if i == 0 else 0.37
        td.extrude = 0.025
        td.space_character = 1.08
        to = new_object(f"Inscricao_{i + 1}", td, col)
        to.matrix_world = M @ Matrix.Translation((0, -0.27, 0.3 - i * 0.6)) @ Euler((math.pi / 2, 0, 0)).to_matrix().to_4x4()
        td.materials.append(letters)
    # correntes penduradas do lintel
    cb = Builder()
    for x, ln in ((-3.0, 2.4), (-1.3, 3.8), (0.9, 1.6), (2.7, 3.0)):
        top = M @ Vector((x, 0, -0.95))
        k = 0
        z = 0.0
        while z < ln:
            rot = Euler((0, 0, (k % 2) * math.pi / 2)).to_matrix()
            cb.ring(top - Vector((0, 0, z + 0.07)), rot, 0.06, 0.017, 1.5, 12, 6)
            z += 0.155
            k += 1
        # gancho em espiral na ponta
        c = top - Vector((0, 0, z + 0.15))
        for i in range(10):
            a = i * 0.6
            cb.cylinder(c + Vector((0.08 * math.sin(a), 0, -0.08 * math.cos(a))),
                        c + Vector((0.08 * math.sin(a + 0.6), 0, -0.08 * math.cos(a + 0.6))), 0.018, 0.018, 6)
    cb.to_object("Portas_Correntes", col, [iron], smooth=True)
    # sincelos no lintel (só no Gelo)
    ib = Builder()
    r2 = random.Random(9)
    for i in range(34):
        x = r2.uniform(-4.2, 4.2)
        p = M @ Vector((x, r2.uniform(-0.28, 0.28), -0.96))
        ib.cylinder(p, p - Vector((0, 0, r2.uniform(0.15, 0.9))), r2.uniform(0.03, 0.07), 0.0, 6)
    ib.to_object("Portas_Sincelos", col, [icicle_mat], smooth=True)
    return M


def build_brazier(col, name, pos, iron, fire_mat):
    """Braseiro alto de ferro com pé em espiral; nas Brasas arde, no Gelo a chama está congelada."""
    gz = ground_height(pos.x, pos.y)
    base = Vector((pos.x, pos.y, gz))
    cu = new_curve(name + "_Pe", 0.04, 2)
    r_ = random.Random(int(pos.x * 10) + 3)
    for k in range(3):
        pts = []
        for i in range(30):
            t = i / 29
            a = 2 * math.pi * (k / 3 + t * 1.2)
            r = 0.35 * (1 - t) + 0.06
            pts.append(base + Vector((math.cos(a) * r, math.sin(a) * r, t * 2.6)))
        spline(cu, pts, [1.0] * 30)
    for k in range(3):
        a = 2 * math.pi * k / 3
        spline(cu, spiral(base + Vector((math.cos(a) * 0.45, math.sin(a) * 0.45, 0.25)),
                          Matrix.Rotation(a + math.pi / 2, 3, "Z"), 1.6, 0.2, 30), [0.8] * 30)
    cu.materials.append(iron)
    new_object(name + "_Pe", cu, col)
    b = Builder()
    top = base + Vector((0, 0, 2.6))
    b.cylinder(top, top + Vector((0, 0, 0.45)), 0.18, 0.62, 12)
    b.cylinder(top + Vector((0, 0, 0.45)), top + Vector((0, 0, 0.52)), 0.66, 0.66, 12)
    b.to_object(name + "_Taca", col, [iron])
    # chama: línguas torcidas com pontas enroladas
    fc = new_curve(name + "_Chama", 1.0, 3)
    for k in range(5):
        a = 2 * math.pi * k / 5 + r_.uniform(-0.3, 0.3)
        st = top + Vector((math.cos(a) * 0.3, math.sin(a) * 0.3, 0.4))
        pts, rr = grow(st, Vector((math.cos(a) * 0.15, math.sin(a) * 0.15, 1)), r_.uniform(1.2, 2.2), 0.24, 0.04, 8, 0.12, r_)
        cp = curl_pts(pts[-1], (pts[-1] - pts[-2]).normalized(), 0.18, 1.3, 14, r_)
        spline(fc, pts + cp[1:], rr + [0.04 * (1 - i / 14) + 0.005 for i in range(1, 14)])
    fc.materials.append(fire_mat)
    new_object(name + "_Chama", fc, col)
    return top + Vector((0, 0, 1.2))


# ---------------------------------------------------------------------------
# Adereços da descida: relógio, placa, gaiolas
# ---------------------------------------------------------------------------
def build_clock(col, wood, face_mat, iron, icicle_mat, pos):
    """Relógio de pé alongadíssimo, meio enterrado e torto, parado às 3:33."""
    gz = ground_height(pos.x, pos.y)
    M = Matrix.Translation((pos.x, pos.y, gz - 0.5)) @ Euler((math.radians(-12), math.radians(9), math.radians(24))).to_matrix().to_4x4()
    b = Builder()
    b.box((0, 0, 1.3), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.55, 0.42, 2.6), M=M)          # corpo
    b.box((0, 0, 2.95), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.8, 0.5, 0.75), M=M)          # caixa do mostrador
    roof = [(-0.46, 0.0), (0.46, 0.0), (0.0, 1.1)]
    b.prism(roof, lambda s, z: M @ Vector((s, -0.27, 3.32 + z)), M.to_3x3() @ Vector((0, 0.54, 0)))
    ob = b.to_object("Relogio_333", col, [wood])
    ob.modifiers.new("Bevel", "BEVEL").width = 0.015
    # espiral no topo
    cu = new_curve("Relogio_Espiral", 0.025)
    spline(cu, spiral(M @ Vector((0, -0.27, 4.6)), M.to_3x3(), 1.8, 0.22, 36), [1.0] * 36)
    cu.materials.append(iron)
    new_object("Relogio_Espiral", cu, col)
    # mostrador, ponteiros (3:33) e pêndulo parado
    fb = Builder()
    c = M @ Vector((0, -0.26, 2.95))
    R = M.to_3x3()
    fb.cylinder(c, c + R @ Vector((0, -0.02, 0)), 0.3, 0.3, 24)
    fb.to_object("Relogio_Mostrador", col, [face_mat])
    hb = Builder()
    for ang, ln, w in (((3 + 33 / 60) * 30, 0.17, 0.022), (33 * 6, 0.26, 0.014)):
        a = math.radians(ang)
        d = R @ Vector((math.sin(a), 0, math.cos(a)))
        p0 = c + R @ Vector((0, -0.035, 0))
        hb.box(p0 + d * ln / 2, (d, R @ Vector((0, 1, 0)), d.cross(R @ Vector((0, 1, 0)))), (ln, 0.01, w))
    for h in range(12):
        a = math.radians(h * 30)
        d = R @ Vector((math.sin(a), 0, math.cos(a)))
        p = c + R @ Vector((0, -0.03, 0)) + d * 0.25
        hb.box(p, (d, R @ Vector((0, 1, 0)), d.cross(R @ Vector((0, 1, 0)))), (0.05, 0.01, 0.012))
    hb.cylinder(c + R @ Vector((0, -0.24, -0.45)), c + R @ Vector((0.05, -0.24, -1.6)), 0.012, 0.012, 6)
    hb.cylinder(c + R @ Vector((0.05, -0.26, -1.6)), c + R @ Vector((0.05, -0.2, -1.6)), 0.11, 0.11, 16)
    hb.to_object("Relogio_Ponteiros_333", col, [iron])
    ib = Builder()
    for i in range(9):
        p = M @ Vector((rng.uniform(-0.4, 0.4), -0.27, 3.3))
        ib.cylinder(p, p - Vector((0, 0, rng.uniform(0.1, 0.4))), 0.025, 0.0, 6)
    ib.to_object("Relogio_Sincelos", col, [icicle_mat], smooth=True)
    return M @ Vector((0, 0, 4.4))


def build_welcome_sign(col, wood, board, ink, pos):
    """Placa "BEM-VINDO" derretida pelo calor (humor macabro)."""
    gz = ground_height(pos.x, pos.y)
    base = Vector((pos.x, pos.y, gz))
    b = Builder()
    b.cylinder(base - Vector((0, 0, 0.3)), base + Vector((0.2, 0.05, 3.1)), 0.07, 0.05, 8)
    b.to_object("Placa_Poste", col, [wood])
    root = new_object("Placa_Derretida", None, col)
    root.location = base + Vector((0.2, 0.05, 2.75))
    root.rotation_euler = (0, math.radians(8), math.radians(20))
    bb = Builder()
    bb.box((0.9, 0, 0), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (2.1, 0.06, 0.8))
    for i in range(7):                                   # escorridos
        x = rng.uniform(0.05, 1.9)
        ln = rng.uniform(0.15, 0.7)
        bb.cylinder((x, 0, -0.38), (x, 0, -0.38 - ln), 0.05, 0.025, 8)
        bb.ico((x, 0, -0.38 - ln), 0.04, (1, 1, 1.3), 1, 0.0)
    bo = bb.to_object("Placa_Tabua", col, [board], smooth=True)
    bo.parent = root
    sub = bo.modifiers.new("Subdivisao", "SUBSURF")
    sub.levels = sub.render_levels = 1
    texts = []
    for i, (line, size, z) in enumerate((("BEM-VINDO", 0.3, 0.1), ("pedimos desculpa pelo calor", 0.1, -0.22))):
        td = bpy.data.curves.new(f"Placa_Texto_{i}", "FONT")
        td.body = line
        td.align_x = "CENTER"
        td.align_y = "CENTER"
        td.size = size
        td.extrude = 0.004
        to = new_object(f"Placa_Texto_{i + 1}", td, col)
        to.parent = root
        to.location = (0.9, -0.035, z)
        to.rotation_euler = (math.pi / 2, 0, 0)
        td.materials.append(ink)
        texts.append(to)
    # derreter: dobrar a placa e o texto para baixo (Simple Deform à volta de um eixo comum)
    pivot = new_object("Placa_Eixo_Derreter", None, col)
    pivot.parent = root
    pivot.location = (0.1, 0, 0)
    pivot.rotation_euler = (0, math.radians(90), math.radians(90))
    for o in [bo] + texts:
        sd = o.modifiers.new("Derreter", "SIMPLE_DEFORM")
        sd.deform_method = "BEND"
        sd.angle = math.radians(-35)
        sd.origin = pivot
        sd.deform_axis = "Z"
    return root


def build_gibbet(col, iron, name, pos, yaw, chain_len, r_):
    """Forca alta e torta com braço em espiral e uma gaiola pendurada."""
    gz = ground_height(pos.x, pos.y)
    base = Vector((pos.x, pos.y, gz - 0.3))
    R = Matrix.Rotation(yaw, 3, "Z")
    cu = new_curve(name + "_Poste", 1.0, 2)
    H = r_.uniform(5.2, 6.4)
    post, pr = grow(base, Vector((0, 0, 1)), H, 0.14, 0.09, 10, 0.03, r_)
    spline(cu, post, pr)
    top = post[-1]
    arm_end = top + R @ Vector((1.8, 0, 0.35))
    spline(cu, [top, top + R @ Vector((0.9, 0, 0.3)), arm_end], [0.09, 0.08, 0.07])
    spline(cu, curl_pts(arm_end, (R @ Vector((1, 0, 0.2))).normalized(), 0.35, 1.6, 26, r_), [0.06 * (1 - i / 26) + 0.01 for i in range(26)])
    spline(cu, [post[6], top + R @ Vector((0.9, 0, 0.3))], [0.06, 0.05])
    cu.materials.append(iron)
    new_object(name + "_Poste", cu, col)
    b = Builder()
    hook = arm_end - Vector((0, 0, 0.05))
    z = 0.0
    k = 0
    while z < chain_len:
        b.ring(hook - Vector((0, 0, z + 0.06)), Euler((0, 0, (k % 2) * math.pi / 2)).to_matrix(), 0.05, 0.014, 1.5, 10, 6)
        z += 0.13
        k += 1
    b.to_object(name + "_Corrente", col, [iron], smooth=True)
    # gaiola em forma de cebola, alongada
    cc = new_curve(name + "_Gaiola", 0.013, 1)
    top_c = hook - Vector((0, 0, chain_len + 0.1))
    Hc, Rc = 1.9, 0.5
    for k in range(10):
        a = 2 * math.pi * k / 10
        pts = []
        for i in range(17):
            t = i / 16
            rr = Rc * math.sin(math.pi * t) ** 0.8 * (1 + 0.15 * math.sin(3 * math.pi * t))
            pts.append(top_c + Vector((math.cos(a) * rr, math.sin(a) * rr, -Hc * t)))
        spline(cc, pts, [1.0] * 17)
    for t in (0.2, 0.55, 0.85):
        rr = Rc * math.sin(math.pi * t) ** 0.8 * (1 + 0.15 * math.sin(3 * math.pi * t))
        spline(cc, [top_c + Vector((math.cos(2 * math.pi * i / 24) * rr, math.sin(2 * math.pi * i / 24) * rr, -Hc * t)) for i in range(25)],
               [1.3] * 25)
    spline(cc, spiral(top_c + Vector((0, 0, 0.25)), Matrix.Identity(3), 1.4, 0.16, 24), [1.0] * 24)
    cc.materials.append(iron)
    go = new_object(name + "_Gaiola", cc, col)
    go.rotation_euler = (0, 0, 0)
    return top_c + Vector((0, 0, 0.35))


# ---------------------------------------------------------------------------
# O rio: cais, barco e Caronte
# ---------------------------------------------------------------------------
PIER_X = -5.0
PIER_Y0, PIER_Y1 = -9.9, -6.4
BOAT_C = Vector((-4.6, -5.1, RIVER_Z))


def build_pier(col, wood):
    b = Builder()
    z = ground_height(PIER_X, PIER_Y0) + 0.18
    r_ = random.Random(12)
    y = PIER_Y0
    while y < PIER_Y1:
        if r_.random() > 0.08:
            b.box((PIER_X + r_.gauss(0, 0.03), y, z + r_.gauss(0, 0.02)), ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
                  (r_.uniform(1.5, 1.7), 0.2, 0.06), rand=r_.random())
        y += 0.24
    for sy in (PIER_Y0 + 0.4, (PIER_Y0 + PIER_Y1) / 2, PIER_Y1):
        for sx in (-0.72, 0.72):
            top = Vector((PIER_X + sx, sy, z + r_.uniform(0.2, 0.7)))
            b.cylinder(top, Vector((PIER_X + sx + r_.gauss(0, 0.05), sy, RIVER_Z - 1.2)), 0.08, 0.1, 8)
    b.box((PIER_X - 0.72, (PIER_Y0 + PIER_Y1) / 2, z - 0.1), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.1, PIER_Y1 - PIER_Y0, 0.12))
    b.box((PIER_X + 0.72, (PIER_Y0 + PIER_Y1) / 2, z - 0.1), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.1, PIER_Y1 - PIER_Y0, 0.12))
    b.to_object("Cais", col, [wood])
    return z


def build_boat(col, wood, iron, lantern_glass):
    """Barco de Caronte: estreito e comprido, proa a enrolar-se numa voluta alta."""
    L, NS, K = 7.2, 36, 11
    verts, faces = [], []
    for i in range(NS + 1):
        t = i / NS
        w = 0.72 * math.sin(math.pi * min(1.0, t * 1.02)) ** 0.55 + 0.03
        ztop = 0.55 + 1.1 * smooth(0.72, 1.0, t) ** 2 + 0.45 * (1 - smooth(0.0, 0.18, t))
        zkeel = -0.35 + 0.25 * smooth(0.8, 1.0, t) + 0.2 * (1 - smooth(0.0, 0.12, t))
        for k in range(K):
            ph = math.pi * k / (K - 1)
            yy = -w * math.cos(ph)
            zz = ztop - (ztop - zkeel) * math.sin(ph) ** 0.65
            verts.append((-L / 2 + L * t, yy, zz))
    for i in range(NS):
        for k in range(K - 1):
            a = i * K + k
            faces.append((a, a + K, a + K + 1, a + 1))
    me = bpy.data.meshes.new("Barco_Caronte")
    me.from_pydata(verts, [], faces)
    me.materials.append(wood)
    me.shade_smooth()
    ob = new_object("Barco_Caronte", me, col)
    so = ob.modifiers.new("Espessura", "SOLIDIFY")
    so.thickness = 0.06
    ob.modifiers.new("Subdivisao", "SUBSURF").levels = 1
    ob.location = BOAT_C + Vector((0, 0, -0.1))
    ob.rotation_euler = (0, 0, math.radians(4))
    Mb = ob.matrix_basis.copy()
    # bancos
    b = Builder()
    for x in (-1.6, 0.2, 1.6):
        b.box((x, 0, 0.25), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.25, 1.1, 0.05), M=Mb)
    b.to_object("Barco_Bancos", col, [wood])
    # voluta da proa e da popa
    cu = new_curve("Barco_Volutas", 1.0, 2)
    prow = Mb @ Vector((L / 2, 0, 1.65))
    pts = [Mb @ Vector((L / 2 - 0.2, 0, 1.3)), prow]
    cp = curl_pts(prow, (Mb.to_3x3() @ Vector((0.3, 0, 1))).normalized(), 0.55, 1.7, 34, random.Random(2))
    spline(cu, pts + cp[1:], [0.11] * 2 + [0.1 * (1 - i / 34) + 0.02 for i in range(1, 34)])
    stern = Mb @ Vector((-L / 2, 0, 0.95))
    cp2 = curl_pts(stern, (Mb.to_3x3() @ Vector((-0.4, 0, 1))).normalized(), 0.3, 1.5, 26, random.Random(4))
    spline(cu, cp2, [0.07 * (1 - i / 26) + 0.015 for i in range(26)])
    cu.materials.append(wood)
    new_object("Barco_Volutas", cu, col)
    # lanterna pendurada de um braço de ferro na proa
    arm0 = Mb @ Vector((L / 2 - 0.35, 0, 1.2))
    arm1 = arm0 + Mb.to_3x3() @ Vector((0.9, 0.0, 0.25))
    lb = Builder()
    lb.cylinder(arm0, arm1, 0.025, 0.025, 6)
    lc = arm1 - Vector((0, 0, 0.55))
    lb.cylinder(arm1, lc + Vector((0, 0, 0.22)), 0.008, 0.008, 4)
    lb.cylinder(lc + Vector((0, 0, 0.16)), lc + Vector((0, 0, 0.36)), 0.12, 0.0, 6)
    lb.cylinder(lc - Vector((0, 0, 0.16)), lc - Vector((0, 0, 0.12)), 0.11, 0.11, 6)
    lb.to_object("Lanterna_Caronte", col, [iron])
    gb = Builder()
    gb.cylinder(lc - Vector((0, 0, 0.12)), lc + Vector((0, 0, 0.16)), 0.085, 0.1, 6)
    gb.to_object("Lanterna_Caronte_Vidro", col, [lantern_glass])
    return Mb, lc


def build_charon(col, robe, wood, bone, Mb):
    """Caronte: figura encapuzada altíssima e magra, sem rosto, com a vara na mão."""
    M = Mb @ Matrix.Translation((-2.6, 0.0, 0.05)) @ Euler((0, 0, math.radians(-100))).to_matrix().to_4x4()
    b = Builder()
    b.cylinder(M @ Vector((0, 0, 0.0)), M @ Vector((0, 0, 2.35)), 0.5, 0.15, 20)       # manto
    b.cylinder(M @ Vector((0, 0.0, 2.3)), M @ Vector((0, -0.05, 2.5)), 0.2, 0.19, 12)  # ombros/pescoço
    b.ico(M @ Vector((0, -0.02, 2.72)), 0.25, (0.9, 1.0, 1.45), 3, 0.05)               # capuz alto
    b.cylinder(M @ Vector((0, 0.02, 2.95)), M @ Vector((0, 0.24, 3.45)), 0.12, 0.0, 8)  # ponta do capuz, a cair para trás
    b.ico(M @ Vector((0, -0.13, 2.66)), 0.16, (0.8, 0.5, 1.1), 3, 0.0, mat=1)          # vazio do capuz
    # mangas compridas até à vara
    for sx in (-1, 1):
        b.cylinder(M @ Vector((sx * 0.2, -0.02, 2.35)), M @ Vector((sx * 0.18, -0.38, 1.75 + 0.35 * (sx > 0))), 0.1, 0.13, 10)
    ob = b.to_object("Caronte", col, [robe, bpy.data.materials["M_Preto_Abismo"]], smooth=True)
    ob.modifiers.new("Subdivisao", "SUBSURF").levels = 1
    # mãos ossudas (dedos longos) e a vara
    hb = Builder()
    for sx, hz in ((-1, 1.75), (1, 2.1)):
        h = M @ Vector((sx * 0.18, -0.42, hz))
        hb.ico(h, 0.05, (1, 1, 1.2), 1, 0.1)
        for f in range(4):
            hb.cylinder(h, h + M.to_3x3() @ Vector((sx * 0.02 * (f - 1.5), -0.1, -0.06 - 0.02 * f)), 0.012, 0.007, 5)
    hb.to_object("Caronte_Maos", col, [bone], smooth=True)
    pb = Builder()
    p0 = M @ Vector((-0.2, -0.45, 3.9))
    p1 = M @ Vector((0.2, -0.38, -1.8))
    pb.cylinder(p0, p1, 0.03, 0.035, 8)
    pb.to_object("Caronte_Vara", col, [wood])
    return ob


# ---------------------------------------------------------------------------
# Abismo: ponte e colina em espiral
# ---------------------------------------------------------------------------
def bridge_ends():
    x0, x1 = 1.3, -0.9
    y0 = abyss_y(x0) - abyss_hw(x0) - 1.6
    y1 = abyss_y(x1) + abyss_hw(x1) + 1.9
    return Vector((x0, y0, ground_height(x0, y0) + 0.12)), Vector((x1, y1, ground_height(x1, y1) + 0.12))


def bridge_point(t):
    a, c = bridge_ends()
    p = a.lerp(c, t)
    p.x += 0.55 * math.sin(2 * math.pi * t * 1.3)
    p.z += 0.9 * math.sin(math.pi * t) + 0.2 * math.sin(3.3 * math.pi * t)
    return p


def build_bridge(col, stone, icicle_mat):
    """Ponte de pedra estreita e torta, sem guardas, com blocos em falta."""
    b = Builder()
    r_ = random.Random(31)
    n = 34
    for i in range(n):
        if i in (11, 23) and True:
            continue                                   # blocos em falta
        t0, t1 = i / n, (i + 1) / n
        p0, p1 = bridge_point(t0), bridge_point(t1)
        d = (p1 - p0)
        u = d.normalized()
        side = u.cross(Vector((0, 0, 1))).normalized()
        roll = r_.gauss(0, 0.07)
        up = (Vector((0, 0, 1)) + side * roll).normalized()
        up = (up - u * up.dot(u)).normalized()
        side = up.cross(u)
        w = r_.uniform(1.1, 1.45)
        b.box((p0 + p1) / 2 - up * 0.18, (u, side, up), (d.length * 1.04, w, 0.36))
    ob = b.to_object("Ponte_Tabuleiro", col, [stone])
    ob.modifiers.new("Bevel", "BEVEL").width = 0.04
    # arco de rocha por baixo (mais grosso junto às paredes)
    cu = new_curve("Ponte_Arco", 1.0, 3)
    pts, rr = [], []
    for i in range(41):
        t = i / 40
        p = bridge_point(t)
        dip = 7.0 * (1 - smooth(0.0, 0.3, t)) + 7.0 * smooth(0.7, 1.0, t)
        pts.append(p - Vector((0, 0, 0.75 + dip)))
        rr.append(0.5 + 1.4 * (1 - smooth(0.0, 0.3, t)) + 1.4 * smooth(0.7, 1.0, t))
    spline(cu, pts, rr)
    cu.materials.append(stone)
    new_object("Ponte_Arco_Rocha", cu, col)
    # estalactites por baixo do arco
    sb = Builder()
    ib = Builder()
    for i in range(22):
        t = r_.uniform(0.2, 0.8)
        p = bridge_point(t) - Vector((0, 0, 1.1)) + Vector((r_.gauss(0, 0.2), 0, 0))
        sb.cylinder(p, p - Vector((r_.gauss(0, 0.1), r_.gauss(0, 0.1), r_.uniform(0.6, 2.8))), r_.uniform(0.12, 0.3), 0.0, 6)
        p2 = bridge_point(r_.uniform(0.05, 0.95)) + Vector((0, 0, -0.1)) + bridge_side(r_) * 0.65
        ib.cylinder(p2, p2 - Vector((0, 0, r_.uniform(0.15, 0.7))), r_.uniform(0.03, 0.07), 0.0, 6)
    sb.to_object("Ponte_Estalactites", col, [stone])
    ib.to_object("Ponte_Sincelos", col, [icicle_mat], smooth=True)
    return ob


def bridge_side(r_):
    return Vector((1 if r_.random() < 0.5 else -1, 0, 0))


def build_spiral_hill(col, stone, icicle_mat):
    """A colina em espiral (homenagem a O Estranho Mundo de Jack), enrolada sobre o abismo."""
    x = 19.0
    C = Vector((x, 13.8, 4.0))
    start_y = 23.0
    start_z = ground_height(x, start_y) - 0.8
    rel = Vector((0, start_y - C.y, start_z - C.z))
    r0 = rel.length
    phi0 = math.atan2(rel.z, rel.y)
    pts, rr = [], []
    N = 120
    turns = 1.55
    for i in range(N + 1):
        t = i / N
        a = phi0 + t * turns * 2 * math.pi
        r = r0 * (1 - 0.86 * t ** 0.9)
        wob = 0.6 * math.sin(t * 9)
        pts.append(C + Vector((wob * (1 - t), math.cos(a) * r, math.sin(a) * r)))
        rr.append(2.6 * (1 - t) ** 1.1 + 0.18)
    cu = new_curve("Colina_Espiral", 1.0, 4)
    spline(cu, pts, rr)
    cu.materials.append(stone)
    ob = new_object("Colina_Espiral", cu, col)
    ib = Builder()
    r_ = random.Random(77)
    for i in range(40, N - 10, 3):   # sincelos por baixo da curva
        p, r = pts[i], rr[i]
        q = p - Vector((0, 0, r * 0.95))
        ib.cylinder(q + Vector((r_.gauss(0, r * 0.3), 0, 0)), q - Vector((0, 0, r_.uniform(0.3, 1.4))), r_.uniform(0.05, 0.14), 0.0, 6)
    ib.to_object("Colina_Sincelos", col, [icicle_mat], smooth=True)
    return ob, pts


# ---------------------------------------------------------------------------
# Picos de rocha, árvores queimadas, Dis
# ---------------------------------------------------------------------------
def make_spire(cu, base, height, r0, r_, curl=False):
    d = Vector((r_.gauss(0, 0.12), r_.gauss(0, 0.12), 1))
    pts, rr = grow(base, d, height, r0, 0.03, 12, 0.07, r_, up_bias=0.05)
    rr = [r0 * (1 - i / 12) ** 1.3 + 0.03 for i in range(13)]
    if curl:
        cp = curl_pts(pts[-1], (pts[-1] - pts[-2]).normalized(), height * 0.07, 1.5, 22, r_)
        pts = pts + cp[1:]
        rr = rr + [0.03] * (len(cp) - 1)
        rr = [max(0.02, r) for r in rr]
        for i in range(len(rr) - len(cp) - 3, len(rr)):
            k = (i - (len(rr) - len(cp) - 3)) / (len(cp) + 2)
            rr[i] = max(0.015, rr[len(rr) - len(cp) - 4] * (1 - k))
    spline(cu, pts, rr)


CAM_ZONES = [(0.6, -47.0), (1.8, -10.6), (-15.0, 11.0), (-9.0, 0.3), (6.8, -21.5), (-15.0, -24.0), (-4.0, 4.0)]


def free_spot(x, y, clear_path=5.0):
    if abs(y - river_y(x)) < 4.8 or abs(y - abyss_y(x)) < abyss_hw(x) + 2.2:
        return False
    if path_dist(x, y) < clear_path:
        return False
    if abs(x) < 9 and y < -8:                        # linha de vista das portas
        return False
    if abs(x) < 7 and -34 < y < -22:
        return False
    if 14 < x < 25 and 12 < y < 27:                  # base da colina em espiral
        return False
    if any(math.hypot(x - a, y - b) < 6.0 for a, b in CAM_ZONES):
        return False
    return True


def build_spires(col, stone):
    r_ = random.Random(44)
    cu = new_curve("Picos_Rocha", 1.0, 2)
    placed = []
    tries = 0
    while len(placed) < 34 and tries < 5000:
        tries += 1
        x, y = r_.uniform(-X_HALF + 2, X_HALF - 2), r_.uniform(-44, 40)
        if not free_spot(x, y) or any(math.hypot(x - a, y - b) < 4.5 for a, b in placed):
            continue
        placed.append((x, y))
        make_spire(cu, Vector((x, y, ground_height(x, y) - 0.5)), r_.uniform(5, 17), r_.uniform(0.5, 1.4), r_, r_.random() < 0.3)
    # anel distante para as silhuetas
    for i in range(60):
        a = r_.uniform(0, 2 * math.pi)
        R = r_.uniform(50, 110)
        x, y = math.cos(a) * R, math.sin(a) * R * 0.8 + 5
        if (y > 55 and abs(x) < 80) or (y < -8 and abs(x) < 55):
            continue
        make_spire(cu, Vector((x, y, ground_height(x, y) - 1.0)), r_.uniform(12, 35), r_.uniform(1.5, 3.5), r_, r_.random() < 0.35)
    cu.materials.append(stone)
    new_object("Picos_Rocha", cu, col)
    return placed


def make_burnt_tree(name, col, mat, seed, height, trunk_r):
    """Árvore queimada, negra, com as pontas dos ramos enroladas."""
    r_ = random.Random(seed)
    cu = new_curve(name, 1.0, 2)
    trunk, tr = grow((0, 0, -0.4), Vector((r_.gauss(0, 0.2), r_.gauss(0, 0.2), 1)), height, trunk_r, trunk_r * 0.12, 16, 0.2, r_, up_bias=0.08)
    spline(cu, trunk, tr)
    ends = []
    for i in range(5, len(trunk) - 1):
        if r_.random() > 0.55:
            continue
        t = i / len(trunk)
        az = r_.uniform(0, 2 * math.pi)
        d = Vector((math.cos(az), math.sin(az), r_.uniform(0.2, 1.0)))
        ln = height * (1 - t) * r_.uniform(0.35, 0.6) + 0.8
        br, brr = grow(trunk[i], d, ln, tr[i] * 0.55, 0.015, 8, 0.3, r_)
        spline(cu, br, brr)
        ends.append((br[-1], (br[-1] - br[-2]).normalized()))
        for j in range(3, len(br) - 1):
            if r_.random() > 0.4:
                continue
            d2 = (br[j + 1] - br[j]).normalized() + Vector((r_.gauss(0, 1), r_.gauss(0, 1), r_.uniform(-0.1, 0.8))) * 0.9
            tw, twr = grow(br[j], d2, ln * r_.uniform(0.25, 0.45), brr[j] * 0.6, 0.008, 5, 0.4, r_)
            spline(cu, tw, twr)
            ends.append((tw[-1], (tw[-1] - tw[-2]).normalized()))
    for p, d in ends:
        if r_.random() < 0.5:
            cp = curl_pts(p, d, r_.uniform(0.12, 0.35), 2.2, 22, r_)
            spline(cu, cp, [0.012 * (1 - i / 22) + 0.003 for i in range(22)])
    for k in range(6):
        az = 2 * math.pi * k / 6 + r_.uniform(-0.3, 0.3)
        pts = [Vector((math.cos(az) * rr_, math.sin(az) * rr_, 0.5 * (1 - rr_ / 2.2) ** 2 - 0.15)) for rr_ in np.linspace(0.05, 2.2, 8)]
        spline(cu, pts, [trunk_r * 0.5 * (1 - i / 8) + 0.02 for i in range(8)])
    cu.materials.append(mat)
    return new_object(name, cu, col)


def build_dis(col, stone, windows):
    """A Cidade de Dis: torres agudíssimas e tortas, com janelas-fornalha, em silhueta."""
    r_ = random.Random(1300)
    b = Builder()
    wb = Builder()
    cu = new_curve("Dis_Espirais", 1.0, 2)
    towers = []
    for i in range(46):
        x = r_.uniform(-85, 85)
        y = r_.uniform(64, 118)
        if any(math.hypot(x - a, y - c) < 6 for a, c, _ in towers):
            continue
        H = (16 + 60 * math.exp(-(x / 32.0) ** 2)) * r_.uniform(0.55, 1.0)
        towers.append((x, y, H))
    towers.append((2.0, 92.0, 105.0))                          # a torre maior, ao centro
    for x, y, H in towers:
        gz = ground_height(x, y) - 1.0
        R = r_.uniform(2.2, 4.5) * (H / 60) ** 0.5 + 1.2
        lean = Vector((r_.gauss(0, 0.05), r_.gauss(0, 0.04), 0))
        p = Vector((x, y, gz))
        segs = r_.randint(3, 5)
        hseg = H * 0.62 / segs
        for s in range(segs):
            q = p + (Vector((0, 0, 1)) + lean * (s + 1)) * hseg + Vector((r_.gauss(0, 0.3), r_.gauss(0, 0.3), 0))
            r1 = R * (0.92 - 0.1 * s)
            b.cylinder(p, q, R, r1, r_.choice((6, 8)))
            b.cylinder(q - Vector((0, 0, 0.5)), q + Vector((0, 0, 0.4)), r1 * 1.18, r1 * 1.18, 8)   # cornija
            # janelas na face virada para nós (-Y)
            for w in range(r_.randint(1, 4)):
                if r_.random() < 0.3:
                    continue
                wz = p.z + r_.uniform(0.2, 0.8) * (q.z - p.z)
                wa = -math.pi / 2 + r_.uniform(-0.8, 0.8)
                rr = (R + r1) / 2 + 0.05
                c = Vector((p.x + math.cos(wa) * rr, p.y + math.sin(wa) * rr, wz))
                nrm = Vector((math.cos(wa), math.sin(wa), 0))
                wb.box(c, (nrm.cross(Vector((0, 0, 1))), nrm, (0, 0, 1)), (0.7, 0.3, r_.uniform(1.4, 2.6)))
            p = q
            R = r1
        top = p + (Vector((0, 0, 1)) + lean * 2) * H * 0.38
        b.cylinder(p, top, R * 1.05, 0.0, 8)
        if r_.random() < 0.45 or H > 100:
            cp = curl_pts(top, (top - p).normalized(), r_.uniform(1.0, 2.5) * (H / 50), 1.4, 26, r_)
            spline(cu, cp, [0.25 * (H / 50) * (1 - i / 26) + 0.05 for i in range(26)])
    # muralha com ameias tortas
    for i in range(60):
        x = -90 + 3 * i
        y = 60 + 2.5 * math.sin(x * 0.05)
        gz = ground_height(x, y) - 1
        h = 7 + 1.5 * math.sin(x * 0.2)
        b.box((x, y, gz + h / 2), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (3.05, 1.6, h))
        if i % 2 == 0:
            b.cylinder(Vector((x, y, gz + h)), Vector((x + r_.gauss(0, 0.2), y, gz + h + r_.uniform(1.2, 2.6))), 0.7, 0.0, 4)
    b.to_object("Cidade_Dis", col, [stone])
    wb.to_object("Cidade_Dis_Janelas", col, [windows])
    cu.materials.append(stone)
    new_object("Cidade_Dis_Espirais", cu, col)


def build_crow_model(col, mat):
    b = Builder()
    b.ico((0, 0, 0.12), 0.08, (0.85, 1.6, 0.9), 2, 0.05)         # corpo (frente = -Y)
    b.ico((0, -0.13, 0.2), 0.05, (1, 1.1, 1), 2, 0.0)            # cabeça
    b.cylinder((0, -0.17, 0.2), (0, -0.25, 0.19), 0.018, 0.0, 6)  # bico
    b.box((0, 0.17, 0.1), ((1, 0, 0), Vector((0, 1, -0.4)).normalized(), Vector((0, 0.4, 1)).normalized()), (0.07, 0.14, 0.01))
    for s in (-1, 1):
        b.box((s * 0.07, 0.02, 0.13), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.02, 0.2, 0.08))
        b.cylinder((s * 0.025, -0.01, 0.05), (s * 0.025, 0.0, -0.02), 0.005, 0.004, 4)
    return b.to_object("Corvo_Cinza_Modelo", col, [mat], smooth=True)


# ---------------------------------------------------------------------------
# Partículas estáticas: fagulhas, cinza, neve
# ---------------------------------------------------------------------------
def build_particles(col, ember_mat, ash_mat, snow_mat):
    r_ = random.Random(99)
    b = Builder()
    for i in range(1000):                       # fagulhas: metade a subir do abismo
        if i % 2:
            x = r_.uniform(-30, 30)
            y = abyss_y(x) + r_.uniform(-5, 5)
            z = r_.uniform(-22, 12)
        else:
            x, y = r_.uniform(-22, 22), r_.uniform(-40, 30)
            z = ground_height(x, y) + r_.uniform(0.3, 9)
        s = r_.uniform(0.006, 0.016)
        b.ico((x, y, z), s, (1, 1, r_.uniform(2.5, 5)), 1, 0.0, rot=(r_.gauss(0, 0.3), r_.gauss(0, 0.3), 0))
    b.to_object("Fagulhas", col, [ember_mat])

    def flakes(name, n, size, area, mat):
        bm = bmesh.new()
        for _ in range(n):
            x, y = r_.uniform(*area[0]), r_.uniform(*area[1])
            z = max(ground_height(x, y), RIVER_Z) + r_.uniform(0.2, area[2])
            m = Matrix.Translation((x, y, z)) @ Euler((r_.uniform(0, 6.3), r_.uniform(0, 6.3), r_.uniform(0, 6.3))).to_matrix().to_4x4()
            s = r_.uniform(*size)
            bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=s, matrix=m)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mat)
        return new_object(name, me, col)

    flakes("Cinza_a_Cair", 3500, (0.012, 0.03), ((-24, 24), (-48, 28), 10), ash_mat)
    flakes("Neve_a_Cair", 6000, (0.01, 0.024), ((-24, 24), (-48, 28), 10), snow_mat)


# ---------------------------------------------------------------------------
# Céu, luzes, câmaras, render
# ---------------------------------------------------------------------------
def make_sky():
    """Um só World: fumo iluminado por baixo (Brasas) ou céu encoberto pálido (Gelo)."""
    w = bpy.data.worlds.new("Ceu_Inferno")
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new
    out = N("ShaderNodeOutputWorld")
    bg = N("ShaderNodeBackground")
    tc = N("ShaderNodeTexCoord")
    sep = N("ShaderNodeSeparateXYZ")
    L(tc.outputs["Generated"], sep.inputs[0])
    g = gelo_node(nt)

    def mr(val, a, b, c=0.0, d=1.0):
        n = N("ShaderNodeMapRange")
        L(val, n.inputs["Value"])
        n.inputs["From Min"].default_value, n.inputs["From Max"].default_value = a, b
        n.inputs["To Min"].default_value, n.inputs["To Max"].default_value = c, d
        return n.outputs["Result"]

    def mixc(fac, a, b, blend="MIX"):
        n = N("ShaderNodeMix")
        n.data_type = "RGBA"
        n.blend_type = blend
        for s_, v in ((sock(n, "Factor_Float"), fac), (sock(n, "A_Color"), a), (sock(n, "B_Color"), b)):
            if isinstance(v, bpy.types.NodeSocket):
                L(v, s_)
            elif isinstance(v, (int, float)):
                s_.default_value = v
            else:
                s_.default_value = (*v, 1) if len(v) == 3 else v
        return sock(n, "Result_Color", out=True)

    mp = N("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.2, 1.2, 4.0)
    L(tc.outputs["Generated"], mp.inputs["Vector"])
    nz = N("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 2.0
    nz.inputs["Detail"].default_value = 8.0
    nz.inputs["Roughness"].default_value = 0.62
    L(mp.outputs["Vector"], nz.inputs["Vector"])
    clouds = mr(nz.outputs["Fac"], 0.3, 0.75, 0.25, 1.4)
    # Brasas: brilho de fornalha no horizonte (mais forte para os lados de Dis), fumo escuro em cima
    dot = N("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    L(tc.outputs["Generated"], dot.inputs[0])
    dot.inputs[1].default_value = (0.0, 1.0, 0.0)
    north = mr(dot.outputs["Value"], -1.0, 1.0, 0.45, 1.0)
    glow = mr(sep.outputs["Z"], -0.02, 0.4, 1.0, 0.0)
    pw = N("ShaderNodeMath")
    pw.operation = "POWER"
    L(glow, pw.inputs[0])
    pw.inputs[1].default_value = 2.8
    gf = N("ShaderNodeMath")
    gf.operation = "MULTIPLY"
    L(pw.outputs[0], gf.inputs[0])
    L(north, gf.inputs[1])
    fire_sky = mixc(gf.outputs[0], (0.01, 0.007, 0.008), (0.62, 0.17, 0.03))
    cl_col = N("ShaderNodeCombineColor")
    for i in range(3):
        L(clouds, cl_col.inputs[i])
    fire_sky = mixc(1.0, fire_sky, cl_col.outputs[0], "MULTIPLY")
    # Gelo: céu encoberto, pálido e chapado, mais claro no horizonte
    ice_grad = mr(sep.outputs["Z"], 0.0, 0.6)
    ice_sky = mixc(ice_grad, (0.48, 0.52, 0.58), (0.17, 0.2, 0.25))
    cl2 = mr(nz.outputs["Fac"], 0.3, 0.75, 0.75, 1.15)
    cl2c = N("ShaderNodeCombineColor")
    for i in range(3):
        L(cl2, cl2c.inputs[i])
    ice_sky = mixc(1.0, ice_sky, cl2c.outputs[0], "MULTIPLY")
    L(mixc(g, fire_sky, ice_sky), bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
    L(bg.outputs[0], out.inputs["Surface"])
    return w


def var_light(name, kind, col, loc, energy, color, on_gelo, **kw):
    """Luz que só acende numa das versões (a força lê a propriedade "gelo")."""
    ld = bpy.data.lights.new(name, kind)
    ld.energy = energy
    ld.color = color
    for k, v in kw.items():
        setattr(ld, k, v)
    ld.use_nodes = True
    nt = ld.node_tree
    em = next(n for n in nt.nodes if n.type == "EMISSION")
    g = gelo_node(nt)
    if on_gelo:
        nt.links.new(g, em.inputs["Strength"])
    else:
        inv = nt.nodes.new("ShaderNodeMath")
        inv.operation = "SUBTRACT"
        inv.inputs[0].default_value = 1.0
        nt.links.new(g, inv.inputs[1])
        nt.links.new(inv.outputs[0], em.inputs["Strength"])
    ob = new_object(name, ld, col)
    ob.location = loc
    ob["versao"] = "Gelo" if on_gelo else "Brasas"
    return ob


def build_lights(v_fire, v_ice, braziers):
    sun = var_light("LUZ_Brasas_Contraluz", "SUN", v_fire, (0, 40, 30), 1.6, (1.0, 0.36, 0.12), False, angle=math.radians(6))
    sun.rotation_euler = SUN_BRASAS.to_track_quat("-Z", "Y").to_euler()
    fill = var_light("LUZ_Brasas_Ceu", "SUN", v_fire, (0, 0, 30), 0.12, (0.9, 0.35, 0.3), False, angle=math.radians(60))
    fill.rotation_euler = Vector((0.2, 0.3, -1)).normalized().to_track_quat("-Z", "Y").to_euler()
    for i, x in enumerate(range(-36, 37, 12)):
        y = abyss_y(x)
        a = var_light(f"LUZ_Brasas_Abismo_{i}", "AREA", v_fire, (x, y, LAVA_Z + 3), 5000, (1.0, 0.3, 0.06), False,
                      shape="RECTANGLE", size=12.0, size_y=8.0)
        a.rotation_euler = (math.pi, 0, 0)
        a.data.shape = "RECTANGLE"
        a.rotation_euler = Vector((0, 0, 1)).to_track_quat("-Z", "Y").to_euler()
    for i, x in enumerate(range(-30, 31, 10)):
        a = var_light(f"LUZ_Brasas_Rio_{i}", "AREA", v_fire, (x, river_y(x), RIVER_Z + 0.4), 500, (1.0, 0.32, 0.07), False,
                      shape="RECTANGLE", size=9.0, size_y=3.5)
        a.rotation_euler = Vector((0, 0, 1)).to_track_quat("-Z", "Y").to_euler()
    for i, p in enumerate(braziers):
        var_light(f"LUZ_Brasas_Braseiro_{i}", "POINT", v_fire, p, 900, (1.0, 0.45, 0.15), False, shadow_soft_size=0.5)
    sun2 = var_light("LUZ_Gelo_Ceu_Encoberto", "SUN", v_ice, (0, 0, 30), 1.4, (0.75, 0.83, 1.0), True, angle=math.radians(35))
    sun2.rotation_euler = SUN_GELO.to_track_quat("-Z", "Y").to_euler()
    for i, x in enumerate(range(-36, 37, 12)):
        a = var_light(f"LUZ_Gelo_Abismo_{i}", "AREA", v_ice, (x, abyss_y(x), LAVA_Z + 3), 1200, (0.4, 0.7, 1.0), True,
                      shape="RECTANGLE", size=12.0, size_y=8.0)
        a.rotation_euler = Vector((0, 0, 1)).to_track_quat("-Z", "Y").to_euler()


def build_atmosphere(col, mat):
    me = bpy.data.meshes.new("Atmosfera")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0, 35, -2)) @ Matrix.Diagonal((180, 180, 62, 1)))
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    new_object("ATMOS_Fumo_Nevoa", me, col)


def build_cameras(col):
    cams = {}

    def cam(name, loc, target, lens, fstop=None, focus=None):
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        cd.sensor_width = 36
        cd.clip_start = 0.05
        cd.clip_end = 800
        if fstop:
            cd.dof.use_dof = True
            cd.dof.aperture_fstop = fstop
            cd.dof.focus_distance = focus
        ob = new_object(name, cd, col)
        ob.location = loc
        ob.rotation_euler = look_at_rotation(loc, target)
        cams[name] = ob

    def g(x, y, dz):
        return Vector((x, y, ground_height(x, y) + dz))

    cam("CAM_1_Portas", g(0.6, -47.0, 1.7), Vector((0.0, -10.0, 5.5)), 20)
    cam("CAM_2_Contrapicado_Inscricao", g(2.2, -33.8, 0.5), Vector((0.0, GATE_Y, 9.0)), 18)
    cam("CAM_3_Barco_Caronte", g(1.8, -10.6, 1.5), BOAT_C + Vector((-1.2, 0, 1.4)), 30, 4.0, 8.4)
    b0, b1 = bridge_ends()
    cam("CAM_4_Ponte_Abismo", Vector((-15.0, 11.0, 0.5)), Vector((2.0, 11.6, -6.5)), 20)
    cam("CAM_5_Dis_Silhueta", g(-9.0, 0.3, 1.8), Vector((3.0, 60.0, 13.0)), 26)
    cam("CAM_6_Fendas_Relogio", g(6.8, -21.5, 0.4), g(4.2, -15.5, 1.6), 28, 5.6, 6.2)
    cam("CAM_7_Fundo_Analise", g(-15.0, -24.0, 2.8), Vector((2.0, 2.0, -0.5)), 24)
    bpy.context.scene.camera = cams["CAM_1_Portas"]
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

    def g(x, y):
        return (x, y, ground_height(x, y))

    marker("PERSONAGEM_1_Portas", g(0.2, -31.5), (0, 1), "diante das Portas, a ler a inscrição (CAM_1 / CAM_2)")
    marker("PERSONAGEM_2_Cais", (PIER_X, PIER_Y1 - 0.5, ground_height(PIER_X, PIER_Y0) + 0.21), (0.3, 1),
           "no fim do cais, à espera de Caronte (CAM_3)")
    p = bridge_point(0.45)
    marker("PERSONAGEM_3_Ponte", (p.x, p.y, p.z), (0, 1), "a meio da ponte sobre o abismo (CAM_4 / CAM_5)")
    marker("PERSONAGEM_4_Preso_no_Gelo", (7.0, river_y(7.0), RIVER_Z), (0, -1),
           "versão Gelo: preso no rio gelado — baixar o personagem ~1,1 m (gelo pelo peito)")


def setup_render():
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.cycles.samples = 384
    scn.cycles.preview_samples = 24
    scn.cycles.use_adaptive_sampling = True
    scn.cycles.adaptive_threshold = 0.02
    scn.cycles.use_denoising = True
    scn.cycles.max_bounces = 8
    scn.cycles.diffuse_bounces = 2
    scn.cycles.glossy_bounces = 3
    scn.cycles.transmission_bounces = 4
    scn.cycles.transparent_max_bounces = 16
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
    scn.view_settings.exposure = EXPOSURE


EXPOSURE = 0.6


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
    """Paleta Burton: dessaturada, sombras violeta; o calor só nas fontes (lava, braseiros, lanterna)."""
    film_look(glare=(1.0, 0.35), lens=(0.008, 0.004), sat=0.9, lift=(0.995, 1.0, 1.015), gamma=(1.0, 1.0, 1.0),
              gain=(1.0, 1.0, 1.0), vignette_min=0.35, grain=0.1)


README_TEXT = """INFERNO: FOGO E GELO (estilo Tim Burton) — como usar
====================================================
UM SÓ INTERRUPTOR: Scene Properties → Custom Properties → "gelo"
   0 = Brasas (lava, fumo, fagulhas, cinza)
   1 = Gelo   (Cocito: lava gelada, geada, névoa, neve, sincelos, chamas congeladas)
Muda materiais, céu, nevoeiro, partículas e luzes de uma vez (nó Attribute
'View Layer' → gelo). Para renderizar mais depressa, exclua a coleção da
versão que não está a usar (05_LUZ/VAR_Brasas ou VAR_Gelo).
Exposição recomendada: 0.6 nas duas versões.
Personagem preso no gelo: PERSONAGEM_4 (baixar ~1,1 m).
"""


def main():
    args = parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.name = "Inferno_Fogo_Gelo"
    scn["gelo"] = 0.0
    ui = scn.id_properties_ui("gelo")
    ui.update(min=0.0, max=1.0, soft_min=0.0, soft_max=1.0, description="0 = Brasas, 1 = Gelo")
    c_models = collection("_MODELOS")
    c_ground = collection("01_TERRENO_RIO_ABISMO")
    c_gate = collection("02_PORTAS_DESCIDA")
    c_river = collection("03_RIO_CARONTE")
    c_abyss = collection("04_PONTE_ESPIRAL_DIS")
    c_light = collection("05_LUZ")
    v_fire = collection("VAR_Brasas", c_light)
    v_ice = collection("VAR_Gelo", c_light)
    c_atmos = collection("ATMOSFERA_PARTICULAS", c_light)
    c_cam = collection("06_CAMARAS")
    c_char = collection("07_PERSONAGEM")

    basalt = mat_basalt("M_Basalto_Fendas", cracks=True)
    rock = mat_basalt("M_Basalto_Rocha", tone=0.9, ash=0.35)
    slabs = mat_basalt("M_Lajes_Caminho", tone=1.5, ash=0.8)
    dark = mat_basalt("M_Pedra_Dis", tone=0.5, ash=0.0)
    gate_stone = mat_gate_stone()
    lava = mat_lava_ice()
    fire = mat_fire_ice()
    iron = mat_iron()
    charred = mat_charred()
    wood = mat_wood("M_Madeira_Barco", dark=1.6)
    robe = mat_robe()
    bone = mat_simple("M_Osso", (0.35, 0.32, 0.27), 0.6, noise_scale=20.0, bump=0.3)
    letters = mat_letters()
    windows = mat_windows()
    icicles = mat_icicles()
    mat_simple("M_Preto_Abismo", (0.0, 0.0, 0.0), 1.0)
    face = mat_simple("M_Mostrador", (0.42, 0.4, 0.33), 0.5, noise_scale=8.0)
    board = mat_simple("M_Placa", (0.36, 0.3, 0.22), 0.8, noise_scale=6.0, bump=0.2)
    ink = mat_simple("M_Tinta_Placa", (0.25, 0.02, 0.01), 0.6)
    lantern = mat_emit("M_Lanterna_Acesa", (1.0, 0.55, 0.2), 25.0)
    embers = mat_show_only("M_Fagulhas", False, None, emit=12.0, emit_color=(1.0, 0.45, 0.08))
    ash = mat_show_only("M_Cinza", False, (0.2, 0.19, 0.19))
    snow = mat_show_only("M_Neve", True, (0.85, 0.88, 0.92))
    atmos = mat_atmosphere()

    print("> terreno, rio e abismo")
    build_terrain(c_ground, basalt)
    build_lava(c_ground, lava)
    build_path_stones(c_ground, slabs)
    print("> portas, braseiros, descida")
    build_gate(c_gate, gate_stone, iron, letters, icicles)
    braz = [build_brazier(c_gate, f"Braseiro_{i}", Vector((sx * 5.4, GATE_Y - 1.8, 0)), iron, fire)
            for i, sx in enumerate((-1, 1))]
    clock_top = build_clock(c_gate, wood, face, iron, icicles, Vector((4.3, -15.8, 0)))
    build_welcome_sign(c_gate, charred, board, ink, Vector((-3.4, -23.2, 0)))
    r_ = random.Random(3)
    cages = [build_gibbet(c_gate, iron, f"Forca_{i}", Vector(p), yaw, ln, r_)
             for i, (p, yaw, ln) in enumerate((((-4.8, -18.6, 0), 0.2, 0.8), ((5.6, -25.0, 0), math.pi - 0.3, 1.3),
                                                ((-6.4, -12.8, 0), 0.5, 0.5)))]
    print("> rio, cais, barco, Caronte")
    build_pier(c_river, wood)
    Mb, lantern_pos = build_boat(c_river, wood, iron, lantern)
    build_charon(c_river, robe, wood, bone, Mb)
    ld = bpy.data.lights.new("LUZ_Lanterna_Caronte", "POINT")
    ld.energy = 120
    ld.color = (1.0, 0.55, 0.2)
    ld.shadow_soft_size = 0.06
    new_object("LUZ_Lanterna_Caronte", ld, c_light).location = lantern_pos
    print("> ponte, colina em espiral, picos, árvores, Dis")
    build_bridge(c_abyss, rock, icicles)
    hill, hill_pts = build_spiral_hill(c_abyss, rock, icicles)
    build_spires(c_abyss, rock)
    tcol = collection("_ARVORES", c_models)
    tmods = []
    for i in range(3):
        mc = collection(f"_ARVORE_QUEIMADA_{i}", tcol)
        make_burnt_tree(f"Arvore_Queimada_{i}", mc, charred, 500 + i, rng.uniform(6, 9), rng.uniform(0.16, 0.26))
        tmods.append(mc)
    r2 = random.Random(18)
    spots = []
    tries = 0
    while len(spots) < 14 and tries < 4000:
        tries += 1
        x, y = r2.uniform(-X_HALF + 3, X_HALF - 3), r2.uniform(-46, 40)
        if not free_spot(x, y, 3.5) or any(math.hypot(x - a, y - b) < 6 for a, b in spots):
            continue
        spots.append((x, y))
        e = bpy.data.objects.new(f"Arvore_{len(spots):02d}", None)
        e.instance_type = "COLLECTION"
        e.instance_collection = r2.choice(tmods)
        e.location = (x, y, ground_height(x, y))
        s = r2.uniform(0.8, 1.35)
        e.scale = (s, s, s * r2.uniform(1.0, 1.3))
        e.rotation_euler = (0, 0, r2.uniform(0, 6.3))
        c_abyss.objects.link(e)
    build_dis(c_abyss, dark, windows)
    crow = build_crow_model(c_models, mat_simple("M_Corvo_Cinza", (0.16, 0.155, 0.15), 0.8, noise_scale=30.0))
    b0, _ = bridge_ends()
    perches = [(clock_top + Vector((0, 0, 0.1)), 0.4), (cages[0], 2.5), (cages[1], 1.0),
               (b0 + Vector((0.5, -0.4, 0.2)), 3.3), (Vector((-3.1, -22.95, ground_height(-3.4, -23.2) + 3.08)), 0.2)]
    for i, (p, yaw) in enumerate(perches):
        c = bpy.data.objects.new(f"Corvo_Cinza_{i}", crow.data)
        c_gate.objects.link(c)
        c.location = p
        c.rotation_euler = (0, 0, yaw)
        c.scale = (1.4, 1.4, 1.5)
    print("> atmosfera, partículas, luz, câmaras")
    build_atmosphere(c_atmos, atmos)
    build_particles(c_atmos, embers, ash, snow)
    scn.world = make_sky()
    build_lights(v_fire, v_ice, braz)
    build_cameras(c_cam)
    build_markers(c_char)
    setup_render()
    setup_compositor()
    bpy.data.texts.new("LEIA-ME").write(README_TEXT)
    vl = bpy.context.view_layer
    vl.layer_collection.children["_MODELOS"].exclude = True
    vl.layer_collection.children["05_LUZ"].children["VAR_Gelo"].exclude = True
    scn.frame_set(1)
    out = os.path.abspath(args.out)
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    print(f"> guardado: {out}")
    if args.render:
        render_previews(args)


PREVIEWS = [   # (ficheiro, câmara, gelo?)
    ("cam1_portas", "CAM_1_Portas", False),
    ("cam2_contrapicado_inscricao", "CAM_2_Contrapicado_Inscricao", False),
    ("cam3_barco_caronte", "CAM_3_Barco_Caronte", False),
    ("cam4_ponte_abismo", "CAM_4_Ponte_Abismo", False),
    ("cam5_dis_silhueta", "CAM_5_Dis_Silhueta", False),
    ("cam6_fendas_relogio", "CAM_6_Fendas_Relogio", False),
    ("cam7_fundo_analise", "CAM_7_Fundo_Analise", False),
    ("gelo_cam1_portas", "CAM_1_Portas", True),
    ("gelo_cam3_barco_caronte", "CAM_3_Barco_Caronte", True),
    ("gelo_cam4_ponte_abismo", "CAM_4_Ponte_Abismo", True),
    ("gelo_cam5_dis_silhueta", "CAM_5_Dis_Silhueta", True),
    ("gelo_cam6_fendas_relogio", "CAM_6_Fendas_Relogio", True),
]


def render_previews(args):
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
    for fname, cam, is_ice in PREVIEWS:
        if only and fname not in only:
            continue
        scn["gelo"] = 1.0 if is_ice else 0.0
        ll.children["VAR_Brasas"].exclude = is_ice
        ll.children["VAR_Gelo"].exclude = not is_ice
        for name in ("Fagulhas", "Cinza_a_Cair"):
            bpy.data.objects[name].hide_render = is_ice
        bpy.data.objects["Neve_a_Cair"].hide_render = not is_ice
        scn.camera = bpy.data.objects[cam]
        scn.frame_set(20)
        scn.render.filepath = os.path.join(os.path.abspath(args.render), fname + ".jpg")
        print(f"> render {fname}")
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
