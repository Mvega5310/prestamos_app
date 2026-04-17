# Kuenta — App de Control de Préstamos

Aplicación web para gestionar préstamos informales: registro de deudores, abonos, alertas de vencimiento y reportes. Desplegada en Railway con PostgreSQL.

---

## Funcionalidades

### Para el administrador
- **Nuevo préstamo** — nombre del deudor, capital, % interés, fecha de vencimiento y notas
- **Registrar abonos** — el sistema valida que no supere el saldo pendiente y marca el préstamo como *Pagado* automáticamente
- **Editar préstamo** — nombre, fecha de vencimiento y notas
- **Alertas de cobro** — en el inicio aparecen los préstamos que vencen hoy, mañana o pasado, o que ya están vencidos
- **Gestionar usuarios** — crear usuarios con rol admin o solo lectura, activar/desactivar y resetear contraseñas

### Para el viewer (solo lectura)
- Consultar deudores activos y sus saldos
- Ver detalle de cada préstamo y su historial de abonos
- Ver reportes de cobrado y pendiente (sin datos de capital)

### Vistas compartidas
- **Inicio** — resumen del estado actual, alertas y tabla de activos
- **Deudores** — lista paginada con filtros: activos / pagados / todos
- **Detalle préstamo** — historial de abonos, saldo, fechas
- **Reportes** — tabla por mes y por prestatario, paginadas
- **Mi perfil** — cambiar nombre para mostrar y contraseña

---

## Tecnología

| Capa | Herramienta |
|---|---|
| Backend | Python 3 + Flask |
| ORM | Flask-SQLAlchemy |
| Autenticación | Flask-Login |
| Base de datos | SQLite (local) / PostgreSQL (producción) |
| Frontend | Bootstrap 5 + Bootstrap Icons |
| Servidor WSGI | Gunicorn |
| Despliegue | Railway |
| PWA | manifest.json + meta tags Apple/Android |

---

## Modelos de datos

### `Usuario`
| Campo | Tipo | Descripción |
|---|---|---|
| `username` | String | Nombre de usuario único |
| `password_hash` | String | Contraseña hasheada (Werkzeug) |
| `nombre` | String | Nombre para mostrar |
| `rol` | String | `admin` o `viewer` |
| `activo` | Boolean | Permite desactivar sin borrar |

### `Prestamo`
| Campo | Tipo | Descripción |
|---|---|---|
| `nombre` | String | Nombre del deudor |
| `fecha` | Date | Fecha de emisión |
| `capital` | Integer | Monto prestado |
| `interes_pct` | Float | Porcentaje de interés (default 20%) |
| `interes` | Integer | Valor calculado del interés |
| `total_pagar` | Integer | Capital + interés |
| `fecha_vence` | Date | Fecha límite de pago |
| `estado` | String | `En curso` o `Pagado` |
| `notas` | Text | Observaciones opcionales |

**Propiedades calculadas:**
- `total_abonado` — suma de todos los abonos
- `saldo` — `total_pagar - total_abonado`
- `dias_vence` — días restantes hasta vencimiento (negativo = vencido)

### `Abono`
| Campo | Tipo | Descripción |
|---|---|---|
| `prestamo_id` | FK | Préstamo al que pertenece |
| `fecha` | Date | Fecha del pago |
| `monto` | Integer | Valor pagado |
| `notas` | Text | Observaciones opcionales |

---

## Roles y permisos

| Acción | Admin | Viewer |
|---|---|---|
| Ver deudores y detalle | ✅ | ✅ |
| Ver reportes | ✅ | ✅ (sin capital) |
| Crear préstamo | ✅ | ❌ |
| Registrar abono | ✅ | ❌ |
| Editar préstamo | ✅ | ❌ |
| Gestionar usuarios | ✅ | ❌ |
| Ver stats de capital | ✅ | ❌ |

---

## Rutas principales

| Ruta | Método | Descripción |
|---|---|---|
| `/` | GET | Dashboard / inicio |
| `/login` | GET, POST | Inicio de sesión |
| `/logout` | GET | Cerrar sesión |
| `/setup` | GET, POST | Crear primer admin (solo si no hay usuarios) |
| `/prestamos` | GET | Lista de préstamos (paginada, con filtros) |
| `/prestamos/nuevo` | GET, POST | Crear préstamo (admin) |
| `/prestamos/<id>` | GET | Detalle del préstamo |
| `/prestamos/<id>/abono` | POST | Registrar abono (admin) |
| `/prestamos/<id>/editar` | GET, POST | Editar préstamo (admin) |
| `/reportes` | GET | Reportes por mes y por prestatario |
| `/usuarios` | GET | Gestión de usuarios (admin) |
| `/usuarios/nuevo` | GET, POST | Crear usuario (admin) |
| `/usuarios/<id>/toggle` | POST | Activar/desactivar usuario (admin) |
| `/usuarios/<id>/reset` | POST | Resetear contraseña (admin) |
| `/perfil` | GET, POST | Perfil del usuario actual |
| `/api/nombres` | GET | Autocomplete de nombres de deudores |

---

## Instalación local

```bash
# 1. Clonar el repositorio
git clone https://github.com/Mvega5310/prestamos_app.git
cd prestamos_app

# 2. Crear entorno virtual
python3 -m venv venv
source venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Ejecutar
python app.py
# → http://localhost:5050
```

Al abrir por primera vez, la app redirige a `/setup` para crear el usuario administrador.

---

## Variables de entorno

| Variable | Descripción | Default |
|---|---|---|
| `DATABASE_URL` | URL de conexión a la base de datos | SQLite local (`prestamos.db`) |
| `SECRET_KEY` | Clave secreta de Flask para sesiones | `dev_local_prestamos_2024` |

> En producción (Railway) estas variables se configuran en el panel de la plataforma. Siempre usar una `SECRET_KEY` segura y aleatoria en producción.

---

## Despliegue en Railway

El proyecto está desplegado en [Railway](https://railway.app) con PostgreSQL como base de datos.

- **Servidor:** Gunicorn — `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
- **Base de datos:** PostgreSQL (Railway Postgres plugin)
- **Deploys automáticos:** cada push a `main` dispara un nuevo deploy

Configuración en [railway.toml](railway.toml).

---

## PWA — Agregar a pantalla de inicio

La app está configurada como Progressive Web App. En el navegador móvil seleccionar *"Agregar a pantalla de inicio"* y aparecerá con el nombre **Kuenta** y el logo de la app.

---

## Rama futura

`feature/multi-tenant` — soporte para múltiples organizaciones independientes con sus propios datos, usuarios y configuración. Pendiente de desarrollo.
