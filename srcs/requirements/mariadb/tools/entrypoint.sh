#!/bin/sh
set -e

# Read database credentials from Docker secrets instead of the image or environment.
DB_ROOT_PASS=$(cat /run/secrets/db_root_password)
DB_PASS=$(cat /run/secrets/db_password)
PROVISION_MARKER=/var/lib/mysql/.inception-provisioned

# Prepare the runtime socket directory with MariaDB ownership.
mkdir -p /run/mysqld
chown mysql:mysql /run/mysqld

if [ ! -d /var/lib/mysql/mysql ]; then
	# Initialize only an empty persistent data directory.
	chown -R mysql:mysql /var/lib/mysql
	mariadb-install-db --user=mysql --datadir=/var/lib/mysql --skip-test-db
fi

if [ ! -f "$PROVISION_MARKER" ]; then
	# Bootstrap directly in the foreground without exposing or backgrounding a server.
	mariadbd --user=mysql --bootstrap --skip-networking <<-SQL
		FLUSH PRIVILEGES;
		CREATE DATABASE IF NOT EXISTS \`${MYSQL_DATABASE}\`;
		CREATE USER IF NOT EXISTS '${MYSQL_USER}'@'%' IDENTIFIED BY '${DB_PASS}';
		ALTER USER '${MYSQL_USER}'@'%' IDENTIFIED BY '${DB_PASS}';
		GRANT ALL PRIVILEGES ON \`${MYSQL_DATABASE}\`.* TO '${MYSQL_USER}'@'%';
		ALTER USER 'root'@'localhost' IDENTIFIED VIA unix_socket OR mysql_native_password USING PASSWORD('${DB_ROOT_PASS}');
		FLUSH PRIVILEGES;
	SQL

	touch "$PROVISION_MARKER"
fi

# Replace the shell so MariaDB receives signals directly as PID 1.
exec mariadbd --user=mysql
