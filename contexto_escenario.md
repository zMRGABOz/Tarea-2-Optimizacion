# Contexto: ruteo consistente para el retiro de muestras clínicas

Tarea Computacional 2 de Optimización · Modelo conVRP-SLA reducido (Campelo et al., 2019) en gurobipy


## 1. Situación

Un laboratorio clínico central procesa las muestras de sangre y orina que le envían consultorios y centros médicos pequeños de una ciudad. Cada día, una flota de **3 vehículos** sale del laboratorio, retira las muestras listas en los consultorios y las trae de vuelta para su análisis. La planificación cubre **3 días**.

El laboratorio quiere minimizar la **distancia total recorrida** por su flota durante los 3 días, respetando:

- la capacidad de carga refrigerada de cada vehículo,
- la ventana horaria de cada consultorio,
- el horario de operación del laboratorio.

## 2. Por qué se necesita consistencia

Cada consultorio es atendido por **el mismo conductor/vehículo en todos los días** en que tiene retiro. Las razones del negocio son:

- **Cadena de custodia:** el conductor asignado está registrado y autorizado en el consultorio, y firma la entrega de las muestras. Cambiar de conductor cada día obliga a repetir trámites de identificación y registro.
- **Personal autorizado:** muchos consultorios solo entregan muestras a personas que conocen y que figuran en su protocolo de acceso.
- **Conocimiento del lugar:** el conductor aprende dónde estacionar, por qué acceso entrar y a quién entregarle el bulto. Eso reduce el tiempo de servicio.

En el modelo, esto se representa con la variable `Z[i,r]`: cada cliente `i` queda asignado a una única ruta `r` para todo el horizonte. Es la restricción (2) del paper.

## 3. Cómo se interpreta cada elemento del modelo

| Elemento del modelo | Interpretación en el escenario |
|---|---|
| Depósito (nodo 0 y n+1) | Laboratorio central, con coordenadas (50, 50) |
| Cliente `i` | Consultorio que entrega muestras |
| Ruta `r` (3 por día) | Vehículo con su conductor fijo |
| Demanda `q[i,t]` | Muestras a retirar el día `t` (en unidades de volumen) |
| Demanda 0 un día | El consultorio no tiene retiro ese día |
| Capacidad `Q` | Capacidad refrigerada del vehículo, en las mismas unidades |
| `READY_TIME` (a_i) | Instante desde el cual las muestras están listas |
| `DUE_DATE` (b_i) | Último instante para comenzar el retiro sin comprometer la estabilidad de la muestra |
| `SERVICE_TIME` (st_i) | Tiempo en el consultorio: registro, custodia y embalaje en frío |
| Horario del depósito (aW, bW) | Apertura y cierre de recepción del laboratorio |
| Distancia / tiempo de viaje | Distancia euclidiana, con velocidad unitaria |

**Unidad de tiempo:** minutos desde la apertura del laboratorio. Por ejemplo, 0 corresponde a las 07:00.

## 4. Las dos instancias

Se generaron dos instancias propias con la misma estructura (3 días, 3 rutas por día, depósito en el centro de una grilla de 100 × 100) y geografías contrastantes. Siguen el estilo de las instancias de Solomon (1987) para VRPTW, pero con datos sintéticos y con la dimensión multi-día construida por nosotros. No se tomaron coordenadas de CVRPLIB.

| | `muestras_A_barrios` | `muestras_B_dispersa` |
|---|---|---|
| Distribución geográfica | 3 barrios compactos (estilo Solomon C) | Consultorios dispersos de forma uniforme (estilo Solomon R) |
| Clientes | 18 | 18 |
| Frecuencia de retiro (3 / 2 / 1 días) | 7 / 7 / 4 clientes | 7 / 7 / 4 clientes |
| Pedidos por día (D1 / D2 / D3) | 13 / 13 / 13 (39 de 54 posibles) | 13 / 13 / 13 (39 de 54 posibles) |
| Clientes con ventana horaria | 9 | 9 |
| Capacidad Q | 88 | 78 |
| Cierre del laboratorio (bW) | 260 min | 310 min |
| Big-M | 352 | 415 |
| Utilización de capacidad (días 1/2/3) | 60% / 61% / 62% | 74% / 62% / 67% |

Los clientes sin ventana propia conservan el horario completo del laboratorio, `[0, bW]`, y por eso el modelo no les aplica la restricción (8).

### Correcciones respecto a TC2

- **Estructura multi-día real.** En TC2 casi todos los consultorios pedían los 3 días (11 de 15 en A y 10 de 16 en B). Ahora cada consultorio tiene una frecuencia de retiro: diaria, 2 de los 3 días o 1 solo día, con los días sin pedido rotando para que la carga quede pareja (13 pedidos por día).
- **Tamaño calibrado.** Con menos pedidos por día el problema se achica: con 16 clientes ambos solvers cerraban en menos de 3 s, y con 20 Gurobi no cerraba en 90 s. Con 18 clientes y ventanas más anchas (que debilitan la relajación del Big-M) las instancias no son triviales y Gurobi prueba optimalidad en ~1,5 min.
- **Un cliente sin pedido un día no se visita ese día.** El modelo ya no crea arcos, flujo ni horario para el par (cliente, día) sin demanda.

### Cómo se construyeron

El script `instances/generar_instancias.py` las genera de forma reproducible (semillas 11 y 23):

1. Se generan las coordenadas, según el tipo de distribución.
2. Cada consultorio recibe una frecuencia (3, 2 o 1 día) y una demanda base de 6 a 20 unidades, con variación diaria del ±25% en los días en que pide.
3. Se arma una solución de referencia consistente: los consultorios se reparten en 3 rutas por barrido angular alrededor del laboratorio y, cada día, cada ruta visita a sus consultorios con pedido por vecino más cercano.
4. La capacidad Q se fija desde la mayor carga diaria de esa solución, con un margen del 3%.
5. La mitad de los consultorios recibe ventana horaria: cubre sus horas de llegada en todos los días en que pide, con 30 min de holgura.
6. El cierre del laboratorio y el Big-M se calculan desde la misma solución y la mayor distancia entre nodos.

Con este procedimiento ambas instancias son **factibles por construcción**. La solución de referencia no es el óptimo, así que el solver tiene un ruteo mejor que encontrar.

- `instances/muestras_A_barrios.txt`
- `instances/muestras_B_dispersa.txt`

### Gráficos

`instances/graficar_instancias.py` genera en `instances/graficos/`, para cada instancia, el mapa de consultorios (color según frecuencia, relleno si tiene ventana), la matriz de demandas diarias (– = no pide) y las ventanas de tiempo frente al horario del laboratorio. Hay una figura completa (`<instancia>.png`) y cada panel por separado.

## Referencia

Campelo, P., Neves-Moreira, F., Amorim, P., & Almada-Lobo, B. (2019). Consistent vehicle routing problem with service level agreements: A case study in the pharmaceutical distribution sector. *European Journal of Operational Research, 273*(1), 131–145.
