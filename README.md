# Vigilante externo MyCode

Comprueba MyCode y Daroka desde los ejecutores de GitHub, aunque el servidor de
las webs esté apagado o sin Internet. No ejecuta comandos en ese servidor.

- Programado cada cinco minutos, con dos intentos por web y ejecución manual.
- Envía a Telegram las caídas y recuperaciones en español, conservando grupos y temas.
- Si ambas webs fallan, indica un posible apagado o fallo de Internet; no confunde esa sospecha con un diagnóstico confirmado.
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
