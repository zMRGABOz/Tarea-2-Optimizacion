"""Punto de entrada principal para la ejecucion del modelo y experimentos.

Permite ejecutar los diferentes modos de operacion requeridos por los 4 integrantes:
- solve: Resolucion estandar del modelo MILP base.
- relax: Resolucion de la relajacion continua y brecha de integralidad (Integrante 3).
- benchmark: Bateria de comparacion de configuraciones del solver (Integrante 3).
- tune: Ajuste automatico de parametros model.tune() (Integrante 3).
- sensitivity: Analisis de sensibilidad post-optimo con model.fixed() (Integrante 4).
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path
from pprint import pprint

from src.data_loader import load_instance
from src.model import build_convrp_model
from src.experiments import (
    compute_continuous_relaxation,
    run_solver_benchmarks,
    run_parameter_tuning,
    run_all_experiments,
    write_csv
)
from src.sensitivity import run_capacity_sensitivity_analysis


def main():
    parser = argparse.ArgumentParser(
        description="Optimizacion conVRP-SLA (Tarea 2 - Gurobi)"
    )
    parser.add_argument(
        "--instance",
        type=str,
        default="instances/sample_toy.txt",
        help="Ruta al archivo .txt de la instancia."
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
        help="Carpeta de resultados para --mode all (por defecto results/<instancia>)."
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

    try:
        # Modo 1: Resolucion MILP directa
        if args.mode == "solve":
            print("\nEjecutando resolucion MILP base...")
            model, refs = build_convrp_model(data)
            model.optimize()

            print(f"\nEstatus de optimizacion: {model.Status}")
            if model.SolCount > 0:
                print(f"Valor objetivo (distancia total): {model.ObjVal:.2f}")
                print(f"Tiempo de resolucion: {model.Runtime:.2f} s")
                print(f"MIPGap final: {model.MIPGap * 100:.2f}%")

        # Modo 2: Relajacion continua y brecha de integralidad
        elif args.mode == "relax":
            print("\nCalculando solucion entera de referencia...")
            milp_model, _ = build_convrp_model(data)
            milp_model.optimize()
            z_milp = milp_model.ObjVal if milp_model.SolCount > 0 else None

            print("\nEjecutando relajacion continua...")
            relax_results = compute_continuous_relaxation(data, z_milp=z_milp)
            print("\nResultados de Relajacion Continua:")
            for k, v in relax_results.items():
                print(f"  {k}: {v}")

        # Modo 3: Bateria de configuraciones de solver
        elif args.mode == "benchmark":
            print("\nEjecutando comparaciones de configuraciones (Threads=1, TimeLimit=600)...")
            results = run_solver_benchmarks(data)
            print("\nResultados comparativos:")
            print(f"{'Configuracion':<15} | {'Estatus':<8} | {'Tiempo (s)':<10} | {'Valor Obj':<12} | {'Gap (%)':<8}")
            print("-" * 65)
            for r in results:
                obj_str = f"{r['obj_val']:.2f}" if r["obj_val"] is not None else "N/A"
                gap_str = f"{r['mip_gap_percent']:.2f}" if r["mip_gap_percent"] is not None else "N/A"
                print(f"{r['configuration']:<15} | {r['status']:<8} | {r['runtime_sec']:<10.2f} | {obj_str:<12} | {gap_str:<8}")

        # Modo 4: Ajuste automatico de parametros (tuning)
        elif args.mode == "tune":
            print(f"\nEjecutando model.tune() con limite de {args.tune_time}s...")
            tune_res = run_parameter_tuning(data, tune_time_limit=args.tune_time, output_tune_file="results/best_tune.prm")
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
