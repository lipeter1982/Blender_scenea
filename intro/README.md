# Intro do canal ARCANAUTA

Uma intro de 8 a 10 segundos feita com os cenários do repositório. Junta a direção artística
Burton com a estética de consola antiga (CRT, PS1), que é a do nicho do canal: jogos obscuros
de PC, PS1 e PS2.

## Guião

| Tempo | Plano | Cenário | Estado |
|---|---|---|---|
| 0–1,5 s | Escuro, estalido de CRT a ligar e o ecrã do gabinete acende | 03 Gabinete | por fazer |
| 1,5–4 s | No ecrã, cortes rápidos (0,4 s) com *scanlines*: portão do cemitério, igreja, floresta, cave | 01, 02, 04, 06 | por fazer |
| 4–10 s | **Plano do Inferno**: a câmara sobe até às Portas, o inferno gela e o lintel diz **ARCANAUTA** | 08 | **v1** |

Som: zumbido de CRT, um "boot" ao estilo de consola antiga (sem usar o som de arranque da
PlayStation, que tem direitos de autor) e um estalar de gelo no fim.

## Plano do Inferno — `plano_inferno_arcanauta.py`

Gera o cenário 08 de raiz e acrescenta:
- a inscrição do lintel trocada por **ARCANAUTA** e *"jogos obscuros · PC · PS1 · PS2"*, gravada a fogo
  e depois em gelo azul luminoso;
- a câmara `CAM_INTRO_Portas`, uma grua que parte do chão, à distância, e sobe até enquadrar o
  lintel (frames 1–144, 6 s a 24 fps);
- a propriedade `gelo` animada de 0 para 1 entre os frames **62 e 98**: a lava apaga-se, as
  chamas congelam, cai neve e aparecem sincelos.

```bash
# gerar o .blend do plano
blender -b -P plano_inferno_arcanauta.py -- --out plano_inferno.blend
# vídeo de teste rápido (640 px, 12 amostras, 1 frame em cada 2)
blender -b -P plano_inferno_arcanauta.py -- --out plano_inferno.blend --render teste --res 640 --samples 12 --step 2
# render final: abrir plano_inferno.blend e renderizar a animação (1920×1080)
```

Para afinar, mude os tempos em `GELO_INI` e `GELO_FIM`, o texto em `TITULO` e `LINHA`, e o
movimento de câmara nos `keys` da função `camara()`.

**Tempo de render:** com Cycles em CPU, a 1920×1080, conte com vários minutos por frame
(144 frames). Numa GPU fica numa noite. Para despachar, baixe as amostras para 64 com denoise.
