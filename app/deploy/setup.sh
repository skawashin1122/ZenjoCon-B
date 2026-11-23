#!/usr/bin/env bash
# EC2（Ubuntu Server 26.04 LTS）に スキマ日南 を入れるスクリプト。手順は deploy/EC2手順.md
#
# 使い方: sudo bash setup.sh <Duck DNS のサブドメイン>
#   例:   sudo bash setup.sh skima-nichinan      → skima-nichinan.duckdns.org を使う
#   Duck DNS のトークンは、実行中に聞かれたら貼り付ける（画面には表示されない）
# 事前に:
#   - Duck DNS（https://www.duckdns.org）でサブドメインを作っておく
#   - EC2 に IAM インスタンスプロファイル「LabInstanceProfile」を付ける（S3を鍵なしで使うため）
#   - Elastic IP を付ける、セキュリティグループで 22・80・443 を開ける
set -euo pipefail

REPO="${REPO:-https://github.com/skawashin1122/ZenjoCon-B.git}"
APP_DIR=/opt/skima

# --- インスタンスメタデータ（IMDSv2：トークンを取ってから読む）
IMDS_TOKEN="$(curl -sf -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 300')"
imds() { curl -sf -H "X-aws-ec2-metadata-token: $IMDS_TOKEN" "http://169.254.169.254/latest/meta-data/$1"; }
REGION="$(imds placement/region)"
PUBLIC_IP="$(imds public-ipv4 || true)"

SUB="${1:?Duck DNS のサブドメインを指定してください（例: sudo bash setup.sh skima-nichinan）}"
SUB="${SUB%.duckdns.org}"   # 「xxx.duckdns.org」と書いても「xxx」として扱う
[[ "$SUB" =~ ^[a-z0-9-]+$ ]] || { echo "サブドメインは英小文字・数字・ハイフンだけです: $SUB"; exit 1; }
DOMAIN="${SUB}.duckdns.org"
[ -n "$PUBLIC_IP" ] || { echo "パブリックIPがありません。Elastic IP を付けてください"; exit 1; }
echo "ドメイン: $DOMAIN ／ IP: $PUBLIC_IP ／ リージョン: $REGION"

# --- Duck DNS のトークン（root だけが読めるファイルに保存。Git には入らない）
DUCK_ENV=/etc/skima/duckdns.env
if [ ! -f "$DUCK_ENV" ]; then
  if [ -z "${DUCKDNS_TOKEN:-}" ]; then
    read -rsp "Duck DNS のトークンを貼り付けて Enter（表示されません）: " DUCKDNS_TOKEN; echo
  fi
  [ -n "$DUCKDNS_TOKEN" ] || { echo "トークンが空です"; exit 1; }
  install -d -m 700 /etc/skima
  umask 077
  printf 'DUCKDNS_SUBDOMAIN=%s\nDUCKDNS_TOKEN=%s\n' "$SUB" "$DUCKDNS_TOKEN" > "$DUCK_ENV"
  umask 022
  unset DUCKDNS_TOKEN
fi

echo "== 1. 必要なソフトを入れる"
apt-get update
apt-get install -y python3-venv python3-pip nginx postgresql git certbot python3-certbot-nginx curl

echo "== 2. アプリ専用のユーザーを作る（rootでは動かさない）"
id skima >/dev/null 2>&1 || useradd --system --no-create-home --home-dir "$APP_DIR" --shell /usr/sbin/nologin skima
install -d -o skima -g skima "$APP_DIR"   # 空のフォルダを作って、そこに git clone する

echo "== 3. コードを取ってくる"
if [ ! -d "$APP_DIR/.git" ]; then
  sudo -u skima git clone "$REPO" "$APP_DIR"
else
  sudo -u skima git -C "$APP_DIR" pull --ff-only
fi

echo "== 3.5 Duck DNS にIPを登録（起動時と30分ごとに自動更新）"
install -m 755 "$APP_DIR/app/deploy/duckdns-update.sh" /usr/local/bin/duckdns-update.sh
cp "$APP_DIR/app/deploy/duckdns.service" "$APP_DIR/app/deploy/duckdns.timer" /etc/systemd/system/
systemctl daemon-reload
/usr/local/bin/duckdns-update.sh
systemctl enable --now duckdns.timer

echo "== 4. Pythonの仮想環境"
sudo -u skima python3 -m venv "$APP_DIR/app/.venv"
sudo -u skima "$APP_DIR/app/.venv/bin/pip" install -q -r "$APP_DIR/app/requirements.txt" -r "$APP_DIR/app/requirements-prod.txt"

echo "== 5. PostgreSQL のデータベースとユーザー"
DB_PASS="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
NEW_DB=0
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='skima'" | grep -q 1; then
  sudo -u postgres psql -c "CREATE USER skima WITH PASSWORD '$DB_PASS';"
  sudo -u postgres psql -c "CREATE DATABASE skima OWNER skima;"
  NEW_DB=1
fi

echo "== 6. .env（秘密の設定）"
ENV_FILE="$APP_DIR/app/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "-- S3バケットを作る（LabInstanceProfile の一時的な認証情報を使う）"
  BUCKET="$(sudo -u skima "$APP_DIR/app/.venv/bin/python" "$APP_DIR/app/deploy/create_bucket.py" "$REGION")"
  echo "   バケット: $BUCKET（uploads/ は1日で自動削除）"

  cp "$APP_DIR/app/.env.example" "$ENV_FILE"
  sed -i "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+psycopg://skima:${DB_PASS}@localhost/skima|" "$ENV_FILE"
  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')|" "$ENV_FILE"
  sed -i "s|^TEACHER_PASSCODE=.*|TEACHER_PASSCODE=$(python3 -c 'import secrets; print(secrets.token_urlsafe(9))')|" "$ENV_FILE"
  sed -i "s|^BASE_URL=.*|BASE_URL=https://${DOMAIN}|" "$ENV_FILE"
  sed -i "s|^S3_BUCKET=.*|S3_BUCKET=${BUCKET}|" "$ENV_FILE"
  sed -i "s|^AWS_REGION=.*|AWS_REGION=${REGION}|" "$ENV_FILE"
  chown skima:skima "$ENV_FILE"
  chmod 600 "$ENV_FILE"   # 持ち主（skima）しか読めないようにする
  echo "!! $ENV_FILE に GEMINI_API_KEY を書き込んでください（LINEは作成後に）"
  echo "!! 教員パスコードは $ENV_FILE の TEACHER_PASSCODE で確認できます"
elif [ "$NEW_DB" = 1 ]; then
  echo "!! DBユーザーを新しく作りました。$ENV_FILE の DATABASE_URL を更新してください"
fi

echo "== 7. systemd と Nginx"
cp "$APP_DIR/app/deploy/skima.service" /etc/systemd/system/skima.service
sed "s/SERVER_NAME/${DOMAIN}/" "$APP_DIR/app/deploy/nginx-skima.conf" > /etc/nginx/sites-available/skima
ln -sf /etc/nginx/sites-available/skima /etc/nginx/sites-enabled/skima
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl daemon-reload
systemctl enable skima
systemctl restart skima
systemctl reload nginx

echo "== 8. 動作確認（HTTP）"
sleep 2
curl -sf "http://127.0.0.1:8000/api/health" && echo " ← アプリは動いています"
RESOLVED="$(getent ahostsv4 "$DOMAIN" | awk 'NR==1{print $1}')"
if [ "$RESOLVED" = "$PUBLIC_IP" ]; then
  echo "$DOMAIN → $PUBLIC_IP （Duck DNS OK）"
else
  echo "!! $DOMAIN がまだ $PUBLIC_IP を指していません（今: ${RESOLVED:-なし}）。数分待ってから certbot を実行してください"
fi

echo
echo "== 次にやること"
echo "1) GEMINI_API_KEY を書いたら: sudo systemctl restart skima"
echo "2) HTTPSにする（メールアドレスの入力と利用規約への同意を求められます）:"
echo "     sudo certbot --nginx -d ${DOMAIN}"
echo "3) スマホで https://${DOMAIN}/ を開く"
