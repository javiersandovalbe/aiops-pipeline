# Pipeline AIOps sobre Prometheus + Alertmanager

Implementa las etapas 2 a 5 del informe (agregación, detección con baseline estacional, deduplicación y correlación)
con Prometheus y Alertmanager. La etapa 6 (contexto enriquecido) queda en las anotaciones y plantillas.

## Estructura
- `prometheus/prometheus.yml`: scrape, evaluación cada 1 min y conexión con Alertmanager.
- `prometheus/rules/aiops_latency.yml`: reglas de grabación (p95, baseline por hora-de-semana, z-score) y alertas.
- `prometheus/tests/aiops_latency_test.yml`: pruebas unitarias con `promtool test rules`.
- `alertmanager/alertmanager.yml`: agrupación, inhibición por causa raíz, silencio por mantenimiento y receptores.
- `alertmanager/secrets/`: archivos con el webhook de Slack y la clave de PagerDuty (valores de ejemplo, reemplázalos).
- `tools/correlate.py`: motor opcional de deduplicación y correlación por topología (análisis offline o webhook propio).

## Requisitos previos (sin esto las reglas no disparan)
1. **Nombres de métrica.** Las reglas usan `http_server_duration_seconds_bucket` y `_count`. Si tu métrica se llama distinto
   (por ejemplo `http_request_duration_seconds_*`, `nginx_ingress_controller_request_duration_seconds_*`), reemplázalo en
   `aiops_latency.yml` y en las pruebas. Si tu histograma está en milisegundos, ajusta también el piso `0.05` del z-score y el umbral `rate(...) > 1`.
2. **Labels `service` y `env` en todas las series** (ver ejemplos en `prometheus.yml`).
3. **Retención de al menos 35 días** (el compose usa 45 d). Con la retención por defecto (15 d) el baseline nunca se forma.
4. **Historia:** las alertas de latencia solo se activan con 3 o más semanas de datos (`seasonal_weeks >= 3`).
   Para empezar antes, baja ese número en las dos alertas o reconstruye la historia con
   `promtool tsdb create-blocks-from rules`.

## Validar antes de levantar (sin instalar nada, con Docker)
```bash
docker run --rm --entrypoint promtool -v "$PWD/prometheus:/etc/prometheus" prom/prometheus:v3.5.0 \
  check config /etc/prometheus/prometheus.yml
docker run --rm --entrypoint promtool -v "$PWD/prometheus:/etc/prometheus" prom/prometheus:v3.5.0 \
  test rules /etc/prometheus/tests/aiops_latency_test.yml
docker run --rm --entrypoint amtool -v "$PWD/alertmanager:/etc/alertmanager" prom/alertmanager:v0.28.1 \
  check-config /etc/alertmanager/alertmanager.yml
```

## Levantar
```bash
docker compose up -d
# Prometheus: http://localhost:9090  (Alerts, Rules)    Alertmanager: http://localhost:9093
curl -X POST http://localhost:9090/-/reload    # tras editar reglas
```

## Marca de deploy
Las reglas esperan la métrica `deploy_window_active{service,env}` = 1 durante el despliegue y 30 min después.
Con Pushgateway (descomenta el job `pushgateway` en `prometheus.yml`), el pipeline de CI/CD publica:
```bash
echo "deploy_window_active 1" | curl --data-binary @- http://pushgateway:9091/metrics/job/deploy/service/checkout/env/prod
# 30 minutos después (tarea programada del CI):
echo "deploy_window_active 0" | curl --data-binary @- http://pushgateway:9091/metrics/job/deploy/service/checkout/env/prod
```
Si la métrica no existe, la regla simplemente no excluye ventanas de deploy y `PostDeployRegression` no se dispara.

## Modo sombra recomendado (4 semanas)
Antes de cambiar el paging, deja `receivers` apuntando a un canal de Slack de pruebas y compara cada día las notificaciones
nuevas con las del sistema actual (volumen, falsos positivos y recall de incidentes reales).

## Limitaciones conocidas
- `ServiceDown` usa `sum by (service, env) (up) == 0`: si el servicio desaparece del descubrimiento (no existe la serie `up`), no alerta.
  Complementa con una regla `absent()` si lo necesitas.
- Las pruebas y las reglas se validaron solo en sintaxis (YAML y PromQL). Ejecuta los tres comandos de arriba antes de usarlo en producción.
- Los umbrales (z > 3, 1,3× la media, `for: 10m`) son valores iniciales de diseño; ajústalos con tus datos en modo sombra.
