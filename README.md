# Sinal

Recolhe o que se publica sobre IA e desenvolvimento onde a informação nasce, julga-o
contra o perfil do Duarte, e diz o que fazer com ele. O objetivo não é mostrar mais
notícias — é mostrar menos, com um veredicto.

O contexto completo do projeto (para quem é, como se julga, o que está fora de âmbito)
está no `CLAUDE.md`, que fica só na máquina — descreve o Duarte em detalhe e este
repositório é público, por isso está no `.gitignore`.

- Site: https://duartemiguelsn-sudo.github.io/sinal/
- Repositório: https://github.com/duartemiguelsn-sudo/sinal

## Estado a 2026-09-20

**Fase 1 (recolher) está feita e a funcionar.** As fases 2 a 5 ainda não existem.

| Fase | Estado |
|---|---|
| 1 — recolher | Feita |
| 2 — filtrar (pontuar com Haiku) | Por fazer, à espera de estimativa de custo |
| 3 — verificar | Por fazer |
| 4 — veredicto (Sonnet) | Por fazer |
| 5 — publicar (GitHub Action) | Por fazer; por agora corre-se à mão |

O site lê `dados/itens.json` e já mostra a recolha real. Como a fase 2 ainda não corre,
os itens não têm nota nem veredicto, por isso aparecem todos como *Incerto* — que é o
comportamento correto: sem dados não há julgamento.

## Estrutura

```
/
├─ index.html, estilo.css, app.js   # o site, servido pelo Pages a partir da raiz
├─ pipeline/
│  ├─ fontes.toml                   # as fontes, editáveis sem tocar no código
│  ├─ fontes.py                     # fase 1: lê RSS e Atom, normaliza os itens
│  └─ principal.py                  # orquestra as fases
└─ dados/
   ├─ itens.json                    # o que o site lê
   └─ vistos.json                   # ids já processados
```

O site está na raiz, e não em `site/` como o `CLAUDE.md` previa, porque o GitHub Pages
só serve a partir da raiz ou de `/docs`. Assim o caminho `dados/itens.json` funciona
sem configuração nenhuma.

## Como correr

```bash
python pipeline/principal.py              # só o que for novo
python pipeline/principal.py --esquecer   # ignora o histórico e apanha tudo
python pipeline/principal.py --dias 30    # alarga a janela (0 desliga o corte)
```

Só precisa de Python 3.11 ou superior. Não há dependências para instalar.

Para ver o site localmente (abrir o `index.html` direto no browser não funciona, o
`fetch` é bloqueado em `file://`):

```bash
python -m http.server 8765
```

## Para a estimativa da fase 2

Números medidos na recolha de 2026-09-20, para não se voltar a adivinhar:

- **9 fontes**, todas de camada 1, todas confirmadas a responder nessa data.
- **3183 itens** no total dos feeds — quase todos servem o arquivo completo, não o dia.
- **34 itens** dentro da janela de 7 dias, ou seja cerca de **5 por dia**.
- **283 caracteres** em média por item (título + resumo somados), com o maior a 485.
  O resumo é cortado aos 400 caracteres no `fontes.py`.
- Total de texto a enviar por recolha semanal: **9631 caracteres**.

A janela de 7 dias existe porque sem ela a primeira corrida mandava 3183 itens para um
modelo pago. Está em `pipeline/principal.py`, na constante `JANELA_DE_DIAS`.

Falta estimar: custo mensal da fase 2 com estes volumes, já a contar com o crescimento
quando entrarem as fontes de camada 2 (Hacker News, GitHub Trending), que são as que
trazem quantidade. O orçamento alvo do projeto é menos de 5 dólares por mês.

## Por decidir

- O grupo de filtros **Tema** no site aparece vazio, porque os temas só nascem na fase 2.
  Esconder o grupo enquanto não houver temas, ou deixar assim.
- A **Anthropic não publica RSS** (testado a 2026-09-20: `/rss.xml`, `/feed.xml`,
  `/news/rss.xml` e `/engineering/rss.xml` devolvem todos 404). Está coberta pelos feeds
  de releases no GitHub, que também são fonte primária, mas convém voltar a verificar.
- O ficheiro `dados/itens.json` ainda não corta os 60 dias de histórico previstos para a
  fase 5, porque ainda não há histórico para cortar.
