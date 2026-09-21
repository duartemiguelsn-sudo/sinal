"""Fase 1 do Sinal: ler os feeds das fontes e normalizar tudo para a mesma forma.

Só usa a biblioteca padrão do Python. A razão não é purismo: cada dependência
é mais uma coisa a instalar, a manter e a explicar. RSS e Atom são XML, e o
`xml.etree` que vem com o Python chega perfeitamente para os ler.

Nem todas as fontes dão feed. O Hacker News e a pesquisa do GitHub só têm API
JSON, e são precisamente as que trazem a camada 2. Por isso cada fonte declara
um `tipo` no fontes.toml, e há um interpretador por tipo. O resultado é sempre
o mesmo dicionário — quem consome não precisa de saber de onde veio.

Há um tipo que foge à regra: `pagina`. Uma página de ofertas não tem entradas
nem datas — é uma lista que hoje está assim e amanhã está de outra maneira. A
única notícia que dela se tira é a diferença para a corrida anterior, e por isso
é o único interpretador com memória. O retrato entra e sai por parâmetro; quem
escreve o ficheiro é o `principal.py`, para esta fase continuar a não tocar no
disco.

Nada aqui julga nada. Esta fase só recolhe. O julgamento vem nas fases 2 a 4.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

# O Atom mete tudo dentro de um espaço de nomes; o RSS 2.0 não usa nenhum.
# Por isso quase todas as procuras abaixo são feitas duas vezes.
ATOM = "{http://www.w3.org/2005/Atom}"

# Identificamo-nos. Alguns servidores recusam pedidos sem User-Agent, e é
# elementar dizer quem está a bater à porta.
AGENTE = "Sinal/0.1 (recolha pessoal de feeds)"

TEMPO_LIMITE = 20  # segundos por fonte; um servidor lento não pode prender a recolha
LIMITE_RESUMO = 400  # caracteres; a fase 2 paga por token, e o resumo inteiro não acrescenta

# Teto por fonte, se a própria fonte não declarar um. Existe por uma razão só:
# a fase 2 é paga ao item. Uma fonte que um dia devolva mil resultados não pode
# arrastar a fatura atrás dela sem ninguém dar por isso.
LIMITE_POR_FONTE = 60

TIPOS = ("rss", "hn", "github", "pagina")

# Marcadores do cartão de parceiro na página de ofertas do Student Pack. São
# frágeis de propósito: dependem do HTML do GitHub, que muda sem avisar. É por
# isso que existe o MINIMO_DE_PARCEIROS — mais vale a fonte dizer que se partiu
# do que anunciar que desapareceram oitenta ofertas.
PARCEIRO = re.compile(r'<h3 id="([^"]+)" class="sr-only">([^<]*)</h3>(.*?)(?=<h3 id="|\Z)', re.S)
OFERTA = re.compile(r"<h5[^>]*>Offer(?: #\d+)?</h5>\s*<p[^>]*>(.*?)</p>", re.S)

# A página tinha 83 parceiros a 2026-09-21. Abaixo deste número assume-se que o
# template mudou e não se compara nada — comparar dava um falso alarme enorme.
MINIMO_DE_PARCEIROS = 40

# Pausa entre dois pedidos ao mesmo servidor. A pesquisa do GitHub aceita 10
# pedidos por minuto sem autenticação e devolve 403 a quem dispara quatro
# seguidos — foi o que aconteceu no primeiro teste desta fase. Seis segundos
# respeitam o limite e não custam nada numa corrida que é diária.
PAUSA_ENTRE_PEDIDOS = 6


class ErroDeFonte(Exception):
    """Uma fonte falhou. Quem chama decide se salta ou se pára — aqui só se assinala."""


def ler_fontes(caminho: Path) -> list[dict]:
    """Lê o fontes.toml. Fica num ficheiro à parte para se poder acrescentar
    uma fonte sem tocar em código."""
    with caminho.open("rb") as ficheiro:
        conteudo = tomllib.load(ficheiro)

    fontes = conteudo.get("fonte", [])
    if not fontes:
        raise ErroDeFonte(f"{caminho} não tem nenhuma fonte definida.")

    for fonte in fontes:
        for campo in ("nome", "url", "camada"):
            if campo not in fonte:
                raise ErroDeFonte(f"A fonte {fonte!r} não tem o campo obrigatório '{campo}'.")
        tipo = fonte.get("tipo", "rss")
        if tipo not in TIPOS:
            raise ErroDeFonte(
                f"A fonte {fonte['nome']!r} declara tipo {tipo!r}, que não existe. Usa um de: {', '.join(TIPOS)}."
            )
    return fontes


def cabecalhos(url: str) -> dict[str, str]:
    """Cabeçalhos do pedido.

    O GITHUB_TOKEN é opcional e nunca obrigatório: sem ele a recolha funciona,
    só com um limite de pedidos mais apertado. Dentro do GitHub Action existe
    um de borla, e aí a pesquisa passa de 10 para 30 pedidos por minuto. Como
    qualquer segredo, vive só no ambiente — nunca no repositório.
    """
    cabecalhos = {"User-Agent": AGENTE}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token and urllib.parse.urlparse(url).hostname == "api.github.com":
        cabecalhos["Authorization"] = f"Bearer {token}"
    return cabecalhos


def descarregar(url: str) -> bytes:
    """Vai buscar o feed. Devolve os bytes crus para o interpretador de XML
    poder usar a codificação declarada no próprio ficheiro."""
    pedido = urllib.request.Request(url, headers=cabecalhos(url))
    try:
        with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:
            return resposta.read()
    except urllib.error.HTTPError as erro:
        raise ErroDeFonte(f"HTTP {erro.code}") from erro
    except Exception as erro:  # rede em baixo, DNS, TLS, tempo esgotado
        raise ErroDeFonte(f"{type(erro).__name__}: {erro}") from erro


def _primeiro_texto(elemento: ET.Element, *nomes: str) -> str:
    """Devolve o texto da primeira etiqueta que existir, testando com e sem
    o espaço de nomes do Atom."""
    for nome in nomes:
        for caminho in (nome, f"{ATOM}{nome}"):
            encontrado = elemento.find(caminho)
            if encontrado is not None and encontrado.text:
                return encontrado.text.strip()
    return ""


def _ligacao(elemento: ET.Element) -> str:
    """O RSS mete o endereço no texto de <link>. O Atom mete-o no atributo
    href, e pode ter vários — queremos o 'alternate', que é a página em si."""
    ligacao_rss = elemento.find("link")
    if ligacao_rss is not None and ligacao_rss.text:
        return ligacao_rss.text.strip()

    alternativas = elemento.findall(f"{ATOM}link")
    for ligacao in alternativas:
        if ligacao.get("rel", "alternate") == "alternate" and ligacao.get("href"):
            return ligacao.get("href", "").strip()
    return alternativas[0].get("href", "").strip() if alternativas else ""


def limpar_texto(bruto: str) -> str:
    """Tira as etiquetas HTML, desfaz as entidades e encolhe os espaços.

    Isto é higiene, não segurança: o site já insere tudo com textContent. Serve
    para o resumo ser legível e para não pagarmos tokens por marcação na fase 2.
    """
    sem_etiquetas = re.sub(r"<[^>]+>", " ", bruto)
    texto = html.unescape(sem_etiquetas)
    texto = re.sub(r"\s+", " ", texto).strip()
    if len(texto) > LIMITE_RESUMO:
        texto = texto[:LIMITE_RESUMO].rstrip() + "…"
    return texto


def data_em_iso(bruto: str) -> str:
    """Normaliza a data para AAAA-MM-DD.

    O RSS usa o formato dos emails ('Mon, 18 Sep 2026 10:00:00 GMT') e o Atom
    usa ISO 8601. Aceitamos os dois e devolvemos sempre o mesmo, porque o site
    ordena por este campo como texto e só funciona se todos tiverem a mesma forma.
    """
    bruto = bruto.strip()
    if not bruto:
        return ""

    for interpretar in (parsedate_to_datetime, datetime.fromisoformat):
        try:
            data = interpretar(bruto.replace("Z", "+00:00"))
            if data.tzinfo is not None:
                data = data.astimezone(timezone.utc)
            return data.date().isoformat()
        except (TypeError, ValueError):
            continue
    return ""


def identificador(url: str) -> str:
    """Um id estável a partir do endereço.

    Os feeds inventam ids em formatos diferentes e alguns mudam-nos entre
    recolhas. O endereço é o que não muda, por isso é dele que sai o id — assim
    o vistos.json reconhece o mesmo item amanhã.
    """
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def itens_do_feed(xml_bruto: bytes, fonte: dict) -> list[dict]:
    """Transforma um feed inteiro na lista de itens normalizados do Sinal."""
    raiz = ET.fromstring(xml_bruto)

    # RSS: <rss><channel><item>. Atom: <feed><entry>.
    entradas = raiz.findall(".//item") + raiz.findall(f".//{ATOM}entry")

    itens = []
    for entrada in entradas:
        url = _ligacao(entrada)
        titulo = _primeiro_texto(entrada, "title")
        if not url or not titulo:
            continue  # sem endereço ou sem título não há item que valha a pena

        resumo_bruto = _primeiro_texto(entrada, "description", "summary", "content")
        data_bruta = _primeiro_texto(entrada, "pubDate", "published", "updated")

        itens.append({
            "id": identificador(url),
            "titulo": limpar_texto(titulo),
            "resumo": limpar_texto(resumo_bruto),
            "url": url,
            "fonte": fonte["nome"],
            "camada": int(fonte["camada"]),
            "data": data_em_iso(data_bruta),
        })
    return itens


def itens_do_hn(json_bruto: bytes, fonte: dict) -> list[dict]:
    """Interpreta a resposta da API de pesquisa do Hacker News (Algolia).

    Camada 2: isto é sinal de atenção, não é verdade. Uma história com muitos
    pontos só quer dizer que muita gente carregou no botão — o que ela vale
    decide-se na fase 3, com factos, e nunca aqui.
    """
    resposta = json.loads(json_bruto)

    itens = []
    for historia in resposta.get("hits", []):
        titulo = (historia.get("title") or "").strip()
        if not titulo:
            continue

        # Ask HN e Show HN sem link externo: o endereço é a própria discussão.
        url = historia.get("url") or f"https://news.ycombinator.com/item?id={historia['objectID']}"

        # Sem texto próprio, o resumo é a tração. É honesto: é isso que a
        # fonte sabe. O modelo da fase 2 vê logo que está a pontuar um boato.
        corpo = historia.get("story_text") or ""
        tracao = f"{historia.get('points', 0)} pontos e {historia.get('num_comments', 0)} comentários no Hacker News"
        resumo = f"{tracao}. {limpar_texto(corpo)}" if corpo else tracao

        itens.append({
            "id": identificador(url),
            "titulo": limpar_texto(titulo),
            "resumo": resumo[:LIMITE_RESUMO],
            "url": url,
            "fonte": fonte["nome"],
            "camada": int(fonte["camada"]),
            "data": data_em_iso(historia.get("created_at", "")),
        })
    return itens


def itens_do_github(json_bruto: bytes, fonte: dict) -> list[dict]:
    """Interpreta a pesquisa de repositórios do GitHub.

    Os números que vêm daqui (estrelas, data do último push, licença) são
    factos da API, não de terceiros. Mesmo assim ficam só no resumo: a fase 3
    é que os grava como factos verificados, porque é ela que os vai buscar
    no momento do julgamento e não há uma semana atrás.
    """
    resposta = json.loads(json_bruto)

    itens = []
    for repositorio in resposta.get("items", []):
        url = repositorio.get("html_url", "")
        nome = repositorio.get("full_name", "")
        if not url or not nome:
            continue

        licenca = (repositorio.get("license") or {}).get("spdx_id") or "sem licença declarada"
        descricao = limpar_texto(repositorio.get("description") or "")
        resumo = (
            f"{repositorio.get('stargazers_count', 0)} estrelas, {licenca}, "
            f"{repositorio.get('language') or 'linguagem não declarada'}. {descricao}"
        )

        itens.append({
            "id": identificador(url),
            "titulo": nome,
            "resumo": resumo[:LIMITE_RESUMO],
            "url": url,
            "fonte": fonte["nome"],
            "camada": int(fonte["camada"]),
            # O push é o que interessa: diz que o repositório está vivo agora.
            "data": data_em_iso(repositorio.get("pushed_at", "")),
        })
    return itens


def ofertas_da_pagina(html_bruto: bytes) -> dict[str, list]:
    """Tira da página do Student Pack o que cada parceiro está a oferecer.

    Devolve `slug -> [nome, [ofertas]]`. Isto é raspar HTML, não é ler um feed:
    parte-se no dia em que o GitHub mexer no template. Quem chama tem de tratar
    um resultado curto como avaria, nunca como "acabaram as ofertas".
    """
    pagina = html_bruto.decode("utf-8", errors="replace")

    parceiros: dict[str, list] = {}
    for slug, nome, corpo in PARCEIRO.findall(pagina):
        parceiros[slug] = [limpar_texto(nome), [limpar_texto(o) for o in OFERTA.findall(corpo)]]
    return parceiros


def itens_da_pagina(html_bruto: bytes, fonte: dict, anterior: dict | None) -> tuple[list[dict], dict, str]:
    """Compara a página de hoje com o retrato da corrida anterior.

    Devolve (itens, retrato_novo, aviso). Uma página não tem entradas nem datas,
    por isso a única notícia que dela sai é o que mudou desde ontem: parceiros
    que entraram, parceiros que saíram, e ofertas reescritas.

    Na primeira corrida não há com que comparar. Guarda-se o retrato e não se
    publica nada — dizer "há 83 parceiros" no dia em que se começou a olhar não
    é notícia, é o ponto de partida.
    """
    agora = ofertas_da_pagina(html_bruto)
    if len(agora) < MINIMO_DE_PARCEIROS:
        raise ErroDeFonte(
            f"só se extraíram {len(agora)} parceiros e esperavam-se pelo menos "
            f"{MINIMO_DE_PARCEIROS}; o HTML da página deve ter mudado"
        )

    if not anterior:
        return [], agora, (
            f"{fonte['nome']}: primeiro retrato guardado com {len(agora)} parceiros; "
            f"a comparação começa na próxima corrida"
        )

    entraram = [agora[slug][0] for slug in agora if slug not in anterior]
    sairam = [anterior[slug][0] for slug in anterior if slug not in agora]
    mudaram = [
        agora[slug][0]
        for slug in agora
        if slug in anterior and agora[slug][1] != anterior[slug][1]
    ]

    if not (entraram or sairam or mudaram):
        return [], agora, ""

    # O resumo diz nomes e não números, porque é pelos nomes que se decide se
    # vale a pena ir lá. A fase 2 recebe isto como recebe qualquer outro resumo.
    partes = []
    rotulos = []
    if entraram:
        partes.append("entraram " + ", ".join(entraram))
        rotulos.append(f"{len(entraram)} a entrar")
    if sairam:
        partes.append("saíram " + ", ".join(sairam))
        rotulos.append(f"{len(sairam)} a sair")
    if mudaram:
        partes.append("mudaram de oferta " + ", ".join(mudaram))
        rotulos.append(f"{len(mudaram)} com oferta diferente")

    item = {
        # O id leva a alteração dentro, e não só o endereço: se a página mudar
        # outra vez na semana que vem, tem de ser um item novo e não um repetido
        # que o vistos.json engole.
        "id": identificador(fonte["url"] + "|" + "; ".join(partes)),
        "titulo": "GitHub Student Pack: " + ", ".join(rotulos),
        "resumo": ("No GitHub Student Pack " + "; ".join(partes) + ".")[:LIMITE_RESUMO],
        "url": fonte["url"],
        "fonte": fonte["nome"],
        "camada": int(fonte["camada"]),
        # A página não diz quando mudou. O que se sabe é o dia em que demos por
        # isso, e é esse que se escreve — a data do GitHub não se inventa.
        "data": datetime.now(timezone.utc).date().isoformat(),
    }
    return [item], agora, ""


# Um interpretador por tipo. Acrescentar uma fonte de um tipo que já existe é
# mexer só no fontes.toml; um tipo novo é uma função nova aqui e mais nada.
INTERPRETES = {
    "rss": itens_do_feed,
    "hn": itens_do_hn,
    "github": itens_do_github,
}


def preencher_url(url: str, dias: int) -> str:
    """Substitui os marcadores de data no endereço da fonte.

    As APIs de pesquisa precisam de saber a partir de quando procurar, e isso
    muda todos os dias. O marcador fica visível no fontes.toml — quem lá mexer
    percebe o que a fonte faz sem abrir o código.

    {desde}     — instante unix, que é o que o Hacker News quer
    {desde_iso} — AAAA-MM-DD, que é o que o GitHub quer
    """
    corte = datetime.now(timezone.utc) - timedelta(days=max(dias, 1))
    return url.format(desde=int(corte.timestamp()), desde_iso=corte.date().isoformat())


def recolher(
    caminho_fontes: Path, dias: int = 7, estado: dict | None = None
) -> tuple[list[dict], list[str], list[str], dict]:
    """Corre todas as fontes e devolve (itens, erros, avisos, retratos).

    Uma fonte em baixo não pode partir a corrida inteira: regista-se o erro,
    salta-se, continua-se. No fim quem chama decide o que fazer com a lista
    de erros — mostrá-la é o mínimo.

    Erros e avisos andam separados de propósito: um erro é uma fonte que não
    respondeu, um aviso é uma fonte que respondeu de mais e foi cortada. São
    coisas diferentes e misturá-las esconde a que importa.

    O `dias` serve para as fontes de pesquisa saberem a partir de quando
    procurar. É o mesmo número da janela da fase 1, para não haver duas
    noções de "recente" a viver no mesmo pipeline.

    O `estado` é o retrato das fontes do tipo `pagina` na corrida anterior, e
    os `retratos` devolvidos são o desta. Passam por parâmetro de propósito:
    assim esta fase continua a não abrir ficheiro nenhum, e quem decide quando
    gravar é o `principal.py`, depois de a corrida chegar ao fim.
    """
    itens: list[dict] = []
    erros: list[str] = []
    avisos: list[str] = []
    vistos_nesta_corrida: set[str] = set()
    servidor_anterior = ""

    # Começa vazio e não como cópia do anterior: assim, uma fonte de página que
    # saia do fontes.toml leva o retrato dela atrás e não fica a ocupar espaço.
    estado_anterior = estado or {}
    retratos: dict[str, dict] = {}

    for fonte in ler_fontes(caminho_fontes):
        tipo = fonte.get("tipo", "rss")
        endereco = preencher_url(fonte["url"], dias)

        # Dois pedidos seguidos ao mesmo servidor levam com o limite de ritmo.
        servidor = urllib.parse.urlparse(endereco).hostname or ""
        if servidor and servidor == servidor_anterior:
            time.sleep(PAUSA_ENTRE_PEDIDOS)
        servidor_anterior = servidor

        try:
            bruto = descarregar(endereco)
            if tipo == "pagina":
                # Excepção com nome: este é o único interpretador que precisa de
                # saber como estavam as coisas ontem, por isso não cabe no
                # INTERPRETES, onde todos têm a mesma assinatura.
                recolhidos, retrato, aviso = itens_da_pagina(
                    bruto, fonte, estado_anterior.get(fonte["nome"])
                )
                retratos[fonte["nome"]] = retrato
                if aviso:
                    avisos.append(aviso)
            else:
                recolhidos = INTERPRETES[tipo](bruto, fonte)
        except ErroDeFonte as erro:
            erros.append(f"{fonte['nome']}: {erro}")
            # Guarda-se o retrato velho: se hoje a página não respondeu, amanhã
            # compara-se com o último bom e a alteração não se perde pelo meio.
            if tipo == "pagina" and fonte["nome"] in estado_anterior:
                retratos[fonte["nome"]] = estado_anterior[fonte["nome"]]
            continue
        except ET.ParseError as erro:
            erros.append(f"{fonte['nome']}: XML inválido ({erro})")
            continue
        except (json.JSONDecodeError, KeyError, TypeError) as erro:
            erros.append(f"{fonte['nome']}: resposta inesperada ({type(erro).__name__}: {erro})")
            continue

        if not recolhidos:
            # Uma página que não mudou é o caso normal e não é erro nenhum. Nas
            # outras fontes é: um feed que responde sem itens está avariado.
            if tipo != "pagina":
                erros.append(f"{fonte['nome']}: respondeu, mas sem itens aproveitáveis")
            continue

        # Teto por fonte. Os itens já vêm ordenados pela própria fonte (mais
        # recentes ou mais votados primeiro), por isso cortar pelo fim tira os
        # piores. Se cortou, diz-se — um limite silencioso esconde uma fonte
        # que passou a despejar.
        limite = int(fonte.get("limite", LIMITE_POR_FONTE))
        if len(recolhidos) > limite:
            avisos.append(f"{fonte['nome']}: {len(recolhidos)} itens, cortados aos {limite} pelo teto da fonte")
            recolhidos = recolhidos[:limite]

        # O mesmo endereço pode aparecer em duas fontes. Fica o primeiro, e
        # como o fontes.toml tem a camada 1 no topo, ganha sempre a fonte
        # mais fiável — o que é exactamente o que queremos.
        for item in recolhidos:
            if item["id"] in vistos_nesta_corrida:
                continue
            vistos_nesta_corrida.add(item["id"])
            itens.append(item)

    return itens, erros, avisos, retratos
