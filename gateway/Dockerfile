FROM nginx:1.29-alpine

COPY nginx.conf /etc/nginx/nginx.conf
COPY templates/ /etc/nginx/templates/
COPY snippets/ /etc/nginx/snippets/
COPY stream.d/ /etc/nginx/stream.d/
COPY routes.d/ /etc/nginx/routes.d/
ENV NGINX_ENVSUBST_FILTER=^NGINX_
ENV NGINX_BACKEND_UPSTREAM=backend:8000
ENV NGINX_FRONTEND_UPSTREAM=frontend:80
ENV NGINX_MINIO_S3_UPSTREAM=minio:9000
ENV NGINX_MINIO_CONSOLE_UPSTREAM=minio:9001
EXPOSE 80 9000 9001

CMD ["nginx", "-g", "daemon off;"]
