FROM debian:12

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends mariadb-server mariadb-client \
    && rm -rf /var/lib/apt/lists/*

COPY conf/99-inception.cnf /etc/mysql/mariadb.conf.d/99-inception.cnf
COPY tools/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 3306

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
