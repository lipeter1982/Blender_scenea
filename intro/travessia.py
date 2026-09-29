"""
Intro do canal ARCANAUTA — "A Travessia" (12 s, 288 frames a 24 fps)

O Arcanauta, sentado ao CRT no gabinete, mergulha no ecrã e atravessa mundos esquecidos
(floresta → escola → cemitério → igreja soterrada), num só passo contínuo cortado de cenário
em cenário, até às Portas do Inferno — que gelam — e o logo ARCANAUTA.

Cada plano gera o seu cenário de raiz (cenarios/NN/build_scene.py), junta o avatar (por agora
o boneco provisório, ver boneco.py), anima a câmara e renderiza os frames com a numeração
global da intro. A montagem (transições, vídeo) é feita depois por montagem.py.

Uso:
    python travessia.py --shot todos --out render_intro --res 480 --samples 8 --step 2   # animatic
    python travessia.py --shot inferno --out render_intro --res 1920 --samples 128        # um plano, final
    blender -b -P travessia.py -- --shot gabinete --out render_intro                      # dentro do Blender
Planos: gabinete, floresta, escola, cemiterio, igreja, inferno.
"""

import argparse
import importlib.util
import os
import subprocess
import sys

import bpy
from mathutils import Vector

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.normpath(os.path.join(AQUI, ".."))
sys.path.insert(0, AQUI)
import boneco  # noqa: E402

# (nome, pasta do cenário, frame inicial, frame final) — numeração global da intro
PLANOS = [
    ("gabinete", "03_gabinete_investigador", 1, 60),
    ("floresta", "04_floresta_enevoada", 61, 84),
    ("escola", "05_escola_corredor_sala", 85, 108),
    ("cemiterio", "06_cemiterio_gotico", 109, 132),
    ("igreja", "02_messiah_igreja_soterrada", 133, 156),
    ("inferno", "08_inferno_fogo_gelo", 157, 288),
]
CHEGA_PORTAS = 204          # o Arcanauta pára diante das Portas
GELO = (214, 248)           # o inferno gela
OLHAR = (252, 268)          # vira-se para a câmara
SEGUE_DIST, SEGUE_ALT, SEGUE_LENTE = 4.4, 1.6, 35   # enquadramento comum dos planos a andar (os cortes em movimento)


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("--shot", default="todos")
    p.add_argument("--out", default=os.path.join(AQUI, "render_intro"))
    p.add_argument("--res", type=int, default=1920)
    p.add_argument("--samples", type=int, default=128)
    p.add_argument("--step", type=int, default=1)
    p.add_argument("--no-render", action="store_true")
    return p.parse_args(argv)


def carregar(pasta, blend_out):
    path = os.path.join(RAIZ, "cenarios", pasta, "build_scene.py")
    spec = importlib.util.spec_from_file_location("cenario_" + pasta[:2], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    argv = sys.argv
    sys.argv = [argv[0], "--out", blend_out]
    mod.main()
    sys.argv = argv
    return mod


def camara(nome, lente=35):
    cd = bpy.data.cameras.new(nome)
    cd.lens = lente
    cd.sensor_width = 36
    cd.clip_start = 0.05
    cd.clip_end = 800
    cam = bpy.data.objects.new(nome, cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    return cam


def olhar(cam, loc, alvo, frame):
    cam.location = loc
    cam.rotation_euler = (Vector(alvo) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    cam.keyframe_insert("location", frame=frame)
    cam.keyframe_insert("rotation_euler", frame=frame)


def seguir(cam, posicoes, direcao, f0, chao):
    """Câmara atrás do Arcanauta, à mesma distância e altura em todos os mundos."""
    d = Vector((direcao[0], direcao[1], 0)).normalized()
    for i, p in enumerate(posicoes):
        c = p - d * SEGUE_DIST
        c.z = chao(c.x, c.y) + SEGUE_ALT
        alvo = p + d * 8.0
        alvo.z = p.z + 1.25
        olhar(cam, c, alvo, f0 + i)


def mundo_a_andar(mod, inicio, direcao, f0, f1, chao):
    j = boneco.criar()
    pos = boneco.andar(j, inicio, direcao, f0, f1, chao)
    cam = camara("CAM_INTRO", SEGUE_LENTE)
    seguir(cam, pos, direcao, f0, chao)


def chao_zero(x, y):
    return 0.0


# ---------------------------------------------------------------------------
# Os planos
# ---------------------------------------------------------------------------
def plano_gabinete(mod, f0, f1):
    """Sentado ao CRT, de costas; o ecrã acende (com a floresta) e a câmara mergulha nele."""
    chair = mod.CHAIR_C
    crt = mod.CRT_C
    j = boneco.criar()
    boneco.sentar(j, Vector((chair.x, chair.y, 0)), crt - chair, f0, f1)
    ecra = bpy.data.objects["CRT_Secretaria_Ecra"]
    cs = [ecra.matrix_world @ Vector(v) for v in ecra.bound_box]
    centro = sum(cs, Vector()) / 8
    normal = ecra.matrix_world.to_3x3() @ Vector((0, -1, 0))
    if normal.dot(Vector((chair.x, chair.y, 1.0)) - centro) < 0:
        normal = -normal
    normal.normalize()
    # o jogo no ecrã é a floresta (onde a câmara vai sair)
    img = bpy.data.images.load(os.path.join(RAIZ, "cenarios", "04_floresta_enevoada", "previews", "cam1_chegada_clareira.jpg"))
    mat = bpy.data.materials["M_Ecra_CRT_Jogo"]
    nt = mat.node_tree
    for n in nt.nodes:
        if n.type == "TEX_IMAGE":
            n.image = img
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    es = bsdf.inputs["Emission Strength"]
    for f, v in ((f0, 0.0), (f0 + 9, 0.0), (f0 + 10, 5.0), (f0 + 11, 0.4), (f0 + 13, 4.5), (f0 + 17, 3.5)):
        es.default_value = v
        es.keyframe_insert("default_value", frame=f)
    cam = camara("CAM_INTRO", 32)
    ini = Vector((chair.x - 0.7, chair.y + 0.68, 1.55))        # por cima do ombro esquerdo
    ctrl = Vector((chair.x - 0.75, chair.y - 0.3, 1.3))        # contorna a cabeça pela esquerda
    fim = centro + normal * 0.012
    for f in range(f0, f1 + 1):
        u = (f - f0) / (f1 - f0)
        t = 0.45 * (u / 0.6) if u < 0.6 else 0.45 + 0.55 * ((u - 0.6) / 0.4) ** 1.8   # devagar, depois mergulha
        t = min(1.0, t)
        loc = (1 - t) ** 2 * ini + 2 * (1 - t) * t * ctrl + t * t * fim
        olhar(cam, loc, centro, f)


def plano_floresta(mod, f0, f1):
    mundo_a_andar(mod, (-2.3, -6.9), (0.28, 1.0), f0, f1, mod.ground_height)


def plano_escola(mod, f0, f1):
    mundo_a_andar(mod, (0.1, 6.6), (0.0, 1.0), f0, f1, chao_zero)


def plano_cemiterio(mod, f0, f1):
    mundo_a_andar(mod, (0.15, -34.4), (0.0, 1.0), f0, f1, mod.ground_height)


def plano_igreja(mod, f0, f1):
    mundo_a_andar(mod, (0.0, 5.4), (0.0, 1.0), f0, f1, chao_zero)


def plano_inferno(mod, f0, f1):
    """Chega às Portas, pára; a câmara sobe e recua, o inferno gela, ele olha para nós."""
    spec = importlib.util.spec_from_file_location("plano_inferno", os.path.join(AQUI, "plano_inferno_arcanauta.py"))
    pi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pi)
    pi.GELO_INI, pi.GELO_FIM = GELO
    pi.inscricao_arcanauta(mod)
    pi.animar_gelo(bpy.context.scene)
    d = Vector((0, 1, 0))
    marca = Vector((0.2, -31.5, 0))
    dist = (CHEGA_PORTAS - f0) / 24 * boneco.VELOCIDADE
    j = boneco.criar()
    pos = boneco.andar(j, (marca.x, marca.y - dist), d, f0, CHEGA_PORTAS, mod.ground_height)
    boneco.parar(j, pos[-1], d, CHEGA_PORTAS + 1, f1, *OLHAR)
    cam = camara("CAM_INTRO", SEGUE_LENTE)
    seguir(cam, pos, d, f0, mod.ground_height)
    # grua: recua e sobe até ter o Arcanauta pequeno em baixo e o logo em cima
    c0 = cam.location.copy()
    a0 = pos[-1] + d * 8.0
    a0.z = pos[-1].z + 1.25
    c1 = Vector((0.1, -44.0, 4.3))
    a1 = Vector((0.12, -29.0, 4.7))
    fim_grua = 244
    for f in range(CHEGA_PORTAS + 1, f1 + 1):
        t = min(1.0, (f - CHEGA_PORTAS) / (fim_grua - CHEGA_PORTAS))
        t = t * t * (3 - 2 * t)
        drift = max(0, f - fim_grua) * 0.004
        olhar(cam, c0.lerp(c1, t) + Vector((0, -drift, drift * 0.3)), a0.lerp(a1, t), f)
        cam.data.lens = SEGUE_LENTE + (26 - SEGUE_LENTE) * t
        cam.data.keyframe_insert("lens", frame=f)


PLANO_FN = {"gabinete": plano_gabinete, "floresta": plano_floresta, "escola": plano_escola,
            "cemiterio": plano_cemiterio, "igreja": plano_igreja, "inferno": plano_inferno}


def renderizar(args, f0, f1):
    scn = bpy.context.scene
    scn.frame_start, scn.frame_end = f0, f1
    scn.frame_step = args.step
    scn.render.resolution_x = args.res
    scn.render.resolution_y = int(args.res * 9 / 16)
    scn.render.resolution_percentage = 100
    scn.cycles.samples = args.samples
    if args.samples <= 32:
        scn.cycles.adaptive_threshold = 0.05
        scn.cycles.volume_step_rate = 3.0
    scn.render.image_settings.file_format = "JPEG"
    scn.render.image_settings.quality = 92
    scn.render.filepath = os.path.join(os.path.abspath(args.out), "frames", "f_")
    bpy.ops.render.render(animation=True)


def um_plano(args, nome):
    _, pasta, f0, f1 = next(p for p in PLANOS if p[0] == nome)
    os.makedirs(os.path.join(args.out, "blend"), exist_ok=True)
    blend = os.path.abspath(os.path.join(args.out, "blend", f"intro_{nome}.blend"))
    mod = carregar(pasta, blend)
    PLANO_FN[nome](mod, f0, f1)
    scn = bpy.context.scene
    scn.frame_start, scn.frame_end = f0, f1
    scn.frame_set(f0)
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)
    print(f"> plano {nome}: {blend}")
    if not args.no_render:
        renderizar(args, f0, f1)


def main():
    args = parse_args()
    if args.shot != "todos":
        for nome in args.shot.split(","):
            um_plano(args, nome)
        return
    # cada plano num processo à parte (cada cenário começa de uma cena vazia)
    for nome, *_ in PLANOS:
        resto = ["--shot", nome, "--out", args.out, "--res", str(args.res), "--samples", str(args.samples),
                 "--step", str(args.step)] + (["--no-render"] if args.no_render else [])
        blender = bpy.app.binary_path
        if blender and "blender" in os.path.basename(blender).lower():     # a correr dentro do Blender
            cmd = [blender, "-b", "-P", os.path.abspath(__file__), "--"] + resto
        else:                                                               # módulo bpy (pip)
            cmd = [sys.executable, os.path.abspath(__file__)] + resto
        print(">", " ".join(cmd))
        subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
