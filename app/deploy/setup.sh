#!/usr/bin/env bash
# EC2（Ubuntu Server 26.04 LTS）に スキマ日南 を入れるスクリプト。
# 使い方: sudo bash setup.sh <ドメイン名>
#   例:   sudo bash setup.sh skima.example.jp
# 事前に: セキュリティグループで 22（SSH）・80・443 を開け、ドメインのAレコードをElastic IPに向けておく。
set -euo pipefail

DOMAIN="${1:?ドメイン名を指定してください}"
REPO="https://github.com/skawashin1122/ZenjoCon-B.git"
APP_DIR=/opt/skima

echo "== 1. 必要なソフトを入れる"
apt-get update
apt-get install -y python3-venv python3-pip nginx postgresql git certbot python3-certbot-nginx

echo "== 2. アプリ専用のユーザーを作る（rootでは動かさない）"
id skima >/dev/null 2>&1 || useradd --system --no-create-home --home-dir "$APP_DIR" --shell /usr/sbin/nologin skima
install -d -o skima -g skima "$APP_DIR"   # 空のフォルダを作って、そこに git clone する

echo "== 3. コードを取ってくる"
if [ ! -d "$APP_DIR/.git" ]; then
  sudo -u skima git clone "$REPO" "$APP_DIR"
else
  sudo -u skima git -C "$APP_DIR" pull --ff-only
fi

echo "== 4. Pythonの仮想環境"
sudo -u skima python3 -m venv "$APP_DIR/app/.venv"
sudo -u skima "$APP_DIR/app/.venv/bin/pip" install -q -r "$APP_DIR/app/requirements.txt" -r "$APP_DIR/app/requirements-prod.txt"

echo "== 5. PostgreSQL のデータベースとユーザー"
DB_PASS="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='skima'" | grep -q 1; then
  sudo -u postgres psql -c "CREATE USER skima WITH PASSWORD '$DB_PASS';"
  sudo -u postgres psql -c "CREATE DATABASE skima OWNER skima;"
  NEW_DB=1
fi

echo "== 6. .env（秘密の設定）"
ENV_FILE="$APP_DIR/app/.env"
if [ ! -f "$ENV_FILE" ]; then
  cp "$APP_DIR/app/.env.example" "$ENV_FILE"
  sed -i "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+psycopg://skima:${DB_PASS}@localhost/skima|" "$ENV_FILE"
  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')|" "$ENV_FILE"
  sed -i "s|^TEACHER_PASSCODE=.*|TEACHER_PASSCODE=$(python3 -c 'import secrets; print(secrets.token_urlsafe(9))')|" "$ENV_FILE"
  sed -i "s|^BASE_URL=.*|BASE_URL=https://${DOMAIN}|" "$ENV_FILE"
  chown skima:skima "$ENV_FILE"
  chmod 600 "$ENV_FILE"   # 持ち主（skima）しか読めないようにする
  echo "!! $ENV_FILE に GEMINI_API_KEY と LINE_CHANNEL_ACCESS_TOKEN を書き込んでください"
  echo "!! 教員パスコードは $ENV_FILE の TEACHER_PASSCODE を確認してください"
elif [ "${NEW_DB:-0}" = 1 ]; then
  echo "!! DBユーザーを新しく作りました。$ENV_FILE の DATABASE_URL を更新してください"
fi

echo "== 7. systemd と Nginx"
cp "$APP_DIR/app/deploy/skima.service" /etc/systemd/system/skima.service
sed "s/SERVER_NAME/${DOMAIN}/" "$APP_DIR/app/deploy/nginx-skima.conf" > /etc/nginx/sites-available/skima
ln -sf /etc/nginx/sites-available/skima /etc/nginx/sites-enabled/skima
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl daemon-reload
systemctl enable --now skima
systemctl reload nginx

echo "== 8. HTTPS（Let's Encrypt）"
echo "次のコマンドで証明書を取得してください（メールアドレスの入力を求められます）:"
echo "  sudo certbot --nginx -d ${DOMAIN}"
echo "完了後、https://${DOMAIN}/api/health が {\"ok\":true} を返せば成功です。"
