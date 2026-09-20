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

**Fases 1, 2 e 3 estão feitas.** As fases 4 e 5 ainda não existem.

| Fase | Estado |
|---|---|
| 1 — recolher | Feita; 16 fontes, camadas 1 e 2 |
| 2 — filtrar (pontuar com Haiku 4.5) | Feita; falta uma corrida a sério com chave |
| 3 — verificar | Feita; a parte do GitHub já correu a sério, a da pesquisa falta chave |
| 4 — veredicto (Sonnet 5) | Por fazer |
| 5 — publicar (GitHub Action) | Por fazer; por agora corre-se à mão |

A fase 3 tem dois caminhos. Um item que aponte para um repositório do GitHub — que são
quase dois terços da recolha — é verificado pela API do GitHub: estrelas, último commit,
licença e linguagem, de graça e sem passar por modelo nenhum. Tudo o resto vai a
pesquisa paga, que é a parte cara e por isso está limitada a três itens e duas pesquisas
cada por corrida. Um facto sem o URL de onde saiu não é guardado; o que não se confirmou
fica como dúvida em aberto.

O site lê `dados/itens.json` e mostra a recolha real. Enquanto a fase 2 não correr com
uma chave, os itens não têm nota nem veredicto e aparecem todos como *Incerto* — que é
o comportamento certo: sem dados não há julgamento.

## Estrutura

```
/
├─ index.html, estilo.css, app.js   # o site, servido pelo Pages a partir da raiz
├─ pipeline/
│  ├─ fontes.toml                   # as fontes, editáveis sem tocar no código
│  ├─ fontes.py                     # fase 1: lê RSS, Atom e APIs JSON, normaliza
│  ├─ filtrar.py                    # fase 2: pontua com o Haiku, com travões de custo
│  ├─ verificar.py                  # fase 3: factos do GitHub de graça, o resto por pesquisa
│  └─ principal.py                  # orquestra as fases
├─ dados/
│  ├─ itens.json                    # o que o site lê
│  └─ vistos.json                   # ids já processados
└─ requirements.txt                 # uma dependência só: o SDK da Anthropic
```

O site está na raiz, e não em `site/` como o `CLAUDE.md` previa, porque o GitHub Pages
só serve a partir da raiz ou de `/docs`. Assim o caminho `dados/itens.json` funciona
sem configuração nenhuma.

## Como correr

A fase 1 só precisa de Python 3.11 ou superior. A fase 2 precisa do SDK e da chave:

```bash
pip install -r requirements.txt
```

A chave nunca vai para o repositório nem para o site. Localmente é uma variável de
ambiente; no GitHub Action será um Secret.

```bash
setx ANTHROPIC_API_KEY "sk-ant-..."
```

```bash
python pipeline/principal.py                # recolhe, pontua e verifica
python pipeline/principal.py --estimar      # diz quanto ia custar, sem gastar nada
python pipeline/principal.py --sem-filtro   # só a fase 1, como antes
python pipeline/principal.py --sem-pesquisa # fase 3 só na parte que é de graça
python pipeline/principal.py --teto 0.05    # aperta o travão de custo da fase 2
python pipeline/principal.py --teto-fase3 0.05 # aperta o travão de custo da fase 3
python pipeline/principal.py --esquecer     # ignora o histórico e apanha tudo
```

Sem `ANTHROPIC_API_KEY` no ambiente, a fase 2 não corre e diz-o — a recolha faz-se na
mesma e os itens vão para o site sem nota. A parte gratuita da fase 3 corre sempre, com
chave ou sem ela.

Contas por corrida, com os tetos que estão no código: fase 2 até 0,25 USD (uma corrida
de 45 itens estimou 0,017 USD) e fase 3 até 0,12 USD. Uma corrida por dia dá menos de
4 USD por mês no pior caso, e o pior caso é raro porque a maioria dos candidatos são
repositórios e verificam-se de graça.

Para ver o site localmente (abrir o `index.html` direto no browser não funciona, o
`fetch` é bloqueado em `file://`):

```bash
python -m http.server 8765
```

## Os travões de custo

A fase 2 paga ao item, por isso há quatro limites, e cada um apanha uma coisa diferente:

| Travão | Onde está | O que apanha |
|---|---|---|
| `limite` por fonte | `fontes.toml` | uma fonte que passou a despejar resultados |
| `JANELA_DE_DIAS` | `principal.py` | o arquivo inteiro de um feed em vez do dia |
| `TETO_DE_ITENS` | `filtrar.py` | a recolha inteira a crescer sem explicação |
| `TETO_DE_DOLARES` | `filtrar.py` | tudo o resto, incluindo o que ainda não se imaginou |

O travão de dólares verifica-se antes de cada lote, com o que já se gastou a sério
(o `usage` da resposta), não com a estimativa. Quando dispara, pára e diz quantos
itens ficaram por pontuar.

O quinto travão é o `LIMIAR_FASE_3`, no `principal.py`: só os itens com nota igual ou
superior a 7 passam à fase 3, que é a fase cara, porque paga por pesquisa a $10 por
1000. Esse número é o que mais decide a fatura do projeto.

## Custo, medido

Números medidos a 2026-09-20, com os preços da tabela oficial dessa data
(Haiku 4.5 a $1/$5 por milhão de tokens de entrada/saída).

- Prompt de sistema da fase 2: ~623 tokens, enviado uma vez por lote de 20 itens.
- Primeira corrida, a apanhar 7 dias de uma vez: 162 itens, 9 lotes, **$0,0588**.
- Corrida diária típica, 25 a 40 itens novos: **$0,009 a $0,015 por dia**, ou seja
  **$0,28 a $0,44 por mês**.

O orçamento alvo do projeto é menos de $5 por mês. A fase 2 usa menos de um décimo
disso. O que ainda pode furar o orçamento é a fase 3, e é por isso que o limiar dos
7 está onde está.

## As fontes

16 fontes, todas testadas a 2026-09-20. Nove de camada 1 (o autor a falar) e sete de
camada 2 (sinal de atenção, nunca verdade).

As de camada 2 não têm feed: são APIs JSON. Por isso cada fonte declara um `tipo` no
`fontes.toml` (`rss`, `hn` ou `github`) e o endereço leva marcadores — `{desde}` e
`{desde_iso}` — que o pipeline preenche na hora com a data de corte.

O corte do Hacker News está nos 150 pontos. Medido nesse dia: acima de 100 pontos são
284 histórias por semana, acima de 250 são 116. Os 150 dão cerca de 28 por dia.

A pesquisa do GitHub procura repositórios **criados** de fresco que já apanharam
estrelas. Ordenar os antigos por estrelas devolve sempre os mesmos gigantes e não diz
nada de novo.

## Por decidir

- O **Reddit** responde, mas corta pedidos seguidos com 429 — aconteceu nos testes à
  segunda chamada. Está lá uma comunidade só (`r/LocalLLaMA`). Se falhar todos os dias
  no Action, tira-se: uma fonte que nunca responde só suja o ecrã.
- A pesquisa do GitHub sem autenticação aceita 10 pedidos por minuto e devolve 403 a
  quem dispara quatro seguidos. O pipeline espera 6 segundos entre pedidos ao mesmo
  servidor, e usa `GITHUB_TOKEN` se ele existir no ambiente — dentro do Action há um
  de borla que sobe o limite para 30.
- A **Anthropic não publica RSS** (testado a 2026-09-20: `/rss.xml`, `/feed.xml`,
  `/news/rss.xml` e `/engineering/rss.xml` devolvem todos 404). Está coberta pelos
  feeds de releases no GitHub, que também são fonte primária, mas convém voltar a
  verificar.
- A **Batch API** dá 50% de desconto nas fases 2 e 4, em troca de um prazo de entrega
  até 24 horas — irrelevante para uma corrida diária agendada. Não está feito porque
  a fase 2 já custa cêntimos; vale a pena quando a fase 4 entrar.
- O ficheiro `dados/itens.json` ainda não corta os 60 dias de histórico previstos para
  a fase 5, porque ainda não há histórico para cortar.
