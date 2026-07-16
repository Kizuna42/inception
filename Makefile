DATA_PATH = /home/kishino/data
COMPOSE = docker compose -f srcs/docker-compose.yml

.PHONY: all up down clean fclean re logs ps dirs secrets

all: up

# Build and start the mandatory stack.
up: dirs secrets
	$(COMPOSE) up -d --build

# Stop containers while preserving images and data.
down:
	$(COMPOSE) down

# Remove locally built images while preserving persistent data.
clean:
	$(COMPOSE) down --rmi all

# Remove containers, images, volumes, and the explicitly listed data directories.
fclean:
	$(COMPOSE) down -v --rmi all
	sudo rm -rf $(DATA_PATH)/wordpress $(DATA_PATH)/mariadb $(DATA_PATH)/backup

# Recreate the complete stack from a clean state.
re: fclean all

# Follow logs from every service.
logs:
	$(COMPOSE) logs -f

# Show the current Compose service state.
ps:
	$(COMPOSE) ps

# Create host bind directories, escalating only when normal permissions fail.
dirs:
	@mkdir -p $(DATA_PATH)/wordpress $(DATA_PATH)/mariadb $(DATA_PATH)/backup 2>/dev/null || { \
		sudo mkdir -p $(DATA_PATH)/wordpress $(DATA_PATH)/mariadb $(DATA_PATH)/backup && \
		sudo chown -R "$$(id -u):$$(id -g)" $(DATA_PATH)/wordpress $(DATA_PATH)/mariadb $(DATA_PATH)/backup; \
	}

# Generate missing file-based secrets without overwriting existing credentials.
secrets:
	@mkdir -p secrets
	@set -e; umask 077; \
	if [ ! -f secrets/db_root_password.txt ]; then \
		value=$$(openssl rand -hex 16); \
		printf '%s' "$$value" > secrets/db_root_password.txt; \
	fi; \
	chmod 600 secrets/db_root_password.txt; \
	if [ ! -f secrets/db_password.txt ]; then \
		value=$$(openssl rand -hex 16); \
		printf '%s' "$$value" > secrets/db_password.txt; \
	fi; \
	chmod 600 secrets/db_password.txt; \
	if [ ! -f secrets/credentials.txt ]; then \
		wp_admin_password=$$(openssl rand -hex 16); \
		wp_user_password=$$(openssl rand -hex 16); \
		ftp_password=$$(openssl rand -hex 16); \
		printf '%s\n' \
			"WP_ADMIN_PASSWORD=$$wp_admin_password" \
			"WP_USER_PASSWORD=$$wp_user_password" \
			"FTP_PASSWORD=$$ftp_password" > secrets/credentials.txt; \
	fi; \
	chmod 600 secrets/credentials.txt
