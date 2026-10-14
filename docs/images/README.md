# Capturas pendientes de SecurityOps

Este directorio es el destino de capturas reales de la demo. No se incluyen
imágenes: no hubo un navegador autenticado disponible durante la preparación.
No generar ilustraciones ni capturas simuladas para sustituirlas.

Seguir el [inicio con la base demo](../demo.md#iniciar-y-volver-a-la-base-habitual)
y el [guion](../demo.md#guion-de-seis-minutos). Antes de capturar, confirmar la
ruta demo en la terminal del servidor y la organización ficticia en la interfaz.
No capturar la base habitual. La autenticación escribe sesiones en la base demo;
requiere permitir esas escrituras antes de completar este paso.

| Archivo previsto | Pantalla y contenido |
| --- | --- |
| `resumen.png` | Resumen de Aurora: totales, pendientes y prioridades. |
| `incidente-detalle.png` | Gestión → Incidentes → Correo sospechoso en Nube Clara: responsable, activos, historial y nota ficticia. |
| `riesgo-residual.png` | Gestión → Riesgos → Acceso indebido al correo ficticio: original 20, residual 8 e historial desplegado con evaluación previa 12. |
| `auditoria.png` | Auditoría de Aurora: filtro de evaluación residual y riesgo, con actor, fecha y detalles del evento. |

Capturar exclusivamente el contenido de la aplicación ya autenticada, sin
pantalla de acceso, gestor de contraseñas, consola, herramientas de desarrollo,
cookies, tokens ni encabezados HTTP. Usar desplazamiento o varias capturas reales
si el historial no entra; no inventar ni alterar datos para acomodarlos.
Comprobar visualmente cada archivo antes de incorporarlo.

Cuando existan y estén revisadas las imágenes, reemplazar el aviso de pendientes
en el README raíz por enlaces relativos con esta sintaxis:

```markdown
![Resumen de Aurora con datos ficticios](docs/images/resumen.png)
![Detalle del incidente ficticio](docs/images/incidente-detalle.png)
![Riesgo y evaluaciones residuales ficticias](docs/images/riesgo-residual.png)
![Auditoría de la organización ficticia](docs/images/auditoria.png)
```

No insertar esos enlaces como imágenes hasta disponer de los archivos reales.
Al terminar, detener el servidor demo y restaurar la base habitual según el guion.
