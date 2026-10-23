# Vigilante externo MyCode

Comprueba MyCode y Daroka desde los ejecutores de GitHub, aunque el servidor de
las webs esté apagado o sin Internet. No ejecuta comandos en ese servidor.

- Programado cada cinco minutos, con tres intentos por web; confirma caídas tras dos ejecuciones consecutivas fallidas.
- Envía a Telegram las caídas y recuperaciones en español, solo al privado del propietario, una vez por cambio confirmado.
- No diagnostica apagados ni reinicios a partir de fallos HTTP. El bot local detecta los reinicios mediante el identificador de arranque.
- El estado y los avisos pendientes se conservan en `.monitor-state.json`.
- Una actualización diaria del estado mantiene actividad en el repositorio.
- No utiliza `getUpdates` ni webhooks: funciona junto al bot de consultas.

Los secretos `TELEGRAM_BOT_TOKEN` y `TELEGRAM_TARGETS_JSON` se configuran en
GitHub Actions. Nunca deben añadirse al código, al estado o a los logs.
El repositorio público contiene únicamente código y disponibilidad de webs
públicas; no contiene datos internos del servidor ni identificadores de chats.

Se utilizan ejecutores estándar de GitHub. En repositorios públicos son
gratuitos. Los trabajos programados pueden sufrir retrasos o ser omitidos:
no se garantiza un aviso exactamente a los cinco minutos.

Referencias: [programación de Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
y [uso gratuito](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

## Comprobaciones funcionales y confirmación geográfica

MyCode: comprobar el contenido de la portada y la validación de una petición
vacía al formulario (no se envía correo ni se prueban entregas de correo).
Daroka: comprobar portada, carta y /api/health, que lee las tablas públicas
necesarias para la carta sin devolver datos ni escribir en ellas.

Ante un fallo repetido se pide una comprobación HTTP a Globalping desde
Alemania y Estados Unidos. Se requieren errores concluyentes de ambos países;
un éxito, resultados ausentes, bloqueos 401/403, límites 429 o discrepancias
no confirman una caída. La API y las sondas son dependencias externas: si no
aportan evidencia suficiente se conserva el estado anterior, sin inventar una
caída ni una recuperación. Los resultados se limitan a los dominios públicos.
Contrato: https://github.com/jsdelivr/globalping/blob/master/public/v1/spec.yaml

Se exigen dos ejecuciones fallidas separadas entre uno y treinta minutos.
Un retraso mayor empieza una confirmación nueva. Los avisos usan nombres
comprensibles, hora del primer fallo y ubicaciones que lo confirman.
