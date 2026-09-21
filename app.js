"use strict";

const nomesVeredictos = {
  agora: "Agora",
  depois: "Depois",
  ruido: "Ruído",
  incerto: "Incerto"
};

const descricoesCamadas = {
  1: "Fonte oficial ou facto verificado",
  2: "Descoberta ou boato com tração",
  3: "Oportunidade para estudante",
  4: "Contexto"
};

let itens = [];
const filtrosActivos = {
  veredictos: new Set(),
  temas: new Set()
};

const elementoLista = document.querySelector("#lista-itens");
const elementoEstado = document.querySelector("#estado");
const elementoAviso = document.querySelector("#aviso-erro");
const elementoResumo = document.querySelector("#resumo-recolha");
const elementoContagem = document.querySelector("#contagem-resultados");
const selectorOrdenacao = document.querySelector("#ordenar");
const elementoFiltrosVeredicto = document.querySelector("#filtros-veredicto");
const elementoFiltrosTema = document.querySelector("#filtros-tema");
const botaoLimpar = document.querySelector("#limpar-filtros");
const botaoTema = document.querySelector("#alternar-tema");
const textoTema = document.querySelector("#texto-tema");

function criarElemento(nome, classe, texto) {
  const elemento = document.createElement(nome);
  if (classe) elemento.className = classe;
  if (texto !== undefined) elemento.textContent = texto;
  return elemento;
}

function dataValida(valor) {
  const data = new Date(`${valor}T00:00:00`);
  return Number.isNaN(data.getTime()) ? null : data;
}

function formatarData(valor) {
  const data = dataValida(valor);
  if (!data) return "Data desconhecida";
  return new Intl.DateTimeFormat("pt-PT", {
    day: "2-digit",
    month: "short",
    year: "numeric"
  }).format(data);
}

// O nome que a fase 2 escreveu ganha ao título do feed. O título cru é quase
// sempre inglês, e em repositórios é o slug `utilizador/projeto`, que não diz
// nada a quem está a ler. Quando não há nome — item por pontuar — mostra-se o
// título, porque mostrar um cartão sem cabeçalho era pior.
function nomeVisivel(item) {
  return String(item.nome || item.titulo || "Sem título");
}

function criarLigacaoSegura(item) {
  const titulo = criarElemento("h3", "titulo-item");
  try {
    const endereco = new URL(String(item.url));
    if (endereco.protocol !== "https:" && endereco.protocol !== "http:") throw new Error("Protocolo não permitido");
    const ligacao = criarElemento("a", "", nomeVisivel(item));
    ligacao.href = endereco.href;
    ligacao.target = "_blank";
    ligacao.rel = "noopener";
    // O título original não se perde: fica no tooltip, para se poder confirmar
    // que o nome corresponde mesmo ao que a fonte publicou.
    if (item.nome && item.titulo) ligacao.title = String(item.titulo);
    titulo.append(ligacao);
  } catch {
    titulo.textContent = nomeVisivel(item);
  }
  return titulo;
}

function criarCartao(item) {
  const veredicto = nomesVeredictos[item.veredicto] ? item.veredicto : "incerto";
  const cartao = criarElemento("article", `cartao cartao--${veredicto}`);
  cartao.setAttribute("aria-labelledby", `titulo-${String(item.id)}`);

  const marca = criarElemento("p", `veredicto veredicto--${veredicto}`, nomesVeredictos[veredicto]);
  const titulo = criarLigacaoSegura(item);
  titulo.id = `titulo-${String(item.id)}`;
  cartao.append(marca, titulo);

  // A linha do que a coisa é, em português, escrita pela fase 2. Substitui o
  // resumo do feed em vez de se juntar a ele: dizem a mesma coisa em línguas
  // diferentes, e o resumo do feed às vezes é lixo puro ("submitted by /u/...").
  // Sem nota ainda não há esta linha, e aí vale o resumo cru — é o que há.
  const descricao = item.o_que_e || item.resumo;
  if (descricao) cartao.append(criarElemento("p", "resumo-item", String(descricao)));

  if (Array.isArray(item.factos) && item.factos.length > 0) {
    const listaFactos = criarElemento("dl", "factos");
    item.factos.forEach((facto) => {
      if (!facto || facto.rotulo === undefined || facto.valor === undefined) return;
      const grupo = criarElemento("div", "facto");
      grupo.append(
        criarElemento("dt", "", `${String(facto.rotulo)}:`),
        criarElemento("dd", "", String(facto.valor))
      );
      listaFactos.append(grupo);
    });
    if (listaFactos.children.length > 0) cartao.append(listaFactos);
  }

  if (item.justificacao) cartao.append(criarElemento("p", "justificacao", String(item.justificacao)));

  if (Array.isArray(item.duvidas) && item.duvidas.length > 0) {
    const listaDuvidas = criarElemento("ul", "duvidas");
    item.duvidas.forEach((duvida) => {
      listaDuvidas.append(criarElemento("li", "", String(duvida)));
    });
    cartao.append(listaDuvidas);
  }

  const rodape = criarElemento("footer", "rodape-cartao");
  rodape.append(
    criarElemento("span", "", String(item.fonte || "Fonte desconhecida")),
    criarElemento("time", "separador", formatarData(item.data))
  );
  rodape.querySelector("time").dateTime = String(item.data || "");

  const camada = [1, 2, 3, 4].includes(Number(item.camada)) ? Number(item.camada) : 4;
  const descricaoCamada = descricoesCamadas[camada];
  const indicador = criarElemento("span", "indicador-camada separador");
  indicador.title = descricaoCamada;
  const ponto = criarElemento("span", `ponto-camada ponto-camada--${camada}`);
  ponto.setAttribute("aria-hidden", "true");
  indicador.append(ponto, criarElemento("span", "so-leitores", `Camada ${camada}: ${descricaoCamada}`));
  rodape.append(indicador);
  cartao.append(rodape);
  return cartao;
}

function mostrarEstado(titulo, mensagem) {
  elementoLista.hidden = true;
  elementoEstado.hidden = false;
  elementoEstado.replaceChildren(
    criarElemento("p", "estado__titulo", titulo),
    criarElemento("p", "", mensagem)
  );
}

function filtrarEOrdenar() {
  const resultado = itens.filter((item) => {
    const passaVeredicto = filtrosActivos.veredictos.size === 0 || filtrosActivos.veredictos.has(item.veredicto);
    const temasDoItem = Array.isArray(item.temas) ? item.temas.map(String) : [];
    const passaTema = filtrosActivos.temas.size === 0 || temasDoItem.some((tema) => filtrosActivos.temas.has(tema));
    return passaVeredicto && passaTema;
  });

  resultado.sort((primeiro, segundo) => {
    if (selectorOrdenacao.value === "data") {
      return String(segundo.data || "").localeCompare(String(primeiro.data || ""));
    }
    const diferencaNota = Number(segundo.nota || 0) - Number(primeiro.nota || 0);
    return diferencaNota || String(segundo.data || "").localeCompare(String(primeiro.data || ""));
  });
  return resultado;
}

function apresentarItens() {
  const resultado = filtrarEOrdenar();
  const haFiltros = filtrosActivos.veredictos.size > 0 || filtrosActivos.temas.size > 0;
  botaoLimpar.disabled = !haFiltros;
  elementoContagem.textContent = `${resultado.length} ${resultado.length === 1 ? "resultado" : "resultados"}`;

  if (resultado.length === 0) {
    const titulo = itens.length === 0 ? "Ainda não há itens." : "Nenhum item passou estes filtros.";
    const mensagem = itens.length === 0
      ? "Espera pela próxima recolha e volta a consultar o painel."
      : "Limpa os filtros ou escolhe menos opções para voltar a ver resultados.";
    mostrarEstado(titulo, mensagem);
    return;
  }

  const fragmento = document.createDocumentFragment();
  resultado.forEach((item) => fragmento.append(criarCartao(item)));
  elementoLista.replaceChildren(fragmento);
  elementoEstado.hidden = true;
  elementoLista.hidden = false;
}

function criarBotaoFiltro(texto, valor, tipo) {
  const botao = criarElemento("button", "filtro", texto);
  botao.type = "button";
  botao.setAttribute("aria-pressed", "false");
  botao.addEventListener("click", () => {
    const conjunto = filtrosActivos[tipo];
    if (conjunto.has(valor)) conjunto.delete(valor);
    else conjunto.add(valor);
    botao.setAttribute("aria-pressed", String(conjunto.has(valor)));
    apresentarItens();
  });
  return botao;
}

function prepararFiltros() {
  Object.entries(nomesVeredictos).forEach(([valor, nome]) => {
    elementoFiltrosVeredicto.append(criarBotaoFiltro(nome, valor, "veredictos"));
  });

  const temas = [...new Set(itens.flatMap((item) => Array.isArray(item.temas) ? item.temas.map(String) : []))]
    .sort((a, b) => a.localeCompare(b, "pt"));
  temas.forEach((tema) => elementoFiltrosTema.append(criarBotaoFiltro(tema, tema, "temas")));
}

function actualizarResumo() {
  const datas = itens.map((item) => dataValida(item.data)).filter(Boolean);
  const ultimaData = datas.length > 0 ? new Date(Math.max(...datas.map((data) => data.getTime()))) : null;
  const quantidade = `${itens.length} ${itens.length === 1 ? "item" : "itens"}`;
  elementoResumo.textContent = ultimaData
    ? `${quantidade} · última recolha a ${new Intl.DateTimeFormat("pt-PT", { day: "2-digit", month: "long", year: "numeric" }).format(ultimaData)}`
    : `${quantidade} · sem data de recolha`;
}

function temaEscuroActivo() {
  const escolha = document.documentElement.dataset.tema;
  if (escolha) return escolha === "escuro";
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function actualizarBotaoTema() {
  const escuro = temaEscuroActivo();
  textoTema.textContent = escuro ? "Tema claro" : "Tema escuro";
  botaoTema.setAttribute("aria-label", escuro ? "Usar tema claro" : "Usar tema escuro");
}

function iniciarTema() {
  const escolhaGuardada = localStorage.getItem("sinal-tema");
  if (escolhaGuardada === "claro" || escolhaGuardada === "escuro") {
    document.documentElement.dataset.tema = escolhaGuardada;
  }
  actualizarBotaoTema();

  botaoTema.addEventListener("click", () => {
    const novoTema = temaEscuroActivo() ? "claro" : "escuro";
    document.documentElement.dataset.tema = novoTema;
    localStorage.setItem("sinal-tema", novoTema);
    actualizarBotaoTema();
  });

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (!document.documentElement.dataset.tema) actualizarBotaoTema();
  });
}

async function carregarItens() {
  try {
    const resposta = await fetch("dados/itens.json", { cache: "no-store" });
    if (!resposta.ok) throw new Error(`Resposta ${resposta.status}`);
    const dados = await resposta.json();
    if (!Array.isArray(dados)) throw new Error("Formato inválido");
    itens = dados;
  } catch (erro) {
    // Nunca se inventa conteúdo. Se o ficheiro não carrega, o painel fica
    // vazio e diz porquê — um veredicto falso é pior do que nenhum.
    itens = [];
    elementoAviso.textContent = `Não foi possível carregar dados/itens.json (${erro.message}).`;
    elementoAviso.hidden = false;
    elementoResumo.textContent = "Sem recolha disponível";
    elementoContagem.textContent = "";
    mostrarEstado(
      "Não há dados para mostrar.",
      "A última recolha não chegou ao site. Confirma que o pipeline correu e que o ficheiro dados/itens.json existe."
    );
    return;
  }

  actualizarResumo();
  prepararFiltros();
  apresentarItens();
}

selectorOrdenacao.addEventListener("change", apresentarItens);
botaoLimpar.addEventListener("click", () => {
  filtrosActivos.veredictos.clear();
  filtrosActivos.temas.clear();
  document.querySelectorAll(".filtro").forEach((botao) => botao.setAttribute("aria-pressed", "false"));
  apresentarItens();
});

iniciarTema();
carregarItens();
