# Benchmark de utilização (Libnest2D)

Compara diferentes configurações do engine (selection, try_triplets, parâmetros DJD) para maximizar o aproveitamento de chapas.

## Pré-requisitos

- API + worker + engine rodando (ex.: `docker compose up -d` na pasta nest-local)
- Python 3 com PyYAML: `pip install pyyaml`

## Uso

```bash
cd nest-local/benchmark
python run_benchmark.py --api-url http://localhost:8080 --cases cases --configs configs/max_quality.yaml --out results/run1.csv
```

- **--api-url:** Base URL da API (default: http://localhost:8080)
- **--cases:** Diretório com JSONs de casos (default: cases)
- **--configs:** Arquivo YAML com lista de configs (default: configs/max_quality.yaml)
- **--out:** Caminho do CSV de saída (default: results/benchmark.csv)

O script envia um job por (caso, config), faz poll com `?embed=result`, e grava para cada linha: case_id, config_name, utilization, bins_used, runtime_ms, status. No final imprime a média de utilização por config.

## Casos

- **rectangles.json** – Retângulos variados (100x50, 80x40, etc.)
- **irregular_L.json** – Formas em L e T
- **many_small.json** – Muitas peças pequenas
- **few_large.json** – Poucas peças grandes
- **mixed.json** – Mix de formatos

## Configuração para máxima utilização

Para **melhor aproveitamento** (aceitando mais CPU e tempo), use no payload:

```json
"options": {
  "selection": "djd",
  "try_triplets": true,
  "rotations": [0, 90, 180, 270],
  "timeout_ms": 120000,
  "initial_fill_proportion": 0.33,
  "waste_increment": 0.05
}
```

Aumente `ENGINE_TIMEOUT` no worker (env) para pelo menos o valor de timeout_ms em segundos (ex.: 120s).

## Nota (ambiente Digital Ocean)

O benchmark pode ser executado no Droplet via SSH (API em `http://localhost:8080`). No ambiente atual, o engine (libnest2d tamasmeszaros em Docker) devolve `bins_used=0` e `utilization=0` para os casos de teste; a API e o script de benchmark estão corretos (o campo `result` com `metrics` e `bins_used` é retornado quando há resultado). Se os valores continuarem zerados, investigar versão/ build do libnest2d ou considerar o fork Ultimaker com outro fluxo de build.
