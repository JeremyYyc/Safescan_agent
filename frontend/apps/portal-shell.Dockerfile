FROM node:24-alpine AS build

WORKDIR /workspace
COPY package.json package-lock.json ./
RUN npm ci
COPY apps ./apps

ARG PORTAL_APP
ARG PORTAL_BASE
RUN npx vite build "apps/${PORTAL_APP}" --base="${PORTAL_BASE}" --outDir=/dist

FROM nginx:1.29-alpine
COPY apps/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
