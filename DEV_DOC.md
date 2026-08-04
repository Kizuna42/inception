# Inception — Developer Documentation

This document describes how to set up, build, operate, and inspect the
Inception stack from a developer's perspective. See `README.md` for the
project rationale and design comparisons, and `USER_DOC.md` for end-user
instructions.

## Setting up the environment from scratch

### Prerequisites

- A Linux virtual machine (this project targets a UTM-hosted Ubuntu VM).
- Docker Engine and the `docker compose` plugin.
- `make`, `git`, and `openssl`.

### Repository layout

```
inception/
├── Makefile
├── secrets/                        # generated locally, git-ignored
│   ├── credentials.txt
│   ├── db_password.txt
│   └── db_root_password.txt
└── srcs/
    ├── .env
    ├── docker-compose.yml
    └── requirements/
        ├── mariadb/
        │   ├── Dockerfile
        │   ├── conf/99-inception.cnf
        │   └── tools/entrypoint.sh
        ├── nginx/
        │   ├── Dockerfile
        │   └── conf/nginx.conf
        └── wordpress/
            ├── Dockerfile
            ├── conf/www.conf
            └── tools/entrypoint.sh
```

### `.env` configuration

`srcs/.env` holds non-sensitive configuration read by `docker-compose.yml` and
passed into containers via `environment:`:

| Variable          | Purpose                                              |
|--------------------|-------------------------------------------------------|
| `DOMAIN_NAME`       | Site domain (`kishino.42.fr`) used by WordPress; it must match nginx's configured `server_name` and certificate |
| `DATA_PATH`         | Host path for persistent data (`/home/kishino/data`), used as the volumes' bind `device` |
| `MYSQL_DATABASE`    | Name of the WordPress database                        |
| `MYSQL_USER`        | Database user WordPress connects as                   |
| `WP_TITLE`          | WordPress site title                                   |
| `WP_ADMIN_USER`     | WordPress administrator username (`kishino`, deliberately not containing "admin") |
| `WP_ADMIN_EMAIL`    | WordPress administrator email                          |
| `WP_USER`           | Second, non-administrator WordPress username (`guest`) |
| `WP_USER_EMAIL`     | Second WordPress user's email                           |

No password lives in `.env`; all passwords come from `secrets/`.

### Secrets

`make secrets` (invoked automatically by `make`/`make up`) creates, if
missing, three `chmod 600` files under `secrets/` using `openssl rand -hex 16`:
`db_root_password.txt`, `db_password.txt`, and `credentials.txt` (which holds
`WP_ADMIN_PASSWORD` and `WP_USER_PASSWORD`). Existing files are never
overwritten. These values are consumed during first-boot provisioning; replacing
a secret without also updating the already-persisted MariaDB or WordPress account
creates a credential mismatch. Rotate credentials through the corresponding
service, or reset the data and secrets together. `secrets/` is listed in
`.gitignore`.

### `/etc/hosts`

```sh
grep -q 'kishino\.42\.fr' /etc/hosts || \
  echo "127.0.0.1 kishino.42.fr" | sudo tee -a /etc/hosts
```

is required so that the VM resolves the configured domain to itself. For a
browser running on the host machine, add the entry on the host and use the VM's
IPv4 address instead of `127.0.0.1`. On a cloud-init image with
`manage_etc_hosts: true`, either re-run the command after a reboot or persist the
entry through the cloud-init hosts template.

## Build and startup flow

`Makefile` wraps `docker compose -f srcs/docker-compose.yml`:

| Target        | Runs                                                                                  |
|----------------|------------------------------------------------------------------------------------------|
| `make` / `make up` | `dirs`, `secrets`, then `docker compose -f srcs/docker-compose.yml up -d --build`   |
| `make down`    | `docker compose -f srcs/docker-compose.yml down`                                       |
| `make clean`   | `docker compose -f srcs/docker-compose.yml down --rmi all`                             |
| `make fclean`  | `docker compose -f srcs/docker-compose.yml down -v --rmi all`, then removes `$(DATA_PATH)/wordpress` and `$(DATA_PATH)/mariadb` |
| `make re`      | `fclean` then `up` (full rebuild from a clean state)                                   |
| `make logs`    | `docker compose -f srcs/docker-compose.yml logs -f`                                    |
| `make ps`      | `docker compose -f srcs/docker-compose.yml ps`                                         |
| `make dirs`    | Creates `$(DATA_PATH)/wordpress` and `$(DATA_PATH)/mariadb` on the host (elevating with `sudo` only if a plain `mkdir` fails) |
| `make secrets` | Generates the three files under `secrets/` described above, without overwriting existing ones |

`docker-compose.yml` (in `srcs/`) declares the `inception` bridge network, the
three services (each with an explicit `image:` tag, `restart: always`, and
`depends_on` — WordPress waits for MariaDB's `service_healthy`, nginx waits
for WordPress's `service_started`), the two named volumes, and the three
secrets sourced from files in `../secrets/`.

## Container and volume management cheatsheet

Rebuild and restart a single service without touching the others:

```sh
docker compose -f srcs/docker-compose.yml up -d --build wordpress
```

Open a shell inside a running container:

```sh
docker exec -it wordpress sh
docker exec -it nginx sh
docker exec -it mariadb sh
```

Connect to the database from inside the `mariadb` container:

```sh
docker exec -it mariadb sh -c 'mariadb -u root -p"$(cat /run/secrets/db_root_password)"'
```

or, as the application user, from the `wordpress` container:

```sh
docker exec -it wordpress sh -c \
  'mariadb -h mariadb -u"$MYSQL_USER" -p"$(cat /run/secrets/db_password)" "$MYSQL_DATABASE"'
```

The inner double quotes are intentionally not backslash-escaped: they group the
expanded values inside the single-quoted `sh -c` script without becoming literal
characters in the MariaDB username, password, or database arguments.

Inspect logs:

```sh
docker logs -f mariadb
docker logs -f wordpress
docker logs -f nginx
```

Inspect volumes and their backing host path:

```sh
docker volume ls
docker volume inspect mariadb_data
docker volume inspect wordpress_data
```

Run `wp-cli` inside the WordPress container (e.g. to list users or plugins):

```sh
docker exec -it -w /var/www/html wordpress wp user list --allow-root
```

## Data persistence and container initialization

### Storage layout

`mariadb_data` and `wordpress_data` are declared as Docker named volumes with
`driver: local` and `driver_opts: {type: none, o: bind, device: ...}`, which
makes them first-class named volumes (visible via `docker volume ls`) while
physically backing them onto the host paths under `${DATA_PATH}`:

- `${DATA_PATH}/mariadb` ↔ `mariadb_data` ↔ `/var/lib/mysql` in the `mariadb` container
- `${DATA_PATH}/wordpress` ↔ `wordpress_data` ↔ `/var/www/html` in both the `wordpress` and `nginx` containers (the latter mounts it read-only, so it can serve static assets directly)

`make down` leaves these directories and volumes untouched — data survives a
stop/start cycle. `make fclean` removes both the Docker volumes and the host
directories, so the next `make` starts from an empty state.

### Initialization flow (first boot on an empty volume)

**MariaDB entrypoint** (`srcs/requirements/mariadb/tools/entrypoint.sh`):

1. If `/var/lib/mysql/mysql` does not exist yet, runs `mariadb-install-db` to
   initialize the data directory.
2. If a `.inception-provisioned` marker file is absent, runs `mariadbd` once in
   foreground bootstrap mode with networking disabled (`--bootstrap
   --skip-networking`). The bootstrap SQL creates the WordPress database and
   application user and configures root authentication from the mounted
   secrets. The script then writes the marker so this step is skipped on
   subsequent starts. No server process is backgrounded during provisioning.
3. Finally `exec`s the real `mariadbd` process as PID 1.

**WordPress entrypoint** (`srcs/requirements/wordpress/tools/entrypoint.sh`):

1. Waits (bounded retries) until it can reach MariaDB with the application
   credentials.
2. Downloads WordPress core into `/var/www/html` with `wp core download` only
   if `wp-load.php` is not already present (i.e. only on an empty volume).
3. Creates `wp-config.php` with `wp config create` only if it does not exist
   yet.
4. Runs `wp core install` only if `wp core is-installed` reports the site is
   not yet installed, creating the administrator account (`WP_ADMIN_USER`)
   with the password from `secrets/credentials.txt`.
5. Creates the second account (`WP_USER`, role `author`) only if it does not
   already exist.
6. Fixes ownership (`www-data:www-data`) on `/var/www/html`, then `exec`s
   `php-fpm8.2 -F` as PID 1.

Because every step is guarded by an existence/state check, restarting the
containers (`make down` followed by `make`) re-runs the same entrypoints
without re-downloading, reinstalling, or duplicating data — the scripts are
idempotent with respect to the persisted volumes.
