# syntax=docker/dockerfile:1
#
# Two stages: build the SPA with node, then serve the static output from nginx.
# The node toolchain does not survive into the runtime image.

FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY . .

# Empty on purpose. api/client.ts builds request URLs as `${BASE}${path}` where
# every path already starts with /api, so an empty base makes them same-origin
# and nginx proxies /api to the backend. Baking a hostname in here would tie the
# image to one deployment.
ENV VITE_API_BASE=""

RUN npm run build


FROM nginx:1.27-alpine AS runtime

# The `map` directive has to live at http scope, not inside a server block.
COPY nginx-upgrade.conf /etc/nginx/conf.d/00-upgrade.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
