"""
Efeito 01 — Eletricidade SSJ (estilo Super Saiyajin 2 do Dragon Ball Z)

Raios elétricos que aparecem e desaparecem ao acaso e percorrem a SUPERFÍCIE do avatar,
como o Gohan contra o Cell. Tudo é feito em Geometry Nodes: não há partículas a simular,
não há cache e o efeito segue a pele mesmo com o avatar animado (Mixamo, armature, etc.).

O controlo principal é a INTENSIDADE (0 a 1):
    0.05  quase nada: um raio solitário de vez em quando
    0.3   esporádico: alguns raios por segundo
    0.6   carregado: o corpo crepita sem parar
    1.0   semi-permanente: o corpo está sempre coberto de raios
Pode ser animada com keyframes (por exemplo, para subir durante uma transformação).

Uso (dentro do Blender, com o avatar aberto):
    1. Selecione o(s) objeto(s) de malha do avatar (corpo, roupa, cabelo...).
    2. Separador Scripting → Open → eletricidade_ssj.py → Run Script.
    3. Cada malha recebe o modificador "Eletricidade SSJ" (no fim da pilha, depois da
       Armature). Os controlos estão no painel do modificador.

Uso (a partir de outro script):
    import eletricidade_ssj
    eletricidade_ssj.add_to_object(obj, Intensidade=0.5)
"""

import bpy

GROUP_NAME = "Eletricidade_SSJ"
MOD_NAME = "Eletricidade SSJ"
MAT_CORE = "Eletricidade_Nucleo"
MAT_HALO = "Eletricidade_Halo"

# (nome, tipo, valor por defeito, mín, máx, subtipo, descrição)
INPUTS = [
    ("Intensidade", "FLOAT", 0.35, 0.0, 1.0, "FACTOR",
     "0 = nada; 0.05 = um raio de vez em quando; 1 = semi-permanente"),
    ("Densidade", "FLOAT", 22.0, 0.0, 400.0, "NONE",
     "Máximo de raios por m² de pele (atingido com Intensidade = 1)"),
    ("Faíscas", "FLOAT", 0.6, 0.0, 1.0, "FACTOR",
     "Quantidade de faíscas pequenas à volta dos raios principais"),
    ("Comprimento", "FLOAT", 0.32, 0.01, 2.0, "DISTANCE", "Comprimento de cada raio (m)"),
    ("Segmentos", "INT", 12, 2, 40, "NONE", "Número de quebras em cada raio"),
    ("Irregularidade", "FLOAT", 0.45, 0.0, 2.0, "FACTOR", "Quanto o raio ziguezagueia"),
    ("Espessura", "FLOAT", 0.0022, 0.0001, 0.1, "DISTANCE", "Raio do núcleo branco (m)"),
    ("Halo", "FLOAT", 7.0, 1.0, 30.0, "NONE", "Largura do brilho à volta do núcleo (× espessura)"),
    ("Afastamento", "FLOAT", 0.008, 0.0, 0.2, "DISTANCE", "Distância à pele (m)"),
    ("Duração", "FLOAT", 3.0, 1.0, 48.0, "NONE", "Frames que cada raio dura antes de saltar"),
    ("Cintilação", "FLOAT", 0.6, 0.0, 1.0, "FACTOR", "Variação de brilho de frame para frame"),
    ("Cor", "RGBA", (0.25, 0.55, 1.0, 1.0), None, None, None, "Cor do halo (o núcleo é quase branco)"),
    ("Brilho", "FLOAT", 30.0, 0.0, 500.0, "NONE", "Força da emissão"),
    ("Semente", "INT", 0, 0, 100000, "NONE", "Muda o padrão dos raios"),
    ("Mostrar Avatar", "BOOLEAN", True, None, None, None,
     "Desligue para ficar só com os raios (útil para render em camadas)"),
]

SOCKET_TYPES = {
    "FLOAT": "NodeSocketFloat",
    "INT": "NodeSocketInt",
    "RGBA": "NodeSocketColor",
    "BOOLEAN": "NodeSocketBool",
}

# Camadas de raios: (nome, mult. densidade, mult. comprimento, mult. irregularidade,
#                    mult. espessura, mult. brilho, controlada por Faíscas?, desvio da semente)
LAYERS = [
    ("Raios", 1.0, 1.0, 1.0, 1.0, 1.0, False, 0),
    ("Faiscas", 3.0, 0.35, 1.4, 0.7, 0.7, True, 7),
]


# ---------------------------------------------------------------------------------------
# Pequena camada por cima da API de nós (os nomes dos sockets mudam entre versões)
# ---------------------------------------------------------------------------------------

def _available(sock):
    if hasattr(sock, "is_unavailable") and sock.is_unavailable:
        return False
    return getattr(sock, "enabled", True)


def _find(socks, names, stype=None):
    if isinstance(names, str):
        names = (names,)
    for name in names:
        for s in socks:
            if s.name == name and _available(s) and (stype is None or s.type == stype):
                return s
    raise KeyError(f"socket {names} ({stype}) não encontrado em {[s.name for s in socks]}")


class Tree:
    def __init__(self, tree):
        self.t = tree
        self.n = tree.nodes
        self.x = 0

    def node(self, idname, **props):
        nd = self.n.new(idname)
        for k, v in props.items():
            setattr(nd, k, v)
        nd.location = (self.x, 0)
        self.x += 30
        return nd

    def link(self, src, dst):
        self.t.links.new(src, dst)

    def feed(self, sock, val):
        """Liga um socket ou define o valor por defeito."""
        if isinstance(val, bpy.types.NodeSocket):
            self.link(val, sock)
        elif val is not None:
            sock.default_value = val

    def math(self, op, a, b=None, c=None):
        nd = self.node("ShaderNodeMath", operation=op)
        for i, v in enumerate((a, b, c)):
            self.feed(nd.inputs[i], v)
        return nd.outputs[0]

    def vmath(self, op, a, b=None, scale=None):
        nd = self.node("ShaderNodeVectorMath", operation=op)
        self.feed(nd.inputs[0], a)
        self.feed(nd.inputs[1], b)
        if scale is not None:
            self.feed(_find(nd.inputs, "Scale"), scale)
        if op in ("LENGTH", "DOT_PRODUCT", "DISTANCE"):
            return _find(nd.outputs, "Value")
        return _find(nd.outputs, "Vector")

    def rand_float(self, lo, hi, id_, seed):
        nd = self.node("FunctionNodeRandomValue", data_type="FLOAT")
        self.feed(_find(nd.inputs, "Min", "VALUE"), lo)
        self.feed(_find(nd.inputs, "Max", "VALUE"), hi)
        self.feed(_find(nd.inputs, "ID"), id_)
        self.feed(_find(nd.inputs, "Seed"), seed)
        return _find(nd.outputs, "Value", "VALUE")

    def rand_vec(self, lo, hi, id_, seed):
        nd = self.node("FunctionNodeRandomValue", data_type="FLOAT_VECTOR")
        self.feed(_find(nd.inputs, "Min", "VECTOR"), (lo, lo, lo))
        self.feed(_find(nd.inputs, "Max", "VECTOR"), (hi, hi, hi))
        self.feed(_find(nd.inputs, "ID"), id_)
        self.feed(_find(nd.inputs, "Seed"), seed)
        return _find(nd.outputs, "Value", "VECTOR")

    def store(self, geo, name, dtype, value, domain="POINT"):
        nd = self.node("GeometryNodeStoreNamedAttribute", data_type=dtype, domain=domain)
        self.link(geo, nd.inputs[0])
        _find(nd.inputs, "Name").default_value = name
        stype = {"FLOAT": "VALUE", "FLOAT_VECTOR": "VECTOR", "FLOAT_COLOR": "RGBA"}[dtype]
        self.feed(_find(nd.inputs, "Value", stype), value)
        return nd.outputs[0]

    def named(self, name, dtype):
        nd = self.node("GeometryNodeInputNamedAttribute", data_type=dtype)
        _find(nd.inputs, "Name").default_value = name
        return _find(nd.outputs, "Attribute")


# ---------------------------------------------------------------------------------------
# Materiais
# ---------------------------------------------------------------------------------------

def _shadow_transparent(nt, shader_out, out_node):
    """Os raios não projetam sombra (só emitem luz)."""
    lp = nt.nodes.new("ShaderNodeLightPath")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Shadow Ray"], mix.inputs[0])
    nt.links.new(shader_out, mix.inputs[1])
    nt.links.new(tr.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out_node.inputs["Surface"])


def _attr(nt, name):
    a = nt.nodes.new("ShaderNodeAttribute")
    a.attribute_type = "GEOMETRY"
    a.attribute_name = name
    return a


def build_materials():
    core = bpy.data.materials.get(MAT_CORE)
    if core is None:
        core = bpy.data.materials.new(MAT_CORE)
        core.use_nodes = True
        nt = core.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        cor = _attr(nt, "eletric_cor")
        bri = _attr(nt, "eletric_brilho")
        # núcleo quase branco, tingido pela cor
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        _find(mix.inputs, "Factor", "VALUE").default_value = 0.6
        nt.links.new(cor.outputs["Color"], _find(mix.inputs, "A", "RGBA"))
        _find(mix.inputs, "B", "RGBA").default_value = (1.0, 1.0, 1.0, 1.0)
        em = nt.nodes.new("ShaderNodeEmission")
        nt.links.new(_find(mix.outputs, "Result", "RGBA"), em.inputs["Color"])
        nt.links.new(bri.outputs["Fac"], em.inputs["Strength"])
        _shadow_transparent(nt, em.outputs[0], out)
        core.diffuse_color = (0.85, 0.93, 1.0, 1.0)

    halo = bpy.data.materials.get(MAT_HALO)
    if halo is None:
        halo = bpy.data.materials.new(MAT_HALO)
        halo.use_nodes = True
        nt = halo.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        cor = _attr(nt, "eletric_cor")
        bri = _attr(nt, "eletric_brilho")
        # opacidade máxima no centro do tubo e a desvanecer para as bordas
        lw = nt.nodes.new("ShaderNodeLayerWeight")
        lw.inputs["Blend"].default_value = 0.5
        inv = nt.nodes.new("ShaderNodeMath")
        inv.operation = "SUBTRACT"
        inv.inputs[0].default_value = 1.0
        nt.links.new(lw.outputs["Facing"], inv.inputs[1])
        pw = nt.nodes.new("ShaderNodeMath")
        pw.operation = "POWER"
        nt.links.new(inv.outputs[0], pw.inputs[0])
        pw.inputs[1].default_value = 2.5
        str_ = nt.nodes.new("ShaderNodeMath")
        str_.operation = "MULTIPLY"
        nt.links.new(bri.outputs["Fac"], str_.inputs[0])
        str_.inputs[1].default_value = 0.3
        em = nt.nodes.new("ShaderNodeEmission")
        nt.links.new(cor.outputs["Color"], em.inputs["Color"])
        nt.links.new(str_.outputs[0], em.inputs["Strength"])
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(pw.outputs[0], mix.inputs[0])
        nt.links.new(tr.outputs[0], mix.inputs[1])
        nt.links.new(em.outputs[0], mix.inputs[2])
        _shadow_transparent(nt, mix.outputs[0], out)
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(halo, attr, val)
            except (AttributeError, TypeError):
                pass
        halo.diffuse_color = (0.45, 0.75, 1.0, 0.4)
    return core, halo


# ---------------------------------------------------------------------------------------
# Geometry Nodes
# ---------------------------------------------------------------------------------------

def _build_layer(g, gi, geo, inv_s, frame, core, halo, spec):
    """Uma camada de raios. Devolve a geometria (malha) dos raios dessa camada."""
    _, k_dens, k_len, k_irr, k_thk, k_bri, use_faiscas, seed_off = spec
    seed = g.math("ADD", gi["Semente"], float(seed_off * 1000))

    # probabilidade de um candidato disparar em cada ciclo: I² (fica muito subtil em baixo)
    p = g.math("POWER", gi["Intensidade"], 2.0)
    if use_faiscas:
        p = g.math("MULTIPLY", p, gi["Faíscas"])

    # candidatos fixos na pele (densidade convertida para o espaço local do objeto)
    dens = g.math("MULTIPLY", gi["Densidade"], k_dens)
    dens = g.math("DIVIDE", dens, g.math("MULTIPLY", inv_s, inv_s))
    dist = g.node("GeometryNodeDistributePointsOnFaces", distribute_method="RANDOM")
    g.link(geo, dist.inputs[0])
    g.link(dens, _find(dist.inputs, "Density", "VALUE"))
    g.link(seed, _find(dist.inputs, "Seed"))
    pts = _find(dist.outputs, "Points")
    nrm = _find(dist.outputs, "Normal")

    id_ = g.node("GeometryNodeInputID").outputs[0]
    hold = g.math("MAXIMUM", gi["Duração"], 1.0)
    # cada candidato tem a sua fase: os raios não saltam todos no mesmo frame
    phase = g.rand_float(0.0, hold, id_, g.math("ADD", seed, 11.0))
    cycle = g.math("FLOOR", g.math("DIVIDE", g.math("ADD", frame, phase), hold))
    cseed = g.math("ADD", g.math("MULTIPLY", cycle, 7.0), seed)

    # dispara neste ciclo?
    roll = g.rand_float(0.0, 1.0, id_, g.math("ADD", cseed, 1.0))
    dele = g.node("GeometryNodeDeleteGeometry", domain="POINT")
    g.link(pts, dele.inputs[0])
    g.link(g.math("GREATER_THAN", roll, p), _find(dele.inputs, "Selection"))
    pts = dele.outputs[0]

    # direção ao acaso no plano tangente à pele
    rv = g.rand_vec(-1.0, 1.0, id_, g.math("ADD", cseed, 2.0))
    tdir = g.vmath("NORMALIZE", g.vmath("CROSS_PRODUCT", nrm, rv))
    # comprimento (local) com variação, um pouco mais curto em intensidade baixa
    lscale = g.math("MULTIPLY_ADD", gi["Intensidade"], 0.35, 0.65)
    length = g.math("MULTIPLY", g.math("MULTIPLY", gi["Comprimento"], k_len), inv_s)
    length = g.math("MULTIPLY", length, lscale)
    length = g.math("MULTIPLY", length, g.rand_float(0.5, 1.25, id_, g.math("ADD", cseed, 3.0)))
    # o raio começa ligeiramente deslocado do candidato, para variar entre ciclos
    jo = g.vmath("SCALE", g.rand_vec(-0.5, 0.5, id_, g.math("ADD", cseed, 4.0)), scale=length)
    pos = g.node("GeometryNodeInputPosition").outputs[0]
    origin = g.vmath("SUBTRACT", g.vmath("ADD", pos, jo), g.vmath("SCALE", tdir, scale=g.math("MULTIPLY", length, 0.5)))
    bseed = g.rand_float(0.0, 1.0, id_, g.math("ADD", cseed, 5.0))
    # cintilação: brilho muda a cada frame
    flick = g.rand_float(0.0, 1.0, id_, g.math("ADD", g.math("MULTIPLY", frame, 13.0), seed))
    bri = g.math("SUBTRACT", 1.0, g.math("MULTIPLY", flick, gi["Cintilação"]))
    bri = g.math("MULTIPLY", g.math("MULTIPLY", bri, gi["Brilho"]), k_bri)

    pts = g.store(pts, "_e_origem", "FLOAT_VECTOR", origin)
    pts = g.store(pts, "_e_dir", "FLOAT_VECTOR", tdir)
    pts = g.store(pts, "_e_comp", "FLOAT", length)
    pts = g.store(pts, "_e_semente", "FLOAT", bseed)
    pts = g.store(pts, "eletric_brilho", "FLOAT", bri)
    pts = g.store(pts, "eletric_cor", "FLOAT_COLOR", gi["Cor"])

    # um segmento de reta com N quebras em cada candidato que disparou
    line = g.node("GeometryNodeCurvePrimitiveLine")
    _find(line.inputs, "End").default_value = (1.0, 0.0, 0.0)
    res = g.node("GeometryNodeResampleCurve")
    g.link(line.outputs[0], res.inputs[0])
    g.link(g.math("ADD", gi["Segmentos"], 1.0), _find(res.inputs, "Count"))
    inst = g.node("GeometryNodeInstanceOnPoints")
    g.link(pts, _find(inst.inputs, "Points"))
    g.link(res.outputs[0], _find(inst.inputs, "Instance"))
    real = g.node("GeometryNodeRealizeInstances")
    g.link(inst.outputs[0], real.inputs[0])
    crv = real.outputs[0]

    # posição de cada vértice do raio: reta + ziguezague, projetada na pele
    sp = g.node("GeometryNodeSplineParameter")
    fac = _find(sp.outputs, "Factor")
    idx = _find(sp.outputs, "Index")
    o = g.named("_e_origem", "FLOAT_VECTOR")
    d = g.named("_e_dir", "FLOAT_VECTOR")
    L = g.named("_e_comp", "FLOAT")
    bs = g.math("FLOOR", g.math("MULTIPLY", g.named("_e_semente", "FLOAT"), 100000.0))
    straight = g.vmath("ADD", o, g.vmath("SCALE", d, scale=g.math("MULTIPLY", fac, L)))
    bump = g.math("MULTIPLY_ADD", g.math("SINE", g.math("MULTIPLY", fac, 3.14159265)), 0.7, 0.3)
    amp = g.math("MULTIPLY", g.math("MULTIPLY", L, g.math("MULTIPLY", gi["Irregularidade"], k_irr)), bump)
    zig = g.vmath("SCALE", g.rand_vec(-0.5, 0.5, idx, bs), scale=amp)
    target = g.vmath("ADD", straight, zig)

    prox = g.node("GeometryNodeProximity", target_element="FACES")
    g.link(geo, prox.inputs[0])
    g.link(target, _find(prox.inputs, ("Source Position", "Sample Position"), "VECTOR"))
    surf = _find(prox.outputs, "Position")
    sns = g.node("GeometryNodeSampleNearestSurface", data_type="FLOAT_VECTOR")
    g.link(geo, sns.inputs[0])
    g.link(g.node("GeometryNodeInputNormal").outputs[0], _find(sns.inputs, "Value", "VECTOR"))
    g.link(target, _find(sns.inputs, "Sample Position"))
    snrm = _find(sns.outputs, "Value", "VECTOR")
    # afastamento da pele, com pequenos arcos para fora
    lift_r = g.rand_float(0.0, 1.0, idx, g.math("ADD", bs, 1.0))
    lift = g.math("MULTIPLY_ADD", g.math("MULTIPLY", lift_r, amp), 0.35,
                  g.math("MULTIPLY", gi["Afastamento"], inv_s))
    newpos = g.vmath("ADD", surf, g.vmath("SCALE", snrm, scale=lift))
    # raios que se afastam demasiado da pele (ex.: atravessam o vão entre as pernas) ficariam
    # com segmentos retos enormes ao serem projetados: descarta-os (média por raio)
    gap = g.math("DIVIDE", _find(prox.outputs, "Distance"), g.math("MAXIMUM", L, 1e-6))
    cull = g.node("GeometryNodeDeleteGeometry", domain="CURVE")
    g.link(crv, cull.inputs[0])
    g.link(g.math("GREATER_THAN", gap, 0.22), _find(cull.inputs, "Selection"))
    crv = cull.outputs[0]
    setp = g.node("GeometryNodeSetPosition")
    g.link(crv, setp.inputs[0])
    g.link(newpos, _find(setp.inputs, "Position"))
    crv = setp.outputs[0]

    # espessura: mais grosso no meio, afinando nas pontas
    taper = g.math("MULTIPLY_ADD", g.math("SINE", g.math("MULTIPLY", fac, 3.14159265)), 0.75, 0.25)
    rad = g.math("MULTIPLY", g.math("MULTIPLY", gi["Espessura"], k_thk * 1.0), inv_s)
    radius = g.math("MULTIPLY", rad, taper)
    scr = g.node("GeometryNodeSetCurveRadius")
    g.link(crv, scr.inputs[0])
    g.link(radius, _find(scr.inputs, "Radius"))
    crv = scr.outputs[0]

    outs = []
    for mat, prof_r, res_n in ((core, 1.0, 4), (halo, None, 6)):
        circ = g.node("GeometryNodeCurvePrimitiveCircle")
        _find(circ.inputs, "Resolution").default_value = res_n
        if prof_r is None:
            g.link(gi["Halo"], _find(circ.inputs, "Radius"))
        else:
            _find(circ.inputs, "Radius").default_value = prof_r
        c2m = g.node("GeometryNodeCurveToMesh")
        g.link(crv, _find(c2m.inputs, "Curve"))
        g.link(circ.outputs[0], _find(c2m.inputs, "Profile Curve"))
        # Blender 4.2+: o raio da curva só conta se for ligado à entrada "Scale"
        if any(s.name == "Scale" for s in c2m.inputs):
            g.link(radius, _find(c2m.inputs, "Scale"))
        sm = g.node("GeometryNodeSetMaterial")
        g.link(c2m.outputs[0], sm.inputs[0])
        _find(sm.inputs, "Material").default_value = mat
        outs.append(sm.outputs[0])
    return outs


def build_node_group():
    old = bpy.data.node_groups.get(GROUP_NAME)
    if old is not None:
        return old
    core, halo = build_materials()
    tree = bpy.data.node_groups.new(GROUP_NAME, "GeometryNodeTree")
    try:
        tree.is_modifier = True
    except AttributeError:
        pass
    tree.description = "Raios elétricos esporádicos na superfície (estilo Super Saiyajin 2)"
    iface = tree.interface
    iface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    iface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    for name, typ, default, lo, hi, sub, desc in INPUTS:
        s = iface.new_socket(name, in_out="INPUT", socket_type=SOCKET_TYPES[typ])
        s.description = desc
        if sub and sub != "NONE":
            try:
                s.subtype = sub
            except (AttributeError, TypeError):
                pass
        s.default_value = default
        if lo is not None:
            s.min_value, s.max_value = lo, hi

    g = Tree(tree)
    gin = g.node("NodeGroupInput")
    gout = g.node("NodeGroupOutput")
    gi = {name: _find(gin.outputs, name) for name, *_ in INPUTS}
    geo = _find(gin.outputs, "Geometry")

    # escala do objeto no mundo: os controlos estão em metros reais mesmo que o avatar
    # tenha escala 0.01 (FBX do Mixamo)
    selfo = g.node("GeometryNodeSelfObject")
    oinfo = g.node("GeometryNodeObjectInfo", transform_space="ORIGINAL")
    g.link(selfo.outputs[0], _find(oinfo.inputs, "Object"))
    sc = g.node("ShaderNodeSeparateXYZ")
    g.link(_find(oinfo.outputs, "Scale"), sc.inputs[0])
    s_avg = g.math("DIVIDE", g.math("ADD", g.math("ADD", sc.outputs[0], sc.outputs[1]), sc.outputs[2]), 3.0)
    inv_s = g.math("DIVIDE", 1.0, g.math("MAXIMUM", g.math("ABSOLUTE", s_avg), 1e-6))

    frame = _find(g.node("GeometryNodeInputSceneTime").outputs, "Frame")

    sw = g.node("GeometryNodeSwitch", input_type="GEOMETRY")
    g.link(gi["Mostrar Avatar"], _find(sw.inputs, "Switch"))
    g.link(geo, _find(sw.inputs, "True"))

    join = g.node("GeometryNodeJoinGeometry")
    g.link(sw.outputs[0], join.inputs[0])
    for spec in LAYERS:
        for o in _build_layer(g, gi, geo, inv_s, frame, core, halo, spec):
            g.link(o, join.inputs[0])

    # limpa os atributos temporários
    final = join.outputs[0]
    for name in ("_e_origem", "_e_dir", "_e_comp", "_e_semente"):
        rm = g.node("GeometryNodeRemoveAttribute")
        g.link(final, rm.inputs[0])
        _find(rm.inputs, "Name").default_value = name
        final = rm.outputs[0]
    g.link(final, _find(gout.inputs, "Geometry"))

    # arruma os nós em colunas para ficar legível no editor
    for i, nd in enumerate(tree.nodes):
        nd.location = ((i // 12) * 220, -(i % 12) * 160)
    gout.location = ((len(tree.nodes) // 12 + 1) * 220, 0)
    return tree


def add_to_object(obj, **values):
    """Adiciona o modificador ao objeto (no fim da pilha) e devolve-o."""
    tree = build_node_group()
    mod = obj.modifiers.get(MOD_NAME) or obj.modifiers.new(MOD_NAME, "NODES")
    mod.node_group = tree
    ids = {it.name: it.identifier for it in tree.interface.items_tree
           if getattr(it, "in_out", None) == "INPUT"}
    # cada objeto do avatar com a sua semente, para não repetirem o mesmo padrão
    values.setdefault("Semente", sum(map(ord, obj.name)) % 1000)
    for k, v in values.items():
        mod[ids[k]] = v
    obj.update_tag()
    return mod


def main():
    objs = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    if not objs:
        raise RuntimeError("Selecione pelo menos um objeto de malha (o avatar) antes de correr o script.")
    for o in objs:
        add_to_object(o)
        print(f"> Eletricidade SSJ adicionada a {o.name}")


if __name__ == "__main__":
    main()
