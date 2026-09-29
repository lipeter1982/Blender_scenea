# Intro do canal ARCANAUTA

## "A Travessia" (12 s): a intro principal

O avatar é o **Arcanauta**, um viajante que atravessa portas para mundos esquecidos. Cada
cenário é o mundo de um jogo obscuro. A intro é a viagem dele, do gabinete até às Portas do
Inferno, onde aparece o logo.

| Frames | Tempo | Plano | Cenário |
|---|---|---|---|
| 1–60 | 0–2,5 s | Sentado ao CRT, visto por cima do ombro. O ecrã acende com a floresta e a câmara **mergulha no ecrã** | 03 Gabinete |
| 61–84 | 2,5–3,5 s | Sai do ecrã **pixelizado (PS1)** e já está a caminhar na floresta | 04 Floresta |
| 85–108 | 3,5–4,5 s | **Corte em movimento**: o mesmo passo, agora no corredor da escola | 05 Escola |
| 109–132 | 4,5–5,5 s | Corte em movimento: atravessa o portão do cemitério | 06 Cemitério |
| 133–156 | 5,5–6,5 s | Corte em movimento: sobe a nave da igreja soterrada | 02 Igreja |
| 157–204 | 6,5–8,5 s | Chega às Portas do Inferno, a arder, e pára | 08 Inferno |
| 205–288 | 8,5–12 s | A câmara recua e sobe, **o inferno gela**, o lintel diz **ARCANAUTA** e ele **vira-se para nós** | 08 Inferno |

Porque é que os cortes funcionam: em todos os mundos, a câmara segue o Arcanauta **à mesma
distância, altura e lente** (`SEGUE_DIST`, `SEGUE_ALT`, `SEGUE_LENTE`), e o ciclo de passada
continua de plano para plano. Parece uma só caminhada que atravessa mundos. Cada corte leva 2
frames de *glitch* de sinal.

**Som** (a acrescentar na edição): zumbido de CRT e o clique do disco; **passos contínuos por
cima de todos os cortes**; um apontamento de 0,3 s por mundo (corvo, sino da escola, coro);
fogo, estalar de gelo e depois silêncio, com um último som no logo.

**Versão curta de 4 s** para separadores a meio dos vídeos: use os frames 196–288 (o gelo e o logo).

### Ficheiros

- `travessia.py`: gera cada plano a partir do seu cenário, junta o avatar, anima a câmara e
  renderiza os frames com a numeração global da intro.
- `boneco.py`: **boneco provisório** (manequim articulado) com as animações de andar, sentar,
  ficar parado e olhar por cima do ombro. Fica no lugar do avatar Mesh2Motion até ele entrar.
- `montagem.py`: junta os frames, aplica o fade-in, o mergulho pixelizado no CRT e os *glitches*
  dos cortes, e codifica o MP4 (opcional: `--letterbox` para barras 2.39:1).
- `animatic_travessia.mp4`: o *animatic* (480 px, 12 fps, poucas amostras), só para acertar o ritmo.

```bash
# animatic rápido (todos os planos, 480 px, 1 frame em cada 2)
python travessia.py --out render_intro --res 480 --samples 8 --step 2
python montagem.py --frames render_intro/frames --out animatic_travessia.mp4

# render final (num PC com GPU; um plano de cada vez, se quiser)
python travessia.py --out render_intro --res 1920 --samples 128
python travessia.py --shot inferno --out render_intro --res 1920 --samples 128
python montagem.py --frames render_intro/frames --out intro_arcanauta.mp4
```

Dentro do Blender: `blender -b -P travessia.py -- --shot gabinete --out render_intro`.
Cada plano fica também guardado em `render_intro/blend/intro_<plano>.blend`, para abrir e afinar.

### Trocar o boneco pelo avatar (Mesh2Motion)

Exporte do Mesh2Motion **um GLB** com o avatar e as animações: sentado, caminhada, idle de pé e
olhar à volta (ou o mais parecido que houver na biblioteca). A seguir, o `boneco.py` ganha uma
função que importa o GLB e aplica cada animação no lugar da pose procedural. Se a caminhada for
"no sítio", o avatar desloca-se pelo mesmo percurso e à mesma velocidade (`VELOCIDADE`).

## Plano do Inferno sozinho: `plano_inferno_arcanauta.py`

O primeiro teste (6 s): uma grua até às Portas, o inferno gela e fica o logo ARCANAUTA. As funções
de inscrição e de gelo são reutilizadas pela Travessia. O vídeo de teste está em `teste_plano_inferno.mp4`.

```bash
blender -b -P plano_inferno_arcanauta.py -- --out plano_inferno.blend
```
