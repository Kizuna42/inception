FROM debian:12

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        php8.2-fpm \
        php8.2-mysql \
        php8.2-cli \
        php8.2-curl \
        php8.2-xml \
        php8.2-mbstring \
        php8.2-zip \
        php8.2-gd \
        php-redis \
        mariadb-client \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://github.com/wp-cli/wp-cli/releases/download/v2.12.0/wp-cli-2.12.0.phar -o /usr/local/bin/wp \
    && chmod +x /usr/local/bin/wp \
    && test "$(/usr/local/bin/wp cli version --allow-root)" = "WP-CLI 2.12.0"

COPY conf/www.conf /etc/php/8.2/fpm/pool.d/www.conf
COPY tools/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 9000

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
