"""Leitura dos logs CSV do scanner OBD-II.

Formato do arquivo (separador ``;``, campos entre aspas)::

    "SECONDS";"PID";"VALUE";"UNITS";"LATITUDE";"LONGTITUDE";

Cada linha representa a leitura de um parametro (``PID``) em um instante
(``SECONDS``). Alguns nomes de parametro contem quebras de linha dentro das
aspas, por isso usamos o modulo :mod:`csv` (e nao ``split``) para interpretar.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

import numpy as np
import pandas as pd

Progresso = Optional[Callable[[int, int], None]]


@dataclass(frozen=True)
class Parametros:
    """Nomes dos parametros de interesse (normalizados)."""

    velocidade: str = "Velocidade do veículo"
    velocidade_media: str = "Velocidade média"
    distancia: str = "Distância percorrida"
    distancia_hoje: str = "Distância percorrida (Hoje)"
    distancia_semana: str = "Distância percorrida (Semana)"
    distancia_total: str = "Distância percorrida (total)"
    rpm: str = "RPM do motor"
    rpm_x1000: str = "RPM do motor x1000"
    consumo_lh: str = "Consumo instantâneo de combustível (l/h)"
    consumo_100km: str = "Consumo instantâneo de combustível (l/100km)"
    consumo_medio: str = "Consumo médio de combustível (l/100km)"
    consumo_medio_hoje: str = "Consumo médio de combustível (l/100km) (Hoje)"
    potencia: str = "Potência instantânea do motor (baseado no consumo de combustível)"
    aceleracao: str = "Aceleração"
    temperatura_ar: str = "Temperatura do ar de admissão"
    borboleta: str = "Posição da borboleta de admissão"
    map_kpa: str = "Pressão absoluta do coletor de admissão"
    boost: str = "Boost calculado"
    combustivel_usado: str = "Combustível usado"
    combustivel_total: str = "Combustível usado (total)"
    preco: str = "Preço do combustível usado"
    preco_total: str = "Preço do combustível usado (total)"
    economizador: str = (
        "Economizador de combustível (com base no estado do sistema de "
        "combustível e na posição do acelerador)"
    )


P = Parametros()


def _normalizar(texto: str) -> str:
    """Colapsa quebras de linha e espacos multiplos em um unico espaco."""
    return " ".join(texto.replace("\r", " ").replace("\n", " ").split())


@dataclass
class LogData:
    """Dados de um arquivo de log ja processados."""

    caminho: str
    nome: str
    df: pd.DataFrame
    t0: float
    t1: float
    parametros: list[str] = field(default_factory=list)

    @property
    def duracao_s(self) -> float:
        return self.t1 - self.t0

    def serie(self, parametro: str) -> pd.DataFrame:
        """Retorna as colunas ``tempo`` e ``valor`` ordenadas para um parametro."""
        sub = self.df[self.df["parametro"] == parametro]
        if sub.empty:
            return pd.DataFrame({"tempo": [], "valor": []})
        return sub[["tempo", "valor", "lat", "lon"]].sort_values("tempo").reset_index(
            drop=True
        )

    def tem(self, parametro: str) -> bool:
        return parametro in self.df["parametro"].values

    def alinhar(self, *parametros: str) -> pd.DataFrame:
        """Alinha varias series no tempo (merge + interpolacao).

        Retorna um ``DataFrame`` indexado por ``tempo`` com uma coluna por
        parametro encontrado. Os valores ausentes em um instante sao
        interpolados a partir dos vizinhos.
        """
        colunas: list[pd.Series] = []
        for parametro in parametros:
            serie = self.serie(parametro)
            if serie.empty:
                continue
            valores = serie.set_index("tempo")["valor"]
            valores = valores[~valores.index.duplicated(keep="first")]
            colunas.append(valores.rename(parametro))

        if not colunas:
            return pd.DataFrame()

        base = colunas[0].to_frame()
        for extra in colunas[1:]:
            base = base.join(extra, how="outer")
        base = base.sort_index().interpolate(limit_direction="both")
        return base.reset_index()


def _linhas(path: str, progresso: Progresso = None) -> Iterable[list[str]]:
    with open(path, newline="", encoding="utf-8", errors="replace") as arquivo:
        leitor = csv.reader(arquivo, delimiter=";")
        try:
            next(leitor)  # cabecalho
        except StopIteration:
            return
        for linha in leitor:
            if not linha or len(linha) < 4 or not linha[0].strip():
                continue
            yield linha


def contar_linhas(path: str) -> int:
    """Conta rapidamente as linhas do arquivo (para a barra de progresso)."""
    total = 0
    with open(path, "rb") as arquivo:
        for _ in arquivo:
            total += 1
    return max(total - 1, 0)


def ler_csv(path: str, progresso: Progresso = None) -> LogData:
    """Le e normaliza um arquivo de log CSV.

    Retorna um :class:`LogData` com um ``DataFrame`` de colunas
    ``tempo, t_abs, parametro, valor, unidade, lat, lon``.
    """
    import os

    tempos: list[float] = []
    parametros: list[str] = []
    valores: list[float] = []
    unidades: list[str] = []
    lats: list[float] = []
    lons: list[float] = []

    total = contar_linhas(path)
    contador = 0

    for linha in _linhas(path, progresso):
        contador += 1
        if progresso is not None and contador % 2000 == 0:
            progresso(contador, total)

        try:
            t = float(linha[0])
            valor = float(linha[2])
        except ValueError:
            continue

        nome = _normalizar(linha[1])
        unidade = _normalizar(linha[3]) if len(linha) > 3 else ""

        try:
            lat = float(linha[4]) if len(linha) > 4 and linha[4].strip() else np.nan
            lon = float(linha[5]) if len(linha) > 5 and linha[5].strip() else np.nan
        except ValueError:
            lat = lon = np.nan

        tempos.append(t)
        parametros.append(nome)
        valores.append(valor)
        unidades.append(unidade)
        lats.append(lat)
        lons.append(lon)

    if not tempos:
        vazio = pd.DataFrame(
            columns=["tempo", "t_abs", "parametro", "valor", "unidade", "lat", "lon"]
        )
        return LogData(path, os.path.basename(path), vazio, 0.0, 0.0, [])

    t0 = tempos[0]
    df = pd.DataFrame(
        {
            "tempo": np.asarray(tempos) - t0,
            "t_abs": tempos,
            "parametro": parametros,
            "valor": valores,
            "unidade": unidades,
            "lat": lats,
            "lon": lons,
        }
    )

    if progresso is not None:
        progresso(total, total)

    unicos = sorted(df["parametro"].unique().tolist())
    return LogData(path, os.path.basename(path), df, t0, tempos[-1], unicos)
