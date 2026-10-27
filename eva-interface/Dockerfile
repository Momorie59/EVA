FROM node:20-slim AS build
WORKDIR /app
ARG VITE_EVA_WS_URL=
ARG VITE_EVA_CORE_URL=
ARG VITE_EVA_VOICE_URL=
# VITE_EVA_AUTH_TOKEN n'est PLUS intégré à l'interface : tout ce qui est dans le JavaScript est lisible par n'importe quel visiteur.
ARG VITE_EVA_AUTH_TOKEN=
ENV VITE_EVA_WS_URL=$VITE_EVA_WS_URL
ENV VITE_EVA_CORE_URL=$VITE_EVA_CORE_URL
ENV VITE_EVA_VOICE_URL=$VITE_EVA_VOICE_URL
COPY package.json ./
RUN npm install --legacy-peer-deps
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
