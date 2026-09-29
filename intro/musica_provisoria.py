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
Uso:
    python musica_provisoria.py --out musica_provisoria.wav
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
    a = p.parse_args()
    guardar_wav(a.out, compor())
    print(f"> {a.out}")
    if a.video and a.com_som:
        subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-i", a.video, "-i", a.out, "-c:v", "copy", "-c:a", "aac",
                        "-b:a", "192k", "-shortest", a.com_som], check=True)
        print(f"> {a.com_som}")


if __name__ == "__main__":
    main()
