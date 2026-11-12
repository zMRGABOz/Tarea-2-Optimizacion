"""Capa adaptadora unificada para ejecucion y comparacion de solvers (Gurobi y CPLEX).

Normaliza parametros, extraccion de metricas, exportacion LP y resultados
para garantizar comparaciones reproducibles y desacopladas.
"""

from __future__ import annotations
from dataclasses import asdict, dataclass, field
import math
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from src.model import (
    build_convrp_model as build_gurobi_model,
    export_lp as export_gurobi_lp
)
from src.cplex_model import (
    build_convrp_cplex_model,
    export_lp as export_cplex_lp
)

_GUROBI_STATUS_MAP = {
    1: "LOADED",
    2: "OPTIMAL",
    3: "INFEASIBLE",
    4: "INF_OR_UNBD",
    5: "UNBOUNDED",
    9: "TIME_LIMIT",
    11: "INTERRUPTED",
    13: "SUBOPTIMAL",
}


@dataclass
class SolverResult:
    """Resultado estandarizado de la optimizacion independiente del solver."""
    solver: str
    status: str
    obj_val: Optional[float]
    best_bound: Optional[float]
    mip_gap_percent: Optional[float]
    runtime_sec: float
    node_count: int
    iterations: int
    sol_count: int
    is_optimal: bool
    continuous_relaxation: bool
    extra_info: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ModelStats:
    """Estadisticas estructurales de la matriz del modelo."""
    solver: str
    num_variables: int
    num_binary_vars: int
    num_continuous_vars: int
    num_constraints: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _normalize_solver_name(solver: str) -> str:
    name = solver.strip().lower()
    if name in ("gurobi", "gurobipy", "grb"):
        return "gurobi"
    if name in ("cplex", "docplex", "ibm"):
        return "cplex"
    raise ValueError(f"Solver no soportado: '{solver}'. Use 'gurobi' o 'cplex'.")


def get_model_stats(
    solver: str,
    data: Dict[str, Any],
    continuous_relaxation: bool = False
) -> ModelStats:
    """Retorna las dimensiones estructurales de la matriz del modelo en el solver dado."""
    s = _normalize_solver_name(solver)
    if s == "gurobi":
        m, _ = build_gurobi_model(data, continuous_relaxation=continuous_relaxation)
        stats = ModelStats(
            solver="gurobi",
            num_variables=m.NumVars,
            num_binary_vars=m.NumBinVars,
            num_continuous_vars=m.NumVars - m.NumBinVars,
            num_constraints=m.NumConstrs
        )
        m.dispose()
        return stats
    else:
        m, _ = build_convrp_cplex_model(data, continuous_relaxation=continuous_relaxation)
        return ModelStats(
            solver="cplex",
            num_variables=m.number_of_variables,
            num_binary_vars=m.number_of_binary_variables,
            num_continuous_vars=m.number_of_continuous_variables,
            num_constraints=m.number_of_constraints
        )


def export_lp(
    solver: str,
    data: Dict[str, Any],
    filepath: str | Path,
    continuous_relaxation: bool = False
) -> str:
    """Construye el modelo con el solver indicado y lo exporta a archivo .lp."""
    s = _normalize_solver_name(solver)
    if s == "gurobi":
        m, _ = build_gurobi_model(data, continuous_relaxation=continuous_relaxation)
        out = export_gurobi_lp(m, filepath)
        m.dispose()
        return out
    else:
        m, _ = build_convrp_cplex_model(data, continuous_relaxation=continuous_relaxation)
        return export_cplex_lp(m, filepath)


def _solve_gurobi(
    data: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
    continuous_relaxation: bool = False,
    log_file: Optional[str] = None
) -> Tuple[SolverResult, Any, Dict[str, Any]]:
    run_params = dict(params or {})
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        run_params["LogFile"] = str(log_file)

    model, refs = build_gurobi_model(
        data,
        params=run_params,
        continuous_relaxation=continuous_relaxation
    )
    model.optimize()

    status_str = _GUROBI_STATUS_MAP.get(model.Status, str(model.Status))
    has_sol = model.SolCount > 0
    obj_val = model.ObjVal if has_sol else None
    runtime = model.Runtime
    iters = int(model.IterCount)

    if continuous_relaxation:
        best_bound = obj_val
        gap = 0.0 if has_sol else None
        nodes = 0
    else:
        best_bound = model.ObjBound if has_sol else None
        gap = model.MIPGap * 100.0 if has_sol else None
        nodes = int(model.NodeCount)

    result = SolverResult(
        solver="gurobi",
        status=status_str,
        obj_val=obj_val,
        best_bound=best_bound,
        mip_gap_percent=gap,
        runtime_sec=runtime,
        node_count=nodes,
        iterations=iters,
        sol_count=model.SolCount,
        is_optimal=(model.Status == 2),
        continuous_relaxation=continuous_relaxation
    )
    return result, model, refs


def _solve_cplex(
    data: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
    continuous_relaxation: bool = False,
    log_file: Optional[str] = None
) -> Tuple[SolverResult, Any, Dict[str, Any]]:
    model, refs = build_convrp_cplex_model(
        data,
        params=params,
        continuous_relaxation=continuous_relaxation
    )

    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        sol = model.solve(log_output=str(log_file))
    else:
        sol = model.solve()

    has_sol = sol is not None
    sd = model.solve_details
    raw_status = (sd.status or "").lower()
    status_code = getattr(sd, "status_code", None)

    if has_sol and ("optimal" in raw_status or status_code in (1, 101, 102)):
        status_str = "OPTIMAL"
    elif "time limit" in raw_status or status_code in (107, 108):
        status_str = "TIME_LIMIT"
    elif "infeasible" in raw_status or status_code in (3, 103):
        status_str = "INFEASIBLE"
    elif has_sol:
        status_str = "FEASIBLE"
    else:
        status_str = "NO_SOLUTION"

    obj_val = model.objective_value if has_sol else None
    runtime = sd.time
    iters = 0
    try:
        iters = int(model.cplex.solution.progress.get_num_iterations())
    except Exception:
        iters = int(getattr(sd, "nb_iterations", 0) or 0)

    if continuous_relaxation:
        best_bound = obj_val
        gap = 0.0 if has_sol else None
        nodes = 0
    else:
        bb = sd.best_bound
        best_bound = bb if (bb is not None and not math.isnan(bb)) else None
        rg = sd.mip_relative_gap
        gap = rg * 100.0 if (rg is not None and not math.isnan(rg)) else None
        nodes = int(getattr(sd, "nb_nodes_processed", 0) or 0)

    result = SolverResult(
        solver="cplex",
        status=status_str,
        obj_val=obj_val,
        best_bound=best_bound,
        mip_gap_percent=gap,
        runtime_sec=runtime,
        node_count=nodes,
        iterations=iters,
        sol_count=1 if has_sol else 0,
        is_optimal=(status_str == "OPTIMAL"),
        continuous_relaxation=continuous_relaxation,
        extra_info={"raw_status": sd.status, "status_code": status_code}
    )
    return result, model, refs


def solve_model(
    solver: str,
    data: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
    continuous_relaxation: bool = False,
    log_file: Optional[str] = None
) -> Tuple[SolverResult, Any, Dict[str, Any]]:
    """Ejecuta la optimizacion con el solver seleccionado devolviendo resultado estandarizado."""
    s = _normalize_solver_name(solver)
    if s == "gurobi":
        return _solve_gurobi(data, params=params, continuous_relaxation=continuous_relaxation, log_file=log_file)
    else:
        return _solve_cplex(data, params=params, continuous_relaxation=continuous_relaxation, log_file=log_file)


def compare_solvers(
    data: Dict[str, Any],
    continuous_relaxation: bool = False,
    log_dir: Optional[str] | Optional[Path] = None
) -> Dict[str, SolverResult]:
    """Ejecuta una corrida comparativa Gurobi vs CPLEX sobre la misma instancia."""
    log_grb = None
    log_cpx = None
    if log_dir:
        ld = Path(log_dir)
        ld.mkdir(parents=True, exist_ok=True)
        prefix = "relax" if continuous_relaxation else "milp"
        log_grb = str(ld / f"gurobi_{prefix}.log")
        log_cpx = str(ld / f"cplex_{prefix}.log")

    res_grb, m_grb, _ = solve_model("gurobi", data, continuous_relaxation=continuous_relaxation, log_file=log_grb)
    m_grb.dispose()

    res_cpx, _, _ = solve_model("cplex", data, continuous_relaxation=continuous_relaxation, log_file=log_cpx)

    return {
        "gurobi": res_grb,
        "cplex": res_cpx,
    }
