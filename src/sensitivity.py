"""Modulo de analisis de sensibilidad post-optimo.

Tareas a evaluar segun la pauta:
1. Tomar el modelo con la mejor solucion entera encontrada.
2. Fijar las variables binarias a sus valores optimos mediante model.fixed().
3. Resolver el problema lineal resultante (LP fijado).
4. Extraer el precio sombra (Pi) y los rangos de validez del lado derecho
   (SARHSLow / SARHSUp) para la restriccion de capacidad del vehiculo Q (14).
5. Interpretar los resultados de sensibilidad.
"""

from typing import Any, Dict, List
import gurobipy as gp
from gurobipy import GRB


from src.data_loader import load_instance
from src.model import build_convrp_model


def run_capacity_sensitivity_analysis(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Analiza la capacidad en el LP con decisiones enteras fixed"""

    # Armar modelo
    model, refs = build_convrp_model(data)
    fixed_model = None

    try:
        # Buscar solucion
        model.optimize()

        if model.SolCount == 0:
            raise RuntimeError(
                f"No se encontro una solucion entera. Codigo: {model.Status}"
            )

        if model.Status == GRB.OPTIMAL:
            print("Solucion optima encontrada")
        else:
            print("Optimo no encontrado, se revisara mejor. Codigo: {model.Status}")

        print(f"Distancia de referencia: {model.ObjVal:.4f}")
        print(f"Gap de referencia: {model.MIPGap * 100:.4f}%")

        # Crear modelo fijado (X, Z)
        fixed_model = model.fixed()

        # Simplex Dual
        fixed_model.Params.Method = 1
        fixed_model.Params.Threads = 1
        fixed_model.Params.TimeLimit = 600
        fixed_model.optimize()

        if fixed_model.Status != GRB.OPTIMAL:
            raise RuntimeError(
                f"El modelo fijado no termino optimo. Codigo: {fixed_model.Status}"
            )

        print(f"Distancia de modelo fijado: {fixed_model.ObjVal:.4f}")

        # Restricciones de capacidad
        results = []

        for (route, day), original_constr in refs["capacity_constrs"].items():
            constraint_name = original_constr.ConstrName
            capacity = fixed_model.getConstrByName(constraint_name)

            if capacity is None:
                raise RuntimeError(
                    f"No se encontro la restriccion {constraint_name}"
                )

            # Guardamos la fila
            results.append({
                "route": route,
                "day": day,
                "current_capacity_Q": capacity.RHS,
                "slack": capacity.Slack,
                "shadow_price_Pi": capacity.Pi,
                "sarhs_low": capacity.SARHSLow,
                "sarhs_up": capacity.SARHSUp,
            })
        return results

    finally:
        # Limpieza de objetos
        if fixed_model is not None:
            fixed_model.dispose()

        model.dispose()
