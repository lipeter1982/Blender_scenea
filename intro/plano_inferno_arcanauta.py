"""
Intro do canal — plano do Inferno (cenário 08)

A câmara avança e sobe até às Portas do Inferno; a meio do plano o inferno gela
(a propriedade "gelo" anima de 0 para 1: a lava apaga-se, cai neve, as chamas congelam)
e a inscrição do lintel diz ARCANAUTA, com a linha do canal por baixo.

6 s a 24 fps (frames 1–144). Gera o cenário 08 de raiz e acrescenta a animação.

Uso (dentro do Blender):
    blender -b -P plano_inferno_arcanauta.py -- --out plano_inferno.blend
Uso (módulo bpy via pip), com um teste em vídeo de baixa resolução:
    python plano_inferno_arcanauta.py --out plano_inferno.blend --render teste --res 640 --samples 12 --step 2
"""

import argparse
import importlib.util
import os
import sys

import bpy

AQUI = os.path.dirname(os.path.abspath(__file__))
CENARIO = os.path.join(AQUI, "..", "cenarios", "08_inferno_fogo_gelo", "build_scene.py")

TITULO = "ARCANAUTA"
LINHA = "jogos obscuros  ·  PC  ·  PS1  ·  PS2"

FIM = 144                # 6 s
GELO_INI, GELO_FIM = 62, 98   # o inferno gela entre estes frames


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="plano_inferno.blend")
    p.add_argument("--render", default="", help="pasta para o vídeo de teste (vazio = não renderiza)")
    p.add_argument("--res", type=int, default=1920)
    p.add_argument("--samples", type=int, default=128)
    p.add_argument("--step", type=int, default=1, help="renderizar 1 frame em cada N (teste rápido)")
    return p.parse_args(argv)


def carregar_cenario(out):
    spec = importlib.util.spec_from_file_location("cenario08", CENARIO)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.argv = [sys.argv[0], "--out", out]
    mod.main()
    return mod


def mat_logo(mod):
    """Letras do logo: gravadas a fogo nas Brasas, gelo azul luminoso no Gelo (mais forte que a inscrição)."""
    m = mod.Mat("M_Logo_Arcanauta")
    g_ = mod.gelo(m)
    m.set("Base Color", m.mix(g_, (0.05, 0.01, 0.0), (0.7, 0.85, 0.95)))
    m.set("Roughness", 0.3)
    m.set("Emission Color", m.mix(g_, (1.0, 0.42, 0.08), (0.45, 0.8, 1.0)))
    m.set("Emission Strength", m.mixf(g_, 6.0, 3.0))
    return m.mat


def inscricao_arcanauta(mod):
    logo = mat_logo(mod)
    for name in ("Inscricao_1", "Inscricao_2"):
        bpy.data.objects[name].data.materials[0] = logo
    t1 = bpy.data.objects["Inscricao_1"]
    t1.data.body = TITULO
    t1.data.size = 0.72
    t1.data.space_character = 1.15
    t1.data.extrude = 0.04
    t2 = bpy.data.objects["Inscricao_2"]
    t2.data.body = LINHA
    t2.data.size = 0.24
    t2.data.space_character = 1.05


def animar_gelo(scn):
    scn["gelo"] = 0.0
    scn.keyframe_insert('["gelo"]', frame=1)
    scn.keyframe_insert('["gelo"]', frame=GELO_INI)
    scn["gelo"] = 1.0
    scn.keyframe_insert('["gelo"]', frame=GELO_FIM)
    # as luzes das duas versões leem o mesmo valor: têm de estar ambas incluídas
    ll = bpy.context.view_layer.layer_collection.children["05_LUZ"]
    ll.children["VAR_Brasas"].exclude = False
    ll.children["VAR_Gelo"].exclude = False
    for name in ("Fagulhas", "Cinza_a_Cair", "Neve_a_Cair"):
        bpy.data.objects[name].hide_render = False


def iter_fcurves(action):
    """F-curves de uma action (Blender 4.x e 5.x, com camadas)."""
    fcs = list(getattr(action, "fcurves", []) or [])
    if not fcs:
        for layer in getattr(action, "layers", []):
            for strip in layer.strips:
                for cb in strip.channelbags:
                    fcs += list(cb.fcurves)
    return fcs


def camara(mod, scn):
    """Grua: parte do chão, à distância, e sobe até enquadrar o lintel."""
    cd = bpy.data.cameras.new("CAM_INTRO_Portas")
    cd.sensor_width = 36
    cd.clip_start = 0.05
    cd.clip_end = 800
    cam = bpy.data.objects.new("CAM_INTRO_Portas", cd)
    bpy.data.collections["06_CAMARAS"].objects.link(cam)
    alvo = bpy.data.objects.new("CAM_INTRO_Alvo", None)
    bpy.data.collections["06_CAMARAS"].objects.link(alvo)
    tr = cam.constraints.new("TRACK_TO")
    tr.target = alvo
    tr.track_axis = "TRACK_NEGATIVE_Z"
    tr.up_axis = "UP_Y"
    gz = mod.ground_height(0.6, -50.0)
    keys = [   # frame, posição da câmara, alvo, lente
        (1, (0.9, -50.0, gz + 1.2), (0.0, -20.0, 4.5), 20),
        (70, (0.4, -45.0, 4.6), (0.05, -28.0, 7.0), 26),
        (110, (0.15, -42.2, 6.6), (0.1, -28.1, 8.1), 33),
        (FIM, (0.05, -41.4, 7.0), (0.1, -28.1, 8.2), 35),
    ]
    for f, loc, tgt, lens in keys:
        cam.location = loc
        cam.keyframe_insert("location", frame=f)
        alvo.location = tgt
        alvo.keyframe_insert("location", frame=f)
        cd.lens = lens
        cd.keyframe_insert("lens", frame=f)
    for ob in (cam, alvo, cd):
        ad = ob.animation_data
        for fc in iter_fcurves(ad.action):
            for kp in fc.keyframe_points:
                kp.interpolation = "BEZIER"
                kp.easing = "AUTO"
    scn.camera = cam
    return cam


def main():
    args = parse_args()
    out = os.path.abspath(args.out)
    mod = carregar_cenario(out)
    scn = bpy.context.scene
    scn.name = "Intro_Inferno_Arcanauta"
    scn.frame_start, scn.frame_end = 1, FIM
    inscricao_arcanauta(mod)
    animar_gelo(scn)
    camara(mod, scn)
    scn.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    print(f"> guardado: {out}")
    if args.render:
        render_teste(args)


def render_teste(args):
    scn = bpy.context.scene
    pasta = os.path.abspath(args.render)
    os.makedirs(pasta, exist_ok=True)
    scn.cycles.samples = args.samples
    scn.cycles.adaptive_threshold = 0.05
    scn.cycles.volume_step_rate = 3.0
    scn.render.resolution_x = args.res
    scn.render.resolution_y = int(args.res * 9 / 16)
    scn.frame_step = args.step
    scn.render.fps = max(1, round(24 / args.step))
    scn.render.image_settings.file_format = "FFMPEG"
    scn.render.ffmpeg.format = "MPEG4"
    scn.render.ffmpeg.codec = "H264"
    scn.render.ffmpeg.constant_rate_factor = "HIGH"
    scn.render.filepath = os.path.join(pasta, "plano_inferno_")
    bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
