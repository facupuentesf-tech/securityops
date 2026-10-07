# securityops

Plataforma de gestión de seguridad para pequeñas y medianas empresas.

## Objetivo

Centralizar la gestión de activos, usuarios, riesgos,
controles de seguridad e incidentes en una única plataforma.

## Primera versión funcional

Aplicación local para registrar e investigar incidentes de seguridad, con
inicio de sesión y permisos verificados por la API. El servidor escucha
únicamente en `127.0.0.1`; esta versión no incluye publicación ni despliegue
para uso compartido. Solo contempla una organización.

### Funciones implementadas

- Crear, listar y consultar incidentes.
- Filtrar por estado y severidad, individualmente o combinados.
- Cambiar el estado y consultar su historial persistente.
- Agregar y consultar notas de investigación.
- Inicio y cierre de sesión con contraseñas derivadas mediante scrypt y cookies
  de sesión `HttpOnly`, `SameSite=Strict`, con expiración y protección CSRF.
- Administración de cuentas por administradores: crear usuarios, cambiar
  nombre/correo/rol, desactivar cuentas y restablecer contraseñas.
- Tres roles comprobados en cada operación del backend: administrador,
  analista y lector.
- Historial de estados y notas nuevos atribuidos al usuario que los generó.
- Interfaz en español adaptable a computadora y celular, con fechas locales
  y mensajes de carga, listas vacías, éxito y errores.
- Persistencia en SQLite, migraciones SQL versionadas, validación y API en `/docs`.
- Pruebas con base temporal y comprobación opcional de la interfaz en Chrome.

### Permisos por rol

| Operación | Administrador | Analista | Lector |
| --- | --- | --- | --- |
| Consultar incidentes, historial y notas | Sí | Sí | Sí |
| Crear incidentes, cambiar estado y agregar notas | Sí | Sí | No |
| Gestionar usuarios (crear, editar, desactivar y restablecer contraseña) | Sí | No | No |

Los cambios existentes anteriores a las migraciones mantienen su contenido,
pero no se les asigna un usuario retroactivamente. Las sesiones se guardan
del lado del servidor y se invalidan al desactivar la cuenta o restablecer
su contraseña.

### Objetivos y mejoras futuras

Aún no están implementados:

- Soporte para varias organizaciones y aislamiento de datos por organización
- Inventario de activos
- Gestión de riesgos
- Controles de seguridad
- Ampliación de incidentes con responsables y activos relacionados
- Auditoría general más allá del historial de incidentes
- Reportes
- Dashboard

## Tecnologías

La versión actual usa Python con FastAPI, Uvicorn y SQLite mediante `sqlite3`
de la biblioteca estándar. FastAPI sirve la interfaz HTML/CSS/JavaScript
desde `GET /` y sus archivos desde `/static`. No requiere npm para ejecutarse.
React, PostgreSQL y Docker pertenecen al stack considerado para etapas futuras.

## Ejecutar el backend en Windows PowerShell

Requisitos: Python (esta versión se comprobó con Python 3.13), PowerShell y
un navegador moderno. Node.js y Chrome solo se necesitan para la comprobación
opcional de la interfaz. PostgreSQL no es necesario.

Desde la raíz del repositorio, crear el entorno virtual e instalar las dependencias:

```powershell
python -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Si el entorno ya existe, omitir el comando que lo crea.

El entorno virtual mantiene las dependencias aisladas del resto del equipo.
Los comandos usan su ejecutable directamente, por lo que no hace falta activar
el entorno ni cambiar la política de ejecución de PowerShell.

Antes de iniciar la aplicación por primera vez, crear el primer administrador.
El comando solicita correo, nombre y una contraseña nueva dos veces; no hay
credenciales predeterminadas ni endpoint de registro público:

```powershell
.\backend\.venv\Scripts\python.exe backend\main.py create-admin
```

El comando aplica las migraciones pendientes sin borrar los registros existentes.
Solo puede crear este administrador inicial cuando la base no contiene usuarios.
Para usar otra ubicación de base SQLite, definir `SECURITYOPS_DATABASE` antes
de ejecutar tanto este comando como Uvicorn, por ejemplo:

```powershell
$env:SECURITYOPS_DATABASE = Join-Path $PWD "backend\securityops.db"
```

Iniciar el servidor de desarrollo:

```powershell
.\backend\.venv\Scripts\python.exe -m uvicorn main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

En otra terminal de PowerShell, comprobar la respuesta:

```powershell
(Invoke-WebRequest -Uri http://127.0.0.1:8000/health -UseBasicParsing).Content
```

Respuesta esperada: `{"status":"ok"}`. También se puede abrir esa dirección
en el navegador. Este endpoint permite comprobar que la API está funcionando.

Para detener el servidor, presionar **Ctrl+C** en la terminal donde se ejecuta.
Para volver a iniciarlo, repetir únicamente el comando de Uvicorn.

## Abrir la interfaz web

Con el servidor iniciado mediante el comando anterior, abrir
http://127.0.0.1:8000/ en el navegador. La interfaz está en español y se adapta
a computadora y celular; todas las llamadas a la API usan rutas relativas.

- El listado muestra título, severidad, estado y fecha. **Aplicar filtros**
  permite combinar estado y severidad; **Limpiar** vuelve al listado completo.
- **Nuevo incidente** abre el formulario. Al crearlo se muestra su detalle.
- Pulsar el título de un incidente abre su descripción, el formulario para
  guardar estado, el historial de estados y las notas de investigación.
- **Agregar nota** guarda el contenido y actualiza el listado de notas.
- **Volver a incidentes** actualiza el listado con los filtros elegidos.
- Los administradores también pueden crear, editar, desactivar y restablecer
  las contraseñas de usuarios desde el panel **Usuarios**.

Las fechas se muestran en la zona horaria del navegador. La interfaz informa
carga, listas vacías, operaciones exitosas y errores, y conserva el texto del
formulario cuando una operación falla. Los textos de usuarios se insertan con
`textContent`, sin interpretarlos como HTML. No requiere servicios externos
ni un proceso adicional de compilación. El alcance sigue
siendo local, con el servidor escuchando en `127.0.0.1`. `/docs` documenta la
API; las operaciones protegidas requieren una sesión y las solicitudes que
modifican datos también requieren el token CSRF de esa sesión.

## Endpoints disponibles

| Método | Ruta | Función |
| --- | --- | --- |
| GET | `/` | Interfaz web |
| GET | `/health` | Respuesta `{"status":"ok"}` |
| POST | `/auth/login` | Iniciar sesión |
| GET | `/auth/session` | Consultar la sesión actual |
| POST | `/auth/logout` | Cerrar sesión |
| GET | `/users` | Listar usuarios (administrador) |
| POST | `/users` | Crear usuario (administrador) |
| PATCH | `/users/{user_id}` | Editar usuario o desactivar cuenta (administrador) |
| POST | `/users/{user_id}/password` | Restablecer contraseña (administrador) |
| POST | `/incidents` | Crear incidente (`201`) |
| GET | `/incidents` | Listar con filtros opcionales `status` y `severity` |
| GET | `/incidents/{incident_id}` | Consultar incidente |
| PATCH | `/incidents/{incident_id}/status` | Cambiar estado |
| GET | `/incidents/{incident_id}/history` | Consultar historial de estados |
| POST | `/incidents/{incident_id}/notes` | Crear nota (`201`) |
| GET | `/incidents/{incident_id}/notes` | Consultar notas |

`/docs` permite consultar los esquemas de la API. Las consultas a un incidente
inexistente devuelven `404`; entradas inválidas devuelven `422` antes de ejecutar
la operación. Las rutas de incidentes y usuarios (excepto `/health`) exigen
autenticación; modificar datos exige el encabezado `X-CSRF-Token`. No hay
endpoints para borrar incidentes ni editar o borrar notas.

## Uso autenticado de la API

`/docs` muestra los esquemas y las respuestas. Para usar las operaciones desde
la interfaz, iniciá sesión en la página principal. Un cliente HTTP debe primero
enviar `POST /auth/login` con `email` y `password`, conservar la cookie de sesión
recibida y usar el `csrf_token` de la respuesta como `X-CSRF-Token` en cada
solicitud que cree o modifique datos. Las lecturas solo requieren la cookie.

Los datos de acceso no tienen valores predeterminados; el primer administrador
se crea mediante el comando local descrito arriba. Severidades de incidentes:
`low`, `medium`, `high`, `critical`. Estados: `open`, `investigating`, `resolved`.

## Historial de cambios de estado

Cada cambio efectivo realizado con `PATCH /incidents/{incident_id}/status`
se registra en la tabla SQLite `incident_status_history`, con `id`,
`incident_id`, `previous_status`, `new_status`, `changed_at` en UTC y el usuario
que lo realizó. Los registros previos a la migración conservan su contenido y
tienen usuario atribuido nulo.
La actualización y la entrada de historial se confirman en la misma transacción:
si falla el registro del historial, se revierte el cambio de estado.
Las actualizaciones concurrentes se serializan para registrar el estado anterior correcto.
Enviar el estado actual devuelve el incidente sin agregar una entrada.

Para consultar el historial en `/docs`, expandir
`GET /incidents/{incident_id}/history`, pulsar **Try it out**, ingresar el ID
del incidente que se acaba de actualizar y pulsar **Execute**. Por ejemplo:

```text
GET /incidents/1/history
```

La respuesta `200` es una lista de cambios ordenados por ID, del más antiguo
al más reciente. Cada entrada tiene esta forma (valores ilustrativos):

```json
{
  "id": 1,
  "incident_id": 1,
  "previous_status": "open",
  "new_status": "investigating",
  "changed_at": "2026-10-01T18:00:00Z",
  "changed_by": 1,
  "changed_by_name": "Nombre del usuario"
}
```

Un incidente sin cambios devuelve `[]`; un ID inexistente devuelve `404`.
La migración agrega la referencia al usuario sin borrar ni modificar
los incidentes existentes. El historial no reconstruye cambios pasados ni
registra la creación.

La base predeterminada se crea en `backend/securityops.db`, relativa al módulo
del backend e independientemente del directorio desde donde se ejecute. Está
excluida de Git; `SECURITYOPS_DATABASE` permite elegir otra ruta.
Detener y volver a iniciar Uvicorn, y repetir `GET /incidents`, permite comprobar
que los registros se conservan.

## Notas de investigación

Las notas se guardan en `incident_notes`; la migración conserva las existentes.
Cada nota incluye `id`, `incident_id`, `content`, `created_at` en UTC y, para
notas nuevas, el usuario que la creó.

Desde la interfaz autenticada, abrir el detalle del incidente y completar
**Nueva nota**. Los clientes API pueden enviar
`POST /incidents/{incident_id}/notes` con:

```json
{
  "content": "  Se revisaron los registros de acceso y se identificó la IP de origen.  "
}
```

La respuesta `201` devuelve la nota creada con el contenido sin espacios
al inicio y al final. El contenido debe tener entre
1 y 5000 caracteres después de quitar esos espacios. Contenido vacío, solo
espacios, más de 5000 caracteres, `null`, valores que no sean texto, un JSON
sin `content` o una solicitud sin cuerpo devuelven `422`.

`GET /incidents/{incident_id}/notes` lista las notas. Cada nota nueva incluye
el usuario que la registró; las notas existentes antes de la migración no se
atribuyen retroactivamente. Ejemplo:

```text
GET /incidents/1/notes
```

La respuesta `200` devuelve las notas del más antiguo al más reciente según
`created_at`, usando `id` ascendente para desempatar. Un incidente sin notas
devuelve `[]`. Ambos endpoints devuelven `404` si el incidente no existe
(en el POST, con un cuerpo válido). Las notas se conservan al reiniciar la API
y agregarlas no modifica el incidente ni su historial de estados.

## Migraciones y alcance organizacional

Las migraciones numeradas viven en `backend/migrations` y se aplican en orden
al iniciar la API o al ejecutar `create-admin`. La primera versión crea el
esquema de incidentes solo si aún no existe; la siguiente agrega usuarios,
sesiones y atribución opcional a historial/notas. No elimina ni reconstruye las
tablas con información existente. Antes de actualizar, se recomienda detener
la API y hacer una copia de la base activa antes de actualizar.

Esta etapa trabaja con una sola organización local y no incorpora una entidad
de organización ni filtros de acceso multi-organización. El soporte multi-tenant
y el aislamiento entre organizaciones quedan pendientes; no se debe exponer esta
versión como servicio compartido.

## Pruebas automatizadas

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

Las pruebas usan una base temporal, crean un administrador de prueba y usan
sesiones de cookie. Cubren salud, creación, listado con filtros individuales y
combinados, ausencia de coincidencias,
consulta, actualización exclusiva del estado, validaciones,
ID inexistente, SQL parametrizado y persistencia de los incidentes y de los
cambios de estado después de reiniciar el proceso del servidor. También cubren
historial, ausencia de entradas duplicadas, aislamiento entre incidentes,
persistencia del historial, actualización de una base de datos heredada mediante
migraciones versionadas y preservación de incidentes, historial y notas existentes, reversión del estado
cuando falla la escritura del historial, rechazo de usuarios anónimos,
protección CSRF, permisos de los tres roles, administración de usuarios,
restablecimiento de contraseñas y protección del último administrador activo.
Para notas cubren creación, recorte del contenido, límites de longitud, validaciones, listado,
orden cronológico y desempate por ID, `404`, persistencia tras reiniciar y
creación de la tabla conservando incidentes e historial existentes.
También se comprueba que `/`, los archivos CSS/JavaScript y `/docs` se sirvan
correctamente.

Comprobación opcional de la interfaz, usando Node.js 24 y Chrome instalado,
con una base temporal (sin dependencias npm). Busca Chrome en `PATH` y en las
ubicaciones habituales; si está instalado en otra ubicación, se puede indicar
su ejecutable en la variable `SECURITYOPS_CHROME`. La prueba inicia sesión y
arranca/detiene su propio servidor; no requiere iniciar Uvicorn por separado:

```powershell
.\backend\.venv\Scripts\python.exe backend\tests\check_browser.py
```

Se verificaron en Chrome sin ventana el inicio de sesión, la creación de
usuarios, el acceso de solo lectura y la ocultación de controles de escritura
para lectores, además de la creación y consulta de incidentes,
cambio de estado e historial, validación y creación de notas, filtros combinados,
listas vacías, recuperación de errores de red, fechas en la zona del navegador,
renderizado seguro de textos con etiquetas HTML y ausencia de desbordamiento
horizontal a 1280 y 390 píxeles. Esta comprobación requiere que el entorno
permita iniciar Chrome y conectarse a su puerto local de depuración; no sustituye
una revisión manual en un celular físico.

## Documentación del proyecto

- [Definición y objetivos](docs/project-definition.md)
- [Requisitos implementados y futuros](docs/requirements.md)
- [Arquitectura actual](docs/architecture.md)
- [Diseño de base de datos](docs/database-design.md)
- [Modelo del sistema](docs/system-model.md)

## Estado

Versión funcional local con autenticación y permisos para una organización.
El soporte multi-organización y los demás módulos del proyecto continúan
pendientes.
