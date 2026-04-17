from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import sqlite3, os
from datetime import date, datetime, timedelta

app = Flask(__name__)
app.secret_key = "prestamos_secret_2024"

DB = os.path.join(os.path.dirname(__file__), "prestamos.db")


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
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


def saldo(prestamo_id, total_pagar, conn):
    row = conn.execute(
        "SELECT COALESCE(SUM(monto),0) FROM abonos WHERE prestamo_id=?",
        (prestamo_id,)
    ).fetchone()
    return total_pagar - row[0]


# ── helpers ──────────────────────────────────────────────────────────────────

def fmt_cop(n):
    try:
        return f"${int(n):,}".replace(",", ".")
    except Exception:
        return n

app.jinja_env.filters["cop"] = fmt_cop


def days_label(fecha_vence_str):
    if not fecha_vence_str:
        return None, None
    try:
        fv = date.fromisoformat(str(fecha_vence_str)[:10])
        delta = (fv - date.today()).days
        return delta, fv
    except Exception:
        return None, None


app.jinja_env.globals["today"] = date.today


# ── routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    conn = get_db()
    totales = conn.execute("""
        SELECT
            COUNT(*)                                                     AS total_prestamos,
            COALESCE(SUM(capital),0)                                     AS total_capital,
            COALESCE(SUM(total_pagar),0)                                 AS total_emitido,
            COUNT(CASE WHEN estado='En curso' THEN 1 END)                AS activos,
            COUNT(CASE WHEN estado='Pagado'   THEN 1 END)                AS pagados
        FROM prestamos
    """).fetchone()

    total_abonado = conn.execute(
        "SELECT COALESCE(SUM(monto),0) FROM abonos"
    ).fetchone()[0]

    # Préstamos activos con saldo
    activos = conn.execute("""
        SELECT p.*, COALESCE(SUM(a.monto),0) AS abonado
        FROM prestamos p
        LEFT JOIN abonos a ON a.prestamo_id = p.id
        WHERE p.estado = 'En curso'
        GROUP BY p.id
        ORDER BY p.fecha_vence ASC NULLS LAST
    """).fetchall()

    alertas = []
    for p in activos:
        sal = p["total_pagar"] - p["abonado"]
        dias, fv = days_label(p["fecha_vence"])
        if dias is not None and dias <= 3:
            alertas.append({
                "id": p["id"], "nombre": p["nombre"],
                "saldo": sal, "dias": dias, "fecha_vence": fv
            })

    conn.close()
    return render_template("dashboard.html",
                           totales=totales,
                           total_abonado=total_abonado,
                           pendiente=totales["total_emitido"] - total_abonado,
                           alertas=alertas)


@app.route("/prestamos")
def lista_prestamos():
    filtro = request.args.get("filtro", "activos")
    conn = get_db()
    if filtro == "todos":
        rows = conn.execute("""
            SELECT p.*, COALESCE(SUM(a.monto),0) AS abonado
            FROM prestamos p
            LEFT JOIN abonos a ON a.prestamo_id = p.id
            GROUP BY p.id ORDER BY p.fecha DESC
        """).fetchall()
    elif filtro == "pagados":
        rows = conn.execute("""
            SELECT p.*, COALESCE(SUM(a.monto),0) AS abonado
            FROM prestamos p
            LEFT JOIN abonos a ON a.prestamo_id = p.id
            WHERE p.estado='Pagado'
            GROUP BY p.id ORDER BY p.fecha DESC
        """).fetchall()
    else:
        rows = conn.execute("""
            SELECT p.*, COALESCE(SUM(a.monto),0) AS abonado
            FROM prestamos p
            LEFT JOIN abonos a ON a.prestamo_id = p.id
            WHERE p.estado='En curso'
            GROUP BY p.id ORDER BY p.fecha_vence ASC NULLS LAST
        """).fetchall()

    prestamos = []
    for p in rows:
        sal = p["total_pagar"] - p["abonado"]
        dias, fv = days_label(p["fecha_vence"])
        prestamos.append({**dict(p), "saldo": sal, "dias": dias})

    conn.close()
    return render_template("prestamos.html", prestamos=prestamos, filtro=filtro)


@app.route("/api/nombres")
def api_nombres():
    q = request.args.get("q", "").strip()
    conn = get_db()
    rows = conn.execute("""
        SELECT DISTINCT nombre FROM prestamos
        WHERE nombre LIKE ? COLLATE NOCASE
        ORDER BY nombre LIMIT 10
    """, (f"%{q}%",)).fetchall()
    conn.close()
    return jsonify([r["nombre"] for r in rows])


@app.route("/prestamos/nuevo", methods=["GET", "POST"])
def nuevo_prestamo():
    if request.method == "POST":
        nombre      = request.form["nombre"].strip()
        fecha       = request.form["fecha"]
        capital     = int(request.form["capital"])
        interes_pct = float(request.form.get("interes_pct", 20))
        interes     = int(capital * interes_pct / 100)
        total_pagar = capital + interes
        fecha_vence = request.form.get("fecha_vence") or None
        notas       = request.form.get("notas", "").strip() or None

        with get_db() as conn:
            conn.execute("""
                INSERT INTO prestamos (nombre,fecha,capital,interes_pct,interes,total_pagar,fecha_vence,notas)
                VALUES (?,?,?,?,?,?,?,?)
            """, (nombre, fecha, capital, interes_pct, interes, total_pagar, fecha_vence, notas))

        flash(f"Préstamo de {nombre} registrado exitosamente.", "success")
        return redirect(url_for("lista_prestamos"))

    return render_template("nuevo_prestamo.html", hoy=date.today().isoformat())


@app.route("/prestamos/<int:pid>")
def detalle_prestamo(pid):
    conn = get_db()
    p = conn.execute("SELECT * FROM prestamos WHERE id=?", (pid,)).fetchone()
    if not p:
        conn.close()
        flash("Préstamo no encontrado.", "danger")
        return redirect(url_for("lista_prestamos"))

    abonos_list = conn.execute(
        "SELECT * FROM abonos WHERE prestamo_id=? ORDER BY fecha DESC",
        (pid,)
    ).fetchall()
    total_abonado = sum(a["monto"] for a in abonos_list)
    sal = p["total_pagar"] - total_abonado
    dias, fv = days_label(p["fecha_vence"])
    conn.close()
    return render_template("detalle_prestamo.html",
                           p=p, abonos=abonos_list,
                           total_abonado=total_abonado,
                           saldo=sal, dias=dias,
                           hoy=date.today().isoformat())


@app.route("/prestamos/<int:pid>/abono", methods=["POST"])
def registrar_abono(pid):
    fecha = request.form["fecha"]
    monto = int(request.form["monto"])
    notas = request.form.get("notas", "").strip() or None

    with get_db() as conn:
        p = conn.execute("SELECT * FROM prestamos WHERE id=?", (pid,)).fetchone()
        if not p:
            flash("Préstamo no encontrado.", "danger")
            return redirect(url_for("lista_prestamos"))

        ya_abonado = conn.execute(
            "SELECT COALESCE(SUM(monto),0) FROM abonos WHERE prestamo_id=?", (pid,)
        ).fetchone()[0]
        sal = p["total_pagar"] - ya_abonado

        if monto > sal:
            flash(f"El abono ({fmt_cop(monto)}) supera el saldo ({fmt_cop(sal)}).", "warning")
            return redirect(url_for("detalle_prestamo", pid=pid))

        conn.execute(
            "INSERT INTO abonos (prestamo_id,fecha,monto,notas) VALUES (?,?,?,?)",
            (pid, fecha, monto, notas)
        )

        nuevo_saldo = sal - monto
        if nuevo_saldo == 0:
            conn.execute(
                "UPDATE prestamos SET estado='Pagado' WHERE id=?", (pid,)
            )
            flash("Abono registrado. ¡Préstamo pagado completamente!", "success")
        else:
            flash(f"Abono de {fmt_cop(monto)} registrado. Saldo restante: {fmt_cop(nuevo_saldo)}.", "success")

    return redirect(url_for("detalle_prestamo", pid=pid))


@app.route("/prestamos/<int:pid>/editar", methods=["GET", "POST"])
def editar_prestamo(pid):
    conn = get_db()
    p = conn.execute("SELECT * FROM prestamos WHERE id=?", (pid,)).fetchone()
    if not p:
        conn.close()
        flash("Préstamo no encontrado.", "danger")
        return redirect(url_for("lista_prestamos"))

    if request.method == "POST":
        nombre      = request.form["nombre"].strip()
        fecha_vence = request.form.get("fecha_vence") or None
        notas       = request.form.get("notas", "").strip() or None
        with conn:
            conn.execute(
                "UPDATE prestamos SET nombre=?, fecha_vence=?, notas=? WHERE id=?",
                (nombre, fecha_vence, notas, pid)
            )
        conn.close()
        flash("Préstamo actualizado.", "success")
        return redirect(url_for("detalle_prestamo", pid=pid))

    conn.close()
    return render_template("editar_prestamo.html", p=p)


@app.route("/reportes")
def reportes():
    conn = get_db()

    mes_param = request.args.get("mes", "")  # formato YYYY-MM

    # Por mes
    por_mes = conn.execute("""
        SELECT strftime('%Y-%m', fecha) AS mes,
               COUNT(*) AS cantidad,
               SUM(capital) AS capital,
               SUM(total_pagar) AS total
        FROM prestamos
        GROUP BY mes ORDER BY mes DESC
        LIMIT 24
    """).fetchall()

    # Por prestatario
    por_persona = conn.execute("""
        SELECT nombre,
               COUNT(*) AS veces,
               SUM(capital) AS capital_total,
               SUM(total_pagar) AS total_pagar,
               COALESCE(SUM(a.abonado),0) AS abonado,
               SUM(total_pagar) - COALESCE(SUM(a.abonado),0) AS pendiente
        FROM prestamos p
        LEFT JOIN (
            SELECT prestamo_id, SUM(monto) AS abonado FROM abonos GROUP BY prestamo_id
        ) a ON a.prestamo_id = p.id
        GROUP BY nombre ORDER BY pendiente DESC, capital_total DESC
    """).fetchall()

    # Totales generales
    totales = conn.execute("""
        SELECT COUNT(*) AS n,
               SUM(capital) AS capital,
               SUM(interes) AS interes,
               SUM(total_pagar) AS total
        FROM prestamos
    """).fetchone()
    total_cobrado = conn.execute("SELECT COALESCE(SUM(monto),0) FROM abonos").fetchone()[0]

    conn.close()
    return render_template("reportes.html",
                           por_mes=por_mes,
                           por_persona=por_persona,
                           totales=totales,
                           total_cobrado=total_cobrado)


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5050)
