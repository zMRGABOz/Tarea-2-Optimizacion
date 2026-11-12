"""Punto de entrada principal para la ejecucion del modelo y experimentos.

Permite ejecutar los diferentes modos de operacion y solvers:
- Solvers soportados: gurobi, cplex, compare.
- solve: Resolucion del modelo MILP base.
- relax: Resolucion de la relajacion continua y brecha de integralidad.
- benchmark: Bateria de configuraciones del solver (Gurobi).
- tune: Ajuste automatico de parametros model.tune() (Gurobi).
- sensitivity: Analisis de sensibilidad post-optimo con model.fixed() (Gurobi).
"""

from __future__ import annotations
import argparse
from pathlib import Path
import sys
from typing import Any, Dict

from src.data_loader import load_instance
from src.model import build_convrp_model
from src.solver_adapter import (
    SolverResult,
    compare_solvers,
    export_lp,
    solve_model
)
from src.experiments import (
    compute_continuous_relaxation,
    run_solver_benchmarks,
    run_parameter_tuning,
    run_all_experiments,
    write_csv
)
from src.sensitivity import run_capacity_sensitivity_analysis


def _print_comparison_table(
    instance_name: str,
    res_relax: Dict[str, SolverResult],
    res_milp: Dict[str, SolverResult]
) -> None:
    """Imprime tabla comparativa de validacion cruzada entre Gurobi y CPLEX."""
    rg_lp, rc_lp = res_relax["gurobi"], res_relax["cplex"]
    rg_m, rc_m = res_milp["gurobi"], res_milp["cplex"]

    diff_lp = abs(rg_lp.obj_val - rc_lp.obj_val) if (rg_lp.obj_val and rc_lp.obj_val) else 0.0
    diff_milp = abs(rg_m.obj_val - rc_m.obj_val) if (rg_m.obj_val and rc_m.obj_val) else 0.0

    gap_int_grb = ((rg_m.obj_val - rg_lp.obj_val) / rg_m.obj_val * 100.0) if (rg_m.obj_val and rg_lp.obj_val) else 0.0
    gap_int_cpx = ((rc_m.obj_val - rc_lp.obj_val) / rc_m.obj_val * 100.0) if (rc_m.obj_val and rc_lp.obj_val) else 0.0

    print("\n" + "=" * 78)
    print(f" VALIDACION CRUZADA GUROBI vs CPLEX — INSTANCIA: {instance_name}")
    print("=" * 78)

    print("\n[1] RELAJACION CONTINUA (LP RELAXED)")
    print(f"{'Metrica':<26} | {'Gurobi':<16} | {'CPLEX':<16} | {'Diferencia':<12}")
    print("-" * 78)
    lp_obj_g = f"{rg_lp.obj_val:.4f}" if rg_lp.obj_val is not None else "N/A"
    lp_obj_c = f"{rc_lp.obj_val:.4f}" if rc_lp.obj_val is not None else "N/A"
    print(f"{'Valor Objetivo (z_LP)':<26} | {lp_obj_g:<16} | {lp_obj_c:<16} | {diff_lp:<12.6f}")
    print(f"{'Tiempo de computo (s)':<26} | {rg_lp.runtime_sec:<16.3f} | {rc_lp.runtime_sec:<16.3f} | {abs(rg_lp.runtime_sec - rc_lp.runtime_sec):<12.3f}")
    print(f"{'Iteraciones Simplex':<26} | {rg_lp.iterations:<16} | {rc_lp.iterations:<16} | {abs(rg_lp.iterations - rc_lp.iterations):<12}")
    print(f"{'Estatus':<26} | {rg_lp.status:<16} | {rc_lp.status:<16} | {'Identico' if rg_lp.status == rc_lp.status else 'Difiere'}")

    print("\n[2] MODELO ENTERO (MILP DEFAULT)")
    print(f"{'Metrica':<26} | {'Gurobi':<16} | {'CPLEX':<16} | {'Diferencia':<12}")
    print("-" * 78)
    m_obj_g = f"{rg_m.obj_val:.4f}" if rg_m.obj_val is not None else "N/A"
    m_obj_c = f"{rc_m.obj_val:.4f}" if rc_m.obj_val is not None else "N/A"
    print(f"{'Valor Objetivo (z_MILP)':<26} | {m_obj_g:<16} | {m_obj_c:<16} | {diff_milp:<12.6f}")
    bb_g = f"{rg_m.best_bound:.4f}" if rg_m.best_bound is not None else "N/A"
    bb_c = f"{rc_m.best_bound:.4f}" if rc_m.best_bound is not None else "N/A"
    print(f"{'Cota Inferior (Bound)':<26} | {bb_g:<16} | {bb_c:<16} | -")
    gap_g = f"{rg_m.mip_gap_percent:.2f}%" if rg_m.mip_gap_percent is not None else "N/A"
    gap_c = f"{rc_m.mip_gap_percent:.2f}%" if rc_m.mip_gap_percent is not None else "N/A"
    print(f"{'MIPGap final':<26} | {gap_g:<16} | {gap_c:<16} | -")
    print(f"{'Tiempo de computo (s)':<26} | {rg_m.runtime_sec:<16.3f} | {rc_m.runtime_sec:<16.3f} | {abs(rg_m.runtime_sec - rc_m.runtime_sec):<12.3f}")
    print(f"{'Nodos explorados':<26} | {rg_m.node_count:<16} | {rc_m.node_count:<16} | {abs(rg_m.node_count - rc_m.node_count):<12}")
    print(f"{'Estatus':<26} | {rg_m.status:<16} | {rc_m.status:<16} | {'Identico' if rg_m.status == rc_m.status else 'Difiere'}")

    print("\n[3] BRECHA DE INTEGRALIDAD ((z_MILP - z_LP) / z_MILP)")
    print(f"{'Gurobi':<26} | {gap_int_grb:.2f}%")
    print(f"{'CPLEX':<26} | {gap_int_cpx:.2f}%")
    print("=" * 78 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Optimizacion conVRP-SLA (Tarea 3 - Gurobi vs CPLEX)"
    )
    parser.add_argument(
        "--instance",
        type=str,
        default="instances/sample_toy.txt",
        help="Ruta al archivo .txt de la instancia."
    )
    parser.add_argument(
        "--solver",
        type=str,
        choices=["gurobi", "cplex", "compare"],
        default="gurobi",
        help="Motor de optimizacion: gurobi, cplex, o compare (ambos simultaneamente)."
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["solve", "relax", "benchmark", "tune", "sensitivity", "all"],
        default="solve",
        help="Modo de ejecucion del programa."
    )
    parser.add_argument(
        "--tune-time",
        type=int,
        default=120,
        help="Limite de tiempo en segundos para model.tune()."
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=None,
        help="Carpeta de resultados (por defecto results/<instancia>)."
    )
    parser.add_argument(
        "--export-lp",
        type=str,
        default=None,
        help="Ruta para exportar el modelo a formato .lp."
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Ruta del archivo de log para la corrida."
    )

    args = parser.parse_args()

    # Cargar datos de la instancia
    print(f"Cargando instancia desde: {args.instance}")
    try:
        data = load_instance(args.instance)
    except Exception as e:
        print(f"Error al cargar la instancia: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Instancia cargada: {data['name']}")
    print(f"Clientes: {len(data['NC'])}, Dias: {len(data['days'])}, Rutas: {len(data['routes'])}")

    out_dir = args.out_dir or f"results/{data['name']}"
    log_dir = Path(out_dir) / "logs"

    try:
        # Exportar LP si fue solicitado
        if args.export_lp:
            s_exp = "gurobi" if args.solver == "compare" else args.solver
            exported = export_lp(s_exp, data, args.export_lp)
            print(f"Modelo exportado en formato LP ({s_exp}): {exported}")

        # Modo Validacion Cruzada Directa (modo compare)
        if args.solver == "compare":
            print("\nEjecutando validacion cruzada completa (Relajacion + Modelo Entero)...")
            res_relax = compare_solvers(data, continuous_relaxation=True, log_dir=log_dir)
            res_milp = compare_solvers(data, continuous_relaxation=False, log_dir=log_dir)
            _print_comparison_table(data["name"], res_relax, res_milp)
            print(f"Archivos log generados en: {log_dir}/")
            return

        # Modo 1: Resolucion MILP directa con solver seleccionado
        if args.mode == "solve":
            print(f"\nEjecutando resolucion MILP base en {args.solver.upper()}...")
            log_path = args.log_file or str(log_dir / f"{args.solver}_milp.log")
            res, _, _ = solve_model(args.solver, data, log_file=log_path)

            print(f"\nEstatus de optimizacion: {res.status}")
            if res.obj_val is not None:
                print(f"Valor objetivo (distancia total): {res.obj_val:.2f}")
                print(f"Tiempo de resolucion: {res.runtime_sec:.3f} s")
                gap_str = f"{res.mip_gap_percent:.2f}%" if res.mip_gap_percent is not None else "0.00%"
                print(f"MIPGap final: {gap_str}")
                print(f"Nodos explorados: {res.node_count}")
                print(f"Log guardado en: {log_path}")

        # Modo 2: Relajacion continua y brecha de integralidad
        elif args.mode == "relax":
            print(f"\nEjecutando relajacion continua en {args.solver.upper()}...")
            log_relax = args.log_file or str(log_dir / f"{args.solver}_relax.log")
            res_lp, _, _ = solve_model(args.solver, data, continuous_relaxation=True, log_file=log_relax)

            print(f"\nCalculando solucion entera de referencia en {args.solver.upper()}...")
            res_milp, _, _ = solve_model(args.solver, data, continuous_relaxation=False)
            z_milp = res_milp.obj_val

            gap = ((z_milp - res_lp.obj_val) / z_milp * 100.0) if (z_milp and res_lp.obj_val) else None

            print(f"\nResultados de Relajacion Continua ({args.solver.upper()}):")
            print(f"  z_LP: {res_lp.obj_val:.4f}")
            print(f"  z_MILP: {z_milp:.4f}" if z_milp is not None else "  z_MILP: N/A")
            print(f"  Brecha de integralidad: {gap:.2f}%" if gap is not None else "  Brecha: N/A")
            print(f"  Tiempo LP: {res_lp.runtime_sec:.3f} s")
            print(f"  Iteraciones: {res_lp.iterations}")
            print(f"  Log guardado en: {log_relax}")

        # Modo 3: Bateria de configuraciones de solver (Gurobi)
        elif args.mode == "benchmark":
            if args.solver == "cplex":
                print("[Aviso]: El modo benchmark de configuraciones corresponde a la bateria de Gurobi.")
            print("\nEjecutando comparaciones de configuraciones (Threads=1, TimeLimit=600)...")
            results = run_solver_benchmarks(data, log_dir=str(log_dir))
            print("\nResultados comparativos:")
            print(f"{'Configuracion':<15} | {'Estatus':<8} | {'Tiempo (s)':<10} | {'Valor Obj':<12} | {'Gap (%)':<8}")
            print("-" * 65)
            for r in results:
                obj_str = f"{r['obj_val']:.2f}" if r["obj_val"] is not None else "N/A"
                gap_str = f"{r['mip_gap_percent']:.2f}" if r["mip_gap_percent"] is not None else "N/A"
                print(f"{r['configuration']:<15} | {r['status']:<8} | {r['runtime_sec']:<10.2f} | {obj_str:<12} | {gap_str:<8}")

        # Modo 4: Ajuste automatico de parametros (Gurobi tuning)
        elif args.mode == "tune":
            print(f"\nEjecutando model.tune() con limite de {args.tune_time}s...")
            tune_res = run_parameter_tuning(data, tune_time_limit=args.tune_time, output_tune_file=f"{out_dir}/best_tune.prm", log_dir=str(log_dir))
            print("\nResultados de Tuning:")
            for k, v in tune_res.items():
                print(f"  {k}: {v}")

        # Modo 5: Analisis de sensibilidad post-optimo
        elif args.mode == "sensitivity":
            print("\nEjecutando analisis de sensibilidad para la capacidad Q (model.fixed())...")
            sens_res = run_capacity_sensitivity_analysis(data)
            out_dir = Path(args.out_dir or f"results/{data['name']}")
            out_path = out_dir / "sensitivity.csv"
            write_csv(sens_res, out_path)
            print(f"Resultados de sensibilidad guardado en {out_path}")
            print("\nSensibilidad de Capacidad Q:")
            print(f"{'Ruta':<6} | {'Dia':<5} | {'Capacidad Q':<12} | {'Slack':<8} | {'Precio Sombra':<14} | {'SARHSLow':<10} | {'SARHSUp':<10}")
            print("-" * 75)
            for row in sens_res:
                low_str = f"{row['sarhs_low']:.2f}" if row['sarhs_low'] is not None else "N/A"
                up_str = f"{row['sarhs_up']:.2f}" if row['sarhs_up'] is not None else "N/A"
                print(f"{row['route']:<6} | {row['day']:<5} | {row['current_capacity_Q']:<12.2f} | {row['slack']:<8.2f} | {row['shadow_price_Pi']:<14.4f} | {low_str:<10} | {up_str:<10}")

        # Modo 6: Benchmark + relajacion + tuning + sens con CSV/JSON
        elif args.mode == "all":
            out_dir = args.out_dir or f"results/{data['name']}"
            summary = run_all_experiments(data, out_dir=out_dir, tune_time_limit=args.tune_time)
            print(f"\nResultados guardados en {out_dir}/")
            print(f"  Brecha de integralidad: {summary['relaxation']['integrality_gap_percent']:.2f}%")
            print(f"  Mejor manual: {summary['best_manual']['configuration']}")
            print(f"  Parametros tuner: {summary['tuning'].get('best_params')}")

    except NotImplementedError as e:
        print(f"\n[Aviso]: {e}")
        sys.exit(0)


if __name__ == "__main__":
    main()
