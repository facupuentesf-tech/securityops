# Resumen inicial

`GET /dashboard` está disponible para administradores, analistas y lectores
autenticados. Sin sesión devuelve `401`; cuentas inactivas o sesiones expiradas
no acceden. La organización se obtiene de la sesión en el servidor. No hay
parámetros para seleccionar otra organización ni consultas a usuarios o auditoría.

## Contrato de respuesta

La respuesta tiene estas claves:

| Campo | Contenido |
| --- | --- |
| `generated_at` | Fecha ISO 8601 UTC de generación del resumen |
| `incidents.total` | Todos los incidentes de la organización |
| `incidents.by_status` | `open`, `investigating`, `resolved` |
| `incidents.by_severity` | `low`, `medium`, `high`, `critical` |
| `incidents.pending.total` | Incidentes `open` o `investigating` |
| `incidents.pending.unassigned` | Pendientes con `assignee_id IS NULL` |
| `incidents.pending.recent` | Hasta 5 pendientes, ordenados por `created_at DESC, id DESC` |
| `assets.total` | Todos los activos |
| `assets.by_criticality` | `low`, `medium`, `high`, `critical` |
| `risks.total` | Todos los riesgos, incluidos los aceptados |
| `risks.by_level` | `low`, `medium`, `high`, `critical`, calculados con la matriz existente |
| `risks.by_status` | `identified`, `treating`, `accepted` |
| `risks.unassigned_pending` | Riesgos `identified` o `treating` con `assignee_id IS NULL` |
| `risks.priority` | Hasta 5 riesgos `identified` o `treating`, por `probability * impact DESC, id DESC` |
| `controls.total` | Todos los controles |
| `controls.by_status` | `planned`, `implemented`, `retired` |

Todas las distribuciones incluyen sus categorías con valor cero. Sin recursos,
los totales son cero y las listas están vacías. Las listas no incluyen contenido
de notas, descripciones, nombres de responsables, correos ni datos administrativos.

Un incidente reciente contiene solamente `id`, `title`, `status`, `severity`,
`created_at`. Un riesgo prioritario contiene `id`, `title`, `status`, `probability`,
`impact`, `score`, `level`, `created_at`. Son recursos que todos los roles ya pueden
consultar. Los riesgos aceptados quedan fuera de prioridades, aunque su puntaje
sea mayor. Los incidentes resueltos quedan fuera de recientes y pendientes.

El puntaje de un riesgo reutiliza la evaluación inicial: probabilidad × impacto;
niveles bajo 1–4, medio 5–9, alto 10–16, crítico 17–25. El resumen no calcula
porcentajes de reducción, eficacia de controles ni un puntaje global de seguridad.

## Lectura y persistencia

Todas las consultas usan la misma conexión con `BEGIN` y una transacción de
lectura; el conjunto refleja una instantánea consistente aun con cambios
concurrentes. Cada consulta parametriza `organization_id`. Los nombres de
tablas y columnas del ayudante de distribución son constantes internas.

Los conteos y listas parten de las tablas de incidentes, activos, riesgos y
controles. No unen tablas de relaciones muchos a muchos: varios activos de un
incidente o controles de un riesgo no multiplican filas ni totales. La consulta
no genera auditoría, no escribe datos ni requiere una migración nueva. Se usan
las migraciones existentes hasta 011.

## Interfaz

**Resumen** es la pantalla inicial al ingresar o restaurar una sesión. La
navegación **Gestión** conserva todos los módulos y sus permisos. Volver a
**Resumen** solicita datos nuevos; **Actualizar** también vuelve a consultar.
Se muestra la fecha local de actualización proporcionada por `generated_at`.

Las tarjetas muestran totales y distribuciones con etiquetas en español. Las
listas enlazan al detalle de incidentes y riesgos dentro de Gestión y reutilizan
las operaciones existentes. Fechas locales, severidad/nivel escritos como texto,
estado activo de navegación, foco visible, mensajes anunciados y `aria-busy`
ayudan a interpretar y navegar el resumen. Las tarjetas se adaptan a una columna
en celular. Los títulos se renderizan con nodos DOM y `textContent`.

La carga oculta el contenido anterior; un error ofrece **Reintentar**. Una
organización vacía muestra un mensaje y conserva todas las categorías en cero.
No se reutilizan respuestas obsoletas al navegar, actualizar o cerrar sesión;
cerrar sesión limpia el contenido del resumen.

## Verificación

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\backend\.venv\Scripts\python.exe backend\tests\check_browser.py
```

`test_dashboard.py` comprueba categorías vacías, conteos, pendientes sin
responsable, prioridades y desempates, selección de 5 recursos, matriz de niveles,
permisos, aislamiento en ambas direcciones y exclusión de usuarios/auditoría.
Incluye varios vínculos por recurso para probar que no se duplican totales.
Una prueba habilita WAL en una base temporal y confirma nuevas escrituras entre
consultas: el lector mantiene su instantánea original y otra petición ve los
datos nuevos. La suite completa sigue verificando los módulos anteriores.

Chrome headless prueba pantalla inicial, organización vacía, navegación a los
detalles, actualización al volver y con el botón, fechas locales, texto seguro,
carga/error/reintento y diseños de escritorio (1280 px) y celular (390 px).
También comprueba la pantalla inicial del lector y los módulos anteriores.

Comprobación manual:

1. Iniciar el servidor según README e ingresar con cualquiera de los tres roles.
   Debe aparecer Resumen; una organización nueva muestra todos los valores en cero.
2. Ir a Gestión y crear recursos según los permisos. Volver a Resumen y verificar
   totales, categorías y fecha actualizada; probar también Actualizar.
3. Crear incidentes pendientes/resueltos y riesgos identificados/en tratamiento/
   aceptados. Verificar que las listas y cantidades sin responsable respeten esos
   estados y que los enlaces abran el detalle correcto.
4. Vincular varios activos a un incidente y varios controles a un riesgo: sus
   totales deben permanecer iguales. Ingresar en otra organización y verificar
   que no se compartan datos.
5. Probar el ancho de celular, navegación con teclado y títulos con caracteres
   especiales. Desconectar la red y actualizar: debe aparecer un error; recuperar
   la conexión y pulsar Reintentar.

El dashboard usa la evaluación original actual; las evaluaciones residuales de
[riesgos](risk-assessments.md) no modifican sus niveles ni prioridades.
