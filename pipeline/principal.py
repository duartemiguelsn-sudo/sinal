"""Orquestra o pipeline do Sinal. Existem as fases 1, 2, 3, 4 e 5.

Correr a partir da raiz do repositório:

    python pipeline/principal.py                 # recolhe, pontua, verifica e julga
    python pipeline/principal.py --estimar       # diz o que ia custar, sem gastar
    python pipeline/principal.py --sem-filtro    # só recolhe, como antes da fase 2
    python pipeline/principal.py --sem-pesquisa  # verifica só o que é de graça
    python pipeline/principal.py --sem-veredicto # não paga julgamento escrito
    python pipeline/principal.py --esquecer      # ignora o histórico e apanha tudo
    python pipeline/principal.py --historico 0   # publica sem cortar nada

A fase 2 é a primeira que custa dinheiro. Por isso está desenhada para se
poder olhar para a conta antes de a fazer: o `--estimar` mostra o custo da
corrida sem chamar a API, e no fim de uma corrida a sério aparece o valor
verdadeiro, tirado do `usage` que a API devolve.

O LIMIAR_FASE_3 é o número que decide o custo do projeto. Tudo o que fica
abaixo dele sai daqui pontuado e com um veredicto tirado da nota, de graça.
Tudo o que fica acima passa pela verificação (fase 3, paga por pesquisa) e
pelo julgamento escrito (fase 4, paga ao Sonnet). Mexer neste número mexe nas
duas contas ao mesmo tempo.

A fase 5 é a que junta esta corrida ao que já estava publicado e corta o
histórico velho. Não chama a API, e está no `publicar.py` porque é a única
parte do pipeline que lê o disco antes de lhe escrever.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

# A consola do Windows não usa UTF-8 por omissão e estraga os acentos.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Deixa importar os módulos ao lado sem transformar a pasta em pacote.
sys.path.insert(0, str(Path(__file__).parent))

import filtrar  # noqa: E402
import publicar  # noqa: E402
import veredicto  # noqa: E402
import verificar  # noqa: E402
from fontes import ErroDeFonte, recolher  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_FONTES = RAIZ / "pipeline" / "fontes.toml"
CAMINHO_ITENS = RAIZ / "dados" / "itens.json"
CAMINHO_VISTOS = RAIZ / "dados" / "vistos.json"

# Quase todos os feeds servem o arquivo inteiro, não o dia. Sem esta janela, a
# primeira corrida apanha milhares de itens antigos e manda-os todos para a
# fase 2, que é paga. Sete dias cobre com folga uma recolha diária, e dá
# margem para o Action falhar um dia ou dois sem se perder nada.
JANELA_DE_DIAS = 7

# A nota a partir da qual um item passa à fase 3. Está aqui em cima e sozinho
# porque é o travão principal de todo o orçamento: tudo o que vem depois custa
# por item, e é este número que decide quantos itens é que há depois.
LIMIAR_FASE_3 = 7


def mostrar_lista(titulo: str, linhas: list[str]) -> None:
    if not linhas:
        return
    print(f"\n{titulo}")
    for linha in linhas:
        print(f"  - {linha}")


def main() -> int:
    argumentos = argparse.ArgumentParser(description="Pipeline do Sinal (fases 1 a 5).")
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
        help=f"travão de custo da fase 2, em dólares por corrida (por omissão {filtrar.TETO_DE_DOLARES})",
    )
    argumentos.add_argument(
        "--sem-pesquisa",
        action="store_true",
        help="na fase 3 usa só o que é de graça (a API do GitHub) e não paga pesquisa nenhuma",
    )
    argumentos.add_argument(
        "--teto-fase3",
        type=float,
        default=verificar.TETO_DE_DOLARES,
        help=f"travão de custo da fase 3, em dólares por corrida (por omissão {verificar.TETO_DE_DOLARES})",
    )
    argumentos.add_argument(
        "--sem-veredicto",
        action="store_true",
        help="na fase 4 não paga julgamento escrito; todos os itens ficam com o veredicto tirado da nota",
    )
    argumentos.add_argument(
        "--teto-fase4",
        type=float,
        default=veredicto.TETO_DE_DOLARES,
        help=f"travão de custo da fase 4, em dólares por corrida (por omissão {veredicto.TETO_DE_DOLARES})",
    )
    argumentos.add_argument(
        "--historico",
        type=int,
        default=publicar.DIAS_DE_HISTORICO,
        help=f"quantos dias de itens ficam no ficheiro que o site lê (por omissão {publicar.DIAS_DE_HISTORICO}); 0 não corta nada",
    )
    opcoes = argumentos.parse_args()

    print("Fase 1 — a ler as fontes\n")

    try:
        itens, erros, avisos = recolher(CAMINHO_FONTES, opcoes.dias)
    except ErroDeFonte as erro:
        print(f"erro fatal na configuração das fontes: {erro}")
        return 1

    # Um dicionário de id -> data; para filtrar só interessam as chaves.
    vistos = {} if opcoes.esquecer else publicar.ler_vistos(CAMINHO_VISTOS)
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
        print(
            f"\nPior caso da fase 3: {verificar.TETO_DE_ITENS_PESQUISADOS} itens pesquisados a "
            f"{verificar.PESQUISAS_POR_ITEM} pesquisas cada, com teto de {opcoes.teto_fase3:.2f} USD.\n"
            "O custo verdadeiro dela só se sabe depois das notas: os itens que forem\n"
            "repositórios do GitHub verificam-se de graça e não entram nesta conta."
        )
        print(
            f"\nPior caso da fase 4: {veredicto.TETO_DE_ITENS_JULGADOS} itens julgados pelo "
            f"{veredicto.MODELO}, com teto de {opcoes.teto_fase4:.2f} USD.\n"
            "Os restantes itens da corrida levam o veredicto tirado da nota da fase 2,\n"
            "que não custa nada."
        )
        print("\n--estimar: fica por aqui, não se chamou a API e não se gastou nada.")
        return 0

    gasto = 0.0

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
        novos, avisos_fase2, gasto_fase2 = filtrar.pontuar(novos, opcoes.teto)
        gasto += gasto_fase2
        mostrar_lista("Fase 2:", avisos_fase2)

        pontuados = [item for item in novos if "nota" in item]
        if pontuados:
            distribuicao: dict[int, int] = {}
            for item in pontuados:
                distribuicao[item["nota"]] = distribuicao.get(item["nota"], 0) + 1
            escala = "  ".join(f"{nota}:{quantos}" for nota, quantos in sorted(distribuicao.items(), reverse=True))
            print(f"\nNotas  {escala}")
        print(f"Custo da fase 2: {gasto_fase2:.4f} USD")

    # Fase 3. Os candidatos vão ordenados por nota, do mais alto para o mais
    # baixo: se o teto de custo cortar a meio, corta pelos que menos interessam.
    candidatos = sorted(
        (item for item in novos if item.get("nota", 0) >= LIMIAR_FASE_3),
        key=lambda item: item["nota"],
        reverse=True,
    )

    if not candidatos:
        print(f"\nFase 3 — nenhum item com nota >= {LIMIAR_FASE_3}. Não há nada para verificar.")
    else:
        conta3 = verificar.estimar(candidatos)
        print(
            f"\nFase 3 — {len(candidatos)} itens com nota >= {LIMIAR_FASE_3}: "
            f"{conta3['repositorios']} são repositórios e verificam-se de graça, "
            f"{conta3['pesquisados']} vão a pesquisa"
        )
        if conta3["ignorados"]:
            print(f"{conta3['ignorados']} ficam por pesquisar por causa do teto de itens")
        print(
            f"Custo estimado: {conta3['dolares']:.4f} USD"
            f"   (teto desta corrida: {opcoes.teto_fase3:.2f} USD)"
        )

        # A pesquisa é a única parte paga desta fase. O caminho do GitHub corre
        # sempre, mesmo sem chave: não custa nada e é ele que dá os números
        # exactos que o julgamento não pode inventar.
        if opcoes.sem_pesquisa:
            print("--sem-pesquisa: corre só a parte de graça.")
        elif not filtrar.tem_chave():
            print("Sem ANTHROPIC_API_KEY: corre só a parte de graça.")
        com_pesquisa = not opcoes.sem_pesquisa and filtrar.tem_chave()

        print("\na verificar...")
        avisos_fase3, gasto_fase3 = verificar.verificar(candidatos, opcoes.teto_fase3, com_pesquisa)
        gasto += gasto_fase3
        mostrar_lista("Fase 3:", avisos_fase3)

        com_factos = sum(1 for item in candidatos if item.get("factos"))
        print(f"\n{com_factos} de {len(candidatos)} itens ficaram com factos verificados")
        print(f"Custo da fase 3: {gasto_fase3:.4f} USD")

    # Fase 4. Só os candidatos verificados levam julgamento escrito — é a única
    # parte paga. Todos os outros apanham o veredicto da nota logo a seguir,
    # de graça, e é por isso que este bloco pode ser saltado inteiro sem que
    # nenhum item fique sem rótulo.
    if not candidatos:
        print("\nFase 4 — não há itens verificados, por isso não há nada para julgar.")
    elif opcoes.sem_veredicto:
        print("\nFase 4 — --sem-veredicto: ninguém é julgado, todos levam o veredicto da nota.")
    elif not filtrar.tem_chave():
        print("\nFase 4 — sem ANTHROPIC_API_KEY: todos levam o veredicto da nota.")
    else:
        conta4 = veredicto.estimar(candidatos)
        print(
            f"\nFase 4 — {conta4['julgados']} itens em {conta4['lotes']} lotes pelo "
            f"{veredicto.MODELO}, ~{conta4['entrada']} tokens de entrada e "
            f"~{conta4['saida']} de saída"
        )
        if conta4["ignorados"]:
            print(f"{conta4['ignorados']} ficam por julgar por causa do teto de itens")
        print(
            f"Custo estimado: {conta4['dolares']:.4f} USD"
            f"   (teto desta corrida: {opcoes.teto_fase4:.2f} USD)"
        )

        print("\na julgar...")
        avisos_fase4, gasto_fase4 = veredicto.julgar(candidatos, opcoes.teto_fase4)
        gasto += gasto_fase4
        mostrar_lista("Fase 4:", avisos_fase4)
        print(f"\nCusto da fase 4: {gasto_fase4:.4f} USD")

    # O resto da corrida — a esmagadora maioria — fica com o veredicto tirado
    # da nota que a fase 2 já pagou, sem chamar modelo nenhum. Corre sempre,
    # também depois de um julgamento escrito, para apanhar os candidatos que
    # um travão ou uma falha deixaram por julgar.
    derivados = veredicto.marcar_sem_julgamento(novos, LIMIAR_FASE_3)
    if derivados:
        escala = "  ".join(f"{rotulo}:{quantos}" for rotulo, quantos in sorted(derivados.items()))
        print(f"\n{sum(derivados.values())} veredictos tirados da nota, de graça  —  {escala}")

    contagem: dict[str, int] = {}
    for item in novos:
        contagem[item["veredicto"]] = contagem.get(item["veredicto"], 0) + 1
    print("Veredictos  " + "  ".join(f"{rotulo}:{quantos}" for rotulo, quantos in sorted(contagem.items())))

    if gasto:
        print(f"\nCusto real desta corrida: {gasto:.4f} USD")

    # Fase 5. Junta esta corrida ao que já estava publicado e corta o que é
    # velho de mais. Não custa nada, e por isso corre sempre até ao fim, mesmo
    # que as fases pagas tenham sido saltadas.
    resumo = publicar.publicar(CAMINHO_ITENS, CAMINHO_VISTOS, novos, opcoes.historico)

    print(
        f"\nFase 5 — {resumo['novos']} itens acrescentados aos {resumo['historico']} "
        f"que já lá estavam"
        + (f", {resumo['repetidos']} actualizados" if resumo["repetidos"] else "")
    )
    if resumo["cortados"]:
        print(
            f"{resumo['cortados']} cortados por passarem os {opcoes.historico} dias de histórico"
            + (f" e {resumo['ids_esquecidos']} ids esquecidos" if resumo["ids_esquecidos"] else "")
        )
    print(f"{resumo['publicados']} itens ficam no site")
    print(f"\nEscrito: {CAMINHO_ITENS.relative_to(RAIZ)} e {CAMINHO_VISTOS.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
