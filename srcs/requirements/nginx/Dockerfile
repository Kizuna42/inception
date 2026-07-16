FROM debian:12

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx openssl \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default \
    && mkdir -p /etc/nginx/ssl \
    && openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
        -keyout /etc/nginx/ssl/inception.key \
        -out /etc/nginx/ssl/inception.crt \
        -subj "/C=JP/ST=Tokyo/O=42Tokyo/CN=kishino.42.fr" \
        -addext "subjectAltName=DNS:kishino.42.fr"

COPY conf/nginx.conf /etc/nginx/conf.d/inception.conf

EXPOSE 443

CMD ["nginx", "-g", "daemon off;"]
