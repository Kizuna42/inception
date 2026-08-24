# Inception — User Documentation

This document explains how to use the Inception stack as an end user or site
administrator, without needing to know how it is built. For build/development
details, see `DEV_DOC.md`.

## What this stack provides

The project runs three services, each in its own container:

- **nginx** — the only service reachable from outside the machine. It serves
  the WordPress site over HTTPS (TLS 1.2/1.3) on port 443 and forwards page
  requests to WordPress internally.
- **WordPress** — the content management system that powers the website
  itself, including its admin dashboard.
- **MariaDB** — the database that stores WordPress's content (posts, users,
  settings). It is not reachable from outside the stack.

## Starting and stopping the project

Run all commands from the repository root.

```sh
make        # build (if needed) and start the whole stack
make down   # stop and remove the containers, keeping images and data
make fclean # also remove images, volumes, and all stored data
```

After `make down`, running `make` again brings the site back up with all
previous content intact. After `make fclean`, the next `make` starts from a
completely empty site (a fresh WordPress installation).

## Accessing the website and the admin dashboard

The site is served under the domain `kishino.42.fr`. Before the first access,
make sure your machine resolves that name to the VM:

```sh
grep -q 'kishino\.42\.fr' /etc/hosts || \
  echo "127.0.0.1 kishino.42.fr" | sudo tee -a /etc/hosts
```

This mapping is for a browser running inside the VM. If the browser runs on the
host machine, add the entry to the host's `/etc/hosts` and replace `127.0.0.1`
with the VM's IPv4 address.

Some cloud-init images regenerate `/etc/hosts` during reboot. If that happens,
re-run the command above or make the entry persistent through the VM's cloud-init
configuration before opening the site again.

Then open:

- **Website:** `https://kishino.42.fr`
- **Admin dashboard:** `https://kishino.42.fr/wp-admin`

Because the certificate is self-signed (generated locally when the nginx image
is built), the browser will show a security warning on the first visit. This
is expected — use the browser's "Advanced" (or equivalent) option and choose
to proceed to the site anyway.

Two WordPress accounts are provisioned automatically:

- An **administrator** account (username `kishino`) — has full access to the
  dashboard, including plugins, themes, and settings.
- A regular **author** account (username `guest`) — can create and edit
  content but does not have administrative privileges.

Log in with either account's username and its password from `secrets/credentials.txt`
(see below).

## Credentials: location and management

All passwords are generated automatically the first time the stack starts and
are kept in the `secrets/` directory at the repository root, never committed
to git:

| File                          | Contents                                              |
|--------------------------------|--------------------------------------------------------|
| `secrets/db_root_password.txt` | MariaDB root account password                         |
| `secrets/db_password.txt`      | Password for the WordPress database user               |
| `secrets/credentials.txt`      | `WP_ADMIN_PASSWORD` and `WP_USER_PASSWORD`, one per line |

To view the WordPress login passwords:

```sh
cat secrets/credentials.txt
```

The generated files are provisioning inputs, not an automatic password-rotation
mechanism. Deleting one while the existing WordPress and MariaDB data volumes are
still in use creates a mismatch between the stored account password and the new
file. For a deliberate full reset, first run `make fclean`, then remove the
credential file and let the Makefile recreate it:

```sh
make fclean
rm secrets/credentials.txt
make secrets
```

`make fclean` permanently removes the site data, so back up anything important
before using this reset flow. The `secrets/` directory is listed in `.gitignore`,
so none of these files are ever tracked or pushed by git.

## Checking that everything is running

```sh
make ps
```

shows the state of the three Compose services (`nginx`, `wordpress`,
`mariadb`). A healthy stack shows all three as `Up`; MariaDB and WordPress also
show `healthy` once their healthchecks pass.

Equivalently, `docker ps` lists the running containers, their images, and
their published ports (only `nginx` should show `443` mapped to the host).

To follow logs (useful when a container is stuck or restarting):

```sh
make logs             # all services
docker logs -f nginx  # a single service
```

To confirm the website itself responds:

```sh
curl -k https://kishino.42.fr
```

(`-k` skips certificate verification, which is expected with a self-signed
certificate.) A successful response returns the site's HTML.

Internally, MariaDB is checked with a Docker healthcheck (`mariadb-admin
ping`, run periodically inside the container). WordPress starts only after
MariaDB is healthy, and nginx starts only after WordPress's PHP-FPM port is
listening, so `make` does not report completion while the web backend is still
unready.
