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
| Clientes | 15 | 16 |
| Clientes con ventana horaria | 10 | 13 |
| Capacidad Q | 71 | 61 |
| Cierre del laboratorio (bW) | 240 min | 290 min |
| Big-M | 336 | 394 |
| Utilización de capacidad (días 1/2/3) | 91% / 71% / 74% | 80% / 84% / 90% |
| Arcos descartados por las ventanas | 26% | 38% |

Los clientes sin ventana propia conservan el horario completo del laboratorio, `[0, bW]`, y por eso el modelo no les aplica la restricción (8).

### Cómo se construyeron

1. Se generan las coordenadas, según el tipo de distribución.
2. Se asigna a cada consultorio una demanda base. Algunos se atienden los 3 días y otros solo 2, con variación diaria del ±25%.
3. Se arma una solución de referencia (plantada): 3 rutas por barrido angular alrededor del laboratorio, con el orden de visita por vecino más cercano.
4. La capacidad Q se fija a partir de la mayor carga de esa solución, con un margen del 5% (instancia A) y del 3% (instancia B).
5. Las ventanas se derivan de los tiempos de llegada de la solución de referencia, con una holgura de 20 min (A) y 15 min (B), y se elige qué clientes tendrán ventana.

Con este procedimiento ambas instancias son **factibles por construcción**. La solución de referencia no es el óptimo, así que el solver tiene un ruteo mejor que encontrar. Las instancias se pueden regenerar con `generar_instancias.py` (semillas 11 y 23).

## Archivos

- `instances/muestras_A_barrios.txt`
- `instances/muestras_B_dispersa.txt`

## Referencia

Campelo, P., Neves-Moreira, F., Amorim, P., & Almada-Lobo, B. (2019). Consistent vehicle routing problem with service level agreements: A case study in the pharmaceutical distribution sector. *European Journal of Operational Research, 273*(1), 131–145.
