FROM nginx:1.29 AS nginx
COPY nginx.conf /etc/nginx/nginx.conf

FROM grafana/loki:3.7.6 AS loki
COPY config/loki/loki.yaml /etc/loki/local-config.yaml

FROM grafana/alloy:v1.19.0 AS alloy
COPY config/alloy/config.alloy /etc/alloy/config.alloy

FROM grafana/grafana:13.2.0 AS grafana
COPY config/grafana/provisioning /etc/grafana/provisioning
COPY config/grafana/dashboards /etc/grafana/dashboards
