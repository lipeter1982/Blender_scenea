"""
Boneco provisório para o animatic da intro (fica no lugar do avatar Mesh2Motion).

Manequim articulado de 1,8 m feito de cápsulas, com animação procedural:
  andar  — ciclo de passada, balanço dos braços e do tronco;
  sentar — sentado numa cadeira, braços para o teclado;
  parado — respiração e um olhar por cima do ombro (vira raiz, tronco e cabeça).

Frente do boneco = +Y local. A raiz fica no chão, entre os pés.
"""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

PASSO_FRAMES = 26          # frames por ciclo de passada (dois passos)
VELOCIDADE = 1.35          # m/s (a 24 fps)


def _col(nome="BONECO_PROVISORIO"):
    col = bpy.data.collections.get(nome)
    if col is None:
        col = bpy.data.collections.new(nome)
        bpy.context.scene.collection.children.link(col)
    return col


def _mat():
    m = bpy.data.materials.get("M_Boneco_Provisorio")
    if m:
        return m
    m = bpy.data.materials.new("M_Boneco_Provisorio")
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (0.42, 0.4, 0.38, 1)
    p.inputs["Roughness"].default_value = 0.55
    p.inputs["Coat Weight"].default_value = 0.2
    return m


def _capsula(nome, comprimento, raio, col, mat, raio2=None):
    """Cápsula a descer do pivô (0,0,0) até (0,0,-comprimento)."""
    raio2 = raio if raio2 is None else raio2
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, segments=12, radius1=raio2, radius2=raio, depth=comprimento,
                          matrix=Matrix.Translation((0, 0, -comprimento / 2)))
    bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=raio)
    bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=raio2, matrix=Matrix.Translation((0, 0, -comprimento)))
    me = bpy.data.meshes.new(nome)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    me.shade_smooth()
    ob = bpy.data.objects.new(nome, me)
    col.objects.link(ob)
    return ob


def _pivo(nome, pai, loc, col):
    e = bpy.data.objects.new(nome, None)
    e.empty_display_size = 0.05
    col.objects.link(e)
    e.parent = pai
    e.location = loc
    return e


def criar(nome="BONECO"):
    """Cria o boneco; devolve um dicionário com as articulações."""
    col = _col()
    mat = _mat()
    j = {}
    raiz = bpy.data.objects.new(nome + "_Raiz", None)
    raiz.empty_display_type = "ARROWS"
    raiz.empty_display_size = 0.4
    col.objects.link(raiz)
    j["raiz"] = raiz
    j["anca"] = _pivo(nome + "_Anca", raiz, (0, 0, 0.95), col)
    j["tronco"] = _pivo(nome + "_Tronco", j["anca"], (0, 0, 0.0), col)
    t = _capsula(nome + "_Torso", 0.5, 0.15, col, mat, 0.13)
    t.parent = j["tronco"]
    t.location = (0, 0, 0.5)
    t.scale = (1.25, 0.8, 1.0)
    j["cabeca"] = _pivo(nome + "_Pescoco", j["tronco"], (0, 0, 0.55), col)
    h = _capsula(nome + "_Cabeca", 0.12, 0.11, col, mat, 0.1)
    h.parent = j["cabeca"]
    h.location = (0, 0, 0.2)
    nariz = _capsula(nome + "_Nariz", 0.03, 0.025, col, mat)   # para se ver para onde olha
    nariz.parent = j["cabeca"]
    nariz.location = (0, 0.1, 0.15)
    for lado, s in (("E", -1), ("D", 1)):
        j["ombro" + lado] = _pivo(f"{nome}_Ombro_{lado}", j["tronco"], (s * 0.22, 0, 0.47), col)
        a = _capsula(f"{nome}_Braco_{lado}", 0.28, 0.055, col, mat, 0.045)
        a.parent = j["ombro" + lado]
        j["cotovelo" + lado] = _pivo(f"{nome}_Cotovelo_{lado}", j["ombro" + lado], (0, 0, -0.29), col)
        f = _capsula(f"{nome}_Antebraco_{lado}", 0.26, 0.045, col, mat, 0.04)
        f.parent = j["cotovelo" + lado]
        j["perna" + lado] = _pivo(f"{nome}_Perna_{lado}", j["anca"], (s * 0.1, 0, -0.02), col)
        c = _capsula(f"{nome}_Coxa_{lado}", 0.43, 0.075, col, mat, 0.06)
        c.parent = j["perna" + lado]
        j["joelho" + lado] = _pivo(f"{nome}_Joelho_{lado}", j["perna" + lado], (0, 0, -0.44), col)
        sh = _capsula(f"{nome}_Canela_{lado}", 0.42, 0.055, col, mat, 0.045)
        sh.parent = j["joelho" + lado]
        pe = _capsula(f"{nome}_Pe_{lado}", 0.16, 0.045, col, mat)
        pe.parent = j["joelho" + lado]
        pe.location = (0, -0.02, -0.46)
        pe.rotation_euler = (-math.pi / 2, 0, 0)
    return j


def _key(ob, frame, rot=None, loc=None):
    if rot is not None:
        ob.rotation_euler = rot
        ob.keyframe_insert("rotation_euler", frame=frame)
    if loc is not None:
        ob.location = loc
        ob.keyframe_insert("location", frame=frame)


def _yaw(direcao):
    return math.atan2(-direcao.x, direcao.y)


def pose_andar(j, fase):
    """Pose do ciclo de passada; fase em radianos."""
    s = math.sin(fase)
    for lado, k in (("E", 1), ("D", -1)):
        sw = k * s
        _key_now(j["perna" + lado], (0.42 * sw, 0, 0))
        # o joelho dobra na fase de balanço (perna a vir para a frente)
        bal = max(0.0, math.cos(fase + (0 if k > 0 else math.pi)))
        _key_now(j["joelho" + lado], (-0.9 * bal - 0.08, 0, 0))
        _key_now(j["ombro" + lado], (-0.38 * sw, 0, k * -0.06))
        _key_now(j["cotovelo" + lado], (0.25 + 0.2 * max(0.0, -sw), 0, 0))
    _key_now(j["tronco"], (0.05, 0, 0.08 * s))
    _key_now(j["cabeca"], (-0.03, 0, -0.05 * s))
    j["anca"].location = (0, 0, 0.93 + 0.025 * abs(math.cos(fase)))


def _key_now(ob, rot):
    ob.rotation_euler = rot


def _key_all(j, frame):
    for k, ob in j.items():
        if k == "raiz":
            continue
        ob.keyframe_insert("rotation_euler", frame=frame)
    j["anca"].keyframe_insert("location", frame=frame)


def andar(j, inicio, direcao, f0, f1, chao=lambda x, y: 0.0, fase0=0.0):
    """Anda em linha reta de `inicio` na `direcao`, dos frames f0 a f1 (inclusive)."""
    d = Vector((direcao[0], direcao[1], 0)).normalized()
    yaw = _yaw(d)
    pos = []
    for f in range(f0, f1 + 1):
        dist = (f - f0) / 24.0 * VELOCIDADE
        p = Vector((inicio[0], inicio[1], 0)) + d * dist
        p.z = chao(p.x, p.y)
        _key(j["raiz"], f, rot=(0, 0, yaw), loc=p)
        pose_andar(j, fase0 + 2 * math.pi * f / PASSO_FRAMES)
        _key_all(j, f)
        pos.append(p.copy())
    return pos


def parar(j, pos, direcao, f0, f1, olhar_de=None, olhar_ate=None):
    """Parado de pé (respiração); entre olhar_de e olhar_ate vira-se a olhar por cima do ombro direito."""
    d = Vector((direcao[0], direcao[1], 0)).normalized()
    yaw = _yaw(d)
    for f in range(f0, f1 + 1):
        t = 0.0
        if olhar_de is not None and f >= olhar_de:
            t = min(1.0, (f - olhar_de) / max(1, olhar_ate - olhar_de))
            t = t * t * (3 - 2 * t)
        br = math.sin(f / 24.0 * 2.2) * 0.012
        _key(j["raiz"], f, rot=(0, 0, yaw - 0.5 * t), loc=pos)
        for lado, k in (("E", 1), ("D", -1)):
            _key_now(j["perna" + lado], (0.0, 0, 0))
            _key_now(j["joelho" + lado], (-0.04, 0, 0))
            _key_now(j["ombro" + lado], (0.05, 0, k * -0.08))
            _key_now(j["cotovelo" + lado], (0.15, 0, 0))
        _key_now(j["tronco"], (0.02 + br, 0, -0.7 * t))
        _key_now(j["cabeca"], (-0.05 + 0.08 * t, 0, -1.25 * t))
        j["anca"].location = (0, 0, 0.93 + br * 0.5)
        _key_all(j, f)


def sentar(j, pos, direcao, f0, f1, assento=0.5):
    """Sentado, virado para `direcao`, braços estendidos para o teclado."""
    d = Vector((direcao[0], direcao[1], 0)).normalized()
    yaw = _yaw(d)
    for f in range(f0, f1 + 1):
        br = math.sin(f / 24.0 * 2.0) * 0.01
        _key(j["raiz"], f, rot=(0, 0, yaw), loc=pos)
        for lado, k in (("E", 1), ("D", -1)):
            _key_now(j["perna" + lado], (math.pi / 2 - 0.05, 0, k * 0.08))
            _key_now(j["joelho" + lado], (-math.pi / 2 + 0.05, 0, 0))
            _key_now(j["ombro" + lado], (0.75, 0, k * 0.15))
            _key_now(j["cotovelo" + lado], (0.95, 0, 0))
        _key_now(j["tronco"], (0.12 + br, 0, 0))
        _key_now(j["cabeca"], (0.08, 0, 0))
        j["anca"].location = (0, 0, assento + 0.06)
        _key_all(j, f)
