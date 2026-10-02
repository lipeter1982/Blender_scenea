"""
Demo do efeito 01 — Eletricidade SSJ

Gera um .blend com um manequim (substituto do avatar), já com o modificador
"Eletricidade SSJ", luz escura e duas câmaras. A Intensidade está animada de 0 a 1
ao longo de 120 frames, para se ver a progressão (quase nada → semi-permanente).

Uso (dentro do Blender):
    blender -b -P build_demo.py -- --out eletricidade_ssj_demo.blend
Uso (módulo bpy via pip):
    python build_demo.py --out eletricidade_ssj_demo.blend --render previews --samples 48
"""

import argparse
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eletricidade_ssj as E  # noqa: E402


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="eletricidade_ssj_demo.blend")
    p.add_argument("--render", default="")
    p.add_argument("--samples", type=int, default=48)
    p.add_argument("--res", type=int, default=1280)
    return p.parse_args(argv)


# esqueleto do manequim: nome → (posição, raio da pele); pose de "power up"
JOINTS = {
    "pelvis": ((0.0, 0.0, 1.00), 0.13),
    "barriga": ((0.0, 0.01, 1.18), 0.13),
    "peito": ((0.0, 0.0, 1.38), 0.16),
    "pescoco": ((0.0, 0.0, 1.56), 0.055),
    "cabeca": ((0.0, -0.01, 1.70), 0.10),
    "topo": ((0.0, 0.0, 1.80), 0.07),
}
for side, sx in (("E", 1.0), ("D", -1.0)):
    JOINTS.update({
        f"ombro{side}": ((0.21 * sx, 0.0, 1.47), 0.075),
        f"cotovelo{side}": ((0.40 * sx, 0.03, 1.22), 0.05),
        f"pulso{side}": ((0.50 * sx, -0.04, 1.02), 0.038),
        f"punho{side}": ((0.53 * sx, -0.05, 0.95), 0.048),
        f"anca{side}": ((0.11 * sx, 0.0, 0.96), 0.09),
        f"joelho{side}": ((0.20 * sx, -0.05, 0.53), 0.062),
        f"tornozelo{side}": ((0.23 * sx, 0.02, 0.10), 0.045),
        f"pe{side}": ((0.25 * sx, -0.13, 0.04), 0.04),
    })
BONES = [("pelvis", "barriga"), ("barriga", "peito"), ("peito", "pescoco"), ("pescoco", "cabeca"),
         ("cabeca", "topo")]
for s in ("E", "D"):
    BONES += [("peito", f"ombro{s}"), (f"ombro{s}", f"cotovelo{s}"), (f"cotovelo{s}", f"pulso{s}"),
              (f"pulso{s}", f"punho{s}"), ("pelvis", f"anca{s}"), (f"anca{s}", f"joelho{s}"),
              (f"joelho{s}", f"tornozelo{s}"), (f"tornozelo{s}", f"pe{s}")]


def build_mannequin():
    names = list(JOINTS)
    me = bpy.data.meshes.new("Manequim")
    me.from_pydata([JOINTS[n][0] for n in names], [(names.index(a), names.index(b)) for a, b in BONES], [])
    ob = bpy.data.objects.new("Avatar_Manequim", me)
    bpy.context.scene.collection.objects.link(ob)
    skin = ob.modifiers.new("Pele", "SKIN")
    skin.use_smooth_shade = True
    for i, n in enumerate(names):
        r = JOINTS[n][1]
        me.skin_vertices[0].data[i].radius = (r, r)
    me.skin_vertices[0].data[names.index("pelvis")].use_root = True
    sub = ob.modifiers.new("Suavizar", "SUBSURF")
    sub.levels = sub.render_levels = 2

    mat = bpy.data.materials.new("Manequim_Pele")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.09, 0.085, 0.1, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.45
    me.materials.append(mat)
    return ob


def build_set():
    scn = bpy.context.scene
    # chão escuro
    bpy.ops.mesh.primitive_plane_add(size=30)
    floor = bpy.context.object
    floor.name = "Chao"
    m = bpy.data.materials.new("Chao")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.02, 0.022, 0.03, 1.0)
    b.inputs["Roughness"].default_value = 0.35
    floor.data.materials.append(m)

    # céu noturno quase preto, azulado
    w = bpy.data.worlds.new("Noite")
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.006, 0.008, 0.016, 1.0)
    bg.inputs["Strength"].default_value = 1.0
    scn.world = w

    def light(name, kind, loc, energy, color, size=1.0):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy
        ld.color = color
        if kind == "AREA":
            ld.size = size
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = (Vector((0, 0, 1.2)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        scn.collection.objects.link(ob)

    light("Luz_Chave", "AREA", (-2.5, -2.5, 3.2), 120, (0.75, 0.82, 1.0), 2.0)
    light("Luz_Recorte", "AREA", (1.8, 2.6, 2.4), 260, (0.4, 0.6, 1.0), 1.0)

    def cam(name, loc, target, lens):
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        ob = bpy.data.objects.new(name, cd)
        ob.location = loc
        ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        scn.collection.objects.link(ob)
        return ob

    c1 = cam("CAM_1_Plano_Medio", (1.15, -2.75, 1.5), (0.0, 0.0, 1.3), 45)
    cam("CAM_2_Corpo_Inteiro", (1.6, -4.3, 1.1), (0.0, 0.0, 0.92), 40)
    scn.camera = c1


def setup_render():
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.cycles.samples = 128
    scn.cycles.preview_samples = 16
    scn.cycles.use_denoising = True
    scn.cycles.transparent_max_bounces = 16
    scn.render.resolution_x, scn.render.resolution_y = 1920, 1080
    scn.render.fps = 24
    scn.frame_start, scn.frame_end = 1, 120
    scn.view_settings.view_transform = "AgX"
    try:
        scn.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    # EEVEE: raios com transparência suave
    try:
        scn.eevee.use_raytracing = True
    except AttributeError:
        pass


def setup_glare():
    """Brilho à volta dos raios no compositor (Bloom). Opcional: o halo já dá brilho."""
    scn = bpy.context.scene
    try:
        if hasattr(scn, "compositing_node_group"):          # Blender 5.x
            nt = bpy.data.node_groups.new("Compositor_Raios", "CompositorNodeTree")
            nt.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
            rl = nt.nodes.new("CompositorNodeRLayers")
            gl = nt.nodes.new("CompositorNodeGlare")
            out = nt.nodes.new("NodeGroupOutput")
            scn.compositing_node_group = nt
        else:                                              # Blender 4.x
            scn.use_nodes = True
            nt = scn.node_tree
            nt.nodes.clear()
            rl = nt.nodes.new("CompositorNodeRLayers")
            gl = nt.nodes.new("CompositorNodeGlare")
            out = nt.nodes.new("CompositorNodeComposite")
        for gt in ("BLOOM", "FOG_GLOW"):
            try:
                if "Type" in gl.inputs:
                    gl.inputs["Type"].default_value = gt.title().replace("_", " ")
                else:
                    gl.glare_type = gt
                break
            except (TypeError, ValueError):
                continue
        gl.quality = "HIGH"
        # Blender 4.5+: definições como entradas do nó; antes: propriedades
        for name, attr, val, legacy in (("Threshold", "threshold", 1.0, 1.0),
                                        ("Size", "size", 0.55, 7),
                                        ("Strength", "mix", 0.8, 0.0)):
            if name in gl.inputs:
                gl.inputs[name].default_value = val
            elif hasattr(gl, attr):
                setattr(gl, attr, legacy)
        nt.links.new(rl.outputs["Image"], gl.inputs["Image"])
        nt.links.new(gl.outputs["Image"], out.inputs[0])
    except Exception as e:  # o compositor mudou muito entre versões; o efeito vive sem ele
        print(f"! compositor não configurado: {e}")


def main():
    args = parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.name = "Eletricidade_SSJ_Demo"
    build_set()
    avatar = build_mannequin()
    mod = E.add_to_object(avatar, Intensidade=0.35, Semente=3)
    setup_render()
    setup_glare()

    # Intensidade animada: 0 no frame 1 → 1 no frame 120
    ident = {it.name: it.identifier for it in mod.node_group.interface.items_tree
             if getattr(it, "in_out", None) == "INPUT"}["Intensidade"]
    for f, v in ((1, 0.0), (120, 1.0)):
        mod[ident] = v
        avatar.keyframe_insert(f'modifiers["{mod.name}"]["{ident}"]', frame=f)
    act = avatar.animation_data.action
    fcurves = getattr(act, "fcurves", None)
    if fcurves is None:          # Blender 5.x: ações em camadas
        fcurves = [fc for lay in act.layers for st in lay.strips for cb in st.channelbags for fc in cb.fcurves]
    for fc in fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"

    scn.frame_set(60)
    out = os.path.abspath(args.out)
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    print(f"> guardado: {out}")
    if args.render:
        render_previews(args, avatar, mod, ident)


PREVIEWS = [  # (ficheiro, câmara, intensidade, frame)
    ("int_012_quase_nada", "CAM_1_Plano_Medio", 0.12, 17),
    ("int_035_esporadico", "CAM_1_Plano_Medio", 0.35, 23),
    ("int_065_carregado", "CAM_1_Plano_Medio", 0.65, 31),
    ("int_100_semi_permanente", "CAM_1_Plano_Medio", 1.0, 40),
    ("corpo_inteiro_050", "CAM_2_Corpo_Inteiro", 0.5, 52),
]


def render_previews(args, avatar, mod, ident):
    scn = bpy.context.scene
    os.makedirs(args.render, exist_ok=True)
    scn.cycles.samples = args.samples
    scn.render.resolution_x = args.res
    scn.render.resolution_y = int(args.res * 9 / 16)
    scn.render.image_settings.file_format = "JPEG"
    scn.render.image_settings.quality = 90
    avatar.animation_data.action = None          # usa o valor fixo de cada preview
    for fname, camname, inten, frame in PREVIEWS:
        mod[ident] = inten
        avatar.update_tag()
        scn.camera = bpy.data.objects[camname]
        scn.frame_set(frame)
        scn.render.filepath = os.path.join(os.path.abspath(args.render), fname + ".jpg")
        print(f"> render {fname}")
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
