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
| 02 | [Igreja gótica soterrada](cenarios/02_messiah_igreja_soterrada/) | Messiah (2000) | v1 |
| 03 | [Gabinete do investigador](cenarios/03_gabinete_investigador/) | Base do canal (todos os vídeos) | v1 |
| 04 | [Floresta enevoada e a clareira](cenarios/04_floresta_enevoada/) | Cenário genérico de horror (noite e dia) | v1 |
| 05 | [Escola: corredor e sala de aula](cenarios/05_escola_corredor_sala/) | Sequência dos vultos (vazia → vultos → viraram-se) | v1 |
| 06 | [Cemitério gótico e decadente](cenarios/06_cemiterio_gotico/) | Estilo Tim Burton (noite e dia) | v1 |
| 07 | [Deserto: canyons, dunas e planícies](cenarios/07_deserto_canyons/) | Paisagem: dia → crepúsculo → noite, 40 s (Blender 5.x, Cycles) | v1 |
| 08 | [Inferno: fogo e gelo](cenarios/08_inferno_fogo_gelo/) | Estilo Tim Burton, inspirado em Dante (Brasas e Gelo, um só interruptor) | v1 |

## Guia de estilo (para os próximos cenários)

**Referência principal: Tim Burton** (*A Noiva Cadáver*, *O Estranho Mundo de Jack*,
*Sleepy Hollow*, *Beetlejuice*):

- **Formas exageradas e alongadas**: tudo mais alto, mais estreito e mais torto do que o
  real. Nada está perfeitamente direito.
- **Espirais e curvas**: ramos enrolados, ferro forjado em volutas, colinas encaracoladas.
- **Silhuetas negras recortadas** contra céus nublados e pálidos. O que se lê é a forma.
- **Paleta fria e dessaturada**: azul-acinzentado e violeta nas sombras. O **único calor**
  vem de fontes pequenas, como candeeiros, velas ou janelas.
- **Luar pálido e fraco**, sem lua grande à vista: céu nublado com uma zona mais clara.
- **Duas versões quando fizer sentido**: noite e dia, com o dia **igualmente inquietante**
  (céu encoberto, luz chapada, nevoeiro).
- **Um toque de humor macabro** nos detalhes: corvos pousados, relógios parados às 3:33, objetos fora de lugar.

## Estrutura

```
cenarios/
  NN_nome/
    build_scene.py   gera o .blend de raiz (reprodutível)
    *.blend          cenário pronto a abrir (Blender 5.0+; scripts compatíveis com 4.5 e 5.x)
    previews/        renders de pré-visualização
    README.md        planos, variantes, como pôr o personagem
```
