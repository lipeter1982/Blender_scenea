"""
Cenário 05 — Corredor de escola americana e a sala de aula (sequência dos vultos)

Corredor noturno com cacifos, linóleo, fluorescentes a falhar e três portas:
duas fechadas e uma aberta para uma sala de aula. A sala tem uma sequência:
  A) vazia;
  B) cheia de vultos negros de crianças, sentados, virados para o quadro;
  C) os mesmos vultos, com a cabeça virada para a porta.
A sequência vem animada (frames 1–240) e também pode ser controlada à mão pelas coleções.

Uso (dentro do Blender):
    blender -b -P build_scene.py -- --out escola_corredor_sala.blend
Uso (módulo bpy via pip):
    python build_scene.py --out escola_corredor_sala.blend --render previews --samples 64
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

SEED = 1987
rng = random.Random(SEED)

# ---------------------------------------------------------------------------
# Dimensões (metros). O corredor corre ao longo de +Y; as salas ficam à esquerda (-X).
# ---------------------------------------------------------------------------
CX = 1.6                  # meia-largura do corredor
CL = 24.0                 # comprimento do corredor
RH = 3.0                  # altura do teto
DOORS = [(6.0, "101", False), (11.1, "102", True), (18.0, "103", False)]   # (y, número, aberta?)
DOOR_W, DOOR_H = 1.0, 2.2
ROOM_X0, ROOM_X1 = -9.6, -CX          # sala de aula
ROOM_Y0, ROOM_Y1 = 9.4, 17.6
BOARD_Y = ROOM_Y1
DOOR_OPEN_Y = 11.1
SEQ = {"A_ate": 100, "B_de": 106, "B_ate": 172, "C_de": 178}   # frames da sequência
def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="escola_corredor_sala.blend")
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
# Materiais comuns
# ---------------------------------------------------------------------------
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
def mat_linoleum():
    m = Mat("M_Linoleo_Encerado")
    obj = m.texcoord().outputs["Object"]
    chk = m.node("ShaderNodeTexChecker")
    chk.inputs["Scale"].default_value = 1.0
    chk.inputs["Color1"].default_value = (0.32, 0.3, 0.26, 1)
    chk.inputs["Color2"].default_value = (0.1, 0.11, 0.1, 1)
    mp = m.node("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / 0.3 * 0.5, 1 / 0.3 * 0.5, 1)
    m.link(obj, mp.inputs["Vector"])
    m.link(mp.outputs["Vector"], chk.inputs["Vector"])
    speck = m.noise(obj, 80.0, 2.0, 0.5)
    col = m.mix(m.math("MULTIPLY", m.maprange(speck.outputs["Fac"], 0.55, 0.7), 0.3), chk.outputs["Color"], (0.02, 0.02, 0.02))
    dirt = m.maprange(m.noise(obj, 0.8, 6.0, 0.6).outputs["Fac"], 0.4, 0.7)
    col = m.mix(m.math("MULTIPLY", dirt, 0.5), col, (0.06, 0.05, 0.035))
    scuff = m.noise(obj, 4.0, 10.0, 0.7)
    m.set("Base Color", col)
    m.set("Roughness", m.maprange(scuff.outputs["Fac"], 0.3, 0.7, 0.12, 0.45))
    m.set("Normal", m.bump(m.noise(obj, 200.0, 2.0, 0.5).outputs["Fac"], 0.05, 0.002))
    return m.mat


def mat_cinder(name, color, low_color):
    """Blocos de cimento pintados (parede de escola), metade de baixo mais escura."""
    m = Mat(name)
    obj = m.texcoord().outputs["Object"]
    uv = m.texcoord().outputs["UV"]
    br = m.node("ShaderNodeTexBrick", offset=0.5, offset_frequency=2)
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Mortar Size"].default_value = 0.008
    br.inputs["Mortar Smooth"].default_value = 0.5
    br.inputs["Brick Width"].default_value = 0.4
    br.inputs["Row Height"].default_value = 0.2
    br.inputs["Color1"].default_value = (1, 1, 1, 1)
    br.inputs["Color2"].default_value = (0.94, 0.94, 0.94, 1)
    m.link(uv, br.inputs["Vector"])
    z = sep_z(m)
    band = m.maprange(z, 1.18, 1.22)
    paint = m.mix(band, low_color, color)
    col = m.mix(1.0, paint, br.outputs["Color"], "MULTIPLY")
    grime = m.maprange(m.noise(obj, 1.5, 8.0, 0.6).outputs["Fac"], 0.35, 0.75)
    col = m.mix(m.math("MULTIPLY", grime, 0.6), col, (0.04, 0.04, 0.03))
    smp = m.node("ShaderNodeMapping")
    smp.inputs["Scale"].default_value = (6.0, 6.0, 0.5)
    m.link(obj, smp.inputs["Vector"])
    streak = m.maprange(m.noise(smp.outputs["Vector"], 2.0, 3.0, 0.5).outputs["Fac"], 0.55, 0.72)
    col = m.mix(m.math("MULTIPLY", streak, 0.5), col, (0.03, 0.028, 0.02))
    m.set("Base Color", col)
    m.set("Roughness", 0.6)
    h = m.math("SUBTRACT", m.math("MULTIPLY", m.noise(obj, 90.0, 3.0, 0.6).outputs["Fac"], 0.3), br.outputs["Fac"])
    m.set("Normal", m.bump(h, 0.4, 0.005))
    return m.mat


def mat_ceiling_tiles():
    m = Mat("M_Teto_Placas")
    obj = m.texcoord().outputs["Object"]
    br = m.node("ShaderNodeTexBrick", offset=0.0)
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Mortar Size"].default_value = 0.012
    br.inputs["Brick Width"].default_value = 0.6
    br.inputs["Row Height"].default_value = 1.2
    br.inputs["Color1"].default_value = (0.5, 0.49, 0.45, 1)
    br.inputs["Color2"].default_value = (0.46, 0.45, 0.42, 1)
    br.inputs["Mortar"].default_value = (0.3, 0.3, 0.3, 1)
    m.link(obj, br.inputs["Vector"])
    stain = m.maprange(m.noise(obj, 0.9, 6.0, 0.65).outputs["Fac"], 0.58, 0.68)
    col = m.mix(m.math("MULTIPLY", stain, 0.6), br.outputs["Color"], (0.2, 0.16, 0.09))
    m.set("Base Color", col)
    m.set("Roughness", 0.95)
    m.set("Normal", m.bump(m.noise(obj, 120.0, 3.0, 0.6).outputs["Fac"], 0.3, 0.003))
    return m.mat


def mat_locker():
    m = Mat("M_Cacifo_Metal_Pintado")
    obj = m.texcoord().outputs["Object"]
    base = m.ramp(m.noise(obj, 3.0, 4.0, 0.5).outputs["Fac"], [(0.3, (0.07, 0.12, 0.15)), (0.7, (0.1, 0.16, 0.19))])
    scratch_map = m.node("ShaderNodeMapping")
    scratch_map.inputs["Scale"].default_value = (30.0, 30.0, 2.0)
    m.link(obj, scratch_map.inputs["Vector"])
    scr = m.maprange(m.noise(scratch_map.outputs["Vector"], 3.0, 4.0, 0.6).outputs["Fac"], 0.66, 0.7)
    col = m.mix(scr, base.outputs["Color"], (0.3, 0.3, 0.3))
    rust = m.maprange(m.noise(obj, 6.0, 8.0, 0.7).outputs["Fac"], 0.66, 0.74)
    col = m.mix(rust, col, (0.1, 0.045, 0.02))
    m.set("Base Color", col)
    m.set("Metallic", m.mixf(m.math("MAXIMUM", scr, rust), 0.55, 0.9))
    m.set("Roughness", m.mixf(scr, 0.4, 0.25))
    m.set("Normal", m.bump(m.math("ADD", scr, m.noise(obj, 40.0, 3.0, 0.6).outputs["Fac"]), 0.15, 0.002))
    return m.mat


def mat_chalkboard():
    m = Mat("M_Quadro_Ardosia")
    obj = m.texcoord().outputs["Object"]
    smear = m.noise(obj, 2.0, 6.0, 0.6)
    col = m.ramp(smear.outputs["Fac"], [(0.3, (0.018, 0.035, 0.028)), (0.7, (0.05, 0.075, 0.065))])
    m.set("Base Color", col.outputs["Color"])
    m.set("Roughness", 0.85)
    return m.mat


def mat_figure():
    """Pele dos vultos: negro absoluto, fosco, com uma aspereza leve."""
    m = Mat("M_Vulto_Negro")
    m.set("Base Color", (0.0015, 0.0015, 0.002))
    m.set("Roughness", 0.95)
    m.set("Specular IOR Level", 0.05)
    m.set("Normal", m.bump(m.noise(m.texcoord().outputs["Object"], 18.0, 6.0, 0.6).outputs["Fac"], 0.3, 0.01))
    return m.mat


def mat_smoke():
    """Fumo negro à volta dos vultos (volume absorvente, esbatido para as bordas)."""
    mat = bpy.data.materials.new("M_Vulto_Fumo")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new
    out = N("ShaderNodeOutputMaterial")
    vol = N("ShaderNodeVolumePrincipled")
    vol.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1)
    vol.inputs["Absorption Color"].default_value = (0.0, 0.0, 0.0, 1)
    tc = N("ShaderNodeTexCoord")
    nz = N("ShaderNodeTexNoise")
    nz.noise_dimensions = "4D"
    nz.inputs["Scale"].default_value = 3.5
    nz.inputs["Detail"].default_value = 6.0
    nz.inputs["Roughness"].default_value = 0.65
    L(tc.outputs["Object"], nz.inputs["Vector"])
    nz.inputs["W"].default_value = 0.0
    nz.inputs["W"].keyframe_insert("default_value", frame=1)
    nz.inputs["W"].default_value = 4.0
    nz.inputs["W"].keyframe_insert("default_value", frame=240)
    grad = N("ShaderNodeTexGradient")
    grad.gradient_type = "SPHERICAL"
    L(tc.outputs["Object"], grad.inputs["Vector"])
    mr = N("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = 0.45
    mr.inputs["From Max"].default_value = 0.75
    mr.inputs["To Min"].default_value = 0.0
    mr.inputs["To Max"].default_value = 40.0
    L(nz.outputs["Fac"], mr.inputs["Value"])
    mul = N("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    L(mr.outputs["Result"], mul.inputs[0])
    pw = N("ShaderNodeMath")
    pw.operation = "POWER"
    L(grad.outputs["Fac"], pw.inputs[0])
    pw.inputs[1].default_value = 1.6
    L(pw.outputs[0], mul.inputs[1])
    L(mul.outputs[0], vol.inputs["Density"])
    L(vol.outputs[0], out.inputs["Volume"])
    return mat


def mat_static():
    """Estática de TV animada."""
    m = Mat("M_TV_Estatica")
    nz = m.node("ShaderNodeTexNoise", noise_dimensions="4D")
    nz.inputs["Scale"].default_value = 600.0
    nz.inputs["Detail"].default_value = 0.0
    m.link(m.texcoord().outputs["UV"], nz.inputs["Vector"])
    nz.inputs["W"].default_value = 0.0
    nz.inputs["W"].keyframe_insert("default_value", frame=1)
    nz.inputs["W"].default_value = 480.0
    nz.inputs["W"].keyframe_insert("default_value", frame=240)
    for fc in iter_fcurves(m.mat.node_tree.animation_data.action):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    v = m.maprange(nz.outputs["Fac"], 0.35, 0.65)
    m.set("Base Color", (0, 0, 0))
    m.set("Emission Color", m.mix(v, (0.02, 0.02, 0.025), (0.85, 0.9, 1.0)))
    m.set("Emission Strength", 2.5)
    return m.mat


def make_drawing(i):
    """Desenho infantil a lápis de cera (casa, sol, figuras de pau… e uma figura negra)."""
    W, H = 360, 270
    r = np.random.default_rng(300 + i)
    px = np.ones((H, W, 3), np.float32) * np.array([0.9, 0.88, 0.8], np.float32)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)

    def stroke(p0, p1, col, w=3.0):
        p0, p1 = np.array(p0, np.float32), np.array(p1, np.float32)
        d = p1 - p0
        ln = max(np.linalg.norm(d), 1e-3)
        t = np.clip(((xx - p0[0]) * d[0] + (yy - p0[1]) * d[1]) / (ln * ln), 0, 1)
        dist = np.sqrt((xx - p0[0] - t * d[0]) ** 2 + (yy - p0[1] - t * d[1]) ** 2)
        a = np.clip(w - dist, 0, 1) * (0.6 + 0.4 * r.random())
        px[:] = px * (1 - a[..., None]) + np.array(col, np.float32) * a[..., None]

    # relva e sol
    for x in range(0, W, 6):
        stroke((x, 20), (x + r.uniform(-3, 3), 20 + r.uniform(8, 18)), (0.1, 0.5, 0.1), 2)
    cx, cy = r.uniform(40, 90), r.uniform(200, 240)
    for k in range(10):
        a = k * math.pi / 5
        stroke((cx, cy), (cx + math.cos(a) * 30, cy + math.sin(a) * 30), (0.95, 0.75, 0.1), 3)
    # casa
    hx = r.uniform(150, 220)
    for p0, p1 in (((hx, 25), (hx + 80, 25)), ((hx, 25), (hx, 95)), ((hx + 80, 25), (hx + 80, 95)), ((hx, 95), (hx + 40, 140)),
                   ((hx + 40, 140), (hx + 80, 95)), ((hx, 95), (hx + 80, 95))):
        stroke(p0, p1, (0.7, 0.1, 0.1), 3)
    # família de pau…
    fx = r.uniform(40, 120)
    n = r.integers(2, 4)
    for k in range(n):
        x = fx + k * 28
        stroke((x, 30), (x, 70), (0.1, 0.15, 0.6), 2.5)
        stroke((x - 12, 55), (x + 12, 55), (0.1, 0.15, 0.6), 2.5)
        stroke((x, 30), (x - 9, 12), (0.1, 0.15, 0.6), 2.5)
        stroke((x, 30), (x + 9, 12), (0.1, 0.15, 0.6), 2.5)
        stroke((x - 7, 78), (x + 7, 78), (0.1, 0.15, 0.6), 7)
    # …e uma figura toda riscada a preto, maior que as outras
    bx = fx + n * 28 + 30
    for _ in range(60):
        stroke((bx + r.uniform(-12, 12), r.uniform(12, 110)), (bx + r.uniform(-12, 12), r.uniform(12, 110)), (0.02, 0.02, 0.02), 2.5)
    return make_image(f"DESENHO_{i}", np.clip(px, 0, 1) ** 2.2)


# ---------------------------------------------------------------------------
# Construção
# ---------------------------------------------------------------------------
def uv_walls(obj):
    """UV em metros projetadas nas paredes (para o padrão de blocos)."""
    me = obj.data
    uv = me.uv_layers.get("UVMap") or me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        n = poly.normal
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            if abs(n.x) > abs(n.y):
                uv.data[li].uv = (co.y, co.z)
            else:
                uv.data[li].uv = (co.x, co.z)


def build_shell(col, mats):
    b = Builder()
    holes_left = [(y - DOOR_W / 2, y + DOOR_W / 2, 0.0, DOOR_H) for y, _, _ in DOORS]
    wall_pieces(b, "x", -CX, (0.0, CL), holes_left)
    wall_pieces(b, "x", CX, (0.0, CL), [])
    wall_pieces(b, "y", 0.0 - 0.0001, (-CX - 0.15, CX + 0.15), [])
    wall_pieces(b, "y", CL, (-CX - 0.15, CX + 0.15), [(-1.0, 1.0, 0.0, 2.3)])
    # sala de aula
    wall_pieces(b, "x", ROOM_X0, (ROOM_Y0, ROOM_Y1), [(ROOM_Y0 + 1.2, ROOM_Y0 + 2.6, 1.0, 2.5), (ROOM_Y0 + 3.4, ROOM_Y0 + 4.8, 1.0, 2.5),
                                                      (ROOM_Y0 + 5.6, ROOM_Y0 + 7.0, 1.0, 2.5)])
    wall_pieces(b, "y", ROOM_Y0, (ROOM_X0 - 0.15, -CX), [])
    wall_pieces(b, "y", ROOM_Y1, (ROOM_X0 - 0.15, -CX), [])
    shell = b.to_object("Paredes", col, [mats["wall"]])
    # a parede de y=0 é criada com espessura para trás da câmara; nada a fazer
    uv_walls(shell)
    b = Builder()
    b.box((0, CL / 2, -0.05), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (2 * CX + 0.3, CL, 0.1))
    b.box(((ROOM_X0 + ROOM_X1) / 2, (ROOM_Y0 + ROOM_Y1) / 2, -0.05), ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
          (ROOM_X1 - ROOM_X0 + 0.3, ROOM_Y1 - ROOM_Y0, 0.1))
    b.to_object("Chao_Linoleo", col, [mats["floor"]])
    b = Builder()
    b.box((0, CL / 2, RH + 0.05), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (2 * CX + 0.3, CL, 0.1))
    b.box(((ROOM_X0 + ROOM_X1) / 2, (ROOM_Y0 + ROOM_Y1) / 2, RH + 0.05), ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
          (ROOM_X1 - ROOM_X0 + 0.3, ROOM_Y1 - ROOM_Y0, 0.1))
    b.to_object("Teto_Placas", col, [mats["ceiling"]])
    # rodapés
    b = Builder()
    for x in (-CX + 0.01, CX - 0.01):
        b.box((x, CL / 2, 0.06), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.02, CL, 0.12))
    b.to_object("Rodapes", col, [mats["rubber"]])


def build_lockers(col, mats):
    """Filas de cacifos metálicos; um deles entreaberto."""
    doors = Builder()
    bodies = Builder()
    handles = Builder()
    open_one = (CX, 4.35)
    segs = [(CX, 0.4, 23.6, -1)]
    edges = [0.4] + sum(([y - DOOR_W / 2 - 0.25, y + DOOR_W / 2 + 0.25] for y, _, _ in DOORS), []) + [23.6]
    for a, c in zip(edges[0::2], edges[1::2]):
        segs.append((-CX, a, c, 1))
    lw, lh, ld = 0.31, 1.82, 0.38
    for x_wall, y0, y1, side in segs:
        n = int((y1 - y0) / lw)
        xf = x_wall + side * ld      # frente dos cacifos
        bodies.box((x_wall + side * ld / 2, (y0 + y0 + n * lw) / 2, 0.1 + lh / 2), ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
                   (ld, n * lw, lh))
        bodies.box((x_wall + side * ld / 2, (y0 + y0 + n * lw) / 2, 0.05), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (ld - 0.04, n * lw, 0.1), mat=1)
        for k in range(n):
            yc = y0 + (k + 0.5) * lw
            is_open = abs(x_wall - open_one[0]) < 0.01 and abs(yc - open_one[1]) < lw / 2
            hinge_y = yc - lw / 2 + 0.01
            ang = math.radians(62) if is_open else 0.0
            R = Euler((0, 0, -side * ang)).to_matrix()
            dcen = Vector((xf + side * 0.012, hinge_y, 0.1 + lh / 2)) + R @ Vector((0, lw / 2 - 0.01, 0))
            ax = (R @ Vector((1, 0, 0)), R @ Vector((0, 1, 0)), (0, 0, 1))
            doors.box(dcen, ax, (0.02, lw - 0.012, lh - 0.02))
            for v in range(6):   # grelha de ventilação
                p = dcen + R @ Vector((side * 0.011, 0, lh / 2 - 0.12 - v * 0.03))
                handles.box(p, ax, (0.004, lw * 0.6, 0.01), mat=1)
            handles.box(dcen + R @ Vector((side * 0.02, lw / 2 - 0.06, 0.05)), ax, (0.03, 0.025, 0.16), mat=0)
            handles.box(dcen + R @ Vector((side * 0.015, 0.0, -0.45)), ax, (0.004, 0.08, 0.05), mat=2)   # etiqueta
    doors.to_object("Cacifos_Portas", col, [mats["locker"]]).modifiers.new("Bevel", "BEVEL").width = 0.003
    bodies.to_object("Cacifos_Corpo", col, [mats["locker"], mats["rubber"]])
    handles.to_object("Cacifos_Puxadores_Grelhas", col, [mats["steel"], mats["black"], mats["paper"]])
    # interior escuro do cacifo aberto, com a manga de um casaco a sair
    b = Builder()
    k = int((open_one[1] - 0.4) / lw)
    yc = 0.4 + (k + 0.5) * lw
    b.box((CX - ld - 0.004, yc, 0.1 + lh / 2), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.006, lw - 0.03, lh - 0.05), mat=0)
    b.ico((CX - ld - 0.03, yc + 0.02, 1.35), 0.1, (0.5, 0.9, 2.2), 3, 0.25, mat=1)
    b.cylinder((CX - ld - 0.06, yc - 0.03, 1.2), (CX - ld - 0.12, yc - 0.07, 0.72), 0.04, 0.035, 10, mat=1)
    b.to_object("Cacifo_Aberto_Interior_Casaco", col, [mats["black"], mats["coat"]], smooth=True)


def build_doors(col, mats, c_light):
    for i, (y, num, is_open) in enumerate(DOORS):
        x = -CX
        b = Builder()
        for (cy, cz, dy, dz) in ((y - DOOR_W / 2 - 0.04, DOOR_H / 2, 0.08, DOOR_H + 0.08), (y + DOOR_W / 2 + 0.04, DOOR_H / 2, 0.08, DOOR_H + 0.08),
                                 (y, DOOR_H + 0.04, DOOR_W + 0.16, 0.08)):
            b.box((x + 0.02, cy, cz), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.08, dy, dz))
        b.to_object(f"Porta_{num}_Aro", col, [mats["frame"]])
        # folha da porta com janela de vidro aramado
        hinge = Vector((x - 0.03, y - DOOR_W / 2 + 0.02, 0))
        ang = math.radians(72) if is_open else 0.0       # abre para dentro da sala
        R = Euler((0, 0, ang)).to_matrix()
        M = Matrix.Translation(hinge) @ R.to_4x4()
        b = Builder()
        w, h, t = DOOR_W - 0.04, DOOR_H - 0.02, 0.045
        gx0, gx1, gz0, gz1 = 0.3, 0.7, 1.25, 1.9
        for (cy, cz, dy, dz) in ((w / 2, gz0 / 2, w, gz0), (w / 2, (gz1 + h) / 2, w, h - gz1), (gx0 / 2, (gz0 + gz1) / 2, gx0, gz1 - gz0),
                                 ((gx1 + w) / 2, (gz0 + gz1) / 2, w - gx1, gz1 - gz0)):
            b.box((0, cy, cz), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (t, dy, dz), M=M)
        b.to_object(f"Porta_{num}_Folha", col, [mats["door_wood"]]).modifiers.new("Bevel", "BEVEL").width = 0.004
        b = Builder()
        b.box((0.005, (gx0 + gx1) / 2, (gz0 + gz1) / 2), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.006, gx1 - gx0, gz1 - gz0), M=M)
        g = b.to_object(f"Porta_{num}_Vidro_Aramado", col, [mats["wired_glass"]])
        g.visible_shadow = False
        b = Builder()
        b.cylinder(M @ Vector((0.04, w - 0.08, 1.0)), M @ Vector((0.1, w - 0.08, 1.0)), 0.012, 0.012, 10)
        b.box(M @ Vector((0.1, w - 0.14, 1.0)), (R @ Vector((1, 0, 0)), R @ Vector((0, 1, 0)), (0, 0, 1)), (0.02, 0.14, 0.025))
        b.to_object(f"Porta_{num}_Macaneta", col, [mats["steel"]], smooth=True)
        # número da sala
        cu = bpy.data.curves.new(f"Porta_{num}_Numero", "FONT")
        cu.body = num
        cu.size = 0.09
        cu.align_x = "CENTER"
        cu.materials.append(mats["black"])
        t_ = new_object(f"Porta_{num}_Numero", cu, col)
        t_.location = (x + 0.012, y, DOOR_H + 0.18)
        t_.rotation_euler = (math.radians(90), 0, math.radians(90))
        b = Builder()
        b.box((x + 0.005, y, DOOR_H + 0.21), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.01, 0.28, 0.16))
        b.to_object(f"Porta_{num}_Placa", col, [mats["paper"]])
        if not is_open:
            # escuridão atrás do vidro e uma mão pequena encostada por dentro
            me = bpy.data.meshes.new(f"Sala_{num}_Escuro")
            me.from_pydata([(x - 0.5, y - 0.6, 0.0), (x - 0.5, y + 0.6, 0.0), (x - 0.5, y + 0.6, 2.4), (x - 0.5, y - 0.6, 2.4)], [], [(0, 1, 2, 3)])
            me.materials.append(mats["black"])
            new_object(f"Sala_{num}_Escuro", me, col)
            if num == "103":
                b = Builder()
                hand_c = Vector((x - 0.07, y - 0.02, 1.52))
                b.ico(hand_c, 0.045, (0.25, 0.9, 1.0), 2, 0.1)
                for k, (dy, dz, ln) in enumerate(((-0.03, 0.05, 0.05), (-0.01, 0.065, 0.06), (0.01, 0.065, 0.062), (0.03, 0.055, 0.055),
                                                 (0.048, 0.0, 0.045))):
                    b.cylinder(hand_c + Vector((0, dy, dz * 0.5)), hand_c + Vector((0, dy * 1.2, dz + ln * 0.5)), 0.009, 0.008, 6)
                b.to_object("Mao_Atras_Do_Vidro_103", col, [mats["hand_pale"]], smooth=True)


def build_corridor_props(col, mats):
    # quadro de cortiça com avisos e desenhos infantis (parede direita, por cima dos cacifos)
    b = Builder()
    y0 = 7.5
    b.box((CX - 0.02, y0 + 1.2, 2.45), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.03, 2.4, 0.9), mat=0)
    b.to_object("Corredor_Quadro_Avisos", col, [mats["cork"]])
    for i in range(6):
        img = make_drawing(i)
        yy = y0 + 0.25 + i * 0.38 + rng.uniform(-0.03, 0.03)
        zz = 2.45 + rng.uniform(-0.2, 0.2)
        R = Euler((rng.uniform(-0.08, 0.08), 0, 0)).to_matrix()
        corners = [Vector((CX - 0.04, yy, zz)) + R @ Vector((0, sy * 0.16, sz * 0.12)) for sy, sz in ((1, -1), (-1, -1), (-1, 1), (1, 1))]
        me = bpy.data.meshes.new(f"Desenho_{i}")
        me.from_pydata([tuple(c) for c in corners], [], [(0, 1, 2, 3)])
        me.uv_layers.new(name="UVMap").data.foreach_set("uv", [1, 0, 0, 0, 0, 1, 1, 1])
        me.materials.append(mat_image(f"M_Desenho_{i}", img, rough=0.8))
        new_object(f"Desenho_Infantil_{i}", me, col)
    # cartaz de desaparecida
    b = Builder()
    b.box((CX - 0.035, 14.2, 2.35), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.004, 0.45, 0.6))
    b.box((CX - 0.04, 14.2, 2.38), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.004, 0.26, 0.28), mat=1)
    b.to_object("Cartaz_Desaparecida", col, [mats["paper"], mats["photo_dark"]])
    for k, (txt, size, z) in enumerate((("MISSING", 0.07, 2.56), ("HAVE YOU SEEN ME?", 0.028, 2.14))):
        cu = bpy.data.curves.new(f"Cartaz_Texto_{k}", "FONT")
        cu.body = txt
        cu.size = size
        cu.align_x = "CENTER"
        cu.materials.append(mats["black"])
        t_ = new_object(f"Cartaz_Texto_{k}", cu, col)
        t_.location = (CX - 0.043, 14.2, z)
        t_.rotation_euler = (math.radians(90), 0, math.radians(-90))
    # bebedouro e caixote do lixo
    b = Builder()
    b.box((CX - 0.2, 16.3, 0.85), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.35, 0.45, 0.25))
    b.box((CX - 0.1, 16.3, 0.45), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.12, 0.25, 0.6))
    b.to_object("Bebedouro", col, [mats["steel"]]).modifiers.new("Bevel", "BEVEL").width = 0.02
    # saída de emergência ao fundo
    b = Builder()
    for sx in (-0.5, 0.5):
        b.box((sx, CL - 0.03, 1.15), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.98, 0.05, 2.28))
        b.box((sx - 0.3 * sx / abs(sx), CL - 0.07, 1.05), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.7, 0.04, 0.06), mat=1)
    b.to_object("Portas_Saida", col, [mats["locker"], mats["steel"]])
    b = Builder()
    b.box((0, CL - 0.08, 2.55), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.5, 0.08, 0.2))
    b.to_object("Sinal_EXIT_Caixa", col, [mats["exit_green"]])
    cu = bpy.data.curves.new("Sinal_EXIT", "FONT")
    cu.body = "EXIT"
    cu.size = 0.13
    cu.align_x = "CENTER"
    cu.materials.append(mats["white_emit"])
    t_ = new_object("Sinal_EXIT", cu, col)
    t_.location = (0, CL - 0.125, 2.5)
    t_.rotation_euler = (math.radians(90), 0, 0)
    gl = light("LUZ_EXIT_Verde", "AREA", col, (0, CL - 0.3, 2.45), 6.0, (0.2, 1.0, 0.35), size=0.5, size_y=0.2)
    gl.rotation_euler = look_at_rotation(gl.location, (0, CL - 3.0, 0.5))
    gl.visible_camera = False


def fixture(b_house, b_diff, loc, length=1.2, width=0.28):
    b_house.box(loc + Vector((0, 0, -0.03)), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (width, length, 0.06))
    b_diff.box(loc + Vector((0, 0, -0.065)), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (width - 0.04, length - 0.04, 0.01))


def flicker(id_data, path, on, pattern_seed, frames=240, dark_spans=(), owner=None):
    r_ = random.Random(pattern_seed)
    f = 1
    state = on
    id_data.__setattr__(path, on)
    id_data.keyframe_insert(path, frame=1)
    while f < frames:
        # longos períodos acesa, curtos trémulos
        f += r_.randint(8, 40)
        for _ in range(r_.randint(1, 4)):
            setattr(id_data, path, on * r_.uniform(0.0, 0.25))
            id_data.keyframe_insert(path, frame=f)
            f += r_.randint(1, 2)
            setattr(id_data, path, on)
            id_data.keyframe_insert(path, frame=f)
            f += r_.randint(1, 3)
    for a, c in dark_spans:
        for fr in range(a, c + 1):
            setattr(id_data, path, 0.0)
            id_data.keyframe_insert(path, frame=fr)
        setattr(id_data, path, on)
        id_data.keyframe_insert(path, frame=c + 1)
    for fc in iter_fcurves((owner or id_data).animation_data.action):
        for kp in fc.keyframe_points:
            kp.interpolation = "CONSTANT"


def build_lights(col, mats):
    """Fluorescentes do corredor e da sala: algumas acesas, uma a piscar, as do fundo mortas."""
    house, diff_on, diff_off = Builder(), Builder(), Builder()
    states = {2.0: "on", 5.0: "on", 8.0: "flicker", 11.0: "dim", 14.0: "on", 17.0: "dim", 20.0: "off", 23.0: "off"}
    for y, st in states.items():
        loc = Vector((0, y, RH))
        tgt = diff_off if st == "off" else diff_on
        if st == "flicker":
            b = Builder()
            fixture(house, b, loc)
            fl_obj = b.to_object("Fluorescente_Corredor_Pisca", col, [mats["tube_flicker_c"]])
        else:
            fixture(house, tgt, loc)
        if st != "off":
            e = {"on": 30.0, "dim": 12.0, "flicker": 30.0}[st]
            ld = light(f"LUZ_Corredor_{y:.0f}", "AREA", col, loc - Vector((0, 0, 0.08)), e, (0.85, 1.0, 0.9), shape="RECTANGLE",
                       size=0.22, size_y=1.15)
            ld.visible_camera = False
            if st == "flicker":
                flicker(ld.data, "energy", e, 3)
    # sala de aula: grelha 2×3, só a da frente (junto ao quadro) acesa e a falhar
    room_on = None
    for i, x in enumerate((-7.4, -3.8)):
        for j, y in enumerate((11.3, 13.5, 15.7)):
            loc = Vector((x, y, RH))
            if (i, j) == (1, 2):
                b = Builder()
                fixture(house, b, loc)
                b.to_object("Fluorescente_Sala_Pisca", col, [mats["tube_flicker_r"]])
                room_on = light("LUZ_Sala_Fluorescente", "AREA", col, loc - Vector((0, 0, 0.08)), 55.0, (0.85, 1.0, 0.9),
                                shape="RECTANGLE", size=0.22, size_y=1.15)
                room_on.visible_camera = False
            else:
                fixture(house, diff_off, loc)
    house.to_object("Luminarias_Caixas", col, [mats["steel"]])
    diff_on.to_object("Luminarias_Difusores_Acesos", col, [mats["tube_on"]])
    diff_off.to_object("Luminarias_Difusores_Apagados", col, [mats["tube_off"]])
    # a luz da sala apaga nas transições A→B e B→C
    darks = ((SEQ["A_ate"], SEQ["B_de"] - 1), (SEQ["B_ate"], SEQ["C_de"] - 1))
    flicker(room_on.data, "energy", 55.0, 7, dark_spans=darks)
    nt = mats["tube_flicker_r"].node_tree
    flicker(nt.nodes["Principled BSDF"].inputs["Emission Strength"], "default_value", 8.0, 7, dark_spans=darks, owner=nt)
    nt = mats["tube_flicker_c"].node_tree
    flicker(nt.nodes["Principled BSDF"].inputs["Emission Strength"], "default_value", 8.0, 3, owner=nt)
    return room_on


def build_classroom(col, mats):
    x0, x1, y0, y1 = ROOM_X0, ROOM_X1 - 0.15, ROOM_Y0, ROOM_Y1
    # quadro de ardósia e moldura
    bx = (x0 + x1) / 2
    b = Builder()
    b.box((bx, y1 - 0.03, 1.55), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (4.6, 0.03, 1.25), mat=0)
    b.box((bx, y1 - 0.08, 0.92), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (4.6, 0.09, 0.03), mat=1)
    for dz, dx in ((2.19, 0), ):
        b.box((bx, y1 - 0.04, dz), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (4.7, 0.05, 0.04), mat=1)
    for sx in (-2.33, 2.33):
        b.box((bx + sx, y1 - 0.04, 1.55), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.04, 0.05, 1.3), mat=1)
    b.to_object("Quadro_Ardosia", col, [mats["chalkboard"], mats["frame"]])
    # frase de castigo a giz
    for k in range(7):
        cu = bpy.data.curves.new(f"Giz_Linha_{k}", "FONT")
        cu.body = "I WILL NOT LEAVE THE ROOM."
        cu.size = 0.105
        cu.materials.append(mats["chalk"])
        t_ = new_object(f"Giz_Linha_{k}", cu, col)
        t_.location = (bx - 1.95 + rng.uniform(-0.03, 0.05), y1 - 0.05, 2.02 - k * 0.155)
        t_.rotation_euler = (math.radians(90), rng.uniform(-0.015, 0.015), 0.0)
    # faixa do alfabeto por cima do quadro
    cu = bpy.data.curves.new("Alfabeto", "FONT")
    cu.body = "Aa Bb Cc Dd Ee Ff Gg Hh Ii Jj Kk Ll Mm"
    cu.size = 0.09
    cu.align_x = "CENTER"
    cu.materials.append(mats["alpha_red"])
    t_ = new_object("Faixa_Alfabeto", cu, col)
    t_.location = (bx, y1 - 0.02, 2.45)
    t_.rotation_euler = (math.radians(90), 0, 0)
    # relógio parado às 3:33
    b = Builder()
    ck = Vector((bx + 2.9, y1 - 0.03, 2.45))
    b.cylinder(ck, ck + Vector((0, -0.05, 0)), 0.17, 0.17, 32, mat=0)
    b.cylinder(ck + Vector((0, -0.051, 0)), ck + Vector((0, -0.052, 0)), 0.155, 0.155, 32, mat=1)
    for ang, ln, wd in ((math.radians(90 - (3 * 30 + 33 * 0.5)), 0.085, 0.007), (math.radians(90 - 33 * 6), 0.13, 0.004)):
        p0 = ck + Vector((0, -0.056, 0))
        p1 = p0 + Vector((math.cos(ang) * ln, 0, math.sin(ang) * ln))
        b.box((p0 + p1) / 2, ((p1 - p0).normalized(), (0, 1, 0), (p1 - p0).normalized().cross(Vector((0, 1, 0)))), (ln, 0.002, wd), mat=2)
    b.to_object("Sala_Relogio_333", col, [mats["black"], mats["paper"], mats["black"]], smooth=True)
    # secretária da professora
    b = Builder()
    td = Vector((bx + 1.2, y1 - 1.3, 0))
    b.box(td + Vector((0, 0, 0.74)), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (1.4, 0.7, 0.04))
    b.box(td + Vector((-0.5, 0, 0.36)), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.4, 0.66, 0.72))
    b.box(td + Vector((0.2, 0.32, 0.4)), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (1.0, 0.03, 0.66))
    b.to_object("Secretaria_Professora", col, [mats["desk_wood"]]).modifiers.new("Bevel", "BEVEL").width = 0.005
    b = Builder()
    b.box(td + Vector((0.2, -0.05, 0.765)), (Vector((1, 0.2, 0)).normalized(), Vector((-0.2, 1, 0)).normalized(), (0, 0, 1)), (0.3, 0.22, 0.012), mat=0)
    b.ico(td + Vector((0.45, -0.1, 0.8)), 0.04, (1, 1, 0.95), 2, 0.1, mat=1)   # maçã
    b.cylinder(td + Vector((-0.55, 0.2, 0.76)), td + Vector((-0.55, 0.2, 0.85)), 0.012, 0.012, 8, mat=2)
    b.ico(td + Vector((-0.55, 0.2, 1.02)), 0.14, (1, 1, 1), 3, 0.0, mat=3)     # globo
    b.to_object("Secretaria_Objetos", col, [mats["paper"], mats["apple"], mats["steel"], mats["globe"]], smooth=True)
    # carteiras
    desks = Builder()
    chairs = Builder()
    seats = []
    cols_x = [-8.3, -6.9, -5.5, -4.1, -2.7]
    rows_y = [11.1, 12.5, 13.9, 15.3]
    for ri, y in enumerate(rows_y):
        for ci, x in enumerate(cols_x):
            if ci == 4 and ri == 0:
                continue   # espaço junto à porta
            jit = Vector((rng.gauss(0, 0.04), rng.gauss(0, 0.04), 0))
            yaw = rng.gauss(0, 0.04)
            R = Euler((0, 0, yaw)).to_matrix()
            dc = Vector((x, y + 0.45, 0)) + jit
            desks.box(dc + R @ Vector((0, 0, 0.72)), (R @ Vector((1, 0, 0)), R @ Vector((0, 1, 0)), (0, 0, 1)), (0.62, 0.45, 0.025))
            desks.box(dc + R @ Vector((0, 0.05, 0.64)), (R @ Vector((1, 0, 0)), R @ Vector((0, 1, 0)), (0, 0, 1)), (0.58, 0.35, 0.12), mat=1)
            for sx in (-0.27, 0.27):
                for sy in (-0.18, 0.18):
                    desks.cylinder(dc + R @ Vector((sx, sy, 0)), dc + R @ Vector((sx, sy, 0.62)), 0.012, 0.012, 8, mat=2)
            # cadeira: algumas afastadas, uma caída
            cjit = Vector((rng.gauss(0, 0.05), -rng.uniform(0, 0.15), 0))
            cc = Vector((x, y - 0.05, 0)) + jit + cjit
            fallen = (ri, ci) == (1, 1)
            Rc = Euler((math.radians(-90) if fallen else 0, 0, yaw + rng.gauss(0, 0.12))).to_matrix()
            base = cc + (Vector((0, -0.3, 0.2)) if fallen else Vector((0, 0, 0)))
            for (p, d) in (((0, 0, 0.44), (0.4, 0.38, 0.025)), ((0, -0.19, 0.7), (0.38, 0.02, 0.26))):
                chairs.box(base + Rc @ Vector(p), (Rc @ Vector((1, 0, 0)), Rc @ Vector((0, 1, 0)), Rc @ Vector((0, 0, 1))), d)
            for sx in (-0.17, 0.17):
                for sy in (-0.16, 0.16):
                    chairs.cylinder(base + Rc @ Vector((sx, sy, 0)), base + Rc @ Vector((sx, sy, 0.43)), 0.011, 0.011, 8, mat=1)
                chairs.cylinder(base + Rc @ Vector((sx, -0.18, 0.44)), base + Rc @ Vector((sx, -0.19, 0.83)), 0.011, 0.011, 8, mat=1)
            if not fallen:
                seats.append((cc + Vector((0, 0.02, 0)), yaw))
    desks.to_object("Carteiras", col, [mats["desk_top"], mats["desk_steel_dark"], mats["steel"]])
    chairs.to_object("Cadeiras", col, [mats["chair_plastic"], mats["steel"]])
    # janelas com persianas meio descidas e a noite lá fora
    b = Builder()
    sl = Builder()
    for wy in (ROOM_Y0 + 1.9, ROOM_Y0 + 4.1, ROOM_Y0 + 6.3):
        for (cy, cz, dy, dz) in ((wy, 1.0, 1.44, 0.06), (wy, 2.5, 1.44, 0.06), (wy - 0.7, 1.75, 0.06, 1.5), (wy + 0.7, 1.75, 0.06, 1.5),
                                 (wy, 1.75, 0.04, 1.5)):
            b.box((x0 + 0.02, cy, cz), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.08, dy, dz))
        drop = rng.uniform(0.5, 1.1)
        n = int(drop / 0.04)
        for k in range(n):
            z = 2.45 - k * 0.04
            u = Vector((0, 1, 0))
            v = Vector((math.cos(0.5), 0, math.sin(0.5)))
            sl.box((x0 + 0.1, wy, z), (u, v, u.cross(v)), (1.38, 0.04, 0.003))
    b.box((x0 + 0.08, (ROOM_Y0 + ROOM_Y1) / 2, 0.97), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.25, ROOM_Y1 - ROOM_Y0 - 0.4, 0.05))
    b.to_object("Janelas_Caixilhos", col, [mats["frame"]])
    sl.to_object("Janelas_Persianas", col, [mats["blinds"]])
    me = bpy.data.meshes.new("Noite_Fora")
    xb = x0 - 3.0
    me.from_pydata([(xb, ROOM_Y0 - 3, -1), (xb, ROOM_Y1 + 3, -1), (xb, ROOM_Y1 + 3, 5), (xb, ROOM_Y0 - 3, 5)], [], [(0, 1, 2, 3)])
    me.materials.append(mats["night_sky"])
    bg = new_object("Noite_Fora_Fundo", me, col)
    bg.visible_diffuse = False
    bg.visible_shadow = False
    moon = light("LUZ_Luar_Janelas", "AREA", col, (x0 - 1.2, (ROOM_Y0 + ROOM_Y1) / 2, 2.6), 90.0, (0.45, 0.55, 0.9),
                 shape="RECTANGLE", size=1.0, size_y=6.5)
    moon.rotation_euler = look_at_rotation(moon.location, (x0 + 4.0, (ROOM_Y0 + ROOM_Y1) / 2, 0.3))
    # TV num carrinho, com estática
    tv_pos = Vector((x1 - 0.7, y1 - 0.9, 0))
    b = Builder()
    b.box(tv_pos + Vector((0, 0, 0.82)), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.7, 0.5, 0.03))
    b.box(tv_pos + Vector((0, 0, 0.3)), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.7, 0.5, 0.03))
    for sx in (-0.33, 0.33):
        for sy in (-0.23, 0.23):
            b.cylinder(tv_pos + Vector((sx, sy, 0.05)), tv_pos + Vector((sx, sy, 0.82)), 0.012, 0.012, 8)
    b.to_object("TV_Carrinho", col, [mats["steel"]])
    yaw = math.atan2(-(-5.0 - tv_pos.x), 12.5 - tv_pos.y) + math.pi
    _, _, tv_c = crt_monitor(col, "TV_Sala", tv_pos + Vector((0, 0, 0.84)), yaw, mats, 0.55, "black", mats["static"])
    tvl = light("LUZ_TV_Estatica", "AREA", col, tv_c + (Vector((-5.0, 12.5, 1.0)) - tv_c).normalized() * 0.15, 12.0, (0.75, 0.85, 1.0),
                size=0.45, size_y=0.35)
    tvl.rotation_euler = look_at_rotation(tvl.location, (-5.0, 12.5, 1.0))
    tvl.visible_camera = False
    flicker(tvl.data, "energy", 12.0, 21)
    return seats


# ---------------------------------------------------------------------------
# Os vultos (esqueleto + Skin, sentados; estado C com a cabeça virada para a porta)
# ---------------------------------------------------------------------------
def figure_joints(scale, turn=0.0):
    """Articulações de uma criança sentada, frente = +Y (para o quadro)."""
    J = {
        "pelvis": (0.0, 0.0, 0.46), "spine": (0.0, 0.01, 0.62), "chest": (0.0, 0.02, 0.78), "neck": (0.0, 0.03, 0.9),
        "head": (0.0, 0.05, 1.0), "crown": (0.0, 0.04, 1.1),
        "sh_l": (-0.14, 0.02, 0.84), "sh_r": (0.14, 0.02, 0.84), "el_l": (-0.18, 0.16, 0.67), "el_r": (0.18, 0.16, 0.67),
        "ha_l": (-0.1, 0.3, 0.71), "ha_r": (0.1, 0.3, 0.71),
        "hip_l": (-0.08, 0.02, 0.44), "hip_r": (0.08, 0.02, 0.44), "kn_l": (-0.09, 0.32, 0.45), "kn_r": (0.09, 0.32, 0.45),
        "ft_l": (-0.09, 0.34, 0.05), "ft_r": (0.09, 0.34, 0.05),
    }
    radii = {"pelvis": (0.11, 0.08), "spine": (0.1, 0.075), "chest": (0.12, 0.08), "neck": (0.045, 0.045), "head": (0.1, 0.105),
             "crown": (0.085, 0.09), "sh_l": (0.05, 0.05), "sh_r": (0.05, 0.05), "el_l": (0.038, 0.038), "el_r": (0.038, 0.038),
             "ha_l": (0.032, 0.032), "ha_r": (0.032, 0.032), "hip_l": (0.07, 0.07), "hip_r": (0.07, 0.07),
             "kn_l": (0.05, 0.05), "kn_r": (0.05, 0.05), "ft_l": (0.04, 0.05), "ft_r": (0.04, 0.05)}
    V = {k: Vector(v) for k, v in J.items()}
    if turn:
        # roda cabeça (inteira) e ombros (parcial) à volta do eixo da coluna
        for keys, frac in ((("head", "crown"), 1.0), (("neck",), 0.8), (("sh_l", "sh_r", "el_l", "el_r", "ha_l", "ha_r", "chest"), 0.3)):
            R = Matrix.Rotation(turn * frac, 3, "Z")
            for k in keys:
                p = V[k]
                V[k] = Vector((0, 0, p.z)) + R @ Vector((p.x, p.y, 0))
    for k in V:
        V[k] *= scale
    return V, {k: (r[0] * scale, r[1] * scale) for k, r in radii.items()}


EDGES = [("pelvis", "spine"), ("spine", "chest"), ("chest", "neck"), ("neck", "head"), ("head", "crown"), ("chest", "sh_l"),
         ("chest", "sh_r"), ("sh_l", "el_l"), ("el_l", "ha_l"), ("sh_r", "el_r"), ("el_r", "ha_r"), ("pelvis", "hip_l"),
         ("pelvis", "hip_r"), ("hip_l", "kn_l"), ("kn_l", "ft_l"), ("hip_r", "kn_r"), ("kn_r", "ft_r")]


def build_figure(name, col, loc, yaw, scale, turn, mats):
    V, RAD = figure_joints(scale, turn)
    keys = list(V.keys())
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(V[k]) for k in keys], [(keys.index(a), keys.index(b)) for a, b in EDGES], [])
    ob = new_object(name, me, col)
    ob.location = loc
    ob.rotation_euler = (0, 0, yaw)
    ob.modifiers.new("Pele", "SKIN")
    sv = me.skin_vertices[0].data
    for i, k in enumerate(keys):
        sv[i].radius = RAD[k]
    sv[keys.index("pelvis")].use_root = True
    me.materials.append(mats["figure"])
    sub = ob.modifiers.new("Subdivisao", "SUBSURF")
    sub.levels, sub.render_levels = 1, 2
    tex = bpy.data.textures.get("T_Vulto_Irregular") or bpy.data.textures.new("T_Vulto_Irregular", "CLOUDS")
    tex.noise_scale = 0.05
    d = ob.modifiers.new("Irregular", "DISPLACE")
    d.texture = tex
    d.strength = 0.012
    ob.data.shade_smooth()
    # "olhos": dois pontos que só apanham a luz (dizem para onde a cabeça olha)
    fwd = Matrix.Rotation(turn, 3, "Z") @ Vector((0, 1, 0))
    side = Matrix.Rotation(turn, 3, "Z") @ Vector((1, 0, 0))
    b = Builder()
    for s in (-1, 1):
        p = V["head"] + (fwd * 0.093 + side * s * 0.036 + Vector((0, 0, 0.012))) * scale
        b.ico(p, 0.009 * scale, (1, 1, 0.7), 1, 0.0)
    eyes = b.to_object(name + "_Olhos", col, [mats["eyes"]], smooth=True)
    eyes.parent = ob
    # fumo negro à volta
    msh = bpy.data.meshes.get("Vulto_Fumo_Forma")
    if msh is None:
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
        msh = bpy.data.meshes.new("Vulto_Fumo_Forma")
        bm.to_mesh(msh)
        bm.free()
        msh.materials.append(mats["smoke"])
    smoke = new_object(name + "_Fumo", msh, col)
    smoke.parent = ob
    smoke.location = (0, 0.05 * scale, 0.8 * scale)
    smoke.scale = (0.4 * scale, 0.38 * scale, 0.6 * scale)
    return [ob, eyes, smoke]


def key_visibility(objs, visible_ranges, total=240):
    """Esconde/mostra objetos por frames (para a sequência A → B → C)."""
    for ob in objs:
        prev = None
        for f in range(1, total + 1):
            vis = any(a <= f <= c for a, c in visible_ranges)
            if vis != prev:
                ob.hide_render = not vis
                ob.hide_viewport = not vis
                ob.keyframe_insert("hide_render", frame=f)
                ob.keyframe_insert("hide_viewport", frame=f)
                prev = vis
        for fc in iter_fcurves(ob.animation_data.action):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"


def build_figures(col_b, col_c, seats, mats):
    door = Vector((-CX, DOOR_OPEN_Y, 1.5))
    r_ = random.Random(66)
    chosen = [s for s in seats if r_.random() < 0.85]
    objs_b, objs_c = [], []
    for i, (p, yaw) in enumerate(chosen):
        scale = r_.uniform(0.9, 1.08)
        # ângulo para a porta, relativo à frente da figura (+Y rodado por yaw)
        to_door = door - p
        ang = math.atan2(to_door.x, to_door.y)
        turn = -(ang + yaw)
        turn = max(-2.0, min(2.0, turn))
        objs_b += build_figure(f"Vulto_B_{i:02d}", col_b, p, yaw, scale, 0.0, mats)
        objs_c += build_figure(f"Vulto_C_{i:02d}", col_c, p, yaw, scale, turn, mats)
    key_visibility(objs_b, [(SEQ["B_de"], SEQ["B_ate"])])
    key_visibility(objs_c, [(SEQ["C_de"], 240)])
    return objs_b, objs_c


# ---------------------------------------------------------------------------
# Câmaras, marcadores, render
# ---------------------------------------------------------------------------
def build_cameras(col):
    cams = {}

    def cam(name, loc, target, lens, fstop=None, focus=None):
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        cd.sensor_width = 36
        cd.clip_start = 0.03
        if fstop:
            cd.dof.use_dof = True
            cd.dof.aperture_fstop = fstop
            cd.dof.focus_distance = focus
        ob = new_object(name, cd, col)
        ob.location = loc
        ob.rotation_euler = look_at_rotation(loc, target)
        cams[name] = ob

    cam("CAM_1_Corredor", (0.35, 1.0, 1.6), (-0.15, CL, 1.45), 28)
    cam("CAM_2_Aproximacao_Porta", (0.75, 7.6, 1.6), (-CX, DOOR_OPEN_Y + 0.2, 1.1), 30, 4.0, 4.3)
    cam("CAM_3_Umbral_Sala", (-1.72, 11.25, 1.5), (-5.6, ROOM_Y1, 0.95), 22)
    cam("CAM_4_Fundo_Sala", (-8.9, 9.8, 1.7), (-4.5, ROOM_Y1, 0.9), 28)
    cam("CAM_5_Secretaria_Professora", (-3.6, ROOM_Y1 - 0.7, 1.45), (-5.8, 11.0, 0.75), 24)
    cam("CAM_6_Quadro_Giz", (-4.3, ROOM_Y1 - 2.4, 1.55), (-5.7, ROOM_Y1, 1.7), 35, 5.6, 2.8)
    cam("CAM_7_Vidro_Porta_103", (-0.6, 17.3, 1.55), (-CX, 18.0, 1.5), 50, 2.8, 1.25)
    cam("CAM_8_Cacifo_Aberto", (0.1, 5.9, 1.45), (CX - 0.4, 4.28, 1.1), 35, 2.8, 2.25)
    bpy.context.scene.camera = cams["CAM_3_Umbral_Sala"]
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

    marker("PERSONAGEM_1_Corredor", (0.2, 5.0, 0.0), (-0.1, 1), "a caminhar pelo corredor (plano da CAM_1)")
    marker("PERSONAGEM_2_A_Porta", (-0.9, 10.7, 0.0), (-1, 0.25), "parado à porta aberta, a olhar para dentro da sala")
    marker("PERSONAGEM_3_Dentro_Sala", (-2.3, 10.3, 0.0), (-0.6, 1), "acabou de entrar na sala")


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
    scn.cycles.volume_bounces = 0
    scn.cycles.sample_clamp_indirect = 6.0
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
    scn.view_settings.exposure = 0.8
    w = bpy.data.worlds.new("Mundo_Noite")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.005, 0.007, 0.012, 1)
    scn.world = w


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
    film_look(glare=(0.85, 0.3), lens=(0.012, 0.006), sat=0.6, lift=(0.98, 1.01, 1.0), gain=(0.98, 1.02, 0.98), vignette_min=0.4, grain=0.12)


README_TEXT = """ESCOLA — CORREDOR E SALA (SEQUÊNCIA DOS VULTOS)
=================================================

SEQUÊNCIA ANIMADA (frames 1-240):
  1-100   A: sala vazia
  101-105 a luz da sala apaga
  106-172 B: vultos sentados, virados para o quadro
  173-177 a luz apaga outra vez
  178-240 C: os vultos viraram a cabeça para a porta

CONTROLO À MÃO: 04_VULTOS/VULTOS_B_Virados_Quadro e VULTOS_C_Virados_Porta.
  A visibilidade dos vultos está animada (hide_render). Para uma imagem fixa
  de um estado, escolha um frame dentro do intervalo, ou apague os keyframes
  e use as caixas das coleções.

FRASE DO QUADRO: objetos Giz_Linha_0..6 (Tab para editar o texto).
"""


def main():
    args = parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.name = "Escola_Corredor_Sala"
    c_arch = collection("01_ARQUITETURA")
    c_corr = collection("02_CORREDOR")
    c_room = collection("03_SALA_DE_AULA")
    c_fig = collection("04_VULTOS")
    c_b = collection("VULTOS_B_Virados_Quadro", c_fig)
    c_c = collection("VULTOS_C_Virados_Porta", c_fig)
    c_light = collection("05_LUZES")
    c_cam = collection("06_CAMARAS")
    c_char = collection("07_PERSONAGEM")

    mats = {
        "wall": mat_cinder("M_Parede_Blocos_Pintados", (0.28, 0.27, 0.22), (0.1, 0.15, 0.13)),
        "floor": mat_linoleum(), "ceiling": mat_ceiling_tiles(), "locker": mat_locker(), "chalkboard": mat_chalkboard(),
        "figure": mat_figure(), "smoke": mat_smoke(), "static": mat_static(),
        "rubber": mat_simple("M_Borracha_Rodape", (0.02, 0.025, 0.02), 0.6),
        "steel": mat_simple("M_Aco", (0.45, 0.45, 0.45), 0.35, metal=1.0, noise_scale=30),
        "black": mat_simple("M_Preto", (0.01, 0.01, 0.01), 0.6),
        "paper": mat_simple("M_Papel", (0.6, 0.58, 0.5), 0.85, noise_scale=40),
        "coat": mat_simple("M_Casaco", (0.018, 0.022, 0.035), 0.85, noise_scale=80, bump=0.3),
        "frame": mat_simple("M_Aro_Madeira_Escura", (0.07, 0.045, 0.025), 0.6, noise_scale=20),
        "door_wood": mat_wood("M_Porta_Madeira", dark=0.8),
        "wired_glass": mat_glass("M_Vidro_Aramado", 0.25),
        "hand_pale": mat_simple("M_Mao_Palida", (0.1, 0.09, 0.085), 0.7, noise_scale=40, bump=0.3),
        "cork": mat_simple("M_Cortica", (0.2, 0.12, 0.06), 0.95, noise_scale=150, bump=0.5),
        "photo_dark": mat_simple("M_Foto_Escura", (0.05, 0.05, 0.05), 0.4, noise_scale=20),
        "exit_green": mat_emit("M_EXIT_Verde", (0.1, 1.0, 0.25), 6.0),
        "white_emit": mat_emit("M_EXIT_Letras", (0.9, 1.0, 0.9), 10.0),
        "tube_on": mat_emit("M_Fluorescente_Acesa", (0.85, 1.0, 0.9), 8.0),
        "tube_off": mat_simple("M_Fluorescente_Apagada", (0.5, 0.5, 0.48), 0.3),
        "tube_flicker_c": mat_emit_principled("M_Fluorescente_Pisca_Corredor"),
        "tube_flicker_r": mat_emit_principled("M_Fluorescente_Pisca_Sala"),
        "chalk": mat_simple("M_Giz", (0.75, 0.75, 0.7), 0.95),
        "alpha_red": mat_simple("M_Letras_Alfabeto", (0.35, 0.03, 0.02), 0.7),
        "desk_wood": mat_wood("M_Secretaria_Madeira", dark=1.0),
        "desk_top": mat_simple("M_Tampo_Carteira", (0.3, 0.22, 0.13), 0.4, noise_scale=12),
        "desk_steel_dark": mat_simple("M_Aco_Escuro", (0.06, 0.06, 0.06), 0.45, metal=0.8),
        "chair_plastic": mat_plastic("M_Cadeira_Plastico", (0.12, 0.05, 0.03), 0.5),
        "apple": mat_simple("M_Maca", (0.3, 0.02, 0.02), 0.3),
        "globe": mat_simple("M_Globo", (0.05, 0.12, 0.25), 0.4, noise_scale=3),
        "blinds": mat_simple("M_Persianas", (0.4, 0.38, 0.33), 0.5),
        "night_sky": mat_emit("M_Noite_Fora", (0.03, 0.05, 0.1), 1.0),
        "eyes": mat_simple("M_Olhos_Vultos", (0.25, 0.25, 0.23), 0.02),
        "plastic_black": mat_plastic("M_Plastico_Preto", (0.02, 0.02, 0.022), 0.4),
        "plastic_beige": mat_plastic("M_Plastico_Bege", (0.42, 0.37, 0.27)),
        "led_green": mat_emit("M_LED_Verde", (0.2, 1.0, 0.3), 20.0),
    }
    print("> arquitetura")
    build_shell(c_arch, mats)
    build_doors(c_arch, mats, c_light)
    print("> corredor")
    build_lockers(c_corr, mats)
    build_corridor_props(c_corr, mats)
    print("> sala de aula")
    seats = build_classroom(c_room, mats)
    print("> vultos")
    build_figures(c_b, c_c, seats, mats)
    print("> luzes, câmaras")
    build_lights(c_light, mats)
    build_cameras(c_cam)
    build_markers(c_char)
    setup_render()
    setup_compositor()
    bpy.data.texts.new("LEIA-ME").write(README_TEXT)
    scn.frame_set(1)
    out = os.path.abspath(args.out)
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    print(f"> guardado: {out}")
    if args.render:
        render_previews(args)


def mat_emit_principled(name):
    m = Mat(name)
    m.set("Base Color", (0.5, 0.5, 0.48))
    m.set("Emission Color", (0.85, 1.0, 0.9))
    m.set("Emission Strength", 8.0)
    m.set("Roughness", 0.3)
    return m.mat


PREVIEWS = [   # (ficheiro, câmara, frame)
    ("cam1_corredor", "CAM_1_Corredor", 60),
    ("cam2_aproximacao_porta", "CAM_2_Aproximacao_Porta", 60),
    ("cam3_umbral_A_vazia", "CAM_3_Umbral_Sala", 60),
    ("cam3_umbral_B_vultos", "CAM_3_Umbral_Sala", 150),
    ("cam3_umbral_C_viraram", "CAM_3_Umbral_Sala", 210),
    ("cam4_fundo_sala_B", "CAM_4_Fundo_Sala", 150),
    ("cam5_secretaria_C", "CAM_5_Secretaria_Professora", 210),
    ("cam6_quadro_giz", "CAM_6_Quadro_Giz", 60),
    ("cam7_vidro_porta_103", "CAM_7_Vidro_Porta_103", 60),
    ("cam8_cacifo_aberto", "CAM_8_Cacifo_Aberto", 60),
]


def render_previews(args):
    scn = bpy.context.scene
    os.makedirs(args.render, exist_ok=True)
    scn.cycles.samples = args.samples
    scn.cycles.adaptive_threshold = 0.05
    scn.cycles.volume_step_rate = 2.0
    scn.render.resolution_x = args.res
    scn.render.resolution_y = int(args.res * 9 / 16)
    scn.render.image_settings.file_format = "JPEG"
    scn.render.image_settings.quality = 90
    only = set(filter(None, args.only.split(",")))
    room = bpy.data.objects["LUZ_Sala_Fluorescente"].data
    fc = next(f for f in iter_fcurves(room.animation_data.action) if f.data_path == "energy")
    for fname, cam, frame in PREVIEWS:
        if only and fname not in only:
            continue
        # evitar um frame em que a fluorescente da sala está a piscar
        for d in range(0, 20):
            if fc.evaluate(frame + d) > 50:
                frame += d
                break
        scn.camera = bpy.data.objects[cam]
        scn.frame_set(frame)
        scn.render.filepath = os.path.join(os.path.abspath(args.render), fname + ".jpg")
        print(f"> render {fname}")
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
