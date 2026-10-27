# Caddy avec le module DuckDNS : obtient un VRAI certificat (Let's Encrypt) pour un nom en duckdns.org, même quand le NAS n'est pas joignable depuis Internet.
FROM caddy:2-builder AS build
RUN xcaddy build --with github.com/caddy-dns/duckdns

FROM caddy:2-alpine
COPY --from=build /usr/bin/caddy /usr/bin/caddy
