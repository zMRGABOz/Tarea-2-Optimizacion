"""Grafica las instancias: mapa, demandas diarias y ventanas de tiempo.

Lee los .txt de instances/ con el mismo data_loader del modelo y guarda en
instances/graficos/:
    <instancia>.png            figura completa (3 paneles)
    <instancia>_mapa.png       mapa de consultorios y laboratorio
    <instancia>_demandas.png   demanda por cliente y dia (- = no pide)
    <instancia>_ventanas.png   ventanas de tiempo y horario del laboratorio

Uso (desde la raiz del repo):
    py -3.13 instances/graficar_instancias.py
"""

from __future__ import annotations
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.data_loader import load_instance  # noqa: E402

INSTANCES = [("muestras_A_barrios", "A: Barrios"), ("muestras_B_dispersa", "B: Dispersa")]
OUT = Path(__file__).resolve().parent / "graficos"

NAVY, INK, INK2, MUTED, GRID = "#244a7c", "#0b0b0b", "#52514e", "#8a8984", "#e4e3df"
# Paleta categorica de referencia (3 primeros slots, validados para cualquier par)
FREQ_COLORS = {3: "#2a78d6", 2: "#eb6834", 1: "#1baf7a"}
FREQ_LABEL = {3: "Pide los 3 días", 2: "Pide 2 días", 1: "Pide 1 día"}
DEMAND_CMAP = LinearSegmentedColormap.from_list("demanda", ["#e8f0fb", "#2a78d6", "#123f75"])

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.titlecolor": NAVY, "axes.titleweight": "bold", "axes.titlesize": 12,
})


def coords_of(path: Path) -> dict[int, tuple[float, float]]:
    coords, in_c = {}, False
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.split()
        if line.startswith("CUSTOMER"):
            in_c = True
        elif in_c and s and s[0].isdigit():
            coords[int(s[0])] = (float(s[1]), float(s[2]))
    return coords


def freq(d, i) -> int:
    return sum(1 for t in d["days"] if d["q"][i, t] > 0)


def panel_map(ax, d, coords, label):
    ax.set_title(f"{label} · ubicaciones", loc="left")
    for i in d["NC"]:
        x, y = coords[i]
        c = FREQ_COLORS[freq(d, i)]
        has_tw = i in d["NTW"]
        ax.scatter(x, y, s=95, color=c if has_tw else "white", edgecolor=c if not has_tw else "white",
                   linewidth=2 if not has_tw else 1.5, zorder=3)
        ax.annotate(str(i), (x, y), xytext=(6, 5), textcoords="offset points", fontsize=8, color=INK2)
    x0, y0 = coords[0]
    ax.scatter(x0, y0, s=170, marker="s", color=NAVY, zorder=4)
    ax.annotate("Laboratorio", (x0, y0), xytext=(9, -13), textcoords="offset points", fontsize=8.5,
                color=NAVY, fontweight="bold")
    ax.set_xlim(0, 100), ax.set_ylim(0, 100), ax.set_aspect("equal")
    ax.grid(color=GRID, linewidth=0.8), ax.set_axisbelow(True)
    handles = [Line2D([], [], marker="o", ls="", color=FREQ_COLORS[k], markersize=8, label=FREQ_LABEL[k])
               for k in (3, 2, 1)]
    handles += [Line2D([], [], marker="o", ls="", color=MUTED, markersize=8, label="Con ventana horaria"),
                Line2D([], [], marker="o", ls="", markerfacecolor="white", markeredgecolor=MUTED,
                       markeredgewidth=2, markersize=8, label="Sin ventana (horario completo)"),
                Line2D([], [], marker="s", ls="", color=NAVY, markersize=9, label="Laboratorio")]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.07), ncol=2, frameon=False, fontsize=8.5)


def panel_demands(ax, d, label):
    days, NC = d["days"], d["NC"]
    mat = [[d["q"][i, t] for t in days] for i in NC]
    vmax = max(max(r) for r in mat)
    ax.set_title(f"{label} · demanda diaria", loc="left")
    for r, i in enumerate(NC):
        for c, t in enumerate(days):
            v = mat[r][c]
            if v > 0:
                ax.add_patch(plt.Rectangle((c, r), 0.96, 0.92, color=DEMAND_CMAP(0.15 + 0.85 * v / vmax)))
                ax.text(c + 0.48, r + 0.46, f"{v:.0f}", ha="center", va="center", fontsize=8,
                        color="white" if v / vmax > 0.45 else INK)
            else:
                ax.add_patch(plt.Rectangle((c, r), 0.96, 0.92, facecolor="white", edgecolor=GRID))
                ax.text(c + 0.48, r + 0.46, "–", ha="center", va="center", fontsize=9, color=MUTED)
    ax.set_xlim(0, len(days)), ax.set_ylim(len(NC), 0)
    ax.set_xticks([c + 0.48 for c in range(len(days))], [f"Día {t}" for t in days])
    ax.set_yticks([r + 0.46 for r in range(len(NC))], [str(i) for i in NC], fontsize=8)
    ax.set_ylabel("Consultorio")
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    per_day = [sum(1 for i in NC if d["q"][i, t] > 0) for t in days]
    loads = [sum(d["q"][i, t] for i in NC) for t in days]
    ax.text(0, len(NC) + 0.9, "Pedidos: " + " · ".join(f"D{t} {n}" for t, n in zip(days, per_day))
            + f"\nCarga total: " + " · ".join(f"D{t} {l:.0f}" for t, l in zip(days, loads))
            + f"  (Q = {d['Q']:.0f} × {len(d['routes'])} rutas)", fontsize=8, color=INK2, va="top")


def panel_windows(ax, d, label):
    NC, aW, bW = d["NC"], d["aW"], d["bW"]
    ax.set_title(f"{label} · ventanas de tiempo", loc="left")
    ax.axvspan(aW, bW, color="#f3f6fb", zorder=0)
    for r, i in enumerate(NC):
        a, b = d["tw"][i]
        if i in d["NTW"]:
            ax.barh(r, b - a, left=a, height=0.62, color=FREQ_COLORS[freq(d, i)], zorder=2)
        else:
            ax.barh(r, bW - aW, left=aW, height=0.62, color="white", edgecolor=GRID, hatch="///", zorder=1)
    ax.set_yticks(range(len(NC)), [str(i) for i in NC], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(aW - 5, bW + 5)
    ax.set_xlabel("Minutos desde la apertura del laboratorio")
    ax.grid(axis="x", color=GRID), ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.legend(handles=[Patch(facecolor=FREQ_COLORS[3], label="Ventana (color = frecuencia)"),
                       Patch(facecolor="white", edgecolor=GRID, hatch="///", label="Sin ventana"),
                       Patch(facecolor="#f3f6fb", label=f"Horario laboratorio [{aW:.0f}, {bW:.0f}]")],
              loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2, frameon=False, fontsize=8.5)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name, label in INSTANCES:
        path = ROOT / "instances" / f"{name}.txt"
        d = load_instance(path)
        coords = coords_of(path)

        fig, axes = plt.subplots(1, 3, figsize=(17, 7.2), gridspec_kw={"width_ratios": [1.15, 0.6, 1.0]})
        panel_map(axes[0], d, coords, label)
        panel_demands(axes[1], d, label)
        panel_windows(axes[2], d, label)
        fig.tight_layout()
        fig.savefig(OUT / f"{name}.png", dpi=200, facecolor="white")
        plt.close(fig)

        for suffix, fn, size in (("mapa", lambda ax: panel_map(ax, d, coords, label), (7, 7.6)),
                                 ("demandas", lambda ax: panel_demands(ax, d, label), (4.2, 7.6)),
                                 ("ventanas", lambda ax: panel_windows(ax, d, label), (7, 7.2))):
            fig, ax = plt.subplots(figsize=size)
            fn(ax)
            fig.tight_layout()
            fig.savefig(OUT / f"{name}_{suffix}.png", dpi=200, facecolor="white")
            plt.close(fig)
        print(f"Graficos de {name} guardados en {OUT}")


if __name__ == "__main__":
    main()
