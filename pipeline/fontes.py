"""Fase 1 do Sinal: ler os feeds das fontes e normalizar tudo para a mesma forma.

Só usa a biblioteca padrão do Python. A razão não é purismo: cada dependência
é mais uma coisa a instalar, a manter e a explicar. RSS e Atom são XML, e o
`xml.etree` que vem com o Python chega perfeitamente para os ler.

Nada aqui julga nada. Esta fase só recolhe. O julgamento vem nas fases 2 a 4.
"""

from __future__ import annotations

import hashlib
import html
import re
import tomllib
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
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
    return fontes


def descarregar(url: str) -> bytes:
    """Vai buscar o feed. Devolve os bytes crus para o interpretador de XML
    poder usar a codificação declarada no próprio ficheiro."""
    pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE})
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


def recolher(caminho_fontes: Path) -> tuple[list[dict], list[str]]:
    """Corre todas as fontes e devolve (itens, erros).

    Uma fonte em baixo não pode partir a corrida inteira: regista-se o erro,
    salta-se, continua-se. No fim quem chama decide o que fazer com a lista
    de erros — mostrá-la é o mínimo.
    """
    itens: list[dict] = []
    erros: list[str] = []
    vistos_nesta_corrida: set[str] = set()

    for fonte in ler_fontes(caminho_fontes):
        try:
            xml_bruto = descarregar(fonte["url"])
            recolhidos = itens_do_feed(xml_bruto, fonte)
        except ErroDeFonte as erro:
            erros.append(f"{fonte['nome']}: {erro}")
            continue
        except ET.ParseError as erro:
            erros.append(f"{fonte['nome']}: XML inválido ({erro})")
            continue

        if not recolhidos:
            erros.append(f"{fonte['nome']}: respondeu, mas sem itens aproveitáveis")
            continue

        # O mesmo endereço pode aparecer em duas fontes. Fica o primeiro.
        for item in recolhidos:
            if item["id"] in vistos_nesta_corrida:
                continue
            vistos_nesta_corrida.add(item["id"])
            itens.append(item)

    return itens, erros
