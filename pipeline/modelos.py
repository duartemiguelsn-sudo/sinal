"""Lê o modelos.toml e entrega a configuração de cada fase paga.

É um ficheiro pequeno de propósito. As fases importam daqui em vez de lerem o
TOML cada uma à sua maneira, e assim um erro no ficheiro — uma chave em falta,
um número escrito como texto — rebenta logo ao arrancar, com uma frase a dizer
o que falta, em vez de rebentar a meio de uma corrida já paga.

O `tomllib` é da biblioteca padrão desde o Python 3.11; não acrescenta
dependência nenhuma.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

CAMINHO = Path(__file__).with_name("modelos.toml")

# O que cada fase tem de ter. Os números são verificados como números porque
# um preço escrito entre aspas passava pelo TOML sem erro e só falhava na
# primeira conta, depois de a API já ter cobrado.
OBRIGATORIOS = {
    "filtro": {"modelo": str, "preco_entrada": float, "preco_saida": float,
               "esforco": str, "teto_dolares": float},
    "verificacao": {"modelo": str, "preco_entrada": float, "preco_saida": float,
                    "esforco": str, "preco_por_pesquisa": float,
                    "itens_pesquisados": int, "pesquisas_por_item": int,
                    "teto_dolares": float},
    "veredicto": {"modelo": str, "preco_entrada": float, "preco_saida": float,
                  "esforco": str, "itens_julgados": int, "teto_dolares": float},
}


class ErroDeConfiguracao(Exception):
    """O modelos.toml está estragado ou incompleto."""


def ler(caminho: Path = CAMINHO) -> dict[str, dict]:
    try:
        with caminho.open("rb") as ficheiro:
            dados = tomllib.load(ficheiro)
    except FileNotFoundError as erro:
        raise ErroDeConfiguracao(f"falta o {caminho.name}") from erro
    except tomllib.TOMLDecodeError as erro:
        raise ErroDeConfiguracao(f"{caminho.name} não se lê: {erro}") from erro

    for fase, campos in OBRIGATORIOS.items():
        if fase not in dados:
            raise ErroDeConfiguracao(f"{caminho.name}: falta a secção [{fase}]")
        for campo, tipo in campos.items():
            valor = dados[fase].get(campo)
            # Um inteiro serve onde se pede um decimal (0 em vez de 0.0); o
            # contrário não, e um booleano nunca serve, apesar de o Python o
            # tratar como inteiro.
            aceite = (int, float) if tipo is float else tipo
            if not isinstance(valor, aceite) or isinstance(valor, bool):
                raise ErroDeConfiguracao(
                    f"{caminho.name}: [{fase}] {campo} tem de ser {tipo.__name__}, está {valor!r}"
                )
    return dados


CONFIG = ler()
