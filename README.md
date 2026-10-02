# securityops

Plataforma de gestión de seguridad para pequeñas y medianas empresas.

## Objetivo

Centralizar la gestión de activos, usuarios, riesgos,
controles de seguridad e incidentes en una única plataforma.

## Funcionalidades

- Gestión de usuarios y roles
- Inventario de activos
- Gestión de riesgos
- Controles de seguridad
- Gestión de incidentes
- Auditoría
- Reportes
- Dashboard

## Tecnologías

Stack propuesto: React, Python con FastAPI y PostgreSQL. Docker se incorporará más adelante.

El backend implementa `GET /health` y un módulo inicial de incidentes con
SQLite. PostgreSQL queda previsto para una etapa posterior.
La interfaz inicial usa HTML, CSS y JavaScript servidos por FastAPI;
React sigue siendo una opción para etapas futuras.

## Ejecutar el backend en Windows PowerShell

Desde la carpeta del repositorio (`I:\securityops`), crear el entorno virtual
e instalar las dependencias:

```powershell
python -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Si Python no está en el PATH, reemplazar `python` por la ruta completa de
`python.exe`, usando `&` delante de la ruta entre comillas.
En este equipo, el comando alternativo es:

```powershell
& 'C:\Users\facup\AppData\Local\Programs\Python\Python313\python.exe' -m venv backend\.venv
```

Si el entorno ya existe, omitir el comando que lo crea.

El entorno virtual mantiene las dependencias aisladas del resto del equipo.
Los comandos usan su ejecutable directamente, por lo que no hace falta activar
el entorno ni cambiar la política de ejecución de PowerShell.

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

Las fechas se muestran en la zona horaria del navegador. La interfaz informa
carga, listas vacías, operaciones exitosas y errores, y conserva el texto del
formulario cuando una operación falla. Los textos de usuarios se insertan con
`textContent`, sin interpretarlos como HTML. No requiere servicios externos,
autenticación ni un proceso adicional de compilación. El alcance sigue siendo
local, con el servidor escuchando en `127.0.0.1`. `/docs` y los endpoints de la
API siguen disponibles, y se utiliza la misma base SQLite.

## Probar incidentes desde /docs

Con el servidor iniciado, abrir http://127.0.0.1:8000/docs.
Expandir cada operación y usar **Try it out** y luego **Execute**.

1. En `POST /incidents`, enviar este JSON:

   ```json
   {
     "title": "Intento de acceso sospechoso",
     "description": "Se detectaron varios intentos fallidos de inicio de sesión.",
     "severity": "high",
     "status": "open"
   }
   ```

   La respuesta es `201`, con un `id` generado y `created_at` en UTC.
   Los campos de la API usan nombres en inglés. `title`, `description` y
   `severity` son obligatorios; `status` toma `open` si se omite.
2. Ejecutar `GET /incidents` para listar los incidentes ordenados por ID.
3. Ejecutar `GET /incidents/{incident_id}` con el ID recibido para consultarlo.
   Un ID inexistente devuelve `404`.
4. Probar título o descripción vacíos (también solo espacios) y valores
   inválidos de severidad o estado: la respuesta debe ser `422`.

Severidades: `low`, `medium`, `high`, `critical`.
Estados: `open`, `investigating`, `resolved`.

`GET /incidents` admite los filtros opcionales `status` y `severity`:

```text
GET /incidents
GET /incidents?status=open
GET /incidents?severity=high
GET /incidents?status=investigating&severity=critical
```

En `/docs`, expandir `GET /incidents`, pulsar **Try it out**, seleccionar
uno o ambos filtros y pulsar **Execute**. Para listar todos, omitir ambos
parámetros. Si se combinan, cada incidente debe cumplir los dos filtros.
El listado conserva el orden por ID y devuelve `200` con `[]` cuando no hay
coincidencias. Los valores inválidos (incluidos parámetros vacíos enviados
en la URL) devuelven `422`.

Para cambiar el estado desde `/docs`, expandir
`PATCH /incidents/{incident_id}/status`, pulsar **Try it out**, ingresar el ID
de un incidente existente y enviar:

```json
{
  "status": "investigating"
}
```

Al pulsar **Execute**, la respuesta `200` devuelve el incidente actualizado.
Solo cambia `status`; los demás campos se conservan. También se pueden enviar
`open` o `resolved`. Un estado inválido, `null`, un JSON sin `status` o una
solicitud sin cuerpo devuelve `422`. Un ID inexistente con un estado válido
devuelve `404`.

## Historial de cambios de estado

Cada cambio efectivo realizado con `PATCH /incidents/{incident_id}/status`
se registra en la tabla SQLite `incident_status_history`, con `id`,
`incident_id`, `previous_status`, `new_status` y `changed_at` en UTC.
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
  "changed_at": "2026-10-01T18:00:00Z"
}
```

Un incidente sin cambios devuelve `[]`; un ID inexistente devuelve `404`.
La tabla se agrega automáticamente al iniciar la API, sin borrar ni modificar
los incidentes existentes. El historial comienza con los cambios realizados
desde esta implementación: no reconstruye cambios pasados ni registra la creación.

La base se crea automáticamente en `backend/securityops.db` al iniciar la API,
independientemente del directorio desde donde se ejecute. Está excluida de Git.
Detener y volver a iniciar Uvicorn, y repetir `GET /incidents`, permite comprobar
que los registros se conservan.

## Notas de investigación

Las notas se guardan en la tabla `incident_notes`, creada automáticamente al
iniciar la API sin borrar ni recrear la base existente. Cada nota incluye
`id`, `incident_id`, `content` y `created_at` en UTC.

Para agregar una nota desde http://127.0.0.1:8000/docs, expandir
`POST /incidents/{incident_id}/notes`, pulsar **Try it out**, ingresar el ID
de un incidente existente y enviar:

```json
{
  "content": "  Se revisaron los registros de acceso y se identificó la IP de origen.  "
}
```

Al pulsar **Execute**, la respuesta `201` devuelve la nota creada con el
contenido sin espacios al inicio y al final. El contenido debe tener entre
1 y 5000 caracteres después de quitar esos espacios. Contenido vacío, solo
espacios, más de 5000 caracteres, `null`, valores que no sean texto, un JSON
sin `content` o una solicitud sin cuerpo devuelven `422`.

Para listar las notas, expandir `GET /incidents/{incident_id}/notes`, pulsar
**Try it out**, ingresar el mismo ID y pulsar **Execute**. Ejemplo:

```text
GET /incidents/1/notes
```

La respuesta `200` devuelve las notas del más antiguo al más reciente según
`created_at`, usando `id` ascendente para desempatar. Un incidente sin notas
devuelve `[]`. Ambos endpoints devuelven `404` si el incidente no existe
(en el POST, con un cuerpo válido). Las notas se conservan al reiniciar la API
y agregarlas no modifica el incidente ni su historial de estados.

## Pruebas automatizadas

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

Las pruebas usan una base temporal y un servidor HTTP local. Cubren salud,
creación, listado con filtros individuales y combinados, ausencia de coincidencias,
consulta, actualización exclusiva del estado, validaciones,
ID inexistente, SQL parametrizado y persistencia de los incidentes y de los
cambios de estado después de reiniciar el proceso del servidor. También cubren
historial, ausencia de entradas duplicadas, aislamiento entre incidentes,
persistencia del historial, creación de la tabla sobre una base existente y
reversión del estado cuando falla la escritura del historial. Para notas cubren
creación, recorte del contenido, límites de longitud, validaciones, listado,
orden cronológico y desempate por ID, `404`, persistencia tras reiniciar y
creación de la tabla conservando incidentes e historial existentes.
También se comprueba que `/`, los archivos CSS/JavaScript y `/docs` se sirvan
correctamente.

Comprobación opcional de la interfaz en Chrome instalado en su ruta habitual
de Windows, usando Node.js 24 y una base temporal (sin dependencias npm):

```powershell
.\backend\.venv\Scripts\python.exe backend/tests/check_browser.py
```

Se verificaron en Chrome sin ventana la creación y consulta de incidentes,
cambio de estado e historial, validación y creación de notas, filtros combinados,
listas vacías, recuperación de errores de red, fechas en la zona del navegador,
renderizado seguro de textos con etiquetas HTML y ausencia de desbordamiento
horizontal a 1280 y 390 píxeles. Esta comprobación requiere que el entorno
permita iniciar Chrome y conectarse a su puerto local de depuración; no sustituye
una revisión manual en un celular físico.

## Estado

🚧 En desarrollo
