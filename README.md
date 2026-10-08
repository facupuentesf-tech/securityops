# securityops

Plataforma de gestión de seguridad para pequeñas y medianas empresas.

## Objetivo

Centralizar la gestión de activos, usuarios, riesgos,
controles de seguridad e incidentes en una única plataforma.

## Primera versión funcional

Aplicación local para registrar activos e investigar incidentes de seguridad, con
inicio de sesión, permisos verificados por la API y aislamiento de datos entre
organizaciones. El servidor escucha únicamente en `127.0.0.1`; esta versión
sigue siendo un prototipo local, sin publicación ni despliegue para uso
compartido.

### Funciones implementadas

- Resumen inicial por organización para todos los roles, con totales, distribuciones y prioridades.
- Crear, listar y consultar incidentes.
- Auditoría local de cambios de negocio y usuarios, con consulta paginada solo para administradores.
- Asignar responsables opcionales a incidentes y riesgos, con filtros por responsable.
- Crear, listar y consultar riesgos, con evaluación inicial y activo opcional.
- Crear, listar y consultar controles de seguridad y vincularlos con riesgos.
- Vincular varios activos por incidente y quitar vínculos sin borrar recursos.
- Crear, listar y consultar activos, con filtros por tipo y criticidad combinados con AND.
- Editar activos, riesgos y controles como administrador o analista, con auditoría atómica.
- Filtrar por estado y severidad, individualmente o combinados.
- Cambiar el estado y consultar su historial persistente.
- Agregar y consultar notas de investigación.
- Inicio y cierre de sesión con contraseñas derivadas mediante scrypt y cookies
  de sesión `HttpOnly`, `SameSite=Strict`, con expiración y protección CSRF.
- Administración de cuentas por administradores: crear usuarios, cambiar
  nombre/correo/rol, desactivar cuentas y restablecer contraseñas.
- Tres roles comprobados en cada operación del backend: administrador,
  analista y lector.
- Organizaciones locales con usuarios, incidentes y activos aislados por organización;
  el servidor obtiene la organización desde la sesión autenticada.
- Historial de estados y notas nuevos atribuidos al usuario que los generó.
- Interfaz en español adaptable a computadora y celular, con fechas locales
  y mensajes de carga, listas vacías, éxito y errores.
- Persistencia en SQLite, migraciones SQL versionadas, validación y API en `/docs`.
- Pruebas con base temporal y comprobación opcional de la interfaz en Chrome.

### Permisos por rol

| Operación | Administrador | Analista | Lector |
| --- | --- | --- | --- |
| Consultar el resumen de la organización | Sí | Sí | Sí |
| Consultar incidentes, historial y notas | Sí | Sí | Sí |
| Crear incidentes, cambiar estado y agregar notas | Sí | Sí | No |
| Consultar activos | Sí | Sí | Sí |
| Crear activos | Sí | Sí | No |
| Editar activos | Sí | Sí | No |
| Consultar riesgos | Sí | Sí | Sí |
| Crear riesgos | Sí | Sí | No |
| Editar riesgos | Sí | Sí | No |
| Consultar responsables y candidatos elegibles | Sí | Sí | Sí |
| Asignar, reasignar y quitar responsables | Sí | No | No |
| Consultar controles y vínculos con riesgos | Sí | Sí | Sí |
| Crear controles, vincular y desvincular | Sí | Sí | No |
| Editar controles | Sí | Sí | No |
| Vincular y desvincular activos de incidentes | Sí | Sí | No |
| Gestionar usuarios (crear, editar, desactivar y restablecer contraseña) | Sí | No | No |
| Consultar auditoría de la organización | Sí | No | No |

Los cambios existentes anteriores a las migraciones mantienen su contenido,
pero no se les asigna un usuario retroactivamente. Las sesiones se guardan
del lado del servidor y se invalidan al desactivar la cuenta o restablecer
su contraseña.

### Objetivos y mejoras futuras

Aún no están implementados:

- Eliminación y asignación de responsables de activos
- Eliminación de riesgos y evaluación residual
- Eliminación de controles de seguridad, evaluación de eficacia
- Eventos de auditoría de autenticación (login, logout, rechazos y expiración)
- Reportes
- Extensiones del dashboard y métricas adicionales

## Activos: creación y consulta

La sección **Activos** permite listar recursos, filtrar por tipo y criticidad,
registrarlos y abrir el detalle pulsando su nombre. Administradores y analistas
pueden crear; lectores solo consultan. Incidentes y usuarios siguen disponibles.

| Método | Ruta | Comportamiento |
| --- | --- | --- |
| POST | `/assets` | Crea un activo, devuelve `201`; requiere sesión y CSRF |
| GET | `/assets` | Lista por ID; filtros opcionales `type` y `criticality` con AND |
| GET | `/assets/{asset_id}` | Detalle; `404` para IDs inexistentes o de otra organización |

Ejemplo de cuerpo de creación:

```json
{"name":"Servidor principal","type":"hardware","description":"Servidor de aplicaciones","criticality":"high"}
```

El nombre es obligatorio, se recorta y no puede quedar vacío. Tipos admitidos:
`hardware`, `software`, `service`, `data`; criticidad: `low`, `medium`, `high`,
`critical`. La descripción es opcional: omitida o null se almacena como null.
El servidor asigna ID, organización y fecha UTC. Los campos extra, incluido
`organization_id`, y los filtros inválidos devuelven `422`. Sin coincidencias,
el listado devuelve `[]`. La edición parcial está implementada; la eliminación sigue pendiente.

Para comprobarlo manualmente:

1. Iniciar la API con el comando de la sección siguiente e ingresar como
   administrador o analista. Crear un activo con espacios alrededor del nombre
   y sin descripción; abrir el detalle y comprobar nombre recortado y fecha local.
2. Crear otros tipos y criticidades. Aplicar cada filtro y ambos juntos;
   comprobar una combinación sin coincidencias y usar **Limpiar**.
3. Ingresar como lector: consultar listado y detalle; no debe aparecer
   **Nuevo activo**. La API también debe rechazar su creación con `403`.
4. Ingresar con una cuenta de otra organización: no debe ver los activos
   anteriores y consultar sus IDs en la API debe devolver `404`.
5. Reiniciar la API y comprobar que los activos siguen disponibles.

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

Antes de iniciar la aplicación por primera vez, crear la primera organización
y su administrador. El comando solicita correo, nombre y una contraseña nueva
dos veces; no hay credenciales predeterminadas ni endpoint de registro público:

```powershell
.\backend\.venv\Scripts\python.exe backend\main.py create-admin
```

El comando aplica las migraciones pendientes sin borrar los registros existentes.
Solo puede crear este administrador inicial cuando la base no contiene usuarios.
Para crear otra organización y su primer administrador en una base ya inicializada,
usar el siguiente comando local. Solicita el nombre de la organización y los
datos del administrador, incluida una contraseña nueva dos veces:

```powershell
.\backend\.venv\Scripts\python.exe backend\main.py create-organization
```

La asociación de usuarios e incidentes se deriva del usuario autenticado y no
se puede establecer ni modificar desde la API. Los administradores solo ven y
gestionan usuarios de su organización; IDs de otras organizaciones responden
`404`. La base existente se migra a una organización inicial, conservando
usuarios, sesiones vigentes, incidentes, historial y notas.
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
al iniciar la API o al ejecutar cualquiera de los comandos locales. La migración
003 agrega organizaciones y asocia los datos existentes a la organización inicial
sin borrar tablas ni invalidar sesiones vigentes. La migración 004 crea `assets`
e índices por organización sin modificar los datos existentes. Antes de actualizar, detener
la API y hacer una copia de la base activa.

El aislamiento multi-organización se implementa en esta etapa, pero la aplicación
sigue siendo un prototipo local que escucha en `127.0.0.1`; no se debe exponer
como servicio compartido.

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
También cubren migración conservando sesiones y datos existentes, creación local
de otra organización y aislamiento de lecturas, filtros, escrituras e
administración de usuarios entre organizaciones.
Para notas cubren creación, recorte del contenido, límites de longitud, validaciones, listado,
orden cronológico y desempate por ID, `404`, persistencia tras reiniciar y
creación de la tabla conservando incidentes e historial existentes.
También se comprueba que `/`, los archivos CSS/JavaScript y `/docs` se sirvan
correctamente.
Para activos se verifican creación, recorte de nombre, descripción opcional,
fechas UTC, tipos y criticidades, consultas, filtros individuales y combinados,
validaciones, SQL parametrizado, CSRF, roles, aislamiento en ambas direcciones
entre dos organizaciones, preservación de datos al migrar y persistencia tras reiniciar.

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
La comprobación también incluye activos: creación y detalle, nombre vacío,
filtros, listas vacías, recuperación de errores de red, textos seguros, fechas
locales y controles de creación ocultos para lectores.

## Documentación del proyecto

- [Definición y objetivos](docs/project-definition.md)
- [Requisitos implementados y futuros](docs/requirements.md)
- [Arquitectura actual](docs/architecture.md)
- [Diseño de base de datos](docs/database-design.md)
- [Modelo del sistema](docs/system-model.md)

## Estado

Prototipo funcional local con autenticación, permisos y aislamiento entre
organizaciones, con creación, consulta y edición de activos, riesgos y controles. Eliminación de
recursos, auditoría de autenticación,
reportes y métricas adicionales continúan pendientes. El resumen inicial está implementado.

## Activos afectados por incidente

La migración 005 incorpora `incident_assets`: relación muchos a muchos sin modificar
los datos existentes. La clave primaria impide duplicados y las claves foráneas
compuestas exigen que ambos recursos pertenezcan a la misma organización; también
impiden cambiar la organización de un recurso con vínculos. Las migraciones se
aplican automáticamente al iniciar la API.

| Método | Ruta | Resultado |
| --- | --- | --- |
| GET | `/incidents/{incident_id}/assets` | Activos vinculados por ID o `[]` |
| POST | `/incidents/{incident_id}/assets` | Cuerpo `{"asset_id": 1}`, `201`; duplicado `409` |
| DELETE | `/incidents/{incident_id}/assets/{asset_id}` | Quita solo el vínculo, `204`; ausente `404` |

Administrador y analista pueden vincular y quitar vínculos; lector solo consulta.
Se exige sesión y CSRF para escrituras. Recursos inexistentes o de otra organización
responden `404`. El ID del cuerpo debe ser un entero positivo; campos extra se
rechazan con `422`. La interfaz muestra **Activos afectados**, excluye del selector
los ya vinculados y ofrece mensajes de carga, vacío, error y reintento.

Comprobación manual:

1. Crear dos activos y dos incidentes. Vincular varios activos al primer incidente
   y el mismo activo al segundo; comprobar que el selector excluye los vinculados.
2. Recargar y reiniciar el servidor: comprobar vínculos, activos, notas e historial.
3. Quitar un vínculo: el activo y ambos incidentes deben conservarse, al igual que
   el vínculo del otro incidente. En `/docs`, repetir POST debe dar `409` y repetir
   DELETE debe dar `404` (con cookie de sesión y cabecera `X-CSRF-Token`).
4. Ingresar como lector: ver la lista sin controles de escritura. Con una cuenta
   de otra organización, comprobar que los IDs ajenos devuelven `404`.
5. Revisar a ancho móvil, con nombres que contengan HTML y con conexión interrumpida;
   comprobar texto seguro, ausencia de desbordamiento y recuperación con Reintentar.

## Riesgos: evaluación inicial

La sección **Riesgos** permite crear, listar, filtrar y consultar riesgos de la
organización autenticada. Administrador y analista pueden crear; lector solo
consulta. Cada riesgo puede asociarse a un activo de la misma organización o
registrarse sin activo. Eliminación y evaluación residual
quedan para una etapa posterior.

| Método | Ruta | Comportamiento |
| --- | --- | --- |
| POST | `/risks` | Crea y devuelve `201`; requiere sesión, permisos y CSRF |
| GET | `/risks` | Lista por ID; filtros opcionales `status`, `level`, `asset_id` con AND |
| GET | `/risks/{risk_id}` | Detalle; `404` para un riesgo inexistente o ajeno |

```json
{"title":"Pérdida de datos","description":"Falla de respaldo","probability":3,"impact":4,"status":"identified","asset_id":1}
```

Título obligatorio, recortado y no vacío. Descripción y `asset_id` son opcionales
y aceptan null. Probabilidad e impacto son enteros estrictos entre 1 y 5: booleanos,
decimales y cadenas se rechazan con `422`. Estados: `identified` (predeterminado),
`treating`, `accepted`. `asset_id`, cuando se envía, debe ser un entero positivo.
El servidor calcula `score` y `level`; el cliente no puede enviar esos campos ni
`organization_id`. La respuesta incluye ID, fecha UTC, campos del riesgo, puntaje,
nivel y `asset_name` (null si no tiene activo).

**Matriz propia del prototipo:** puntaje = probabilidad × impacto. Estos umbrales
son una convención de SecurityOps, no una clasificación atribuida a un estándar.

| Puntaje | Nivel API | Interfaz |
| --- | --- | --- |
| 1–4 | low | Bajo |
| 5–9 | medium | Medio |
| 10–16 | high | Alto |
| 17–25 | critical | Crítico |

Con factores enteros de 1 a 5, algunos puntajes intermedios (por ejemplo, 17) no
se obtienen por multiplicación; los intervalos definen igualmente el criterio.
Puntaje y nivel se calculan al consultar y no se almacenan como datos independientes.
Sin coincidencias, el listado devuelve `[]`. Si `asset_id` en una creación o filtro
es inexistente o de otra organización, devuelve `404`; un activo propio sin riesgos
devuelve `[]`. Filtros inválidos devuelven `422`. Lectores no pueden crear (`403`)
y solicitudes anónimas reciben `401`.

La migración **006** agrega `risks` e índices sin modificar registros existentes.
La clave foránea compuesta `(asset_id, organization_id)` protege la pertenencia del
activo; impide moverlo a otra organización o borrarlo mientras tenga riesgos.
La organización siempre se deriva de la sesión. Se mantienen SQL parametrizado,
CSRF y renderizado mediante `textContent`, con mensajes de carga, vacío y error.

Comprobación manual:

1. Iniciar la API e ingresar como administrador o analista. En **Riesgos**, crear
   uno sin activo y otro asociado a un activo propio; verificar el título recortado,
   fecha local, probabilidad, impacto, puntaje, nivel, estado y activo del detalle.
2. Probar 1×4 (bajo), 1×5 (medio), 2×5 (alto), 4×4 (alto) y 4×5 (crítico).
   En `/docs`, verificar que booleanos, valores 0/6 y campos `score`, `level` o
   `organization_id` sean rechazados (usar cookie y `X-CSRF-Token` para POST).
3. Aplicar filtros por estado, nivel y activo por separado y juntos; probar una
   combinación vacía y **Limpiar**. Recargar y reiniciar: los riesgos deben persistir.
4. Ingresar como lector: consultar listado y detalle, sin **Nuevo riesgo**.
   Desde otra organización, los riesgos y activos anteriores no deben aparecer;
   consultar sus IDs o usarlos en creación/filtros debe devolver `404`.
5. Revisar en ancho móvil y con textos que contengan HTML. Interrumpir la conexión
   y comprobar mensajes de error y reintentos en listado, detalle y selector.

Las pruebas de riesgos cubren las 25 combinaciones, límites de los niveles,
validaciones, filtros, roles, CSRF, aislamiento en ambas direcciones, integridad
en SQL directo, conservación de todos los módulos al migrar y persistencia.
La comprobación Chrome incluye creación con/sin activo, filtros, lector, fechas,
textos seguros, errores de red y anchos 1280/390.

## Controles de seguridad y vínculos con riesgos

La sección **Controles** ofrece listado, filtros, creación y detalle. Nombre
obligatorio, recortado y no vacío; descripción opcional (omitida o null se guarda
como null). Tipos: `preventive`, `detective`, `corrective`. Estados: `planned`
(predeterminado), `implemented`, `retired`. El servidor asigna ID, organización y
fecha UTC. Campos extra, incluido `organization_id`, y valores inválidos reciben
`422`. La interfaz muestra nombres, descripciones, tipos, estados y fechas locales
mediante renderizado seguro.

```json
{"name":"Copias de respaldo","description":"Respaldo diario","type":"corrective","status":"implemented"}
```

| Método | Ruta | Resultado |
| --- | --- | --- |
| POST | `/controls` | Crea el control y devuelve `201` con sus datos públicos |
| GET | `/controls` | Lista por ID; filtros `type` y `status` combinados con AND; sin coincidencias `[]` |
| GET | `/controls/{control_id}` | Detalle o `404` |
| GET | `/risks/{risk_id}/controls` | Controles asociados por ID o `[]` |
| POST | `/risks/{risk_id}/controls` | Cuerpo `{"control_id": 1}`; devuelve `201` con la pareja; duplicado `409` |
| DELETE | `/risks/{risk_id}/controls/{control_id}` | Elimina solo el vínculo; `204` vacío; vínculo ausente `404` |

Administrador y analista crean, vinculan y desvinculan; lector solo consulta.
Todas las rutas requieren sesión; las escrituras exigen `X-CSRF-Token`. Recursos
inexistentes o ajenos reciben `404`. El ID del vínculo debe ser un entero positivo
estricto; booleanos, decimales, cadenas y campos adicionales reciben `422`.

La migración **007** agrega `security_controls` y `risk_controls` sin modificar
registros existentes. La clave primaria de la pareja evita duplicados; claves
foráneas compuestas exigen la misma organización, también en SQL directo y al
cambiar la organización de cualquiera de los recursos. No se permiten borrados de
recursos con vínculos. Se conserva SQL parametrizado y se serializan escrituras
de vínculos con `BEGIN IMMEDIATE`.

El detalle de riesgo muestra **Controles asociados** y ofrece solo controles
propios que todavía no estén vinculados. Quitar el vínculo conserva riesgo y
control, y permite seleccionarlo otra vez. La asociación documenta una medida:
**no cambia automáticamente el puntaje o nivel ni demuestra la eficacia del
control**. Se pueden documentar controles planificados, implementados o retirados.
Evaluación residual y eliminación de controles quedan pendientes.

Comprobación manual:

1. Ingresar como administrador o analista y crear controles de distintos tipos y
   estados, con y sin descripción. Comprobar recorte del nombre, detalle y fecha local.
2. Filtrar por tipo y estado individualmente y juntos; probar una combinación sin
   resultados y **Limpiar**. Revisar también a ancho móvil y con texto que contenga HTML.
3. Crear dos riesgos. Vincular varios controles al primero y el mismo control al
   segundo; comprobar que el selector excluye los asociados y que puntaje/nivel
   no cambian. Quitar un vínculo: ambos recursos y el vínculo del segundo riesgo
   deben permanecer. En `/docs`, repetir POST da `409` y repetir DELETE da `404`
   (con cookie de sesión y cabecera CSRF).
4. Reiniciar la API y comprobar controles, vínculos y datos anteriores. Ingresar
   como lector: ver listas y detalles sin botones de creación/vinculación/desvinculación.
5. Desde otra organización, consultar o vincular IDs anteriores debe dar `404`.
   Interrumpir la conexión: comprobar mensajes y recuperación en listado, detalle
   y **Controles asociados** mediante los reintentos disponibles.

Las pruebas cubren los nueve pares de tipo/estado, validaciones, permisos y CSRF,
relaciones muchos a muchos, duplicados (incluidas peticiones concurrentes),
desvinculación, aislamiento en ambas direcciones y restricciones de SQL directo.
También comparan todos los datos previos y secuencias de IDs al migrar y comprueban
persistencia tras reiniciar. Chrome verifica los flujos, lector, textos seguros,
errores de red y anchos 1280/390 con una base temporal.

## Responsables de incidentes y riesgos

Cada incidente y riesgo puede tener un responsable opcional. Solo los
administradores pueden asignar, reasignar o quitar responsables. Analistas y
lectores consultan la información y filtran los listados según sus permisos.
Los candidatos son usuarios activos, administradores o analistas, de la misma
organización. El cliente no selecciona la organización.

| Método | Ruta | Resultado |
| --- | --- | --- |
| GET | `/assignees` | Candidatos elegibles ordenados por ID; solo `id` y `display_name`, o `[]` |
| PATCH | `/incidents/{incident_id}/assignee` | Devuelve el incidente actualizado con `200` |
| PATCH | `/risks/{risk_id}/assignee` | Devuelve el riesgo actualizado con `200` |

Asignar o reasignar: `{"assignee_id": 1}`. Quitar: `{"assignee_id": null}`.
El campo es obligatorio: omitirlo, enviar booleanos, cadenas, decimales, IDs no
positivos o campos extra recibe `422`. Recurso o usuario inexistente o ajeno
recibe `404`; usuario propio inactivo o lector recibe `422`. Las escrituras
requieren sesión de administrador y `X-CSRF-Token`. Usuarios anónimos reciben
`401` y otros roles o CSRF inválido reciben `403`.

Las respuestas de creación, listado, detalle y cambio de estado de incidentes,
y de creación, listado y detalle de riesgos, incluyen `assignee_id` y
`assignee_name`: ambos null cuando no hay responsable. El nombre se consulta
desde la cuenta actual. La creación no acepta asignaciones: se usa el PATCH de
administrador. Cambiar el responsable no altera estado, historial, notas,
vínculos, probabilidad, impacto ni puntaje.

`GET /incidents?assignee_id=1` combina el responsable con `status` y `severity`.
`GET /risks?assignee_id=1` lo combina con `status`, `level` y `asset_id`, siempre
con AND. Sin coincidencias devuelve `[]`. Usuario de filtro inexistente o ajeno
recibe `404`; un usuario propio sin asignaciones, incluso si ya no es elegible,
produce `[]`. Omitir `assignee_id` consulta todos los responsables. La interfaz
usa únicamente los candidatos permitidos para sus filtros.

La migración **008** agrega `assignee_id` nullable e índices en ambas tablas;
todos los registros existentes quedan inicialmente sin asignar. Las claves
foráneas a usuarios y triggers de inserción/actualización protegen elegibilidad y
pertenencia a la organización. También se impide mover a otra organización un
usuario que tenga asignaciones.

Al desactivar un usuario o convertirlo en lector, un trigger limpia sus
asignaciones de incidentes y riesgos en la misma transacción de la actualización.
Un fallo revierte tanto el usuario como todas las asignaciones. Los recursos y
sus vínculos se conservan; reactivar o devolver el rol analista no reconstruye
las asignaciones anteriores. Esta protección funciona también en SQL directo.
Se mantienen SQL parametrizado, autenticación y CSRF. La asignación no genera
notificaciones ni mensajes. La migración 009 incorpora auditoría local de estos
cambios y de las retiradas automáticas; la auditoría de autenticación queda pendiente.

En los detalles se muestra el nombre o **Sin asignar**. Los administradores ven
selector, **Asignar responsable** y **Quitar responsable**; otros roles solo la
información. La interfaz conserva diseño adaptable, texto seguro y mensajes de
carga, error y ausencia de candidatos, con reintentos. Al gestionar usuarios se
actualizan candidatos, filtros y asignaciones visibles.

Comprobación manual:

1. Ingresar como administrador. Crear un analista y un lector; el selector y
   `/assignees` deben incluir al administrador y al analista, sin correo, rol ni
   otros datos. Abrir un incidente y un riesgo: inicialmente **Sin asignar**.
2. Asignar el analista, reasignar al administrador y quitar la asignación en ambos
   detalles. Revisar que estado, puntaje y vínculos sigan intactos; repetir en
   ancho móvil y con un nombre que contenga HTML.
3. Asignar varios recursos al analista y combinar los filtros por responsable
   con los existentes. Probar una combinación vacía y limpiar los filtros.
4. Convertirlo en lector o desactivarlo desde **Usuarios**: todos sus incidentes
   y riesgos deben quedar sin asignar, sin perder recursos ni otros vínculos.
   Reactivarlo no debe restaurar las asignaciones anteriores.
5. Ingresar como analista o lector: consultar responsables y filtros sin acciones
   de asignación. Desde otra organización, consultar/asignar IDs ajenos recibe
   `404`. En `/docs`, comprobar booleanos, campo ausente y usuario inactivo (`422`)
   usando cookie y cabecera CSRF para PATCH.
6. Reiniciar y verificar persistencia. Interrumpir la conexión y comprobar
   mensajes y reintentos en candidatos y asignación.

Las pruebas usan bases temporales, verifican conservación de todos los módulos
al migrar, persistencia, permisos, aislamiento, SQL directo, desactivación y cambio
a lector. Un fallo provocado en la limpieza de riesgos comprueba la reversión
completa del usuario y de ambas colecciones. Chrome comprueba asignación,
reasignación, eliminación, filtros, limpieza desde Usuarios, lector, texto seguro,
errores y anchos 1280/390.


## Auditoría inicial (migración 009)

La sección **Auditoría**, visible solo para administradores, registra operaciones
exitosas de negocio y administración de usuarios: creaciones, cambios de estado,
notas (solo su ID), vínculos, responsables, roles, desactivaciones y
restablecimientos de contraseña. También registra cada responsable retirado
al desactivar una cuenta o convertirla en lector. El ID y nombre histórico del
actor se conservan aunque cambie su cuenta.

Cada evento se guarda en la misma transacción que el cambio. Si la auditoría
falla se revierte toda la operación, incluidos efectos automáticos y sesiones.
Las solicitudes fallidas y los cambios sin efecto no generan eventos. La
migración conserva todos los datos y no reconstruye eventos anteriores.
Los detalles tienen una lista explícita de campos permitidos y no incluyen
contraseñas, hashes, cookies, tokens, notas, descripciones ni cuerpos completos.

`GET /audit-logs` exige administrador y siempre consulta su organización.
Filtros opcionales: `actor_id`, `action`, `resource_type`, `date_from`, `date_to`,
combinados con AND. Fechas ISO con zona y límites inclusivos; rango invertido
inválido. Paginación: `page=1`, `page_size=25` por defecto, máximo 100 eventos
por página. Orden por fecha UTC descendente e ID descendente. No hay edición
ni eliminación de eventos por API. La interfaz muestra fechas locales, detalles
comprensibles, filtros y mensajes de carga/error/vacío; dispone de Actualizar.

Las pruebas de auditoría se incluyen en la suite completa. La comprobación
opcional de Chrome cubre además la sección, filtros, paginación, fechas locales,
renderizado seguro, errores de red y ancho de celular. Los comandos y pasos
manuales están en [docs/audit.md](docs/audit.md).

Es **auditoría local**: no garantiza resistencia a modificaciones de alguien con
acceso directo a SQLite. Los eventos de autenticación quedan pendientes.


## Resumen inicial

**Resumen** es la pantalla inicial al iniciar sesión y está disponible para
administradores, analistas y lectores. **Gestión** conserva los módulos actuales.
Muestra totales y distribuciones de incidentes (estado y severidad), activos
(criticidad), riesgos (nivel y estado) y controles (estado), incluidas categorías
con cero. Presenta los incidentes pendientes sin responsable, los 5 pendientes
más recientes y los riesgos identificados/en tratamiento sin responsable y los
5 de mayor puntaje. Los enlaces abren los detalles existentes; etiquetas y
fechas se muestran en español y en la zona horaria del navegador.

`GET /dashboard` obtiene la organización de la sesión, parametriza las consultas
y usa una única transacción de lectura consistente. No consulta usuarios ni
auditoría y no une relaciones que multipliquen conteos. Incidentes recientes:
fecha descendente e ID descendente. Riesgos prioritarios: probabilidad × impacto
descendente e ID descendente; los aceptados no participan de esa lista.
No calcula reducción, eficacia de controles ni puntajes globales de seguridad.

Al volver a Resumen o pulsar **Actualizar** se consultan datos nuevos y se muestra
la fecha local de actualización. Incluye mensajes de carga/error/vacío,
**Reintentar**, renderizado seguro y diseño adaptable. No requiere migración nueva
ni modifica datos. Contrato de API, pruebas y pasos manuales:
[docs/dashboard.md](docs/dashboard.md).


## Edición parcial de activos, riesgos y controles

Administradores y analistas pueden usar **Editar** en cada detalle. Formularios
precargados permiten guardar o cancelar, muestran errores y bloquean envíos
repetidos. Los lectores solo consultan. Guardar refresca detalle/listado; volver
a Resumen actualiza el dashboard.

- `PATCH /assets/{asset_id}`: nombre, descripción, tipo y criticidad.
- `PATCH /risks/{risk_id}`: título, descripción, probabilidad, impacto, estado y activo asociado.
- `PATCH /controls/{control_id}`: nombre, descripción, tipo y estado.

Los campos omitidos se conservan. Cuerpos vacíos, campos desconocidos y valores
inválidos reciben `422`. Null solo se admite en descripción y en `asset_id` del
riesgo (quita la asociación). Los PATCH no modifican ID, organización, fecha de
creación ni responsable. El servidor valida permisos, organización y CSRF;
recursos/activos asociados inexistentes o ajenos reciben `404`. Recalcula puntaje
y nivel del riesgo y conserva vínculos. Implementar un control no reduce el puntaje.

La migración 010 permite la acción de auditoría `updated`, conservando eventos,
IDs y secuencias. Edición y evento comparten transacción; un fallo revierte todo.
No se generan eventos sin cambios efectivos. Para textos solo se registran
indicadores de campos cambiados; para valores y asociaciones, valores/IDs
anteriores y nuevos. No se implementa eliminación.

Contrato, migración, pruebas y pasos manuales:
[docs/resource-edits.md](docs/resource-edits.md).
