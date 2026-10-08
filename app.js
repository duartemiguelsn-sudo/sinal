"use strict";

// O site tem três ecrãs, escolhidos pelo pedaço do endereço depois do "#":
//   #/            → Para ti: só o que pede decisão, curto de propósito
//   #/tudo        → Tudo: o arquivo inteiro em lista, com filtros
//   #/item/<id>   → um item sozinho, com factos, porquê e dúvidas
// Com o "#" não é preciso servidor: o GitHub Pages serve sempre o mesmo
// index.html e é o JavaScript que decide o que desenhar.

const VEREDICTOS = {
  agora: "Agora",
  depois: "Depois",
  ruido: "Ignora",
  incerto: "Sem dados"
};

// A camada diz quanto confiar. O texto curto vai na linha de metadados; o
// longo fica no title, para quem quiser confirmar o que o ponto quer dizer.
const CAMADAS = {
  1: ["Oficial", "Publicado pela própria fonte — é facto"],
  2: ["Por confirmar", "Está a circular (Hacker News, Reddit, GitHub) — atenção, não prova"],
  3: ["Para estudante", "Oferta ou programa para estudantes"],
  4: ["Contexto", "Resumo de terceiros, só para apanhar o que escapou"]
};

// A ordem é a de leitura do Duarte, igual à de `pipeline/filtrar.py`. As duas
// últimas já não são atribuídas, mas ainda há itens antigos com elas no
// histórico de 60 dias; ficam com nome para não aparecerem como um slug cru.
const AREAS = [
  ["modelos-apis", "Modelos e APIs"],
  ["agentes-codigo", "Agentes e ferramentas de código"],
  ["skills-mcp", "Skills, MCP e automação"],
  ["repos-em-alta", "Repositórios em alta"],
  ["gratis-estudante", "Grátis para estudante"],
  ["ferramentas-dia-a-dia", "Ferramentas do dia-a-dia"],
  ["meu-stack", "O meu stack"],
  ["carreira-junior", "Carreira júnior"]
];
const NOMES_AREAS = Object.fromEntries(AREAS);

// As listas mostram-se aos bocados. Os ignorados de uma semana passam das
// trezentas linhas, e desenhá-las todas de uma vez deixava o telemóvel lento.
const POR_PAGINA = 40;

// A nota a partir da qual um item vai à verificação e ao veredicto. É o
// LIMIAR_FASE_3 do pipeline/principal.py: se mudar lá, muda aqui.
const LIMIAR = 7;

// Quantos dias de ignorados o pipeline guarda (DIAS_DE_IGNORADOS, no
// pipeline/publicar.py). Só serve para a frase que o diz ao leitor.
const DIAS_IGNORADOS = 7;

// O selector de período de Tudo. Sessenta é o histórico inteiro que o
// pipeline guarda; mais do que isso não há.
const PERIODOS = [7, 14, 30, 60];

let itens = [];
let porId = new Map();
let erroCarga = null;

const estadoTudo = {
  veredicto: "todos",
  area: "todas",
  ordem: "data",
  periodo: 7,
  limite: POR_PAGINA,
  // A secção dos ignorados lembra-se se estava aberta e quantos mostrava,
  // para o leitor voltar de um item ignorado e cair no mesmo sítio.
  ignoradosAbertos: false,
  limiteIgnorados: POR_PAGINA
};

// Guarda onde se estava em cada lista. Ao voltar de um item, o leitor cai
// no mesmo sítio em vez de recomeçar do topo.
const posicoes = { "para-ti": 0, tudo: 0 };
let vistaActual = null;
let ultimaLista = "para-ti";

const conteudo = document.querySelector("#conteudo");
const dataRecolha = document.querySelector("#data-recolha");
const botaoTema = document.querySelector("#alternar-tema");

// ——— Utilitários ———

// Todo o texto entra com textContent, nunca com innerHTML. O conteúdo vem de
// feeds de terceiros, e um título com HTML lá dentro tem de aparecer como
// texto, não correr como código.
function el(nome, classe, texto) {
  const elemento = document.createElement(nome);
  if (classe) elemento.className = classe;
  if (texto !== undefined && texto !== null) elemento.textContent = String(texto);
  return elemento;
}

function lerData(valor) {
  const partes = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(valor || ""));
  if (!partes) return null;
  return new Date(Number(partes[1]), Number(partes[2]) - 1, Number(partes[3]));
}

function diasAtras(data) {
  const hoje = new Date();
  const inicioHoje = new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate());
  return Math.round((inicioHoje - data) / 86400000);
}

const formatoCurto = new Intl.DateTimeFormat("pt-PT", { day: "numeric", month: "short" });
const formatoLongo = new Intl.DateTimeFormat("pt-PT", { weekday: "long", day: "numeric", month: "long" });
const formatoNumero = new Intl.NumberFormat("pt-PT");

// "há 3 dias" lê-se mais depressa do que uma data. Passada uma semana, a
// distância deixa de ajudar e mostra-se a data.
function dataRelativa(valor) {
  const data = lerData(valor);
  if (!data) return "Sem data";
  const dias = diasAtras(data);
  if (dias <= 0) return "Hoje";
  if (dias === 1) return "Ontem";
  if (dias < 7) return `Há ${dias} dias`;
  return formatoCurto.format(data);
}

function rotuloDia(valor) {
  const data = lerData(valor);
  if (!data) return "Sem data";
  const dias = diasAtras(data);
  const longa = formatoLongo.format(data);
  if (dias <= 0) return `Hoje · ${longa}`;
  if (dias === 1) return `Ontem · ${longa}`;
  return longa.charAt(0).toUpperCase() + longa.slice(1);
}

function veredictoDe(item) {
  return VEREDICTOS[item.veredicto] ? item.veredicto : "incerto";
}

function avaliado(item) {
  return Number.isFinite(Number(item.nota)) && item.nota !== null && item.nota !== undefined;
}

// Um ignorado é o que o filtro deixou cair (nota abaixo do limiar) ou o que
// teve nota para passar mas não coube no limite diário da fase 3 — esse traz
// o campo `ignorado` com a razão. Não tem veredicto, só a nota e o porquê.
function ignorado(item) {
  return avaliado(item) && (Boolean(item.ignorado) || Number(item.nota) < LIMIAR);
}

// O que a vista principal mostra: passou o filtro e foi julgado. Um item sem
// nota não entra em lado nenhum — não há nada para dizer sobre ele.
function comVeredicto(item) {
  return avaliado(item) && !ignorado(item);
}

// A data pela qual um item envelhece: a de publicação, ou a de recolha quando
// o feed não a deu. É a mesma regra do pipeline/publicar.py.
function idadeDe(item) {
  return item.data || item.recolhido || "";
}

// O nome escrito pela fase 2 ganha ao título do feed, que é quase sempre
// inglês ou um slug `utilizador/projeto`. Sem avaliação, fica o título cru.
function nomeDe(item) {
  return String(item.nome || item.titulo || "Sem título");
}

function nomeArea(slug) {
  return NOMES_AREAS[slug] || "";
}

function urlSegura(valor) {
  try {
    const endereco = new URL(String(valor));
    return endereco.protocol === "https:" || endereco.protocol === "http:" ? endereco.href : null;
  } catch {
    return null;
  }
}

function idSeguro(id) {
  return String(id).replace(/[^a-zA-Z0-9_-]/g, "-");
}

// ——— Peças comuns ———

function marcaVeredicto(item, etiqueta = "p") {
  const v = veredictoDe(item);
  return el(etiqueta, `veredicto veredicto--${v}`, VEREDICTOS[v]);
}

function linhaMeta(item) {
  const meta = el("p", "meta");
  meta.append(el("span", "", item.fonte || "Fonte desconhecida"));

  const camada = CAMADAS[Number(item.camada)] ? Number(item.camada) : 4;
  const [curto, longo] = CAMADAS[camada];
  // O ponto é um elemento próprio e não um pseudo-elemento: o ::before do
  // span já está ocupado pelo separador "·" da linha de metadados.
  const indicador = el("span", `camada camada--${camada}`);
  indicador.title = longo;
  const ponto = el("span", "camada__ponto");
  ponto.setAttribute("aria-hidden", "true");
  indicador.append(ponto, document.createTextNode(curto));
  meta.append(indicador);

  const tempo = el("time", "", dataRelativa(item.data));
  tempo.dateTime = String(item.data || "");
  meta.append(tempo);
  return meta;
}

function ligacaoItem(item) {
  const ligacao = el("a", "ligacao-item", nomeDe(item));
  ligacao.href = `#/item/${encodeURIComponent(item.id)}`;
  return ligacao;
}

// A frase por baixo do título muda com o veredicto, para cada linha dizer o
// que interessa naquele caso: o que fazer, o que é, porque não, ou o que
// falta saber.
function fraseDaLinha(item) {
  const v = veredictoDe(item);
  if (v === "agora") return item.acao || item.o_que_e;
  if (v === "ruido") return item.justificacao || item.o_que_e;
  if (v === "incerto" && avaliado(item)) {
    return Array.isArray(item.duvidas) && item.duvidas.length ? item.duvidas[0] : item.o_que_e;
  }
  return item.o_que_e || item.resumo;
}

// Os factos da fase 3 numa linha só, pequena: "Estrelas 1 204 · Licença MIT".
// Três chegam para a lista; a ficha inteira está na página do item. Devolve
// null quando não há factos, para não deixar uma linha vazia.
function linhaFactos(item) {
  const factos = Array.isArray(item.factos)
    ? item.factos.filter((f) => f && f.rotulo && f.valor !== undefined).slice(0, 3)
    : [];
  if (factos.length === 0) return null;
  const linha = el("p", "factos-linha");
  factos.forEach((facto) => {
    const parte = el("span", "factos-linha__facto");
    parte.append(el("span", "factos-linha__rotulo", facto.rotulo), document.createTextNode(` ${valorFacto(facto.valor)}`));
    linha.append(parte);
  });
  return linha;
}

function criarLinha(item, compacta) {
  const v = veredictoDe(item);
  const linha = el("li", `linha linha--${v}${compacta ? " linha--compacta" : ""}`);
  const titulo = el("h3", "linha__titulo");
  titulo.append(ligacaoItem(item));
  linha.append(marcaVeredicto(item), titulo);
  const frase = fraseDaLinha(item);
  if (frase) linha.append(el("p", "linha__texto", frase));
  const factos = compacta ? null : linhaFactos(item);
  if (factos) linha.append(factos);
  // A área fica de fora da linha: escolhe-se no selector e aparece na página
  // do item. Com ela, a linha de metadados partia em duas no telemóvel.
  linha.append(linhaMeta(item));
  return linha;
}

function criarEntrada(item) {
  const entrada = el("li", "entrada");
  const titulo = el("h3", "entrada__titulo");
  titulo.append(ligacaoItem(item));
  entrada.append(marcaVeredicto(item), titulo);
  if (item.o_que_e) entrada.append(el("p", "entrada__texto", item.o_que_e));
  if (item.acao) entrada.append(el("p", "entrada__acao", item.acao));
  const factos = linhaFactos(item);
  if (factos) entrada.append(factos);
  entrada.append(linhaMeta(item));
  return entrada;
}

function estado(titulo, texto, ligacao, erro) {
  const caixa = el("div", `estado${erro ? " estado--erro" : ""}`);
  caixa.setAttribute("role", erro ? "alert" : "status");
  caixa.append(el("p", "estado__titulo", titulo));
  if (texto) caixa.append(el("p", "", texto));
  if (ligacao) {
    const p = el("p");
    const a = el("a", "", ligacao[0]);
    a.href = ligacao[1];
    p.append(a);
    caixa.append(p);
  }
  return caixa;
}

// ——— Para ti ———

function ordenarPorDataENota(a, b) {
  return String(b.data || "").localeCompare(String(a.data || "")) || Number(b.nota || 0) - Number(a.nota || 0);
}

function desenharParaTi() {
  // Só itens com veredicto. Um ignorado pode ter "depois" e nota 8 (ficou
  // fora do limite diário), mas ninguém o julgou — não é para aqui.
  const julgados = itens.filter(comVeredicto);
  const agora = julgados.filter((item) => veredictoDe(item) === "agora").sort(ordenarPorDataENota);
  const depoisTodos = julgados.filter((item) => veredictoDe(item) === "depois");
  // Os "Depois" de nota mais alta. Os outros não desaparecem: estão em Tudo,
  // a um toque. Esta página é curta de propósito.
  const depois = depoisTodos
    .slice()
    .sort((a, b) => Number(b.nota) - Number(a.nota) || ordenarPorDataENota(a, b))
    .slice(0, 8);

  const vista = el("div", "para-ti");

  const abertura = el("section", "abertura");
  const n = agora.length;
  const tituloAbertura = n === 0
    ? "Nada pede atenção agora."
    : `${n === 1 ? "Uma coisa pede" : `${n} coisas pedem`} atenção agora.`;
  abertura.append(el("h1", "abertura__titulo", tituloAbertura));
  abertura.append(el("p", "abertura__texto",
    `De ${julgados.length} itens julgados, estes são os que contam. O resto está em Tudo, com o porquê.`));
  vista.append(abertura);

  const blocoAgora = el("section", "bloco");
  blocoAgora.setAttribute("aria-labelledby", "titulo-agora");
  const tituloAgora = el("h2", "bloco__titulo");
  tituloAgora.id = "titulo-agora";
  tituloAgora.append(el("span", "", "Agora"));
  blocoAgora.append(tituloAgora);
  if (n === 0) {
    blocoAgora.append(estado("Hoje não houve nada que valha a pena.", "Volta amanhã, ou vê o que ficou para depois."));
  } else {
    const lista = el("ol");
    agora.forEach((item) => lista.append(criarEntrada(item)));
    blocoAgora.append(lista);
  }
  vista.append(blocoAgora);

  if (depois.length > 0) {
    const blocoDepois = el("section", "bloco bloco--lateral");
    blocoDepois.setAttribute("aria-labelledby", "titulo-depois");
    const tituloDepois = el("h2", "bloco__titulo");
    tituloDepois.id = "titulo-depois";
    tituloDepois.append(el("span", "", "Para depois"));
    const verTodos = el("a", "", `Ver os ${depoisTodos.length} ›`);
    verTodos.href = "#/tudo";
    verTodos.addEventListener("click", () => {
      estadoTudo.veredicto = "depois";
      estadoTudo.area = "todas";
      // O número do link conta os 60 dias, por isso Tudo abre com eles.
      estadoTudo.periodo = PERIODOS[PERIODOS.length - 1];
      estadoTudo.limite = POR_PAGINA;
      posicoes.tudo = 0;
    });
    tituloDepois.append(verTodos);
    blocoDepois.append(tituloDepois);
    const lista = el("ul");
    depois.forEach((item) => lista.append(criarLinha(item, true)));
    blocoDepois.append(lista);
    vista.append(blocoDepois);
  }

  const fim = el("p", "fim", "É tudo por hoje. ");
  const verTudo = el("a", "", "Ver todos os veredictos ›");
  verTudo.href = "#/tudo";
  verTudo.addEventListener("click", () => {
    estadoTudo.veredicto = "todos";
    estadoTudo.area = "todas";
    estadoTudo.limite = POR_PAGINA;
    posicoes.tudo = 0;
  });
  fim.append(verTudo);
  vista.append(fim);

  return vista;
}

// ——— Tudo ———

// Dentro do período escolhido. Um item sem data nenhuma fica: deitá-lo fora
// por uma falha do feed seria decidir com o que não se sabe.
function noPeriodo(item, dias = estadoTudo.periodo) {
  const data = lerData(idadeDe(item));
  return !data || diasAtras(data) < dias;
}

function itensDeTudo() {
  return itens.filter((item) => {
    if (!comVeredicto(item) || !noPeriodo(item)) return false;
    if (estadoTudo.veredicto !== "todos" && veredictoDe(item) !== estadoTudo.veredicto) return false;
    if (estadoTudo.area !== "todas" && String(item.area || "") !== estadoTudo.area) return false;
    return true;
  }).sort((a, b) => {
    if (estadoTudo.ordem === "nota") {
      return Number(b.nota ?? -1) - Number(a.nota ?? -1) || ordenarPorDataENota(a, b);
    }
    return ordenarPorDataENota(a, b);
  });
}

function contarPor(chave, lista) {
  const contas = new Map();
  lista.forEach((item) => {
    const valor = chave(item);
    contas.set(valor, (contas.get(valor) || 0) + 1);
  });
  return contas;
}

function redesenharTudo() {
  posicoes.tudo = window.scrollY;
  conteudo.replaceChildren(desenharTudo());
}

// Um selector com rótulo por cima, no formato dos outros. `aoMudar` recebe o
// valor novo; o redesenho e o foco tratam-se aqui, iguais para todos.
function criarSelector(rotulo, opcoes, valor, aoMudar) {
  const campo = el("label", "", rotulo);
  const select = el("select");
  opcoes.forEach(([valorOpcao, texto, desligada]) => {
    const opcao = new Option(texto, valorOpcao);
    opcao.disabled = Boolean(desligada);
    select.append(opcao);
  });
  select.value = String(valor);
  select.dataset.rotulo = rotulo;
  select.addEventListener("change", () => {
    aoMudar(select.value);
    estadoTudo.limite = POR_PAGINA;
    redesenharTudo();
    // O redesenho troca o select por um novo; o foco volta ao equivalente.
    document.querySelector(`.selectores select[data-rotulo="${rotulo}"]`)?.focus();
  });
  campo.append(select);
  return campo;
}

function desenharTudo() {
  const vista = el("div", "tudo");
  const resultado = itensDeTudo();

  const topo = el("div", "tudo__topo");
  topo.append(el("h1", "titulo-vista", "Tudo"));
  const contagem = el("p", "contagem", `${resultado.length} ${resultado.length === 1 ? "veredicto" : "veredictos"}`);
  contagem.setAttribute("aria-live", "polite");
  topo.append(contagem);
  vista.append(topo);

  const controlos = el("div", "controlos");

  // Os contadores dos botões respeitam o período e a área escolhidos, para o
  // número dizer o que se vai ver ao carregar.
  const julgados = itens.filter((item) => comVeredicto(item) && noPeriodo(item));
  const naArea = julgados.filter((item) => estadoTudo.area === "todas" || String(item.area || "") === estadoTudo.area);
  const porVeredicto = contarPor(veredictoDe, naArea);
  const segmentos = el("div", "segmentos");
  segmentos.setAttribute("role", "group");
  segmentos.setAttribute("aria-label", "Filtrar por veredicto");
  const opcoes = [["todos", "Todos"], ["agora", "Agora"], ["depois", "Depois"], ["ruido", "Ignora"], ["incerto", "Sem dados"]];
  opcoes.forEach(([valor, nome]) => {
    const total = valor === "todos" ? naArea.length : porVeredicto.get(valor) || 0;
    // "Sem dados" só aparece quando há algum: é o veredicto mais raro, e um
    // botão a zero todos os dias era ruído na barra.
    if (valor === "incerto" && total === 0 && estadoTudo.veredicto !== "incerto") return;
    const botao = el("button", "", nome);
    botao.type = "button";
    botao.setAttribute("aria-pressed", String(estadoTudo.veredicto === valor));
    botao.append(el("span", "conta", total));
    botao.addEventListener("click", () => {
      estadoTudo.veredicto = valor;
      estadoTudo.limite = POR_PAGINA;
      redesenharTudo();
      document.querySelector(`.segmentos button[aria-pressed="true"]`)?.focus();
    });
    segmentos.append(botao);
  });
  controlos.append(segmentos);

  const porArea = contarPor((item) => String(item.area || ""), julgados);
  const opcoesArea = [["todas", "Todas as áreas"]];
  AREAS.forEach(([slug, nome]) => {
    const total = porArea.get(slug) || 0;
    // Áreas antigas só aparecem se ainda houver itens com elas no histórico.
    if (total === 0 && (slug === "meu-stack" || slug === "carreira-junior")) return;
    opcoesArea.push([slug, `${nome} (${total})`, total === 0]);
  });

  const selectores = el("div", "selectores");
  selectores.append(
    criarSelector("Período", PERIODOS.map((dias) => [String(dias), `Últimos ${dias} dias`]), estadoTudo.periodo,
      (valor) => { estadoTudo.periodo = Number(valor); }),
    criarSelector("Ordenar", [["data", "Mais recentes"], ["nota", "Mais relevantes"]], estadoTudo.ordem,
      (valor) => { estadoTudo.ordem = valor; }),
    // A área vai em último porque é o mais largo: no telemóvel ocupa a linha
    // inteira por baixo dos outros dois, e os nomes não ficam cortados.
    criarSelector("Área", opcoesArea, estadoTudo.area,
      (valor) => { estadoTudo.area = valor; })
  );
  controlos.append(selectores);
  vista.append(controlos);

  if (resultado.length === 0) {
    const ultimo = PERIODOS[PERIODOS.length - 1];
    if (itens.length === 0) {
      vista.append(estado("Ainda não há itens.", "Espera pela próxima recolha diária e volta cá."));
    } else if (estadoTudo.periodo < ultimo) {
      vista.append(estado("Nada com estes filtros.", `Alarga o período até ${ultimo} dias, escolhe outra área ou carrega em Todos.`));
    } else {
      vista.append(estado("Nada com estes filtros.", "Escolhe outra área ou carrega em Todos."));
    }
  } else {
    // Por data, a lista parte-se por dias, como as edições de um jornal. Por
    // relevância não há dias: seria partir uma ordem que não é temporal.
    const visiveis = resultado.slice(0, estadoTudo.limite);
    let lista = null;
    let diaActual = null;
    visiveis.forEach((item) => {
      const dia = String(item.data || "");
      if (!lista || (estadoTudo.ordem === "data" && dia !== diaActual)) {
        if (estadoTudo.ordem === "data") vista.append(el("h2", "grupo-data", rotuloDia(dia)));
        lista = el("ul");
        vista.append(lista);
        diaActual = dia;
      }
      lista.append(criarLinha(item, false));
    });

    if (resultado.length > visiveis.length) {
      const mais = el("div", "mais");
      const botao = el("button", "botao", `Mostrar mais ${Math.min(POR_PAGINA, resultado.length - visiveis.length)}`);
      botao.type = "button";
      botao.addEventListener("click", () => {
        estadoTudo.limite += POR_PAGINA;
        redesenharTudo();
        window.scrollTo(0, posicoes.tudo);
      });
      mais.append(botao);
      vista.append(mais);
    }
  }

  vista.append(desenharIgnorados());
  return vista;
}

// ——— Ignorados ———

// A data da recolha mais recente que trouxe ignorados. É a ela que o contador
// se refere: "hoje" quando a recolha foi hoje, a data quando não foi — dizer
// "hoje: 0" num dia em que o Action não correu enganava.
function ultimaRecolha(lista) {
  return lista.reduce((ultima, item) => {
    const valor = String(item.recolhido || "");
    return valor > ultima ? valor : ultima;
  }, "");
}

function criarLinhaIgnorada(item) {
  const linha = el("li", "ignorada");
  const nota = el("p", "ignorada__nota", item.nota);
  nota.setAttribute("aria-label", `Nota ${item.nota} em 10`);
  const titulo = el("h3", "ignorada__titulo");
  titulo.append(ligacaoItem(item));
  linha.append(nota, titulo);
  if (item.justificacao) linha.append(el("p", "ignorada__texto", item.justificacao));
  const meta = linhaMeta(item);
  // Um 8 ignorado pede explicação: não foi o filtro, foi o limite do dia.
  if (item.ignorado) meta.append(el("span", "ignorada__razao", "Fora do limite do dia"));
  linha.append(meta);
  return linha;
}

function desenharListaIgnorados(caixa, lista) {
  const conteudoLista = el("div", "ignorados__corpo");
  conteudoLista.append(el("p", "ignorados__explicacao",
    `O que o filtro deixou cair nos últimos ${DIAS_IGNORADOS} dias, da nota mais alta para a mais baixa. ` +
    "Não é para ler todos os dias: serve para apanhar um bom que tenha escapado."));

  const visiveis = lista.slice(0, estadoTudo.limiteIgnorados);
  const ul = el("ul");
  visiveis.forEach((item) => ul.append(criarLinhaIgnorada(item)));
  conteudoLista.append(ul);

  if (lista.length > visiveis.length) {
    const mais = el("div", "mais");
    const botao = el("button", "botao", `Mostrar mais ${Math.min(POR_PAGINA, lista.length - visiveis.length)}`);
    botao.type = "button";
    botao.addEventListener("click", () => {
      estadoTudo.limiteIgnorados += POR_PAGINA;
      // Só a lista é redesenhada: a página não salta, e o foco fica no
      // primeiro item novo, que é onde o leitor ia continuar.
      const antes = visiveis.length;
      desenharListaIgnorados(caixa, lista);
      caixa.querySelectorAll(".ignorada .ligacao-item")[antes]?.focus();
    });
    mais.append(botao);
    conteudoLista.append(mais);
  }

  caixa.querySelector(".ignorados__corpo")?.remove();
  caixa.append(conteudoLista);
}

function desenharIgnorados() {
  // O pipeline já corta os ignorados aos 7 dias; o filtro aqui repete-o para
  // o site não depender disso — um itens.json antigo mostrava semanas deles.
  const lista = itens
    .filter((item) => ignorado(item) && noPeriodo(item, DIAS_IGNORADOS))
    .sort((a, b) => Number(b.nota) - Number(a.nota) || ordenarPorDataENota(a, b));

  // Um <details> nativo: abre e fecha com o teclado e o leitor de ecrã diz o
  // estado sem código nenhum. Fica fechado por omissão.
  const caixa = el("details", "ignorados");
  caixa.open = estadoTudo.ignoradosAbertos;

  const resumo = el("summary", "ignorados__resumo");
  resumo.append(el("span", "ignorados__titulo", "Ignorados"));
  const recolha = ultimaRecolha(lista);
  const doDia = lista.filter((item) => item.recolhido === recolha).length;
  const data = lerData(recolha);
  const quando = !data ? "" : diasAtras(data) <= 0 ? "hoje" : diasAtras(data) === 1 ? "ontem" : formatoCurto.format(data);
  resumo.append(el("span", "ignorados__conta", lista.length === 0
    ? "nenhum esta semana"
    : `${quando ? `${quando}: ` : ""}${doDia} ${doDia === 1 ? "ignorado" : "ignorados"} · ${lista.length} em ${DIAS_IGNORADOS} dias`));
  caixa.append(resumo);

  // A lista só se desenha ao abrir. Fechada, a secção é uma linha, e não há
  // razão para pôr centenas de itens na página de quem nunca a abre.
  if (caixa.open && lista.length) desenharListaIgnorados(caixa, lista);
  caixa.addEventListener("toggle", () => {
    estadoTudo.ignoradosAbertos = caixa.open;
    if (caixa.open && lista.length && !caixa.querySelector(".ignorados__corpo")) {
      desenharListaIgnorados(caixa, lista);
    }
  });

  return caixa;
}

// ——— Página do item ———

function valorFacto(valor) {
  const texto = String(valor);
  // As estrelas vêm como "148783"; com separador lê-se "148 783".
  return /^\d{4,}$/.test(texto) ? formatoNumero.format(Number(texto)) : texto;
}

function desenharItem(id) {
  const item = porId.get(id);
  const voltar = el("a", "voltar", ultimaLista === "tudo" ? "‹ Voltar a Tudo" : "‹ Voltar a Para ti");
  voltar.href = ultimaLista === "tudo" ? "#/tudo" : "#/";

  if (!item) {
    const vista = el("div", "artigo");
    vista.append(voltar, estado(
      "Este item já não está na recolha.",
      "O Sinal guarda 60 dias de histórico. Pode ter saído, ou o endereço estar errado.",
      ["Ver tudo o que entrou ›", "#/tudo"]
    ));
    return vista;
  }

  const v = veredictoDe(item);
  const artigo = el("article", "artigo");
  artigo.append(voltar);
  if (nomeArea(item.area)) artigo.append(el("p", "artigo__area", nomeArea(item.area)));
  // Um ignorado não leva o rótulo de veredicto: ninguém o julgou. O que tem é
  // a nota e a frase do filtro, e é isso que a página mostra.
  const deitadoFora = ignorado(item);
  artigo.append(deitadoFora ? el("p", "veredicto veredicto--ignorado", "Ignorado") : marcaVeredicto(item));
  const titulo = el("h1", "artigo__titulo", nomeDe(item));
  titulo.id = `titulo-${idSeguro(item.id)}`;
  artigo.append(titulo);
  if (item.o_que_e) artigo.append(el("p", "artigo__subtitulo", item.o_que_e));

  const meta = linhaMeta(item);
  if (avaliado(item)) meta.append(el("span", "", `Nota ${item.nota}/10`));
  artigo.append(meta);

  if (deitadoFora) {
    artigo.append(el("p", "artigo__razao", item.ignorado
      ? `Teve nota para passar, mas ${String(item.ignorado)}. Não foi verificado nem julgado.`
      : `O filtro deu-lhe ${item.nota}, abaixo dos ${LIMIAR} que levam à verificação. Não foi verificado nem julgado.`));
  }

  if (item.acao && !deitadoFora) {
    const acao = el("p", "artigo__acao");
    acao.append(el("span", "", "O que fazer"), document.createTextNode(String(item.acao)));
    artigo.append(acao);
  }

  if (!avaliado(item)) {
    const parte = el("section", "parte");
    parte.append(el("h2", "parte__titulo", "Ainda não avaliado"));
    parte.append(el("p", "parte__texto",
      "Este item entrou na recolha mas ainda não passou pelo filtro. Não há veredicto nem factos — só o que a fonte disse."));
    if (item.resumo) parte.append(el("p", "parte__nota parte__nota--original", item.resumo));
    artigo.append(parte);
  }

  // Os factos vêm antes do porquê: são o que não se discute, e o porquê
  // assenta neles. Num ignorado não há factos, e a razão já está escrita.
  if (avaliado(item) && !deitadoFora) {
    const parte = el("section", "parte");
    parte.append(el("h2", "parte__titulo", "Factos verificados"));
    const factos = Array.isArray(item.factos)
      ? item.factos.filter((f) => f && f.rotulo !== undefined && f.valor !== undefined)
      : [];
    if (factos.length > 0) {
      const ficha = el("dl", "ficha");
      factos.forEach((facto) => {
        const grupo = el("div");
        grupo.append(el("dt", "", facto.rotulo), el("dd", "", valorFacto(facto.valor)));
        ficha.append(grupo);
      });
      parte.append(ficha);
      const verificado = lerData(item.verificado);
      if (verificado) parte.append(el("p", "parte__nota", `Verificado a ${formatoCurto.format(verificado)}.`));
    } else {
      // Dizer que não houve verificação é diferente de não dizer nada: sem
      // esta frase, a falta de factos parecia um esquecimento do site.
      parte.append(el("p", "parte__nota", "A verificação não confirmou nada. O que ficou por saber está nas dúvidas."));
    }
    artigo.append(parte);
  }

  if (item.justificacao) {
    const parte = el("section", "parte");
    const tituloPorque = deitadoFora ? "O que o filtro disse" : v === "ruido" ? "Porque não te serve" : "Porquê";
    parte.append(el("h2", "parte__titulo", tituloPorque));
    parte.append(el("p", "parte__texto", item.justificacao));
    artigo.append(parte);
  }

  if (Array.isArray(item.duvidas) && item.duvidas.length > 0) {
    const parte = el("section", "parte");
    parte.append(el("h2", "parte__titulo", "Dúvidas em aberto"));
    const lista = el("ul", "duvidas");
    item.duvidas.forEach((duvida) => lista.append(el("li", "", duvida)));
    parte.append(lista);
    artigo.append(parte);
  }

  if (item.nome && item.titulo && item.nome !== item.titulo) {
    const parte = el("section", "parte");
    parte.append(el("h2", "parte__titulo", "Título original"));
    parte.append(el("p", "parte__nota parte__nota--original", item.titulo));
    artigo.append(parte);
  }

  const endereco = urlSegura(item.url);
  if (endereco) {
    const fonte = el("a", "botao artigo__fonte", "Ler na fonte original ↗");
    fonte.href = endereco;
    fonte.target = "_blank";
    fonte.rel = "noopener";
    artigo.append(fonte);
  }

  return artigo;
}

// ——— Navegação ———

function lerRota() {
  const caminho = location.hash.replace(/^#\/?/, "");
  if (caminho.startsWith("item/")) return { vista: "item", id: decodeURIComponent(caminho.slice(5)) };
  if (caminho === "tudo") return { vista: "tudo" };
  return { vista: "para-ti" };
}

function desenhar() {
  const rota = lerRota();

  if (vistaActual === "para-ti" || vistaActual === "tudo") posicoes[vistaActual] = window.scrollY;
  if (rota.vista !== "item") ultimaLista = rota.vista;

  document.querySelectorAll(".seccoes a").forEach((ligacao) => {
    const activa = ligacao.dataset.vista === (rota.vista === "item" ? ultimaLista : rota.vista);
    if (activa) ligacao.setAttribute("aria-current", "page");
    else ligacao.removeAttribute("aria-current");
  });

  if (erroCarga) {
    conteudo.replaceChildren(estado(
      "Não foi possível ler a recolha.",
      `O ficheiro dados/itens.json não chegou (${erroCarga}). Se estás sem rede, tenta outra vez quando voltares a ter. Se não, confirma que o pipeline correu.`,
      ["Tentar outra vez", location.hash || "#/"],
      true
    ));
    conteudo.querySelector(".estado a")?.addEventListener("click", (evento) => {
      evento.preventDefault();
      carregar();
    });
    vistaActual = rota.vista;
    return;
  }

  if (rota.vista === "item") {
    conteudo.replaceChildren(desenharItem(rota.id));
    document.title = `${porId.get(rota.id) ? nomeDe(porId.get(rota.id)) : "Item"} — Sinal`;
    window.scrollTo(0, 0);
  } else {
    conteudo.replaceChildren(rota.vista === "tudo" ? desenharTudo() : desenharParaTi());
    document.title = rota.vista === "tudo" ? "Tudo — Sinal" : "Sinal";
    window.scrollTo(0, posicoes[rota.vista] || 0);
  }

  // O foco passa para o conteúdo novo, para quem usa teclado ou leitor de
  // ecrã não ficar preso no link em que carregou, que já não existe.
  if (vistaActual !== null) conteudo.focus({ preventScroll: true });
  vistaActual = rota.vista;
}

function actualizarCabecalho() {
  const recolhas = itens.map((item) => lerData(item.recolhido || item.data)).filter(Boolean);
  if (recolhas.length === 0) {
    dataRecolha.textContent = "";
    return;
  }
  const ultima = new Date(Math.max(...recolhas.map((data) => data.getTime())));
  const dias = diasAtras(ultima);
  const quando = dias <= 0 ? "hoje" : dias === 1 ? "ontem" : `a ${formatoCurto.format(ultima)}`;
  dataRecolha.textContent = `Recolhido ${quando}`;
}

// ——— Tema ———

function temaEscuro() {
  const escolha = document.documentElement.dataset.tema;
  if (escolha) return escolha === "escuro";
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function actualizarTema() {
  const escuro = temaEscuro();
  botaoTema.textContent = escuro ? "Claro" : "Escuro";
  botaoTema.setAttribute("aria-label", escuro ? "Usar tema claro" : "Usar tema escuro");
  document.querySelector('meta[name="theme-color"]').setAttribute("content", escuro ? "#151412" : "#f7f4ee");
}

function iniciarTema() {
  actualizarTema();
  botaoTema.addEventListener("click", () => {
    const novo = temaEscuro() ? "claro" : "escuro";
    document.documentElement.dataset.tema = novo;
    try {
      localStorage.setItem("sinal-tema", novo);
    } catch {
      // Em navegação privada o Safari recusa guardar; o tema muda na mesma,
      // só não fica lembrado para a próxima visita.
    }
    actualizarTema();
  });
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (!document.documentElement.dataset.tema) actualizarTema();
  });
}

// ——— Notificações ———

// A metade pública do par VAPID. Não é segredo: serve só para o serviço de
// push do browser confirmar que quem manda é o Sinal, que assina com a metade
// privada guardada no Secret VAPID_CHAVE_PRIVADA. As duas têm de ser do mesmo
// par; foram geradas com `python pipeline/notificar.py --gerar-chaves`.
const CHAVE_PUBLICA_PUSH = "BNx0u-jUaO08_JWkupXg9RaJd5QAVaQfaEsb9R93THSmenpWvATJaGyguxYWXVH2XecePbqiIg358eCGsT88y-Y";

const avisos = {
  caixa: document.querySelector("#avisos"),
  estado: document.querySelector("#avisos-estado"),
  ligar: document.querySelector("#avisos-ligar"),
  desligar: document.querySelector("#avisos-desligar"),
  subscricao: document.querySelector("#avisos-subscricao"),
  codigo: document.querySelector("#avisos-codigo"),
  copiar: document.querySelector("#avisos-copiar")
};

// O browser quer a chave em bytes; ela está escrita em base64 de URL, sem o
// "=" do fim, que é como a norma a passa de um lado para o outro.
function chaveEmBytes(texto) {
  const base64 = (texto + "=".repeat((4 - (texto.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(base64), (letra) => letra.charCodeAt(0));
}

function mostrarAvisos(texto, subscricao) {
  avisos.estado.textContent = texto;
  avisos.ligar.hidden = Boolean(subscricao) || Notification.permission === "denied";
  avisos.desligar.hidden = !subscricao;
  avisos.subscricao.hidden = !subscricao;
  // Uma linha só, sem espaços: é o formato que o notificar.py lê, uma
  // subscrição por linha, e cola-se no Secret sem arrumar nada.
  avisos.codigo.value = subscricao ? JSON.stringify(subscricao) : "";
}

async function iniciarAvisos() {
  avisos.caixa.hidden = false;

  const suporta = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  if (!suporta) {
    // O iPhone só dá push a sites instalados no ecrã principal. Fora disso
    // nem sequer expõe o PushManager, e a mensagem genérica não ajudava.
    const iphone = /iPhone|iPad|iPod/.test(navigator.userAgent);
    avisos.estado.textContent = iphone
      ? "No iPhone, as notificações só funcionam com o Sinal no ecrã principal: Partilhar › Adicionar ao ecrã principal, e abre-o de lá."
      : "Este browser não suporta notificações.";
    return;
  }

  // O `ready` nunca resolve se o service worker não se instalar, e o texto
  // fica este. Melhor do que uma caixa vazia sem explicação.
  avisos.estado.textContent = "A verificar se as notificações estão ativas…";
  let registo;
  try {
    registo = await navigator.serviceWorker.ready;
  } catch {
    avisos.estado.textContent = "As notificações precisam do service worker, que não arrancou.";
    return;
  }

  const actual = await registo.pushManager.getSubscription();
  if (actual) {
    mostrarAvisos("Ativas neste aparelho. Recebes um resumo quando há coisas novas Para ti.", actual);
  } else if (Notification.permission === "denied") {
    mostrarAvisos("Bloqueaste as notificações para este site. Para as receberes, liga-as nas definições do browser.", null);
  } else {
    mostrarAvisos("Recebe um resumo no telemóvel ou no PC quando há coisas novas Para ti. Uma vez por dia, no máximo.", null);
  }

  avisos.ligar.addEventListener("click", async () => {
    avisos.ligar.disabled = true;
    try {
      // Pedir a permissão só aqui, e não ao abrir a página: o browser só a
      // pede uma vez, e um "não" dado sem contexto fica para sempre.
      const permissao = await Notification.requestPermission();
      if (permissao !== "granted") {
        mostrarAvisos(permissao === "denied"
          ? "Bloqueaste as notificações para este site. Para as receberes, liga-as nas definições do browser."
          : "Ficou por decidir. Carrega outra vez quando quiseres.", null);
        return;
      }
      const subscricao = await registo.pushManager.subscribe({
        // O Chrome exige que cada push mostre uma notificação visível. É a
        // garantia de que o site não usa o push para correr às escondidas.
        userVisibleOnly: true,
        applicationServerKey: chaveEmBytes(CHAVE_PUBLICA_PUSH)
      });
      mostrarAvisos("Ativas neste aparelho. Falta só colar a linha abaixo no GitHub.", subscricao);
      avisos.codigo.focus();
      avisos.codigo.select();
    } catch (erro) {
      mostrarAvisos(`Não foi possível ativar: ${erro.message}`, null);
    } finally {
      avisos.ligar.disabled = false;
    }
  });

  avisos.desligar.addEventListener("click", async () => {
    const subscricao = await registo.pushManager.getSubscription();
    if (subscricao) await subscricao.unsubscribe();
    mostrarAvisos("Desativadas neste aparelho. Tira a linha dele do Secret PUSH_SUBSCRICOES para o pipeline deixar de tentar.", null);
    avisos.ligar.focus();
  });

  avisos.copiar.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(avisos.codigo.value);
      avisos.copiar.textContent = "Copiado";
    } catch {
      // Sem acesso à área de transferência, deixa o texto seleccionado para
      // se copiar à mão.
      avisos.codigo.focus();
      avisos.codigo.select();
      avisos.copiar.textContent = "Selecionado, copia à mão";
    }
    setTimeout(() => { avisos.copiar.textContent = "Copiar"; }, 2500);
  });
}

// ——— Arranque ———

async function carregar() {
  try {
    const resposta = await fetch("dados/itens.json", { cache: "no-store" });
    if (!resposta.ok) throw new Error(`resposta ${resposta.status}`);
    const dados = await resposta.json();
    if (!Array.isArray(dados)) throw new Error("formato inválido");
    itens = dados.filter((item) => item && item.id !== undefined);
    porId = new Map(itens.map((item) => [String(item.id), item]));
    erroCarga = null;
  } catch (erro) {
    // Nunca se inventa conteúdo. Se o ficheiro não carrega, o site diz isso
    // em vez de mostrar uma lista vazia que parecia um dia sem notícias.
    itens = [];
    porId = new Map();
    erroCarga = erro.message;
  }
  actualizarCabecalho();
  desenhar();
}

if ("scrollRestoration" in history) history.scrollRestoration = "manual";

window.addEventListener("hashchange", desenhar);
iniciarTema();
carregar();

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("./sw.js").catch(() => {
      // A cache offline é um extra: sem ela o site funciona igual com rede.
    });
  });
}
iniciarAvisos();
