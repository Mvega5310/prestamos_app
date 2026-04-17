# Kuenta — App de Control de Préstamos

Aplicación web para gestionar préstamos informales: registro de deudores, abonos, alertas de vencimiento y reportes. Desplegada en Railway con PostgreSQL. Diseño responsive con experiencia mobile-first (card list UI).

---

## Funcionalidades

### Para el administrador
- **Nuevo préstamo** — nombre del deudor, capital, % interés, fecha de vencimiento y notas
- **Registrar abonos** — valida que no supere el saldo pendiente y marca el préstamo como *Pagado* automáticamente
- **Editar préstamo** — nombre, fecha de vencimiento y notas
- **Alertas de cobro** — en el inicio aparecen los préstamos que vencen hoy, mañana o pasado, o ya vencidos
- **Gestionar usuarios** — crear usuarios con rol admin o solo lectura, activar/desactivar y resetear contraseñas
- **Capital inicial configurable** — ingresa el monto propio invertido para ver la ganancia neta en el dashboard
- **Búsqueda en tiempo real** — filtra deudores y prestatarios por nombre mientras escribes (debounce 350ms)
- **Selector de filas** — elige ver 10, 20 o 50 registros por página en todas las listas

### Para el viewer (solo lectura)
- Ver deudores **activos** y sus saldos (sin acceso a pagados ni todos)
- Ver detalle de cada préstamo y su historial de abonos
- Ver solo el stat de **Pendiente por cobrar** en el dashboard
- Sin acceso a Reportes ni datos de capital

### Vistas compartidas
- **Inicio** — stats de resumen, alertas de cobro y tabla de activos
- **Deudores** — lista paginada con búsqueda y filtros (admin: activos/pagados/todos · viewer: solo activos)
- **Detalle préstamo** — historial de abonos, saldo, fechas
- **Mi perfil** — cambiar nombre para mostrar y contraseña

### Solo admin
- **Reportes** — tablas por mes y por prestatario con búsqueda y paginación
- **Ajustes** — configurar capital inicial para cálculo de ganancia neta
- **Usuarios** — gestión completa de accesos

---

## Roles y permisos

| Acción | Admin | Viewer |
|---|---|---|
| Ver deudores activos | ✅ | ✅ |
| Ver deudores pagados / todos | ✅ | ❌ |
| Ver detalle de préstamo | ✅ | ✅ |
| Crear préstamo | ✅ | ❌ |
| Registrar abono | ✅ | ❌ |
| Editar préstamo | ✅ | ❌ |
| Ver Reportes | ✅ | ❌ |
| Ver stats de capital | ✅ | ❌ |
| Gestionar usuarios | ✅ | ❌ |
| Ajustes (capital inicial) | ✅ | ❌ |

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
| `password_hash` | String | Contraseña hasheada (Werkzeug pbkdf2:sha256) |
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

### `Configuracion`
| Campo | Tipo | Descripción |
|---|---|---|
| `clave` | String (PK) | Identificador del parámetro |
| `valor` | String | Valor almacenado |

Parámetros actuales: `capital_inicial` (monto propio invertido para calcular ganancia neta).

---

## Rutas principales

| Ruta | Método | Acceso | Descripción |
|---|---|---|---|
| `/` | GET | Todos | Dashboard / inicio |
| `/login` | GET, POST | Público | Inicio de sesión |
| `/logout` | GET | Todos | Cerrar sesión |
| `/setup` | GET, POST | Público | Crear primer admin (solo si no hay usuarios) |
| `/prestamos` | GET | Todos | Lista paginada con búsqueda y filtros |
| `/prestamos/nuevo` | GET, POST | Admin | Crear préstamo |
| `/prestamos/<id>` | GET | Todos | Detalle del préstamo |
| `/prestamos/<id>/abono` | POST | Admin | Registrar abono |
| `/prestamos/<id>/editar` | GET, POST | Admin | Editar préstamo |
| `/reportes` | GET | Admin | Reportes por mes y por prestatario |
| `/ajustes` | GET, POST | Admin | Configurar capital inicial |
| `/usuarios` | GET | Admin | Gestión de usuarios |
| `/usuarios/nuevo` | GET, POST | Admin | Crear usuario |
| `/usuarios/<id>/toggle` | POST | Admin | Activar/desactivar usuario |
| `/usuarios/<id>/reset` | POST | Admin | Resetear contraseña |
| `/perfil` | GET, POST | Todos | Cambiar nombre y contraseña |
| `/api/nombres` | GET | Todos | Autocomplete de nombres |

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
python3 app.py
# → http://localhost:5050
```

Al abrir por primera vez la app redirige a `/setup` para crear el usuario administrador.

> **Nota:** En Python 3.9 (macOS) el hash de contraseñas usa `pbkdf2:sha256` en lugar de `scrypt` por compatibilidad con la versión de OpenSSL del sistema.

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

## Diseño mobile

La app usa **card list UI** en dispositivos móviles (< 768px) en lugar de tablas:

- Cada deudor/préstamo se muestra como tarjeta tocable con borde de color según urgencia
- Alertas con fondo coloreado (rojo/naranja/amarillo) según estado de vencimiento
- Bottom navigation bar con acceso rápido a Inicio, Deudores, Nuevo préstamo (admin), Reportes y Perfil
- En desktop (≥ 768px) se mantienen las tablas originales

---

## PWA — Agregar a pantalla de inicio

La app está configurada como Progressive Web App. En el navegador móvil seleccionar *"Agregar a pantalla de inicio"* y aparecerá con el nombre **Kuenta**, el logo de la app y favicon en la pestaña del navegador.

---

## Rama futura

`feature/multi-tenant` — soporte para múltiples organizaciones independientes con sus propios datos, usuarios y configuración. Pendiente de desarrollo.
