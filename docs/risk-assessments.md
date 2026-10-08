# Evaluaciones de riesgo residual

Las evaluaciones residuales son estimaciones manuales y forman un historial.
No sobrescriben la evaluación original del riesgo. Vincular controles o cambiar
su estado a implementado no crea evaluaciones ni modifica valores automáticamente.
Un residual puede ser mayor, igual o menor que el original.

## API

| Método | Ruta | Permiso y respuesta |
| --- | --- | --- |
| POST | `/risks/{risk_id}/assessments` | Administrador/analista; devuelve la evaluación con 201 |
| GET | `/risks/{risk_id}/assessments` | Todos los roles autenticados; lista de reciente a antigua |

El cuerpo POST requiere exactamente estos campos:

```json
{"residual_probability": 2, "residual_impact": 3, "justification": "Estimación manual documentada"}
```

Probabilidad e impacto son enteros estrictos entre 1 y 5. Booleanos, strings,
floats (incluso 1.0) y null se rechazan. Justificación es un string obligatorio,
recortado, de 1 a 5000 caracteres. Campos desconocidos, cuerpos vacíos/incompletos
o inválidos reciben 422. No se aceptan IDs, organización, evaluador, fechas,
valores originales, puntajes ni niveles suministrados por el cliente.

Actor y organización provienen de la sesión. Riesgo inexistente/ajeno devuelve
404. Sin sesión: 401; lector en POST o CSRF inválido: 403. No hay endpoints de
edición o eliminación de evaluaciones. Cada POST exitoso añade una evaluación,
incluso si sus valores coinciden con otra: es una nueva estimación documentada.

La respuesta incluye id, risk_id, evaluator_id, evaluator_name (nombre histórico),
created_at (UTC), residual_probability, residual_impact, residual_score,
residual_level, justification, original_probability, original_impact,
original_score y original_level. No incluye organización ni datos privados de
la cuenta. GET devuelve [] si no hay evaluaciones y usa `created_at DESC, id DESC`.

Puntajes: probabilidad × impacto; niveles con la misma matriz del riesgo original:
bajo 1–4, medio 5–9, alto 10–16 y crítico 17–25. Al evaluar se guarda una
instantánea de probabilidad, impacto y puntaje originales, leída bajo bloqueo de
escritura. Modificar el riesgo después no altera esa comparación histórica.

## Migración y auditoría

Migración 011 crea `risk_assessments`, un índice por organización/riesgo/fecha/ID
y una clave única usuario/organización. Claves foráneas compuestas vinculan el
riesgo y el evaluador a la misma organización. La base rechaza relaciones ajenas,
cambios de organización que las invaliden, valores numéricos fuera de rango,
justificaciones vacías/largas y puntajes originales inconsistentes con su producto.
El evaluador conserva su nombre histórico aunque cambie su cuenta. Las claves
foráneas no borran evaluaciones en cascada.

Se guardan todos los registros nuevos sin reconstruir evaluaciones anteriores.
La migración también permite la acción de auditoría `assessed`, siguiendo el
procedimiento de migración 010 para conservar todos los eventos, IDs, índices
y máximos de secuencia al ampliar el CHECK de acciones. Otras tablas y datos
existentes no se modifican.

POST usa BEGIN IMMEDIATE y una sola conexión/transacción para riesgo original,
evaluación y auditoría. Un fallo de inserción del evento revierte evaluación y
secuencias. El evento referencia el riesgo y contiene solo assessment_id,
original_probability, original_impact, original_score, residual_probability,
residual_impact y residual_score. No copia justificación, título, descripción,
contraseñas ni tokens. Las solicitudes fallidas no generan eventos. La auditoría
sigue siendo local, sin resistencia garantizada ante acceso directo a SQLite.

## Interfaz y dashboard

El detalle distingue **Evaluación original (actual)**, **Última evaluación residual**
e historial consultable. Cada entrada muestra evaluador, fecha local, valores,
puntaje/nivel, justificación y diferencia en puntos respecto a su instantánea
original. Sin registros muestra **Sin evaluación residual**. Administradores y
analistas disponen de formulario; lectores consultan el historial. La interfaz
conserva CSRF, texto seguro, carga/error/reintento, bloqueo de envíos repetidos
y diseño adaptable. Respuestas de otro riesgo o sesión se descartan.

El dashboard mantiene totales por nivel y prioridades basados únicamente en la
**evaluación original actual** (`risks.probability * risks.impact`). Una evaluación
residual, incluso más alta, no cambia tarjetas ni prioridades del resumen.

## Verificación

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\backend\.venv\Scripts\python.exe backend\tests\check_browser.py
```

Las pruebas cubren las 25 combinaciones, límites, booleanos y otros valores
inválidos, justificaciones y campos protegidos, permisos/CSRF/aislamiento,
historial y desempate, instantáneas después de editar el original, evaluador
histórico, persistencia, claves foráneas y migración con conservación de datos.
Se fuerza un fallo de auditoría y se compara la base completa antes/después.
Chrome comprueba historial, valores mayores/menores, instantáneas, original y
dashboard conservados, justificación segura, fechas locales, errores/reintento,
envíos repetidos, lector y tamaños de escritorio/celular.

Comprobación manual:

1. Ingresar como administrador o analista y abrir un riesgo en Gestión. Verificar
   la sección original y Sin evaluación residual.
2. Registrar una evaluación con justificación. Verificar nombre, fecha local,
   puntaje/nivel y comparación con la instantánea original. Registrar otra con
   valores mayores: debe aceptarse y aparecer primera en el historial.
3. Editar probabilidad/impacto originales y volver al historial: las comparaciones
   anteriores deben conservar sus valores. Registrar otra evaluación y comprobar
   que su instantánea usa los valores originales nuevos.
4. Vincular o implementar controles: no debe cambiar el original ni crear otra
   evaluación. Volver a Resumen y confirmar que usa el puntaje original.
5. Como lector consultar el historial sin formulario. Probar otra organización,
   ancho de celular, texto con caracteres especiales, red desconectada y Reintentar.
6. Actualizar Auditoría como administrador y verificar el evento de evaluación,
   con IDs/números y sin justificación. Reiniciar para comprobar persistencia.
