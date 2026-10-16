# Tarea 2 - Optimizacion: conVRP-SLA

Implementacion y evaluacion computacional en Gurobi de una version reducida del problema de ruteo vehicular consistente con acuerdos de nivel de servicio (conVRP-SLA), basado en Campelo et al. (2019).

## Origen de Datos y Formato de Instancias

Las instancias de prueba se construyen a partir del benchmark de **Solomon (1987) para VRPTW** disponible en CVRPLIB:
- Enlace oficial: [CVRPLIB Instances](https://galgos.inf.puc-rio.br/cvrplib/en/instances) (Categoria VRPTW)

### Extension Multi-Dia (.txt)
Dado que las instancias originales de Solomon consideran un unico dia, se extiende su formato en archivos de texto plano (`.txt`) para incorporar la dimension multi-periodo y la consistencia de conductor:
- Cabecera con parametros globales: `DAYS` (ej. 3), `ROUTES` (ej. 3), `CAPACITY` ($Q$) y `BIG_M`.
- Tabla de clientes con demandas independientes por dia (`DEMAND_D1`, `DEMAND_D2`, `DEMAND_D3`).
- El registro `0` define las coordenadas y la ventana de operacion del deposito (`READY_TIME` = $aW$, `DUE_DATE` = $bW$).
- Los registros `1` a `N` definen clientes con sus ventanas de entrega (`READY_TIME` = $a_i$, `DUE_DATE` = $b_i$) y tiempo de atencion (`SERVICE_TIME` = $st_i$).

El archivo [instances/sample_toy.txt](instances/sample_toy.txt) sirve como plantilla de referencia para la construccion de las instancias definitivas.

## Estructura del Repositorio

```text
Tarea 2 Optimización/
├── .gitignore         # Archivos y patrones excluidos de git
├── README.md          # Guia tecnica y comandos de ejecucion
├── requirements.txt   # Dependencias de Python
├── main.py            # Punto de entrada unificado por CLI
├── instances/         # Instancias de evaluacion (.txt)
│   └── sample_toy.txt # Plantilla y muestra minima de verificacion
├── src/               # Modulos del sistema
│   ├── __init__.py
│   ├── data_loader.py # Lector de instancias tipo Solomon extendido
│   ├── model.py       # Formulacion algebraica reducida en gurobipy
│   ├── experiments.py # Relajacion continua, benchmarks de solver y tuning
│   └── sensitivity.py # Analisis de sensibilidad con model.fixed()
└── results/           # Archivos de salida (.prm, tablas y logs)
```

## Requisitos e Instalacion

Requisitos: Python 3.10+ y licencia activa de Gurobi.

1. Crear y activar entorno virtual:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```

## Modos de Ejecucion (CLI)

El archivo `main.py` permite ejecutar las distintas fases de analisis mediante el argumento `--mode`:

### 1. Resolucion Estandar (MILP Base)
Resuelve la instancia con el modelo entero bajo parametros predeterminados:
```bash
python3 main.py --instance instances/sample_toy.txt --mode solve
```

### 2. Relajacion Continua y Brecha de Integralidad
Resuelve la relajacion continua ($z_{LP}$), obtiene el valor entero ($z_{MILP}$) y calcula la brecha:
$$\text{Brecha} = \frac{z_{MILP} - z_{LP}}{z_{MILP}} \times 100\%$$
```bash
python3 main.py --instance instances/sample_toy.txt --mode relax
```

### 3. Comparacion de Configuraciones del Solver
Ejecuta la bateria de pruebas con 1 hilo (`Threads=1`) y 600 segundos (`TimeLimit=600`):
- Baseline (por defecto)
- Cuts=0
- Presolve=0
- MIPFocus=1
- MIPFocus=3
- Heuristics=0

```bash
python3 main.py --instance instances/sample_toy.txt --mode benchmark
```

### 4. Ajuste Automatico de Parametros (Tuning)
Ejecuta `model.tune()` con un tiempo limite configurable y exporta el mejor perfil a `results/best_tune.prm`:
```bash
python3 main.py --instance instances/sample_toy.txt --mode tune --tune-time 120
```

### 5. Analisis de Sensibilidad Post-Optimo
Fija las variables enteras a su valor optimo (`model.fixed()`) y analiza el precio sombra (`Pi`) y los rangos de validez del lado derecho (`SARHSLow` / `SARHSUp`) para la restriccion de capacidad $Q$:
```bash
python3 main.py --instance instances/sample_toy.txt --mode sensitivity
```
