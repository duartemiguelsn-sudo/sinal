"""Fase 5 — junta a corrida de hoje ao histórico e escreve o que o site lê.

Até aqui, cada fase mexia nos itens da corrida. Esta é a única que olha para o
que já estava no disco, e existe por duas razões:

1. A corrida só devolve o que é **novo**. Se o `itens.json` fosse escrito com
   essa lista, o site perdia tudo o que apareceu ontem de cada vez que o
   pipeline corresse. Junta-se, não se substitui.
2. Juntar sem cortar faz o ficheiro crescer para sempre, e quem o paga é o
   telemóvel de quem abre o site — o `itens.json` é descarregado inteiro a
   cada visita. Por isso o histórico tem um limite em dias.

O `vistos.json` é cortado pela mesma janela. Guardava só ids, uma lista, e
passa a guardar a data em que cada id foi visto — sem essa data não há forma
de saber qual é que já pode sair. Ficheiros no formato antigo continuam a
ler-se; ver `ler_vistos`.

Nada aqui chama a API. Esta fase não custa nada.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

# Quantos dias de itens ficam no ficheiro que o site descarrega. Sessenta dias
# a ~150 itens por dia dá um ficheiro na ordem dos poucos MB no pior caso, o
# que ainda é aceitável numa ligação de telemóvel. Mexer aqui mexe no peso do
# site, não no custo do pipeline.
DIAS_DE_HISTORICO = 60


def gravar_json(caminho: Path, conteudo) -> None:
    """Grava com indentação e acentos legíveis.

    ensure_ascii=False é de propósito: estes ficheiros vão para o Git e o
    diff tem de ser legível por uma pessoa. Sem isto, o 'ç' sai escrito como uma sequência de escape e o diff deixa de se ler.
    """
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(conteudo, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def ler_itens(caminho: Path) -> list[dict]:
    """O histórico que já está publicado. Ficheiro em falta é a primeira corrida."""
    if not caminho.exists():
        return []
    try:
        guardado = json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # Um histórico ilegível não pode parar a corrida: perde-se o passado,
        # mas publica-se o presente. O aviso fica no log do Action.
        print(f"aviso: {caminho.name} ilegível, a recomeçar o histórico do zero")
        return []
    if not isinstance(guardado, list):
        print(f"aviso: {caminho.name} não é uma lista, a recomeçar o histórico do zero")
        return []
    return [item for item in guardado if isinstance(item, dict) and item.get("id")]


def ler_vistos(caminho: Path) -> dict[str, str]:
    """Ids já processados, cada um com a data em que foi visto pela primeira vez.

    Aceita o formato antigo — uma lista só com os ids — porque houve corridas
    que o escreveram. Nesses ids não se sabe a data, e inventar uma recente
    seria pior do que a alternativa: ficam com a data mínima, saem na primeira
    limpeza, e a janela de recolha de sete dias trata de que não voltem.
    """
    if not caminho.exists():
        return {}
    try:
        guardado = json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"aviso: {caminho.name} ilegível, a recomeçar o histórico do zero")
        return {}

    if isinstance(guardado, list):
        return {str(id_): "" for id_ in guardado if id_}
    if isinstance(guardado, dict):
        return {str(id_): str(quando or "") for id_, quando in guardado.items() if id_}

    print(f"aviso: {caminho.name} com formato inesperado, a recomeçar o histórico do zero")
    return {}


def juntar(historico: list[dict], novos: list[dict]) -> tuple[list[dict], int]:
    """Junta a corrida ao histórico. Devolve a lista e quantos itens repetiram.

    Um id repetido não substitui o item antigo em bloco: escreve por cima
    campo a campo. A diferença interessa numa corrida com `--sem-filtro` ou
    sem chave, em que o item novo vem sem nota e sem veredicto — assim
    aproveita-se o julgamento que já tinha sido pago, em vez de o deitar fora.
    """
    por_id = {item["id"]: dict(item) for item in historico}

    repetidos = 0
    for item in novos:
        anterior = por_id.get(item["id"])
        if anterior is None:
            por_id[item["id"]] = dict(item)
            continue
        repetidos += 1
        primeira_vez = anterior.get("recolhido")
        anterior.update(item)
        # A data de recolha é a da primeira vez que o item apareceu, não a
        # desta. Se fosse a desta, um item que o feed sirva todos os dias sem
        # data de publicação rejuvenescia a cada corrida e nunca saía daqui.
        if primeira_vez:
            anterior["recolhido"] = primeira_vez

    return list(por_id.values()), repetidos


def idade(item: dict) -> str:
    """A data pela qual o item é considerado velho.

    É a data de publicação. Quando o feed não a deu, vale a data em que o item
    foi recolhido: sem isto, um item sem data nunca envelhecia e ficava no
    ficheiro para sempre.
    """
    return item.get("data") or item.get("recolhido") or ""


def cortar(itens: list[dict], dias: int, hoje: str) -> tuple[list[dict], int]:
    """Deita fora o que é mais velho do que a janela. `dias` a 0 desliga o corte."""
    if dias <= 0:
        return itens, 0

    limite = (date.fromisoformat(hoje) - timedelta(days=dias)).isoformat()
    # Um item sem data nenhuma — nem de publicação nem de recolha — fica.
    # É um caso de ficheiro escrito por uma versão antiga do pipeline, e
    # apagá-lo por falta de informação seria decidir com o que não se sabe.
    mantidos = [item for item in itens if not idade(item) or idade(item) >= limite]
    return mantidos, len(itens) - len(mantidos)


def publicar(
    caminho_itens: Path,
    caminho_vistos: Path,
    novos: list[dict],
    dias: int = DIAS_DE_HISTORICO,
    hoje: str | None = None,
) -> dict:
    """Escreve os dois ficheiros de dados e devolve o resumo do que fez.

    Lê o `vistos.json` do disco em vez de receber o que a corrida leu ao
    início. É de propósito: com `--esquecer` a corrida ignora o histórico para
    apanhar tudo outra vez, mas isso é uma decisão sobre o que recolher, não
    uma ordem para apagar o que já se sabe.
    """
    hoje = hoje or date.today().isoformat()

    # Marca em que dia é que cada item entrou. Serve para o envelhecer quando
    # o feed não deu data, e é a única coisa que esta fase acrescenta ao item.
    for item in novos:
        item.setdefault("recolhido", hoje)

    historico = ler_itens(caminho_itens)
    juntos, repetidos = juntar(historico, novos)
    mantidos, cortados = cortar(juntos, dias, hoje)

    # Mais recente primeiro, como o site mostra por omissão. Ordenar aqui faz
    # com que o diff do Git seja quase sempre um bloco no topo, legível.
    mantidos.sort(key=lambda item: (idade(item), item["id"]), reverse=True)

    vistos = ler_vistos(caminho_vistos)
    for item in novos:
        vistos.setdefault(item["id"], hoje)

    # Um id só sai do vistos quando o item também já saiu do histórico. Enquanto
    # lá estiver, tem de continuar a ser reconhecido como repetido.
    ids_publicados = {item["id"] for item in mantidos}
    limite = (date.fromisoformat(hoje) - timedelta(days=dias)).isoformat() if dias > 0 else ""
    vistos_mantidos = {
        id_: quando
        for id_, quando in vistos.items()
        if id_ in ids_publicados or quando >= limite
    }
    ids_esquecidos = len(vistos) - len(vistos_mantidos)

    gravar_json(caminho_itens, mantidos)
    gravar_json(caminho_vistos, dict(sorted(vistos_mantidos.items())))

    return {
        "novos": len(novos) - repetidos,
        "repetidos": repetidos,
        "historico": len(historico),
        "cortados": cortados,
        "publicados": len(mantidos),
        "ids_esquecidos": ids_esquecidos,
    }
