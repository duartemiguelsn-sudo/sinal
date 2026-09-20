"""Orquestra o pipeline do Sinal. Por agora só existe a fase 1.

Correr a partir da raiz do repositório:

    python pipeline/principal.py            # só o que for novo
    python pipeline/principal.py --esquecer # ignora o histórico e apanha tudo

As fases 2 a 4 (filtrar, verificar, dar veredicto) entram aqui depois, cada uma
a receber a lista da anterior. A fase 1 é deliberadamente a primeira a existir
sozinha: é mais fácil corrigir o rumo com dados reais à frente.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

# A consola do Windows não usa UTF-8 por omissão e estraga os acentos.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Deixa importar o fontes.py estando ao lado, sem transformar a pasta em pacote.
sys.path.insert(0, str(Path(__file__).parent))

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
    diff tem de ser leg\u00edvel por uma pessoa. Sem isto, 'ç' vira '\u00e7'.
    """
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(conteudo, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    argumentos = argparse.ArgumentParser(description="Pipeline do Sinal (fase 1).")
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
    opcoes = argumentos.parse_args()

    print("Fase 1 — a ler as fontes\n")

    try:
        itens, erros = recolher(CAMINHO_FONTES)
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

    if erros:
        print("\nFontes com problemas:")
        for erro in erros:
            print(f"  - {erro}")

    sem_data = sum(1 for item in novos if not item["data"])
    print(f"\n{len(itens)} itens recolhidos, {len(novos)} novos nos últimos {opcoes.dias} dias", end="")
    if antigos:
        print(f", {antigos} descartados por serem mais antigos", end="")
    print(f", {sem_data} sem data" if sem_data else "")

    if not novos:
        print("\nNada de novo. Isso também é um resultado — não se inventa recolha.")
        return 0

    gravar_json(CAMINHO_ITENS, novos)
    gravar_json(CAMINHO_VISTOS, sorted(vistos | {item["id"] for item in novos}))
    print(f"\nEscrito: {CAMINHO_ITENS.relative_to(RAIZ)} e {CAMINHO_VISTOS.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
