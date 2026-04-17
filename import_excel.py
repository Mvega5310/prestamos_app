"""
Importa los datos de la hoja 'Prestamos' del Excel a prestamos.db
Solo se ejecuta una vez. Si la DB ya tiene datos, aborta.
"""
import sqlite3, os, sys
from datetime import date
import openpyxl

BASE = os.path.dirname(__file__)
DB   = os.path.join(BASE, "prestamos.db")
XLS  = os.path.join(BASE, "Control_Prestamos_n8n (1).xlsx")

# ── inicializar DB igual que app.py ──────────────────────────────────────────
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
conn.executescript("""
    CREATE TABLE IF NOT EXISTS prestamos (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre      TEXT    NOT NULL,
        fecha       DATE    NOT NULL,
        capital     INTEGER NOT NULL,
        interes_pct REAL    NOT NULL DEFAULT 20,
        interes     INTEGER NOT NULL,
        total_pagar INTEGER NOT NULL,
        fecha_vence DATE,
        estado      TEXT    NOT NULL DEFAULT 'En curso',
        notas       TEXT,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS abonos (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        prestamo_id INTEGER NOT NULL REFERENCES prestamos(id),
        fecha       DATE    NOT NULL,
        monto       INTEGER NOT NULL,
        notas       TEXT,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );
""")

existing = conn.execute("SELECT COUNT(*) FROM prestamos").fetchone()[0]
if existing > 0:
    print(f"La DB ya tiene {existing} registros. No se importará de nuevo.")
    conn.close()
    sys.exit(0)

# ── leer Excel ───────────────────────────────────────────────────────────────
wb = openpyxl.load_workbook(XLS, data_only=True)
ws = wb["Prestamos"]

prestamos_ok = 0
abonos_ok    = 0
omitidos     = 0

for row in ws.iter_rows(min_row=2, values_only=True):
    # columnas: 0=ID, 1=Nombre, 2=FechaPrestamo, 3=Capital, 4=Interes,
    #           5=Total, 6=NumCuotas, 7=FechaAbono, 8=MontoAbono,
    #           9=SaldoRestante, 10=Estado, 11=FechaPagoCompleto
    nombre      = row[1]
    fecha_raw   = row[2]
    capital_raw = row[3]
    interes_raw = row[4]
    total_raw   = row[5]
    fecha_abono = row[7]
    monto_abono = row[8]
    saldo_raw   = row[9]
    estado_raw  = row[10]

    if not nombre or not fecha_raw or not capital_raw:
        omitidos += 1
        continue

    # fecha del préstamo
    if hasattr(fecha_raw, "date"):
        fecha = fecha_raw.date().isoformat()
    else:
        try:
            fecha = str(fecha_raw)[:10]
        except Exception:
            omitidos += 1
            continue

    capital = int(capital_raw) if capital_raw else 0
    if capital <= 0:
        omitidos += 1
        continue

    # interes_pct: deducido del valor
    interes = 0
    if interes_raw and isinstance(interes_raw, (int, float)):
        interes = int(interes_raw)
    interes_pct = round((interes / capital * 100), 1) if capital else 20

    total_pagar = int(total_raw) if total_raw and isinstance(total_raw, (int, float)) else capital + interes

    estado = "Pagado" if str(estado_raw or "").strip() == "Pagado" else "En curso"

    saldo = int(saldo_raw) if saldo_raw and isinstance(saldo_raw, (int, float)) else total_pagar

    # fecha_vence: usamos la fecha del abono del Excel como fecha esperada
    fecha_vence = None
    if fecha_abono and hasattr(fecha_abono, "date"):
        fecha_vence = fecha_abono.date().isoformat()
    elif fecha_abono:
        try:
            fecha_vence = str(fecha_abono)[:10]
        except Exception:
            pass

    cursor = conn.execute("""
        INSERT INTO prestamos (nombre,fecha,capital,interes_pct,interes,total_pagar,fecha_vence,estado)
        VALUES (?,?,?,?,?,?,?,?)
    """, (str(nombre).strip(), fecha, capital, interes_pct, interes, total_pagar, fecha_vence, estado))
    pid = cursor.lastrowid
    prestamos_ok += 1

    # si el estado es Pagado y hay monto_abono, registrar el abono
    if estado == "Pagado" and monto_abono and isinstance(monto_abono, (int, float)) and monto_abono > 0:
        fecha_abono_str = fecha_vence or fecha
        conn.execute(
            "INSERT INTO abonos (prestamo_id,fecha,monto) VALUES (?,?,?)",
            (pid, fecha_abono_str, int(monto_abono))
        )
        abonos_ok += 1
    elif estado == "En curso" and monto_abono and isinstance(monto_abono, (int, float)) and monto_abono > 0:
        # abono parcial
        ya_pagado = total_pagar - saldo
        if ya_pagado > 0:
            fecha_abono_str = fecha_vence or fecha
            conn.execute(
                "INSERT INTO abonos (prestamo_id,fecha,monto) VALUES (?,?,?)",
                (pid, fecha_abono_str, int(ya_pagado))
            )
            abonos_ok += 1

conn.commit()
conn.close()

print(f"✓ Importados: {prestamos_ok} préstamos, {abonos_ok} abonos. Omitidos: {omitidos} filas.")
