"""Modulo del Modelo de Optimizacion conVRP-SLA en CPLEX (docplex.mp).

Formulacion algebraica reducida basada en Campelo et al. (2019):
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
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from docplex.mp.model import Model
    from docplex.mp.constr import LinearConstraint
except ImportError:
    Model = None
    LinearConstraint = None


def export_lp(model: Model, filepath: str | Path) -> str:
    """Exporta la formulacion de CPLEX a formato LP."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    model.export_as_lp(str(path))
    return str(path.resolve())


def configure_solver_parameters(
    model: Model,
    params: Optional[Dict[str, Any]] = None
) -> None:
    """Configura parametros de ejecucion del solver CPLEX.

    Por defecto no se modifica ningun parametro (configuracion por defecto del
    solver, como exige la comparacion Gurobi vs CPLEX).
    """
    if params:
        for key, value in params.items():
            if hasattr(model.parameters, key):
                getattr(model.parameters, key).set(value)
            elif "." in key:
                parts = key.split(".")
                curr = model.parameters
                for p in parts:
                    curr = getattr(curr, p)
                curr.set(value)


def build_convrp_cplex_model(
    data: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
    continuous_relaxation: bool = False
) -> Tuple[Model, Dict[str, Any]]:
    """Construye la formulacion en docplex segun la version reducida del paper.

    Args:
        data: Diccionario con conjuntos y parametros procesados por data_loader.
        params: Diccionario opcional con parametros de configuracion del solver.
        continuous_relaxation: True para relajar variables enteras a continuas [0, 1].

    Returns:
        Tupla (model, refs) con referencias homólogas a la implementacion de Gurobi.
    """
    if Model is None:
        raise ImportError("docplex no esta instalado o no se pudo importar.")

    model = Model(name=f"conVRP_SLA_{data.get('name', 'instance')}")

    # --- 1. Conjuntos y parametros ---
    NC: List[int] = data["NC"]
    depot_start: int = data["depot_start"]
    depot_end: int = data["depot_end"]
    N: List[int] = data["N"]
    days: List[int] = data["days"]
    routes: List[int] = data["routes"]
    NTW: List[int] = data["NTW"]
    O: Set[Tuple[int, int]] = set(data["O"])
    A: List[Tuple[int, int, int]] = data["A"]

    td: Dict[Tuple[int, int], float] = data["td"]
    tt: Dict[Tuple[int, int], float] = data["tt"]
    q: Dict[Tuple[int, int], float] = data["q"]
    st: Dict[Tuple[int, int], float] = data["st"]
    tw: Dict[int, Tuple[float, float]] = data["tw"]
    aW: float = data["aW"]
    bW: float = data["bW"]
    Q: float = data["Q"]
    M: float = data["M"]

    # --- 2. Variables de decision ---
    arc_indices = [(i, j, t, r) for (i, j, t) in A for r in routes]
    z_indices = [(i, r) for i in NC for r in routes]
    w_indices = sorted(O)  # W solo para clientes con pedido ese dia
    rw_indices = [(r, t) for r in routes for t in days]

    if continuous_relaxation:
        X = model.continuous_var_dict(arc_indices, lb=0.0, ub=1.0, name="X")
        Z = model.continuous_var_dict(z_indices, lb=0.0, ub=1.0, name="Z")
    else:
        X = model.binary_var_dict(arc_indices, name="X")
        Z = model.binary_var_dict(z_indices, name="Z")

    W = model.continuous_var_dict(w_indices, lb=0.0, name="W")
    dW = model.continuous_var_dict(routes, lb=0.0, name="dW")
    rW = model.continuous_var_dict(rw_indices, lb=0.0, name="rW")

    # --- 3. Funcion objetivo (1): Minimizar distancia total ---
    obj_dist = model.sum(
        td[i, j] * X[i, j, t, r]
        for (i, j, t) in A
        for r in routes
    )
    model.minimize(obj_dist)

    # --- 4. Restricciones del paper ---
    in_neighbors: Dict[Tuple[int, int], List[int]] = {(node, t): [] for node in N for t in days}
    out_neighbors: Dict[Tuple[int, int], List[int]] = {(node, t): [] for node in N for t in days}
    for (i, j, t) in A:
        in_neighbors[(j, t)].append(i)
        out_neighbors[(i, t)].append(j)

    # (2) Asignacion unica cliente-ruta
    for i in NC:
        model.add_constraint(
            model.sum(Z[i, r] for r in routes) == 1,
            ctname=f"assign_{i}"
        )

    # (3) Conservacion de flujo de entrada: solo para clientes con pedido ese dia.
    # Un cliente sin pedido el dia t no tiene arcos en A, por lo que no se visita.
    for (j, t) in sorted(O):
        for r in routes:
            model.add_constraint(
                model.sum(X[i, j, t, r] for i in in_neighbors[(j, t)]) == Z[j, r],
                ctname=f"flow_in_{j}_{r}_{t}"
            )

    # (4) Conservacion de flujo de salida: solo para clientes con pedido ese dia
    for (i, t) in sorted(O):
        for r in routes:
            model.add_constraint(
                model.sum(X[i, j, t, r] for j in out_neighbors[(i, t)]) == Z[i, r],
                ctname=f"flow_out_{i}_{r}_{t}"
            )

    # (5) Salida diaria obligatoria del deposito por ruta
    for t in days:
        for r in routes:
            model.add_constraint(
                model.sum(X[depot_start, j, t, r] for j in out_neighbors[(depot_start, t)]) == 1,
                ctname=f"depot_out_{r}_{t}"
            )

    # (7) Seguimiento temporal entre clientes y eliminacion de subtours (Big-M)
    for (i, j, t) in A:
        if i in NC and j in NC:
            for r in routes:
                model.add_constraint(
                    W[i, t] + st[i, t] + tt[i, j] <= W[j, t] + M * (1.0 - X[i, j, t, r]),
                    ctname=f"time_link_{i}_{j}_{t}_{r}"
                )

    # (8) Cumplimiento de ventanas de tiempo para clientes en NTW con orden activa
    for (i, t) in O:
        if i in NTW:
            ai, bi = tw[i]
            model.add_constraint(W[i, t] >= ai, ctname=f"tw_lb_{i}_{t}")
            model.add_constraint(W[i, t] <= bi, ctname=f"tw_ub_{i}_{t}")

    # (9) Coordinacion de salida del deposito hacia el primer cliente
    for (i, j, t) in A:
        if i == depot_start and j in NC:
            for r in routes:
                model.add_constraint(
                    dW[r] + tt[depot_start, j] <= W[j, t] + M * (1.0 - X[depot_start, j, t, r]),
                    ctname=f"depot_depart_{j}_{t}_{r}"
                )

    # (10) Coordinacion de retorno al deposito desde el ultimo cliente
    for (i, j, t) in A:
        if j == depot_end and i in NC:
            for r in routes:
                model.add_constraint(
                    W[i, t] + st[i, t] + tt[i, depot_end] <= rW[r, t] + M * (1.0 - X[i, depot_end, t, r]),
                    ctname=f"depot_return_{i}_{t}_{r}"
                )

    # (11)-(12) Horarios de operacion del deposito
    for r in routes:
        model.add_constraint(dW[r] >= aW, ctname=f"depot_open_{r}")
        for t in days:
            model.add_constraint(rW[r, t] <= bW, ctname=f"depot_close_{r}_{t}")

    # (14) Capacidad maxima del vehiculo Q
    capacity_constrs: Dict[Tuple[int, int], Any] = {}
    for r in routes:
        for t in days:
            c = model.add_constraint(
                model.sum(q[i, t] * Z[i, r] for i in NC) <= Q,
                ctname=f"capacity_{r}_{t}"
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
