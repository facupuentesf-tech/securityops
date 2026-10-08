# Auditoría local

La migración 009 agrega `audit_logs` e índices sin modificar tablas, filas,
relaciones ni secuencias existentes. No reconstruye eventos anteriores: el
registro empieza con las operaciones realizadas después de esta actualización.

## Eventos y datos permitidos

Cada evento contiene `id`, `organization_id`, `actor_id`, `actor_name`, `action`,
`resource_type`, `resource_id`, `occurred_at` (ISO 8601 UTC) y `details` (objeto JSON).
El servidor obtiene actor y organización de la sesión autenticada. El ID y el
nombre del actor son una instantánea histórica, independiente del nombre, correo,
rol o acceso actual de su cuenta. No se consulta el nombre actual para mostrar
eventos anteriores; el actor no tiene una FK ni eliminación en cascada.

| Acción | Operación | Detalles permitidos |
| --- | --- | --- |
| `created` | Crear incidente, activo, riesgo, control o usuario | `{}`; en riesgos, `asset_id` opcional/null |
| `status_changed` | Cambio efectivo de estado de incidente | `previous_status`, `new_status` |
| `note_created` | Crear nota de incidente | `note_id` |
| `linked`, `unlinked` | Vincular/desvincular activo de incidente o control de riesgo | `asset_id` o `control_id` |
| `assignee_changed` | Asignar, reasignar o quitar responsable | `previous_assignee_id`, `new_assignee_id` (ID o null) |
| `assignee_changed` | Retirada automática por desactivación o conversión a lector | Los IDs anteriores, más `automatic: true`, `user_id` |
| `role_changed` | Cambio efectivo de rol | `previous_role`, `new_role` |
| `deactivated`, `reactivated` | Cambio efectivo del acceso a la cuenta | `previous_is_active`, `new_is_active` |
| `password_reset` | Restablecer contraseña y revocar sesiones | `{}` |
| `user_updated` | Cambio efectivo de nombre/correo | Solo indicadores `display_name_changed`, `email_changed` |

No se almacenan contraseñas, hashes, cookies, tokens, cuerpos completos,
descripciones, títulos de recursos ni contenido de notas. Tampoco se guardan
los correos anteriores/nuevos: para cambios de perfil bastan los indicadores.
Las claves están explícitamente permitidas por acción en `record_audit` y cada
operación construye sus detalles; nunca se serializa un modelo o cuerpo entero.

El evento se inserta con la misma conexión y transacción que la operación.
Los cambios que consultan estado anterior usan `BEGIN IMMEDIATE`. Antes de
modificar un usuario se consultan sus asignaciones; el trigger existente las
retira y el servidor registra un evento por recurso retirado. Un fallo en
cualquier evento revierte usuario, asignaciones, sesiones y eventos de esa
operación, incluso si algunos eventos ya se habían insertado.

Solicitudes fallidas y cambios sin efecto no generan eventos. Repetir estado,
responsable, rol, acceso o perfil normalizado no agrega registros. Un
restablecimiento de contraseña siempre reemplaza el hash y revoca las sesiones,
por lo que representa una operación aunque se elija la misma contraseña.

## Consulta

`GET /audit-logs` requiere administrador; usuarios sin sesión reciben `401` y
analistas/lectores `403`. Siempre se limita a la organización de la sesión,
sin permitir que el cliente elija otra organización. No hay rutas para crear,
editar ni eliminar eventos de auditoría.

| Parámetro | Validación y comportamiento |
| --- | --- |
| `actor_id` | ID positivo; sin coincidencias devuelve una página vacía, incluso para un actor ajeno |
| `action` | Una de las acciones de la tabla anterior |
| `resource_type` | `incident`, `asset`, `risk`, `control`, `user` |
| `date_from`, `date_to` | ISO 8601 con zona horaria, normalizado a UTC; límites inclusivos |
| `page` | Entero de 1 a 1.000.000; predeterminado 1 |
| `page_size` | Entero de 1 a 100; predeterminado 25 |

Todos los filtros se combinan con AND y usan parámetros SQL. Fechas inválidas,
sin zona, rangos invertidos y valores inválidos reciben `422`. La respuesta es
`{"items": [...], "total": N, "page": 1, "page_size": 25}` y cada evento devuelve
`details` como objeto. Orden: `occurred_at DESC, id DESC`. Conteo y página se
consultan en una misma transacción de lectura. La paginación es por desplazamiento:
con escrituras concurrentes puede desplazarse el contenido entre solicitudes.

Ejemplo:

```text
GET /audit-logs?actor_id=1&action=assignee_changed&resource_type=risk&page=1&page_size=25
GET /audit-logs?date_from=2026-10-08T00:00:00Z&date_to=2026-10-08T23:59:59Z
```

## Interfaz y comprobación

La sección **Auditoría** solo aparece para administradores. Muestra fecha local,
nombre histórico e ID del actor, acción, tipo/ID del recurso y detalles en español.
Los filtros de fecha usan hora local y se envían en UTC. El listado pagina de 25
en 25, ofrece Actualizar/Limpiar y mensajes de carga, error y vacío. Usa nodos DOM
y `textContent`, limpia datos al cerrar sesión e ignora respuestas obsoletas.

Pruebas automatizadas:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\backend\.venv\Scripts\python.exe backend\tests\check_browser.py
```

La suite usa bases temporales. Cubre eventos, campos permitidos, ausencia de
secretos, actor histórico, solicitudes fallidas, cambios sin efecto, permisos,
aislamiento, filtros AND, fechas, paginación y desempate, persistencia y migración
idempotente con conservación de todas las tablas/secuencias. Triggers de prueba
provocan fallos de inserción para verificar reversión en todas las operaciones,
incluido un fallo tardío en el evento de retirada automática de un riesgo.
Chrome headless comprueba carga/error/vacío, filtros, fechas locales, paginación,
XSS, visibilidad por rol y diseño en anchos de 1280 y 390 píxeles.

Comprobación manual:

1. Iniciar el servidor según README e ingresar como administrador. Crear un
   recurso y pulsar **Actualizar** en Auditoría: debe aparecer un evento nuevo.
2. Cambiar estado, agregar nota, vincular/desvincular y asignar/reasignar. Verificar
   IDs y valores anteriores/nuevos; repetir estado/responsable sin agregar eventos.
3. Asignar incidentes y riesgos a un analista; desactivarlo o convertirlo en
   lector. Verificar eventos de cuenta y una retirada automática por recurso.
4. Renombrar al actor y crear otro recurso: los eventos anteriores mantienen su
   nombre original. Combinar filtros, usar un rango local y recorrer páginas.
5. Consultar como analista/lector: la sección no aparece y el endpoint devuelve
   `403`. Probar otra organización: no debe ver los eventos de la primera.
6. Reiniciar el servidor y verificar persistencia; probar un ancho de celular y
   desconectar la red para verificar el mensaje de error y reintentar con Actualizar.

## Límites

Es auditoría local: **no garantiza resistencia a modificaciones de alguien con
acceso directo a SQLite**. No incluye firmas, encadenamiento criptográfico,
almacenamiento externo ni protección contra el administrador del sistema local.
Los cambios SQL directos no pasan por los eventos de negocio de la API.
Los eventos de autenticación (login, logout, rechazo o expiración) quedan pendientes.
