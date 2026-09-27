# grafico-scanner

Aplicativo desktop (Python + Tkinter + Matplotlib) que le logs CSV de scanner
OBD-II e apresenta, de forma visual, um resumo da viagem, graficos de uso do
motor e o trajeto percorrido.

## Recursos

- **Resumo**: distancia percorrida, duracao, velocidades (maxima e medias),
  RPM, consumo (L/100km e km/L), combustivel usado, custo, temperatura,
  aceleracao, boost e MAP.
- **Metricas derivadas**:
  - potencia e torque estimados (dyno virtual por faixa de RPM);
  - marcha estimada, tempo por marcha e trocas;
  - velocidade mais economica, custo por km/hora e custo da marcha lenta;
  - emissao de CO2 e eco-score de conducao;
  - melhores tempos de aceleracao (0-60, 0-100 e 60-100 km/h).
- **Graficos de uso** (serie temporal):
  - Velocidade e RPM;
  - Consumo e potencia do motor;
  - Potencia e torque estimados (dyno virtual);
  - Marcha ao longo do tempo e tempo por marcha;
  - Rendimento (km/L) por velocidade;
  - Aceleracao, borboleta, MAP e temperatura do ar;
  - Percurso acumulado (distancia e combustivel).
- **Mapa do trajeto** com `tkintermapview` (OpenStreetMap), com fallback para
  Matplotlib quando nao ha internet ou coordenadas GPS suficientes. O trajeto
  pode ser colorido por velocidade, RPM, consumo ou boost.
- **Multi-arquivo**: abra varios CSVs, alterne entre eles e combine logs do
  mesmo dia em um unico painel.

## Requisitos

- Python **com Tkinter**. Neste sistema, o `python3` do sistema (3.14) nao
  possui Tkinter; o `~/.local/bin/python3.13` possui. O `run.sh` localiza
  automaticamente um interpretador com Tkinter.
- Nao e necessario instalar nada via `rpm`: as dependencias Python vao para
  uma venv local.

## Como executar

```bash
./run.sh
```

Na primeira execucao o script cria a `.venv`, instala as dependencias
(`requirements.txt`) e abre o programa com o CSV mais recente da pasta.

Para abrir arquivos especificos:

```bash
./run.sh "2026-09-26 13-11-48.csv"
./run.sh a.csv b.csv
```

Ou, com a venv ja criada:

```bash
./.venv/bin/python main.py "2026-09-26 13-11-48.csv"
```

Se o Tkinter estiver em outro interpretador:

```bash
PYTHON=/caminho/para/python3.13 ./run.sh
```

## Uso

1. Clique em **Abrir CSV...** (ou `Ctrl+O`) e selecione um ou mais arquivos.
2. Clique em um item da lista lateral para visualizar; use `Ctrl+clique` para
   selecionar varios.
3. Use **Combinar** para juntar os logs selecionados em um unico painel.
4. Navegue pelas abas: Resumo, Velocidade e RPM, Consumo e potencia,
   Desempenho (dyno), Marchas, Economia, Motor e ambiente, Percurso acumulado
   e Mapa do trajeto.
5. Use a barra de ferramentas do Matplotlib (rodape das abas) para dar zoom,
   mover e salvar os graficos como imagem.
6. No menu **Veiculo**, escolha um perfil (ex.: `Polo Flex 1.6 2005`) para usar
   as proporcoes de marcha conhecidas do carro, ou mantenha **Automatico** para
   detecta-las pelo log. Use **Salvar proporções deste log como veículo...**
   para criar um perfil a partir do arquivo aberto.

## Perfis de veiculo (`veiculos.json`)

As proporcoes de marcha ficam em `veiculos.json`, na raiz do projeto. Cada
perfil informa a relacao **rpm por km/h** de cada marcha, da 1a em diante:

```json
{
  "veiculos": [
    { "nome": "Polo Flex 1.6 2005 (manual)", "marchas": [124.6, 88.1, 56.3, 40.1, 31.8] }
  ]
}
```

Em vez de `marchas`, e possivel informar os dados de fabrica e o pneu, que o
programa converte:

```json
{
  "veiculos": [
    {
      "nome": "Meu carro",
      "relacoes_cambio": [3.45, 1.94, 1.28, 0.93, 0.76],
      "diferencial": 4.16,
      "pneu": "185/60R14"
    }
  ]
}
```

Perfis com o mesmo nome sobrescrevem os embutidos.

## Formato do CSV

Arquivo separado por `;`, com campos entre aspas:

```csv
"SECONDS";"PID";"VALUE";"UNITS";"LATITUDE";"LONGTITUDE";
"47529.6912562";"Velocidade do veículo";"0";"km/h";"-27.2262389";"-52.0224716";
```

Cada linha e a leitura de um parametro (`PID`) em um instante (`SECONDS`).
O leitor interpreta corretamente nomes de parametro que contem quebras de
linha dentro das aspas.

## Estrutura

```
grafico-scanner/
├── main.py                  # ponto de entrada
├── run.sh                   # cria a venv e executa
├── requirements.txt
├── veiculos.json            # perfis de marchas por veiculo
└── grafico_scanner/
    ├── parser.py            # leitura/normalizacao do CSV
    ├── analysis.py          # metricas e resumo
    ├── charts.py            # figuras Matplotlib
    ├── mapview.py           # mapa do trajeto (com fallback)
    ├── veiculos.py          # perfis de veiculo (marchas)
    └── app.py               # interface Tkinter
```

## Observacoes

- O mapa depende de internet para baixar os tiles do OpenStreetMap.
- Se as coordenadas GPS variarem muito pouco no log (GPS impreciso/sem fix),
  o aplicativo avisa e o mapa pode ficar impreciso.
