"""Modulo de carga y preprocesamiento de instancias.

Lee instancias en formato texto plano basado en el benchmark Solomon (1987) de CVRPLIB
y construye los conjuntos y matrices requeridos por el modelo conVRP-SLA.
"""

from __future__ import annotations
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple


def calculate_euclidean_distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Calcula la distancia euclidiana 2D entre dos puntos (x, y)."""
    return round(math.hypot(p1[0] - p2[0], p1[1] - p2[1]), 2)


def load_instance(filepath: str | Path) -> Dict[str, Any]:
    """Carga y procesa una instancia desde un archivo .txt tipo Solomon extendido.

    Estructura de columnas en seccion CUSTOMER:
    CUST_NO, XCOORD, YCOORD, DEMAND_D1, DEMAND_D2, DEMAND_D3, READY_TIME, DUE_DATE, SERVICE_TIME
    """
    path = Path(filepath)
    if not path.is_file():
        raise FileNotFoundError(f"Archivo de instancia no encontrado: {filepath}")

    with open(path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

    # -------------------------------------------------------------------------
    # Paso 1: Leer parametros globales del encabezado
    # -------------------------------------------------------------------------
    name = path.stem
    num_days = 3
    num_routes = 3
    capacity = 50.0
    big_m_val = None

    customer_lines = []
    in_customers = False

    for line in lines:
        if in_customers:
            parts = line.split()
            # Ignorar encabezados de columnas (ej. 'CUST_NO')
            if parts and parts[0].isdigit():
                customer_lines.append([float(x) for x in parts])
        elif line.upper().startswith("CUSTOMER"):
            in_customers = True
        elif ":" in line:
            key, val = [x.strip() for x in line.split(":", 1)]
            key_upper = key.upper()
            if key_upper == "NAME":
                name = val
            elif key_upper == "DAYS":
                num_days = int(val)
            elif key_upper == "ROUTES":
                num_routes = int(val)
            elif key_upper == "CAPACITY":
                capacity = float(val)
            elif key_upper == "BIG_M":
                big_m_val = float(val)

    if not customer_lines:
        raise ValueError(f"No se encontraron registros de clientes en: {filepath}")

    days = list(range(1, num_days + 1))
    routes = list(range(1, num_routes + 1))

    # -------------------------------------------------------------------------
    # Paso 2: Extraer datos del deposito (nodo 0) y clientes (nodos 1 a n)
    # -------------------------------------------------------------------------
    coords: Dict[int, Tuple[float, float]] = {}
    q: Dict[Tuple[int, int], float] = {}       # q[(cliente, dia)] = demanda
    st: Dict[Tuple[int, int], float] = {}      # st[(cliente, dia)] = tiempo servicio
    tw: Dict[int, Tuple[float, float]] = {}    # tw[cliente] = (a_i, b_i)
    NC: List[int] = []
    O: List[Tuple[int, int]] = []              # Ordenes activas (cliente, dia) con demanda > 0
    NTW: List[int] = []                        # Clientes con ventana de tiempo

    depot_start = 0
    aW, bW = 0.0, 1440.0

    for row in customer_lines:
        cid = int(row[0])
        x, y = row[1], row[2]
        demands = row[3 : 3 + num_days]
        ready_time, due_date, service_time = row[3 + num_days : 3 + num_days + 3]

        if cid == depot_start:
            # Registro del deposito
            coords[depot_start] = (x, y)
            aW, bW = ready_time, due_date
        else:
            # Registro de cliente
            NC.append(cid)
            coords[cid] = (x, y)
            tw[cid] = (ready_time, due_date)

            # Si la ventana es mas estrecha que el deposito, pertenece a NTW
            if ready_time > aW or due_date < bW:
                NTW.append(cid)

            for d_idx, d in enumerate(days):
                dem = demands[d_idx]
                q[(cid, d)] = dem
                st[(cid, d)] = service_time
                if dem > 0:
                    O.append((cid, d))

    NC.sort()
    n = len(NC)
    depot_end = n + 1                          # Nodo ficticio de retorno
    coords[depot_end] = coords[depot_start]    # Misma ubicacion que la salida
    N = [depot_start] + NC + [depot_end]

    # -------------------------------------------------------------------------
    # Paso 3: Calcular matrices de distancias (td) y tiempos de viaje (tt)
    # -------------------------------------------------------------------------
    td: Dict[Tuple[int, int], float] = {}
    tt: Dict[Tuple[int, int], float] = {}
    for i in N:
        for j in N:
            dist = calculate_euclidean_distance(coords[i], coords[j])
            td[(i, j)] = dist
            tt[(i, j)] = dist                  # Velocidad unitaria (Solomon benchmark)

    # -------------------------------------------------------------------------
    # Paso 4: Construir arcos validos (A) para cada dia
    # -------------------------------------------------------------------------
    A: List[Tuple[int, int, int]] = []
    for d in days:
        A.append((depot_start, depot_end, d))  # Bypass para rutas inactivas
        for j in NC:
            A.append((depot_start, j, d))      # Salida de deposito a cliente
            A.append((j, depot_end, d))        # Retorno de cliente a deposito
        for i in NC:
            for j in NC:
                if i != j:
                    A.append((i, j, d))        # Traslado entre clientes distintos

    # Big-M ajustado si no fue especificado manualmente
    if big_m_val is None or big_m_val <= 0:
        max_tt = max(tt.values()) if tt else 0.0
        max_st = max(st.values()) if st else 0.0
        big_m_val = round(bW + max_tt + max_st + 100.0, 2)

    return {
        "name": name,
        "NC": NC,
        "depot_start": depot_start,
        "depot_end": depot_end,
        "N": N,
        "days": days,
        "routes": routes,
        "NTW": NTW,
        "O": O,
        "A": A,
        "td": td,
        "tt": tt,
        "q": q,
        "st": st,
        "tw": tw,
        "aW": aW,
        "bW": bW,
        "Q": capacity,
        "M": big_m_val
    }
