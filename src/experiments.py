#Modulo de experimentacion y evaluacion computacional del solver.

from __future__ import annotations
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import gurobipy as gp
from gurobipy import GRB

from src.model import build_convrp_model

# Configuraciones exigidas por el enunciado (cada una se compara contra el baseline)
SOLVER_CONFIGURATIONS: List[tuple[str, Dict[str, Any]]] = [
    ("Baseline", {}),
    ("Cuts=0", {"Cuts": 0}),
    ("Presolve=0", {"Presolve": 0}),
    ("MIPFocus=1", {"MIPFocus": 1}),
    ("MIPFocus=3", {"MIPFocus": 3}),
    ("Heuristics=0", {"Heuristics": 0}),
]

# Parametros de entorno que no forman parte de una configuracion del solver
_NON_SOLVER_PARAMS = {"LicenseID", "Username", "LogFile", "OutputFlag", "LogToConsole",
                      "TuneOutput", "TuneTimeLimit", "TuneResults", "TuneTrials"}

_STATUS_NAMES = {
    2: "OPTIMAL", 3: "INFEASIBLE", 4: "INF_OR_UNBD", 5: "UNBOUNDED",
    9: "TIME_LIMIT", 11: "INTERRUPTED", 13: "SUBOPTIMAL",
}

def _status_name(code: int) -> str:
    return _STATUS_NAMES.get(code, str(code))

def _collect_mip_metrics(model: gp.Model, label: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Extrae las metricas de una corrida MILP ya optimizada."""
    has_sol = model.SolCount > 0
    return {
        "configuration": label,
        "params": json.dumps(params),
        "status": _status_name(model.Status),
        "runtime_sec": model.Runtime,
        "obj_val": model.ObjVal if has_sol else None,
        "obj_bound": model.ObjBound,
        "mip_gap_percent": model.MIPGap * 100 if has_sol else None,
        "node_count": model.NodeCount,
        "simplex_iters": model.IterCount,
        "sol_count": model.SolCount,
    }

def _log_path(log_dir: Optional[str], name: str) -> Optional[str]:
    if not log_dir:
        return None
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    return str(Path(log_dir) / f"{name}.log")

def solve_milp(
    data: Dict[str, Any],
    label: str = "Baseline",
    params: Optional[Dict[str, Any]] = None,
    log_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Resuelve el MILP con los parametros dados (sobre Threads=1, TimeLimit=600)."""
    params = dict(params or {})
    run_params = dict(params)
    log_file = _log_path(log_dir, label.replace("=", "_"))
    if log_file:
        run_params["LogFile"] = log_file
    model, _ = build_convrp_model(data, params=run_params)
    model.optimize()
    metrics = _collect_mip_metrics(model, label, params)
    model.dispose()
    return metrics

def compute_continuous_relaxation(
    data: Dict[str, Any],
    z_milp: Optional[float] = None
) -> Dict[str, Any]:
    #Resuelve la relajacion continua y calcula la brecha de integralidad.
    # X y Z pasan a ser continuas en [0, 1]; el resto del modelo no cambia
    model, _ = build_convrp_model(data, continuous_relaxation=True)
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"La relajacion continua termino con estatus {_status_name(model.Status)}")

    z_lp = model.ObjVal
    gap = (z_milp - z_lp) / z_milp * 100 if z_milp else None
    result = {
        "z_lp": z_lp,
        "z_milp": z_milp,
        "integrality_gap_percent": gap,
        "lp_runtime_sec": model.Runtime,
        "lp_status": _status_name(model.Status),
    }
    model.dispose()
    return result

def run_solver_benchmarks(
    data: Dict[str, Any],
    log_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    #Ejecuta las configuraciones del solver.
    results = []
    for label, params in SOLVER_CONFIGURATIONS:
        print(f"  -> {label} ...", flush=True)
        r = solve_milp(data, label=label, params=params, log_dir=log_dir)
        print(f"     {r['status']}  t={r['runtime_sec']:.1f}s  obj={r['obj_val']}  "
              f"gap={r['mip_gap_percent']}", flush=True)
        results.append(r)
    return results

def _read_prm(path: str) -> Dict[str, Any]:
    """Lee un archivo .prm de Gurobi, omitiendo parametros de entorno/licencia."""
    params: Dict[str, Any] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) < 2 or line.startswith("#") or parts[0] in _NON_SOLVER_PARAMS:
                continue
            value: Any = parts[1]
            for cast in (int, float):
                try:
                    value = cast(value)
                    break
                except ValueError:
                    pass
            params[parts[0]] = value
    return params

def run_parameter_tuning(
    data: Dict[str, Any],
    tune_time_limit: int = 120,
    output_tune_file: Optional[str] = None,
    log_dir: Optional[str] = None,
) -> Dict[str, Any]:
    #Ejecuta la herramienta model.tune() de Gurobi sobre la instancia.
    tune_params: Dict[str, Any] = {"TuneTimeLimit": tune_time_limit}
    tune_log = _log_path(log_dir, "tune")
    if tune_log:
        tune_params["LogFile"] = tune_log
    model, _ = build_convrp_model(data, params=tune_params)
    model.tune()

    result_count = model.TuneResultCount
    if result_count == 0:
        model.dispose()
        return {"tune_result_count": 0, "best_params": {}, "message": "El tuner no encontro resultados."}

    # Resultado 0 = baseline; resultado 1 = mejor conjunto mejorado (si el tuner encontro alguno)
    best_index = 1 if result_count > 1 else 0
    model.getTuneResult(best_index)
    prm_path = output_tune_file or str(Path(log_dir or ".") / "best_tune.prm")
    Path(prm_path).parent.mkdir(parents=True, exist_ok=True)
    model.write(prm_path)
    model.dispose()

    best_params = {k: v for k, v in _read_prm(prm_path).items()
                   if k not in ("Threads", "TimeLimit")}
    label = "Tuned" if best_params else "Tuned (=Baseline)"
    print(f"  -> Re-resolviendo con parametros del tuner: {best_params}", flush=True)
    rerun = solve_milp(data, label=label, params=best_params, log_dir=log_dir)
    return {
        "tune_result_count": result_count,
        "tune_result_index": best_index,
        "tune_time_limit_sec": tune_time_limit,
        "best_params": best_params,
        "prm_file": prm_path,
        "rerun": rerun,
    }

def write_csv(rows: List[Dict[str, Any]], path: str | Path) -> None:
    """Guarda una lista de diccionarios como CSV."""
    if not rows:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

def run_all_experiments(
    data: Dict[str, Any],
    out_dir: str | Path,
    tune_time_limit: int = 900,
) -> Dict[str, Any]:
    """Ejecuta y guarda los resultados en out_dir.
    1. Bateria de configuraciones (incluye el baseline, que entrega z_MILP).
    2. Relajacion continua y brecha de integralidad contra la mejor solucion entera.
    3. model.tune() y comparacion contra baseline y mejor configuracion manual.
    """
    out_dir = Path(out_dir)
    log_dir = out_dir / "logs"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("[1/3] Configuraciones del solver (Threads=1, TimeLimit=600)", flush=True)
    bench = run_solver_benchmarks(data, log_dir=str(log_dir))
    write_csv(bench, out_dir / "benchmark.csv")

    # z_MILP: mejor incumbente entre todas las corridas (el optimo si alguna cerro)
    feasible = [r for r in bench if r["obj_val"] is not None]
    z_milp = min(r["obj_val"] for r in feasible) if feasible else None

    print("[2/3] Relajacion continua", flush=True)
    relax = compute_continuous_relaxation(data, z_milp=z_milp)
    print(f"     z_LP={relax['z_lp']:.2f}  z_MILP={z_milp}  brecha={relax['integrality_gap_percent']}", flush=True)

    print(f"[3/3] model.tune() con TuneTimeLimit={tune_time_limit}s", flush=True)
    tune = run_parameter_tuning(data, tune_time_limit=tune_time_limit,
                                output_tune_file=str(out_dir / "best_tune.prm"),
                                log_dir=str(log_dir))

    # Mejor configuracion manual (sin contar el baseline): menor tiempo entre las optimas;
    # si ninguna cerro, menor gap final
    def manual_key(r):
        if r["status"] == "OPTIMAL":
            return (0, r["runtime_sec"])
        return (1, r["mip_gap_percent"] if r["mip_gap_percent"] is not None else float("inf"))
    best_manual = min(bench[1:], key=manual_key)

    summary = {
        "instance": data["name"],
        "relaxation": relax,
        "baseline": bench[0],
        "best_manual": best_manual,
        "tuning": tune,
    }
    comparison = [bench[0], best_manual] + ([tune["rerun"]] if "rerun" in tune else [])
    write_csv(comparison, out_dir / "tune_comparison.csv")
    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    return summary