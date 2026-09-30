"""
Música provisória da intro "A Travessia" (12 s), sintetizada em código — 100% original.

Valsa em lá menor de caixinha de música (à Elfman), com pizzicato, coro sintético e efeitos,
sincronizada ao frame com os planos de travessia.py:
  0–2,5 s   gabinete: zumbido de CRT, o ecrã a ligar, três notas de caixinha de música a acordar
  2,5 s     mergulho no ecrã: whoosh e um "boot" de consola (inventado)
  2,5–6,5 s os quatro mundos: a valsa arranca, um compasso por mundo; passos no tempo da caminhada;
            um toque por corte (sino da escola, corvo, "ah" de coro)
  6,5–8,5 s Portas do Inferno: graves, coro sombrio, fogo
  8,9–10,3  o inferno gela: a caixinha de música abranda e desafina, gelo a estalar
  10,3–12 s meio segundo de silêncio e uma nota de celesta com reverberação longa no logo

É uma maqueta: serve para acertar o ritmo; a faixa final deve ser composta ou licenciada.
Estilo alternativo "trailer de ação" (--estilo trailer): tiquetaque e drone, BRAAAM de metais graves
e impacto no mergulho, ostinato de cordas e taikos pelos mundos, um impacto em cada corte, um riser
e um rufo de tarola a acelerar no Inferno, a maior pancada quando gela, silêncio total e a última
pancada no logo.

Uso:
    python musica_provisoria.py --out musica_provisoria.wav
    python musica_provisoria.py --estilo trailer --out musica_trailer.wav --video animatic_travessia.mp4 --com-som animatic_trailer.mp4
    python musica_provisoria.py --out musica_provisoria.wav --video animatic_travessia.mp4 --com-som animatic_com_som.mp4
"""

import argparse
import shutil
import subprocess
import wave

import numpy as np

SR = 44100
DUR = 12.0
FPS = 24
N = int(SR * DUR)
rng = np.random.default_rng(1993)

# momentos (em frames globais da intro — iguais aos de travessia.py)
ECRA_LIGA = 10
MERGULHO = 61
CORTES = [85, 109, 133, 157]
CHEGA = 204
GELO = (214, 248)
LOGO_NOTA = 262


def t_(frame):
    return (frame - 1) / FPS


def nota(nome):
    """'A4' → Hz (com sustenidos: 'G#4')."""
    ordem = {"C": -9, "C#": -8, "D": -7, "D#": -6, "E": -5, "F": -4, "F#": -3, "G": -2, "G#": -1, "A": 0, "A#": 1, "B": 2}
    return 440.0 * 2 ** ((ordem[nome[:-1]] + 12 * (int(nome[-1]) - 4)) / 12)


def pista():
    return np.zeros(N, np.float32)


def por(dst, sinal, t0, ganho=1.0):
    i = int(t0 * SR)
    if i >= N:
        return
    j = min(N, i + len(sinal))
    dst[i:j] += sinal[: j - i] * ganho


def env(n, ataque=0.002, decai=1.0):
    t = np.arange(n) / SR
    a = np.minimum(1.0, t / max(ataque, 1e-4))
    return a * np.exp(-t / decai)


def caixinha(freq, dur=2.5, desafina=0.0, bend=0.0):
    """Lamela de caixinha de música: parciais inarmónicos, ataque seco, decaimento longo."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    f = freq * (1 + desafina) * (1 + bend * t / dur)
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = (np.sin(ph) + 0.35 * np.sin(ph * 2.76) * np.exp(-t / 0.25) + 0.18 * np.sin(ph * 5.4) * np.exp(-t / 0.08)
         + 0.06 * np.sin(ph * 8.93) * np.exp(-t / 0.03))
    return (s * env(n, 0.001, 0.9)).astype(np.float32)


def pizzicato(freq, dur=0.7):
    """Corda beliscada (Karplus-Strong)."""
    n = int(SR * dur)
    p = max(2, int(SR / freq))
    buf = rng.uniform(-1, 1, p).astype(np.float32)
    out = np.zeros(n, np.float32)
    for i in range(n):
        v = buf[i % p]
        out[i] = v
        buf[i % p] = 0.5 * (v + buf[(i + 1) % p]) * 0.994
    return out * env(n, 0.001, 0.35)


def ruido(n, cor="branco"):
    x = rng.normal(0, 1, n).astype(np.float32)
    if cor == "castanho":
        x = np.cumsum(x)
        x -= np.convolve(x, np.ones(2001) / 2001, mode="same")
        x /= np.max(np.abs(x)) + 1e-9
    return x


def filtro(x, lo=None, hi=None):
    """Passa-banda por FFT (lo/hi em Hz)."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    m = np.ones_like(f)
    if lo:
        m *= 1 / (1 + (lo / np.maximum(f, 1)) ** 4)
    if hi:
        m *= 1 / (1 + (f / hi) ** 4)
    return np.fft.irfft(X * m, len(x)).astype(np.float32)


def coro(freqs, dur, vogal=(800, 1150, 2900), ataque=0.4):
    """Coro sintético "ah": dentes-de-serra com vibrato, moldados por formantes."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    s = np.zeros(n, np.float32)
    for k, f0 in enumerate(freqs):
        for voz in range(3):
            vib = 1 + 0.006 * np.sin(2 * np.pi * (5.0 + voz * 0.4) * t + k + voz)
            ph = np.cumsum(f0 * (1 + (voz - 1) * 0.004) * vib) / SR
            s += (2 * (ph % 1.0) - 1).astype(np.float32)
    X = np.fft.rfft(s)
    f = np.fft.rfftfreq(n, 1 / SR)
    forma = sum(g * np.exp(-((f - fc) / (fc * 0.12)) ** 2) for fc, g in zip(vogal, (1.0, 0.6, 0.25)))
    s = np.fft.irfft(X * forma, n).astype(np.float32)
    a = np.minimum(1, t / ataque) * np.minimum(1, (dur - t) / 0.3)
    return s * a / (np.max(np.abs(s)) + 1e-9)


def reverb(x, tempo=2.5, mistura=0.35, semente=0):
    r = np.random.default_rng(semente)
    n = int(SR * tempo)
    ir = r.normal(0, 1, n).astype(np.float32) * np.exp(-np.arange(n) / SR / (tempo / 6.9))
    ir = filtro(ir, hi=6000)
    m = len(x) + n
    y = np.fft.irfft(np.fft.rfft(x, m) * np.fft.rfft(ir, m), m)[: len(x)]
    y = y / (np.max(np.abs(y)) + 1e-9) * (np.max(np.abs(x)) + 1e-9)
    return ((1 - mistura) * x + mistura * y).astype(np.float32)


# ---------------------------------------------------------------------------
def compor():
    musica, efeitos = pista(), pista()
    tt = np.arange(N) / SR

    # --- gabinete: zumbido de CRT e o ecrã a ligar
    hum = (0.5 * np.sin(2 * np.pi * 50 * tt) + 0.25 * np.sin(2 * np.pi * 100 * tt) + 0.12 * np.sin(2 * np.pi * 150 * tt)
           + 0.02 * np.sin(2 * np.pi * 15734 * tt))
    liga = np.clip((tt - t_(ECRA_LIGA)) * 8, 0, 1) * np.clip((t_(MERGULHO) - tt) * 3, 0, 1)
    efeitos += (hum * liga * 0.06).astype(np.float32)
    thunk = filtro(ruido(int(SR * 0.25)), hi=300) * env(int(SR * 0.25), 0.001, 0.06)
    por(efeitos, thunk, t_(ECRA_LIGA), 0.9)
    estatica = filtro(ruido(int(SR * 0.5)), lo=2000) * env(int(SR * 0.5), 0.001, 0.12)
    por(efeitos, estatica, t_(ECRA_LIGA) + 0.02, 0.25)
    # três notas a acordar, lentas e desafinadas
    for k, (nm, t0) in enumerate((("E5", 0.9), ("C5", 1.45), ("A4", 2.0))):
        por(musica, caixinha(nota(nm), 2.2, desafina=-0.012 + 0.004 * k), t0, 0.35)

    # --- mergulho no ecrã: whoosh e boot de consola (inventado)
    n = int(SR * 0.9)
    w = filtro(ruido(n), lo=400, hi=5000) * np.linspace(0, 1, n) ** 2
    por(efeitos, w, t_(MERGULHO) - 0.85, 0.5)
    bt = np.arange(int(SR * 1.2)) / SR
    boot = (np.sin(2 * np.pi * nota("E6") * bt) * (bt < 0.09) + np.sin(2 * np.pi * nota("A6") * bt) * (bt >= 0.09)) * np.exp(-bt / 0.35)
    boot += 0.5 * np.sin(2 * np.pi * nota("A3") * bt) * np.exp(-bt / 0.5)
    por(efeitos, reverb(boot.astype(np.float32), 1.5, 0.4, 3), t_(MERGULHO), 0.35)

    # --- a valsa: um compasso (3/4) por segundo, um compasso por mundo; depois o Inferno
    compasso = 1.0
    t_valsa = t_(MERGULHO)
    harmonia = [("A2", ["A4", "C5", "E5"]), ("D3", ["D5", "F5", "A5"]), ("E2", ["G#4", "B4", "E5"]), ("A2", ["A4", "C5", "E5"]),
                ("F2", ["F4", "A4", "C5"]), ("E2", ["G#4", "B4", "D5"])]
    melodia = [["E5", "A5", "C6"], ["F5", "E5", "D5"], ["B4", "E5", "G#5"], ["A5", "C6", "E6"],
               ["F5", "E5", "C5"], ["B4", "D5", "G#5"]]
    for b, ((baixo, acorde), mel) in enumerate(zip(harmonia, melodia)):
        t0 = t_valsa + b * compasso
        por(musica, pizzicato(nota(baixo)), t0, 0.55)
        for beat in (1, 2):
            for nm in acorde:
                por(musica, pizzicato(nota(nm) / 2, 0.4), t0 + beat * compasso / 3, 0.12)
        for k, nm in enumerate(mel):
            por(musica, caixinha(nota(nm), 1.8), t0 + k * compasso / 3, 0.28 if k == 0 else 0.2)

    # passos, no tempo da caminhada do boneco (um passo a cada 13 frames)
    for f in range(MERGULHO + 4, CHEGA + 1):
        if f % 13 == 0:
            n = int(SR * 0.12)
            p = filtro(ruido(n), lo=80, hi=1800) * env(n, 0.002, 0.03)
            por(efeitos, p, t_(f), 0.45)

    # um toque por corte: sino da escola, corvo, "ah" de coro, sopro de fogo
    c1, c2, c3, c4 = (t_(c) for c in CORTES)
    sb = np.arange(int(SR * 1.2)) / SR
    sino = sum(a * np.sin(2 * np.pi * nota("E6") * r * sb) for a, r in ((1, 1), (0.5, 2.4), (0.3, 3.9))) * np.exp(-sb / 0.4)
    por(efeitos, sino.astype(np.float32), c1, 0.12)
    for k in range(2):   # corvo: ruído com formante a descer, duas vezes
        n = int(SR * 0.22)
        cw = ruido(n)
        fc = np.linspace(1400, 900, n)
        cw = cw * (1 + np.sin(2 * np.pi * np.cumsum(fc) / SR)) * env(n, 0.01, 0.1)
        por(efeitos, filtro(cw, lo=500, hi=3000), c2 + 0.05 + k * 0.28, 0.35)
    por(musica, reverb(coro([nota("A4"), nota("E5")], 0.9, ataque=0.08), 2.0, 0.5, 5), c3, 0.3)
    n = int(SR * 2.8)
    fogo = filtro(ruido(n, "castanho"), hi=900) * (0.6 + 0.4 * filtro(ruido(n), hi=6)) * np.minimum(1, np.arange(n) / SR / 0.3)
    fogo *= np.clip((t_(GELO[0]) + 0.6 - (c4 + np.arange(n) / SR)) / 0.6, 0, 1)
    por(efeitos, fogo.astype(np.float32), c4 - 0.1, 0.45)

    # --- Inferno: graves e coro sombrio
    t_inf = c4
    n = int(SR * (t_(GELO[0]) + 0.3 - t_inf))
    grave = (np.sin(2 * np.pi * nota("A1") * np.arange(n) / SR) + 0.5 * np.sin(2 * np.pi * nota("E2") * np.arange(n) / SR))
    grave *= np.minimum(1, np.arange(n) / SR / 0.4) * np.minimum(1, (n - np.arange(n)) / SR / 0.3)
    por(musica, grave.astype(np.float32), t_inf, 0.22)
    por(musica, reverb(coro([nota("A3"), nota("C4"), nota("E4"), nota("A2")], t_(GELO[0]) + 0.4 - t_inf, ataque=0.6), 2.5, 0.45, 7),
        t_inf, 0.32)

    # --- o inferno gela: a caixinha abranda e desafina; gelo a estalar
    g0, g1 = t_(GELO[0]), t_(GELO[1])
    queda = ["C6", "A5", "E5", "C5", "A4"]
    for k, nm in enumerate(queda):
        t0 = g0 + (g1 - g0) * (k / len(queda)) ** 0.8
        por(musica, caixinha(nota(nm), 2.2, desafina=-0.01 * k, bend=-0.03 * k), t0, 0.26)
    for k in range(9):
        t0 = g0 + rng.uniform(0, g1 - g0 + 0.2)
        n = int(SR * 0.08)
        cr = filtro(ruido(n), lo=2500) * env(n, 0.0005, 0.012)
        por(efeitos, cr, t0, rng.uniform(0.25, 0.5))
    n = int(SR * (g1 - g0))
    brilho = np.sin(2 * np.pi * np.cumsum(np.linspace(nota("E6"), nota("E7"), n)) / SR) * np.sin(np.pi * np.arange(n) / n) ** 2
    por(musica, brilho.astype(np.float32), g0, 0.05)
    n = int(SR * 0.9)
    geada = filtro(ruido(n), lo=5000) * np.sin(np.pi * np.arange(n) / n)
    por(efeitos, geada, g0 + 0.2, 0.08)

    # --- silêncio e a nota final no logo
    tl = t_(LOGO_NOTA)
    fim = caixinha(nota("A5"), 3.0) + 0.6 * caixinha(nota("E6"), 3.0, desafina=0.002) + 0.4 * caixinha(nota("A4"), 3.0)
    por(musica, fim, tl, 0.35)
    fundo = coro([nota("A3"), nota("E4")], DUR - tl, vogal=(400, 800, 2600), ataque=0.6)
    por(musica, fundo, tl, 0.08)
    silencio = np.ones(N, np.float32)
    s0, s1 = t_(GELO[1]) + 0.05, tl
    idx = (tt > s0) & (tt < s1)
    silencio[idx] = 0.08
    musica *= silencio

    esq = reverb(musica, 2.8, 0.38, 11) + efeitos * 0.9
    dir_ = reverb(musica, 2.8, 0.38, 12) + efeitos * 0.9
    st = np.stack([esq, dir_], 1)
    fade = np.minimum(1, tt / 0.05)[:, None] * np.minimum(1, (DUR - tt) / 0.4)[:, None]
    st = st * fade
    st = st / (np.max(np.abs(st)) + 1e-9) * 0.89
    return st.astype(np.float32)


# ---------------------------------------------------------------------------
# Estilo "trailer de ação"
# ---------------------------------------------------------------------------
def serra(freq, dur, detune=0.0):
    t = np.arange(int(SR * dur)) / SR
    f = freq * (1 + detune)
    return (2 * ((f * t) % 1.0) - 1).astype(np.float32)


def braaam(raiz="A1", dur=2.2, abre=0.25):
    """Metais graves à Inception: serras desafinadas, distorção e um filtro que abre."""
    n = int(SR * dur)
    s = np.zeros(n, np.float32)
    for nm in (raiz, raiz[:-1] + str(int(raiz[-1]) + 1)):
        for d in (-0.012, -0.004, 0.0, 0.005, 0.011):
            s += serra(nota(nm), dur, d)
    s += 0.8 * serra(nota(raiz) * 1.5, dur, 0.003)            # a quinta
    escuro, claro = filtro(s, hi=180), filtro(s, hi=2400)
    t = np.arange(n) / SR
    abertura = np.clip(t / abre, 0, 1) * np.exp(-t / 0.9)
    s = escuro * (1 - abertura) + claro * abertura
    s = np.tanh(s / (np.max(np.abs(s)) + 1e-9) * 3.0)
    return (s * np.minimum(1, t / 0.03) * np.exp(-t / (dur * 0.45))).astype(np.float32)


def impacto(dur=2.5, f0=70.0, f1=28.0):
    """Pancada de trailer: sub-grave a descer + estalo de ruído."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t / 0.25)
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.9)
    estalo = filtro(ruido(n), hi=4000) * np.exp(-t / 0.05)
    corpo = filtro(ruido(n), hi=400) * np.exp(-t / 0.3)
    return np.tanh(1.6 * sub + 0.7 * estalo + 0.8 * corpo).astype(np.float32)


def taiko(forca=1.0):
    n = int(SR * 0.6)
    t = np.arange(n) / SR
    f = 55 + 60 * np.exp(-t / 0.03)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.18)
    s += 0.5 * filtro(ruido(n), hi=900) * np.exp(-t / 0.03)
    return (np.tanh(s * 1.5) * forca).astype(np.float32)


def tarola():
    n = int(SR * 0.25)
    t = np.arange(n) / SR
    s = filtro(ruido(n), lo=1500) * np.exp(-t / 0.06) + 0.5 * np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.04)
    return s.astype(np.float32)


def riser(dur, f_ini=200.0, f_fim=2400.0):
    """Tensão a subir: ruído que clareia e serras em glissando."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    u = t / dur
    nz = ruido(n)
    bandas = [filtro(nz, lo=lo, hi=lo * 2.2) for lo in (150, 500, 1500, 4000)]
    peso = np.clip(u * len(bandas), 0, len(bandas) - 1e-6)
    k = peso.astype(int)
    fr = peso - k
    b = np.stack(bandas)
    ruido_sobe = b[k, np.arange(n)] * (1 - fr) + b[np.minimum(k + 1, len(bandas) - 1), np.arange(n)] * fr
    f = f_ini * (f_fim / f_ini) ** (u ** 1.5)
    gl = sum(2 * ((np.cumsum(f * (1 + d)) / SR) % 1.0) - 1 for d in (-0.01, 0.0, 0.01)) / 3
    gl = filtro(gl.astype(np.float32), hi=3500)
    return ((0.6 * ruido_sobe + 0.4 * gl) * u ** 2.2).astype(np.float32)


def ostinato(t0, t1, dst, notas=("A2", "A2", "C3", "A2", "E3", "A2", "D3", "A2"), passo=0.125, ganho=0.18):
    """Cordas graves em staccato, a semicolcheias (120 bpm)."""
    k = 0
    t = t0
    while t < t1 - 0.01:
        n = int(SR * passo * 0.9)
        s = sum(serra(nota(notas[k % len(notas)]), passo * 0.9, d) for d in (-0.006, 0.0, 0.006))
        s = filtro(s.astype(np.float32), hi=1400) * env(n, 0.003, 0.05)
        acento = 1.35 if k % 4 == 0 else 1.0
        por(dst, s, t, ganho * acento)
        t += passo
        k += 1


def compor_trailer():
    musica, perc, efeitos = pista(), pista(), pista()
    tt = np.arange(N) / SR
    m0 = t_(MERGULHO)
    cortes = [t_(c) for c in CORTES]
    g0, g1 = t_(GELO[0]), t_(GELO[1])
    tl = t_(LOGO_NOTA)

    # 0–2,5 s: tiquetaque (a acelerar), drone a crescer, CRT
    t = 0.2
    k = 0
    while t < m0 - 0.3:
        n = int(SR * 0.02)
        tick = filtro(ruido(n), lo=3000 if k % 2 else 5000) * env(n, 0.0005, 0.004)
        por(efeitos, tick, t, 0.5)
        t += 0.5 if t < 1.2 else 0.25
        k += 1
    n = int(SR * m0)
    drone = (np.sin(2 * np.pi * nota("A1") * tt[:n]) + 0.4 * serra(nota("A2"), m0, 0.004)[:n] * 0.2) * (tt[:n] / m0) ** 1.5
    por(musica, drone.astype(np.float32), 0, 0.3)
    hum = 0.5 * np.sin(2 * np.pi * 50 * tt) + 0.25 * np.sin(2 * np.pi * 100 * tt)
    efeitos += (hum * np.clip((tt - t_(ECRA_LIGA)) * 8, 0, 1) * np.clip((m0 - tt) * 3, 0, 1) * 0.05).astype(np.float32)
    por(perc, impacto(1.2, 90, 45), t_(ECRA_LIGA), 0.35)                  # o ecrã acende: um "tum"
    por(efeitos, riser(1.3, 300, 3000), m0 - 1.3, 0.55)                   # a entrar no ecrã

    # 2,5 s: BRAAAM + impacto — a caminhada começa
    por(musica, braaam("A1", 2.0), m0, 0.9)
    por(perc, impacto(), m0, 1.0)

    # 2,5–6,5 s: ostinato, taikos no tempo, um impacto e um whoosh em cada corte
    ostinato(m0 + 0.25, cortes[3], musica)
    batida = 0.5
    t = m0 + batida
    k = 1
    while t < cortes[3] - 0.01:
        por(perc, taiko(1.0 if k % 2 == 0 else 0.6), t, 0.55)
        if k % 2 == 1:
            por(perc, tarola(), t + 0.25, 0.25)
        t += batida
        k += 1
    for i, c in enumerate(cortes[:3]):
        por(efeitos, riser(0.35, 800, 5000), c - 0.35, 0.35)
        por(perc, impacto(1.2, 80 - 5 * i, 40), c, 0.6)
        por(musica, braaam(("A1", "F1", "E1")[i], 0.9, 0.08), c, 0.35)

    # 6,5–8,9 s: Inferno — a tensão sobe até ao gelo
    ci = cortes[3]
    por(musica, braaam("D1", 1.4), ci, 0.8)
    por(perc, impacto(), ci, 0.9)
    ostinato(ci + 0.25, g0, musica, notas=("D2", "D2", "F2", "D2", "A2", "D2", "G#2", "D2"), ganho=0.2)
    por(efeitos, riser(g0 - ci, 150, 4000), ci, 0.75)
    t = ci + 0.5
    passo = 0.25
    while t < g0 - 0.02:                                                  # rufo de tarola a acelerar
        por(perc, tarola(), t, 0.18 + 0.25 * (t - ci) / (g0 - ci))
        t += passo
        passo = max(0.05, passo * 0.9)
    por(perc, taiko(1.2), ci + 1.0, 0.7)
    por(perc, taiko(1.2), ci + 1.5, 0.7)

    # 8,9 s: o inferno gela — a maior pancada, depois só gelo a estalar e tensão fina
    por(musica, braaam("A0", 2.6, 0.12), g0, 1.0)
    por(perc, impacto(3.0, 60, 22), g0, 1.1)
    n = int(SR * (g1 - g0 + 0.2))
    fio = sum(np.sin(2 * np.pi * nota(nm) * np.arange(n) / SR) for nm in ("E6", "F6", "A6")) / 3
    fio *= np.minimum(1, np.arange(n) / SR / 0.8)
    por(musica, fio.astype(np.float32), g0 + 0.4, 0.06)
    for _ in range(10):
        n = int(SR * 0.08)
        por(efeitos, filtro(ruido(n), lo=2500) * env(n, 0.0005, 0.012), g0 + 0.3 + rng.uniform(0, g1 - g0), rng.uniform(0.3, 0.6))

    # 10,3–10,9 s: silêncio total … e a última pancada no logo
    mix = musica + perc + efeitos
    final = pista()
    por(final, braaam("A1", 2.5, 0.05), tl, 0.9)
    por(final, impacto(2.5, 75, 25), tl, 1.1)
    por(final, taiko(1.3), tl, 0.6)
    n = int(SR * 1.6)
    brilho = sum(caixinha(nota(nm), 1.6) for nm in ("A5", "E6"))[:n]
    por(final, brilho, tl, 0.2)                                         # um aceno à caixinha de música
    # o corte para o silêncio vem depois da reverberação, para não ficar a cauda por baixo
    corte = (tt > g1 + 0.02) & (tt < tl)
    rampa = np.clip((tt - g1 - 0.02) / 0.12, 0, 1)
    gate = np.where(corte, 1 - rampa, np.where(tt >= tl, 0.0, 1.0)).astype(np.float32)
    st = np.stack([reverb(mix, 2.2, 0.25, 21) * gate + reverb(final, 2.4, 0.3, 23),
                   reverb(mix, 2.2, 0.25, 22) * gate + reverb(final, 2.4, 0.3, 24)], 1)
    st = np.tanh(st / (np.max(np.abs(st)) + 1e-9) * 1.8)                # limitador suave: mais volume
    st = st * np.minimum(1, (DUR - tt) / 0.3)[:, None]
    st = st / (np.max(np.abs(st)) + 1e-9) * 0.9
    return st.astype(np.float32)


def guardar_wav(path, st):
    pcm = (np.clip(st, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def ffmpeg_exe():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="musica_provisoria.wav")
    p.add_argument("--video", default="")
    p.add_argument("--com-som", default="")
    p.add_argument("--estilo", choices=("valsa", "trailer"), default="valsa")
    a = p.parse_args()
    guardar_wav(a.out, compor_trailer() if a.estilo == "trailer" else compor())
    print(f"> {a.out}")
    if a.video and a.com_som:
        subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-i", a.video, "-i", a.out, "-c:v", "copy", "-c:a", "aac",
                        "-b:a", "192k", "-shortest", a.com_som], check=True)
        print(f"> {a.com_som}")


if __name__ == "__main__":
    main()
