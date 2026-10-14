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

En la misma terminal, guardar la selección habitual antes de activar la demo.
Si la base demo ya existe, no volver a ejecutar `create-demo`: definir su ruta
explícitamente. Verificar que corresponde a la demo ficticia preparada, sin
abrir ni mostrar datos de la base habitual:

```powershell
$usualDatabase = $env:SECURITYOPS_DATABASE
$demoDatabase = Join-Path $PWD 'backend\portfolio-demo.db'
if (-not (Test-Path -LiteralPath $demoDatabase -PathType Leaf)) { throw 'Falta la base demo; seguir la preparación anterior.' }
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

Preparación: iniciar sesión con `admin@aurora.example.test` (Alba Demo) y la
contraseña elegida al ejecutar `create-demo`; mantener las otras tres cuentas
de la tabla disponibles en el gestor, sin mostrarlas junto a sus contraseñas.
Este recorrido consulta los registros existentes: no guardar notas, estados,
asignaciones ni evaluaciones. Iniciar/cerrar sesión sí crea o elimina sesiones
en la base demo; no ejecutar la presentación si se exige conservarla byte a byte.
Los totales y puntajes siguientes corresponden a la carga inicial de `create-demo`;
si la demo fue usada antes, comprobarlos y explicar cualquier diferencia.

1. **0:00–0:45 — Problema y resumen.** Explicar la información dispersa y abrir
   Resumen: Aurora tiene 3 incidentes, 4 activos, 3 riesgos y 3 controles. Mostrar
   pendientes, falta de responsable y prioridades. Los riesgos del dashboard
   muestran la evaluación original, no la residual.
2. **0:45–1:50 — Investigación.** Ir a Gestión, filtrar incidentes por “En
   investigación” y severidad alta, abrir “Correo sospechoso en Nube Clara”.
   Mostrar a Bruno como responsable, los dos activos afectados, la nota y el
   historial atribuido. Leer la nota ficticia ya creada, sin agregar otra. El
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
   sección **Evaluación residual** y desplegar **Historial de evaluaciones
   residuales**. Mostrar evaluador, fecha y la instantánea de la evaluación
   original conservada en cada registro (no se guarda una instantánea de los
   controles). Explicar que no reemplaza la original ni modifica sus métricas
   del dashboard; no pulsar **Guardar evaluación**.
6. **4:00–4:50 — Auditoría y exportación.** En auditoría, filtrar acción o tipo
   de recurso para revisar creación, asignación, nota, vínculo o evaluación.
   Las operaciones usan la lógica existente y registran actor y organización;
   no se inventaron filas de auditoría. Volver a incidentes, aplicar filtros y
   señalar **Exportar CSV** y explicar que respeta los filtros; para mantener
   el ritmo, la descarga puede quedar para preguntas. Los lectores no pueden
   exportar. En Auditoría, seleccionar acción **Evaluación residual** y recurso
   **Riesgo**, aplicar filtros y mostrar actor, fecha e IDs del evento.
7. **4:50–6:00 — Roles y aislamiento.** Usar **Cerrar sesión** antes de cada
   cambio de cuenta:
   - Ingresar con `analista@aurora.example.test` (Bruno Demo), abrir Gestión
     y el mismo incidente/riesgo: mostrar formularios para investigar y evaluar,
     sin enviarlos. No dispone de gestión de usuarios, Auditoría ni asignación
     de responsables.
   - Ingresar con `lector@aurora.example.test` (Clara Demo): abrir el mismo
     detalle y su historial residual; puede consultar, sin formularios de
     escritura, exportación ni Auditoría.
   - Ingresar con `admin@delta.example.test` (Dalia Demo): abrir Resumen
     (1 incidente, 1 activo, 0 riesgos y 0 controles), luego Gestión. Mostrar
     **Revisión exclusiva de Delta** y **Estación Delta exclusiva**; los recursos
     de Aurora no aparecen. Es otra organización, aunque el rol sea administrador.

La vista demuestra el cambio de alcance; la garantía del backend se comprueba
por separado con las pruebas existentes: permisos denegados con `403` e IDs
de otra organización con `404`. No presentar el cambio visual como prueba
suficiente de todos los permisos de la API. Para llegar a siete minutos, ampliar
la explicación de historial y aislamiento; para cinco, abreviar Activos y CSV.

## Capturas de la presentación

Las cuatro capturas están pendientes; esta preparación no dispuso de un
navegador autenticado y no inició el servidor ni sesiones para evitar escrituras
en las bases. No se crearon imágenes de reemplazo. Seguir el
[plan de capturas](images/README.md) una vez habilitada una sesión de demo.
La presentación y el guion se revisaron contra los archivos del repositorio,
sin ejecutar la aplicación ni las pruebas en esta preparación.

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
