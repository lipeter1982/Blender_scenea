"""
Montagem da intro "A Travessia": junta os frames renderizados por travessia.py,
aplica as transições e codifica o vídeo.

  - fade-in do negro no início;
  - mergulho no CRT: o fim do gabinete pixeliza (blocos cada vez maiores, scanlines) e a
    floresta "resolve-se" a partir dos mesmos blocos — a estética PS1 do canal;
  - cortes em movimento (floresta → escola → cemitério → igreja → inferno): 2 frames de
    glitch de sinal (faixas deslocadas, RGB separado) em cada corte.

Precisa de Pillow e numpy; o vídeo usa o ffmpeg do sistema ou o do pacote imageio-ffmpeg.
Uso:
    python montagem.py --frames render_intro/frames --out intro_arcanauta.mp4 [--fps 12] [--letterbox]
"""

import argparse
import glob
import os
import random
import re
import shutil
import subprocess
import tempfile

import numpy as np
from PIL import Image

CORTES = [85, 109, 133, 157]    # primeiro frame de cada mundo (ver PLANOS em travessia.py)
MERGULHO = (48, 60, 72)         # começa a pixelizar, corte gabinete→floresta, floresta nítida


def ffmpeg_exe():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def pixelizar(im, bloco):
    if bloco <= 1:
        return im
    w, h = im.size
    pequeno = im.resize((max(1, w // bloco), max(1, h // bloco)), Image.BILINEAR)
    return pequeno.resize((w, h), Image.NEAREST)


def scanlines(a, forca):
    if forca <= 0:
        return a
    linhas = np.ones(a.shape[0], np.float32)
    linhas[::2] = 1.0 - forca
    return a * linhas[:, None, None]


def glitch(a, forca, rng):
    h, w, _ = a.shape
    out = a.copy()
    for _ in range(int(6 + 10 * forca)):
        y0 = rng.randrange(0, h)
        y1 = min(h, y0 + rng.randrange(2, max(3, h // 12)))
        out[y0:y1] = np.roll(out[y0:y1], rng.randrange(-int(w * 0.08 * forca) - 1, int(w * 0.08 * forca) + 1), axis=1)
    dx = max(1, int(w * 0.006 * forca))
    out[..., 0] = np.roll(out[..., 0], dx, axis=1)
    out[..., 2] = np.roll(out[..., 2], -dx, axis=1)
    return np.clip(out * (1 + 0.25 * forca), 0, 255)


def processar(im, f, rng, letterbox):
    a0, corte, a1 = MERGULHO
    if a0 <= f < corte:                                  # a entrar no ecrã
        t = (f - a0) / (corte - a0)
        im = pixelizar(im, int(1 + 30 * t ** 1.5))
        sl = 0.35 * t
    elif corte <= f < a1:                                # a sair na floresta
        t = 1 - (f - corte) / (a1 - corte)
        im = pixelizar(im, int(1 + 30 * t ** 1.5))
        sl = 0.35 * t
    else:
        sl = 0.0
    a = np.asarray(im, np.float32)
    a = scanlines(a, sl)
    for c in CORTES:
        if c <= f < c + 2:
            a = glitch(a, 1.0 if f == c else 0.45, rng)
        elif f == c - 1:
            a = glitch(a, 0.3, rng)
    if f <= 8:                                           # fade-in do negro
        a = a * (f / 8.0)
    if letterbox:                                        # barras 2.39:1
        h, w, _ = a.shape
        barra = int((h - w / 2.39) / 2)
        a[:barra] = 0
        a[h - barra:] = 0
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--frames", default="render_intro/frames")
    p.add_argument("--out", default="intro_arcanauta.mp4")
    p.add_argument("--fps", type=float, default=0, help="0 = automático (24 / passo entre frames)")
    p.add_argument("--letterbox", action="store_true")
    args = p.parse_args()
    fs = sorted(glob.glob(os.path.join(args.frames, "f_*.jpg")) + glob.glob(os.path.join(args.frames, "f_*.png")))
    nums = [int(re.search(r"f_(\d+)", os.path.basename(f)).group(1)) for f in fs]
    passo = min(b - a for a, b in zip(nums, nums[1:])) if len(nums) > 1 else 1
    fps = args.fps or 24.0 / passo
    rng = random.Random(7)
    tmp = tempfile.mkdtemp()
    for i, (f, path) in enumerate(zip(nums, fs)):
        im = processar(Image.open(path).convert("RGB"), f, rng, args.letterbox)
        im.save(os.path.join(tmp, f"m_{i:05d}.png"))
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error", "-framerate", str(fps), "-i", os.path.join(tmp, "m_%05d.png"),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", args.out]
    subprocess.run(cmd, check=True)
    shutil.rmtree(tmp)
    print(f"> {args.out}: {len(fs)} frames a {fps:g} fps")


if __name__ == "__main__":
    main()
