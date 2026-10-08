# Exportaciones CSV

Administradores y analistas pueden descargar incidentes, activos, riesgos y
controles de su organización. El lector recibe `403`; una sesión ausente o
inválida recibe `401`. La organización se obtiene de la sesión, nunca de la URL.

| Endpoint GET | Filtros opcionales, iguales al listado JSON |
| --- | --- |
| `/reports/incidents.csv` | `status`, `severity`, `assignee_id` |
| `/reports/assets.csv` | `type`, `criticality` |
| `/reports/risks.csv` | `status`, `level`, `asset_id`, `assignee_id` |
| `/reports/controls.csv` | `type`, `status` |

Los filtros se combinan con AND. Se usan los mismos enums y validaciones de
IDs positivos del listado: valores inválidos reciben `422`; responsables o
activos inexistentes/ajenos reciben `404`. Los filtros y valores SQL se pasan
como parámetros. Las respuestas actuales de los listados no cambian.

## Contenido

Cada recurso ocupa exactamente una fila, ordenada por ID ascendente, sin límite
de resultados ni paginación. Sin coincidencias se devuelve solo el encabezado.
Columnas y estados, niveles, criticidades y tipos tienen etiquetas en español.

- Incidentes: ID, título, descripción, severidad, estado, fecha de creación,
  ID/nombre del responsable e IDs/nombres de activos afectados. Las listas de
  activos se ordenan por ID y se separan con ` | ` dentro de la celda.
- Activos: ID, nombre, descripción, tipo, criticidad y fecha de creación.
- Riesgos: ID, título, descripción, probabilidad/impacto/puntaje/nivel original
  actual, estado, ID/nombre del activo y responsable, fecha de creación y última
  evaluación residual (ID, probabilidad, impacto, puntaje, nivel y fecha).
  La última evaluación se selecciona por fecha descendente e ID descendente;
  sus seis columnas quedan vacías si no existe. No se exporta su justificación.
- Controles: ID, nombre, descripción, tipo, estado y fecha de creación.

Las fechas usan ISO 8601 en UTC con zona `+00:00`. Relaciones y evaluaciones se
consultan dentro de la misma transacción de lectura que los recursos para
obtener una instantánea consistente. Las relaciones múltiples no multiplican
filas. Los nombres de responsables acompañan al recurso; no se exportan correos,
roles, credenciales, sesiones, registros de administración de usuarios, auditoría,
notas de investigación ni justificaciones residuales.

## Formato y neutralización de fórmulas

CSV UTF-8 con BOM, delimitador `;` y finales de registro CRLF. El escritor CSV
escapa separadores, comillas (duplicándolas) y saltos de línea. Los valores
numéricos calculados por el servidor siguen siendo numéricos; los opcionales
ausentes se representan con celdas vacías.

Antes de escribir cada texto se inspecciona su inicio, saltando espacios Unicode
y caracteres Unicode de control/formato, incluidos los de ancho cero. Si el
primer carácter significativo es `=`, `+`, `-` o `@`, se antepone un apóstrofo
ASCII al texto completo. También se antepone cuando ese prefijo contiene
caracteres de control/formato. Esto impide que esos textos se interpreten como
fórmulas al abrirlos en una hoja de cálculo. No se eliminan espacios ni se
modifican los datos almacenados. Cada nombre de activo afectado se neutraliza
antes de componer su celda y todos los textos finales pasan por esta protección.

La respuesta tiene `Content-Type: text/csv; charset=utf-8`,
`Content-Disposition: attachment; filename="securityops-{recurso}.csv"`,
`Cache-Control: no-store` y `X-Content-Type-Options: nosniff`. Los nombres son
constantes del servidor. El archivo se genera en memoria; no se guarda en disco
del servidor ni se recortan resultados silenciosamente. El consumo de memoria
crece con el número y tamaño de los resultados.

## Interfaz y comprobación

En Gestión, cada listado ofrece **Exportar CSV** para administrador/analista.
Exporta todos los resultados de los últimos filtros aplicados, aunque luego se
editen los campos sin pulsar **Aplicar filtros**. Durante la solicitud muestra
el estado y deshabilita el botón; un error habilita el reintento. El lector no
ve el botón. El navegador descarga mediante un Blob sin insertar contenido CSV
en el HTML. Cerrar o cambiar la sesión invalida las descargas pendientes.

Pruebas automatizadas:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests
.\backend\.venv\Scripts\python.exe backend/tests/check_browser.py
```

`test_reports.py` verifica contenido, permisos, aislamiento, filtros y validación,
ausencia de duplicados/secretos, última evaluación, textos especiales, fórmulas,
organizaciones vacías, orden, ausencia de truncamiento/escrituras y lectura
consistente con escrituras concurrentes. Chrome comprueba descargas reales de
los cuatro módulos, BOM, filtros aplicados, encabezados vacíos, errores, clics
repetidos y tamaños de escritorio/móvil, además de los flujos existentes.

Comprobación manual:

1. Iniciar sesión como administrador o analista; abrir Gestión y aplicar filtros.
2. Descargar cada listado y abrir el archivo seleccionando UTF-8 y separador `;`.
   Comparar IDs, categorías, responsables, vínculos y fechas con los detalles.
3. Evaluar un riesgo varias veces y comprobar la última residual; verificar
   celdas vacías en otro riesgo sin evaluaciones y encabezados sin coincidencias.
4. Probar nombres/descripciones con `ñ`, comillas, `;`, saltos de línea y
   `=1+1` precedido por espacios: el último debe mostrarse como texto.
5. Interrumpir la conexión, descargar y reintentar tras recuperarla. Revisar
   que el botón bloquee clics repetidos y que la pantalla funcione en celular.
6. Entrar como lector y comprobar que no aparece el botón y que el endpoint
   devuelve `403`; comprobar con otra organización que solo obtiene sus datos.

No se implementan PDF, Excel nativo ni auditoría de descargas. No requiere
migración ni modifica recursos, evaluaciones o eventos de auditoría.
