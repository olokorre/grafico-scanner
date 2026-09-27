"""Perfis de veiculos com proporcoes de marcha conhecidas.

Cada perfil guarda a relacao ``rpm por km/h`` de cada marcha (1a em diante),
que e exatamente a razao usada para estimar a marcha a partir de RPM e
velocidade. As proporcoes podem ser informadas de duas formas no arquivo
``veiculos.json``:

1. Diretamente em ``marchas`` (rpm por km/h), por exemplo::

       {"nome": "Polo 1.6", "marchas": [124.6, 88.1, 56.3, 40.1, 31.8]}

2. A partir dos dados de fabrica (``relacoes_cambio``, ``diferencial`` e
   ``pneu``)::

       {
         "nome": "Polo 1.6",
         "relacoes_cambio": [3.45, 1.94, 1.28, 0.93, 0.76],
         "diferencial": 4.16,
         "pneu": "185/60R14"
       }

O arquivo fica na raiz do projeto e pode ser editado livremente; perfis com o
mesmo nome sobrescrevem os embutidos.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass

CAMINHO_PADRAO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "veiculos.json"
)


@dataclass(frozen=True)
class Veiculo:
    """Perfil de um veiculo."""

    nome: str
    marchas: tuple[float, ...]  # rpm por km/h, da 1a marcha em diante
    observacao: str = ""


# Perfis embutidos. O arquivo ``veiculos.json`` pode adicionar/sobrescrever.
PADRAO: tuple[Veiculo, ...] = (
    Veiculo(
        nome="Polo Flex 1.6 2005 (manual)",
        marchas=(124.6, 88.1, 56.3, 40.1, 31.8),
        observacao="Proporcoes medidas no proprio log; 5a marcha e a mais usada.",
    ),
)


def _circunferencia_m(pneu: str) -> float | None:
    """Circunferencia do pneu em metros a partir de algo como ``185/60R14``."""
    try:
        medida, aro = pneu.upper().replace(" ", "").split("R")
        largura, perfil = medida.split("/")
        diametro_mm = float(aro) * 25.4 + 2.0 * float(largura) * float(perfil) / 100.0
        return math.pi * diametro_mm / 1000.0
    except (ValueError, AttributeError):
        return None


def calcular_marchas(
    relacoes_cambio: list[float], diferencial: float, pneu: str
) -> tuple[float, ...]:
    """Converte relacoes de cambio em ``rpm por km/h``."""
    circunferencia = _circunferencia_m(pneu)
    if not circunferencia:
        return ()
    fator = (1000.0 / 60.0) / circunferencia  # rpm por km/h por unidade
    return tuple(
        round(fator * relacao * diferencial, 1) for relacao in relacoes_cambio
    )


def _perfil_de_dict(dados: dict) -> Veiculo | None:
    nome = str(dados.get("nome", "")).strip()
    if not nome:
        return None

    marchas = dados.get("marchas")
    if marchas:
        try:
            valores = tuple(float(valor) for valor in marchas)
        except (TypeError, ValueError):
            return None
    else:
        relacoes = dados.get("relacoes_cambio")
        diferencial = dados.get("diferencial")
        pneu = dados.get("pneu")
        if not (relacoes and diferencial and pneu):
            return None
        valores = calcular_marchas(relacoes, float(diferencial), str(pneu))

    if not valores:
        return None
    return Veiculo(nome, valores, str(dados.get("observacao", "")))


def carregar(caminho: str = CAMINHO_PADRAO) -> dict[str, Veiculo]:
    """Carrega os perfis embutidos e os do arquivo JSON (se existir)."""
    perfis: dict[str, Veiculo] = {perfil.nome: perfil for perfil in PADRAO}
    if not os.path.isfile(caminho):
        return perfis

    try:
        with open(caminho, encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
    except (OSError, json.JSONDecodeError):
        return perfis

    itens = dados.get("veiculos", dados) if isinstance(dados, dict) else dados
    if not isinstance(itens, list):
        return perfis

    for item in itens:
        if not isinstance(item, dict):
            continue
        perfil = _perfil_de_dict(item)
        if perfil is not None:
            perfis[perfil.nome] = perfil
    return perfis


def salvar_perfil(
    nome: str, marchas: tuple[float, ...], caminho: str = CAMINHO_PADRAO
) -> None:
    """Adiciona/atualiza um perfil no arquivo JSON."""
    itens: list[dict] = []
    if os.path.isfile(caminho):
        try:
            with open(caminho, encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
            itens = dados.get("veiculos", dados) if isinstance(dados, dict) else dados
        except (OSError, json.JSONDecodeError):
            itens = []
    if not isinstance(itens, list):
        itens = []

    itens = [item for item in itens if not (isinstance(item, dict) and item.get("nome") == nome)]
    itens.append({"nome": nome, "marchas": [round(valor, 1) for valor in marchas]})

    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump({"veiculos": itens}, arquivo, ensure_ascii=False, indent=2)
        arquivo.write("\n")
