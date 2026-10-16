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
from typing import Any, Dict, Optional, Tuple
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
    model.Params.Threads = 1
    model.Params.TimeLimit = 600

    if params:
        for key, value in params.items():
            if hasattr(model.Params, key):
                setattr(model.Params, key, value)
            else:
                raise KeyError(f"Parametro de Gurobi no reconocido: {key}")


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
        Tupla (model, refs) con el objeto gp.Model y referencias a variables/restricciones.
    """
    # Pasos de implementacion de la formulacion:
    # 1. Extraer conjuntos: NC, depot_start, depot_end, N, days, routes, NTW, O, A
    # 2. Extraer parametros: td, tt, q, st, tw, aW, bW, Q, M
    # 3. Declarar variables: X (arcos), Z (asignacion), W (llegadas), dW (salida dep), rW (retorno dep)
    # 4. Definir funcion objetivo (1): minimizar distancia total
    # 5. Agregar restricciones (2), (3)-(4), (5), (7)-(8), (9)-(12), (14)
    # 6. Configurar parametros de solver

    raise NotImplementedError(
        "build_convrp_model pendiente de implementacion."
    )
