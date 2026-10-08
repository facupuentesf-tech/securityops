# Edición de activos, riesgos y controles

Administradores y analistas pueden editar recursos de su organización mediante
PATCH. Lectores solo consultan. Los endpoints devuelven el recurso actualizado
con el mismo formato que las consultas existentes.

| Endpoint | Campos editables |
| --- | --- |
| `PATCH /assets/{asset_id}` | `name`, `description`, `type`, `criticality` |
| `PATCH /risks/{risk_id}` | `title`, `description`, `probability`, `impact`, `status`, `asset_id` |
| `PATCH /controls/{control_id}` | `name`, `description`, `type`, `status` |

## Actualizaciones parciales y validación

Los campos omitidos conservan su valor. `{}`, cuerpos ausentes, campos
desconocidos y valores inválidos devuelven `422`. No se admiten cambios a `id`,
`organization_id`, `created_at`, `assignee_id`, `assignee_name`, `score` ni `level`.

`description` admite string o null; `""` sigue siendo un string válido. En riesgos,
`asset_id` admite un entero positivo estricto o null; null quita la asociación.
Los demás campos rechazan null. Nombres/títulos se recortan y deben conservar
al menos un carácter. Tipos, estados y criticidad usan los mismos valores que
la creación. Probabilidad e impacto son enteros estrictos de 1 a 5: se rechazan
booleanos, strings y floats, incluso `1.0`.

La organización y el actor vienen de la sesión; no del cuerpo. Sin sesión se
recibe `401`, lectores o solicitudes con CSRF inválido reciben `403`. Recursos
inexistentes/ajenos y activos asociados inexistentes/ajenos reciben `404`, sin
revelar su existencia. Las consultas y actualizaciones parametrizan sus valores.

Ejemplos:

```json
{"name": "Servidor actualizado", "description": null}
```

```json
{"probability": 5, "status": "treating", "asset_id": null}
```

El puntaje y nivel del riesgo se recalculan en el servidor con probabilidad ×
impacto y la matriz existente. Fechas de creación, responsables, notas, historial
y vínculos muchos a muchos se conservan. Cambiar un control a `implemented`
**no reduce automáticamente el puntaje del riesgo** ni prueba su eficacia.
No se implementa eliminación de recursos.

## Auditoría y migración 010

La edición consulta el estado previo con `BEGIN IMMEDIATE` y guarda el cambio
y un evento `updated` en la misma conexión/transacción. Si falla el evento,
se revierte toda la edición. Los valores normalizados iguales a los existentes
devuelven el recurso sin generar eventos; las solicitudes fallidas tampoco
generan eventos.

Los detalles solo incluyen los campos que cambiaron:

- Textos: `name_changed`, `title_changed`, `description_changed`, con valor true.
  No se copian nombres, títulos ni descripciones anteriores o nuevos.
- Valores enumerados/números/asociaciones: pares `previous_...`, `new_...` para
  `type`, `status`, `criticality`, `probability`, `impact`, `asset_id` según el recurso.
  `asset_id` contiene IDs o null, nunca el nombre del activo.

La lista de claves de auditoría está explícitamente permitida. No se guardan
contraseñas, hashes, cookies, tokens, notas ni cuerpos completos. La consulta
de auditoría permite filtrar `action=updated` y muestra estos detalles en español.
Sigue siendo auditoría local sin resistencia garantizada frente a cambios con
acceso directo a SQLite; la auditoría de autenticación sigue pendiente.

La migración 010 amplía el CHECK de acciones de `audit_logs`. SQLite requiere
crear una tabla con la restricción nueva y copiar las filas; la migración conserva
todos los eventos, IDs, fechas, detalles, organización y actor, reconstruye los
dos índices y conserva el máximo de la secuencia, incluso si supera el ID actual
más alto. No modifica tablas de negocio, vínculos, usuarios ni sesiones y no
reconstruye eventos históricos. La migración completa es transaccional e idempotente.

## Interfaz

El detalle de cada recurso ofrece **Editar** solo a administradores y analistas.
Los formularios están precargados, con **Guardar**, **Cancelar** y mensajes de
validación/error. El selector del activo de un riesgo carga solo activos de la
organización y ofrece **Sin activo asociado**; un fallo de carga permite reintentar.

La interfaz envía solo los campos modificados. Vaciar una descripción existente
la limpia a null; una descripción que ya era `""` se conserva si no se modifica.
Cancelar descarta el formulario sin enviar PATCH. Durante el guardado se deshabilitan
los controles y se bloquean envíos repetidos. Navegar a otro detalle, volver al
listado, al resumen o cerrar sesión invalida el editor anterior para ignorar
resultados obsoletos.

Guardar refresca detalle y listado del módulo. Al volver a Resumen el dashboard
reconsulta los datos y refleja distribuciones y puntajes nuevos. Se mantienen
CSRF, renderizado con nodos DOM/textContent, foco visible y diseño de celular.

## Verificación

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\backend\.venv\Scripts\python.exe backend\tests\check_browser.py
```

Las pruebas cubren actualizaciones parciales/completas, null, campos protegidos,
validaciones, permisos, CSRF, aislamiento, activos asociados, recálculo, vínculos,
responsables, fecha original, persistencia y dashboard. Verifican detalles de
auditoría, ausencia de textos y eventos sin cambios. Un trigger de prueba falla
al insertar `updated` y se compara toda la base antes/después para confirmar
reversión y conservación de relaciones. La migración se comprueba con eventos
previos y una secuencia superior al último ID existente. Chrome prueba precarga,
guardar/cancelar, errores de validación/red, reintento, envíos repetidos, texto
seguro, permisos del lector, recálculo y ancho de celular.

Comprobación manual:

1. Ingresar como administrador o analista, ir a Gestión y abrir el detalle de un
   activo, riesgo o control. Pulsar Editar: los valores deben estar precargados.
2. Modificar valores y cancelar. Reabrir: deben mantenerse los valores originales.
   Guardar cambios, volver al listado y verificar los valores nuevos.
3. En un riesgo cambiar probabilidad/impacto y quitar el activo; verificar puntaje,
   nivel, responsable y controles asociados. Cambiar un control a implementado:
   el puntaje del riesgo debe mantenerse.
4. Como administrador, actualizar Auditoría: comprobar un evento de edición con
   indicadores para textos y valores/IDs anteriores/nuevos para los otros campos.
   Guardar sin cambios no debe agregar eventos. Volver a Resumen para verificarlo.
5. Probar nombre/título vacío, red desconectada y volver a guardar tras corregir
   el error. Probar teclado y ancho de celular. Ingresar como lector: no debe
   aparecer Editar y los PATCH deben devolver `403`.
