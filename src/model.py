"""Modulo del Modelo de Optimizacion (conVRP-SLA).

Formulacion algebraica reducida en gurobipy basada en Campelo et al. (2019):
- Funcion objetivo (1)
- Asignacion cliente-ruta (2)
- Conservacion de flujo de clientes (3)-(4)
- Salida del deposito (5)
- Seguimiento de tiempos mediante Big-M (7) y ventanas de tiempo (8)
- Horarios de salida/retorno y horario de operacion de deposito (9)-(12)
- Restriccion de capacidad de vehiculo Q (14)
- Condiciones de integralidad y no negatividad (16)
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Set, Tuple
try:
    import gurobipy as gp
    from gurobipy import GRB
except ImportError:
    gp = None
    GRB = None


def configure_solver_parameters(
    model: gp.Model,
    params: Optional[Dict[str, Any]] = None
) -> None:
    """Configura parametros de ejecucion del solver Gurobi.

    Parametros base exigidos por el enunciado:
    - Threads: 1
    - TimeLimit: 600 segundos
    """
    model.setParam("Threads", 1)
    model.setParam("TimeLimit", 600)

    if params:
        for key, value in params.items():
            model.setParam(key, value)


def build_convrp_model(
    data: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
    continuous_relaxation: bool = False
) -> Tuple[gp.Model, Dict[str, Any]]:
    """Construye la formulacion en gurobipy segun la version reducida del paper.

    Args:
        data: Diccionario con conjuntos y parametros procesados por data_loader.
        params: Diccionario opcional con parametros de configuracion del solver.
        continuous_relaxation: True para relajar variables enteras a continuas [0, 1].

    Returns:
        Tupla (model, refs) donde refs es un diccionario con:
        - 'X': gp.tupledict con variables de ruteo de arcos X[i, j, t, r].
        - 'Z': gp.tupledict con asignacion cliente-ruta consistente Z[i, r].
        - 'W': gp.tupledict con horarios de inicio de atencion W[i, t].
        - 'dW': gp.tupledict con horario de salida de ruta desde el deposito dW[r].
        - 'rW': gp.tupledict con horario de retorno de ruta al deposito rW[r, t].
        - 'capacity_constrs': Dict[(r, t), gp.Constr] con restricciones de capacidad.
        - 'data': Diccionario original de datos de la instancia procesada.
    """
    if gp is None:
        raise ImportError("gurobipy no esta instalado o no se pudo importar.")

    model = gp.Model(f"conVRP_SLA_{data.get('name', 'instance')}")

    # --- 1. Conjuntos y parametros ---
    NC: List[int] = data["NC"]                  # Clientes reales {1, ..., n}
    depot_start: int = data["depot_start"]      # Nodo salida deposito (0)
    depot_end: int = data["depot_end"]          # Nodo retorno deposito (n + 1)
    N: List[int] = data["N"]                    # Todos los nodos: {0} U NC U {n+1}
    days: List[int] = data["days"]              # Dias de planificacion D
    routes: List[int] = data["routes"]          # Rutas / vehiculos disponibles R
    NTW: List[int] = data["NTW"]                # Clientes con ventana de tiempo (N_TW)
    O: Set[Tuple[int, int]] = set(data["O"])    # Ordenes activas (i, t) con demanda > 0
    A: List[Tuple[int, int, int]] = data["A"]   # Arcos dirigidos validos (i, j, t)

    td: Dict[Tuple[int, int], float] = data["td"]       # Distancia de viaje entre nodos (i, j)
    tt: Dict[Tuple[int, int], float] = data["tt"]       # Tiempo de viaje entre nodos (i, j)
    q: Dict[Tuple[int, int], float] = data["q"]         # Demanda del cliente i en dia t (q_it)
    st: Dict[Tuple[int, int], float] = data["st"]       # Tiempo de atencion del cliente i en dia t (st_it)
    tw: Dict[int, Tuple[float, float]] = data["tw"]     # Ventana horaria [a_i, b_i] de cada cliente i
    aW: float = data["aW"]                              # Apertura mas temprana del deposito
    bW: float = data["bW"]                              # Cierre mas tardio del deposito
    Q: float = data["Q"]                                # Capacidad maxima del vehiculo
    M: float = data["M"]                                # Constante Big-M para cotas de tiempo

    # --- 2. Variables de decision ---
    vtype_bin = GRB.CONTINUOUS if continuous_relaxation else GRB.BINARY

    # X[i, j, t, r]: 1 si la ruta r recorre el arco (i, j) en dia t; 0 e.o.c.
    arc_indices = [(i, j, t, r) for (i, j, t) in A for r in routes]
    X = model.addVars(arc_indices, lb=0.0, ub=1.0, vtype=vtype_bin, name="X")

    # Z[i, r]: 1 si el cliente i es asignado a la ruta r (consistente en todo D)
    Z = model.addVars(NC, routes, lb=0.0, ub=1.0, vtype=vtype_bin, name="Z")

    # W[i, t]: momento de atencion del cliente i en dia t (W_it >= 0)
    W = model.addVars(NC, days, lb=0.0, vtype=GRB.CONTINUOUS, name="W")

    # dW[r]: horario de salida de la ruta r desde el deposito (dW^r >= 0)
    dW = model.addVars(routes, lb=0.0, vtype=GRB.CONTINUOUS, name="dW")

    # rW[r, t]: horario de retorno de la ruta r al deposito en dia t (rW_t^r >= 0)
    rW = model.addVars(routes, days, lb=0.0, vtype=GRB.CONTINUOUS, name="rW")

    # --- 3. Funcion objetivo (1): Minimizar distancia total ---
    obj_dist = gp.quicksum(
        td[i, j] * X[i, j, t, r]
        for (i, j, t) in A
        for r in routes
    )
    model.setObjective(obj_dist, GRB.MINIMIZE)

    # --- 4. Restricciones del paper ---
    # Precomputar vecinos entrantes y salientes para cada (nodo, dia)
    in_neighbors: Dict[Tuple[int, int], List[int]] = {(node, t): [] for node in N for t in days}
    out_neighbors: Dict[Tuple[int, int], List[int]] = {(node, t): [] for node in N for t in days}
    for (i, j, t) in A:
        in_neighbors[(j, t)].append(i)
        out_neighbors[(i, t)].append(j)

    # (2) Asignacion unica cliente-ruta (consistencia de conductor)
    for i in NC:
        model.addConstr(
            gp.quicksum(Z[i, r] for r in routes) == 1,
            name=f"assign_{i}"
        )

    # (3) Conservacion de flujo de entrada a clientes
    for j in NC:
        for r in routes:
            for t in days:
                rhs = Z[j, r] if (j, t) in O else 0
                model.addConstr(
                    gp.quicksum(X[i, j, t, r] for i in in_neighbors[(j, t)]) == rhs,
                    name=f"flow_in_{j}_{r}_{t}"
                )

    # (4) Conservacion de flujo de salida de clientes
    for i in NC:
        for r in routes:
            for t in days:
                rhs = Z[i, r] if (i, t) in O else 0
                model.addConstr(
                    gp.quicksum(X[i, j, t, r] for j in out_neighbors[(i, t)]) == rhs,
                    name=f"flow_out_{i}_{r}_{t}"
                )

    # (5) Salida diaria obligatoria del deposito por ruta (bypass 0 -> n+1 si inactiva)
    for t in days:
        for r in routes:
            model.addConstr(
                gp.quicksum(X[depot_start, j, t, r] for j in out_neighbors[(depot_start, t)]) == 1,
                name=f"depot_out_{r}_{t}"
            )

    # (7) Seguimiento temporal entre clientes y eliminacion de subtours (Big-M)
    for (i, j, t) in A:
        if i in NC and j in NC:
            for r in routes:
                model.addConstr(
                    W[i, t] + st[i, t] + tt[i, j] <= W[j, t] + M * (1.0 - X[i, j, t, r]),
                    name=f"time_link_{i}_{j}_{t}_{r}"
                )

    # (8) Cumplimiento de ventanas de tiempo para clientes en NTW con orden activa
    for (i, t) in O:
        if i in NTW:
            ai, bi = tw[i]
            model.addConstr(W[i, t] >= ai, name=f"tw_lb_{i}_{t}")
            model.addConstr(W[i, t] <= bi, name=f"tw_ub_{i}_{t}")

    # (9) Coordinacion de salida del deposito hacia el primer cliente
    for (i, j, t) in A:
        if i == depot_start and j in NC:
            for r in routes:
                model.addConstr(
                    dW[r] + tt[depot_start, j] <= W[j, t] + M * (1.0 - X[depot_start, j, t, r]),
                    name=f"depot_depart_{j}_{t}_{r}"
                )

    # (10) Coordinacion de retorno al deposito desde el ultimo cliente
    for (i, j, t) in A:
        if j == depot_end and i in NC:
            for r in routes:
                model.addConstr(
                    W[i, t] + st[i, t] + tt[i, depot_end] <= rW[r, t] + M * (1.0 - X[i, depot_end, t, r]),
                    name=f"depot_return_{i}_{t}_{r}"
                )

    # (11)-(12) Horarios de operacion del deposito (apertura aW, cierre bW)
    for r in routes:
        model.addConstr(dW[r] >= aW, name=f"depot_open_{r}")
        for t in days:
            model.addConstr(rW[r, t] <= bW, name=f"depot_close_{r}_{t}")

    # (14) Capacidad maxima del vehiculo Q (almacenada para analisis de sensibilidad)
    capacity_constrs: Dict[Tuple[int, int], gp.Constr] = {}
    for r in routes:
        for t in days:
            c = model.addConstr(
                gp.quicksum(q[i, t] * Z[i, r] for i in NC) <= Q,
                name=f"capacity_{r}_{t}"
            )
            capacity_constrs[(r, t)] = c

    # --- 5. Parametros del solver y retorno ---
    configure_solver_parameters(model, params)

    refs: Dict[str, Any] = {
        "X": X,
        "Z": Z,
        "W": W,
        "dW": dW,
        "rW": rW,
        "capacity_constrs": capacity_constrs,
        "data": data,
    }

    return model, refs
