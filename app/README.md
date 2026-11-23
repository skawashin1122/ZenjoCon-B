# スキマ日南ファーム＆シー（アプリ本体）

写真と声だけで、農家・漁師が短時間のお手伝いを募集できるWebアプリ。

## いまできること（第2週まで）
| 機能 | 状態 |
| :--- | :--- |
| デモ用ログイン（生産者・生徒は選ぶだけ、教員はパスコード） | ✅ |
| 生産者：写真＋声 → Gemini で求人の下書き → 足りない項目だけ聞き直し → 読み上げ → 公開 | ✅ |
| ルール判定：船上NG・最低賃金・時刻の順番・過去の日付 | ✅ |
| 安全マッチング：承認・5〜22時・15kg以下・陸上・空き時間で絞り込み → スコア順 | ✅ |
| 案内（募集人数×2人に送る）→ 先着で参加確定 → 定員で締切 | ✅ 同時に押されても定員を超えない |
| キャンセル → 募集再開 → 次の順位の人へ案内 | ✅ |
| 通知：アプリ内のお知らせ（LINE風）＋ LINE Messaging API | ✅（LINEはトークン設定後に有効） |
| 教員：保護者同意・学校許可のチェック → 承認／取り消し、参加予定の一覧 | ✅ |
| 高校生：お知らせ・参加／キャンセル・空き時間の登録 | ✅ |
| 求人カードは、案内を受けた生徒・その生産者・教員だけが見られる | ✅ |
| EC2用の設定（Nginx・systemd・PostgreSQL・HTTPS） | ✅ ファイルのみ（未構築） |
| LINEの友だち登録と生徒の結びつけ（Webhook） | 第3週（LINE公式アカウント作成後） |

## パソコンで動かす（Windows）

```bash
cd app
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
```

学校PCでは、SQLAlchemy の高速化用DLLがアプリ制御ポリシーでブロックされます。DLLを使わない版に入れ直してください（性能はほぼ変わりません）。

```bash
DISABLE_SQLALCHEMY_CEXT=1 .venv/Scripts/python -m pip install --force-reinstall --no-deps --no-binary sqlalchemy sqlalchemy
```

起動：

```bash
.venv/Scripts/python -m uvicorn skima.main:app --reload
```

ブラウザで http://localhost:8000 を開く。教員のパスコードは `.env` の `TEACHER_PASSCODE`（初期値 `demo-teacher`）。

> データベースの表の形を変えたときは、`app/skima.db` を消してから起動し直す（デモデータが作り直される）。

### 設定（.env）
`.env.example` をコピーして `.env` を作る。**.env は Git に入らない。チャットや画面にも貼らない。**

| 項目 | 内容 |
| :--- | :--- |
| `GEMINI_API_KEY` | 空なら「テスト用の仮AI」で動く |
| `GEMINI_MODEL` / `GEMINI_FALLBACK_MODEL` | いつものモデル／混雑時の予備。2026-11-23時点で `gemini-3.5-flash-lite`（約2秒）／`gemini-3.5-flash` |
| `MIN_WAGE` | 宮崎労働局で確認した最新の最低賃金 |
| `TEACHER_PASSCODE` | 教員画面のパスコード |
| `SECRET_KEY` | ログイン状態の署名用。空なら起動のたびに作り直す（ログインが切れる） |
| `LINE_CHANNEL_ACCESS_TOKEN` | 空なら LINE には送らず、アプリ内のお知らせだけ |
| `BASE_URL` | 通知に載せるリンクの先頭 |

### テスト
```bash
.venv/Scripts/python -m pytest -q
```

## EC2 に公開する（Ubuntu Server 26.04 LTS）
1. EC2 を起動し、Elastic IP を付ける。セキュリティグループで 22・80・443 を開ける
2. ドメイン名の A レコードを Elastic IP に向ける（方法は先生と相談：学校のドメイン／無料DNS）
3. EC2 で `sudo bash setup.sh <ドメイン名>`（`deploy/setup.sh`）
4. `/opt/skima/app/.env` に `GEMINI_API_KEY`・`LINE_CHANNEL_ACCESS_TOKEN` を書き、`sudo systemctl restart skima`
5. `sudo certbot --nginx -d <ドメイン名>` で HTTPS にする

GitHub のリポジトリが非公開の場合は、EC2 から clone できるように「デプロイキー」を設定する。

## フォルダ構成
```
app/
├─ skima/
│  ├─ main.py             入口・ログイン・デモデータ
│  ├─ routes_producer.py  生産者の画面とAPI
│  ├─ routes_student.py   高校生の画面とAPI・求人カード
│  ├─ routes_teacher.py   教員の画面とAPI
│  ├─ ai.py               Gemini 呼び出し（予備モデル・テスト用の仮AI）
│  ├─ rules.py            安全・法令の判定（AIに任せない部分）
│  ├─ matching.py         安全マッチング（絞り込み→スコア→並べ替え）
│  ├─ applications.py     案内・先着確定・キャンセル
│  ├─ notify.py           通知（アプリ内＋LINE）
│  ├─ auth.py             ログイン状態
│  ├─ schemas.py          AIが返す下書きの形（JSONスキーマ）
│  ├─ models.py           データベースの表（6つ）
│  ├─ jobs.py / stats.py  変換・読み上げ文／日南の統計ひとこと
│  ├─ templates/ static/  画面
├─ deploy/                EC2用（setup.sh・Nginx・systemd）
└─ tests/                 自動テスト
```

## 注意
- カメラ・マイクは **localhost か HTTPS** でないと使えない。スマホ実機で試すのは EC2 を HTTPS 化してから。
- 写真・音声はサーバーに保存せず、AIの解析後に捨てている。
- 地区のとなり合い（`matching.py` の `NEIGHBORS`）はおおよそ。地図で確認して直すこと。
