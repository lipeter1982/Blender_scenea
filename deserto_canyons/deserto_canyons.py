"""
Deserto com canyons, dunas e planícies (500 x 500 m)
Transição dia -> crepúsculo -> noite, 960 frames @ 24 fps (40 s), Cycles.

Testado em Blender 5.0; feito para Blender 5.x (5.2).

Como usar
---------
  * Blender > Scripting > abrir este ficheiro > Run Script   (demora ~20 s)
  * ou em linha de comandos:
        blender -b -P deserto_canyons.py -- --save deserto.blend
        blender -b deserto.blend -a                      # render da animação

O script apaga a cena atual e constrói tudo de raiz. Todos os parâmetros
importantes estão no bloco CONFIG logo abaixo.

Orientação do mundo: +Y = Norte, +X = Este. O sol põe-se a Oeste-Noroeste,
atrás dos canyons; as dunas ficam a Este; as planícies e o leito seco
(playa) ficam no meio. A câmara faz um travelling lento das dunas para oeste.

O "relógio" da cena é a curva de elevação do sol (SOL_ELEVACAO). Tudo o
resto (cor e força do sol, céu, brilho do crepúsculo, cinturão de Vénus,
sombra da Terra, estrelas, Via Láctea, lua, poeira, calor, exposição) é
derivado dela e gravado como keyframes, por isso pode ser afinado no
Graph Editor depois de gerado.
"""

import math
import random
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Vector

# =============================================================================
# CONFIG
# =============================================================================
TAMANHO = 500.0            # lado do terreno principal (m)
RESOLUCAO = 1001           # vértices por lado do terreno principal (0.5 m)
RAIO_HORIZONTE = 12000.0   # alcance do terreno distante (m)
SEMENTE = 7

FPS = 24
FRAME_INI = 1
FRAME_FIM = 960            # 40 s
PASSO_KEYS = 8             # keyframes da luz/céu a cada N frames
ESCALA_CEU = 0.16          # céu físico vs. lâmpada do sol (contraste sol/sombra)

# Elevação do sol (graus) ao longo do tempo normalizado t = 0..1.
# Dia abrasador -> hora dourada -> pôr do sol (t~0.47) -> crepúsculo civil,
# náutico e astronómico (ênfase: ~45 % do tempo) -> noite.
SOL_ELEVACAO = [
    (0.00, 29.0),
    (0.12, 23.0),
    (0.30, 13.0),
    (0.40, 5.0),
    (0.47, 0.0),
    (0.56, -3.5),
    (0.66, -7.0),
    (0.76, -11.0),
    (0.86, -15.0),
    (1.00, -20.0),
]
SOL_AZIMUTE = (243.0, 255.0)       # graus a partir do Norte (sentido horário): põe-se a OSO
LUA_AZ_EL_INI = (188.0, 33.0)      # lua crescente a sul
LUA_AZ_EL_FIM = (198.0, 29.0)
VIA_NUCLEO = (212.0, 12.0)         # centro da Via Láctea (az, el)
LUA_RAIO_GRAUS = 1.1               # exagerado para leitura (real: 0.26)

# Câmara: posição inicial/final (x, y) e direção do olhar (t, azimute, elevação)
CAM_INI = (100.0, -38.0)
CAM_FIM = (18.0, -72.0)
CAM_OLHAR = [(0.00, 244.0, 9.5), (0.20, 245.0, 7.0), (0.40, 247.0, 3.5), (0.55, 248.0, 3.5),
             (0.66, 244.0, 5.0), (0.78, 230.0, 9.0), (0.90, 213.0, 13.5), (1.00, 206.0, 15.0)]

# Render
RES_X, RES_Y = 1920, 1080
AMOSTRAS = 256
USAR_VOLUME = True         # poeira volumétrica + raios crepusculares
USAR_CALOR = True          # distorção do ar quente (só na parte diurna)
USAR_COMPOSITOR = True     # bloom do sol

# Scatter
N_PEDRAS = 1400
N_PEDREGULHOS = 160
N_ARBUSTOS = 520
N_ERVAS = 700
N_CACTOS = 38

MEIO = TAMANHO / 2.0

# =============================================================================
# Utilitários
# =============================================================================


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def sstep(e0, e1, x):
    """smoothstep escalar."""
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def dir_az_el(az_deg, el_deg):
    """Vetor unitário a partir de azimute (N=0, E=90) e elevação."""
    az, el = math.radians(az_deg), math.radians(el_deg)
    return Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))


# ---- Ruído de Perlin vetorizado (numpy) -------------------------------------


class Perlin2D:
    _GRAD = np.array([[math.cos(a), math.sin(a)] for a in np.linspace(0, 2 * math.pi, 16, endpoint=False)])

    def __init__(self, seed):
        rng = np.random.default_rng(seed)
        p = rng.permutation(256)
        self.perm = np.concatenate([p, p]).astype(np.int64)

    def __call__(self, x, y):
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        xf0 = np.floor(x)
        yf0 = np.floor(y)
        xi = xf0.astype(np.int64) & 255
        yi = yf0.astype(np.int64) & 255
        xf = x - xf0
        yf = y - yf0
        u = xf * xf * xf * (xf * (xf * 6 - 15) + 10)
        v = yf * yf * yf * (yf * (yf * 6 - 15) + 10)
        perm = self.perm
        g = self._GRAD

        def grad(ix, iy, dx, dy):
            h = perm[perm[ix] + iy] & 15
            return g[h, 0] * dx + g[h, 1] * dy

        n00 = grad(xi, yi, xf, yf)
        n10 = grad(xi + 1, yi, xf - 1, yf)
        n01 = grad(xi, yi + 1, xf, yf - 1)
        n11 = grad(xi + 1, yi + 1, xf - 1, yf - 1)
        a = n00 + u * (n10 - n00)
        b = n01 + u * (n11 - n01)
        return (a + v * (b - a)) * 1.4


_ruidos = {}


def fbm(x, y, oct=4, seed=0, lac=2.0, gain=0.5):
    total = 0.0
    amp = 1.0
    norm = 0.0
    f = 1.0
    for o in range(oct):
        key = seed * 101 + o
        if key not in _ruidos:
            _ruidos[key] = Perlin2D(SEMENTE * 1000 + key)
        total = total + amp * _ruidos[key](x * f + 17.3 * o, y * f - 9.1 * o)
        norm += amp
        amp *= gain
        f *= lac
    return total / norm


def ridged(x, y, oct=5, seed=0):
    total = 0.0
    amp = 1.0
    norm = 0.0
    f = 1.0
    for o in range(oct):
        key = seed * 101 + o + 50
        if key not in _ruidos:
            _ruidos[key] = Perlin2D(SEMENTE * 1000 + key)
        n = 1.0 - np.abs(_ruidos[key](x * f + 3.1 * o, y * f + 5.7 * o))
        total = total + amp * n * n
        norm += amp
        amp *= 0.5
        f *= 2.0
    return total / norm


# =============================================================================
# Terreno (função de altura contínua - usada no terreno próximo e distante)
# =============================================================================

BUTTES = [
    # x, y, raio, altura   (monólitos isolados na planície)
    (-10.0, 105.0, 24.0, 42.0),
    (35.0, 40.0, 12.0, 30.0),
    (-45.0, -150.0, 34.0, 36.0),
    (60.0, 175.0, 18.0, 26.0),
    (-20.0, -40.0, 9.0, 21.0),
]


def terraco(h, X, Y, passo, seed, forca=0.8):
    """Estratificação em degraus (bancadas planas + escarpas)."""
    q = (h + 1.8 * fbm(X / 90.0, Y / 90.0, 2, seed)) / passo
    f = q - np.floor(q)
    f2 = smoothstep(0.55, 0.97, f)
    hq = (np.floor(q) + f2) * passo
    return lerp(h, hq, forca)


def altura(X, Y):
    """Devolve (altura, mascara_rocha, mascara_duna, mascara_playa)."""
    # o mapa está rodado 45 graus: canyons a NO, dunas a SE, poente livre a OSO
    X0, Y0 = X, Y
    r = np.sqrt(X * X + Y * Y)
    # direção do poente (OSO): fora dos 500 m o horizonte fica livre para o sol
    poente = (X0 * -0.927 + Y0 * -0.375) / np.maximum(r, 1.0)
    livre = smoothstep(0.7, 0.88, poente) * smoothstep(260.0, 420.0, r)
    X, Y = (X - Y) * 0.70710678, (X + Y) * 0.70710678
    # distorção de domínio - quebra formas regulares
    wx = fbm(X / 190.0, Y / 190.0, 3, 11) * 45.0
    wy = fbm(X / 190.0, Y / 190.0, 3, 12) * 45.0
    Xw, Yw = X + wx, Y + wy

    # --- regiões -------------------------------------------------------------
    borda_c = -80.0 + 30.0 * fbm(Y / 140.0, 0.5, 3, 13) + 14.0 * fbm(Y / 40.0, 2.5, 2, 15)
    w_canyon = smoothstep(borda_c + 12.0, borda_c - 10.0, Xw) * (1.0 - livre)
    borda_d = 85.0 + 25.0 * fbm(Y / 130.0, 3.5, 3, 14)
    w_duna = smoothstep(borda_d - 35.0, borda_d + 30.0, Xw)

    # --- planície --------------------------------------------------------------
    plan = 1.6 * fbm(X / 260.0, Y / 260.0, 4, 1) + 0.35 * fbm(X / 45.0, Y / 45.0, 3, 2)
    # bajada: a planície sobe suavemente em direção às mesas
    plan += 6.0 * smoothstep(40.0, -120.0, Xw)
    # leito seco (playa)
    dp = np.sqrt(((X - 25.0) / 75.0) ** 2 + ((Y + 105.0) / 42.0) ** 2) + 0.18 * fbm(X / 60.0, Y / 60.0, 3, 3)
    w_playa = smoothstep(1.0, 0.78, dp) * (1.0 - w_duna) * (1.0 - w_canyon)
    plan = lerp(plan, -0.5 + 0.04 * fbm(X / 8.0, Y / 8.0, 2, 4), w_playa)
    # leitos de ribeira secos (arroios) que saem dos canyons
    arroio = np.abs(fbm(Xw / 220.0, Yw / 90.0, 3, 5))
    plan -= 1.3 * smoothstep(0.06, 0.0, arroio) * (1.0 - w_playa)

    # --- dunas (vento de oeste; cristas N-S; face de avalanche a este) -------
    fase = (X + 0.35 * Y + 22.0 * fbm(Y / 95.0, X / 95.0, 3, 21)) / 58.0
    f = fase - np.floor(fase)
    a = 0.74
    s = np.where(f < a, f / a, (1.0 - f) / (1.0 - a))
    perfil = 0.45 * s + 0.55 * s * s * (3.0 - 2.0 * s)
    amp = 8.5 * np.clip(0.55 + 0.9 * fbm(X / 170.0, Y / 170.0, 3, 22), 0.15, 1.2)
    fase2 = (X * 0.8 - Y * 0.6 + 7.0 * fbm(X / 40.0, Y / 40.0, 2, 23)) / 17.0
    f2 = fase2 - np.floor(fase2)
    s2 = np.where(f2 < 0.7, f2 / 0.7, (1.0 - f2) / 0.3)
    dunas = amp * perfil + 1.1 * s2 * s2 + 5.0 * (fbm(X / 280.0, Y / 280.0, 2, 24) + 0.4) + 1.0
    H = lerp(plan, np.maximum(plan, dunas), w_duna)

    # --- mesas e canyons -------------------------------------------------------
    Xc = Xw + 25.0 * fbm(X / 70.0, Y / 70.0, 2, 31)
    Yc = Yw + 25.0 * fbm(X / 70.0, Y / 70.0, 2, 32)
    n1 = np.abs(fbm(Xc / 190.0, Yc / 190.0, 4, 33))
    n2 = np.abs(fbm(Xc / 95.0 + 4.0, Yc / 95.0, 3, 34))
    t1 = smoothstep(0.018, 0.075, n1)                      # rede de canyons
    # canyon principal: meandros de oeste para a boca virada à planície
    yc = 12.0 + 38.0 * np.sin(X / 75.0 + 0.6) + 18.0 * fbm(X / 60.0, 1.7, 3, 38)
    larg = 16.0 + 10.0 * smoothstep(-120.0, -20.0, X)       # alarga junto à boca
    t_main = smoothstep(larg, larg + 30.0, np.abs(Y - yc) + 6.0 * fbm(X / 25.0, Y / 25.0, 2, 39))
    t1 = t1 * t_main
    trib = 1.0 - smoothstep(0.12, 0.3, n1)                 # afluentes só perto dele
    t2 = lerp(1.0, smoothstep(0.008, 0.035, n2), trib)     # canyons secundários
    t = t1 * t2
    planalto = 50.0 + 9.0 * fbm(X / 320.0, Y / 320.0, 3, 35) + 2.0 * fbm(X / 30.0, Y / 30.0, 2, 36)
    fundo = plan + 0.8
    mesa = fundo + (planalto - fundo) * t ** 0.85
    Hc = lerp(H, mesa, w_canyon)

    # --- buttes isolados ------------------------------------------------------
    rocha_butte = np.zeros_like(H)
    for i, (bx, by, br, bh) in enumerate(BUTTES):
        d = np.sqrt((X - bx) ** 2 + (Y - by) ** 2) / br
        d = d + 0.16 * fbm(X / 18.0, Y / 18.0, 3, 40 + i)
        topo = bh * (1.0 - smoothstep(0.82, 1.08, d))
        talude = bh * 0.38 * smoothstep(2.1, 1.0, d) ** 2
        b = H + np.maximum(topo, talude)
        Hc = np.maximum(Hc, b)
        rocha_butte = np.maximum(rocha_butte, smoothstep(1.35, 1.0, d))

    # estratificação (degraus) só nas zonas rochosas
    w_rocha = np.clip(np.maximum(w_canyon, rocha_butte), 0.0, 1.0)
    Hc = lerp(Hc, terraco(Hc, X, Y, 6.5, 37), smoothstep(0.0, 0.35, w_rocha))

    # --- relevo distante (fora dos 500 m) ------------------------------------
    w_longe = smoothstep(700.0, 2600.0, r)
    if np.any(w_longe > 0):
        oeste = smoothstep(-0.2, 0.8, -X / np.maximum(r, 1.0))  # mais relevo a oeste
        mesas_long = 160.0 * smoothstep(0.02, 0.2, fbm(X / 1100.0, Y / 1100.0, 3, 50))
        mesas_long = terraco(mesas_long, X, Y, 38.0, 51, 0.9)
        serras = 520.0 * ridged(X / 3200.0, Y / 3200.0, 5, 52) ** 2.2 * smoothstep(3500.0, 7000.0, r)
        # horizonte baixo na direção do poente (o sol toca o horizonte perto dos 0 graus)
        baixo = 1.0 - 0.85 * smoothstep(0.82, 0.97, poente)
        Hc = Hc + w_longe * (mesas_long * (0.35 + 0.65 * oeste) + serras) * baixo
        w_rocha = np.maximum(w_rocha, w_longe * smoothstep(8.0, 40.0, mesas_long))

    return Hc, w_rocha, w_duna * (1.0 - w_rocha), w_playa


# =============================================================================
# Limpeza da cena
# =============================================================================


def limpar_cena():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for col in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras,
                bpy.data.worlds, bpy.data.node_groups, bpy.data.images, bpy.data.curves,
                bpy.data.actions):
        for b in list(col):
            col.remove(b)
    sc = bpy.context.scene
    for c in list(sc.collection.children):
        bpy.data.collections.remove(c)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)


def colecao(nome, pai=None):
    c = bpy.data.collections.new(nome)
    (pai or bpy.context.scene.collection).children.link(c)
    return c


# =============================================================================
# Malhas do terreno
# =============================================================================


def malha_grelha(nome, xs, ys, Z, cores=None, remover_nucleo=None):
    """Cria malha de grelha (tensor xs x ys) com alturas Z[j, i]."""
    nx, ny = len(xs), len(ys)
    GX, GY = np.meshgrid(xs, ys)
    co = np.stack([GX, GY, Z], axis=-1).reshape(-1, 3).astype(np.float32)

    i = np.arange(nx - 1)
    j = np.arange(ny - 1)
    I, J = np.meshgrid(i, j)
    I = I.ravel()
    J = J.ravel()
    if remover_nucleo is not None:
        cx = 0.5 * (xs[I] + xs[I + 1])
        cy = 0.5 * (ys[J] + ys[J + 1])
        m = ~((np.abs(cx) < remover_nucleo) & (np.abs(cy) < remover_nucleo))
        I, J = I[m], J[m]
    v0 = J * nx + I
    quads = np.stack([v0, v0 + 1, v0 + nx + 1, v0 + nx], axis=-1).ravel().astype(np.int32)
    nf = len(v0)

    me = bpy.data.meshes.new(nome)
    me.vertices.add(len(co))
    me.vertices.foreach_set("co", co.ravel())
    me.loops.add(nf * 4)
    me.loops.foreach_set("vertex_index", quads)
    me.polygons.add(nf)
    me.polygons.foreach_set("loop_start", np.arange(0, nf * 4, 4, dtype=np.int32))
    me.polygons.foreach_set("use_smooth", np.ones(nf, dtype=bool))
    if cores is not None:
        ca = me.color_attributes.new("mascaras", 'FLOAT_COLOR', 'POINT')
        ca.data.foreach_set("color", cores.astype(np.float32).ravel())
    me.update(calc_edges=True)
    me.validate(verbose=False)
    return me


def eixo_horizonte(meio, passo_nucleo, raio):
    """Eixo com passo fino no núcleo e passo crescente para o horizonte."""
    nucleo = np.linspace(-meio, meio, int(round(2 * meio / passo_nucleo)) + 1)
    fora = []
    x, p = meio, passo_nucleo
    while x < raio:
        p = min(p * 1.045, 90.0)
        x += p
        fora.append(x)
    fora = np.array(fora)
    return np.concatenate([-fora[::-1], nucleo, fora])


def criar_terreno(col):
    print("[deserto] a gerar terreno principal ...")
    xs = np.linspace(-MEIO, MEIO, RESOLUCAO)
    GX, GY = np.meshgrid(xs, xs)
    H, rocha, duna, playa = altura(GX, GY)
    cores = np.stack([rocha, duna, playa, np.ones_like(H)], axis=-1)
    me = malha_grelha("Terreno_500m", xs, xs, H, cores)
    ob = bpy.data.objects.new("Terreno_500m", me)
    col.objects.link(ob)

    print("[deserto] a gerar terreno distante ...")
    ax = eixo_horizonte(MEIO, 5.0, RAIO_HORIZONTE)
    GX2, GY2 = np.meshgrid(ax, ax)
    H2, r2, d2, p2 = altura(GX2, GY2)
    # dentro do núcleo o terreno distante afunda (fica escondido)
    dist_q = np.maximum(np.abs(GX2), np.abs(GY2))
    H2 = H2 - 30.0 * smoothstep(MEIO, MEIO - 5.0, dist_q)
    cores2 = np.stack([r2, d2, p2, np.zeros_like(H2)], axis=-1)
    me2 = malha_grelha("Terreno_Horizonte", ax, ax, H2, cores2, remover_nucleo=MEIO - 5.0)
    ob2 = bpy.data.objects.new("Terreno_Horizonte", me2)
    col.objects.link(ob2)
    return ob, ob2


# =============================================================================
# Nós: pequenos ajudantes
# =============================================================================


class NB:
    """Construtor de árvores de nós compacto."""

    def __init__(self, tree):
        self.t = tree
        self.n = tree.nodes
        self.l = tree.links
        self.x = 0

    def node(self, tipo, loc=None, **props):
        nd = self.n.new(tipo)
        for k, v in props.items():
            setattr(nd, k, v)
        if loc:
            nd.location = loc
        else:
            nd.location = (self.x, 0)
            self.x += 30
        return nd

    def link(self, a, b):
        self.l.new(a, b)

    def put(self, sock, v):
        if isinstance(v, bpy.types.NodeSocket):
            self.link(v, sock)
        else:
            if isinstance(v, tuple) and len(v) == 3 and len(sock.default_value) == 4:
                v = (*v, 1.0)
            sock.default_value = v

    def math(self, op, a, b=None, c=None, clamp=False):
        nd = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        self.put(nd.inputs[0], a)
        if b is not None:
            self.put(nd.inputs[1], b)
        if c is not None:
            self.put(nd.inputs[2], c)
        return nd.outputs[0]

    def vmath(self, op, a, b=None, sc=None):
        nd = self.node("ShaderNodeVectorMath", operation=op)
        self.put(nd.inputs[0], a)
        if b is not None:
            self.put(nd.inputs[1], b)
        if sc is not None:
            self.put(nd.inputs["Scale"], sc)
        out = nd.outputs["Value"] if op in ("DOT_PRODUCT", "LENGTH", "DISTANCE") else nd.outputs["Vector"]
        return out

    def mix(self, fac, a, b, tipo='RGBA', blend='MIX', clamp=True):
        nd = self.node("ShaderNodeMix", data_type=tipo, blend_type=blend, clamp_factor=clamp)
        if tipo == 'RGBA':
            ins = (nd.inputs[0], nd.inputs[6], nd.inputs[7])
            out = nd.outputs[2]
        elif tipo == 'FLOAT':
            ins = (nd.inputs[0], nd.inputs[2], nd.inputs[3])
            out = nd.outputs[0]
        else:
            ins = (nd.inputs[0], nd.inputs[4], nd.inputs[5])
            out = nd.outputs[1]
        self.put(ins[0], fac)
        self.put(ins[1], a)
        self.put(ins[2], b)
        return out

    def maprange(self, v, a, b, c=0.0, d=1.0, tipo='LINEAR', clamp=True):
        nd = self.node("ShaderNodeMapRange", interpolation_type=tipo, clamp=clamp)
        self.put(nd.inputs[0], v)
        nd.inputs[1].default_value = a
        nd.inputs[2].default_value = b
        nd.inputs[3].default_value = c
        nd.inputs[4].default_value = d
        return nd.outputs[0]

    def ramp(self, fac, pontos, interp='LINEAR'):
        nd = self.node("ShaderNodeValToRGB")
        cr = nd.color_ramp
        cr.interpolation = interp
        els = cr.elements
        while len(els) > 1:
            els.remove(els[-1])
        els[0].position = pontos[0][0]
        els[0].color = (*pontos[0][1], 1.0)
        for p, c in pontos[1:]:
            e = els.new(p)
            e.color = (*c, 1.0)
        self.put(nd.inputs[0], fac)
        return nd.outputs[0]

    def sep(self, v):
        nd = self.node("ShaderNodeSeparateXYZ")
        self.put(nd.inputs[0], v)
        return nd.outputs

    def comb(self, x, y, z):
        nd = self.node("ShaderNodeCombineXYZ")
        self.put(nd.inputs[0], x)
        self.put(nd.inputs[1], y)
        self.put(nd.inputs[2], z)
        return nd.outputs[0]

    def noise(self, vec, escala, detalhe=4.0, rug=0.5, dist=0.0, dims='3D', tipo='FBM', w=None):
        nd = self.node("ShaderNodeTexNoise", noise_dimensions=dims)
        try:
            nd.noise_type = tipo
        except Exception:
            pass
        if vec is not None:
            self.put(nd.inputs["Vector"], vec)
        nd.inputs["Scale"].default_value = escala
        nd.inputs["Detail"].default_value = detalhe
        nd.inputs["Roughness"].default_value = rug
        nd.inputs["Distortion"].default_value = dist
        if w is not None:
            self.put(nd.inputs["W"], w)
        return nd

    def valor(self, nome, v=0.0):
        nd = self.node("ShaderNodeValue")
        nd.name = nd.label = nome
        nd.outputs[0].default_value = v
        return nd

    def vetor(self, nome, v=(0, 0, 1)):
        nd = self.node("ShaderNodeCombineXYZ")
        nd.name = nd.label = nome
        for k in range(3):
            nd.inputs[k].default_value = v[k]
        return nd

    def rgb(self, nome, c):
        nd = self.node("ShaderNodeRGB")
        nd.name = nd.label = nome
        nd.outputs[0].default_value = (*c, 1.0)
        return nd


def arrumar(tree, col_w=260):
    """Disposição simples em colunas por profundidade (só estética)."""
    prof = {}

    def depth(n, seen=()):
        if n in prof:
            return prof[n]
        d = 0
        for s in n.outputs:
            for lk in s.links:
                if lk.to_node not in seen:
                    d = max(d, depth(lk.to_node, seen + (n,)) + 1)
        prof[n] = d
        return d

    for n in tree.nodes:
        depth(n)
    maxd = max(prof.values()) if prof else 0
    linhas = {}
    for n in tree.nodes:
        c = maxd - prof[n]
        linhas.setdefault(c, 0)
        n.location = (c * col_w, -linhas[c] * 190)
        linhas[c] += 1


# =============================================================================
# Céu (grupo de nós partilhado pelo World e pela névoa do terreno)
# =============================================================================


def definir_tipo_ceu(sky):
    for tipo in ('MULTIPLE_SCATTERING', 'SINGLE_SCATTERING', 'NISHITA'):
        try:
            sky.sky_type = tipo
            break
        except TypeError:
            continue
    for nome, v in (("altitude", 600.0), ("air_density", 1.0), ("aerosol_density", 1.6),
                    ("dust_density", 1.6), ("ozone_density", 1.0)):
        if hasattr(sky, nome):
            try:
                setattr(sky, nome, v)
            except Exception:
                pass


def criar_grupo_ceu():
    g = bpy.data.node_groups.new("Ceu_Deserto", "ShaderNodeTree")
    g.interface.new_socket("Direcao", in_out='INPUT', socket_type='NodeSocketVector')
    g.interface.new_socket("Ceu", in_out='OUTPUT', socket_type='NodeSocketColor')
    g.interface.new_socket("Horizonte", in_out='OUTPUT', socket_type='NodeSocketColor')
    b = NB(g)
    gi = b.node("NodeGroupInput")
    go = b.node("NodeGroupOutput")

    d = b.vmath('NORMALIZE', gi.outputs[0])
    dx, dy, dz = b.sep(d)

    # --- controlos animados (keyframes) -----------------------------------
    k_sol = b.vetor("SolDir", (0, 1, 0.3))
    k_solh = b.vetor("SolDirH", (0, 1, 0))        # direção horizontal do sol
    k_brilho = b.valor("BrilhoCrepusculo", 0.0)
    k_aureola = b.valor("Aureola", 0.0)
    k_venus = b.valor("CinturaoVenus", 0.0)
    k_noite = b.valor("Noite", 0.0)
    k_estrelas = b.valor("Estrelas", 0.0)
    k_ceu = b.valor("ForcaCeu", 1.0)
    k_lua_r = b.vetor("LuaR", (1, 0, 0))
    k_lua_u = b.vetor("LuaU", (0, 0, 1))
    k_lua_m = b.vetor("LuaM", (0, 1, 0))
    k_lua_luz = b.vetor("LuaFase", (0, 0, 1))
    k_lua_int = b.valor("LuaIntensidade", 0.0)
    k_cor_brilho = b.rgb("CorCrepusculo", (1.0, 0.35, 0.08))
    k_t = b.valor("Tempo", 0.0)

    # --- céu físico (sem disco - para iluminação) --------------------------
    sky = b.node("ShaderNodeTexSky")
    sky.name = sky.label = "CeuFisico"
    definir_tipo_ceu(sky)
    sky.sun_disc = False
    b.link(d, sky.inputs[0])
    # céu físico com disco solar, só visto pela câmara
    sky2 = b.node("ShaderNodeTexSky")
    sky2.name = sky2.label = "CeuDiscoSolar"
    definir_tipo_ceu(sky2)
    sky2.sun_disc = True
    sky2.sun_size = math.radians(0.9)
    sky2.sun_intensity = 1.0
    b.link(d, sky2.inputs[0])
    lp = b.node("ShaderNodeLightPath")
    ceu_base = b.mix(lp.outputs["Is Camera Ray"], sky.outputs[0], sky2.outputs[0])
    ceu_base = b.mix(1.0, ceu_base, k_ceu.outputs[0], blend='MULTIPLY')

    # --- geometria relativa ao sol -----------------------------------------
    dh = b.vmath('NORMALIZE', b.comb(dx, dy, 0.0))
    cos_az = b.vmath('DOT_PRODUCT', dh, k_solh.outputs[0])       # -1..1
    dz_pos = b.math('MAXIMUM', dz, 0.0)

    # brilho do crepúsculo: faixa junto ao horizonte, concentrada no azimute do sol
    lado_sol = b.math('POWER', b.maprange(cos_az, -0.2, 1.0), 3.5)
    faixa = b.math('EXPONENT', b.math('MULTIPLY', dz_pos, -11.0))
    faixa_alta = b.math('EXPONENT', b.math('MULTIPLY', dz_pos, -3.0))
    brilho = b.math('ADD', b.math('MULTIPLY', faixa, lado_sol),
                    b.math('MULTIPLY', b.math('MULTIPLY', faixa_alta, 0.3), lado_sol))
    brilho = b.math('MULTIPLY', brilho, k_brilho.outputs[0])
    cor_topo = b.mix(b.maprange(dz, 0.0, 0.3), k_cor_brilho.outputs[0], (0.45, 0.16, 0.38))
    # auréola amarelo-dourada em torno do próprio sol (mesmo abaixo do horizonte)
    ang_sol = b.vmath('DOT_PRODUCT', d, k_sol.outputs[0])
    aureola = b.math('ADD', b.math('POWER', b.maprange(ang_sol, 0.85, 1.0), 8.0),
                     b.math('MULTIPLY', b.math('POWER', b.maprange(ang_sol, 0.6, 1.0), 3.0), 0.25))
    aureola = b.math('MULTIPLY', b.math('MULTIPLY', aureola, b.maprange(dz, -0.02, 0.02)), k_aureola.outputs[0])
    c_aureola = b.mix(1.0, (1.0, 0.62, 0.22), b.math('MULTIPLY', aureola, 1.6), blend='MULTIPLY')
    glow = b.mix(1.0, cor_topo, brilho, blend='MULTIPLY')

    # cinturão de Vénus (rosa) sobre a sombra da Terra (azul), do lado oposto
    oposto = b.math('POWER', b.maprange(cos_az, 0.3, -1.0), 1.5)
    banda_v = b.math('MULTIPLY', b.maprange(dz, 0.03, 0.09), b.maprange(dz, 0.28, 0.12))
    sombra = b.maprange(dz, 0.08, 0.0)
    venus = b.math('MULTIPLY', b.math('MULTIPLY', banda_v, oposto), k_venus.outputs[0])
    sombra_t = b.math('MULTIPLY', b.math('MULTIPLY', sombra, oposto), k_venus.outputs[0])
    c_venus = b.mix(1.0, (0.95, 0.42, 0.55), venus, blend='MULTIPLY')
    c_sombra = b.mix(1.0, (0.10, 0.14, 0.32), sombra_t, blend='MULTIPLY')

    # --- céu noturno -------------------------------------------------------
    grad_noite = b.mix(b.math('POWER', dz_pos, 0.5), (0.010, 0.015, 0.034), (0.0018, 0.0028, 0.008))
    base_noite = b.mix(1.0, grad_noite, k_noite.outputs[0], blend='MULTIPLY')

    # atenuação atmosférica das estrelas perto do horizonte
    ext = b.maprange(dz, 0.0, 0.25)

    # estrelas: voronoi na esfera celeste
    vor = b.node("ShaderNodeTexVoronoi", voronoi_dimensions='3D', feature='F1')
    b.link(d, vor.inputs["Vector"])
    vor.inputs["Scale"].default_value = 420.0
    vor.inputs["Randomness"].default_value = 1.0
    raio_e = b.maprange(vor.outputs["Distance"], 0.07, 0.0)
    rnd = b.sep(vor.outputs["Color"])
    mag = b.math('POWER', rnd[0], 14.0)
    est = b.math('MULTIPLY', b.math('POWER', raio_e, 2.0), mag)
    # campo de estrelas fracas mais denso
    vor2 = b.node("ShaderNodeTexVoronoi", voronoi_dimensions='3D', feature='F1')
    b.link(d, vor2.inputs["Vector"])
    vor2.inputs["Scale"].default_value = 1100.0
    rnd2 = b.sep(vor2.outputs["Color"])
    est2 = b.math('MULTIPLY', b.math('POWER', b.maprange(vor2.outputs["Distance"], 0.1, 0.0), 2.0),
                  b.math('POWER', rnd2[1], 6.0))
    # cintilação ligeira
    cint = b.noise(d, 60.0, 0.0, 0.5, dims='4D', w=b.math('MULTIPLY', k_t.outputs[0], 40.0))
    cint_f = b.maprange(cint.outputs[0], 0.3, 0.7, 0.6, 1.2)
    est_tot = b.math('MULTIPLY', b.math('ADD', b.math('MULTIPLY', est, 25.0), b.math('MULTIPLY', est2, 1.6)), cint_f)
    cor_est = b.mix(rnd[2], (0.75, 0.85, 1.0), (1.0, 0.85, 0.65))

    # Via Láctea: faixa em torno de um grande círculo que nasce a sudoeste
    nucleo_dir = dir_az_el(VIA_NUCLEO[0], VIA_NUCLEO[1])
    polo = nucleo_dir.cross(dir_az_el(262.0, 72.0)).normalized()
    dist_g = b.math('ABSOLUTE', b.vmath('DOT_PRODUCT', d, tuple(polo)))
    faixa_g = b.math('EXPONENT', b.math('MULTIPLY', b.math('POWER', b.math('DIVIDE', dist_g, 0.11), 2.0), -1.0))
    faixa_larga = b.math('EXPONENT', b.math('MULTIPLY', b.math('POWER', b.math('DIVIDE', dist_g, 0.3), 2.0), -1.0))
    nuvem = b.noise(d, 16.0, 10.0, 0.72)
    nuvem_g = b.noise(d, 4.0, 3.0, 0.5)
    nuvem_f = b.math('MULTIPLY', b.maprange(nuvem.outputs[0], 0.38, 0.72), b.maprange(nuvem_g.outputs[0], 0.3, 0.65, 0.4, 1.2))
    poeira = b.noise(d, 9.0, 8.0, 0.65)
    lanes = b.math('MULTIPLY', b.maprange(poeira.outputs[0], 0.5, 0.6), b.maprange(dist_g, 0.0, 0.08, 1.0, 0.0))
    # núcleo galáctico mais brilhante (sudoeste, baixo no horizonte)
    nuc = b.math('POWER', b.maprange(b.vmath('DOT_PRODUCT', d, tuple(nucleo_dir)), 0.75, 1.0), 2.0)
    via = b.math('ADD', b.math('MULTIPLY', faixa_g, b.math('ADD', nuvem_f, b.math('MULTIPLY', nuc, 1.5))),
                 b.math('MULTIPLY', faixa_larga, 0.12))
    via = b.math('MULTIPLY', via, b.math('SUBTRACT', 1.0, b.math('MULTIPLY', lanes, 0.9), clamp=True))
    cor_via = b.mix(nuc, (0.62, 0.66, 0.85), (1.0, 0.80, 0.60))
    k_via = b.math('POWER', k_estrelas.outputs[0], 2.5)
    via_c = b.mix(1.0, cor_via, b.math('MULTIPLY', b.math('MULTIPLY', via, 0.006), k_via), blend='MULTIPLY')
    # estrelas extra dentro da Via Láctea
    est_via = b.math('MULTIPLY', est2, b.math('MULTIPLY', b.math('MULTIPLY', faixa_g, nuvem_f), 5.0))
    est_tot = b.math('ADD', est_tot, est_via)
    est_c = b.mix(1.0, cor_est, est_tot, blend='MULTIPLY')
    est_c = b.mix(1.0, est_c, k_estrelas.outputs[0], blend='MULTIPLY')
    noturno = b.mix(1.0, est_c, via_c, blend='ADD')
    noturno = b.mix(1.0, noturno, ext, blend='MULTIPLY')

    # --- lua ----------------------------------------------------------------
    rad = math.radians(LUA_RAIO_GRAUS)
    u = b.math('DIVIDE', b.vmath('DOT_PRODUCT', d, k_lua_r.outputs[0]), rad)
    v = b.math('DIVIDE', b.vmath('DOT_PRODUCT', d, k_lua_u.outputs[0]), rad)
    frente = b.math('GREATER_THAN', b.vmath('DOT_PRODUCT', d, k_lua_m.outputs[0]), 0.0)
    r2 = b.math('ADD', b.math('MULTIPLY', u, u), b.math('MULTIPLY', v, v))
    disco = b.math('MULTIPLY', b.maprange(r2, 1.0, 0.94), frente)
    w = b.math('SQRT', b.math('MAXIMUM', b.math('SUBTRACT', 1.0, r2), 0.0))
    fase = b.sep(k_lua_luz.outputs[0])
    lit = b.math('ADD', b.math('ADD', b.math('MULTIPLY', u, fase[0]), b.math('MULTIPLY', v, fase[1])),
                 b.math('MULTIPLY', w, fase[2]))
    lit = b.maprange(lit, -0.04, 0.12, 0.012, 1.0)  # terminador suave + luz cinzenta
    mares = b.noise(b.comb(u, v, 0.0), 2.2, 5.0, 0.6)
    mares_f = b.maprange(mares.outputs[0], 0.4, 0.62, 1.0, 0.62)
    lua_v = b.math('MULTIPLY', b.math('MULTIPLY', disco, lit), mares_f)
    halo = b.math('MULTIPLY', b.math('EXPONENT', b.math('MULTIPLY', b.math('SQRT', r2), -1.6)), 0.018)
    halo = b.math('MULTIPLY', halo, frente)
    lua_tot = b.math('MULTIPLY', b.math('ADD', b.math('MULTIPLY', lua_v, 1.0), halo), k_lua_int.outputs[0])
    lua_c = b.mix(1.0, (1.0, 0.97, 0.9), lua_tot, blend='MULTIPLY')

    # --- soma ---------------------------------------------------------------
    horiz = b.mix(1.0, ceu_base, glow, blend='ADD')
    horiz = b.mix(1.0, horiz, c_aureola, blend='ADD')
    horiz = b.mix(1.0, horiz, c_venus, blend='ADD')
    horiz = b.mix(sombra_t, horiz, c_sombra, blend='MIX')
    horiz = b.mix(1.0, horiz, base_noite, blend='ADD')
    tot = b.mix(1.0, horiz, noturno, blend='ADD')
    tot = b.mix(1.0, tot, lua_c, blend='ADD')
    b.link(tot, go.inputs[0])
    b.link(horiz, go.inputs[1])
    arrumar(g)
    return g


def criar_mundo(grupo):
    w = bpy.data.worlds.new("Mundo_Deserto")
    bpy.context.scene.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    nt = w.node_tree
    nt.nodes.clear()
    b = NB(nt)
    tc = b.node("ShaderNodeTexCoord")
    gn = b.node("ShaderNodeGroup")
    gn.node_tree = grupo
    b.link(tc.outputs["Generated"], gn.inputs[0])
    bg = b.node("ShaderNodeBackground")
    b.link(gn.outputs[0], bg.inputs[0])
    out = b.node("ShaderNodeOutputWorld")
    b.link(bg.outputs[0], out.inputs[0])
    arrumar(nt)
    try:
        w.cycles.sampling_method = 'MANUAL'
        w.cycles.sample_map_resolution = 2048
    except Exception:
        pass
    return w


# =============================================================================
# Materiais
# =============================================================================


def mat_novo(nome):
    m = bpy.data.materials.new(nome)
    try:
        m.use_nodes = True
    except Exception:
        pass
    m.node_tree.nodes.clear()
    return m, NB(m.node_tree)


def criar_mat_terreno(grupo_ceu):
    m, b = mat_novo("Terreno_Deserto")
    tc = b.node("ShaderNodeTexCoord")
    geo = b.node("ShaderNodeNewGeometry")
    pos = geo.outputs["Position"]
    attr = b.node("ShaderNodeAttribute", attribute_name="mascaras")
    msk = b.node("ShaderNodeSeparateColor")
    b.link(attr.outputs["Color"], msk.inputs[0])
    m_rocha, m_duna, m_playa = msk.outputs[0], msk.outputs[1], msk.outputs[2]
    px, py, pz = b.sep(pos)
    nz = b.sep(geo.outputs["Normal"])[2]
    declive = b.maprange(nz, 0.93, 0.62)          # 0 plano .. 1 íngreme

    # --- areia ---------------------------------------------------------------
    n_areia = b.noise(pos, 0.012, 4.0, 0.55)
    areia1 = b.mix(n_areia.outputs[0], (0.84, 0.45, 0.18), (0.72, 0.34, 0.12))
    n_plan = b.noise(pos, 0.03, 5.0, 0.6)
    plan_c = b.mix(n_plan.outputs[0], (0.72, 0.48, 0.30), (0.58, 0.38, 0.24))
    # cascalho escuro (reg / pavimento desértico)
    vor = b.node("ShaderNodeTexVoronoi", feature='F1')
    b.link(pos, vor.inputs["Vector"])
    vor.inputs["Scale"].default_value = 9.0
    casc = b.math('MULTIPLY', b.maprange(vor.outputs["Distance"], 0.25, 0.12),
                  b.maprange(b.sep(vor.outputs["Color"])[0], 0.55, 0.8))
    plan_c = b.mix(b.math('MULTIPLY', casc, 0.7), plan_c, (0.26, 0.17, 0.12))
    solo = b.mix(m_duna, plan_c, areia1)
    # playa: argila clara com gretas
    vor_g = b.node("ShaderNodeTexVoronoi", feature='DISTANCE_TO_EDGE')
    n_greta = b.noise(pos, 0.8, 2.0, 0.5)
    b.link(b.vmath('ADD', pos, b.vmath('SCALE', n_greta.outputs["Color"], sc=0.35)), vor_g.inputs["Vector"])
    vor_g.inputs["Scale"].default_value = 1.1
    greta = b.maprange(vor_g.outputs["Distance"], 0.0, 0.035, 1.0, 0.0)
    playa_c = b.mix(greta, (0.74, 0.62, 0.48), (0.36, 0.28, 0.21))
    solo = b.mix(m_playa, solo, playa_c)

    # --- rocha (arenito estratificado) --------------------------------------
    n_estr = b.noise(pos, 0.04, 3.0, 0.5)
    zz = b.math('ADD', pz, b.math('MULTIPLY', n_estr.outputs[0], 5.0))
    estr = b.math('FRACT', b.math('DIVIDE', zz, 23.0))
    rocha_c = b.ramp(estr, [
        (0.00, (0.46, 0.15, 0.07)),
        (0.18, (0.62, 0.27, 0.11)),
        (0.32, (0.74, 0.43, 0.22)),
        (0.40, (0.84, 0.66, 0.46)),
        (0.47, (0.62, 0.30, 0.14)),
        (0.62, (0.52, 0.20, 0.10)),
        (0.78, (0.40, 0.19, 0.14)),
        (0.88, (0.70, 0.40, 0.20)),
        (1.00, (0.46, 0.15, 0.07)),
    ])
    n_rv = b.noise(pos, 0.3, 6.0, 0.6)
    rocha_c = b.mix(b.maprange(n_rv.outputs[0], 0.3, 0.7, 0.0, 0.35), rocha_c, (0.25, 0.12, 0.08))
    # verniz do deserto: escorrências escuras verticais nas paredes
    esc = b.noise(b.vmath('MULTIPLY', pos, (0.35, 0.35, 0.025)), 2.0, 4.0, 0.6)
    verniz = b.math('MULTIPLY', b.maprange(esc.outputs[0], 0.5, 0.7), declive)
    rocha_c = b.mix(b.math('MULTIPLY', verniz, 0.75), rocha_c, (0.12, 0.07, 0.05))

    # fator rocha: máscara + declive
    f_rocha = b.math('MAXIMUM', b.math('MULTIPLY', m_rocha, b.maprange(nz, 0.97, 0.85)),
                     b.maprange(nz, 0.72, 0.5))
    f_rocha = b.math('MULTIPLY', f_rocha, b.math('SUBTRACT', 1.0, b.math('MULTIPLY', m_duna, 0.8)), clamp=True)
    n_mix = b.noise(pos, 0.15, 4.0, 0.6)
    f_rocha = b.maprange(b.math('ADD', f_rocha, b.math('MULTIPLY', b.math('SUBTRACT', n_mix.outputs[0], 0.5), 0.5)),
                         0.35, 0.6)
    cor = b.mix(f_rocha, solo, rocha_c)

    # --- relevo fino (bump) --------------------------------------------------
    # ondulações do vento na areia
    ond = b.node("ShaderNodeTexWave", wave_type='BANDS', bands_direction='X', wave_profile='SIN')
    b.link(b.vmath('ADD', pos, b.vmath('SCALE', b.vmath('MULTIPLY', pos, (0.0, 1.0, 0.0)), sc=0.35)), ond.inputs["Vector"])
    ond.inputs["Scale"].default_value = 3.2
    ond.inputs["Distortion"].default_value = 5.0
    ond.inputs["Detail"].default_value = 2.0
    ond.inputs["Detail Scale"].default_value = 0.4
    f_ond = b.math('MULTIPLY', b.math('SUBTRACT', 1.0, f_rocha), b.maprange(nz, 0.9, 0.99))
    f_ond = b.math('MULTIPLY', f_ond, b.math('ADD', m_duna, 0.25), clamp=True)
    h_ond = b.math('MULTIPLY', ond.outputs["Fac"], f_ond)
    n_bump = b.noise(pos, 0.6, 8.0, 0.65)
    h_rocha = b.math('MULTIPLY', n_bump.outputs[0], f_rocha)
    grao = b.noise(pos, 25.0, 2.0, 0.5)
    h_tot = b.math('ADD', b.math('ADD', b.math('MULTIPLY', h_ond, 0.6), b.math('MULTIPLY', h_rocha, 3.0)),
                   b.math('MULTIPLY', grao.outputs[0], 0.08))
    h_tot = b.math('ADD', h_tot, b.math('MULTIPLY', greta, b.math('MULTIPLY', m_playa, 0.4)))
    bump = b.node("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.08
    b.link(h_tot, bump.inputs["Height"])

    bsdf = b.node("ShaderNodeBsdfPrincipled")
    b.link(cor, bsdf.inputs["Base Color"])
    b.link(b.mix(f_rocha, 0.95, 0.82, tipo='FLOAT'), bsdf.inputs["Roughness"])
    b.link(bump.outputs[0], bsdf.inputs["Normal"])
    bsdf.inputs["Specular IOR Level"].default_value = 0.12
    # brilho da areia contra a luz
    bsdf.inputs["Sheen Weight"].default_value = 0.04
    bsdf.inputs["Sheen Roughness"].default_value = 0.5
    try:
        bsdf.inputs["Diffuse Roughness"].default_value = 0.6
    except KeyError:
        pass

    # --- perspetiva aérea (névoa de distância com a cor do horizonte) -------
    cam = b.node("ShaderNodeCameraData")
    vista = b.vmath('SCALE', geo.outputs["Incoming"], sc=-1.0)
    vx, vy, vz = b.sep(vista)
    dir_h = b.comb(vx, vy, 0.035)
    gceu = b.node("ShaderNodeGroup")
    gceu.node_tree = grupo_ceu
    b.link(dir_h, gceu.inputs[0])
    nev = b.math('SUBTRACT', 1.0, b.math('EXPONENT', b.math('DIVIDE', cam.outputs["View Distance"], -4500.0)))
    nev = b.math('MULTIPLY', nev, 0.92)
    em = b.node("ShaderNodeEmission")
    b.link(gceu.outputs["Horizonte"], em.inputs[0])
    ms = b.node("ShaderNodeMixShader")
    b.link(nev, ms.inputs[0])
    b.link(bsdf.outputs[0], ms.inputs[1])
    b.link(em.outputs[0], ms.inputs[2])
    out = b.node("ShaderNodeOutputMaterial")
    b.link(ms.outputs[0], out.inputs[0])
    arrumar(m.node_tree)
    return m


def criar_mat_rocha():
    m, b = mat_novo("Pedra_Arenito")
    tc = b.node("ShaderNodeTexCoord")
    geo = b.node("ShaderNodeNewGeometry")
    obj = tc.outputs["Object"]
    info = b.node("ShaderNodeObjectInfo")
    n1 = b.noise(obj, 1.2, 6.0, 0.6)
    base = b.mix(info.outputs["Random"], (0.55, 0.24, 0.11), (0.42, 0.26, 0.17))
    c = b.mix(b.maprange(n1.outputs[0], 0.35, 0.7), base, (0.30, 0.15, 0.09))
    # pó/areia depositada no topo
    nz = b.sep(geo.outputs["Normal"])[2]
    c = b.mix(b.maprange(nz, 0.55, 0.9, 0.0, 0.55), c, (0.78, 0.50, 0.27))
    n2 = b.noise(obj, 6.0, 8.0, 0.7)
    bump = b.node("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.5
    b.link(n2.outputs[0], bump.inputs["Height"])
    bsdf = b.node("ShaderNodeBsdfPrincipled")
    b.link(c, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    bsdf.inputs["Specular IOR Level"].default_value = 0.3
    b.link(bump.outputs[0], bsdf.inputs["Normal"])
    out = b.node("ShaderNodeOutputMaterial")
    b.link(bsdf.outputs[0], out.inputs[0])
    arrumar(m.node_tree)
    return m


def criar_mat_madeira_seca():
    m, b = mat_novo("Arbusto_Seco")
    info = b.node("ShaderNodeObjectInfo")
    tc = b.node("ShaderNodeTexCoord")
    n = b.noise(tc.outputs["Object"], 8.0, 3.0, 0.5)
    c = b.mix(b.math('ADD', b.math('MULTIPLY', n.outputs[0], 0.6), b.math('MULTIPLY', info.outputs["Random"], 0.4)),
              (0.30, 0.22, 0.15), (0.52, 0.44, 0.33))
    bsdf = b.node("ShaderNodeBsdfPrincipled")
    b.link(c, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.9
    out = b.node("ShaderNodeOutputMaterial")
    b.link(bsdf.outputs[0], out.inputs[0])
    return m


def criar_mat_erva():
    m, b = mat_novo("Erva_Seca")
    info = b.node("ShaderNodeObjectInfo")
    tc = b.node("ShaderNodeTexCoord")
    gz = b.sep(tc.outputs["Object"])[2]
    c = b.mix(info.outputs["Random"], (0.62, 0.50, 0.30), (0.75, 0.62, 0.38))
    c = b.mix(b.maprange(gz, 0.0, 0.25, 1.0, 0.0), c, (0.35, 0.28, 0.18))
    bsdf = b.node("ShaderNodeBsdfPrincipled")
    b.link(c, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.8
    bsdf.inputs["Transmission Weight"].default_value = 0.0
    try:
        bsdf.inputs["Subsurface Weight"].default_value = 0.15
    except KeyError:
        pass
    out = b.node("ShaderNodeOutputMaterial")
    b.link(bsdf.outputs[0], out.inputs[0])
    return m


def criar_mat_cacto():
    m, b = mat_novo("Cacto_Saguaro")
    tc = b.node("ShaderNodeTexCoord")
    ox, oy, oz = b.sep(tc.outputs["Object"])
    ang = b.math('ARCTAN2', oy, ox)
    costelas = b.math('ABSOLUTE', b.math('SINE', b.math('MULTIPLY', ang, 11.0)))
    costelas = b.math('POWER', costelas, 0.5)
    info = b.node("ShaderNodeObjectInfo")
    c = b.mix(info.outputs["Random"], (0.16, 0.24, 0.10), (0.22, 0.27, 0.13))
    c = b.mix(b.math('SUBTRACT', 1.0, costelas), c, (0.08, 0.12, 0.05))
    n = b.noise(tc.outputs["Object"], 3.0, 4.0, 0.5)
    c = b.mix(b.maprange(n.outputs[0], 0.55, 0.75, 0.0, 0.5), c, (0.35, 0.33, 0.22))
    bump = b.node("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.6
    b.link(costelas, bump.inputs["Height"])
    bsdf = b.node("ShaderNodeBsdfPrincipled")
    b.link(c, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.55
    b.link(bump.outputs[0], bsdf.inputs["Normal"])
    out = b.node("ShaderNodeOutputMaterial")
    b.link(bsdf.outputs[0], out.inputs[0])
    return m


# =============================================================================
# Recursos para scatter (pedras, arbustos, erva, cactos)
# =============================================================================


def objeto_malha(nome, bm, col, mat):
    me = bpy.data.meshes.new(nome)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat)
    ob = bpy.data.objects.new(nome, me)
    col.objects.link(ob)
    return ob


def criar_pedra(nome, col, mat, rng, tipo):
    from mathutils import noise as mn
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=4, radius=1.0)
    esc = Vector((rng.uniform(0.8, 1.4), rng.uniform(0.7, 1.2), rng.uniform(0.45, 0.8)))
    if tipo == 'pedregulho':
        esc.z *= 1.2
    off = Vector((rng.uniform(-50, 50), rng.uniform(-50, 50), rng.uniform(-50, 50)))
    for v in bm.verts:
        p = v.co.copy()
        n = mn.fractal(p * 1.3 + off, 0.6, 2.0, 5)
        # facetas: cortes planos aproximados
        p = p * (1.0 + 0.28 * n)
        p = Vector((p.x * esc.x, p.y * esc.y, p.z * esc.z))
        if p.z < -0.15 * esc.z:
            p.z = -0.15 * esc.z + (p.z + 0.15 * esc.z) * 0.3
        v.co = p
    return objeto_malha(nome, bm, col, mat)


def arvore_skin(nome, col, mat, verts, arestas, raios, subsurf=1):
    me = bpy.data.meshes.new(nome)
    me.from_pydata(verts, arestas, [])
    me.materials.append(mat)
    ob = bpy.data.objects.new(nome, me)
    col.objects.link(ob)
    sk = ob.modifiers.new("Skin", 'SKIN')
    sk.use_smooth_shade = True
    sk.branch_smoothing = 0.5
    for i, r in enumerate(raios):
        ob.data.skin_vertices[0].data[i].radius = (r, r)
    ob.data.skin_vertices[0].data[0].use_root = True
    if subsurf:
        ss = ob.modifiers.new("Subdiv", 'SUBSURF')
        ss.levels = subsurf
        ss.render_levels = subsurf
    return ob


def criar_arbusto(nome, col, mat, rng):
    verts = [(0.0, 0.0, -0.05)]
    arestas = []
    raios = [0.035]

    def ramo(pai, direc, comp, raio, nivel):
        pos = Vector(verts[pai])
        segs = 3
        idx = pai
        for s in range(segs):
            direc = (direc + Vector((rng.uniform(-0.35, 0.35), rng.uniform(-0.35, 0.35), rng.uniform(-0.1, 0.25)))).normalized()
            pos = pos + direc * (comp / segs)
            verts.append(tuple(pos))
            raios.append(max(raio * (1.0 - (s + 1) / (segs + 1.5)), 0.004))
            arestas.append((idx, len(verts) - 1))
            idx = len(verts) - 1
            if nivel < 3 and rng.random() < 0.75:
                nd = (direc + Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(0.0, 0.7)))).normalized()
                ramo(idx, nd, comp * rng.uniform(0.45, 0.7), raios[-1] * 0.7, nivel + 1)

    for k in range(rng.randint(5, 8)):
        a = rng.uniform(0, 2 * math.pi)
        d = Vector((math.cos(a) * 0.6, math.sin(a) * 0.6, 1.0)).normalized()
        ramo(0, d, rng.uniform(0.45, 0.8), 0.03, 1)
    return arvore_skin(nome, col, mat, verts, arestas, raios, subsurf=0)


def criar_erva(nome, col, mat, rng):
    bm = bmesh.new()
    for k in range(rng.randint(35, 60)):
        a = rng.uniform(0, 2 * math.pi)
        incl = rng.uniform(0.1, 0.9)
        alt = rng.uniform(0.25, 0.6)
        larg = 0.012
        base = Vector((math.cos(a) * 0.04, math.sin(a) * 0.04, 0.0))
        topo = base + Vector((math.cos(a) * incl * alt, math.sin(a) * incl * alt, alt))
        meio = base.lerp(topo, 0.5) + Vector((0, 0, 0.05))
        lat = Vector((-math.sin(a), math.cos(a), 0.0)) * larg
        v = [bm.verts.new(base - lat), bm.verts.new(base + lat), bm.verts.new(meio + lat * 0.6),
             bm.verts.new(meio - lat * 0.6), bm.verts.new(topo)]
        bm.faces.new((v[0], v[1], v[2], v[3]))
        bm.faces.new((v[3], v[2], v[4]))
    return objeto_malha(nome, bm, col, mat)


def criar_cacto(nome, col, mat, rng):
    h = rng.uniform(4.5, 8.5)
    verts = [(0.0, 0.0, -0.3)]
    arestas = []
    raios = [0.33]
    n = 10
    tronco = [0]
    for i in range(1, n + 1):
        z = h * i / n
        verts.append((0.0, 0.0, z))
        raios.append(0.33 if i < n - 1 else (0.26 if i == n - 1 else 0.14))
        arestas.append((len(verts) - 2, len(verts) - 1))
        tronco.append(len(verts) - 1)
    for k in range(rng.randint(0, 3)):
        ib = rng.randint(int(n * 0.35), int(n * 0.6))
        a = rng.uniform(0, 2 * math.pi) if k == 0 else (a + math.pi + rng.uniform(-0.8, 0.8))
        dx, dy = math.cos(a), math.sin(a)
        base = Vector(verts[tronco[ib]])
        pts = [base + Vector((dx * 0.55, dy * 0.55, 0.15)),
               base + Vector((dx * 0.85, dy * 0.85, 0.6))]
        topo_b = rng.uniform(1.4, 2.8)
        for s in range(1, 5):
            pts.append(base + Vector((dx * 0.9, dy * 0.9, 0.6 + topo_b * s / 4)))
        prev = tronco[ib]
        for j, p in enumerate(pts):
            verts.append(tuple(p))
            raios.append(0.22 if j < len(pts) - 1 else 0.11)
            arestas.append((prev, len(verts) - 1))
            prev = len(verts) - 1
    return arvore_skin(nome, col, mat, verts, arestas, raios, subsurf=2)


# ---- Geometry Nodes: instanciar coleção em pontos ---------------------------


def grupo_instancias():
    g = bpy.data.node_groups.new("Espalhar_Instancias", "GeometryNodeTree")
    g.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    g.interface.new_socket("Colecao", in_out='INPUT', socket_type='NodeSocketCollection')
    g.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    try:
        g.is_modifier = True
    except Exception:
        pass
    n, l = g.nodes, g.links
    gi = n.new("NodeGroupInput")
    go = n.new("NodeGroupOutput")
    ci = n.new("GeometryNodeCollectionInfo")
    ci.transform_space = 'ORIGINAL'
    ci.inputs["Separate Children"].default_value = True
    ci.inputs["Reset Children"].default_value = True
    l.new(gi.outputs[1], ci.inputs["Collection"])
    iop = n.new("GeometryNodeInstanceOnPoints")
    iop.inputs["Pick Instance"].default_value = True
    rot = n.new("GeometryNodeInputNamedAttribute")
    rot.data_type = 'FLOAT_VECTOR'
    rot.inputs["Name"].default_value = "rot"
    esc = n.new("GeometryNodeInputNamedAttribute")
    esc.data_type = 'FLOAT_VECTOR'
    esc.inputs["Name"].default_value = "escala"
    var = n.new("GeometryNodeInputNamedAttribute")
    var.data_type = 'INT'
    var.inputs["Name"].default_value = "variante"
    e2r = None
    try:
        e2r = n.new("FunctionNodeEulerToRotation")
    except RuntimeError:
        pass
    l.new(gi.outputs[0], iop.inputs["Points"])
    l.new(ci.outputs[0], iop.inputs["Instance"])
    l.new(var.outputs["Attribute"], iop.inputs["Instance Index"])
    if e2r:
        l.new(rot.outputs["Attribute"], e2r.inputs[0])
        l.new(e2r.outputs[0], iop.inputs["Rotation"])
    else:
        l.new(rot.outputs["Attribute"], iop.inputs["Rotation"])
    l.new(esc.outputs["Attribute"], iop.inputs["Scale"])
    l.new(iop.outputs[0], go.inputs[0])
    arrumar(g)
    return g


def nuvem_pontos(nome, col, pts, rots, escs, vars_, grupo, colecao_inst):
    me = bpy.data.meshes.new(nome)
    me.vertices.add(len(pts))
    me.vertices.foreach_set("co", np.asarray(pts, dtype=np.float32).ravel())
    a = me.attributes.new("rot", 'FLOAT_VECTOR', 'POINT')
    a.data.foreach_set("vector", np.asarray(rots, dtype=np.float32).ravel())
    a = me.attributes.new("escala", 'FLOAT_VECTOR', 'POINT')
    a.data.foreach_set("vector", np.asarray(escs, dtype=np.float32).ravel())
    a = me.attributes.new("variante", 'INT', 'POINT')
    a.data.foreach_set("value", np.asarray(vars_, dtype=np.int32))
    me.update()
    ob = bpy.data.objects.new(nome, me)
    col.objects.link(ob)
    md = ob.modifiers.new("Espalhar", 'NODES')
    md.node_group = grupo
    # socket da coleção (identificador do 2º input)
    ident = [it.identifier for it in grupo.interface.items_tree
             if getattr(it, "in_out", None) == 'INPUT'][1]
    md[ident] = colecao_inst
    return ob


def amostrar_pontos(rng, n, aceitar, margem=4.0, tentativas=40):
    """Amostragem por rejeição sobre o terreno. aceitar(H, rocha, duna, playa, decl) -> prob."""
    out = []
    lote = n * 6
    for _ in range(tentativas):
        X = rng.uniform(-MEIO + margem, MEIO - margem, lote)
        Y = rng.uniform(-MEIO + margem, MEIO - margem, lote)
        H, ro, du, pl = altura(X, Y)
        e = 0.6
        hx = altura(X + e, Y)[0]
        hy = altura(X, Y + e)[0]
        decl = np.sqrt(((hx - H) / e) ** 2 + ((hy - H) / e) ** 2)
        p = aceitar(X, Y, H, ro, du, pl, decl)
        ok = rng.uniform(0, 1, lote) < p
        for x, y, h, dc in zip(X[ok], Y[ok], H[ok], decl[ok]):
            out.append((x, y, h, dc))
            if len(out) >= n:
                return out
    return out


def criar_scatter(col_cena, col_assets):
    print("[deserto] a criar pedras, arbustos e cactos ...")
    rng = random.Random(SEMENTE)
    nrng = np.random.default_rng(SEMENTE)
    m_rocha = criar_mat_rocha()
    m_arb = criar_mat_madeira_seca()
    m_erva = criar_mat_erva()
    m_cacto = criar_mat_cacto()
    c_ped = colecao("Assets_Pedras", col_assets)
    c_arb = colecao("Assets_Arbustos", col_assets)
    c_erv = colecao("Assets_Ervas", col_assets)
    c_cac = colecao("Assets_Cactos", col_assets)
    for i in range(7):
        ob = criar_pedra(f"Pedra_{i}", c_ped, m_rocha, rng, 'pedra')
        ob.location.x = i * 4.0
    for i in range(5):
        ob = criar_arbusto(f"Arbusto_{i}", c_arb, m_arb, rng)
        ob.location = (i * 3.0, 6.0, 0.0)
    for i in range(4):
        ob = criar_erva(f"Erva_{i}", c_erv, m_erva, rng)
        ob.location = (i * 2.0, 12.0, 0.0)
    for i in range(4):
        ob = criar_cacto(f"Cacto_{i}", c_cac, m_cacto, rng)
        ob.location = (i * 4.0, 18.0, 0.0)

    g = grupo_instancias()

    def empacotar(pts, esc_min, esc_max, nvar, afund, achatar=1.0, inclinar=0.08):
        P, R, E, V = [], [], [], []
        for (x, y, h, dc) in pts:
            s = nrng.uniform(esc_min, esc_max)
            P.append((x, y, h - afund * s))
            R.append((nrng.normal(0, inclinar), nrng.normal(0, inclinar), nrng.uniform(0, 2 * math.pi)))
            E.append((s, s * nrng.uniform(0.85, 1.15), s * achatar * nrng.uniform(0.85, 1.15)))
            V.append(int(nrng.integers(0, nvar)))
        return P, R, E, V

    # pedras pequenas: planícies e fundos dos canyons (não nas dunas)
    pts = amostrar_pontos(nrng, N_PEDRAS, lambda X, Y, H, ro, du, pl, dc:
                          (0.25 + 0.75 * ro) * (1 - du) * (1 - pl) * (dc < 0.6))
    nuvem_pontos("Scatter_Pedras", col_cena, *empacotar(pts, 0.15, 0.7, 7, 0.25), g, c_ped)
    # pedregulhos: no sopé das escarpas
    pts = amostrar_pontos(nrng, N_PEDREGULHOS, lambda X, Y, H, ro, du, pl, dc:
                          ro * (dc > 0.15) * (dc < 0.9) * (1 - pl))
    nuvem_pontos("Scatter_Pedregulhos", col_cena, *empacotar(pts, 1.2, 3.8, 7, 0.3, inclinar=0.2), g, c_ped)
    # arbustos secos
    pts = amostrar_pontos(nrng, N_ARBUSTOS, lambda X, Y, H, ro, du, pl, dc:
                          (1 - 0.8 * du) * (1 - pl) * (dc < 0.35) * (0.6 + 0.4 * (fbm(X / 40, Y / 40, 2, 90) > 0)))
    nuvem_pontos("Scatter_Arbustos", col_cena, *empacotar(pts, 0.7, 1.6, 5, 0.03, inclinar=0.1), g, c_arb)
    # tufos de erva seca (incluindo depressões entre dunas)
    pts = amostrar_pontos(nrng, N_ERVAS, lambda X, Y, H, ro, du, pl, dc:
                          (1 - pl) * (dc < 0.3) * (1 - 0.5 * ro))
    nuvem_pontos("Scatter_Ervas", col_cena, *empacotar(pts, 0.7, 1.5, 4, 0.02, inclinar=0.05), g, c_erv)
    # cactos saguaro nas planícies/bajada
    pts = amostrar_pontos(nrng, N_CACTOS, lambda X, Y, H, ro, du, pl, dc:
                          (1 - du) * (1 - pl) * (1 - ro) * (dc < 0.2))
    nuvem_pontos("Scatter_Cactos", col_cena, *empacotar(pts, 0.75, 1.25, 4, 0.1, inclinar=0.04), g, c_cac)


# =============================================================================
# Animação: sol, lua, céu, poeira, exposição
# =============================================================================


def _interp_mono(ts, vs, t):
    """Interpolação cúbica monótona (Fritsch-Carlson), escalar."""
    ts = np.asarray(ts, float)
    vs = np.asarray(vs, float)
    n = len(ts)
    dl = np.diff(vs) / np.diff(ts)
    m = np.zeros(n)
    m[0], m[-1] = dl[0], dl[-1]
    for k in range(1, n - 1):
        m[k] = 0.0 if dl[k - 1] * dl[k] <= 0 else 2.0 / (1.0 / dl[k - 1] + 1.0 / dl[k])
    k = int(np.clip(np.searchsorted(ts, t) - 1, 0, n - 2))
    h = ts[k + 1] - ts[k]
    s = (t - ts[k]) / h
    h00 = 2 * s ** 3 - 3 * s ** 2 + 1
    h10 = s ** 3 - 2 * s ** 2 + s
    h01 = -2 * s ** 3 + 3 * s ** 2
    h11 = s ** 3 - s ** 2
    return h00 * vs[k] + h10 * h * m[k] + h01 * vs[k + 1] + h11 * h * m[k + 1]


def elevacao_sol(t):
    return _interp_mono([p[0] for p in SOL_ELEVACAO], [p[1] for p in SOL_ELEVACAO], t)


def cor_sol(el):
    """Cor aproximada da luz solar direta em função da elevação."""
    tab = [(-2.0, (1.0, 0.22, 0.05)), (0.5, (1.0, 0.32, 0.08)), (3.0, (1.0, 0.50, 0.20)),
           (7.0, (1.0, 0.66, 0.36)), (14.0, (1.0, 0.80, 0.58)), (25.0, (1.0, 0.90, 0.76)),
           (40.0, (1.0, 0.95, 0.86))]
    if el <= tab[0][0]:
        return tab[0][1]
    for (e0, c0), (e1, c1) in zip(tab, tab[1:]):
        if el <= e1:
            f = (el - e0) / (e1 - e0)
            return tuple(lerp(a, b, f) for a, b in zip(c0, c1))
    return tab[-1][1]


def tabela(x, pontos):
    """Interpolação linear numa tabela [(x, valor)] com x decrescente; valor escalar ou tuplo."""
    if x >= pontos[0][0]:
        return pontos[0][1]
    for (x0, v0), (x1, v1) in zip(pontos, pontos[1:]):
        if x >= x1:
            f = (x0 - x) / (x0 - x1)
            if isinstance(v0, tuple):
                return tuple(lerp(a, b, f) for a, b in zip(v0, v1))
            return lerp(v0, v1, f)
    return pontos[-1][1]


def estado(t):
    """Todos os parâmetros da cena para o tempo normalizado t."""
    el = elevacao_sol(t)
    az = lerp(SOL_AZIMUTE[0], SOL_AZIMUTE[1], t)
    s = {}
    s["el"], s["az"] = el, az
    s["sol_dir"] = dir_az_el(az, el)
    # força do sol (W/m2 da lâmpada): atenuação por massa de ar
    massa = 1.0 / max(math.sin(math.radians(max(el, 0.0))) + 0.15 * (max(el, 0.0) + 3.885) ** -1.253, 1e-3)
    s["sol_forca"] = 7.0 * sstep(-1.2, 1.5, el) * math.exp(-0.085 * (massa - 1.0) ** 0.9)
    s["sol_cor"] = cor_sol(el)
    # céu físico: a partir de ~-4 graus o modelo apaga-se; mantém-no suave
    s["ceu_forca"] = ESCALA_CEU
    # brilho crepuscular (adicional ao céu físico) - pico ~2 graus abaixo do horizonte
    s["brilho"] = tabela(el, [(12.0, 0.0), (6.0, 0.12), (2.0, 0.3), (-1.0, 0.36), (-3.5, 0.3),
                              (-6.0, 0.16), (-9.0, 0.06), (-13.0, 0.012), (-18.0, 0.0)])
    # cor do brilho: dourado -> laranja -> vermelho -> magenta profundo
    c = tabela(el, [(8.0, (1.0, 0.62, 0.22)), (2.0, (1.0, 0.48, 0.12)), (-2.0, (1.0, 0.36, 0.07)),
                    (-5.0, (0.92, 0.24, 0.07)), (-8.0, (0.62, 0.14, 0.12)), (-12.0, (0.30, 0.08, 0.18))])
    s["cor_brilho"] = c
    s["aureola"] = tabela(el, [(14.0, 0.0), (6.0, 0.25), (1.0, 0.5), (-2.0, 0.35), (-5.0, 0.1), (-8.0, 0.0)])
    s["venus"] = 0.35 * sstep(3.0, -1.0, el) * sstep(-11.0, -5.0, el)
    s["noite"] = sstep(-3.0, -14.0, el)
    s["estrelas"] = sstep(-6.0, -16.0, el)
    s["lua"] = 0.25 + 0.75 * sstep(4.0, -8.0, el)
    s["lua_luz"] = 0.14 * sstep(-2.0, -12.0, el)
    # exposição: compressão da enorme gama dinâmica dia/noite
    ex = tabela(el, [(30.0, -1.2), (20.0, -0.9), (12.0, -0.6), (6.0, -0.1), (2.0, 0.4), (-1.0, 1.2),
                     (-3.0, 1.9), (-6.0, 2.5), (-10.0, 2.9), (-20.0, 2.9)])
    s["exposicao"] = ex
    # poeira / volume
    s["poeira"] = 0.0001 + 0.00032 * math.exp(-((el - 1.0) / 7.0) ** 2) - 0.0001 * sstep(-4.0, -14.0, el)
    s["calor"] = sstep(6.0, 22.0, el)
    # lua
    maz = lerp(LUA_AZ_EL_INI[0], LUA_AZ_EL_FIM[0], t)
    mel = lerp(LUA_AZ_EL_INI[1], LUA_AZ_EL_FIM[1], t)
    m = dir_az_el(maz, mel)
    r = m.cross(Vector((0, 0, 1))).normalized()
    u = r.cross(m).normalized()
    S = s["sol_dir"]
    s["lua_m"], s["lua_r"], s["lua_u"] = m, r, u
    # normal visível: n = u*r + v*up - w*m ; iluminação = n . S
    s["lua_fase"] = Vector((r.dot(S), u.dot(S), -m.dot(S)))
    return s


def rotacao_ceu(az):
    """Azimute -> sun_rotation do Sky Texture.
    Blender 5.x: 0 = Norte (+Y), sentido horário (verificado com câmara panorâmica).
    Blender 4.x (Nishita): 0 = Norte, sentido anti-horário."""
    if bpy.app.version >= (5, 0, 0):
        return math.radians(az) % (2 * math.pi)
    return (-math.radians(az)) % (2 * math.pi)


def kf(alvo, caminho, frame, idx=-1):
    alvo.keyframe_insert(caminho, frame=frame, index=idx)


def animar(sol, lua, grupo_ceu, vol_mat, calor_mat):
    sc = bpy.context.scene
    nodes = grupo_ceu.nodes
    ceus = [nodes["CeuFisico"], nodes["CeuDiscoSolar"]]
    frames = list(range(FRAME_INI, FRAME_FIM + 1, PASSO_KEYS))
    if frames[-1] != FRAME_FIM:
        frames.append(FRAME_FIM)
    euler_ant = None
    for fr in frames:
        t = (fr - FRAME_INI) / (FRAME_FIM - FRAME_INI)
        s = estado(t)
        # sol
        q = s["sol_dir"].to_track_quat('Z', 'Y')
        e = q.to_euler('XYZ', euler_ant) if euler_ant else q.to_euler('XYZ')
        euler_ant = e
        sol.rotation_euler = e
        kf(sol, "rotation_euler", fr)
        sol.data.energy = s["sol_forca"]
        kf(sol.data, "energy", fr)
        sol.data.color = s["sol_cor"]
        kf(sol.data, "color", fr)
        # lua (luz)
        lua.rotation_euler = s["lua_m"].to_track_quat('Z', 'Y').to_euler('XYZ')
        kf(lua, "rotation_euler", fr)
        lua.data.energy = s["lua_luz"]
        kf(lua.data, "energy", fr)
        # céu
        for ceu in ceus:
            ceu.sun_elevation = math.radians(s["el"])
            ceu.sun_rotation = rotacao_ceu(s["az"])
            kf(ceu, "sun_elevation", fr)
            kf(ceu, "sun_rotation", fr)
        sd = s["sol_dir"]
        sh = Vector((sd.x, sd.y, 0.0)).normalized()
        for nome, vec in (("SolDir", sd), ("SolDirH", sh), ("LuaR", s["lua_r"]), ("LuaU", s["lua_u"]),
                          ("LuaM", s["lua_m"]), ("LuaFase", s["lua_fase"])):
            nd = nodes[nome]
            for k in range(3):
                nd.inputs[k].default_value = vec[k]
                kf(nd.inputs[k], "default_value", fr)
        for nome, chave in (("BrilhoCrepusculo", "brilho"), ("CinturaoVenus", "venus"), ("Noite", "noite"), ("Aureola", "aureola"),
                            ("Estrelas", "estrelas"), ("ForcaCeu", "ceu_forca"), ("LuaIntensidade", "lua")):
            nd = nodes[nome]
            nd.outputs[0].default_value = s[chave]
            kf(nd.outputs[0], "default_value", fr)
        nd = nodes["CorCrepusculo"]
        nd.outputs[0].default_value = (*s["cor_brilho"], 1.0)
        kf(nd.outputs[0], "default_value", fr)
        # exposição
        sc.view_settings.exposure = s["exposicao"]
        kf(sc.view_settings, "exposure", fr)
        # poeira
        if vol_mat:
            nd = vol_mat.node_tree.nodes["Densidade"]
            nd.outputs[0].default_value = s["poeira"]
            kf(nd.outputs[0], "default_value", fr)
            nd = vol_mat.node_tree.nodes["CorPoeira"]
            nd.outputs[0].default_value = (*[lerp(0.55, c, 0.35) for c in s["sol_cor"]], 1.0)
            kf(nd.outputs[0], "default_value", fr)
        if calor_mat:
            nd = calor_mat.node_tree.nodes["Calor"]
            nd.outputs[0].default_value = s["calor"]
            kf(nd.outputs[0], "default_value", fr)

    # tempo linear (cintilação das estrelas, tremor do ar quente)
    for alvo in [nodes["Tempo"]] + ([calor_mat.node_tree.nodes["TempoCalor"]] if calor_mat else []):
        for fr, v in ((FRAME_INI, 0.0), (FRAME_FIM, 1.0)):
            alvo.outputs[0].default_value = v
            kf(alvo.outputs[0], "default_value", fr)
        linearizar(alvo.id_data, 'nodes["%s"]' % alvo.name)


def _fcurves(idb):
    ad = idb.animation_data
    if not ad or not ad.action:
        return []
    act = ad.action
    if hasattr(act, "fcurves") and not getattr(act, "is_action_layered", False):
        return list(act.fcurves)
    res = []
    for layer in act.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                res.extend(bag.fcurves)
    return res


def linearizar(idb, prefixo=""):
    for fc in _fcurves(idb):
        if fc.data_path.startswith(prefixo):
            for kp in fc.keyframe_points:
                kp.interpolation = 'LINEAR'


def criar_luzes(col):
    ld = bpy.data.lights.new("Sol", 'SUN')
    ld.angle = math.radians(0.53)
    try:
        ld.cycles.max_bounces = 1024
    except Exception:
        pass
    sol = bpy.data.objects.new("Sol", ld)
    col.objects.link(sol)
    ld2 = bpy.data.lights.new("Luar", 'SUN')
    ld2.angle = math.radians(0.52)
    ld2.color = (0.62, 0.72, 1.0)
    lua = bpy.data.objects.new("Luar", ld2)
    col.objects.link(lua)
    return sol, lua


# =============================================================================
# Volume de poeira e distorção de calor
# =============================================================================


def criar_volume(col):
    me = bpy.data.meshes.new("Poeira_Volume")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("Poeira_Volume", me)
    ob.scale = (TAMANHO + 40.0, TAMANHO + 40.0, 160.0)
    ob.location = (0.0, 0.0, 70.0)
    col.objects.link(ob)
    m, b = mat_novo("Poeira_Atmosferica")
    geo = b.node("ShaderNodeNewGeometry")
    pz = b.sep(geo.outputs["Position"])[2]
    dens = b.valor("Densidade", 0.001)
    # concentrada junto ao solo, com nuvens de poeira suaves
    queda = b.math('EXPONENT', b.math('DIVIDE', pz, -22.0))
    n = b.noise(geo.outputs["Position"], 0.012, 3.0, 0.5)
    var = b.maprange(n.outputs[0], 0.3, 0.7, 0.5, 1.5)
    d = b.math('MULTIPLY', b.math('MULTIPLY', b.math('ADD', b.math('MULTIPLY', queda, 1.0), 0.18), var), dens.outputs[0])
    cor = b.rgb("CorPoeira", (0.9, 0.7, 0.5))
    pv = b.node("ShaderNodeVolumePrincipled")
    b.link(cor.outputs[0], pv.inputs["Color"])
    b.link(d, pv.inputs["Density"])
    pv.inputs["Anisotropy"].default_value = 0.45
    pv.inputs["Absorption Color"].default_value = (0.85, 0.7, 0.55, 1.0)
    out = b.node("ShaderNodeOutputMaterial")
    b.link(pv.outputs[0], out.inputs["Volume"])
    arrumar(m.node_tree)
    me.materials.append(m)
    ob.visible_shadow = True
    return m


def criar_calor(col, cam):
    """Plano refrativo à frente da câmara: tremor do ar quente perto do horizonte."""
    me = bpy.data.meshes.new("Ar_Quente")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("Ar_Quente", me)
    col.objects.link(ob)
    ob.parent = cam
    d = 0.5
    ob.location = (0.0, 0.0, -d)
    larg = 2.0 * d * math.tan(cam.data.angle / 2.0) * 1.1
    ob.scale = (larg * 2.0, larg * 2.0, 1.0)
    for attr in ("visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter",
                 "visible_shadow"):
        setattr(ob, attr, False)
    m, b = mat_novo("Ar_Quente")
    tc = b.node("ShaderNodeTexCoord")
    gen = tc.outputs["Generated"]
    gy = b.sep(gen)[1]
    calor = b.valor("Calor", 0.0)
    tempo = b.valor("TempoCalor", 0.0)
    # máscara: faixa do horizonte (parte central/baixa da imagem)
    faixa = b.math('MULTIPLY', b.maprange(gy, 0.25, 0.42), b.maprange(gy, 0.62, 0.48))
    w = b.math('MULTIPLY', tempo.outputs[0], 55.0)
    vec = b.vmath('MULTIPLY', gen, (1.0, 5.0, 1.0))
    n = b.noise(vec, 22.0, 2.0, 0.5, dims='4D', w=w)
    bump = b.node("ShaderNodeBump")
    b.link(b.math('MULTIPLY', n.outputs[0], b.math('MULTIPLY', faixa, calor.outputs[0])), bump.inputs["Height"])
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.004
    refr = b.node("ShaderNodeBsdfRefraction")
    refr.inputs["IOR"].default_value = 1.003
    refr.inputs["Roughness"].default_value = 0.0
    refr.inputs["Color"].default_value = (1, 1, 1, 1)
    b.link(bump.outputs[0], refr.inputs["Normal"])
    tr = b.node("ShaderNodeBsdfTransparent")
    ms = b.node("ShaderNodeMixShader")
    b.link(b.math('MULTIPLY', faixa, calor.outputs[0]), ms.inputs[0])
    b.link(tr.outputs[0], ms.inputs[1])
    b.link(refr.outputs[0], ms.inputs[2])
    out = b.node("ShaderNodeOutputMaterial")
    b.link(ms.outputs[0], out.inputs[0])
    arrumar(m.node_tree)
    me.materials.append(m)
    return m


# =============================================================================
# Câmara (travelling lento das dunas para oeste)
# =============================================================================


def criar_camara(col):
    cd = bpy.data.cameras.new("Camara")
    cd.lens = 24.0
    cd.sensor_width = 36.0
    cd.clip_start = 0.1
    cd.clip_end = 30000.0
    cam = bpy.data.objects.new("Camara", cd)
    col.objects.link(cam)
    bpy.context.scene.camera = cam
    alvo = bpy.data.objects.new("Camara_Alvo", None)
    alvo.empty_display_size = 5.0
    col.objects.link(alvo)
    tr = cam.constraints.new('TRACK_TO')
    tr.target = alvo
    tr.track_axis = 'TRACK_NEGATIVE_Z'
    tr.up_axis = 'UP_Y'

    # percurso: começa entre as dunas e avança para oés-sudoeste
    p0 = np.array([CAM_INI[0], CAM_INI[1]])
    p1 = np.array([CAM_FIM[0], CAM_FIM[1]])
    n = 13
    ts = np.linspace(0.0, 1.0, n)
    # velocidade suave (ease in/out)
    tt = ts * ts * (3 - 2 * ts) * 0.3 + ts * 0.7
    xy = p0[None, :] + (p1 - p0)[None, :] * tt[:, None]
    xy[:, 0] += 8.0 * np.sin(tt * math.pi)           # ligeira curva
    # altura: segue o terreno com folga (máximo numa vizinhança)
    alt = []
    for (x, y) in xy:
        ang = np.linspace(0, 2 * math.pi, 16, endpoint=False)
        rx = np.concatenate([[x], x + 8 * np.cos(ang), x + 16 * np.cos(ang)])
        ry = np.concatenate([[y], y + 8 * np.sin(ang), y + 16 * np.sin(ang)])
        alt.append(float(np.max(altura(rx, ry)[0])) + 3.5)
    alt = np.convolve(np.pad(alt, 1, mode='edge'), [0.25, 0.5, 0.25], mode='valid')
    for k in range(n):
        fr = int(round(FRAME_INI + ts[k] * (FRAME_FIM - FRAME_INI)))
        cam.location = (xy[k, 0], xy[k, 1], alt[k])
        kf(cam, "location", fr)

    # direção do olhar: poente (ONO) -> desvia para sudoeste à noite (lua e Via Láctea)
    olhar = CAM_OLHAR
    for t, az, el in olhar:
        fr = int(round(FRAME_INI + t * (FRAME_FIM - FRAME_INI)))
        k = min(int(t * (n - 1) + 0.5), n - 1)
        base = Vector((xy[k, 0], xy[k, 1], alt[k]))
        alvo.location = base + dir_az_el(az, el) * 400.0
        kf(alvo, "location", fr)
    return cam


# =============================================================================
# Render, compositor
# =============================================================================


def configurar_render():
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.render.fps = FPS
    sc.frame_start = FRAME_INI
    sc.frame_end = FRAME_FIM
    sc.frame_current = FRAME_INI
    sc.render.resolution_x = RES_X
    sc.render.resolution_y = RES_Y
    sc.render.resolution_percentage = 100
    cy = sc.cycles
    cy.samples = AMOSTRAS
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.02
    cy.use_denoising = True
    try:
        cy.denoiser = 'OPENIMAGEDENOISE'
    except Exception:
        pass
    cy.max_bounces = 8
    cy.diffuse_bounces = 3
    cy.glossy_bounces = 2
    cy.transmission_bounces = 4
    cy.volume_bounces = 1
    cy.transparent_max_bounces = 8
    cy.sample_clamp_indirect = 8.0
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    try:
        cy.volume_step_rate = 4.0
        cy.volume_max_steps = 256
    except Exception:
        pass
    try:
        sc.render.use_persistent_data = True
    except Exception:
        pass
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.refresh_devices() if hasattr(prefs, "refresh_devices") else prefs.get_devices()
        for tipo in ('OPTIX', 'CUDA', 'HIP', 'METAL', 'ONEAPI'):
            try:
                prefs.compute_device_type = tipo
                if any(d.type == tipo for d in prefs.devices):
                    for d in prefs.devices:
                        d.use = True
                    cy.device = 'GPU'
                    break
            except TypeError:
                continue
    except Exception:
        pass
    vs = sc.view_settings
    try:
        vs.view_transform = 'AgX'
        vs.look = 'AgX - Punchy'
    except TypeError:
        try:
            vs.view_transform = 'Filmic'
            vs.look = 'Medium High Contrast'
        except TypeError:
            pass
    sc.render.image_settings.file_format = 'PNG'
    sc.render.filepath = "//render/deserto_"


def configurar_compositor():
    sc = bpy.context.scene
    try:
        if hasattr(sc, "compositing_node_group"):
            tree = bpy.data.node_groups.new("Compositor_Deserto", "CompositorNodeTree")
            sc.compositing_node_group = tree
            tree.interface.new_socket("Image", in_out='OUTPUT', socket_type='NodeSocketColor')
            out = tree.nodes.new("NodeGroupOutput")
            out_in = out.inputs[0]
        else:
            sc.use_nodes = True
            tree = sc.node_tree
            tree.nodes.clear()
            out = tree.nodes.new("CompositorNodeComposite")
            out_in = out.inputs[0]
        rl = tree.nodes.new("CompositorNodeRLayers")
        gl = tree.nodes.new("CompositorNodeGlare")
        valores = {"Type": 'Bloom', "Quality": 'High', "Threshold": 1.2, "Strength": 0.35,
                   "Size": 0.8, "Saturation": 1.0}
        for k, v in valores.items():
            if k in gl.inputs:
                try:
                    gl.inputs[k].default_value = v
                except Exception:
                    pass
        if "Type" not in gl.inputs:
            gl.glare_type = 'BLOOM' if 'BLOOM' in [e.identifier for e in gl.bl_rna.properties['glare_type'].enum_items] else 'FOG_GLOW'
            gl.threshold = 1.2
            gl.mix = -0.7
        tree.links.new(rl.outputs["Image"], gl.inputs["Image"])
        tree.links.new(gl.outputs["Image"], out_in)
        rl.location = (-400, 0)
        out.location = (300, 0)
    except Exception as e:
        print("[deserto] compositor não configurado:", e)


# =============================================================================
# Principal
# =============================================================================


def main():
    t0 = __import__("time").time()
    limpar_cena()
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'

    c_terreno = colecao("Terreno")
    c_veg = colecao("Pedras_e_Vegetacao")
    c_luz = colecao("Luz_Ceu_Camara")
    c_assets = colecao("Assets (instanciados)")

    configurar_render()
    grupo_ceu = criar_grupo_ceu()
    criar_mundo(grupo_ceu)

    ter, hor = criar_terreno(c_terreno)
    mt = criar_mat_terreno(grupo_ceu)
    ter.data.materials.append(mt)
    hor.data.materials.append(mt)

    criar_scatter(c_veg, c_assets)
    # esconde os assets originais (continuam a ser instanciados)
    vl = bpy.context.view_layer.layer_collection
    for lc in vl.children:
        if lc.collection == c_assets:
            lc.exclude = True

    sol, lua = criar_luzes(c_luz)
    cam = criar_camara(c_luz)
    vol_m = criar_volume(c_luz) if USAR_VOLUME else None
    calor_m = criar_calor(c_luz, cam) if USAR_CALOR else None
    animar(sol, lua, grupo_ceu, vol_m, calor_m)
    if USAR_COMPOSITOR:
        configurar_compositor()
    sc.frame_set(FRAME_INI)
    print("[deserto] cena criada em %.1f s" % (__import__("time").time() - t0))


if __name__ == "__main__":
    main()
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--save" in argv:
        caminho = argv[argv.index("--save") + 1]
        bpy.ops.wm.save_as_mainfile(filepath=bpy.path.abspath(caminho))
        print("[deserto] guardado em", caminho)
