"""Generador de instancias multi-dia para el conVRP-SLA (formato Solomon extendido).

Construye instancias ficticias de retiro de muestras clinicas con estructura
multi-dia real: cada consultorio tiene una frecuencia de retiro (diaria, 2 dias
o 1 dia por semana de planificacion), por lo que no todos piden todos los dias.

Las instancias son factibles por construccion:
1. Se generan coordenadas (barrios compactos o dispersas) y frecuencias.
2. Se arma una solucion de referencia consistente: los clientes se reparten en
   3 rutas por barrido angular y, cada dia, cada ruta visita a sus clientes con
   pedido en orden de vecino mas cercano.
3. La capacidad Q se fija desde la mayor carga diaria de esa solucion (+ margen).
4. Las ventanas cubren las horas de llegada de la solucion en todos los dias en
   que el cliente pide (+ holgura), asi que la solucion de referencia las cumple.
5. El cierre del deposito bW y el Big-M se calculan desde la misma solucion.

Uso (desde la raiz del repo):
    py -3.13 instances/generar_instancias.py
"""

from __future__ import annotations
import math
import random
from dataclasses import dataclass
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
DEPOT = (50.0, 50.0)
SERVICE_TIME = 10.0


@dataclass
class Config:
    name: str
    seed: int
    layout: str                 # "clustered" o "random"
    n_customers: int
    n_daily: int                # clientes que piden los 3 dias
    n_two_days: int             # clientes que piden 2 de los 3 dias
    days: int = 3
    routes: int = 3
    q_margin: float = 0.05      # holgura de capacidad sobre la mayor carga
    tw_slack: float = 15.0      # holgura de las ventanas (min)
    tw_share: float = 0.7       # fraccion de clientes con ventana propia
    depot_margin: float = 20.0  # holgura del cierre del deposito (min)


# Calibradas para que no sean triviales: con 16 clientes ambos solvers cierran en
# segundos; con 20 Gurobi no cierra en 90 s. Con 18 y ventanas anchas (que debilitan
# el Big-M) Gurobi prueba optimalidad en ~1,5 min.
CONFIGS = [
    Config("muestras_A_barrios", seed=11, layout="clustered", n_customers=18, n_daily=7, n_two_days=7,
           tw_share=0.5, tw_slack=30, q_margin=0.03),
    Config("muestras_B_dispersa", seed=23, layout="random", n_customers=18, n_daily=7, n_two_days=7,
           tw_share=0.5, tw_slack=30, q_margin=0.03),
]


def dist(a, b) -> float:
    return round(math.hypot(a[0] - b[0], a[1] - b[1]), 2)


def gen_coords(cfg: Config, rng: random.Random) -> list[tuple[float, float]]:
    if cfg.layout == "random":
        pts = []
        while len(pts) < cfg.n_customers:
            p = (float(rng.randint(5, 95)), float(rng.randint(5, 95)))
            if dist(p, DEPOT) > 8 and p not in pts:
                pts.append(p)
        return pts
    # Barrios compactos alrededor de 3 centros
    centers = [(22.0, 78.0), (80.0, 70.0), (45.0, 20.0)]
    pts = []
    k = 0
    while len(pts) < cfg.n_customers:
        cx, cy = centers[k % len(centers)]
        p = (float(round(cx + rng.gauss(0, 7))), float(round(cy + rng.gauss(0, 7))))
        p = (min(max(p[0], 2.0), 98.0), min(max(p[1], 2.0), 98.0))
        if p not in pts:
            pts.append(p)
            k += 1
    return pts


def gen_demands(cfg: Config, rng: random.Random) -> list[list[float]]:
    """Demanda por cliente y dia; 0 = no pide ese dia."""
    n, D = cfg.n_customers, cfg.days
    n_one = n - cfg.n_daily - cfg.n_two_days
    kinds = ["diario"] * cfg.n_daily + ["2dias"] * cfg.n_two_days + ["1dia"] * n_one
    rng.shuffle(kinds)
    demands = []
    skip_cycle, only_cycle = 0, 0
    for kind in kinds:
        base = rng.randint(6, 20)
        if kind == "diario":
            active = set(range(D))
        elif kind == "2dias":
            active = set(range(D)) - {skip_cycle % D}   # rota el dia sin pedido
            skip_cycle += 1
        else:
            active = {only_cycle % D}                    # rota el unico dia con pedido
            only_cycle += 1
        row = []
        for t in range(D):
            row.append(float(max(1, round(base * rng.uniform(0.75, 1.25)))) if t in active else 0.0)
        demands.append(row)
    return demands


def reference_solution(cfg: Config, coords, demands):
    """Asignacion consistente por barrido angular + secuencia diaria por vecino mas cercano."""
    n, R, D = cfg.n_customers, cfg.routes, cfg.days
    order = sorted(range(n), key=lambda i: math.atan2(coords[i][1] - DEPOT[1], coords[i][0] - DEPOT[0]))
    total = sum(sum(r) for r in demands)
    assign, acc, r = {}, 0.0, 0
    for i in order:
        if acc >= total * (r + 1) / R and r < R - 1:
            r += 1
        assign[i] = r
        acc += sum(demands[i])

    arrivals = {i: [] for i in range(n)}   # horas de inicio de servicio en los dias con pedido
    loads, returns, total_dist = [], [], 0.0
    for t in range(D):
        for r in range(R):
            todo = [i for i in range(n) if assign[i] == r and demands[i][t] > 0]
            loads.append(sum(demands[i][t] for i in todo))
            pos, clock = DEPOT, 0.0
            while todo:
                nxt = min(todo, key=lambda i: dist(pos, coords[i]))
                clock += dist(pos, coords[nxt])
                total_dist += dist(pos, coords[nxt])
                arrivals[nxt].append(clock)
                clock += SERVICE_TIME
                pos = coords[nxt]
                todo.remove(nxt)
            total_dist += dist(pos, DEPOT)
            returns.append(clock + dist(pos, DEPOT))
    return assign, arrivals, max(loads), max(returns), round(total_dist, 1)


def build(cfg: Config) -> dict:
    rng = random.Random(cfg.seed)
    coords = gen_coords(cfg, rng)
    demands = gen_demands(cfg, rng)
    assign, arrivals, max_load, max_return, ref_dist = reference_solution(cfg, coords, demands)

    bW = float(math.ceil((max_return + cfg.depot_margin) / 10.0) * 10)
    Q = float(math.ceil(max_load * (1 + cfg.q_margin)))

    with_tw = set(rng.sample(range(cfg.n_customers), round(cfg.tw_share * cfg.n_customers)))
    windows = []
    for i in range(cfg.n_customers):
        if i in with_tw:
            a = max(0.0, math.floor(min(arrivals[i]) - cfg.tw_slack))
            b = min(bW, math.ceil(max(arrivals[i]) + cfg.tw_slack))
            windows.append((float(a), float(b)))
        else:
            windows.append((0.0, bW))

    pts = [DEPOT] + coords
    max_tt = max(dist(p, q) for p in pts for q in pts)
    big_m = float(math.ceil(bW + SERVICE_TIME + max_tt + 1))

    return {"cfg": cfg, "coords": coords, "demands": demands, "windows": windows,
            "Q": Q, "bW": bW, "M": big_m, "ref_dist": ref_dist, "assign": assign}


def write(inst: dict) -> Path:
    cfg = inst["cfg"]
    path = OUT_DIR / f"{cfg.name}.txt"
    lines = [
        f"# Instancia ficticia {cfg.name} - generada con generar_instancias.py "
        f"(seed={cfg.seed}, layout={cfg.layout})",
        f"# Factible por construccion (solucion de referencia de distancia {inst['ref_dist']})",
        "# Estructura multi-dia: demanda 0 = el consultorio no pide ese dia",
        "",
        f"NAME: {cfg.name}",
        f"DAYS: {cfg.days}",
        f"ROUTES: {cfg.routes}",
        f"CAPACITY: {inst['Q']}",
        f"BIG_M: {inst['M']}",
        "",
        "CUSTOMER",
        "CUST_NO  XCOORD  YCOORD  " + "  ".join(f"DEMAND_D{t + 1}" for t in range(cfg.days))
        + "  READY_TIME  DUE_DATE  SERVICE_TIME",
        f"0  {DEPOT[0]}  {DEPOT[1]}  " + "  ".join("0.0" for _ in range(cfg.days))
        + f"  0.0  {inst['bW']}  0.0",
    ]
    for i, (x, y) in enumerate(inst["coords"]):
        a, b = inst["windows"][i]
        lines.append(f"{i + 1}  {x}  {y}  " + "  ".join(str(v) for v in inst["demands"][i])
                     + f"  {a}  {b}  {SERVICE_TIME}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def describe(inst: dict) -> str:
    cfg, dem = inst["cfg"], inst["demands"]
    n, D = cfg.n_customers, cfg.days
    freq = [sum(1 for v in row if v > 0) for row in dem]
    per_day = [sum(1 for i in range(n) if dem[i][t] > 0) for t in range(D)]
    util = [sum(dem[i][t] for i in range(n)) / (inst["Q"] * cfg.routes) for t in range(D)]
    n_tw = sum(1 for w in inst["windows"] if w != (0.0, inst["bW"]))
    return (f"{cfg.name}: {n} clientes | frecuencia 3/2/1 dias = {freq.count(3)}/{freq.count(2)}/{freq.count(1)} | "
            f"pedidos por dia {per_day} (total {sum(per_day)} de {n * D}) | Q={inst['Q']:.0f} | "
            f"uso de Q {'/'.join(f'{u:.0%}' for u in util)} | con ventana {n_tw} | bW={inst['bW']:.0f} | "
            f"M={inst['M']:.0f} | ref={inst['ref_dist']}")


def main() -> None:
    for cfg in CONFIGS:
        inst = build(cfg)
        path = write(inst)
        print(describe(inst))
        print(f"  -> {path}")


if __name__ == "__main__":
    main()
