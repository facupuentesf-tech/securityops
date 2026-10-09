# Demostración local de SecurityOps

SecurityOps es un prototipo local que centraliza información de seguridad que
una pequeña organización podría tener dispersa en planillas: activos, incidentes,
responsables, riesgos, controles y decisiones de evaluación. Esta demo usa
organizaciones, personas y escenarios completamente ficticios. No acredita
cumplimiento normativo, eficacia de controles ni preparación para producción.

## Preparar la base separada

Ejecutar desde la raíz del repositorio en PowerShell. Si el entorno virtual ya
existe, omitir su creación; instalar las dependencias si aún no están disponibles:

```powershell
python -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Detener cualquier servidor previo con Ctrl+C. Mantener `SECURITYOPS_DATABASE`
con su valor habitual (o sin definir) durante la creación: el comando también
protege esa ruta, además de `backend/securityops.db` y sus respaldos conocidos.
No usa ni migra esas bases. No cambiar la variable a la ruta demo hasta que
termine la creación.

```powershell
$demoDatabase = Join-Path $PWD 'backend\portfolio-demo.db'
.\backend\.venv\Scripts\python.exe backend\main.py create-demo --database "$demoDatabase"
if ($LASTEXITCODE -ne 0) { throw 'No se creó la demo; revisá el destino y la entrada interactiva.' }
```

Solicita una contraseña nueva y su confirmación para cada cuenta. Usar entre
12 y 128 caracteres. La entrada debe ser interactiva y oculta; el comando
no lee contraseñas de redirecciones y no acepta contraseñas por argumentos o variables de
entorno. No imprime ni documenta contraseñas; almacena únicamente sus hashes
scrypt. Conservá las contraseñas elegidas en tu gestor de contraseñas.

En Windows se comprueba que haya una consola disponible (`CONIN$`), porque una
terminal integrada puede informar `stdin.isatty() == False` y aun así permitir
que `getpass` lea desde la consola con entrada oculta. Sin consola, el comando
rechaza la entrada y nunca recurre a una lectura con eco. Los errores distinguen
ruta existente/protegida/inválida, contraseña inválida, confirmación incorrecta,
entrada no interactiva y fallo interno. Un fallo interno no muestra excepciones
ni valores de entrada que puedan contener secretos.

| Organización ficticia | Cuenta | Rol |
| --- | --- | --- |
| Aurora Laboratorio | `admin@aurora.example.test` | Administrador |
| Aurora Laboratorio | `analista@aurora.example.test` | Analista |
| Aurora Laboratorio | `lector@aurora.example.test` | Lector |
| Delta Taller | `admin@delta.example.test` | Administrador |

El destino debe terminar en `.db` y su directorio debe existir. Se rechazan la
base predeterminada, la habitual configurada, los respaldos conocidos, destinos
existentes y auxiliares SQLite existentes. La reserva exclusiva del archivo
también impide sobrescribirlo si otro proceso lo crea durante las preguntas.
Las bases `.db` y sus archivos `-journal`, `-wal` y `-shm` se excluyen de Git.
Si la carga falla después de reservar el archivo, puede quedar una base parcial:
no usarla para presentar; elegir otro nombre nuevo y repetir. Nunca reemplazar
la base habitual ni sus respaldos. Para repetir una presentación con los mismos
datos, basta iniciar nuevamente la base demo; para empezar desde cero, usar otro
archivo nuevo, por ejemplo `backend\portfolio-demo-2.db`.

## Iniciar y volver a la base habitual

En la misma terminal, guardar la selección habitual antes de activar la demo:

```powershell
$usualDatabase = $env:SECURITYOPS_DATABASE
$env:SECURITYOPS_DATABASE = $demoDatabase
.\backend\.venv\Scripts\python.exe -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
```

En otra terminal, abrir la interfaz:

```powershell
Start-Process 'http://127.0.0.1:8000/'
```

Ingresar con una de las cuentas y la contraseña elegida. Al finalizar, detener
Uvicorn con Ctrl+C y restaurar la selección en la terminal del servidor:

```powershell
if ([string]::IsNullOrEmpty($usualDatabase)) {
    Remove-Item Env:SECURITYOPS_DATABASE -ErrorAction SilentlyContinue
} else {
    $env:SECURITYOPS_DATABASE = $usualDatabase
}
.\backend\.venv\Scripts\python.exe -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Si abrís una terminal nueva sin recordar una configuración personalizada,
consultá tu configuración local. Para volver explícitamente a la ruta
predeterminada, detener primero el servidor, ejecutar
`Remove-Item Env:SECURITYOPS_DATABASE -ErrorAction SilentlyContinue` y luego el
comando de Uvicorn anterior. Cambiar la variable no cambia la base de un proceso
que ya está iniciado. Las sesiones de la demo no sirven en la base habitual.

## Guion de seis minutos

Preparación: iniciar sesión como administrador de Aurora; mantener las otras
cuentas disponibles en el gestor. Toda modificación en la presentación queda
persistida en la base demo, incluidos estados, notas y evaluaciones.

1. **0:00–0:45 — Problema y resumen.** Explicar la información dispersa y abrir
   Resumen: Aurora tiene 3 incidentes, 4 activos, 3 riesgos y 3 controles. Mostrar
   pendientes, falta de responsable y prioridades. Los riesgos del dashboard
   muestran la evaluación original, no la residual.
2. **0:45–1:50 — Investigación.** Ir a Gestión, filtrar incidentes por “En
   investigación” y severidad alta, abrir “Correo sospechoso en Nube Clara”.
   Mostrar a Bruno como responsable, los dos activos afectados, la nota y el
   historial atribuido. Agregar una nota breve marcada como simulación. El
   incidente de Atlas sigue abierto sin responsable; el acceso de prueba ya
   tiene dos cambios de estado hasta resuelto.
3. **1:50–2:30 — Activos.** Filtrar por servicio y criticidad crítica; abrir
   “Correo Nube Clara”. Limpiar filtros para mostrar hardware, software y datos,
   con las cuatro criticidades. Explicar que un incidente puede afectar varios
   activos sin duplicarlos ni eliminarlos.
4. **2:30–3:15 — Riesgo y controles.** Abrir “Acceso indebido al correo ficticio”:
   probabilidad 4, impacto 5, puntaje original 20, estado en tratamiento. Mostrar
   los controles preventivo implementado y detectivo planificado; vinculación
   no equivale a eficacia medida.
5. **3:15–4:00 — Evaluación residual.** Abrir el historial: dos estimaciones
   manuales con puntajes 12 y 8, original 20 y justificación. Mostrar la
   instantánea de controles y evaluador. Opcionalmente registrar otra evaluación
   explicando que es una decisión ficticia; no reemplaza la original ni modifica
   sus métricas del dashboard.
6. **4:00–4:50 — Auditoría y exportación.** En auditoría, filtrar acción o tipo
   de recurso para revisar creación, asignación, nota, vínculo o evaluación.
   Las operaciones usan la lógica existente y registran actor y organización;
   no se inventaron filas de auditoría. Volver a incidentes, aplicar filtros y
   exportar CSV; abrir el archivo descargado para mostrar que respeta los
   filtros. Los lectores no pueden exportar.
7. **4:50–6:00 — Roles y aislamiento.** Cerrar sesión e ingresar como analista:
   puede investigar y evaluar, pero no administrar usuarios ni asignar
   responsables. Cerrar sesión e ingresar como lector de Aurora: consulta sin
   formularios de escritura ni auditoría. Finalmente ingresar como administrador
   de Delta: resumen con 1 incidente y 1 activo exclusivo, sin recursos de
   Aurora. La API también verifica permisos y devuelve 404 para IDs ajenos.

## Decisiones técnicas y límites

FastAPI sirve API e interfaz HTML/CSS/JavaScript en un único proceso Uvicorn;
SQLite y migraciones SQL versionadas simplifican la ejecución local sin servicios
externos. Las operaciones usan consultas parametrizadas, validación, transacciones
para cambios con auditoría y restricciones organizacionales. La organización se
obtiene de la sesión y los permisos se verifican en el backend. Las contraseñas
usan scrypt; las cookies de sesión son HttpOnly y SameSite=Strict, con expiración
y protección CSRF. La demo reutiliza las funciones de negocio; solo organizaciones
y administradores iniciales se crean mediante bootstrap local, sin inventar un
actor previo ni eventos de autenticación que el sistema no registra.

Las evaluaciones residuales son estimaciones manuales con historial, no un modelo
validado de reducción del riesgo. La auditoría SQLite local no es un registro
inmutable frente a quien controle el archivo. No hay auditoría de autenticación,
MFA de acceso a la aplicación, recuperación pública de contraseña ni controles
operativos de un despliegue compartido. Las exportaciones son CSV de recursos,
no informes de cumplimiento. Tampoco hay detección automática de amenazas ni
integración con fuentes reales. El servidor debe permanecer en `127.0.0.1`.

## Verificación reproducible

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\backend\.venv\Scripts\python.exe backend\tests\check_browser.py
.\backend\.venv\Scripts\python.exe backend\tests\check_demo_browser.py
```

La suite usa bases temporales; las pruebas de demo verifican creación, datos,
contraseñas derivadas, historial, auditoría, aislamiento, integridad SQLite,
rechazo de rutas y conservación byte a byte de una base habitual temporal.
La prueba de navegador requiere Node.js y Chrome; usa otra base temporal y
comprueba flujos, filtros, roles, evaluaciones, auditoría y descargas CSV. No
iniciar esas verificaciones contra la base habitual ni la demo de presentación.
`check_demo_browser.py` recorre específicamente los datos ficticios de portafolio
en otra base temporal, con contraseñas aleatorias que no se muestran ni guardan
en archivos.
