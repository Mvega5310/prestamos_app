from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import subqueryload
from functools import wraps
from datetime import date, datetime
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_local_prestamos_2024")

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(os.path.dirname(os.path.abspath(__file__)), "prestamos.db")
)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Inicia sesión para continuar."
login_manager.login_message_category = "warning"


# ── Modelos ───────────────────────────────────────────────────────────────────

class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    nombre        = db.Column(db.String(120))
    rol           = db.Column(db.String(20), default="viewer")  # admin | viewer
    activo        = db.Column(db.Boolean, default=True)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw, method="pbkdf2:sha256")

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class Prestamo(db.Model):
    __tablename__ = "prestamos"
    id          = db.Column(db.Integer, primary_key=True)
    nombre      = db.Column(db.String(120), nullable=False)
    fecha       = db.Column(db.Date, nullable=False)
    capital     = db.Column(db.Integer, nullable=False)
    interes_pct = db.Column(db.Float, default=20.0)
    interes     = db.Column(db.Integer, nullable=False)
    total_pagar = db.Column(db.Integer, nullable=False)
    fecha_vence = db.Column(db.Date)
    estado      = db.Column(db.String(20), default="En curso")
    notas       = db.Column(db.Text)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    abonos      = db.relationship("Abono", backref="prestamo", lazy=True,
                                  cascade="all, delete-orphan")

    @property
    def total_abonado(self):
        return sum(a.monto for a in self.abonos)

    @property
    def saldo(self):
        return self.total_pagar - self.total_abonado

    @property
    def dias_vence(self):
        if not self.fecha_vence:
            return None
        return (self.fecha_vence - date.today()).days


class Abono(db.Model):
    __tablename__ = "abonos"
    id          = db.Column(db.Integer, primary_key=True)
    prestamo_id = db.Column(db.Integer, db.ForeignKey("prestamos.id"), nullable=False)
    fecha       = db.Column(db.Date, nullable=False)
    monto       = db.Column(db.Integer, nullable=False)
    notas       = db.Column(db.Text)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)


class Configuracion(db.Model):
    __tablename__ = "configuracion"
    clave = db.Column(db.String(80), primary_key=True)
    valor = db.Column(db.String(256), nullable=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

@login_manager.user_loader
def load_user(uid):
    return db.session.get(Usuario, int(uid))


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.rol != "admin":
            flash("Necesitas permisos de administrador.", "danger")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated


def get_config(clave, default="0"):
    row = db.session.get(Configuracion, clave)
    return row.valor if row else default

def set_config(clave, valor):
    row = db.session.get(Configuracion, clave)
    if row:
        row.valor = str(valor)
    else:
        db.session.add(Configuracion(clave=clave, valor=str(valor)))
    db.session.commit()


def fmt_cop(n):
    try:
        return f"${int(n):,}".replace(",", ".")
    except Exception:
        return n

app.jinja_env.filters["cop"] = fmt_cop
app.jinja_env.globals["today"] = date.today

# Crea las tablas al iniciar (funciona con gunicorn y python directo)
with app.app_context():
    db.create_all()


# ── Setup primer uso ──────────────────────────────────────────────────────────

@app.route("/setup", methods=["GET", "POST"])
def setup():
    if Usuario.query.count() > 0:
        return redirect(url_for("login"))
    if request.method == "POST":
        u = Usuario(
            username=request.form["username"].strip(),
            nombre=request.form["nombre"].strip(),
            rol="admin"
        )
        u.set_password(request.form["password"])
        db.session.add(u)
        db.session.commit()
        flash("Administrador creado. Ya puedes iniciar sesión.", "success")
        return redirect(url_for("login"))
    return render_template("setup.html")


# ── Login / Logout ────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        u = Usuario.query.filter_by(
            username=request.form["username"].strip(), activo=True
        ).first()
        if u and u.check_password(request.form["password"]):
            login_user(u, remember=request.form.get("remember") == "on")
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Usuario o contraseña incorrectos.", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def dashboard():
    activos = (Prestamo.query
               .filter_by(estado="En curso")
               .options(subqueryload(Prestamo.abonos))
               .order_by(Prestamo.fecha_vence.asc().nullslast())
               .all())

    total_capital = db.session.query(db.func.sum(Prestamo.capital)).scalar() or 0
    total_emitido = db.session.query(db.func.sum(Prestamo.total_pagar)).scalar() or 0
    total_abonado = db.session.query(db.func.sum(Abono.monto)).scalar() or 0
    total_count   = Prestamo.query.count()
    pagados_count = Prestamo.query.filter_by(estado="Pagado").count()
    pendiente     = sum(p.saldo for p in activos)
    capital_inicial = int(get_config("capital_inicial", "0"))
    ganancia_neta   = db.session.query(db.func.sum(Prestamo.interes)).scalar() or 0

    alertas = [p for p in activos if p.dias_vence is not None and p.dias_vence <= 3]

    return render_template("dashboard.html",
        total_capital=total_capital,
        total_abonado=total_abonado,
        pendiente=pendiente,
        total_count=total_count,
        total_activos=len(activos),
        total_pagados=pagados_count,
        capital_inicial=capital_inicial,
        ganancia_neta=ganancia_neta,
        activos=activos,
        alertas=alertas)


# ── Lista préstamos ───────────────────────────────────────────────────────────

@app.route("/prestamos")
@login_required
def lista_prestamos():
    filtro   = request.args.get("filtro", "activos")
    if current_user.rol != "admin":
        filtro = "activos"
    buscar   = request.args.get("q", "").strip()
    page     = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    if per_page not in (10, 20, 50):
        per_page = 10

    q = Prestamo.query.options(subqueryload(Prestamo.abonos))

    if buscar:
        q = q.filter(Prestamo.nombre.ilike(f"%{buscar}%"))

    if filtro == "pagados":
        q = q.filter_by(estado="Pagado").order_by(Prestamo.fecha.desc(), Prestamo.id.desc())
    elif filtro == "todos":
        q = q.order_by(Prestamo.fecha.desc(), Prestamo.id.desc())
    else:
        q = (q.filter_by(estado="En curso")
               .order_by(Prestamo.fecha.desc(), Prestamo.id.desc()))

    paginacion = q.paginate(page=page, per_page=per_page, error_out=False)
    return render_template("prestamos.html",
                           prestamos=paginacion.items,
                           paginacion=paginacion,
                           filtro=filtro,
                           buscar=buscar,
                           per_page=per_page)


# ── Nuevo préstamo ────────────────────────────────────────────────────────────

@app.route("/prestamos/nuevo", methods=["GET", "POST"])
@admin_required
def nuevo_prestamo():
    if request.method == "POST":
        capital     = int(request.form["capital"])
        interes_pct = float(request.form.get("interes_pct", 20))
        interes     = round(capital * interes_pct / 100)
        fv_str      = request.form.get("fecha_vence")

        p = Prestamo(
            nombre      = request.form["nombre"].strip(),
            fecha       = date.fromisoformat(request.form["fecha"]),
            capital     = capital,
            interes_pct = interes_pct,
            interes     = interes,
            total_pagar = capital + interes,
            fecha_vence = date.fromisoformat(fv_str) if fv_str else None,
            notas       = request.form.get("notas", "").strip() or None,
        )
        db.session.add(p)
        db.session.commit()
        flash(f"Préstamo de {p.nombre} registrado.", "success")
        return redirect(url_for("lista_prestamos"))

    return render_template("nuevo_prestamo.html", hoy=date.today().isoformat())


# ── Detalle préstamo ──────────────────────────────────────────────────────────

@app.route("/prestamos/<int:pid>")
@login_required
def detalle_prestamo(pid):
    p = (Prestamo.query
         .options(subqueryload(Prestamo.abonos))
         .get_or_404(pid))
    abonos = sorted(p.abonos, key=lambda a: a.fecha, reverse=True)
    return render_template("detalle_prestamo.html",
        p=p, abonos=abonos, hoy=date.today().isoformat())


# ── Registrar abono ───────────────────────────────────────────────────────────

@app.route("/prestamos/<int:pid>/abono", methods=["POST"])
@admin_required
def registrar_abono(pid):
    p = Prestamo.query.options(subqueryload(Prestamo.abonos)).get_or_404(pid)
    monto = int(request.form["monto"])

    if monto > p.saldo:
        flash(f"El abono ({fmt_cop(monto)}) supera el saldo ({fmt_cop(p.saldo)}).", "warning")
        return redirect(url_for("detalle_prestamo", pid=pid))

    a = Abono(
        prestamo_id = pid,
        fecha       = date.fromisoformat(request.form["fecha"]),
        monto       = monto,
        notas       = request.form.get("notas", "").strip() or None,
    )
    db.session.add(a)

    if p.saldo - monto == 0:
        p.estado = "Pagado"
        flash(f"Abono registrado. ¡Préstamo de {p.nombre} completamente pagado!", "success")
    else:
        flash(f"Abono de {fmt_cop(monto)} registrado. Saldo: {fmt_cop(p.saldo - monto)}.", "success")

    db.session.commit()
    return redirect(url_for("detalle_prestamo", pid=pid))


# ── Editar abono ──────────────────────────────────────────────────────────────

@app.route("/abonos/<int:aid>/editar", methods=["POST"])
@admin_required
def editar_abono(aid):
    a = Abono.query.get_or_404(aid)
    monto_nuevo = int(request.form["monto"])
    otros_abonos = sum(x.monto for x in a.prestamo.abonos if x.id != a.id)
    if monto_nuevo < 1 or otros_abonos + monto_nuevo > a.prestamo.total_pagar:
        flash("Monto inválido: supera el total a pagar.", "warning")
        return redirect(url_for("detalle_prestamo", pid=a.prestamo_id))
    a.fecha = date.fromisoformat(request.form["fecha"])
    a.monto = monto_nuevo
    a.notas = request.form.get("notas", "").strip() or None
    if a.prestamo.estado == "Pagado" and a.prestamo.saldo != 0:
        a.prestamo.estado = "En curso"
    elif a.prestamo.estado == "En curso" and a.prestamo.saldo == 0:
        a.prestamo.estado = "Pagado"
    db.session.commit()
    flash("Abono actualizado.", "success")
    return redirect(url_for("detalle_prestamo", pid=a.prestamo_id))


# ── Editar préstamo ───────────────────────────────────────────────────────────

@app.route("/prestamos/<int:pid>/editar", methods=["GET", "POST"])
@admin_required
def editar_prestamo(pid):
    p = Prestamo.query.get_or_404(pid)
    if request.method == "POST":
        capital     = int(request.form["capital"])
        interes_pct = float(request.form.get("interes_pct", 20))
        interes     = round(capital * interes_pct / 100)
        p.nombre      = request.form["nombre"].strip()
        p.fecha       = date.fromisoformat(request.form["fecha"])
        fv_str        = request.form.get("fecha_vence")
        p.fecha_vence = date.fromisoformat(fv_str) if fv_str else None
        p.capital     = capital
        p.interes_pct = interes_pct
        p.interes     = interes
        p.total_pagar = capital + interes
        p.estado      = request.form.get("estado", "En curso")
        p.notas       = request.form.get("notas", "").strip() or None
        db.session.commit()
        flash("Préstamo actualizado.", "success")
        return redirect(url_for("detalle_prestamo", pid=pid))
    return render_template("editar_prestamo.html", p=p)


@app.route("/prestamos/<int:pid>/eliminar", methods=["POST"])
@admin_required
def eliminar_prestamo(pid):
    p = Prestamo.query.get_or_404(pid)
    nombre = p.nombre
    db.session.delete(p)
    db.session.commit()
    flash(f"Préstamo de {nombre} eliminado.", "success")
    return redirect(url_for("lista_prestamos"))


# ── Reportes ──────────────────────────────────────────────────────────────────

@app.route("/reportes")
@admin_required
def reportes():
    from sqlalchemy import text
    is_sqlite  = "sqlite" in DATABASE_URL
    fmt_mes    = "strftime('%Y-%m', fecha)" if is_sqlite else "to_char(fecha, 'YYYY-MM')"
    per_page = request.args.get("per_page", 10, type=int)
    if per_page not in (10, 20, 50):
        per_page = 10
    page_mes = request.args.get("page_mes", 1, type=int)
    page_per = request.args.get("page_per", 1, type=int)
    q_per    = request.args.get("q_per", "").strip()

    with db.engine.connect() as conn:
        # ── Por mes ──────────────────────────────────────────────────────────
        total_mes = conn.execute(text(f"""
            SELECT COUNT(*) FROM (
                SELECT {fmt_mes} AS mes FROM prestamos GROUP BY mes
            ) t
        """)).scalar() or 0

        por_mes = conn.execute(text(f"""
            SELECT {fmt_mes} AS mes,
                   COUNT(*) AS cantidad,
                   SUM(capital) AS capital,
                   SUM(total_pagar) AS total
            FROM prestamos
            GROUP BY mes ORDER BY mes DESC
            LIMIT :lim OFFSET :off
        """), {"lim": per_page, "off": (page_mes - 1) * per_page}).mappings().all()

        # ── Por prestatario ───────────────────────────────────────────────────
        where_per = "WHERE p.nombre ILIKE :q_per" if q_per and not is_sqlite else \
                    "WHERE p.nombre LIKE :q_per" if q_per else ""
        q_per_val = f"%{q_per}%" if q_per else None

        total_per = conn.execute(text(f"""
            SELECT COUNT(*) FROM (
                SELECT DISTINCT nombre FROM prestamos
                {'WHERE nombre ILIKE :q_per' if q_per and not is_sqlite
                 else 'WHERE nombre LIKE :q_per' if q_per else ''}
            ) t
        """), {"q_per": q_per_val} if q_per else {}).scalar() or 0

        por_persona = conn.execute(text(f"""
            SELECT p.nombre,
                   COUNT(*) AS veces,
                   SUM(p.capital) AS capital_total,
                   SUM(p.total_pagar) AS total_pagar,
                   COALESCE(SUM(a.abonado), 0) AS abonado,
                   SUM(p.total_pagar) - COALESCE(SUM(a.abonado), 0) AS pendiente
            FROM prestamos p
            LEFT JOIN (
                SELECT prestamo_id, SUM(monto) AS abonado
                FROM abonos GROUP BY prestamo_id
            ) a ON a.prestamo_id = p.id
            {where_per}
            GROUP BY p.nombre
            ORDER BY pendiente DESC, capital_total DESC
            LIMIT :lim OFFSET :off
        """), {"lim": per_page, "off": (page_per - 1) * per_page,
               **( {"q_per": q_per_val} if q_per else {}) }).mappings().all()

    total_capital = db.session.query(db.func.sum(Prestamo.capital)).scalar() or 0
    total_interes = db.session.query(db.func.sum(Prestamo.interes)).scalar() or 0
    total_emitido = db.session.query(db.func.sum(Prestamo.total_pagar)).scalar() or 0
    total_cobrado = db.session.query(db.func.sum(Abono.monto)).scalar() or 0
    total_n       = Prestamo.query.count()

    import math
    return render_template("reportes.html",
        por_mes=por_mes,        total_mes=total_mes,
        page_mes=page_mes,      pages_mes=math.ceil(total_mes / per_page),
        por_persona=por_persona, total_per=total_per,
        page_per=page_per,      pages_per=math.ceil(total_per / per_page),
        per_page=per_page,
        total_capital=total_capital, total_interes=total_interes,
        total_emitido=total_emitido, total_cobrado=total_cobrado,
        total_n=total_n, q_per=q_per)


# ── API autocomplete nombres ──────────────────────────────────────────────────

@app.route("/api/nombres")
@login_required
def api_nombres():
    q = request.args.get("q", "").strip()
    rows = (Prestamo.query
            .with_entities(Prestamo.nombre)
            .filter(Prestamo.nombre.ilike(f"%{q}%"))
            .distinct()
            .order_by(Prestamo.nombre)
            .limit(10)
            .all())
    return jsonify([r.nombre for r in rows])


# ── Exportar Excel ───────────────────────────────────────────────────────────

@app.route("/exportar")
@login_required
def exportar_excel():
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    import io

    wb = openpyxl.Workbook()

    header_font  = Font(bold=True, color="FFFFFF")
    header_fill  = PatternFill("solid", fgColor="1a2340")
    center       = Alignment(horizontal="center")

    def estilizar(ws, headers):
        for i, h in enumerate(headers, 1):
            c = ws.cell(row=1, column=i, value=h)
            c.font, c.fill, c.alignment = header_font, header_fill, center
        ws.row_dimensions[1].height = 18

    def autoajustar(ws):
        for col in ws.columns:
            max_len = max((len(str(c.value)) for c in col if c.value), default=8)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 40)

    def cop(n):
        try: return f"${int(n):,}".replace(",", ".")
        except: return n

    prestamos = (Prestamo.query
                 .filter_by(estado="En curso")
                 .options(subqueryload(Prestamo.abonos))
                 .order_by(Prestamo.fecha.desc(), Prestamo.id.desc()).all())

    # ── Hoja 1: Deudores activos ─────────────────────────────────────────────
    ws1 = wb.active
    ws1.title = "Deudores activos"
    headers1 = ["#", "Nombre", "Fecha", "Capital", "Interés %", "Total a pagar",
                "Abonado", "Saldo", "Fecha vence"]
    estilizar(ws1, headers1)
    for p in prestamos:
        ws1.append([
            p.id, p.nombre,
            p.fecha.strftime("%d/%m/%Y"),
            cop(p.capital), p.interes_pct,
            cop(p.total_pagar), cop(p.total_abonado),
            cop(p.saldo),
            p.fecha_vence.strftime("%d/%m/%Y") if p.fecha_vence else "",
        ])
    autoajustar(ws1)

    # ── Hoja 2: Abonos ───────────────────────────────────────────────────────
    ws2 = wb.create_sheet("Abonos")
    headers2 = ["# Préstamo", "Nombre", "Fecha abono", "Monto", "Notas"]
    estilizar(ws2, headers2)
    abonos = (Abono.query
              .join(Prestamo)
              .order_by(Abono.fecha.desc()).all())
    for a in abonos:
        ws2.append([
            a.prestamo_id, a.prestamo.nombre,
            a.fecha.strftime("%d/%m/%Y"),
            cop(a.monto), a.notas or ""
        ])
    autoajustar(ws2)

    # ── Hoja 3: Por prestatario ──────────────────────────────────────────────
    ws3 = wb.create_sheet("Por prestatario")
    headers3 = ["Nombre", "Veces", "Capital total", "Total a pagar", "Cobrado", "Pendiente"]
    estilizar(ws3, headers3)
    from sqlalchemy import text
    is_sqlite = "sqlite" in DATABASE_URL
    with db.engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT p.nombre,
                   COUNT(*) AS veces,
                   SUM(p.capital) AS capital_total,
                   SUM(p.total_pagar) AS total_pagar,
                   COALESCE(SUM(a.abonado),0) AS abonado,
                   SUM(p.total_pagar) - COALESCE(SUM(a.abonado),0) AS pendiente
            FROM prestamos p
            LEFT JOIN (
                SELECT prestamo_id, SUM(monto) AS abonado
                FROM abonos GROUP BY prestamo_id
            ) a ON a.prestamo_id = p.id
            GROUP BY p.nombre ORDER BY pendiente DESC
        """)).mappings().all()
    for r in rows:
        ws3.append([r.nombre, r.veces, cop(r.capital_total),
                    cop(r.total_pagar), cop(r.abonado), cop(r.pendiente)])
    autoajustar(ws3)

    # ── Hoja 4: Por mes ──────────────────────────────────────────────────────
    ws4 = wb.create_sheet("Por mes")
    headers4 = ["Mes", "Préstamos", "Capital", "Total"]
    estilizar(ws4, headers4)
    fmt_mes = "strftime('%Y-%m', fecha)" if is_sqlite else "to_char(fecha, 'YYYY-MM')"
    with db.engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT {fmt_mes} AS mes, COUNT(*) AS cantidad,
                   SUM(capital) AS capital, SUM(total_pagar) AS total
            FROM prestamos GROUP BY mes ORDER BY mes DESC
        """)).mappings().all()
    for r in rows:
        ws4.append([r.mes, r.cantidad, cop(r.capital), cop(r.total)])
    autoajustar(ws4)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    nombre_archivo = f"Kuenta_{date.today().strftime('%Y%m%d')}.xlsx"
    return send_file(buf, as_attachment=True,
                     download_name=nombre_archivo,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ── Gestión de usuarios (solo admin) ─────────────────────────────────────────

@app.route("/usuarios")
@admin_required
def lista_usuarios():
    usuarios = Usuario.query.order_by(Usuario.username).all()
    return render_template("usuarios.html", usuarios=usuarios)


@app.route("/usuarios/nuevo", methods=["GET", "POST"])
@admin_required
def nuevo_usuario():
    if request.method == "POST":
        username = request.form["username"].strip()
        if Usuario.query.filter_by(username=username).first():
            flash("Ese nombre de usuario ya existe.", "warning")
            return redirect(url_for("nuevo_usuario"))
        u = Usuario(
            username = username,
            nombre   = request.form["nombre"].strip(),
            rol      = request.form.get("rol", "viewer"),
        )
        u.set_password(request.form["password"])
        db.session.add(u)
        db.session.commit()
        flash(f"Usuario '{u.username}' creado.", "success")
        return redirect(url_for("lista_usuarios"))
    return render_template("nuevo_usuario.html")


@app.route("/usuarios/<int:uid>/toggle", methods=["POST"])
@admin_required
def toggle_usuario(uid):
    u = db.session.get(Usuario, uid)
    if u and u.id != current_user.id:
        u.activo = not u.activo
        db.session.commit()
        flash(f"Usuario '{u.username}' {'activado' if u.activo else 'desactivado'}.", "success")
    return redirect(url_for("lista_usuarios"))


@app.route("/usuarios/<int:uid>/reset", methods=["POST"])
@admin_required
def reset_password(uid):
    u = db.session.get(Usuario, uid)
    nueva = request.form.get("password", "").strip()
    if u and nueva:
        u.set_password(nueva)
        db.session.commit()
        flash(f"Contraseña de '{u.username}' actualizada.", "success")
    return redirect(url_for("lista_usuarios"))


# ── Ajustes (solo admin) ─────────────────────────────────────────────────────

@app.route("/ajustes", methods=["GET", "POST"])
@admin_required
def ajustes():
    if request.method == "POST":
        raw = request.form.get("capital_inicial", "0").replace(".", "").replace(",", "").strip()
        set_config("capital_inicial", int(raw) if raw.isdigit() else 0)
        flash("Ajustes guardados.", "success")
        return redirect(url_for("ajustes"))
    capital_inicial = int(get_config("capital_inicial", "0"))
    return render_template("ajustes.html", capital_inicial=capital_inicial)


# ── Perfil ────────────────────────────────────────────────────────────────────

@app.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    if request.method == "POST":
        accion = request.form.get("accion")

        if accion == "nombre":
            current_user.nombre = request.form["nombre"].strip()
            db.session.commit()
            flash("Nombre actualizado.", "success")

        elif accion == "password":
            actual = request.form["password_actual"]
            nueva  = request.form["password_nueva"]
            confirmar = request.form["password_confirmar"]
            if not current_user.check_password(actual):
                flash("La contraseña actual es incorrecta.", "danger")
            elif nueva != confirmar:
                flash("Las contraseñas nuevas no coinciden.", "warning")
            elif len(nueva) < 6:
                flash("La contraseña debe tener mínimo 6 caracteres.", "warning")
            else:
                current_user.set_password(nueva)
                db.session.commit()
                flash("Contraseña actualizada correctamente.", "success")

        return redirect(url_for("perfil"))

    return render_template("perfil.html")


# ── Init ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5050)
