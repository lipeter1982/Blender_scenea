# Blender_scenea

Cenários de horror em Blender para os vídeos do canal: análises de jogos de horror
obscuros para PC e PlayStation, e curtas.

Cada cenário é entregue como um **set pronto a filmar**, com ambiente, iluminação
cinematográfica, atmosfera, câmaras sugeridas, variantes de luz e marcadores para
o personagem (avatar Mixamo). No fim só falta importar o personagem, escolher o
plano e retocar no render.

## Cenários

| # | Cenário | Jogo | Estado |
|---|---|---|---|
| 01 | [Cave de Rustin Parr](cenarios/01_blair_witch_cave_parr/) | Blair Witch Vol. 1: Rustin Parr (2000) | v1 |

## Estrutura

```
cenarios/
  NN_nome/
    build_scene.py   gera o .blend de raiz (reprodutível)
    *.blend          cenário pronto a abrir (Blender 4.5+)
    previews/        renders de pré-visualização
    README.md        planos, variantes, como pôr o personagem
```
