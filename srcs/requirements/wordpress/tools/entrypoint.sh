#!/bin/sh
set -e

# Load passwords only from mounted Docker secret files.
DB_PASS=$(cat /run/secrets/db_password)
. /run/secrets/credentials

# Finite retry: the subject forbids infinite loops, and restart: always handles later retries.
i=0
until mariadb -h mariadb -u"$MYSQL_USER" -p"$DB_PASS" -e 'SELECT 1' >/dev/null 2>&1; do
	i=$((i + 1))
	if [ "$i" -ge 30 ]; then
		echo "MariaDB did not become ready" >&2
		exit 1
	fi
	sleep 2
done

# Keep all WordPress state on the persistent named volume.
cd /var/www/html

# Use the frozen ZIP release so long core paths are not truncated by the tar extractor.
[ -f wp-load.php ] || wp core download https://wordpress.org/wordpress-7.1.zip --allow-root

# Generate configuration once while keeping the database password out of the image.
[ -f wp-config.php ] || wp config create \
	--dbname="$MYSQL_DATABASE" \
	--dbuser="$MYSQL_USER" \
	--dbpass="$DB_PASS" \
	--dbhost=mariadb:3306 \
	--allow-root

# Install the site idempotently with the required non-generic administrator name.
wp core is-installed --allow-root || wp core install \
	--url="https://$DOMAIN_NAME" \
	--title="$WP_TITLE" \
	--admin_user="$WP_ADMIN_USER" \
	--admin_password="$WP_ADMIN_PASSWORD" \
	--admin_email="$WP_ADMIN_EMAIL" \
	--skip-email \
	--allow-root

# Ensure the second, non-administrator account exists.
wp user get "$WP_USER" --allow-root >/dev/null 2>&1 || wp user create \
	"$WP_USER" \
	"$WP_USER_EMAIL" \
	--role=author \
	--user_pass="$WP_USER_PASSWORD" \
	--allow-root

# Give PHP-FPM ownership after any root-run wp-cli changes.
chown -R www-data:www-data /var/www/html

# Debian's PHP-FPM package expects its runtime directory to exist.
mkdir -p /run/php

# Replace the shell so PHP-FPM is the foreground PID 1 process.
exec /usr/sbin/php-fpm8.2 -F
