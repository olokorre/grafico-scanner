"""Calculo de metricas e resumo a partir de um :class:`LogData`."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

import numpy as np
import pandas as pd

from .parser import P, LogData

if TYPE_CHECKING:
    from .veiculos import Veiculo

# Conversoes e constantes usadas nas estimativas.
HP_PARA_KW = 0.7457
CO2_POR_LITRO_GASOLINA = 2.31  # kg de CO2 por litro
RPM_MIN_TORQUE = 800  # abaixo disso o torque estimado nao faz sentido
VEL_MIN_MARCHA = 5.0  # km/h minimo para estimar marcha
NUM_MARCHAS = 6  # numero maximo de marchas assumido no agrupamento


def _max(serie: pd.DataFrame) -> Optional[float]:
    if serie.empty:
        return None
    return float(serie["valor"].max())


def _min(serie: pd.DataFrame) -> Optional[float]:
    if serie.empty:
        return None
    return float(serie["valor"].min())


def _media(serie: pd.DataFrame, positivos: bool = False) -> Optional[float]:
    if serie.empty:
        return None
    valores = serie["valor"].to_numpy(dtype=float)
    if positivos:
        valores = valores[valores > 0]
        if valores.size == 0:
            return None
    return float(np.mean(valores))


def _delta(serie: pd.DataFrame) -> Optional[float]:
    """Diferenca entre o ultimo e o primeiro valor (contadores acumulados)."""
    if serie.empty:
        return None
    return float(serie["valor"].iloc[-1] - serie["valor"].iloc[0])


def _argmax(serie: pd.DataFrame) -> Optional[float]:
    """Tempo (s) em que ocorre o valor maximo de uma serie."""
    if serie.empty:
        return None
    indice = serie["valor"].to_numpy(dtype=float).argmax()
    return float(serie["tempo"].iloc[indice])


def _intervalos(tempo: np.ndarray) -> np.ndarray:
    """Duracao de cada amostra (diferenca para a proxima), em segundos."""
    if tempo.size < 2:
        return np.zeros_like(tempo)
    dt = np.diff(tempo, prepend=tempo[0])
    dt = np.where(dt <= 0, np.nan, dt)
    return dt


def _kmeans_1d(valores: np.ndarray, k: int, iteracoes: int = 60):
    """Agrupamento 1-D simples (k-means) implementado em numpy."""
    x = np.asarray(valores, dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return np.array([], dtype=int), np.array([], dtype=float)
    k = max(1, min(k, x.size))
    # Inicializa com quantis cobrindo tambem a cauda alta (1a marcha), que e
    # pouco frequente e seria ignorada por quantis uniformes.
    centros = np.quantile(x, np.linspace(0.02, 0.998, k))
    rotulos = np.zeros(x.size, dtype=int)
    for _ in range(iteracoes):
        distancias = np.abs(x[:, None] - centros[None, :])
        rotulos = distancias.argmin(axis=1)
        novos = np.array(
            [
                x[rotulos == indice].mean() if np.any(rotulos == indice) else centros[indice]
                for indice in range(k)
            ]
        )
        if np.allclose(novos, centros):
            break
        centros = novos
    # maior razao RPM/velocidade corresponde a marcha mais baixa (1a).
    ordem = np.argsort(centros)[::-1]
    mapa = {int(origem): posicao + 1 for posicao, origem in enumerate(ordem)}
    rotulos = np.array([mapa[int(rotulo)] for rotulo in rotulos], dtype=int)
    return rotulos, centros


def _limpar_rotulos(rotulos: np.ndarray, minimo: int = 4) -> np.ndarray:
    """Remove trechos curtos (< minimo amostras) de troca de marcha.

    Trechos curtos sao fundidos no vizinho estavel (anterior ou, se nao
    houver, o proximo). Amostras ``nan`` (fora de qualquer marcha) sao
    preservadas.
    """
    resultado = np.asarray(rotulos, dtype=float).copy()
    n = resultado.size
    if n == 0:
        return resultado
    for _ in range(2):
        inicio = 0
        while inicio < n:
            if np.isnan(resultado[inicio]):
                inicio += 1
                continue
            fim = inicio + 1
            while fim < n and resultado[fim] == resultado[inicio]:
                fim += 1
            if (fim - inicio) < minimo:
                vizinho = None
                for posicao in range(inicio - 1, -1, -1):
                    if not np.isnan(resultado[posicao]):
                        vizinho = resultado[posicao]
                        break
                if vizinho is None:
                    for posicao in range(fim, n):
                        if not np.isnan(resultado[posicao]):
                            vizinho = resultado[posicao]
                            break
                if vizinho is not None:
                    resultado[inicio:fim] = vizinho
            inicio = fim
    return resultado


def _ajustar_retas(
    velocidade: np.ndarray, rpm: np.ndarray, inclinacoes: np.ndarray,
    iteracoes: int = 100,
) -> tuple[np.ndarray, np.ndarray]:
    """Ajusta retas ``rpm = k * velocidade`` as amostras (k-means 2D).

    Cada observacao e associada a reta de menor erro vertical ``|rpm - k*vel|``
    (que pondera mais as velocidades altas) e cada reta e reajustada por
    minimos quadrados passando pela origem.
    """
    k = np.asarray(inclinacoes, dtype=float)
    if k.size == 0:
        return k, np.array([], dtype=int)
    rotulos = np.zeros(velocidade.size, dtype=int)
    for _ in range(iteracoes):
        erro = np.abs(rpm[:, None] - velocidade[:, None] * k[None, :])
        novos_rotulos = erro.argmin(axis=1)
        novos = k.copy()
        for indice in range(k.size):
            selecao = novos_rotulos == indice
            denominador = float(np.sum(velocidade[selecao] ** 2))
            if selecao.sum() >= 5 and denominador > 0:
                novos[indice] = float(
                    np.sum(velocidade[selecao] * rpm[selecao]) / denominador
                )
        convergiu = np.allclose(novos, k, rtol=1e-4)
        k, rotulos = novos, novos_rotulos
        if convergiu:
            break
    return k, rotulos


def _mesclar_inclinacoes(
    inclinacoes: np.ndarray, minimo_relativo: float = 0.06
) -> np.ndarray:
    """Junta inclinacoes muito proximas (evita marchas duplicadas)."""
    grupos: list[list[float]] = []
    for valor in sorted(inclinacoes.tolist(), reverse=True):
        if grupos and abs(grupos[-1][-1] - valor) / valor < minimo_relativo:
            grupos[-1].append(valor)
        else:
            grupos.append([valor])
    return np.array([float(np.mean(grupo)) for grupo in grupos], dtype=float)


def _detectar_inclinacoes(
    velocidade: np.ndarray, rpm: np.ndarray, k_inicial: int = NUM_MARCHAS
) -> np.ndarray:
    """Inclinacoes (rpm por km/h) das marchas, do maior para o menor."""
    if velocidade.size == 0:
        return np.array([], dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        razao = rpm / velocidade
    _rotulos, centros = _kmeans_1d(razao, k_inicial)
    if centros.size == 0:
        return np.array([], dtype=float)
    k, _ = _ajustar_retas(velocidade, rpm, centros)
    k = _mesclar_inclinacoes(k)
    k, _ = _ajustar_retas(velocidade, rpm, k)
    return np.sort(k)[::-1]


# --------------------------------------------------------------- torque / dyno
def serie_torque(log: LogData) -> pd.DataFrame:
    """Torque estimado (Nm) a partir da potencia e do RPM."""
    if not (log.tem(P.rpm) and log.tem(P.potencia)):
        return pd.DataFrame({"tempo": [], "valor": []})
    base = log.alinhar(P.rpm, P.potencia)
    if base.empty:
        return pd.DataFrame({"tempo": [], "valor": []})
    rpm = base[P.rpm].to_numpy(dtype=float)
    potencia_kw = base[P.potencia].to_numpy(dtype=float) * HP_PARA_KW
    with np.errstate(divide="ignore", invalid="ignore"):
        torque = np.where(rpm > RPM_MIN_TORQUE, potencia_kw * 9549.0 / rpm, np.nan)
    quadro = pd.DataFrame({"tempo": base["tempo"], "valor": torque})
    return quadro.dropna(subset=["valor"]).reset_index(drop=True)


def curva_dyno(log: LogData, passo_rpm: int = 250) -> pd.DataFrame:
    """Curva de potencia/torque maximos por faixa de RPM (dyno virtual)."""
    if not (log.tem(P.rpm) and log.tem(P.potencia)):
        return pd.DataFrame()
    base = log.alinhar(P.rpm, P.potencia)
    if base.empty:
        return pd.DataFrame()
    rpm = base[P.rpm].to_numpy(dtype=float)
    hp = base[P.potencia].to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        torque = np.where(rpm > RPM_MIN_TORQUE, hp * HP_PARA_KW * 9549.0 / rpm, np.nan)
    quadro = pd.DataFrame({"rpm": rpm, "hp": hp, "torque": torque})
    quadro = quadro[(quadro["rpm"] > RPM_MIN_TORQUE) & np.isfinite(quadro["torque"])]
    if quadro.empty:
        return pd.DataFrame()
    maximo = float(quadro["rpm"].max())
    faixas = np.arange(RPM_MIN_TORQUE, maximo + passo_rpm, passo_rpm)
    quadro["faixa"] = pd.cut(quadro["rpm"], faixas)
    agrupado = quadro.groupby("faixa", observed=True).agg(
        rpm=("rpm", "mean"), hp=("hp", "max"), torque=("torque", "max")
    )
    return agrupado.reset_index(drop=True)


# ------------------------------------------------------------------- marchas
def _razao_rpm_velocidade(log: LogData):
    """Retorna ``(tempo, rpm, velocidade, razao, valido)`` para a marcha."""
    base = log.alinhar(P.rpm, P.velocidade)
    if base.empty:
        return None
    rpm = base[P.rpm].to_numpy(dtype=float)
    vel = base[P.velocidade].to_numpy(dtype=float)
    valido = (vel > VEL_MIN_MARCHA) & (rpm > 500)
    if valido.sum() < 20:
        return None
    razao = np.full(rpm.shape, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        razao[valido] = rpm[valido] / vel[valido]
    razao = pd.Series(razao).rolling(5, min_periods=1, center=True).median().to_numpy()
    return base["tempo"].to_frame(), rpm, vel, razao, valido


def detectar_proporcoes(log: LogData, k: int = NUM_MARCHAS) -> tuple[float, ...]:
    """Proporcoes RPM/velocidade (1a..N) detectadas no log."""
    dados = _razao_rpm_velocidade(log)
    if dados is None:
        return ()
    _tempo, rpm, vel, _razao, valido = dados
    inclinacoes = _detectar_inclinacoes(vel[valido], rpm[valido], k)
    return tuple(round(float(valor), 1) for valor in inclinacoes)


def serie_marchas(log: LogData, veiculo: "Veiculo | None" = None) -> pd.DataFrame:
    """Marcha estimada (1..N) ao longo do tempo a partir de RPM/velocidade.

    A classificacao usa o plano velocidade x RPM: cada amostra e associada a
    reta ``rpm = k * velocidade`` de menor erro vertical, o que pondera mais
    as velocidades altas e torna a leitura menos sensivel a ruido em baixa
    velocidade. Se ``veiculo`` for informado, usa as proporcoes conhecidas do
    perfil; caso contrario, detecta as marchas automaticamente (k-means 2D).
    """
    vazio = pd.DataFrame({"tempo": [], "marcha": [], "rpm": [], "velocidade": []})
    if not (log.tem(P.rpm) and log.tem(P.velocidade)):
        return vazio
    dados = _razao_rpm_velocidade(log)
    if dados is None:
        return vazio
    tempo, rpm, vel, razao, valido = dados

    marchas = np.full(rpm.shape, np.nan)
    if veiculo is not None and veiculo.marchas:
        proporcoes = np.array(sorted(veiculo.marchas, reverse=True), dtype=float)
        distancias = np.abs(razao[valido][:, None] - proporcoes[None, :])
        indices = distancias.argmin(axis=1)
        minimos = distancias[np.arange(indices.size), indices]
        aceito = minimos <= 0.10 * proporcoes[indices]
        rots = np.where(aceito, indices + 1, np.nan)
        marchas[valido] = rots
        marchas = _limpar_rotulos(marchas)
    else:
        inclinacoes = _detectar_inclinacoes(vel[valido], rpm[valido])
        if inclinacoes.size == 0:
            return vazio
        distancias = np.abs(razao[valido][:, None] - inclinacoes[None, :])
        indices = distancias.argmin(axis=1)
        minimos = distancias[np.arange(indices.size), indices]
        aceito = minimos <= 0.10 * inclinacoes[indices]
        rots = np.where(aceito, indices + 1, np.nan)
        marchas[valido] = rots
        marchas = _limpar_rotulos(marchas)

    return pd.DataFrame(
        {
            "tempo": tempo["tempo"],
            "marcha": marchas,
            "rpm": rpm,
            "velocidade": vel,
        }
    ).dropna(subset=["marcha"]).reset_index(drop=True)


def estatisticas_marchas(serie: pd.DataFrame) -> dict:
    """Tempo por marcha, numero de trocas e RPM medio de troca."""
    resultado: dict[str, object] = {
        "tempo_por_marcha": {},
        "num_trocas": 0,
        "rpm_medio_troca": None,
        "marcha_mais_usada": None,
    }
    if serie.empty:
        return resultado

    tempo = serie["tempo"].to_numpy(dtype=float)
    marcha = serie["marcha"].to_numpy(dtype=float)
    rpm = serie["rpm"].to_numpy(dtype=float)
    dt = _intervalos(tempo)
    positivos = dt[np.isfinite(dt) & (dt > 0)]
    # Limita o passo: intervalos longos indicam que a marcha nao estava
    # engatada (ponto morto, motor desligado) e nao devem ser contados.
    limite = max(4.0 * float(np.median(positivos)), 5.0) if positivos.size else 5.0
    valido = np.isfinite(dt) & (dt > 0) & (dt <= limite)
    passo = np.where(valido, dt, 0.0)

    tempos: dict[int, float] = {}
    trocas: list[float] = []
    for indice, valor in enumerate(marcha):
        marcha_int = int(valor)
        tempos[marcha_int] = tempos.get(marcha_int, 0.0) + float(passo[indice])
        if indice > 0 and valor > marcha[indice - 1] and valido[indice]:
            trocas.append(float(rpm[indice]))

    resultado["tempo_por_marcha"] = dict(sorted(tempos.items()))
    resultado["num_trocas"] = len(trocas)
    resultado["rpm_medio_troca"] = float(np.mean(trocas)) if trocas else None
    if tempos:
        resultado["marcha_mais_usada"] = max(tempos, key=lambda marcha: tempos[marcha])
    return resultado


# ------------------------------------------------------------------ economia
def consumo_por_velocidade(log: LogData, passo_kmh: int = 10) -> pd.DataFrame:
    """Rendimento (km/L) por faixa de velocidade, via velocidade / (L/h)."""
    if not (log.tem(P.velocidade) and log.tem(P.consumo_lh)):
        return pd.DataFrame()
    base = log.alinhar(P.velocidade, P.consumo_lh)
    if base.empty:
        return pd.DataFrame()
    vel = base[P.velocidade].to_numpy(dtype=float)
    lh = base[P.consumo_lh].to_numpy(dtype=float)
    valido = (lh > 0.05) & (vel > 10)
    if valido.sum() < 10:
        return pd.DataFrame()
    kml = vel[valido] / lh[valido]
    vel = vel[valido]
    faixas = np.arange(0, vel.max() + passo_kmh, passo_kmh)
    quadro = pd.DataFrame({"velocidade": vel, "km_l": kml})
    quadro["faixa"] = pd.cut(quadro["velocidade"], faixas)
    agrupado = quadro.groupby("faixa", observed=True).agg(
        velocidade=("velocidade", "mean"),
        km_l=("km_l", "median"),
        amostras=("km_l", "size"),
    )
    return agrupado[agrupado["amostras"] >= 5].reset_index(drop=True)


def estatisticas_ociosidade(log: LogData) -> dict:
    """Tempo, combustivel e custo gastos parado com o motor ligado."""
    resultado = {"tempo_s": 0.0, "combustivel_l": 0.0, "consumo_lh": None}
    if not (log.tem(P.velocidade) and log.tem(P.rpm)):
        return resultado
    parametros = [P.velocidade, P.rpm]
    if log.tem(P.consumo_lh):
        parametros.append(P.consumo_lh)
    base = log.alinhar(*parametros)
    if base.empty:
        return resultado
    vel = base[P.velocidade].to_numpy(dtype=float)
    rpm = base[P.rpm].to_numpy(dtype=float)
    dt = _intervalos(base["tempo"].to_numpy(dtype=float))
    dt = np.where(np.isfinite(dt), dt, 0.0)
    parado = (vel < 1.0) & (rpm > 300)
    resultado["tempo_s"] = float(dt[parado].sum())
    if P.consumo_lh in base.columns:
        lh = base[P.consumo_lh].to_numpy(dtype=float)
        combustivel = float(np.nansum(lh[parado] * dt[parado] / 3600.0))
        resultado["combustivel_l"] = combustivel
        if resultado["tempo_s"] > 0:
            resultado["consumo_lh"] = combustivel / (resultado["tempo_s"] / 3600.0)
    return resultado


# -------------------------------------------------------------------- emissao
def _co2_kg(combustivel_l: Optional[float]) -> Optional[float]:
    if not combustivel_l:
        return None
    return combustivel_l * CO2_POR_LITRO_GASOLINA


# ------------------------------------------------------------------ eco-score
def eco_score(log: LogData, resumo: "Resumo") -> tuple[Optional[float], Optional[str]]:
    """Indice heuristico de conducao economica (0..100)."""
    penalidades: list[tuple[float, float]] = []  # (peso, fracao 0..1)

    if resumo.combustivel_ocioso_s and log.duracao_s > 0:
        penalidades.append((0.30, min(resumo.combustivel_ocioso_s / log.duracao_s, 1.0)))

    rpm = log.serie(P.rpm)
    if not rpm.empty:
        valores = rpm["valor"].to_numpy(dtype=float)
        fracao_alto = float((valores > 3500).mean())
        penalidades.append((0.30, min(fracao_alto, 1.0)))

    acel = log.serie(P.aceleracao)
    if not acel.empty:
        valores = acel["valor"].to_numpy(dtype=float)
        fracao_forte = float((valores > 0.15).mean())
        penalidades.append((0.25, min(fracao_forte * 5.0, 1.0)))

    borboleta = log.serie(P.borboleta)
    if not borboleta.empty:
        valores = borboleta["valor"].to_numpy(dtype=float)
        fracao_aberta = float((valores > 50).mean())
        penalidades.append((0.15, min(fracao_aberta, 1.0)))

    if not penalidades:
        return None, None

    soma_pesos = sum(peso for peso, _ in penalidades)
    deficit = sum(peso * fracao for peso, fracao in penalidades) / soma_pesos
    nota = max(0.0, min(100.0, 100.0 * (1.0 - deficit)))
    if nota >= 80:
        rotulo = "Economico"
    elif nota >= 60:
        rotulo = "Moderado"
    else:
        rotulo = "Agressivo"
    return nota, rotulo


# --------------------------------------------------------------- performance
def _melhor_aceleracao(
    tempo: np.ndarray, velocidade: np.ndarray, inicio: float, fim: float, tolerancia: float = 2.0
) -> Optional[float]:
    """Melhor tempo (s) para ir de ``inicio`` a ``fim`` km/h."""
    melhor: Optional[float] = None
    n = velocidade.size
    i = 0
    while i < n - 1:
        if velocidade[i] <= inicio and velocidade[i + 1] > velocidade[i]:
            tempo_inicio = tempo[i]
            maximo = velocidade[i]
            j = i + 1
            while j < n:
                if velocidade[j] < maximo - tolerancia:
                    break
                maximo = max(maximo, velocidade[j])
                if maximo >= fim:
                    decorrido = tempo[j] - tempo_inicio
                    if decorrido > 0.3 and (melhor is None or decorrido < melhor):
                        melhor = decorrido
                    break
                j += 1
            i = j
        i += 1
    return melhor


def desempenho(log: LogData) -> dict:
    """Melhores tempos de aceleracao detectados no log."""
    resultado: dict[str, object] = {
        "0_60": None,
        "0_100": None,
        "60_100": None,
        "velocidade_max": None,
    }
    vel = log.serie(P.velocidade)
    if vel.empty:
        return resultado
    tempo = vel["tempo"].to_numpy(dtype=float)
    valores = vel["valor"].to_numpy(dtype=float)
    resultado["velocidade_max"] = float(valores.max())
    if valores.max() >= 60:
        resultado["0_60"] = _melhor_aceleracao(tempo, valores, 0.0, 60.0)
        resultado["60_100"] = _melhor_aceleracao(tempo, valores, 60.0, 100.0)
    if valores.max() >= 100:
        resultado["0_100"] = _melhor_aceleracao(tempo, valores, 0.0, 100.0)
    return resultado


@dataclass
class Resumo:
    duracao_s: float = 0.0
    distancia_km: Optional[float] = None
    odometro_km: Optional[float] = None
    velocidade_max: Optional[float] = None
    velocidade_media_movendo: Optional[float] = None
    velocidade_media_geral: Optional[float] = None
    rpm_max: Optional[float] = None
    rpm_medio: Optional[float] = None
    consumo_lh_medio: Optional[float] = None
    consumo_l_100km: Optional[float] = None
    consumo_km_l: Optional[float] = None
    combustivel_l: Optional[float] = None
    custo_total: Optional[float] = None
    temperatura_min: Optional[float] = None
    temperatura_max: Optional[float] = None
    aceleracao_max: Optional[float] = None
    aceleracao_min: Optional[float] = None
    boost_max: Optional[float] = None
    mapa_kpa_max: Optional[float] = None
    combustivel_duracao_estimada_s: Optional[float] = None
    # Desempenho / motor
    potencia_max: Optional[float] = None
    potencia_max_rpm: Optional[float] = None
    torque_max: Optional[float] = None
    torque_max_rpm: Optional[float] = None
    # Marchas
    marcha_mais_usada: Optional[int] = None
    num_trocas: Optional[int] = None
    rpm_medio_troca: Optional[float] = None
    # Economia
    velocidade_otima: Optional[float] = None
    rendimento_otimo: Optional[float] = None
    combustivel_ocioso_s: Optional[float] = None
    combustivel_ocioso_l: Optional[float] = None
    custo_ocioso: Optional[float] = None
    custo_por_km: Optional[float] = None
    custo_por_hora: Optional[float] = None
    co2_kg: Optional[float] = None
    eco_nota: Optional[float] = None
    eco_rotulo: Optional[str] = None
    # Performance
    melhor_0_60: Optional[float] = None
    melhor_0_100: Optional[float] = None
    melhor_60_100: Optional[float] = None
    rotulos: list[tuple[str, str]] = field(default_factory=list)


def _fmt(valor: Optional[float], casas: int = 1, sufixo: str = "") -> str:
    if valor is None or (isinstance(valor, float) and not np.isfinite(valor)):
        return "--"
    return f"{valor:,.{casas}f}{sufixo}".replace(",", " ")


def _fmt_duracao(segundos: float) -> str:
    segundos = int(round(segundos))
    h, resto = divmod(segundos, 3600)
    m, s = divmod(resto, 60)
    if h:
        return f"{h}h {m:02d}min"
    if m:
        return f"{m}min {s:02d}s"
    return f"{s}s"


def _preco_por_litro(res: Resumo) -> Optional[float]:
    if res.custo_total and res.combustivel_l and res.combustivel_l > 0:
        return res.custo_total / res.combustivel_l
    return None


def analisar(log: LogData, veiculo: "Veiculo | None" = None) -> Resumo:
    """Calcula o resumo estatistico de um log."""
    res = Resumo(duracao_s=log.duracao_s)

    dist = log.serie(P.distancia)
    res.distancia_km = _max(dist)
    res.odometro_km = _delta(log.serie(P.distancia_total)) if log.tem(P.distancia_total) else None

    vel = log.serie(P.velocidade)
    res.velocidade_max = _max(vel)
    res.velocidade_media_movendo = _media(vel, positivos=True)
    if res.distancia_km is not None and log.duracao_s > 0:
        res.velocidade_media_geral = res.distancia_km / (log.duracao_s / 3600.0)

    rpm = log.serie(P.rpm)
    res.rpm_max = _max(rpm)
    res.rpm_medio = _media(rpm)

    res.consumo_lh_medio = _media(log.serie(P.consumo_lh), positivos=True)

    if log.tem(P.combustivel_total):
        res.combustivel_l = _delta(log.serie(P.combustivel_total))
    else:
        res.combustivel_l = _max(log.serie(P.combustivel_usado))

    if res.combustivel_l and res.distancia_km and res.distancia_km > 0:
        res.consumo_l_100km = res.combustivel_l / res.distancia_km * 100.0
        res.consumo_km_l = res.distancia_km / res.combustivel_l

    if log.tem(P.preco_total):
        res.custo_total = _delta(log.serie(P.preco_total))

    temp = log.serie(P.temperatura_ar)
    res.temperatura_min = _min(temp)
    res.temperatura_max = _max(temp)

    acel = log.serie(P.aceleracao)
    res.aceleracao_max = _max(acel)
    res.aceleracao_min = _min(acel)

    res.boost_max = _max(log.serie(P.boost))
    res.mapa_kpa_max = _max(log.serie(P.map_kpa))

    if res.combustivel_l and res.consumo_lh_medio and res.consumo_lh_medio > 0:
        res.combustivel_duracao_estimada_s = res.combustivel_l / res.consumo_lh_medio * 3600.0

    # ---------------------------------------------------------- torque / dyno
    dyno = curva_dyno(log)
    if not dyno.empty:
        indice_torque = dyno["torque"].to_numpy(dtype=float).argmax()
        indice_hp = dyno["hp"].to_numpy(dtype=float).argmax()
        res.torque_max = float(dyno["torque"].iloc[indice_torque])
        res.torque_max_rpm = float(dyno["rpm"].iloc[indice_torque])
        res.potencia_max = float(dyno["hp"].iloc[indice_hp])
        res.potencia_max_rpm = float(dyno["rpm"].iloc[indice_hp])

    # ---------------------------------------------------------------- marchas
    marchas = serie_marchas(log, veiculo)
    stats_marchas = estatisticas_marchas(marchas)
    res.marcha_mais_usada = stats_marchas["marcha_mais_usada"]
    res.num_trocas = stats_marchas["num_trocas"]
    res.rpm_medio_troca = stats_marchas["rpm_medio_troca"]

    # --------------------------------------------------------------- economia
    por_velocidade = consumo_por_velocidade(log)
    if not por_velocidade.empty:
        indice = por_velocidade["km_l"].to_numpy(dtype=float).argmax()
        res.velocidade_otima = float(por_velocidade["velocidade"].iloc[indice])
        res.rendimento_otimo = float(por_velocidade["km_l"].iloc[indice])

    ociosidade = estatisticas_ociosidade(log)
    res.combustivel_ocioso_s = ociosidade["tempo_s"]
    res.combustivel_ocioso_l = ociosidade["combustivel_l"]
    preco_litro = _preco_por_litro(res)
    if preco_litro and ociosidade["combustivel_l"]:
        res.custo_ocioso = ociosidade["combustivel_l"] * preco_litro

    if res.custo_total and res.distancia_km and res.distancia_km > 0:
        res.custo_por_km = res.custo_total / res.distancia_km
    if res.custo_total and log.duracao_s > 0:
        res.custo_por_hora = res.custo_total / (log.duracao_s / 3600.0)

    res.co2_kg = _co2_kg(res.combustivel_l)

    nota, rotulo = eco_score(log, res)
    res.eco_nota = nota
    res.eco_rotulo = rotulo

    # ------------------------------------------------------------ performance
    perf = desempenho(log)
    res.melhor_0_60 = perf["0_60"]
    res.melhor_0_100 = perf["0_100"]
    res.melhor_60_100 = perf["60_100"]

    res.rotulos = [
        ("Duracao", _fmt_duracao(res.duracao_s)),
        ("Distancia percorrida", _fmt(res.distancia_km, 2, " km")),
        ("Odometro acumulado", _fmt(res.odometro_km, 2, " km")),
        ("Velocidade maxima", _fmt(res.velocidade_max, 0, " km/h")),
        ("Velocidade media (em movimento)", _fmt(res.velocidade_media_movendo, 1, " km/h")),
        ("Velocidade media (geral)", _fmt(res.velocidade_media_geral, 1, " km/h")),
        ("RPM maximo", _fmt(res.rpm_max, 0, " rpm")),
        ("RPM medio", _fmt(res.rpm_medio, 0, " rpm")),
        ("Potencia maxima (estimada)", f"{_fmt(res.potencia_max, 0, ' hp')} @ {_fmt(res.potencia_max_rpm, 0, ' rpm')}"),
        ("Torque maximo (estimado)", f"{_fmt(res.torque_max, 0, ' Nm')} @ {_fmt(res.torque_max_rpm, 0, ' rpm')}"),
        ("Marcha mais usada", _fmt(res.marcha_mais_usada, 0, "a") if res.marcha_mais_usada else "--"),
        ("Trocas de marcha", _fmt(res.num_trocas, 0) if res.num_trocas else "--"),
        ("RPM medio nas trocas", _fmt(res.rpm_medio_troca, 0, " rpm")),
        ("Consumo instantaneo medio", _fmt(res.consumo_lh_medio, 2, " L/h")),
        ("Consumo medio", _fmt(res.consumo_l_100km, 2, " L/100km")),
        ("Rendimento medio", _fmt(res.consumo_km_l, 2, " km/L")),
        ("Velocidade mais economica", f"{_fmt(res.velocidade_otima, 0, ' km/h')} ({_fmt(res.rendimento_otimo, 1, ' km/L')})"),
        ("Combustivel usado", _fmt(res.combustivel_l, 3, " L")),
        ("Custo estimado", _fmt(res.custo_total, 2, " R$")),
        ("Custo por km", _fmt(res.custo_por_km, 2, " R$/km")),
        ("Custo por hora", _fmt(res.custo_por_hora, 2, " R$/h")),
        ("Marcha lenta (tempo)", _fmt_duracao(res.combustivel_ocioso_s or 0.0)),
        ("Combustivel em marcha lenta", _fmt(res.combustivel_ocioso_l, 3, " L")),
        ("Custo em marcha lenta", _fmt(res.custo_ocioso, 2, " R$")),
        ("CO2 emitido", _fmt(res.co2_kg, 2, " kg")),
        ("Eco-score", f"{_fmt(res.eco_nota, 0)}/100 ({res.eco_rotulo or '--'})"),
        ("0-60 km/h", _fmt(res.melhor_0_60, 1, " s")),
        ("0-100 km/h", _fmt(res.melhor_0_100, 1, " s")),
        ("60-100 km/h", _fmt(res.melhor_60_100, 1, " s")),
        ("Temperatura do ar (min / max)", f"{_fmt(res.temperatura_min, 0, ' °C')} / {_fmt(res.temperatura_max, 0, ' °C')}"),
        ("Aceleracao (min / max)", f"{_fmt(res.aceleracao_min, 2, ' g')} / {_fmt(res.aceleracao_max, 2, ' g')}"),
        ("Boost maximo", _fmt(res.boost_max, 2, " bar")),
        ("MAP maximo", _fmt(res.mapa_kpa_max, 0, " kPa")),
    ]
    return res
