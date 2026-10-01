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

La base se crea automáticamente en `backend/securityops.db` al iniciar la API,
independientemente del directorio desde donde se ejecute. Está excluida de Git.
Detener y volver a iniciar Uvicorn, y repetir `GET /incidents`, permite comprobar
que los registros se conservan.

## Pruebas automatizadas

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

Las pruebas usan una base temporal y un servidor HTTP local. Cubren salud,
creación, listado con filtros individuales y combinados, ausencia de coincidencias,
consulta, actualización exclusiva del estado, validaciones,
ID inexistente, SQL parametrizado y persistencia de los incidentes y de los
cambios de estado después de reiniciar el proceso del servidor.

## Estado

🚧 En desarrollo
