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

El primer paso implementado es una API mínima con `GET /health`.

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

## Estado

🚧 En desarrollo
