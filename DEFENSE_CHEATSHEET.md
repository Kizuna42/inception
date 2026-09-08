# Inception Defense Cheat Sheet

[42 EvalHub — Inception](https://www.42evalhub.com/common/inception) の評価順に、判定条件を落とさず日本語で整理した学習・実演用の一枚。
**「評価項目」は原文の要旨訳、「本実装／口頭説明」はこのリポジトリへの対応と補足**。実演結果は当日確認する。

## 0. 読み方と実演の前提

コマンドは **Linux 評価 VM のリポジトリルート**で実行する。`$` は付けずにコピーできる。
以下の関数を最初に定義する。**再ログイン・別ターミナルでは再定義**する。

```sh
dc() { docker compose -f srcs/docker-compose.yml "$@"; }
wp() { dc exec -T -w /var/www/html wordpress wp "$@" --allow-root; }
```

| 本実装の名前 | 値／役割 |
|---|---|
| URL／管理画面 | `https://kishino.42.fr` ／ `/wp-admin/` |
| Compose service／container | `nginx`、`wordpress`、`mariadb` |
| image | `nginx:kishino`、`wordpress:kishino`、`mariadb:kishino` |
| DB／DB 接続ユーザー | `wordpress` ／ `wpuser` |
| WordPress アカウント | `kishino`：administrator、`guest`：author |
| network／volume | `inception` ／ `wordpress_data`、`mariadb_data` |
| 実データ | `/home/kishino/data/wordpress`、`/home/kishino/data/mariadb` |

### Introduction / Guidelines — 評価の姿勢・共通ルール

**評価項目：** 礼節を守って不具合を議論し、仕様の解釈差に配慮して公平に評価する。評価対象は提出 Git の内容だけ。
本人・リポジトリ・課題を照合し、空ディレクトリへ clone する。alias による偽装がないか確認し、評価補助スクリプトは一緒に読む。
未履修の評価者は subject 全文を読む。空提出・動作不能・Norm 違反等は該当 flag で終了・0 点、不正は -42 点。
不正以外では、終了後も間違いを振り返ることが推奨される。

**説明：**「補助テストの PASS だけに頼らず、提出コード・設定・実際の応答を対応させて説明します。」

## 1. Preliminary tests — 提出物・本人・秘密情報

**評価項目：** 本人が立ち会い、本人の station で提出 Git を clone する。未提出・ファイル／場所／名前の誤りは 0 点で終了。
ローカル `.env` や Docker secrets の利用は許可されるが、評価中に作成する secrets ファイル以外に、Git リポジトリ内の認証情報・API key・password があれば 0 点で終了。
不正が疑われた場合は慎重に判断し、Cheat flag で評価を止める。

```sh
git status -sb
git log -1 --format='%h %s'
git ls-files Makefile srcs README.md USER_DOC.md DEV_DOC.md
git ls-files secrets
git check-ignore secrets/db_root_password.txt secrets/db_password.txt secrets/credentials.txt
git log --all --oneline -- secrets
```

**期待結果：** 必須提出物あり、`git ls-files secrets` は空、3 ファイルが ignore 対象。履歴に secrets があれば調査する。
ignore とファイル名の検査だけでは「別名のファイルや過去 commit に秘密がない」とは証明できない。提出差分・履歴も確認し、秘密値を画面共有やログへ出さない。

**口頭説明：**「`srcs/.env` はドメインや DB 名などの非機密設定です。password は `make secrets` がローカル生成し、Git 管理外の `secrets/` から必要な container だけへ渡します。」

**周辺知識：** `.gitignore` は既に tracked のファイルや履歴を消さない。Compose の file-based secrets は `/run/secrets/` への読み取り専用 mount で、ローカル元ファイルを暗号化保管する機能ではない。
本実装は生成元を mode `600` にするが、アプリが読む必要はあり、DB password は永続 `wp-config.php` にも保存される。
既存 DB／WordPress の password は secret ファイルを書き換えるだけでは変更されない。

## 2. General instructions — 構成・禁止事項・起動

**評価項目：** 不明な確認方法は被評価者が説明する。root に `Makefile`、アプリ設定一式を置く `srcs/` が必要。
Compose に明示的な `network(s)` が必要で、host network・`links:`・スクリプトの `--link` は禁止。
各 image は Alpine または Debian の **直前の stable 系列**をベースにする。
Dockerfile／entrypoint でのバックグラウンド起動、単なる `bash`／`sh`、`tail -f`、`sleep infinity`、無限ループによる延命は禁止。
スクリプトを実行するための shell は許可される。違反なら終了し、条件を確認したら Makefile を実行する。

```sh
cat Makefile srcs/docker-compose.yml
cat srcs/requirements/*/Dockerfile
cat srcs/requirements/*/tools/entrypoint.sh
rg -n 'network_mode:.*host|links:|--link|tail .* -f|tail -f|sleep infinity|while true' Makefile srcs
find srcs/requirements -name '*.sh' -exec sh -n {} \;
dc config --quiet
```

**期待結果：** 禁止パターンの検索は空、構文チェックは成功。検索は見落としもあるので script 本文と終了条件まで読む。
`rg` が VM にない場合は同じパターンを `grep -RnE` で検索する。
本実装は全て `FROM debian:12`。2026-09-08 確認の Debian は 13 が stable、12 が oldstable（前 stable）；評価日にも [公式 release 一覧](https://www.debian.org/releases/) と照合する。

### 評価開始時の全削除と fresh build

**評価項目：** 評価開始前に以下の Docker リソース全削除を実行する。
**これは専用評価 VM 限定。他プロジェクトの container・image・volume・network も対象になる。**
既存データを残す必要がある場合、先に `make down` で停止してから `/home/kishino/data` を別名へ退避する。稼働中の DB ディレクトリは移動しない。

```sh
# EvalHub 指定。専用評価 VM で対象を確認してから実行する。
docker stop $(docker ps -qa); docker rm $(docker ps -qa); \
docker rmi -f $(docker images -qa); docker volume rm $(docker volume ls -q); \
docker network rm $(docker network ls -q) 2>/dev/null
```

対象 0 件や既定 network の削除ではエラーが出る場合がある。bind 元のデータは volume 削除だけでは消えないため、これだけで「空データから起動した」とは言えない。

```sh
make
dc ps
```

**期待結果：** 3 service が Up、MariaDB と WordPress は最終的に healthy。`make` は data／secrets の準備と `compose up -d --build` を行う。

**口頭説明：**「server 自身を foreground で動かし、終了したら container も終了させます。`exec` で shell を server に置き換え、PID 1 が終了シグナルを直接受け取れるようにします。」

**周辺知識：** `up -d` はホスト側 CLI を切り離す指定で、entrypoint 内の `server &` とは別。
WordPress の DB 待ちは最大 30 回の有限 retry。`restart: always` は終了した container を再起動するが、**unhealthy だけで再起動するわけではない**。

## 3. Activity overview — Docker と構成を説明

**評価項目：** Docker／Compose の仕組み、Compose を使う場合と使わない場合の image の違い、VM に対する Docker の利点、指定ディレクトリ構造の意義を平易に説明する。

```text
ブラウザ ── HTTPS :443 ──> nginx ── FastCGI :9000 ──> wordpress (PHP-FPM)
                             │                            │
                             └── static files (read-only) │── SQL :3306 ──> mariadb
                                      wordpress_data ─────┘                mariadb_data
```

| 質問 | 口頭説明 |
|---|---|
| Docker とは？ | 「アプリと依存関係を image にまとめ、独立したプロセス環境で動かします。image は実行元の層、container はその image を起動した実体です。」 |
| Compose とは？ | 「複数 service の build・network・volume・依存関係を YAML に宣言して、一括で再現するツールです。」 |
| Compose の有無で image は変わる？ | 「形式は同じです。同じ image を `docker run` でも起動できます。変わるのは起動設定を個別コマンドで与えるか YAML に集約するかです。」 |
| VM との違いは？ | 「VM は guest kernel ごと動かし、container は Linux host の kernel を共有します。container は軽量に分けやすく、VM は別 kernel の境界を持ちます。本課題では VM 内で Docker を動かします。」 |
| ディレクトリを分ける理由は？ | 「root の Makefile を入口にし、`srcs/` に全体設定、`requirements/<service>/` に Dockerfile・conf・tools を分け、責務と build context を明確にします。」 |

**周辺知識：** namespaces はプロセス・network・mount 等の見える範囲を分け、cgroups は CPU／memory 等を管理する。
この Compose は resource limit を指定していない。「container だから自動的に使用量を制限している」とは説明しない。
`RUN` は build 時、`COPY` は build context から image へのコピー、`CMD`／`ENTRYPOINT` は起動時。
`EXPOSE` は想定 port の宣言であり、ホストへ公開する設定は `ports:`。

## 4. README check — 必須 README

**評価項目：** root の `README.md` が存在し、先頭行が斜体の
`This project has been created as part of the 42 curriculum by <login...>` 形式であること。
`Description`、`Instructions`、AI 利用の説明を含む `Resources` が必須。欠落があれば終了。

```sh
head -n 1 README.md
rg -n '^## |^### Use of AI|Claude|Codex' README.md
```

**期待結果／口頭説明：** 先頭行に `kishino`、必要 section と AI の利用説明がある。
「README は課題の目的、起動方法、設計理由、参照資料、AI の支援範囲の入口です。採用した内容の理解と説明は本人の責任です。」

## 5. Documentation check — 利用者用・開発者用文書

**評価項目：** root に空でない `USER_DOC.md` と `DEV_DOC.md` が必要。欠落・空なら終了。
USER_DOC は開始／停止、サイト／管理画面へのアクセス、認証情報管理、基本確認を扱う。
DEV_DOC は前提環境、setup、Makefile、Compose コマンド、データ永続化を扱う。

```sh
test -s USER_DOC.md && test -s DEV_DOC.md
rg -n '^## |^### ' USER_DOC.md DEV_DOC.md
```

**口頭説明：**「利用者には運用の手順を、開発者には構成を再現・変更するための情報を分けています。」

| 日常操作 | 本実装での効果 |
|---|---|
| `make` | 準備・build・起動 |
| `make down` | container／network を削除。image／volume／実データは保持 |
| `make clean` | `down` に加えて service image を削除。実データは保持 |
| `make fclean`／`make re` | **実データも削除**／削除後に起動。永続化の実演には使わない |
| `dc logs --tail=40 wordpress` | 対象 service の直近ログで起動失敗を調べる |

## 6. Simple setup — HTTPS だけで完成済みサイトへ

**評価項目：** NGINX は port 443 だけからアクセスでき、SSL/TLS 証明書を使用する。
`https://<login>.42.fr` に設定済み WordPress が表示され、インストール画面は出ない。
`http://<login>.42.fr` はアクセスできない。不成立なら終了。

```sh
getent hosts kishino.42.fr
dc ps
curl --noproxy '*' --max-time 5 http://kishino.42.fr/
curl --noproxy '*' -ksS --fail -D /tmp/inception-headers \
  https://kishino.42.fr/ -o /tmp/inception-home.html
head -n 1 /tmp/inception-headers
wp core is-installed
```

**期待結果：** HTTP は接続失敗、HTTPS は成功し HTML が保存され、`wp core is-installed` は exit 0。
ブラウザでも `https://kishino.42.fr` を開き、サイト本文が見え、install 画面でないことを確認する。
**HTTP status だけでは十分でない**。保存 HTML に error／install 画面がないか確認し、画面と突き合わせる。

**口頭説明：**「入口を nginx の 443 に限定しています。80 は redirect 用にも開けていません。証明書は自己署名なので、ブラウザ警告は想定内です。」

**周辺知識：** VM 内ブラウザなら `/etc/hosts` の `127.0.0.1 kishino.42.fr`、ホスト側ブラウザならホスト側で VM の IP に対応させる。
`curl -k` は証明書検証を省略するが通信の暗号化は続く。名前解決だけ切り分ける場合は `--resolve kishino.42.fr:443:127.0.0.1` を使えるが、通常のブラウザ用名前解決の確認も必要。

## 7. Docker Basics — 自作 image・build・プロセス

**評価項目：** service ごとに空でない自作 Dockerfile があり、自分で image を build すること。完成済み service image／DockerHub 等への依存は禁止。
ベースは直前 stable の Alpine／Debian（原文は `FROM alpine:X.X.X`、`FROM debian:XXXXX` または local image を確認）。
image 名は対応 service 名と一致すること。Makefile が Compose 経由で全 service を build／起動し、クラッシュしないこと。不成立なら終了。

```sh
dc config --services
dc images
rg -n '^FROM|^RUN|^COPY|^ENTRYPOINT|^CMD' srcs/requirements/*/Dockerfile
for svc in nginx wordpress mariadb; do
  docker inspect "$svc" --format '{{.Name}} image={{.Config.Image}} status={{.State.Status}} restarts={{.RestartCount}}'
  docker exec "$svc" sh -c 'tr "\000" " " </proc/1/cmdline; echo'
done
```

**期待結果：** 自作 3 image、対応する running container、PID 1 は nginx master／php-fpm／mariadbd。
restart 回数が増える場合は正常稼働とせずログで調べる。Debian OS ベースの取得と、完成済み `FROM nginx` 等の使用を区別する。

**口頭説明：**「3 つとも `debian:12` に必要な package を自分で install します。`image: nginx:kishino` は完成済み image を使う指定ではなく、隣の `build:` から作る image の名前です。」

**周辺知識：** `:kishino` は tag、image の repository 名は service と同じ。tag 固定と digest 固定は異なり、`debian:12` の中身は更新され得る。
1 service＝1 container は 1 PID の意味ではない。nginx／PHP-FPM は master と worker を持てる。

## 8. Docker Network — 明示 network と名前解決

**評価項目：** Compose が Docker network を利用し、`docker network ls` で確認できること。仕組みを簡単に説明すること。不成立なら終了。

```sh
docker network ls
docker network inspect inception --format '{{.Driver}} {{range .Containers}}{{.Name}} {{end}}'
docker exec nginx getent hosts wordpress
docker exec wordpress getent hosts mariadb
docker port nginx
docker port wordpress
docker port mariadb
```

**期待結果：** `inception` は bridge で 3 container が所属。service 名が IP に解決される。公開 port は nginx の 443 のみ。

**口頭説明：**「ユーザー定義 bridge 内では Docker の DNS で service 名を解決できます。IP を固定せず `wordpress:9000` と `mariadb:3306` へ接続します。host network はこの network namespace を分ける方式と異なり、課題では禁止です。」

**周辺知識：** container 内の `localhost` はその container 自身。NGINX から `localhost:9000` では PHP-FPM に届かない。
内部 port はホストへ publish しなくても同じ network から接続できる。`ports:` がないことは外部公開しない設定であり、Docker host 管理者からのアクセスまで遮断する保証ではない。
本 network は `internal: true` ではなく、WordPress 初期 download 等の外向き通信も行う。

## 9. NGINX with SSL/TLS — TLS の設定と実通信

**評価項目：** Dockerfile と起動済み container を確認し、HTTP:80 が接続不可、HTTPS で完成済み WordPress が表示されること。
TLS 1.2 または 1.3 の使用を実証する（原文は「TLS v1.2/v1.3 certificate」と表現）。自己署名は許可される。説明・動作が不成立なら終了。

```sh
dc ps nginx
docker exec nginx nginx -t
docker exec nginx nginx -T 2>&1 | grep -E 'listen|ssl_protocols|fastcgi_pass'
openssl s_client -connect kishino.42.fr:443 -servername kishino.42.fr -tls1_2 -brief </dev/null
openssl s_client -connect kishino.42.fr:443 -servername kishino.42.fr -tls1_3 -brief </dev/null
openssl s_client -connect kishino.42.fr:443 -servername kishino.42.fr -tls1 -cipher 'ALL:@SECLEVEL=0' -brief </dev/null
openssl s_client -connect kishino.42.fr:443 -servername kishino.42.fr -tls1_1 -cipher 'ALL:@SECLEVEL=0' -brief </dev/null
```

**期待結果：** 構文 OK、`ssl_protocols TLSv1.2 TLSv1.3`、1.2／1.3 の handshake 成功と negotiated protocol／cipher 表示。
1.0／1.1 は成立しない。ただし client の `no protocols available`／`no ciphers available` は **client 側の拒否で、server の拒否証明ではない**。
上の `-cipher` はこの検証 client だけの制限を緩める指定。server 由来の `alert protocol version` を確認する。
それでも旧 protocol を送信できなければ対応 client が必要で、拒否の実通信は未確認とし、設定の証拠と分けて説明する。
HTTP／HTTPS のページ確認は §6 の GET とブラウザ実演を用いる。

**口頭説明：**「TLS version は証明書自体の種類ではなく、handshake で合意する通信 protocol です。証明書は公開鍵とサーバー名等を結びつけ、自己署名では第三者 CA による身元保証がありません。」

**周辺知識：** TLS は盗聴対策の暗号化・改ざん検出・相手認証を担う。公開鍵／証明書と秘密鍵は別物。
NGINX は静的ファイルを直接返し、PHP は `fastcgi_pass wordpress:9000` へ渡す。`SCRIPT_FILENAME` が実行ファイルの path を PHP-FPM に伝える。
本実装は build 時に自己署名証明書と秘密鍵を生成する。image に秘密鍵が含まれるため、image を公開配布する設計ではない。

## 10. WordPress with php-fpm and its volume — CMS・権限・共有ファイル

**評価項目：** 専用 Dockerfile があり NGINX を含まないこと。container が起動し、`docker volume ls`／`inspect` で `/home/<login>/data/` 配下を確認できること。
用意された WordPress user でコメントを追加できること。管理者で dashboard に入り、管理者名に `admin`／`Admin` を含まないこと。
dashboard から page を編集し、サイト側に反映されること。不成立なら終了。

```sh
cat srcs/requirements/wordpress/Dockerfile
dc ps wordpress
docker volume ls
docker volume inspect wordpress_data --format '{{json .Options}}'
docker inspect nginx wordpress --format '{{.Name}} {{range .Mounts}}{{.Name}} -> {{.Destination}} RW={{.RW}} {{end}}'
wp user list --fields=user_login,roles
```

**期待結果：** `device=/home/kishino/data/wordpress`、両 container に `/var/www/html`、nginx 側 `RW=false`。
ユーザーは `kishino`＝administrator、`guest`＝author。資格情報は `secrets/credentials.txt` にあるが共有画面へ値を出さず入力する。

**ブラウザ実演：** `guest` でログイン → コメント可能な投稿に識別しやすいコメントを追加 → 必要なら管理者で承認 → 公開表示を確認。
次に `kishino` で `/wp-admin/` → 固定ページを編集・更新 → 公開ページを再読込して変更を確認する。
コメント欄がない場合は対象投稿のコメント許可を確認する。再起動テストで再確認するため、URL と変更内容を控える。

**口頭説明：**「WordPress は PHP の CMS、PHP-FPM は PHP 実行プロセスを管理する FastCGI server です。NGINX とは別 container にして、PHP の実行と HTTP/TLS の処理を分担します。」

**周辺知識：** WordPress ファイル・uploads・`wp-config.php` は `wordpress_data`、投稿・コメント・ユーザー・設定値は DB 側に保存される。
FastCGI は HTTP ではないため `curl http://wordpress:9000` は正しい動作検証ではない。
本実装の FPM healthcheck は port LISTEN を調べるだけで、PHP 実行や DB 利用の成功まで保証しない。
起動 script は DB 接続を待ち、未取得なら core を download、未作成なら config、未 install ならサイト、未登録なら第 2 user を作り、最後に `exec php-fpm8.2 -F` する。

## 11. MariaDB and its volume — DB 接続・中身・権限

**評価項目：** 専用 Dockerfile があり NGINX を含まないこと。container が起動し、volume の実 path が `/home/<login>/data/` 配下であること。
DB へのログイン方法を説明し、DB が空でないことを確認する。不成立なら終了。

```sh
cat srcs/requirements/mariadb/Dockerfile
dc ps mariadb
docker volume inspect mariadb_data --format '{{json .Options}}'
docker exec -it mariadb mariadb -u root -p
```

password は prompt に手入力する（コマンド行・履歴に書かない）。接続後は以下を実行する。

```sql
SHOW DATABASES;
USE wordpress;
SHOW TABLES;
SELECT ID, post_title, post_status FROM wp_posts LIMIT 5;
SELECT user_login FROM wp_users;
EXIT;
```

**期待結果：** `device=/home/kishino/data/mariadb`、WordPress の DB・table・投稿／ユーザーの行が存在する。`user_pass` 等の認証値は表示しない。
アプリと同じ TCP 経路・認証を示す場合は次を使い、DB 用 password を手入力する。

```sh
docker exec -it wordpress mariadb -h mariadb -P 3306 -u wpuser -p wordpress
```

**口頭説明：**「WordPress は専用 DB user で `mariadb:3306` に接続します。管理用 root と分け、`wpuser` の権限は WordPress 用 DB に限定しています。」

**周辺知識：** この root は `unix_socket OR mysql_native_password` 認証。
container 内の OS root なら `docker exec -it mariadb mariadb -u root` でも Unix socket 経由で接続できる。
これは password が未設定という意味ではなく、socket の OS identity を信頼する別経路。`root -p` の成功だけでは password 認証の証明にならず、アプリ user の TCP 接続で確認する。
`mariadb-admin ping` の healthy は server の生存確認で、WordPress user の認証・table の存在の証明ではない。

**初回起動を聞かれたら：**「空 data に `mariadb-install-db` で system table を作ります。marker がなければ `mariadbd --bootstrap --skip-networking` に SQL を渡し、DB・user・権限・root 認証を設定します。成功時だけ marker を作り、最後に `exec mariadbd --user=mysql` で通常 server に切り替えます。bootstrap は foreground で処理して終了し、一時 server を background にしていません。」

## 12. Persistence! — VM 再起動をまたいで保持

**評価項目：** **VM を再起動**し、Compose を再実行して全 service が機能し、WordPress／MariaDB の設定と先ほどのサイト変更が残ることを確認する。不成立なら終了。

```sh
# §10 の変更とコメントが公開画面にあることを確認してから実行。
sudo reboot
```

再ログイン後、同じリポジトリへ移動し §0 の `dc`／`wp` を再定義する。

```sh
make
dc ps
getent hosts kishino.42.fr
wp core is-installed
wp user list --fields=user_login,roles
```

**期待結果：** 初期 install 画面ではなく既存サイトが開き、§10 の編集・コメントが残る。管理画面と §11 の DB 接続も再確認する。
`make down` → `make` は container 再作成の補助検証にはなるが、VM 再起動の代わりにはならない。

**口頭説明：**「container の書き込み層の外にデータを置きます。named volume を local driver の bind option で `/home/kishino/data/` に対応させ、container を作り直しても同じデータを mount します。」

**周辺知識：** `docker volume inspect` の `Options.device` が指定 host path。`Mountpoint` は Docker 管理 path を示す場合がある。
MariaDB は data／初期化 marker、WordPress は既存 config／install 状態を確認し、再起動時の上書き・二重作成を避ける（冪等性）。
起動順は MariaDB → WordPress → NGINX。`depends_on` だけでは ready を待たないため、本実装は `condition: service_healthy` と WordPress 内の実接続 retry を使う。
cloud-init が hosts を再生成する VM では名前解決設定も永続化が必要。データが消えたのか、名前解決だけ失敗したのかを分ける。

## 13. Configuration modification — 指定された設定を変更

**評価項目：** 評価者が service と変更内容（例：空いている新 port）を選ぶ。被評価者が変更し、**project を rebuild・restart**して、新設定でもアクセス・機能が維持されることを実証する。できなければ終了。

**口頭説明：**「待受側・接続側・公開 port・healthcheck・永続設定を順に追います。Dockerfile を rebuild しても volume 内の既存設定が自動で書き換わるわけではありません。」

### A. NGINX の例：443 → 8443

```sh
ss -ltn | grep ':8443 '  # 出力があれば別の空き port を選ぶ
```

1. `srcs/requirements/nginx/conf/nginx.conf` の IPv4／IPv6 両方の `listen 443` を `8443` に変更。
2. `srcs/docker-compose.yml` の nginx `ports` を `"8443:8443"` に変更。
3. nginx Dockerfile の `EXPOSE` を `8443` に揃える（これは公開操作そのものではない）。
4. `srcs/.env` の `DOMAIN_NAME` を `kishino.42.fr:8443` にする。これは本実装の WordPress URL 初期化用。NGINX の `server_name`／証明書の DNS 名には port を付けない。
5. 既存 WordPress の canonical URL も更新する。

```sh
wp option update home 'https://kishino.42.fr:8443'
wp option update siteurl 'https://kishino.42.fr:8443'
make
dc ps
docker exec nginx nginx -t
curl --noproxy '*' -ksS --fail -L --max-redirs 5 \
  https://kishino.42.fr:8443/ -o /tmp/inception-8443.html
curl --noproxy '*' -k --max-time 5 https://kishino.42.fr/
wp option get home
wp option get siteurl
```

**期待結果：** 8443 の GET 成功、旧 443 は接続失敗、両 option は新 URL。
ブラウザでも `:8443` の本文・リンク・管理画面ログインを確認する。固定で埋め込まれた旧 URL が残る場合は対象リンクも修正する。
公開側だけ `8443:443` にする方法もあるが、container 内の待受変更を指定された場合はそれだけでは不足。

### B. PHP-FPM の例：9000 → 9001

| 変更ファイル | 対応 |
|---|---|
| `wordpress/conf/www.conf` | `listen = 9001` |
| `nginx/conf/nginx.conf` | `fastcgi_pass wordpress:9001;` |
| `wordpress/Dockerfile` | `EXPOSE 9001` |
| `srcs/docker-compose.yml` | WordPress healthcheck の `:2328` を `:2329` に変更（9001 の 16 進数） |

上の省略 path は `srcs/requirements/` からの相対 path。`/proc/net/tcp*` の port は 16 進数、`0A` は LISTEN。

```sh
make
dc ps
docker exec wordpress sh -c "grep ':2329 .* 0A ' /proc/net/tcp /proc/net/tcp6"
curl --noproxy '*' -ksS --fail https://kishino.42.fr/ -o /tmp/inception-fpm.html
```

**期待結果：** WordPress healthy、PHP ページ本文と管理画面が機能する。FPM は内部 port なので host の `ports:` は追加しない。
A を同時に適用したままなら確認 URL に `:8443` を付ける。

### C. MariaDB の例：3306 → 3307

| 変更箇所 | 対応 |
|---|---|
| `mariadb/conf/99-inception.cnf`／Dockerfile | `port=3307`／`EXPOSE 3307` |
| `wordpress/tools/entrypoint.sh` の接続待ち | `mariadb -h mariadb` に `-P 3307` を追加 |
| 同 script の `wp config create` | `--dbhost=mariadb:3307` |
| 既存 volume 内の `wp-config.php` | 下記 WP-CLI で `DB_HOST` を更新 |

```sh
wp config set DB_HOST 'mariadb:3307'
make
dc ps
wp config get DB_HOST
docker exec -it wordpress mariadb -h mariadb -P 3307 -u wpuser -p wordpress
```

**期待結果：** アプリ user で TCP 接続でき、SQL と Web ページ／管理画面が機能する。
本 DB healthcheck は socket 接続なので port 指定変更は不要だが、TCP 3307 成功の証明にもならない。

**復元：** 実演で変えた設定と永続値を元に戻して `make`、§6 の GET／ブラウザ確認を行う。
A は `home`／`siteurl` も元 URL、C は `DB_HOST` も `mariadb:3306` に戻す。`git diff` だけでは volume 内の復元漏れは検出できない。
`make re` でデータを消して設定変更を成立させる方法は、既存サイト維持の実演として使わない。

## 14. Bonus — 本実装では未実装

**評価項目：** mandatory が全項目完全に機能する場合だけ採点。追加 service ごとに自作 Dockerfile・専用 container、必要なら専用 volume を用意する。
以下の許可された追加機能を実際に確認し、各 1 点・最大 5 点。自由選択は仕組みと有用性も説明する。

| 評価項目の日本語訳 | 実装した場合の確認方法 | 口頭説明・周辺知識 |
|---|---|---|
| WordPress の cache 管理に Redis を導入 | Redis の応答に加え、WordPress の object cache 接続と利用を確認 | 「繰り返す DB 問い合わせ結果等を memory に cache し、DB の負荷を減らします。」起動しているだけでは連携の証明にならない。 |
| WordPress volume を参照する FTP server container を用意 | FTP client でログイン・upload し、同じファイルを WordPress volume で確認 | 「共有 volume にファイルを転送します。」FTP と SFTP は別 protocol。認証・権限と data connection も理解する。 |
| PHP 以外で簡単な static website を作成 | サイト表示、配信ファイル、独自 Dockerfile／container を確認 | 「自己紹介等の完成済みファイルを配信し、リクエストごとの PHP 実行を必要としません。」 |
| Adminer を導入 | browser から DB へログインし WordPress の table を確認 | 「browser で DB を操作する管理用 client です。MariaDB 自体や WordPress dashboard とは別です。」 |
| 有用だと思う service を自由に追加 | その service の実機能を操作し、既存構成への効果を示す | 「何を解決するか、どう動くか、なぜこの構成に必要か」を説明する。起動だけで完了にしない。 |

## 参照先

- 評価条件：[42 EvalHub — Inception](https://www.42evalhub.com/common/inception)、リポジトリの `inception.pdf`。
- 実装根拠：`Makefile`、`srcs/docker-compose.yml`、`srcs/requirements/`、`README.md`、`USER_DOC.md`、`DEV_DOC.md`。
- 補足：[Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/)、[Debian releases](https://www.debian.org/releases/)。
