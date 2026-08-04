# Inception Defense Cheat Sheet

> 42 Inception の評価当日に、上から順に操作・説明するための実戦用資料。
> 正本は `inception.pdf` Version 5.3 と
> [42 EvalHub — Inception](https://www.42evalhub.com/common/inception)。
> この資料の基準スナップショットは 2026-08-02。

## 0. 最初に見るページ

### 評価停止条件

次のどれかがあれば、その場で修正せず評価が終了し得る。

- Git に credential、API key、password が追跡されている。
- ルートに `Makefile`、`srcs/`、`README.md`、`USER_DOC.md`、`DEV_DOC.md` がない。
- Compose に `network_mode: host`、`links:`、Docker 利用スクリプトに `--link` がある。
- network 定義がない。
- Dockerfile／entrypoint がプログラムをバックグラウンド実行する。
- `tail -f`、`sleep infinity`、無限ループでコンテナを維持する。
- service ごとの自作 Dockerfile、penultimate stable の Debian/Alpine、service と同名の image が成立しない。
- `make` で3サービスが起動しない。
- HTTP、TLS、WordPress、volume、database、persistence、設定変更のいずれかが機能しない。

### 90秒プレフライト

~~~sh
git status -sb
git remote get-url origin | sed -E 's#(https?://)[^/@]+@#\1[REDACTED]@#'
git ls-files secrets
git check-ignore -v secrets/db_root_password.txt \
  secrets/db_password.txt secrets/credentials.txt
find srcs/requirements -path '*/tools/*.sh' -exec sh -n {} \;
grep -RInE 'network_mode:[[:space:]]*host|links:|--link' \
  Makefile srcs || true
grep -RInE 'tail[[:space:]]+-f|sleep[[:space:]]+infinity|while[[:space:]]+true' \
  Makefile srcs || true
grep -RInE '[[:space:]]&[[:space:]]*($|#)' \
  srcs/requirements/*/tools || true
docker compose -f srcs/docker-compose.yml config --quiet
~~~

期待値:

- `git ls-files secrets` は出力なし。
- 禁止パターン3検査も出力なし。
- shell syntax と Compose config は終了コード0。
- `git status` の差分は、評価対象として提出した内容と一致する。

> [!CAUTION]
> EvalHub は評価開始時に全 container/image/volume/network を削除するコマンドを指定している。
> これは **専用の評価VMだけ** で実行する。共有Macや別プロジェクトが動くDocker環境では実行しない。

### 当日の順番

1. Git所有者・提出物・secret非追跡を確認。
2. 停止条件の静的検査。
3. `make` で fresh build。
4. `docker compose ps`、image、PID 1、network、volumeを確認。
5. HTTP拒否、HTTPS、TLS 1.2/1.3を確認。
6. WordPressの2ユーザー、コメント、管理画面編集を確認。
7. MariaDBへ接続し、DBが空でないことを確認。
8. `make down && make`、続いてVM再起動で永続化を確認。
9. reviewer指定の設定変更を行い、rebuild・restart・疎通確認。

## 1. アーキテクチャ

~~~mermaid
flowchart LR
    B["Browser<br/>https://kishino.42.fr:443"]

    subgraph H["Linux VM host"]
        HP["published port 443"]

        subgraph N["Docker bridge network: inception"]
            NX["nginx<br/>PID 1: nginx<br/>TLS 1.2/1.3"]
            WP["wordpress<br/>PID 1: php-fpm8.2 -F<br/>port 9000"]
            DB["mariadb<br/>PID 1: mariadbd<br/>port 3306"]
            NX -->|"FastCGI wordpress:9000"| WP
            WP -->|"Docker DNS mariadb:3306"| DB
        end

        WV["named volume: wordpress_data<br/>/home/kishino/data/wordpress"]
        DV["named volume: mariadb_data<br/>/home/kishino/data/mariadb"]
        S["Docker secrets<br/>/run/secrets/*"]

        HP --> NX
        WV -->|"rw"| WP
        WV -->|"ro"| NX
        DV -->|"rw"| DB
        S --> WP
        S --> DB
    end

    B --> HP
~~~

外部に publish されるのは nginx の443だけ。WordPressとMariaDBには `ports:` がなく、
`inception` network 上の service name をDocker DNSとして利用する。

## 2. コードの住所録

行番号は現在の目安。ずれたら右端の locator を使う。

| 確認対象 | パス・現在行 | locator |
|---|---|---|
| Compose 3 services | `srcs/docker-compose.yml:3-59` | `grep -nE '^  (mariadb|wordpress|nginx):' srcs/docker-compose.yml` |
| image名・restart・network | `srcs/docker-compose.yml:7-10,27-30,50-53` | `grep -nE 'image:|restart:|networks:' srcs/docker-compose.yml` |
| nginx公開ポート | `srcs/docker-compose.yml:54` | `grep -n 'ports:' srcs/docker-compose.yml` |
| volume mount | `srcs/docker-compose.yml:15-16,41-42,55-56` | `grep -nE 'mariadb_data|wordpress_data' srcs/docker-compose.yml` |
| named volume host path | `srcs/docker-compose.yml:66-81` | `grep -nE 'driver_opts|device:' srcs/docker-compose.yml` |
| Docker secrets | `srcs/docker-compose.yml:83-89` | `grep -nE '^secrets:|file:' srcs/docker-compose.yml` |
| Make entrypoint | `Makefile:6-10` | `grep -nE '^all:|^up:' Makefile` |
| 非破壊停止 | `Makefile:12-14` | `grep -nA2 '^down:' Makefile` |
| 破壊的clean | `Makefile:16-26` | `grep -nE '^clean:|^fclean:|^re:' Makefile` |
| secret生成・mode 600 | `Makefile:43-64` | `grep -nA22 '^secrets:' Makefile` |
| MariaDB image | `srcs/requirements/mariadb/Dockerfile` | `nl -ba srcs/requirements/mariadb/Dockerfile` |
| MariaDB port | `srcs/requirements/mariadb/conf/99-inception.cnf:2-4` | `grep -nE 'bind-address|port|skip-name' srcs/requirements/mariadb/conf/99-inception.cnf` |
| foreground bootstrap | `srcs/requirements/mariadb/tools/entrypoint.sh:19-31` | `grep -nE 'bootstrap|FLUSH|CREATE|GRANT|ALTER|PROVISION' srcs/requirements/mariadb/tools/entrypoint.sh` |
| MariaDB PID 1 | `srcs/requirements/mariadb/tools/entrypoint.sh:35` | `grep -n 'exec mariadbd' srcs/requirements/mariadb/tools/entrypoint.sh` |
| WordPress image | `srcs/requirements/wordpress/Dockerfile` | `nl -ba srcs/requirements/wordpress/Dockerfile` |
| PHP-FPM port | `srcs/requirements/wordpress/conf/www.conf:4` | `grep -n 'listen' srcs/requirements/wordpress/conf/www.conf` |
| WordPress初期化 | `srcs/requirements/wordpress/tools/entrypoint.sh:19-49` | `grep -nE 'wp core|wp config|wp user' srcs/requirements/wordpress/tools/entrypoint.sh` |
| PHP-FPM PID 1 | `srcs/requirements/wordpress/tools/entrypoint.sh:58` | `grep -n 'exec.*php-fpm' srcs/requirements/wordpress/tools/entrypoint.sh` |
| nginx image・証明書 | `srcs/requirements/nginx/Dockerfile:1-20` | `nl -ba srcs/requirements/nginx/Dockerfile` |
| nginx TLS・port | `srcs/requirements/nginx/conf/nginx.conf:2-8` | `grep -nE 'listen|server_name|ssl_' srcs/requirements/nginx/conf/nginx.conf` |
| FastCGI routing | `srcs/requirements/nginx/conf/nginx.conf:21-25` | `grep -nA5 'location.*php' srcs/requirements/nginx/conf/nginx.conf` |
| 非機密設定 | `srcs/.env` | `cut -d= -f1 srcs/.env` |
| secret除外 | `.gitignore:1-2` | `nl -ba .gitignore` |
| 設計説明 | `README.md` | `grep -n '^### ' README.md` |
| 利用者手順 | `USER_DOC.md` | `grep -n '^## ' USER_DOC.md` |
| 開発者手順 | `DEV_DOC.md` | `grep -n '^## ' DEV_DOC.md` |

## 3. EvalHub順の完全確認

### A. Preliminaries

#### Gitと提出物

~~~sh
git rev-parse --show-toplevel
git remote get-url origin | sed -E 's#(https?://)[^/@]+@#\1[REDACTED]@#'
git status -sb
find . -maxdepth 2 -type f -not -path './.git/*' | sort
~~~

説明:

- 評価対象はcloneされたGitリポジトリの内容だけ。
- 必須設定はルートの `srcs/` 内、操作入口はルートの `Makefile`。
- local secretは生成物であり、提出物ではない。

#### secretを値なしで証明

~~~sh
git ls-files secrets
git check-ignore -v secrets/db_root_password.txt \
  secrets/db_password.txt secrets/credentials.txt
stat -c '%a %n' secrets/*.txt
docker inspect wordpress --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | sed 's/=.*$/=[REDACTED]/' | grep -Ei 'PASS|PASSWORD|SECRET' || true
~~~

期待:

- Git追跡なし、`.gitignore` が適用。
- file modeは600。
- container environmentにpassword/secret名がない。
- 実値は画像共有、ログ、レビュー記録へ貼らない。WordPressログイン時だけローカルで確認する。

### B. General instructions / hard-stop scan

~~~sh
grep -nE 'network_mode|links:|networks:' srcs/docker-compose.yml
grep -RIn -- '--link' Makefile srcs || true
grep -RInE 'tail[[:space:]]+-f|sleep[[:space:]]+infinity|while[[:space:]]+true' \
  Makefile srcs || true
grep -RInE '[[:space:]]&[[:space:]]*($|#)' \
  srcs/requirements/*/tools || true
head -n1 srcs/requirements/*/Dockerfile
docker compose -f srcs/docker-compose.yml config --quiet
~~~

答え:

- `network_mode: host`、`links:`、`--link` は不使用。
- 全serviceが宣言済み `inception` bridge networkへ参加。
- entrypointは初期化後に `exec` し、本体をforegroundのPID 1にする。
- MariaDB初期化も `mariadbd --bootstrap --skip-networking` をforegroundで一度実行する。
- 全Dockerfileは `debian:12`。Debian 13がstableのためDebian 12はpenultimate stable。

### C. Build / Docker basics

専用評価VMで:

~~~sh
make
make ps
docker compose -f srcs/docker-compose.yml ps
docker images --format '{{.Repository}}:{{.Tag}}' | grep ':kishino$'
docker inspect mariadb wordpress nginx \
  --format '{{.Name}} image={{.Config.Image}} restart={{.HostConfig.RestartPolicy.Name}}'
~~~

期待:

- `mariadb:kishino`、`wordpress:kishino`、`nginx:kishino`。
- 3 containerがUp、MariaDBはhealthy。
- 3つとも `restart=always`。
- hostへ公開されるPORTSはnginxの443だけ。

「ready-made imageでは？」への答え:

> `debian:12` は許可されたOS base imageです。nginx、MariaDB、WordPressの完成済みservice imageは使わず、
> 各DockerfileでDebian packageやWP-CLIを導入し、自分の設定とentrypointを組み込んでいます。

### D. README / documentation

~~~sh
head -n1 README.md
grep -nE '^## (Description|Instructions|Resources)$' README.md
grep -n 'Use of AI assistance' README.md
test -s USER_DOC.md && test -s DEV_DOC.md
grep -nE 'Starting and stopping|admin dashboard|Credentials|Checking' USER_DOC.md
grep -nE 'Prerequisites|Makefile|docker compose|persistence|Storage' DEV_DOC.md
~~~

説明:

- README 1行目は指定形式でitalic。
- `Description`、`Instructions`、`Resources`、AI利用説明がある。
- USER_DOCは利用者／管理者向け、DEV_DOCは構築／運用／永続化向け。

### E. Simple setup / HTTPS only

~~~sh
curl --connect-timeout 3 -v http://kishino.42.fr
curl -kfsSI https://kishino.42.fr
curl -kfsS https://kishino.42.fr | grep -i '<title>'
docker port nginx
docker inspect nginx --format '{{.Path}} {{join .Args " "}}'
~~~

期待:

- HTTP port 80はconnection refused。HTTPS redirectではなく、そもそもlistenしない。
- HTTPSは200系でWordPressのHTMLを返す。
- `docker port nginx` は `443/tcp` だけ。
- 実行commandは `nginx -g daemon off;`。
- WordPress installation画面は出ない。

### F. NGINX + TLS

~~~sh
openssl s_client -connect kishino.42.fr:443 \
  -servername kishino.42.fr -tls1_2 </dev/null 2>/dev/null \
  | grep -E 'Protocol|Cipher'
openssl s_client -connect kishino.42.fr:443 \
  -servername kishino.42.fr -tls1_3 </dev/null 2>/dev/null \
  | grep -E 'Protocol|Cipher'
openssl s_client -connect kishino.42.fr:443 \
  -servername kishino.42.fr </dev/null 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates -ext subjectAltName
~~~

旧TLS拒否:

~~~sh
openssl s_client -connect kishino.42.fr:443 \
  -servername kishino.42.fr -tls1 </dev/null
openssl s_client -connect kishino.42.fr:443 \
  -servername kishino.42.fr -tls1_1 </dev/null
~~~

期待:

- TLS 1.2/1.3はhandshake成功。
- TLS 1.0/1.1はhandshake失敗。
- subject/SANに `kishino.42.fr`。
- 自己署名警告は許容。暗号化していないこととは異なる。

コード:

- protocol制限: `srcs/requirements/nginx/conf/nginx.conf` の `ssl_protocols`。
- certificate生成: `srcs/requirements/nginx/Dockerfile` の `openssl req`。
- foreground: Dockerfile末尾の `nginx -g 'daemon off;'`。

### G. Docker network

~~~sh
docker network ls | grep inception
docker network inspect inception \
  --format '{{range .Containers}}{{.Name}} {{end}}'
docker exec nginx getent hosts wordpress
docker exec wordpress getent hosts mariadb
~~~

期待:

- driverはbridge、3 containerが参加。
- Docker DNSで `wordpress` と `mariadb` が解決できる。

15秒回答:

> 各containerは独立したnetwork namespaceを持ちます。Composeのuser-defined bridgeへ参加すると、
> Docker DNSによりservice nameで相互接続できます。hostへpublishするのはnginxの443だけなので、
> WordPressの9000とMariaDBの3306は外部へ露出しません。

### H. WordPress + PHP-FPM + volume

~~~sh
docker compose -f srcs/docker-compose.yml ps wordpress
docker exec wordpress sh -c 'ps -p 1 -o pid=,comm=,args='
docker exec wordpress wp core is-installed --allow-root --path=/var/www/html
docker exec wordpress wp core version --allow-root --path=/var/www/html
docker exec wordpress wp user list \
  --fields=user_login,roles --allow-root --path=/var/www/html
docker volume inspect wordpress_data \
  --format 'name={{.Name}} device={{index .Options "device"}}'
docker inspect nginx \
  --format '{{range .Mounts}}{{.Name}} rw={{.RW}} dest={{.Destination}}{{println}}{{end}}'
~~~

期待:

- PID 1は `php-fpm8.2 -F`。
- userは `kishino` administrator、`guest` author。
- 管理者名に `admin` / `Admin` を含まない。
- volume deviceは `/home/kishino/data/wordpress`。
- nginx側のWordPress volumeは `rw=false`。

ブラウザ実演:

1. `guest` でログインし、既存記事へコメントを投稿。
2. `kishino` で `/wp-admin` にログイン。
3. pageまたはsite taglineを変更して保存。
4. public siteで変更が表示されることを確認。

> passwordは `secrets/credentials.txt` からローカルで確認するが、画面共有のterminalへ出しっぱなしにしない。

### I. MariaDB + volume

~~~sh
docker compose -f srcs/docker-compose.yml ps mariadb
docker exec mariadb sh -c 'ps -p 1 -o pid=,comm=,args='
docker volume inspect mariadb_data \
  --format 'name={{.Name}} device={{index .Options "device"}}'
docker exec wordpress sh -c \
  'mariadb -h mariadb -u"$MYSQL_USER" \
  -p"$(cat /run/secrets/db_password)" "$MYSQL_DATABASE" \
  -Nse "SHOW TABLES"' | wc -l
docker exec mariadb sh -c \
  'mariadb -u root -p"$(cat /run/secrets/db_root_password)" \
  -Nse "SELECT User, Host FROM mysql.user ORDER BY User, Host"'
~~~

期待:

- PID 1は `mariadbd`。
- volume deviceは `/home/kishino/data/mariadb`。
- WordPress DBのtable数は0より大きい。
- `wpuser` は `wordpress` DBだけにgrantされる。

grant確認:

~~~sh
docker exec mariadb sh -c \
  'mariadb -u root -p"$(cat /run/secrets/db_root_password)" \
  "$MYSQL_DATABASE" -Nse \
  "SELECT GRANTEE, TABLE_SCHEMA, PRIVILEGE_TYPE
   FROM information_schema.SCHEMA_PRIVILEGES
   WHERE TABLE_SCHEMA = DATABASE()
   ORDER BY GRANTEE, PRIVILEGE_TYPE"'
~~~

初回起動の説明:

> 空volumeなら `mariadb-install-db` でsystem tableを作ります。markerがなければ
> `mariadbd --bootstrap --skip-networking` をforegroundで実行し、DB、app user、
> root認証を設定します。成功後にmarkerを置き、最後に `exec mariadbd` します。
> 通常serverを一時的にbackground起動していません。

### J. Persistence

評価前にブラウザで固有の変更を作る。例: taglineを `defense-YYYYMMDD-HHMM` にする。

container再作成:

~~~sh
docker exec wordpress wp option get blogdescription \
  --allow-root --path=/var/www/html
make down
make
docker exec wordpress wp option get blogdescription \
  --allow-root --path=/var/www/html
~~~

期待: 前後が同じ。`make down` はvolume/dataを削除しない。

VM再起動:

~~~sh
sudo reboot
~~~

再ログイン後:

~~~sh
docker ps
curl -kfsSI https://kishino.42.fr
docker exec wordpress wp option get blogdescription \
  --allow-root --path=/var/www/html
~~~

期待: 3 containerが `restart: always` で復帰し、サイトと固有変更が残る。

> [!WARNING]
> `make fclean` はvolumeと `/home/kishino/data/{wordpress,mariadb}` を削除する。
> persistence確認中は使わない。

### K. daemon exit recovery（質問された場合）

`docker stop` / `docker kill` はDockerが明示停止として扱うため、restart policyの試験にならないことがある。
Linux VMのhost PIDを終了させてdaemon crashを再現する。

~~~sh
before=$(docker inspect wordpress --format '{{.RestartCount}}')
host_pid=$(docker inspect wordpress --format '{{.State.Pid}}')
sudo kill -KILL "$host_pid"
sleep 5
docker inspect wordpress \
  --format 'running={{.State.Running}} restart_count={{.RestartCount}}'
printf 'before=%s\n' "$before"
~~~

期待: `running=true` かつ restart countが増える。

## 4. ライブコーディング完全手順

### 最も安全な選択: nginx 443 → 8443

reviewerがportを自由指定するため、以下の `8443` は指定値へ読み替える。

変更箇所:

| ファイル | 変更 |
|---|---|
| `srcs/docker-compose.yml` | `ports: ["443:443"]` → `ports: ["8443:8443"]` |
| `srcs/requirements/nginx/conf/nginx.conf` | IPv4/IPv6の `listen 443 ssl` → `listen 8443 ssl` |
| `srcs/requirements/nginx/Dockerfile` | `EXPOSE 443` → `EXPOSE 8443` |

#### 1. 事前確認

~~~sh
ss -lnt | grep ':8443 ' || true
git status -sb
git diff -- srcs/docker-compose.yml \
  srcs/requirements/nginx/conf/nginx.conf \
  srcs/requirements/nginx/Dockerfile
~~~

出力がなければportは空いている。既存差分がある場合は、上書き前にreviewerと確認する。

#### 2. 編集

~~~sh
nano srcs/docker-compose.yml
nano srcs/requirements/nginx/conf/nginx.conf
nano srcs/requirements/nginx/Dockerfile
~~~

編集後:

~~~sh
grep -nE 'ports:|listen |EXPOSE' \
  srcs/docker-compose.yml \
  srcs/requirements/nginx/conf/nginx.conf \
  srcs/requirements/nginx/Dockerfile
docker compose -f srcs/docker-compose.yml config --quiet
git diff --check
git diff -- srcs/docker-compose.yml \
  srcs/requirements/nginx/conf/nginx.conf \
  srcs/requirements/nginx/Dockerfile
~~~

#### 3. rebuild・restart

~~~sh
docker compose -f srcs/docker-compose.yml up -d --build nginx
docker compose -f srcs/docker-compose.yml ps
docker logs --tail 50 nginx
~~~

#### 4. 新portを証明

~~~sh
curl -kfsSI https://kishino.42.fr:8443
openssl s_client -connect kishino.42.fr:8443 \
  -servername kishino.42.fr -tls1_2 </dev/null 2>/dev/null \
  | grep -E 'Protocol|Cipher'
docker port nginx
curl --connect-timeout 3 -kfsSI https://kishino.42.fr:443
~~~

期待:

- 8443でWordPressが200系。
- TLS 1.2以上。
- `docker port nginx` は8443。
- 旧443は接続失敗。

#### 5. rollback（reviewer確認後だけ）

~~~sh
git diff -- srcs/docker-compose.yml \
  srcs/requirements/nginx/conf/nginx.conf \
  srcs/requirements/nginx/Dockerfile
git restore -- srcs/docker-compose.yml \
  srcs/requirements/nginx/conf/nginx.conf \
  srcs/requirements/nginx/Dockerfile
docker compose -f srcs/docker-compose.yml up -d --build nginx
curl -kfsSI https://kishino.42.fr
~~~

`git restore` は上記3ファイルの未コミット変更を破棄する。reviewerが変更を残すよう求めた場合は実行しない。

### reviewerが別serviceを指定した場合

| 変更 | 必須編集箇所 | 再build |
|---|---|---|
| PHP-FPM 9000 → 9001 | `wordpress/conf/www.conf` の `listen`、`wordpress/Dockerfile` の `EXPOSE`、`nginx/conf/nginx.conf` の `fastcgi_pass` | wordpress, nginx |
| MariaDB 3306 → 3307 | `mariadb/conf/99-inception.cnf` の `port`、`mariadb/Dockerfile` の `EXPOSE`、WordPress entrypointの接続待ちと `--dbhost` | mariadb, wordpress |

PHP-FPM例:

~~~sh
docker compose -f srcs/docker-compose.yml up -d --build wordpress nginx
curl -kfsSI https://kishino.42.fr
~~~

MariaDB変更時の追加注意:

- persisted `wp-config.php` の `DB_HOST` は初回作成後に自動再生成されない。
- stack停止前に、指定portへ合わせて更新する。

~~~sh
docker exec wordpress wp config set DB_HOST 'mariadb:3307' \
  --allow-root --path=/var/www/html
docker compose -f srcs/docker-compose.yml up -d --build mariadb wordpress nginx
~~~

## 5. 頻出質問と短答

### DockerとDocker Composeはどう動く？

> Dockerfileからimmutableなimageをbuildし、imageから隔離されたcontainerを起動します。
> Composeは複数containerのbuild context、network、volume、secret、依存関係、
> restart policyを一つの宣言ファイルで再現可能にまとめます。

### Composeあり／なしでimageは違う？

> image形式は同じです。Composeなしなら `docker build`、`docker run`、`docker network`、
> `docker volume` などを個別に指定します。Composeは同じ操作と関係を宣言的に一括管理します。

### imageとcontainerの違いは？

> imageはread-only layerのtemplate、containerはそのimageにwritable layer、process、
> network namespaceなどを加えた実行instanceです。重要データをcontainer layerへ置かずvolumeへ保存します。

### DockerがVMより有利な点は？

> containerはhost kernelを共有するため軽量・高速・再現しやすいです。VMはguest kernelを含み、
> isolationは強い一方でresourceと起動時間のcostが大きいです。この課題ではVMの中でDockerを動かします。

### なぜ1 container 1 service？

> lifecycle、log、failure、resource、更新単位を分離できます。nginx、PHP-FPM、MariaDBを独立させ、
> Compose networkで接続することで、責任範囲と障害箇所が明確になります。

### なぜPID 1とforegroundが重要？

> containerの停止signalはPID 1へ届きます。shellがserverをchild/backgroundにするとsignal伝達や終了code、
> zombie回収が不明瞭になります。entrypoint末尾で `exec` し、本体をforegroundのPID 1にします。

### MariaDB初期化でbackground serverを使わない方法は？

> `mariadbd --bootstrap --skip-networking` はSQLをstdinからforegroundで処理して終了します。
> 最初に `FLUSH PRIVILEGES` し、DB/user/grant/root認証を設定した後、通常の `mariadbd` を `exec` します。

### `depends_on` だけでreadyを保証できる？

> 起動順だけではreadyを保証しません。MariaDBにはhealthcheckを定義し、WordPressは
> `condition: service_healthy` に依存します。WordPress entrypoint自身も有限回の実接続retryを行います。

### Docker networkとhost networkの違いは？

> user-defined bridgeではcontainerごとにnetwork namespaceを保ち、Docker DNSと明示的なport publishを使えます。
> host networkはhostのnetwork namespaceを共有し、port隔離とCompose service discoveryの利点を失います。

### named volumeなのにhost pathが見えるのはなぜ？

> `driver: local` と `driver_opts` の `type: none`、`o: bind`、`device` を組み合わせています。
> Dockerにはnamed volumeとして管理させつつ、subject指定の `/home/kishino/data` を実体にしています。

### volumeとbind mountの違いは？

> plain bind mountは任意のhost pathを直接mountします。named volumeはDockerが名前とlifecycleを管理します。
> 本構成はnamed volumeにlocal driverのbind optionを付け、両要件を満たします。

### secretとenvironmentの違いは？

> environmentは `docker inspect` やprocess environmentから見えやすいです。
> secretはread-only fileとして `/run/secrets` にmountされ、image layerやenvironmentへ入れません。
> domain、DB名、usernameは非機密なのでenvironment、passwordだけsecretです。

### なぜnginxだけvolumeがread-only？

> nginxはstatic assetを読むだけで、WordPress fileを書き換える責任がありません。
> `:ro` で最小権限にし、書込みはWordPress containerだけへ限定します。

### なぜTLS 1.2/1.3だけ？

> subject要件であり、TLS 1.0/1.1は古いprotocolです。nginxの `ssl_protocols TLSv1.2 TLSv1.3` で制限します。
> 自己署名かどうかはtrustの問題で、通信暗号化の有無とは別です。

### なぜDebian 12？

> Debian 13がcurrent stableで、Debian 12がoldstable＝penultimate stableです。
> tagを固定することで `latest` の漂流も避けます。

### WordPress再起動で再インストールされない？

> volume上の `wp-load.php`、`wp-config.php`、`wp core is-installed`、user存在を検査します。
> MariaDB側もdata directoryとprovision markerを検査するため、初期化処理はidempotentです。

### `EXPOSE` と `ports` の違いは？

> `EXPOSE` はimageが想定するlisten portのmetadataで、host公開はしません。
> Compose `ports` がhostとcontainerのport mappingを作ります。本構成で `ports` があるのはnginxだけです。

### certificateはどこで作る？

> nginx image build時にDockerfileの `openssl req -x509` で作り、
> `/etc/nginx/ssl/inception.crt` と `inception.key` をnginx configから参照します。

### directory構成の意味は？

> ルートは操作契約のMakefileと必須documentation、`srcs/docker-compose.yml` は全体orchestration、
> `requirements/<service>` はservice固有のDockerfile、config、entrypointに分離しています。
> reviewerは全体から各service実装へ辿れます。

## 6. トラブルシュート

~~~mermaid
flowchart TD
    A["make / access failure"] --> B{"docker compose ps"}
    B -->|"container absent/exited"| C["docker compose logs --tail 100 SERVICE"]
    B -->|"all Up"| D{"HTTPS response?"}
    C --> E{"Which service?"}
    E -->|"mariadb"| F["secret mount / datadir / bootstrap SQL / healthcheck"]
    E -->|"wordpress"| G["DB credentials / DNS / wp-config / PHP-FPM"]
    E -->|"nginx"| H["listen port / certificate / fastcgi_pass / shared volume"]
    D -->|"connection refused"| I["published port / nginx listen / /etc/hosts"]
    D -->|"502"| G
    D -->|"DB error"| F
    D -->|"wrong content"| J["wordpress_data mount / WordPress install state"]
~~~

最短診断:

~~~sh
docker compose -f srcs/docker-compose.yml ps
docker compose -f srcs/docker-compose.yml logs --tail 100
docker inspect mariadb --format '{{json .State.Health}}'
docker network inspect inception
docker volume inspect mariadb_data wordpress_data
curl -kvI https://kishino.42.fr
~~~

| 症状 | 最初に見る場所 |
|---|---|
| MariaDB unhealthy | `docker logs mariadb`、secret mount、`/home/kishino/data/mariadb` ownership |
| WordPress restart loop | `docker logs wordpress`、DB DNS/credential、有限retry |
| 502 Bad Gateway | PHP-FPMのlisten、nginx `fastcgi_pass`、WordPress container状態 |
| HTTPS connection refused | Compose `ports`、nginx `listen`、container状態 |
| certificate warning | 自己署名なら正常。CN/SANと期限だけ確認 |
| loginできない | persisted accountとsecret fileの不一致を疑う。値を作り直すだけでは直らない |
| 変更が消えた | named volume mountとhost device、`make fclean` 実行有無 |
| port変更後だけ失敗 | 全参照箇所、persisted config、rebuild対象を再確認 |

## 7. 最終チェックリスト

### 提出前

- [ ] `git status -sb` を説明できる。
- [ ] secret実値がGit履歴・tracked fileにない。
- [ ] root必須5点: `Makefile`、`srcs/`、`README.md`、`USER_DOC.md`、`DEV_DOC.md`。
- [ ] 禁止pattern検査が空。
- [ ] 3 Dockerfileが `FROM debian:12`。
- [ ] image名とservice名が一致。
- [ ] entrypointにbackground program、無限loopがない。
- [ ] `docker compose config --quiet` が通る。
- [ ] fresh `make` が通る。
- [ ] 3 containerがUp、MariaDB healthy。
- [ ] nginxだけ443をpublish。
- [ ] TLS 1.2/1.3成功、1.0/1.1失敗。
- [ ] WordPress install画面が出ない。
- [ ] `kishino` admin、`guest` author。
- [ ] comment追加とadmin編集を実演済み。
- [ ] DB接続とtable非空を実演済み。
- [ ] named volumeのdeviceが `/home/kishino/data/...`。
- [ ] `make down && make` で変更保持。
- [ ] VM reboot後も復帰・保持。
- [ ] reviewer指定port変更をrebuild・restart・疎通まで練習済み。
- [ ] Bonusは実装していないため主張しない。

### 口頭防御

- [ ] Docker / Compose / image / containerを自分の言葉で説明できる。
- [ ] Docker vs VMを説明できる。
- [ ] bridge network / Docker DNS / host network不使用を説明できる。
- [ ] named volume + local bind driverを説明できる。
- [ ] secrets vs environmentを説明できる。
- [ ] PID 1 / `exec` / foregroundを説明できる。
- [ ] TLS、PHP-FPM、FastCGI、MariaDBのrequest flowを図で説明できる。
- [ ] 初回provisioningとidempotencyを説明できる。
- [ ] failure時に `ps → logs → network/volume/config` の順で切り分けられる。

## 8. この資料自体の更新確認

コード変更後は、古い行番号やportを残さない。

~~~sh
grep -nE '443|9000|3306|bootstrap|DEFENSE' DEFENSE_CHEATSHEET.md
grep -nE 'ports:|listen |fastcgi_pass|port=|EXPOSE|bootstrap' \
  srcs/docker-compose.yml \
  srcs/requirements/*/Dockerfile \
  srcs/requirements/*/conf/* \
  srcs/requirements/*/tools/*.sh
git diff --check
~~~

最終原則:

> 「動いた」ではなく、どの要件を、どのコードが担い、どのコマンドと画面で証明したかを答える。
> 不明なときは推測せず、Compose → service config → runtime state → logsの順に根拠を示す。
