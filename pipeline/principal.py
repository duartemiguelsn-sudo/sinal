"""Orquestra o pipeline do Sinal. Existem as fases 1 e 2.

Correr a partir da raiz do repositório:

    python pipeline/principal.py             # recolhe e pontua
    python pipeline/principal.py --estimar   # diz o que ia custar, sem gastar
    python pipeline/principal.py --sem-filtro # só recolhe, como antes da fase 2
    python pipeline/principal.py --esquecer  # ignora o histórico e apanha tudo

A fase 2 é a primeira que custa dinheiro. Por isso está desenhada para se
poder olhar para a conta antes de a fazer: o `--estimar` mostra o custo da
corrida sem chamar a API, e no fim de uma corrida a sério aparece o valor
verdadeiro, tirado do `usage` que a API devolve.

As fases 3 (verificar) e 4 (veredicto) entram aqui a seguir, e só vão ver os
itens com nota igual ou superior ao LIMIAR_FASE_3. É esse número, mais do que
qualquer outro, que decide o custo do projeto — a fase 3 paga por pesquisa.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

# A consola do Windows não usa UTF-8 por omissão e estraga os acentos.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Deixa importar os módulos ao lado sem transformar a pasta em pacote.
sys.path.insert(0, str(Path(__file__).parent))

import filtrar  # noqa: E402
from fontes import ErroDeFonte, recolher  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_FONTES = RAIZ / "pipeline" / "fontes.toml"
CAMINHO_ITENS = RAIZ / "dados" / "itens.json"
CAMINHO_VISTOS = RAIZ / "dados" / "vistos.json"

DIAS_DE_HISTORICO = 60  # ver fase 5: o ficheiro não pode crescer sem fim

# Quase todos os feeds servem o arquivo inteiro, não o dia. Sem esta janela, a
# primeira corrida apanha milhares de itens antigos e manda-os todos para a
# fase 2, que é paga. Sete dias cobre com folga uma recolha diária, e dá
# margem para o Action falhar um dia ou dois sem se perder nada.
JANELA_DE_DIAS = 7

# A nota a partir da qual um item passa à fase 3. Está aqui em cima e sozinho
# porque é o travão principal de todo o orçamento: tudo o que vem depois custa
# por item, e é este número que decide quantos itens é que há depois.
LIMIAR_FASE_3 = 7


def ler_vistos(caminho: Path) -> set[str]:
    """Ids já processados. Ficheiro em falta é normal na primeira corrida."""
    if not caminho.exists():
        return set()
    try:
        return set(json.loads(caminho.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, TypeError):
        print(f"aviso: {caminho.name} ilegível, a recomeçar o histórico do zero")
        return set()


def gravar_json(caminho: Path, conteudo) -> None:
    """Grava com indentação e acentos legíveis.

    ensure_ascii=False é de propósito: estes ficheiros vão para o Git e o
    diff tem de ser legível por uma pessoa. Sem isto, 'ç' vira 'ç'.
    """
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(conteudo, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def mostrar_lista(titulo: str, linhas: list[str]) -> None:
    if not linhas:
        return
    print(f"\n{titulo}")
    for linha in linhas:
        print(f"  - {linha}")


def main() -> int:
    argumentos = argparse.ArgumentParser(description="Pipeline do Sinal (fases 1 e 2).")
    argumentos.add_argument(
        "--dias",
        type=int,
        default=JANELA_DE_DIAS,
        help=f"só aceita itens publicados nos últimos N dias (por omissão {JANELA_DE_DIAS}); 0 desliga o corte",
    )
    argumentos.add_argument(
        "--esquecer",
        action="store_true",
        help="ignora o vistos.json e volta a apanhar tudo o que as fontes derem",
    )
    argumentos.add_argument(
        "--sem-filtro",
        action="store_true",
        help="corre só a fase 1; não chama a API e não gasta nada",
    )
    argumentos.add_argument(
        "--estimar",
        action="store_true",
        help="recolhe, diz quanto é que a fase 2 ia custar, e pára sem gastar",
    )
    argumentos.add_argument(
        "--teto",
        type=float,
        default=filtrar.TETO_DE_DOLARES,
        help=f"travão de custo em dólares por corrida (por omissão {filtrar.TETO_DE_DOLARES})",
    )
    opcoes = argumentos.parse_args()

    print("Fase 1 — a ler as fontes\n")

    try:
        itens, erros, avisos = recolher(CAMINHO_FONTES, opcoes.dias)
    except ErroDeFonte as erro:
        print(f"erro fatal na configuração das fontes: {erro}")
        return 1

    vistos = set() if opcoes.esquecer else ler_vistos(CAMINHO_VISTOS)
    novos = [item for item in itens if item["id"] not in vistos]

    # Um item sem data é sempre aceite: preferimos vê-lo e decidir do que
    # deitá-lo fora por uma falha de formato do feed.
    antigos = 0
    if opcoes.dias > 0:
        limite = (date.today() - timedelta(days=opcoes.dias)).isoformat()
        antes = len(novos)
        novos = [item for item in novos if not item["data"] or item["data"] >= limite]
        antigos = antes - len(novos)

    # Mais recente primeiro. Os itens sem data vão para o fim, onde se notam.
    novos.sort(key=lambda item: item["data"] or "", reverse=True)

    por_fonte: dict[str, int] = {}
    for item in novos:
        por_fonte[item["fonte"]] = por_fonte.get(item["fonte"], 0) + 1

    for nome, quantidade in sorted(por_fonte.items(), key=lambda par: -par[1]):
        print(f"  {quantidade:>4}  {nome}")

    mostrar_lista("Fontes com problemas:", erros)
    mostrar_lista("Fontes cortadas pelo teto:", avisos)

    sem_data = sum(1 for item in novos if not item["data"])
    print(f"\n{len(itens)} itens recolhidos, {len(novos)} novos nos últimos {opcoes.dias} dias", end="")
    if antigos:
        print(f", {antigos} descartados por serem mais antigos", end="")
    print(f", {sem_data} sem data" if sem_data else "")

    if not novos:
        print("\nNada de novo. Isso também é um resultado — não se inventa recolha.")
        return 0

    # Teto de itens. É o segundo travão: mesmo que uma fonte passe o teto dela,
    # a corrida inteira nunca manda mais do que isto para a parte paga. Corta
    # pelos mais antigos, porque os novos são os que interessam.
    if len(novos) > filtrar.TETO_DE_ITENS:
        print(
            f"\ntravão: {len(novos)} itens é mais do que o teto de {filtrar.TETO_DE_ITENS}; "
            f"ficam os {filtrar.TETO_DE_ITENS} mais recentes"
        )
        novos = novos[:filtrar.TETO_DE_ITENS]

    conta = filtrar.estimar(novos)
    print(
        f"\nFase 2 — {len(novos)} itens em {conta['lotes']} lotes, "
        f"~{conta['entrada']} tokens de entrada e ~{conta['saida']} de saída"
    )
    print(f"Custo estimado: {conta['dolares']:.4f} USD   (teto desta corrida: {opcoes.teto:.2f} USD)")

    if opcoes.estimar:
        print("\n--estimar: fica por aqui, não se chamou a API e não se gastou nada.")
        return 0

    if opcoes.sem_filtro:
        print("\n--sem-filtro: a fase 2 não correu. Os itens vão para o site sem nota.")
    elif not filtrar.tem_chave():
        print(
            "\nANTHROPIC_API_KEY não está no ambiente, por isso a fase 2 não correu.\n"
            "Os itens vão para o site sem nota, o que é o comportamento certo:\n"
            "sem julgamento não se inventa um."
        )
    else:
        print("\na pontuar...")
        novos, avisos_fase2, gasto = filtrar.pontuar(novos, opcoes.teto)
        mostrar_lista("Fase 2:", avisos_fase2)

        pontuados = [item for item in novos if "nota" in item]
        if pontuados:
            candidatos = [item for item in pontuados if item["nota"] >= LIMIAR_FASE_3]
            distribuicao: dict[int, int] = {}
            for item in pontuados:
                distribuicao[item["nota"]] = distribuicao.get(item["nota"], 0) + 1
            escala = "  ".join(f"{nota}:{quantos}" for nota, quantos in sorted(distribuicao.items(), reverse=True))
            print(f"\nNotas  {escala}")
            print(f"{len(candidatos)} itens com nota >= {LIMIAR_FASE_3} — é o que a fase 3 irá verificar")
        print(f"Custo real desta corrida: {gasto:.4f} USD")

    gravar_json(CAMINHO_ITENS, novos)
    gravar_json(CAMINHO_VISTOS, sorted(vistos | {item["id"] for item in novos}))
    print(f"\nEscrito: {CAMINHO_ITENS.relative_to(RAIZ)} e {CAMINHO_VISTOS.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
