"""Genera graficos descriptivos de las instancias conVRP-SLA para la presentacion."""

import argparse
from pathlib import Path
from typing import Dict, Tuple

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

from src.data_loader import load_instance


def load_coords(filepath: str | Path) -> Dict[int, Tuple[float, float]]:
    """Extrae las coordenadas (x, y) de la seccion CUSTOMER del archivo .txt."""
    coords: Dict[int, Tuple[float, float]] = {}
    in_customers = False
    with open(filepath, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.upper().startswith("CUSTOMER"):
                in_customers = True
                continue
            if in_customers:
                parts = line.split()
                if parts and parts[0].isdigit():
                    cid = int(parts[0])
                    coords[cid] = (float(parts[1]), float(parts[2]))
    return coords


def plot_instance(filepath: str | Path, out_dir: str | Path) -> Path:
    data = load_instance(filepath)
    coords = load_coords(filepath)

    name = data["name"]
    nc = data["NC"]
    days = data["days"]
    ntw = set(data["NTW"])
    q = data["q"]
    tw = data["tw"]
    aW, bW = data["aW"], data["bW"]
    Q = data["Q"]

    fig, axes = plt.subplots(1, 3, figsize=(16, 5.5), gridspec_kw={"width_ratios": [1.15, 0.9, 1.05]})
    fig.patch.set_facecolor("white")

    # ------------------------------------------------------------------
    # Panel 1: Mapa espacial 2D
    # ------------------------------------------------------------------
    ax_map = axes[0]
    dx, dy = coords[data["depot_start"]]
    ax_map.scatter([dx], [dy], marker="*", s=260, c="#D62728", zorder=5, label="Depósito (0)")
    ax_map.annotate("0", (dx, dy), textcoords="offset points", xytext=(6, 6),
                    fontsize=9, fontweight="bold", color="#D62728")

    tw_x = [coords[i][0] for i in nc if i in ntw]
    tw_y = [coords[i][1] for i in nc if i in ntw]
    open_x = [coords[i][0] for i in nc if i not in ntw]
    open_y = [coords[i][1] for i in nc if i not in ntw]

    if tw_x:
        ax_map.scatter(tw_x, tw_y, s=75, c="#1F4E79", edgecolors="white", linewidths=0.8,
                       zorder=4, label=f"Con ventana ({len(tw_x)})")
    if open_x:
        ax_map.scatter(open_x, open_y, marker="^", s=80, c="#2A9D8F", edgecolors="white", linewidths=0.8,
                       zorder=4, label=f"Sin ventana fija ({len(open_x)})")

    for i in nc:
        xi, yi = coords[i]
        ax_map.annotate(str(i), (xi, yi), textcoords="offset points", xytext=(4, 4),
                        fontsize=8, color="#222222")

    ax_map.set_title("Distribución espacial", fontsize=12, fontweight="bold", pad=10)
    ax_map.set_xlabel("Coordenada X")
    ax_map.set_ylabel("Coordenada Y")
    ax_map.grid(True, linestyle="--", alpha=0.35)
    ax_map.legend(loc="best", fontsize=8.5, frameon=True)

    # ------------------------------------------------------------------
    # Panel 2: Matriz de demandas multi-día (heatmap)
    # ------------------------------------------------------------------
    ax_dem = axes[1]
    mat = np.array([[q[(i, d)] for d in days] for i in nc], dtype=float)
    masked = np.ma.masked_where(mat == 0, mat)

    cmap = plt.cm.Blues.copy()
    cmap.set_bad(color="#F0F0F0")
    ax_dem.imshow(masked, cmap=cmap, aspect="auto", vmin=0, vmax=max(mat.max(), 1))

    for row_idx, i in enumerate(nc):
        for col_idx, d in enumerate(days):
            val = int(round(mat[row_idx, col_idx]))
            if val == 0:
                ax_dem.text(col_idx, row_idx, "—", ha="center", va="center", color="#888888", fontsize=9)
            else:
                txt_color = "white" if val > mat.max() * 0.6 else "#111111"
                ax_dem.text(col_idx, row_idx, str(val), ha="center", va="center",
                            color=txt_color, fontsize=8.5, fontweight="bold")

    ax_dem.set_xticks(range(len(days)))
    ax_dem.set_xticklabels([f"Día {d}" for d in days], fontsize=9.5)
    ax_dem.set_yticks(range(len(nc)))
    ax_dem.set_yticklabels([f"C{i}" for i in nc], fontsize=8.5)
    ax_dem.set_title(f"Demandas diarias (Q = {int(Q)})", fontsize=12, fontweight="bold", pad=10)

    # Totales diarios arriba/abajo
    day_totals = [int(round(mat[:, c].sum())) for c in range(len(days))]
    ax_dem.set_xlabel("Total por día: " + " | ".join(f"D{d}: {tot}" for d, tot in zip(days, day_totals)),
                      fontsize=8.5, labelpad=8)

    # ------------------------------------------------------------------
    # Panel 3: Ventanas horarias
    # ------------------------------------------------------------------
    ax_tw = axes[2]
    ax_tw.axvspan(aW, bW, color="#F7F9FC", zorder=0)
    ax_tw.axvline(aW, color="#D62728", linestyle="--", linewidth=1.1, alpha=0.8)
    ax_tw.axvline(bW, color="#D62728", linestyle="--", linewidth=1.1, alpha=0.8, label=f"Depósito [{int(aW)}, {int(bW)}]")

    for idx, i in enumerate(nc):
        ai, bi = tw[i]
        color = "#1F4E79" if i in ntw else "#B0BEC5"
        lw = 4.5 if i in ntw else 2.5
        ax_tw.hlines(y=idx, xmin=ai, xmax=bi, color=color, linewidth=lw)
        if i in ntw:
            ax_tw.plot([ai, bi], [idx, idx], "o", color="#1F4E79", markersize=4)

    ax_tw.set_yticks(range(len(nc)))
    ax_tw.set_yticklabels([f"C{i}" for i in nc], fontsize=8.5)
    ax_tw.invert_yaxis()
    ax_tw.set_xlim(aW - 10, bW + 15)
    ax_tw.set_xlabel("Tiempo (min)")
    ax_tw.set_title("Ventanas horarias [a_i, b_i]", fontsize=12, fontweight="bold", pad=10)
    ax_tw.grid(True, axis="x", linestyle="--", alpha=0.35)

    p_tw = mpatches.Patch(color="#1F4E79", label="Ventana acotada (N_TW)")
    p_open = mpatches.Patch(color="#B0BEC5", label="Ventana abierta")
    ax_tw.legend(handles=[p_tw, p_open], loc="lower right", fontsize=8, frameon=True)

    fig.suptitle(
        f"Instancia: {name}  |  {len(nc)} clientes, {len(days)} días, {len(data['routes'])} rutas, Capacidad Q={Q:g}",
        fontsize=14, fontweight="bold", y=0.99
    )
    plt.tight_layout(rect=[0, 0, 1, 0.94])

    out_path = Path(out_dir) / f"{name}_instancia.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Graficar instancias conVRP-SLA.")
    parser.add_argument(
        "--instances",
        nargs="+",
        default=["instances/muestras_A_barrios.txt", "instances/muestras_B_dispersa.txt"],
        help="Archivos de instancia .txt a graficar."
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default="results/plots",
        help="Carpeta donde guardar las imagenes .png."
    )
    args = parser.parse_args()

    for inst in args.instances:
        out = plot_instance(inst, args.out_dir)
        print(f"Grafico generado: {out}")


if __name__ == "__main__":
    main()