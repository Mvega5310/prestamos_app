"""
Importa los datos de la hoja 'Prestamos' del Excel.
Ejecutar una sola vez: python3 import_excel.py
Si la DB ya tiene préstamos, aborta para no duplicar.
"""
import os, sys
from datetime import date
import openpyxl

BASE = os.path.dirname(os.path.abspath(__file__))
XLS  = os.path.join(BASE, "Control_Prestamos_n8n (1).xlsx")

# Usar la misma variable de entorno que app.py
os.environ.setdefault(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(BASE, "prestamos.db")
)

from app import app, db, Prestamo, Abono

with app.app_context():
    db.create_all()

    if Prestamo.query.count() > 0:
        print(f"La DB ya tiene {Prestamo.query.count()} préstamos. No se importará de nuevo.")
        sys.exit(0)

    wb = openpyxl.load_workbook(XLS, data_only=True)
    ws = wb["Prestamos"]

    ok = 0
    abonos_ok = 0
    omitidos = 0

    for row in ws.iter_rows(min_row=2, values_only=True):
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

        capital = int(capital_raw) if capital_raw else 0
        if capital <= 0:
            omitidos += 1
            continue

        if hasattr(fecha_raw, "date"):
            fecha = fecha_raw.date()
        else:
            try:
                fecha = date.fromisoformat(str(fecha_raw)[:10])
            except Exception:
                omitidos += 1
                continue

        interes = int(interes_raw) if interes_raw and isinstance(interes_raw, (int, float)) else 0
        interes_pct = round(interes / capital * 100, 1) if capital else 20
        total_pagar = int(total_raw) if total_raw and isinstance(total_raw, (int, float)) else capital + interes
        estado = "Pagado" if str(estado_raw or "").strip() == "Pagado" else "En curso"
        saldo = int(saldo_raw) if saldo_raw and isinstance(saldo_raw, (int, float)) else total_pagar

        fecha_vence = None
        if fecha_abono and hasattr(fecha_abono, "date"):
            fecha_vence = fecha_abono.date()
        elif fecha_abono:
            try:
                fecha_vence = date.fromisoformat(str(fecha_abono)[:10])
            except Exception:
                pass

        p = Prestamo(
            nombre=str(nombre).strip(),
            fecha=fecha,
            capital=capital,
            interes_pct=interes_pct,
            interes=interes,
            total_pagar=total_pagar,
            fecha_vence=fecha_vence,
            estado=estado,
        )
        db.session.add(p)
        db.session.flush()

        if estado == "Pagado" and monto_abono and isinstance(monto_abono, (int, float)) and monto_abono > 0:
            db.session.add(Abono(
                prestamo_id=p.id,
                fecha=fecha_vence or fecha,
                monto=int(monto_abono)
            ))
            abonos_ok += 1
        elif estado == "En curso":
            ya_pagado = total_pagar - saldo
            if ya_pagado > 0:
                db.session.add(Abono(
                    prestamo_id=p.id,
                    fecha=fecha_vence or fecha,
                    monto=ya_pagado
                ))
                abonos_ok += 1

        ok += 1

    db.session.commit()
    print(f"✓ Importados: {ok} préstamos, {abonos_ok} abonos. Omitidos: {omitidos} filas.")
