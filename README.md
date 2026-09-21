# Sinal

Recolhe o que se publica sobre IA e desenvolvimento onde a informação nasce, julga-o
contra o perfil do Duarte, e diz o que fazer com ele. O objetivo não é mostrar mais
notícias — é mostrar menos, com um veredicto.

O contexto completo do projeto (para quem é, como se julga, o que está fora de âmbito)
está no `CLAUDE.md`, que fica só na máquina — descreve o Duarte em detalhe e este
repositório é público, por isso está no `.gitignore`.

- Site: https://duartemiguelsn-sudo.github.io/sinal/
- Repositório: https://github.com/duartemiguelsn-sudo/sinal

## Estado a 2026-09-21

**O pipeline está completo: fases 1 a 5.**

| Fase | Estado |
|---|---|
| 1 — recolher | Feita; 23 fontes, camadas 1, 2 e 3 |
| 2 — filtrar (pontuar com Haiku 4.5) | Feita e corrida a sério |
| 3 — verificar | Feita e corrida a sério, nos dois caminhos |
| 4 — veredicto (Sonnet 5) | Feita e corrida a sério |
| 5 — publicar (GitHub Action) | Feita; Secret e Pages ligados, o Action já fez commit |

A fase 2 não devolve só a nota. Devolve também o **nome** e a **linha do que a coisa
é**, ambos em português, e são eles que o cartão mostra em cima. O título do feed não
serve para ler: metade são slugs de repositório (`ejfkdev/ddc`) e quase todos vêm em
inglês. O modelo só pode usar o que está no título, no resumo e na fonte — se isso não
chegar, escreve que não dá para saber, que é melhor do que inventar. O título original
não se perde: fica no tooltip da ligação.

A fase 2 arruma também cada item numa **área**, uma só, escolhida pelo assunto e não
pela fonte. São as oito por que o painel se lê, mais uma válvula de escape:

| Área | O que leva | Novidades esperadas |
|---|---|---|
| Modelos e APIs | lançamentos dos laboratórios, modelos novos, preços, limites | Diária |
| Agentes e ferramentas de código | Claude Code, Copilot, Cursor, editores, CLIs, planos | Diária |
| Skills, MCP e automação | servidores e clientes MCP, skills, prompts, automação | Diária |
| Repositórios em alta | tração recente sem assunto próprio noutra área | Diária |
| Grátis para estudante | cursos, certificações, licenças, Student Pack | Semanal |
| O teu stack | PHP, web, Android, Java, MySQL, MQTT: versões, CVEs, fim de suporte | Diária |
| Ferramentas do dia-a-dia | clientes REST, base de dados, utilitários, ícones e fontes | Semanal |
| Carreira júnior | o que se pede a um júnior em Portugal, portfólio, estágios | Semanal |
| Fora de âmbito | não cabe em nenhuma das oito | — |

Uma área por item, e não duas, porque duas punham o mesmo item em dois filtros ao mesmo
tempo — e um filtro que devolve o mesmo duas vezes não está a filtrar. A lista é fechada
por `enum` no esquema da resposta, por isso a API garante sozinha que a área existe.
O desempate está escrito no prompt: um repositório de MCP vai para *Skills, MCP e
automação* e não para *Repositórios em alta*; um de PHP ou Android vai para *O teu
stack*; uma oferta de estudante vai para *Grátis para estudante* seja qual for o assunto.

*Fora de âmbito* é o alarme. Na corrida de 2026-09-21 levou **81 de 164** itens, quase
todos do Hacker News e do r/LocalLLaMA e nenhum acima de nota 4. Não é erro de
classificação: é a medida de quanto é que as fontes de hoje trazem que não serve para
nada. Quando encher, o sítio de mexer é o `fontes.toml`.

Três áreas nasceram sem fonte nenhuma que as alimentasse. A 2026-09-21 foram
procuradas fontes para elas, e o resultado foi desigual:

- *Ferramentas do dia-a-dia* resolveu-se bem. Quatro feeds de releases — Bruno, DBeaver,
  Lucide e Mosquitto — que são camada 1 porque é o próprio autor a anunciar a versão.
  Falam pouco e por isso quase não custam.
- *Grátis para estudante* resolveu-se a meio. Há freeCodeCamp e JetBrains Academy, que
  anunciam cursos e avisam quando uma oferta fecha, mas **a página do GitHub Student
  Pack continua sem feed** e é essa a que mais interessa.
- *Carreira júnior* não se resolveu. Não existe feed nenhum sobre o mercado português.
  Ficou a categoria do blogue do GitHub sobre o ofício, que é global e é opinião — dá
  alguma coisa, não dá o que a área promete.

O site mostra na mesma as áreas vazias, desligadas e a dizer porquê: escondê-las dava a
entender que não havia novidades, quando o que não há é fonte.

A fase 3 tem dois caminhos. Um item que aponte para um repositório do GitHub — que são
quase dois terços da recolha — é verificado pela API do GitHub: estrelas, último commit,
licença e linguagem, de graça e sem passar por modelo nenhum. Tudo o resto vai a
pesquisa paga, que é a parte cara e por isso está limitada a três itens e duas pesquisas
cada por corrida. Um facto sem o URL de onde saiu não é guardado; o que não se confirmou
fica como dúvida em aberto.

A fase 4 tem dois caminhos, pela mesma lógica. Os itens verificados — meia dúzia por
dia — vão ao Sonnet 5, que lê os factos da fase 3 e escreve o veredicto e o parágrafo
de justificação. Todos os outros, que são a esmagadora maioria, não vão a modelo
nenhum: o veredicto sai da nota que a fase 2 já pagou, por uma regra fixa (0–3 é
*Ruído*, 4–6 é *Depois*, sem nota é *Incerto*), e a justificação continua a ser a
frase que a fase 2 escreveu. Custo zero, e nenhum facto novo aparece pelo caminho.
Um item nunca chega a *Agora* por esta via: para ser *Agora* é preciso alguém ter ido
ver os factos, e isso é a fase 3.

A fase 5 é a única que lê o disco antes de lhe escrever. Junta a corrida de hoje ao
que já estava publicado — sem isto, cada corrida apagava o dia anterior — e corta o que
passou os 60 dias, para o ficheiro que o telemóvel descarrega não crescer sem fim. Um id
repetido não substitui o item antigo em bloco: escreve por cima campo a campo, para que
uma corrida sem chave não deite fora a nota e o veredicto que já foram pagos. O
`vistos.json` é cortado pela mesma janela e passou a guardar a data em que cada id foi
visto, porque sem ela não havia como saber qual é que já podia sair; ficheiros no formato
antigo continuam a ler-se.

**No `vistos.json` só entra o que tem nota.** "Visto" quer dizer julgado, não quer dizer
recolhido. Um item que passe pela fase 5 sem nota — porque não havia chave, porque o lote
falhou, porque um travão de custo o apanhou — não é dado por visto, e se já lá estava é
libertado para a corrida seguinte o apanhar outra vez. Sem esta regra, uma corrida sem
chave queima em silêncio tudo o que recolheu: o item fica no site como *Incerto* para
sempre e a fase 1 nunca mais o volta a ver. Aconteceu de verdade às primeiras corridas,
que prenderam 152 itens — a camada 1 inteira entre eles. Não faz ciclo sem fim porque a
fase 1 só aceita itens dos últimos sete dias: passada essa janela o feed deixa de os dar
e desiste-se sozinho.

O site lê `dados/itens.json` e mostra a recolha real. Enquanto a fase 2 não correr com
uma chave, os itens não têm nota e aparecem todos como *Incerto* — que é o
comportamento certo: sem dados não há julgamento.

## Estrutura

```
/
├─ index.html, estilo.css, app.js   # o site, servido pelo Pages a partir da raiz
├─ pipeline/
│  ├─ fontes.toml                   # as fontes, editáveis sem tocar no código
│  ├─ fontes.py                     # fase 1: lê RSS, Atom e APIs JSON, normaliza
│  ├─ filtrar.py                    # fase 2: pontua com o Haiku, com travões de custo
│  ├─ verificar.py                  # fase 3: factos do GitHub de graça, o resto por pesquisa
│  ├─ veredicto.py                  # fase 4: julgamento escrito pelo Sonnet, ou tirado da nota
│  ├─ publicar.py                   # fase 5: junta ao histórico, corta os 60 dias, grava
│  └─ principal.py                  # orquestra as fases
├─ .github/workflows/recolha.yml    # fase 5: corre o pipeline e faz commit, uma vez por dia
├─ dados/
│  ├─ itens.json                    # o que o site lê
│  └─ vistos.json                   # id -> data em que foi visto
├─ .env.exemplo                     # modelo do .env; o .env a sério nunca entra no Git
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

A chave nunca vai para o repositório nem para o site. Na tua máquina fica num `.env`,
que está no `.gitignore` e o Git não vê; no GitHub Action vem de um Secret, e lá o `.env`
nem existe. Copia o exemplo e preenche:

```bash
copy .env.exemplo .env
```

O `.env` tem duas linhas. A `ANTHROPIC_API_KEY` é a que paga as fases 2, 3 e 4, e tira-se
em <https://console.anthropic.com/settings/keys>. A `GITHUB_TOKEN` é opcional e sobe o
limite da pesquisa do GitHub na fase 3 de 10 para 30 pedidos por minuto; chega um token
clássico sem permissão nenhuma marcada.

O pipeline lê o ficheiro no arranque e diz os **nomes** das chaves que encontrou — nunca
os valores. O que já estiver no ambiente ganha ao ficheiro, por isso um `setx` continua a
funcionar se preferires:

```bash
setx ANTHROPIC_API_KEY "sk-ant-..."
```

Uma nota: esta pasta está dentro do OneDrive, por isso o `.env` é sincronizado para a
nuvem como qualquer outro ficheiro. Não sai do repositório nem do site, mas se preferires
que a chave não vá para lado nenhum, usa o `setx` e deixa o `.env` por preencher.

```bash
python pipeline/principal.py                   # recolhe, pontua, verifica e julga
python pipeline/principal.py --estimar         # diz quanto ia custar, sem gastar nada
python pipeline/principal.py --sem-filtro      # só a fase 1, como antes
python pipeline/principal.py --sem-pesquisa    # fase 3 só na parte que é de graça
python pipeline/principal.py --sem-veredicto   # fase 4 só na parte que é de graça
python pipeline/principal.py --teto 0.05       # aperta o travão de custo da fase 2
python pipeline/principal.py --teto-fase3 0.05 # aperta o travão de custo da fase 3
python pipeline/principal.py --teto-fase4 0.05 # aperta o travão de custo da fase 4
python pipeline/principal.py --esquecer        # ignora o histórico e apanha tudo
python pipeline/principal.py --historico 90    # guarda 90 dias em vez de 60; 0 não corta
```

Sem `ANTHROPIC_API_KEY` no ambiente, a fase 2 não corre e diz-o — a recolha faz-se na
mesma e os itens vão para o site sem nota. As partes gratuitas das fases 3 e 4 correm
sempre, com chave ou sem ela.

Com chave mas sem saldo na conta é o mesmo resultado, e também com a razão escrita: a
API responde 400 e as três fases pagas traduzem-no para *"a conta da Anthropic está sem
saldo"*, em vez do código sozinho. A corrida não se perde — recolhe, publica, e diz o
que ficou por pontuar.

Contas por corrida, com os tetos que estão no código: fase 2 até 0,25 USD (uma corrida
de 45 itens estimou 0,017 USD), fase 3 até 0,12 USD e fase 4 até 0,15 USD. Uma corrida
por dia dá menos de 5 USD por mês no pior caso, e o pior caso é raro: a maioria dos
candidatos são repositórios e verificam-se de graça, e a fase 4 só paga por meia dúzia
de itens.

Para ver o site localmente (abrir o `index.html` direto no browser não funciona, o
`fetch` é bloqueado em `file://`):

```bash
python -m http.server 8765
```

## A corrida automática

O `.github/workflows/recolha.yml` corre o pipeline às 06:00 UTC todos os dias, faz
commit do `dados/` neste mesmo repositório, e o site — que é estático e lê o ficheiro
directamente — fica actualizado sem mais nada. Se num dia não houver nada de novo, não
há commit: um dia vazio é um resultado, não uma avaria.

Faltam dois passos, que se fazem uma vez só e na interface do GitHub:

1. **Settings > Secrets and variables > Actions > New repository secret**, com o nome
   `ANTHROPIC_API_KEY`. Sem ele o Action corre na mesma, mas só faz a fase 1 e os itens
   vão para o site sem nota.
2. **Settings > Pages > Deploy from a branch**, ramo `main`, pasta `/ (root)`. É por
   isso que o site está na raiz e não em `site/`.

O Action escreve no repositório, e isso não é o comportamento por omissão: o
`permissions: contents: write` do ficheiro é que lho permite. Confirma também que em
**Settings > Actions > General** a opção *Workflow permissions* não está presa em
*Read repository contents*.

Para testar sem esperar um dia, o separador **Actions > recolha > Run workflow** corre
à mão, com uma caixa para o fazer sem gastar nada na API.

Um aviso sobre o agendamento: o GitHub atrasa — e às vezes salta — corridas agendadas
quando a plataforma está com carga, e desliga o `schedule` num repositório que fique
60 dias sem qualquer actividade. Por isso a janela de recolha é de sete dias e não de
um: uma corrida falhada não deixa buracos no site.

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
superior a 7 passam à fase 3 e à fase 4, que são as fases caras — uma paga por pesquisa
a $10 por 1000, a outra paga ao Sonnet 5. Esse número é o que mais decide a fatura do
projeto, porque mexe nas duas contas ao mesmo tempo.

A fase 4 tem os seus dois, no `veredicto.py`: `TETO_DE_ITENS_JULGADOS` (12 por corrida)
e `TETO_DE_DOLARES` (0,15 USD). Um item que um travão deixe por julgar não fica sem
rótulo — apanha o veredicto da nota, que para um item de nota alta dá *Incerto*. É o
estado honesto de quem não conseguiu julgar, e não uma promessa que ninguém verificou.

## Custo, medido

Números medidos a 2026-09-20, com os preços da tabela oficial dessa data
(Haiku 4.5 a $1/$5 por milhão de tokens de entrada/saída).

- Prompt de sistema da fase 2: ~1500 tokens, enviado uma vez por lote de 20 itens.
- Corrida a apanhar 7 dias de uma vez: 149 itens, 8 lotes, **$0,1161** medidos a
  2026-09-21, ou **$0,0008 por item**.
- Corrida diária típica, 25 a 40 itens novos: **$0,020 a $0,032 por dia**, ou seja
  **$0,60 a $0,96 por mês**.

Dois aumentos, medidos no mesmo dia e no mesmo lote:

- O `nome` e a linha do que a coisa é levaram o custo por item de **$0,00036 para
  $0,0008**, pouco mais do dobro. A culpa é toda dos tokens de saída, que são os
  caros: subiram de ~50 para ~95 por item. Uns $0,50 por mês.
- A área não custou praticamente nada. Substituiu a lista de temas, por isso a saída
  não mexeu; o que cresceu foi o prompt de sistema, de ~950 para ~1500 tokens, e esse
  é de entrada e paga-se uma vez por lote — na ordem de **$0,002 por corrida**.

As sete fontes acrescentadas a 2026-09-21 custam pouco porque falam pouco. Medido na
primeira corrida com elas: 14 itens novos, **$0,0120**, e nenhum chegou à nota 7, por
isso as fases 3 e 4 não correram. Em regime, esperam-se cerca de 3,5 itens por dia
vindos delas — dez em cada onze são do freeCodeCamp — o que dá **$0,09 por mês** na
fase 2. As quatro de releases somam menos de $0,01 por mês entre todas: na maior parte
dos dias não têm nada para dizer.

Em conjunto, a fase 2 fica em menos de **$1 por mês**, e o projeto todo, com a fase 4
por cima, na ordem dos **$2,50**.

Fase 4, estimada com os preços do Sonnet 5 ($2/$10 por milhão) sobre a recolha que
está no disco: 12 itens em 3 lotes dão **$0,063 por corrida**, ou **$1,90 por mês**.
Dez itens por dia, que é o esperado, ficam em **$1,60 por mês**. Os tokens de
raciocínio contam como saída, e é por isso que o esforço está em `low`.

O orçamento alvo do projeto é menos de $5 por mês. Somadas, as fases 2, 3 e 4 ficam
à volta de **$4 por mês no pior caso** e bem abaixo disso num dia normal. O que ainda
pode furar o orçamento são as fases 3 e 4, e é por isso que o limiar dos 7 está onde
está.

## As fontes

23 fontes, todas testadas antes de entrarem. Treze de camada 1 (o autor a falar), sete
de camada 2 (sinal de atenção, nunca verdade) e duas de camada 3 (ofertas para
estudante). As nove primeiras foram testadas a 2026-09-20, as sete últimas a 2026-09-21.

Quatro das de camada 1 são feeds de releases de ferramentas — Bruno para REST, DBeaver
para base de dados, Lucide para ícones, Mosquitto para MQTT. São camada 1 porque quem
anuncia a versão é quem a fez. O Mosquitto está calado desde 2026-02-09 e fica na mesma:
o dia em que sair um CVE, é por ali que chega primeiro.

Testados a 2026-09-21 e **recusados**, para ninguém voltar a gastar tempo com eles:

| Endereço | Porquê não |
|---|---|
| `github.blog/tag/student-developer-pack/feed/` | responde 200, mas o item mais recente é de 2021-09-01 |
| `github.blog/tag/github-education/feed/` | o mesmo, parado em 2024-11-21 |
| `microsoft.com/en-us/education/blog/feed/` | vivo, mas escrito para direções de escolas |
| `landing.jobs/blog/feed/` | responde 200 sem um único item |
| `itjobs.pt` | 404 em `/feed` e em `/noticias/rss` |
| `hoppscotch/hoppscotch` releases | vivo, mas o Bruno já cobre clientes REST |

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
  obriga a esperar e a ir buscar os resultados depois, o que parte a corrida em duas;
  vale a pena rever se a conta mensal se aproximar dos $5.
- A fase 4 podia **guardar em cache o prompt de sistema**, que é longo e não muda. Não
  está feito porque o mínimo para uma prefixo entrar em cache anda nos 1024 a 4096
  tokens conforme o modelo, e este anda perto do limite de baixo — é preciso medir
  antes de acrescentar código que talvez não poupe nada.
- O corte dos 60 dias está feito e testado, mas **ainda nunca cortou nada a sério** —
  não há histórico com essa idade. A primeira limpeza verdadeira é daqui a dois meses.
- Os ids que já estavam no `vistos.json` no formato antigo ficaram sem data. Mantêm-se
  enquanto o item deles estiver publicado, e saem na primeira limpeza depois disso.
- **A *Carreira júnior* continua sem fonte a sério.** Procurou-se a 2026-09-21 e não
  há feed nenhum sobre o mercado português: a `landing.jobs` responde sem itens e o
  `itjobs.pt` devolve 404. O que está lá é a categoria do blogue do GitHub sobre o
  ofício, que é global e é opinião. Resolver isto a sério obriga a pesquisa paga
  semanal, que é desenho novo e custo novo, e está por decidir.
- **A página de ofertas do GitHub Student Pack não tem feed** e é a que mais interessa
  à área *Grátis para estudante*. Dava para a vigiar de graça — buscar a página, guardar
  uma impressão digital da lista de ofertas e só produzir um item quando ela mudar, sem
  modelo nenhum pelo meio. É um `tipo` novo no `fontes.py` e ainda não está feito.
- **O freeCodeCamp está em observação.** Publica umas três por dia e na primeira corrida
  seis dos dez itens foram parar a *Fora de âmbito* — são tutoriais. Está lá porque é
  onde saem os cursos gratuitos, e custa uns $0,09 por mês. Se ao fim de uma semana não
  tiver trazido um único curso, é o primeiro a sair.
- A periodicidade das áreas é, para já, **uma promessa e não um mecanismo**. Está
  escrita no site para se saber o que esperar, mas o Action corre tudo uma vez por dia:
  não há fontes marcadas como semanais nem nada que as trave.
