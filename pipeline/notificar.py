"""Avisa no telemóvel e no PC quando há coisas novas "Para ti".

Usa Web Push, a norma dos browsers para notificações. O site, ao carregar no
botão, pede ao browser uma *subscrição*: um endereço do serviço de push do
fabricante (Google para o Chrome, Mozilla para o Firefox, Apple para o
Safari) e duas chaves para cifrar a mensagem. Esse endereço é colado num
Secret do repositório, e é para lá que este ficheiro manda o resumo. O
serviço do fabricante entrega-o ao service worker do site, que mostra a
notificação mesmo com o separador fechado.

Não há servidor nosso nem conta nova: quem guarda e entrega é o browser. Não
custa nada, nem na API da Anthropic — isto corre depois de tudo estar pago.

Três modos:

    python pipeline/notificar.py --gerar-chaves       # uma vez, no início
    python pipeline/notificar.py --teste              # manda uma de experiência
    python pipeline/notificar.py CAMINHO_DO_RESUMO    # o que o Action corre

O resumo é escrito pelo `principal.py` e lido aqui num passo à parte do
Action, depois do push. A ordem interessa: se o aviso saísse antes de o
commit chegar ao GitHub Pages, tocar na notificação abria o site com os
dados de ontem.

Dependência nova: `pywebpush`. A mensagem tem de ir cifrada (ECDH e AES-GCM,
RFC 8291) e assinada (VAPID, RFC 8292), e a biblioteca padrão do Python não
tem curvas elípticas. Escrever isto à mão era criptografia caseira, que é a
pior parte de um projeto para inventar. Só o Action e quem testar localmente
precisam dela; o resto do pipeline não a importa.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_AMBIENTE = RAIZ / ".env"

# O mesmo critério do ecrã "Para ti" no app.js: tudo o que é "Agora" e os
# "Depois" com nota alta. Se um mudar, o outro tem de mudar com ele, senão a
# notificação promete coisas que o ecrã não mostra.
NOTA_MINIMA_DEPOIS = 7

# Quantos nomes cabem no corpo da notificação. O Android corta por volta das
# duas linhas e o Windows por volta das três; o resto lê-se no site.
NOMES_NO_CORPO = 3

# O serviço de push guarda a mensagem até o aparelho ligar. Um dia chega: o
# resumo de amanhã substitui este, e um aviso com dois dias já não ajuda.
VIDA_EM_SEGUNDOS = 24 * 60 * 60

# A norma VAPID exige um contacto para o fabricante saber a quem se queixar se
# isto começar a mandar lixo. A Apple recusa tudo o que não seja `mailto:` ou
# `https:`. O domínio do site é público e chega; vai sem caminho, porque o
# py_vapid recusa um `https:` com pasta no fim.
CONTACTO = "https://duartemiguelsn-sudo.github.io"

# O site está numa subpasta do GitHub Pages. O caminho vai relativo, e o
# service worker resolve-o contra o sítio onde está instalado.
ENDERECO_PARA_TI = "./#/"


def para_ti(itens: list[dict]) -> list[dict]:
    """Os itens que o ecrã "Para ti" mostraria, pela ordem em que lá aparecem."""
    agora = [item for item in itens if item.get("veredicto") == "agora"]
    depois = [
        item for item in itens
        if item.get("veredicto") == "depois" and (item.get("nota") or 0) >= NOTA_MINIMA_DEPOIS
        # Um "depois" com nota alta pode ser um item que só ficou fora do
        # limite diário da fase 3. Esse é um ignorado, e o site não o mostra
        # Para ti; avisar dele era mandar abrir uma página onde ele não está.
        and not item.get("ignorado")
    ]
    depois.sort(key=lambda item: item.get("nota") or 0, reverse=True)
    return agora + depois


def guardar_resumo(caminho: Path, itens: list[dict]) -> int:
    """Escreve o que é para avisar desta corrida. Devolve quantos itens leva.

    Só leva o que o aviso precisa. O resto do item vem de feeds de terceiros e
    não tem nada que fazer num ficheiro que sai do pipeline.
    """
    escolhidos = [
        {
            "id": item["id"],
            "nome": str(item.get("nome") or item.get("titulo") or "Sem título"),
            "veredicto": item.get("veredicto"),
        }
        for item in para_ti(itens)
        if item.get("area") != "fora-de-ambito"
    ]
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(escolhidos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(escolhidos)


def montar_mensagem(escolhidos: list[dict]) -> dict | None:
    """Um resumo só para a corrida inteira. Sem nada para dizer, não há aviso.

    Um dia vazio no site diz "nada pede atenção"; no telemóvel, o equivalente
    é ficar calado. Uma notificação diária a dizer "hoje nada" ensinava a
    ignorar as outras.
    """
    if not escolhidos:
        return None

    agora = [item for item in escolhidos if item["veredicto"] == "agora"]
    depois = [item for item in escolhidos if item["veredicto"] != "agora"]

    if agora:
        titulo = "1 coisa pede atenção agora" if len(agora) == 1 else f"{len(agora)} coisas pedem atenção agora"
    else:
        titulo = "1 coisa boa para depois" if len(depois) == 1 else f"{len(depois)} coisas boas para depois"

    nomes = [item["nome"] for item in (agora or depois)[:NOMES_NO_CORPO]]
    corpo = " · ".join(nomes)
    sobram = len(agora or depois) - len(nomes)
    if sobram > 0:
        corpo += f" · e mais {sobram}"
    if agora and depois:
        corpo += f"\n+ {len(depois)} para depois"

    # Com um item só, a notificação abre logo esse item. Com vários, abre o
    # "Para ti", que é onde eles estão juntos.
    if len(escolhidos) == 1:
        endereco = f"./#/item/{quote(str(escolhidos[0]['id']), safe='')}"
    else:
        endereco = ENDERECO_PARA_TI

    return {"titulo": titulo, "corpo": corpo, "endereco": endereco}


def ler_subscricoes(texto: str) -> list[dict]:
    """Aceita uma subscrição, uma lista delas, ou uma por linha.

    Cada aparelho tem a sua. Colar uma por linha no Secret é o mais fácil de
    manter à mão: para juntar o PC ao telemóvel, acrescenta-se uma linha.
    """
    texto = texto.strip()
    if not texto:
        return []
    try:
        lido = json.loads(texto)
        candidatas = lido if isinstance(lido, list) else [lido]
    except json.JSONDecodeError:
        candidatas = []
        for numero, linha in enumerate(texto.splitlines(), start=1):
            if not linha.strip():
                continue
            try:
                candidatas.append(json.loads(linha))
            except json.JSONDecodeError:
                print(f"aviso: a linha {numero} de PUSH_SUBSCRICOES não é JSON, saltada")

    validas = []
    for subscricao in candidatas:
        if isinstance(subscricao, dict) and subscricao.get("endpoint") and isinstance(subscricao.get("keys"), dict):
            validas.append(subscricao)
        else:
            print("aviso: uma das subscrições não tem endpoint e chaves, saltada")
    return validas


def aviso_action(texto: str) -> None:
    """Imprime o aviso e, dentro do Action, põe-no também no resumo da corrida.

    O `::warning::` é a forma de o GitHub mostrar um aviso no topo da página
    da corrida, sem a dar como falhada. Fora do Action seria só ruído.
    """
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::warning::{texto}")
    else:
        print(f"aviso: {texto}")


def enviar(mensagem: dict) -> int:
    """Manda a mensagem para cada aparelho. Devolve quantos a receberam.

    Nunca rebenta. Um aviso que falha não pode dar a corrida por falhada: os
    dados já estão publicados, e é isso que importa.
    """
    chave = os.environ.get("VAPID_CHAVE_PRIVADA", "").strip()
    subscricoes = ler_subscricoes(os.environ.get("PUSH_SUBSCRICOES", ""))
    if not chave or not subscricoes:
        # O estado normal de quem ainda não ligou as notificações. Diz-se o
        # que falta e segue-se.
        em_falta = [nome for nome, valor in (("VAPID_CHAVE_PRIVADA", chave), ("PUSH_SUBSCRICOES", subscricoes)) if not valor]
        print(f"Notificações desligadas: falta {' e '.join(em_falta)}.")
        return 0

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        aviso_action("pywebpush não está instalado; corre pip install -r requirements.txt")
        return 0

    dados = json.dumps(mensagem, ensure_ascii=False)
    entregues = 0
    for numero, subscricao in enumerate(subscricoes, start=1):
        # O domínio diz de que browser é a subscrição, sem mostrar o resto do
        # endereço, que identifica o aparelho.
        servico = subscricao["endpoint"].split("/")[2] if "//" in subscricao["endpoint"] else "?"
        try:
            webpush(
                subscription_info=subscricao,
                data=dados,
                vapid_private_key=chave,
                vapid_claims={"sub": CONTACTO},
                ttl=VIDA_EM_SEGUNDOS,
                timeout=15,
            )
            entregues += 1
        except WebPushException as erro:
            estado = getattr(erro.response, "status_code", None)
            if estado in (404, 410):
                # O browser deitou a subscrição fora: o site foi desinstalado,
                # as permissões foram retiradas, ou passou muito tempo. Não há
                # forma de a renovar daqui; tem de ser no próprio aparelho.
                aviso_action(
                    f"a subscrição {numero} ({servico}) expirou. Volta a ativar as "
                    "notificações nesse aparelho e substitui a linha no Secret PUSH_SUBSCRICOES."
                )
            elif estado == 403:
                aviso_action(
                    f"a subscrição {numero} ({servico}) recusou a assinatura. A chave pública "
                    "do app.js e o Secret VAPID_CHAVE_PRIVADA não são do mesmo par."
                )
            else:
                aviso_action(f"a subscrição {numero} ({servico}) falhou: {estado or erro}")
        except Exception as erro:  # noqa: BLE001 — rede, tempo esgotado, chave mal colada
            aviso_action(f"a subscrição {numero} ({servico}) falhou: {type(erro).__name__}: {erro}")
    return entregues


def gerar_chaves() -> int:
    """Cria o par de chaves VAPID e guarda a privada no .env.

    A privada nunca é impressa: fica no .env, que está no .gitignore, e é de
    lá que se copia para o Secret do GitHub. A pública não é segredo nenhum —
    vai no app.js, à vista de quem abrir o site, e é assim que deve ser.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    def b64url(dados: bytes) -> str:
        return base64.urlsafe_b64encode(dados).rstrip(b"=").decode("ascii")

    texto_atual = CAMINHO_AMBIENTE.read_text(encoding="utf-8") if CAMINHO_AMBIENTE.exists() else ""
    if any(linha.strip().startswith("VAPID_CHAVE_PRIVADA=") and linha.split("=", 1)[1].strip()
           for linha in texto_atual.splitlines()):
        # Gerar outra vez em cima da que existe invalidava todas as
        # subscrições feitas com a antiga, sem aviso nenhum.
        print("Já há uma VAPID_CHAVE_PRIVADA no .env. Apaga essa linha primeiro se queres mesmo trocar de par.")
        return 1

    privada = ec.generate_private_key(ec.SECP256R1())
    bruta = privada.private_numbers().private_value.to_bytes(32, "big")
    publica = privada.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )

    separador = "" if not texto_atual or texto_atual.endswith("\n") else "\n"
    with CAMINHO_AMBIENTE.open("a", encoding="utf-8") as ficheiro:
        ficheiro.write(f"{separador}\n# Par VAPID das notificações. Copia este valor para o Secret do mesmo nome.\n")
        ficheiro.write(f"VAPID_CHAVE_PRIVADA={b64url(bruta)}\n")

    print("Chave privada guardada no .env como VAPID_CHAVE_PRIVADA.")
    print(f"Chave pública, para pôr em CHAVE_PUBLICA_PUSH no app.js:\n\n{b64url(publica)}\n")
    return 0


def main() -> int:
    argumentos = argparse.ArgumentParser(description="Notificações do Sinal (Web Push).")
    argumentos.add_argument("resumo", nargs="?", type=Path, help="ficheiro escrito pelo principal.py --resumo-notificacao")
    argumentos.add_argument("--gerar-chaves", action="store_true", help="cria o par VAPID e guarda a privada no .env")
    argumentos.add_argument("--teste", action="store_true", help="manda uma notificação de experiência")
    opcoes = argumentos.parse_args()

    if opcoes.gerar_chaves:
        return gerar_chaves()

    # O mesmo leitor do .env que o resto do pipeline usa, para o teste local
    # funcionar sem mexer no ambiente à mão.
    sys.path.insert(0, str(Path(__file__).parent))
    from principal import carregar_ambiente  # noqa: E402

    carregar_ambiente(CAMINHO_AMBIENTE)

    if opcoes.teste:
        mensagem = {
            "titulo": "Sinal — teste",
            "corpo": "Se estás a ler isto, as notificações estão a funcionar.",
            "endereco": ENDERECO_PARA_TI,
        }
    elif opcoes.resumo:
        if not opcoes.resumo.exists():
            print("Não há resumo desta corrida (o pipeline parou cedo ou nada mudou). Sem aviso.")
            return 0
        try:
            escolhidos = json.loads(opcoes.resumo.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            aviso_action("o resumo da notificação está ilegível; não se mandou nada")
            return 0
        mensagem = montar_mensagem(escolhidos if isinstance(escolhidos, list) else [])
        if mensagem is None:
            print("Nada novo para ti nesta corrida. Sem aviso, de propósito.")
            return 0
    else:
        argumentos.print_help()
        return 1

    entregues = enviar(mensagem)
    if entregues:
        print(f"Notificação entregue a {entregues} {'aparelho' if entregues == 1 else 'aparelhos'}: {mensagem['titulo']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
