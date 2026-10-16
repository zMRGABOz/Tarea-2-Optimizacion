"""Modulo de analisis de sensibilidad post-optimo.

Tareas a evaluar segun la pauta:
1. Tomar el modelo con la mejor solucion entera encontrada.
2. Fijar las variables binarias a sus valores optimos mediante model.fixed().
3. Resolver el problema lineal resultante (LP fijado).
4. Extraer el precio sombra (Pi) y los rangos de validez del lado derecho
   (SARHSLow / SARHSUp) para la restriccion de capacidad del vehiculo Q (14).
5. Interpretar los resultados de sensibilidad.
"""

from __future__ import annotations
from typing import Any, Dict, List
try:
    import gurobipy as gp
    from gurobipy import GRB
except ImportError:
    gp = None
    GRB = None

from src.model import build_convrp_model


def run_capacity_sensitivity_analysis(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Ejecuta el analisis de sensibilidad fijando variables binarias con model.fixed().

    Args:
        data: Datos de la instancia procesada.

    Returns:
        Lista de diccionarios con el reporte de precios sombra y rangos de validez de Q.
    """
    raise NotImplementedError(
        "run_capacity_sensitivity_analysis pendiente de implementacion."
    )
