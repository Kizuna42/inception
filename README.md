*This project has been created as part of the 42 curriculum by kishino.*

# Inception

## Description

Inception is a system administration project that builds a small, production-shaped
web infrastructure entirely with Docker. The mandatory deliverable is a three-service
stack — an nginx reverse proxy, a WordPress site running on PHP-FPM, and a MariaDB
database — each running in its own container, built from a custom `Dockerfile`
written from scratch (no ready-made service images), and orchestrated with Docker
Compose. The exercise focuses on containerizing services correctly rather than on
application code: writing minimal, purpose-built images, isolating services on a
private network, persisting data outside the containers, and keeping secrets out of
the image and out of version control.

Only nginx is reachable from outside the stack, over TLS on port 443. WordPress
and MariaDB are only reachable from other containers on the internal Docker
network.

## Instructions

### Prerequisites

- A Linux virtual machine (this project targets a UTM-hosted Ubuntu VM).
- Docker Engine and the `docker compose` plugin.
- `make`, `git`, and `openssl`.

### Setup and build

```sh
git clone https://github.com/Kizuna42/inception.git
cd inception
grep -q 'kishino\.42\.fr' /etc/hosts || \
  echo "127.0.0.1 kishino.42.fr" | sudo tee -a /etc/hosts
make
```

`make` (equivalent to `make up`) creates the host data directories, generates the
Docker secrets used for database and WordPress passwords, then builds and starts
all three containers with `docker compose -f srcs/docker-compose.yml up -d --build`.
The hosts entry above assumes the browser runs inside the VM. When accessing the
site from the host machine, map `kishino.42.fr` to the VM's IPv4 address instead.

### Available `make` targets

| Target       | Effect                                                                 |
|--------------|-------------------------------------------------------------------------|
| `make` / `make up` | Prepare data directories and secrets, build images, start the stack |
| `make down`  | Stop and remove containers, keep images, volumes, and data             |
| `make clean` | `down` plus removal of the locally built images                        |
| `make fclean`| `clean` with volumes removed and the host data directories deleted     |
| `make re`    | `fclean` followed by `up`, i.e. a full rebuild from a clean state      |
| `make logs`  | Follow the logs of every service                                       |
| `make ps`    | Show the current state of the Compose services                        |

Once the stack is up, the site is reachable at `https://kishino.42.fr` and the
WordPress admin dashboard at `https://kishino.42.fr/wp-admin`. See `USER_DOC.md`
for end-user details and `DEV_DOC.md` for developer-facing operations.

## Resources

### Reference documentation

- Docker overview — https://docs.docker.com/get-started/overview/
- Compose file reference — https://docs.docker.com/reference/compose-file/
- Dockerfile best practices — https://docs.docker.com/build/building/best-practices/
- Using secrets with Compose — https://docs.docker.com/compose/how-tos/use-secrets/
- Docker networking — https://docs.docker.com/engine/network/
- Running multiple services / PID 1 in a container — https://docs.docker.com/engine/containers/multi-service_container/
- "Dumb-init: an init process for Docker" (the classic PID 1 / zombie-reaping problem) — https://engineeringblog.yelp.com/2016/01/dumb-init-an-init-process-for-docker.html
- nginx documentation — https://nginx.org/en/docs/
- WordPress developer resources — https://developer.wordpress.org/
- WP-CLI command reference — https://developer.wordpress.org/cli/commands/
- MariaDB Knowledge Base — https://mariadb.com/kb/en/documentation/
- Debian release cycle (stable/oldstable) — https://www.debian.org/releases/

### Use of AI assistance

AI assistants (Claude/Codex) were used as development and verification tools. The
author remains responsible for understanding, reviewing, and defending every
configuration and command in the project. AI assistance was used for:

- Reviewing the overall container/network/volume design against the subject
  requirements before writing any file.
- Drafting configuration snippets (Dockerfiles, `nginx.conf`, entrypoint scripts,
  `docker-compose.yml`) which were then read, adjusted, and tested by hand.
- Cross-checking the implementation against the subject text to catch missed
  mandatory requirements (e.g. TLS-only nginx, no `latest` tag, no
  infinite-loop/`tail -f`/`sleep infinity` hacks, non-`admin` admin username).
- Drafting and correcting `README.md`, `USER_DOC.md`, and `DEV_DOC.md`.
- Running repeatable static, container, TLS, persistence, crash-recovery, and
  browser checks on an isolated UTM validation VM.

The mandatory stack was validated in an isolated Docker environment. The checks
covered a fresh build and startup, HTTPS-only access, TLS 1.2/1.3, database
connectivity, the administrator and author accounts, administrator authentication,
named-volume persistence across `make down`/`make`, automatic recovery after
service exits, and rendering the site and login page in Chrome. These checks, plus
a full VM reboot, must still be repeated on the final evaluation VM.

## Project description

### How Docker is used, and what the sources contain

`srcs/docker-compose.yml` defines the three mandatory services, the `inception`
bridge network, the two named volumes, and the three file-based secrets. Each
service has its own build context under `srcs/requirements/<service>/`:

- `nginx/Dockerfile` — installs `nginx` and `openssl` on `debian:12`, generates a
  self-signed certificate at build time, and copies `conf/nginx.conf`, which
  restricts `ssl_protocols` to `TLSv1.2 TLSv1.3`, listens only on 443, serves
  WordPress's static files, and forwards `.php` requests to `wordpress:9000` over
  FastCGI.
- `wordpress/Dockerfile` — installs `php8.2-fpm` and the PHP extensions WordPress
  needs, plus `wp-cli` pinned to a fixed release, and copies `conf/www.conf`
  (PHP-FPM pool listening on `9000`) and `tools/entrypoint.sh`.
- `mariadb/Dockerfile` — installs `mariadb-server`, copies
  `conf/99-inception.cnf` (binds MariaDB on all interfaces, port 3306) and
  `tools/entrypoint.sh`.

Each entrypoint script performs idempotent, first-boot provisioning (creating the
database/user, downloading and configuring WordPress, creating the two WordPress
accounts) and then uses `exec` to replace itself with the real server process
(`mariadbd`, `php-fpm8.2 -F`), so that process becomes PID 1 and receives signals
directly instead of being hidden behind a shell.

### Key design decisions

- **`debian:12` (bookworm) as the base image.** At the time of writing, Debian 12
  is the penultimate stable release (the previous stable line, with Debian 13
  "trixie" as current stable), which matches the subject's requirement to use a
  penultimate stable Debian or Alpine image.
- **Dockerfiles written from scratch.** No `wordpress`, `nginx`, or `mariadb`
  Docker Hub image is used; each container is built by installing the relevant
  Debian package(s) directly, as required by the subject.
- **Idempotent entrypoints.** Every entrypoint checks for existing state (an
  initialized data directory, an existing `wp-config.php`, an already-installed
  WordPress site, an existing secondary user) before acting, so containers can be
  restarted or recreated without corrupting or duplicating data, and without ever
  relying on an infinite polling loop of unbounded length.
- **Docker secrets for every password.** No credential is baked into an image,
  written to `.env`, or passed as a plain `environment:` value.

### Virtual Machines vs Docker

A virtual machine virtualizes hardware and runs a full guest operating system
(its own kernel) on top of a hypervisor, giving strong isolation at the cost of
larger images, slower boot times, and duplicated OS overhead per VM. Docker
containers share the host kernel and are isolated from each other with kernel
namespaces and cgroups, which makes them far lighter and faster to start, at the
cost of a shared kernel attack surface instead of full hardware-level isolation.
This project runs three containers *inside* one VM: the VM provides the required
sandboxed environment for the exercise, and Docker provides fine-grained,
per-service isolation and reproducibility on top of it.

### Secrets vs Environment Variables

Values set under Compose's `environment:` end up in the container's process
environment; they are visible with `docker inspect`, readable from
`/proc/<pid>/environ`, and easily leak into logs or child-process output. Docker
secrets are files that are mounted read-only at `/run/secrets/<name>` inside the
container, never baked into an image layer, and not exposed through
`docker inspect`'s environment listing. In this project, non-sensitive
configuration (domain, database name, usernames, titles) is passed via
`environment:`, while every password (`db_root_password`, `db_password`,
`credentials`) is defined under `secrets:` in `docker-compose.yml`, sourced from
files in the git-ignored `secrets/` directory, and read at container startup with
`cat /run/secrets/...`.

### Docker Network vs Host Network

Host networking removes the container's network namespace and binds it directly
to the host's interfaces and ports, so containers compete for the same port space
and can reach the entire host network with no isolation or built-in service
discovery. This project instead declares a dedicated bridge network, `inception`,
under `networks:`. Each container gets its own network namespace, containers
resolve each other by service name through Docker's embedded DNS (nginx reaches
`wordpress:9000`, WordPress reaches `mariadb:3306`), and only the nginx container
publishes a port to the host (`443:443`), keeping WordPress and MariaDB
unreachable from outside the Docker network entirely.

### Docker Volumes vs Bind Mounts

A plain bind mount (`host/path:/container/path`) points a container path directly
at an arbitrary host directory; Docker keeps no managed record of it, so it does
not satisfy the subject's requirement for *named* Docker volumes. A named volume
is a Docker-managed object (visible via `docker volume ls`, with its own
lifecycle), but by default its data lives inside Docker's internal storage area,
not at the specific host path (`/home/<login>/data/...`) the subject also
requires. This project reconciles both constraints by declaring named volumes
(`mariadb_data`, `wordpress_data`) with `driver: local` and
`driver_opts: {type: none, o: bind, device: ...}`: Docker treats them as
first-class named volumes for inspection and lifecycle management, while the
`bind` driver option makes their actual backing storage the required host
directories under `${DATA_PATH}` (`/home/kishino/data/mariadb` and
`/home/kishino/data/wordpress`).
