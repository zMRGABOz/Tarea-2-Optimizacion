# Tarea 3 - Optimizacion: conVRP-SLA (Gurobi vs. CPLEX)

Implementacion, validacion cruzada y evaluacion computacional comparativa entre **Gurobi** y **IBM ILOG CPLEX** para el problema de ruteo vehicular consistente con acuerdos de nivel de servicio (conVRP-SLA), basado en Campelo et al. (2019).

## Correcciones respecto a TC2

- **Flujo (ecs. 3-4):** un cliente sin pedido en un dia ya no tiene arcos, restricciones de flujo ni variable de horario ese dia (`src/data_loader.py`, `src/model.py`, `src/cplex_model.py`).
- **Instancias con estructura multi-dia real:** cada consultorio pide 3, 2 o 1 dia (39 de 54 pedidos posibles), en vez de que casi todos pidan todos los dias. Detalle en [contexto_escenario.md](contexto_escenario.md).
- **Configuracion por defecto:** los modelos ya no fijan `Threads` ni `TimeLimit`; la comparacion Gurobi vs CPLEX usa la configuracion por defecto de cada solver. Los experimentos de TC2 siguen usando `Threads=1` y `TimeLimit=600` de forma explicita.

## Origen de Datos y Formato de Instancias

Las instancias siguen el formato del benchmark de **Solomon (1987) para VRPTW** de CVRPLIB ([CVRPLIB Instances](https://galgos.inf.puc-rio.br/cvrplib/en/instances), categoria VRPTW), con datos sinteticos propios y la dimension multi-dia construida por el grupo.

### Extension Multi-Dia (.txt)
Dado que las instancias originales de Solomon consideran un unico dia, se extiende su formato en archivos de texto plano (`.txt`) para incorporar la dimension multi-periodo y la consistencia de conductor:
- Cabecera con parametros globales: `DAYS` (ej. 3), `ROUTES` (ej. 3), `CAPACITY` ($Q$) y `BIG_M`.
- Tabla de clientes con demandas independientes por dia (`DEMAND_D1`, `DEMAND_D2`, `DEMAND_D3`). Una demanda 0 significa que el cliente no pide ese dia.
- El registro `0` define las coordenadas y la ventana de operacion del deposito (`READY_TIME` = $aW$, `DUE_DATE` = $bW$).
- Los registros `1` a `N` definen clientes con sus ventanas de entrega (`READY_TIME` = $a_i$, `DUE_DATE` = $b_i$) y tiempo de atencion (`SERVICE_TIME` = $st_i$).

### Generacion y graficos
Las dos instancias (18 clientes, 3 dias, 3 rutas) se generan de forma reproducible y se grafican con:
```bash
python3 instances/generar_instancias.py     # escribe instances/muestras_*.txt
python3 instances/graficar_instancias.py    # escribe instances/graficos/*.png
```

El archivo [instances/sample_toy.txt](instances/sample_toy.txt) es una muestra minima (4 clientes) para verificar que todo funciona.

## Estructura del Repositorio

```text
Tarea 2 Optimización/
├── .gitignore          # Archivos y patrones excluidos de git
├── README.md           # Guia tecnica y comandos de ejecucion
├── requirements.txt    # Dependencias de Python (gurobipy, cplex, docplex, pandas)
├── main.py             # Punto de entrada unificado por CLI (--solver / --mode)
├── contexto_escenario.md # Escenario, instancias y correcciones respecto a TC2
├── instances/          # Instancias de evaluacion (.txt)
│   ├── sample_toy.txt  # Muestra minima de verificacion
│   ├── muestras_A_barrios.txt
│   ├── muestras_B_dispersa.txt
│   ├── generar_instancias.py  # Generador reproducible de las instancias
│   ├── graficar_instancias.py # Mapas, demandas diarias y ventanas
│   └── graficos/       # Figuras de las instancias (.png)
├── src/                # Modulos del sistema
│   ├── __init__.py
│   ├── data_loader.py  # Lector de instancias tipo Solomon extendido
│   ├── model.py        # Formulacion reducida en Gurobi (gurobipy)
│   ├── cplex_model.py  # Formulacion equivalente en CPLEX (docplex.mp)
│   ├── solver_adapter.py # Capa adaptadora unificada y normalizacion de metricas
│   ├── experiments.py  # Bateria de benchmarks y tuning
│   └── sensitivity.py  # Analisis de sensibilidad post-optimo
└── results/
    ├── muestras_*/     # Resultados de TC2 (benchmark, tuning, sensibilidad)
    └── tc3/<instancia>/ # Comparacion Gurobi vs CPLEX: comparacion.csv/.json,
                         # modelo_gurobi.lp, modelo_cplex.lp y logs/*.log
```

## Requisitos e Instalacion

Requisitos: Python 3.10+ con licencia activa de Gurobi e instalacion de IBM ILOG CPLEX Optimization Studio **completa** (version academica, no Community Edition: la Community limita los modelos a 1.000 variables y 1.000 restricciones, y nuestras instancias tienen ~1.750 variables).

1. Crear y activar entorno virtual:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```

3. Quitar el limite de tamano de CPLEX en Python, apuntando a la instalacion completa:
   ```bash
   docplex config --upgrade "C:\Program Files\IBM\ILOG\CPLEX_Studio222"
   ```

En Windows, si hay varios Python instalados, usar el mismo en todos los pasos (por ejemplo `py -3.13` en vez de `python3`).

## Modos de Ejecucion (CLI)

El punto de entrada principal es `main.py`, que permite seleccionar el solver mediante `--solver {gurobi, cplex, compare}` y el modo de operacion mediante `--mode`:

### 1. Validacion Cruzada Directa (Gurobi vs. CPLEX)
Ejecuta secuencialmente la Relajacion Continua y el Modelo Entero en ambos motores sobre la misma instancia, con la **configuracion por defecto** de cada solver (sin limite de tiempo ni de hilos), imprime la tabla comparativa y guarda los resultados en `results/tc3/<instancia>/`:
```bash
python3 main.py --instance instances/muestras_A_barrios.txt --solver compare
python3 main.py --instance instances/muestras_B_dispersa.txt --solver compare
```

Archivos generados:
- `comparacion.csv`: una fila por fase (relajacion / entero) y solver.
- `comparacion.json`: lo mismo, mas el tamano del modelo en cada solver y las versiones usadas.
- `logs/gurobi_relax.log`, `logs/cplex_relax.log`, `logs/gurobi_milp.log`, `logs/cplex_milp.log`.

Metricas reportadas:
- **Relajacion continua**: $z_{LP}$, tiempo de computo (s), iteraciones simplex y estatus.
- **Modelo entero**: $z_{MILP}$, cota inferior (*best bound*), MIPGap final (%), tiempo (s), nodos explorados y estatus.
- **Brecha de integralidad**: $\frac{z_{MILP} - z_{LP}}{z_{MILP}} \times 100\%$.

Las corridas de ambas instancias deben hacerse una despues de la otra (no en paralelo), para que los solvers no compitan por los nucleos. El `.gitignore` excluye `*.log` y `*.lp`; para versionarlos usar `git add -f`.

### 2. Resolucion Estandar (MILP Base)
Resuelve el modelo entero bajo configuracion por defecto en el solver seleccionado (`gurobi` o `cplex`):
```bash
# En Gurobi
python3 main.py --instance instances/sample_toy.txt --solver gurobi --mode solve

# En CPLEX
python3 main.py --instance instances/sample_toy.txt --solver cplex --mode solve
```

### 3. Relajacion Continua y Brecha de Integralidad
Resuelve la relajacion continua ($z_{LP}$) fijando variables binarias a continuas $[0, 1]$, calcula el valor entero ($z_{MILP}$) y reporta la brecha de integralidad:
```bash
# En Gurobi
python3 main.py --instance instances/sample_toy.txt --solver gurobi --mode relax

# En CPLEX
python3 main.py --instance instances/sample_toy.txt --solver cplex --mode relax
```

### 4. Exportacion a Formato LP
Permite volcar el modelo canónico generado a un archivo `.lp` para auditar variables y restricciones:
```bash
python3 main.py --instance instances/sample_toy.txt --solver cplex --export-lp results/modelo_cplex.lp
```
Despues de exportar, `main.py` continua con el `--mode` indicado (por defecto `solve`). Los `.lp` de las instancias de TC3 estan en `results/tc3/<instancia>/modelo_gurobi.lp` y `modelo_cplex.lp`: ambos tienen las mismas variables, restricciones y coeficientes.

Los modos 5 a 7 corresponden a la Tarea 2 (solo Gurobi).

### 5. Comparacion de Configuraciones del Solver (Gurobi, TC2)
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

### 6. Ajuste Automatico de Parametros (Tuning)
Ejecuta `model.tune()` en Gurobi con tiempo limite configurable:
```bash
python3 main.py --instance instances/sample_toy.txt --mode tune --tune-time 120
```

### 7. Analisis de Sensibilidad Post-Optimo
Fija las variables enteras a su valor optimo (`model.fixed()`) y analiza el precio sombra (`Pi`) y rangos de validez (`SARHSLow` / `SARHSUp`) para la capacidad $Q$:
```bash
python3 main.py --instance instances/sample_toy.txt --mode sensitivity
```
