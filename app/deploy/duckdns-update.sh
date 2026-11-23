#!/usr/bin/env bash
# Duck DNS に、このEC2のIPアドレスを登録する（タイマーで30分ごと・起動時に実行）。
# 設定は /etc/skima/duckdns.env（root だけが読める）:
#   DUCKDNS_SUBDOMAIN=skima-nichinan   ← 「.duckdns.org」の前の部分
#   DUCKDNS_TOKEN=xxxxxxxx-xxxx-...    ← Duck DNS のトークン（秘密）
set -euo pipefail
source /etc/skima/duckdns.env

# ip= を空にすると、Duck DNS が「アクセスしてきたIP」を登録する（＝このEC2のパブリックIP）
# トークンをコマンドの引数に出さないよう、curl の設定を標準入力から渡す
result="$(curl -sf -K - <<EOF
url = "https://www.duckdns.org/update?domains=${DUCKDNS_SUBDOMAIN}&token=${DUCKDNS_TOKEN}&ip="
EOF
)"
if [ "$result" = "OK" ]; then
  echo "Duck DNS 更新OK: ${DUCKDNS_SUBDOMAIN}.duckdns.org"
else
  echo "Duck DNS 更新失敗（サブドメイン名とトークンを確認）: $result" >&2
  exit 1
fi
