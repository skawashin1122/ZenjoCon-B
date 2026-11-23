# スキマ日南ファーム＆シー（アプリ本体）

写真と声だけで、農家・漁師が短時間のお手伝いを募集できるWebアプリ。

## いまできること（第1週）
| 機能 | 状態 |
| :--- | :--- |
| 生産者画面：「写真をとる」「話して伝える」の2ボタン | ✅ |
| 写真をスマホ側で縮小（長辺1280px）、声を16kHzのWAVに変換して送信 | ✅ |
| Gemini で写真＋声 → 求人の下書き（JSON・型チェック付き） | ✅（APIキーを入れれば本物、無ければ仮AI） |
| 足りない項目だけを声で聞き直す | ✅ |
| 下書きの読み上げ（ブラウザの音声合成） | ✅ |
| ルール判定：船上NG・最低賃金・時刻の順番・過去の日付 | ✅（自動テストあり） |
| 高校生に表示できるかの判定：5〜22時・15kg以下・陸上 | ✅（自動テストあり） |
| 学生向け求人カード＋「日南の統計ひとこと」 | ✅ |
| 教員の承認画面・マッチング・応募・LINE通知 | 第2週 |
| ログイン、S3、PostgreSQL、EC2公開 | 第2週 |

## パソコンで動かす（Windows）

```bash
cd app
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
```

学校PCでは、SQLAlchemy の高速化用DLLがアプリ制御ポリシーでブロックされます。そのため、DLLを使わない版に入れ直します（性能はほぼ変わりません）。

```bash
DISABLE_SQLALCHEMY_CEXT=1 .venv/Scripts/python -m pip install --force-reinstall --no-deps --no-binary sqlalchemy sqlalchemy
```

起動：

```bash
.venv/Scripts/python -m uvicorn skima.main:app --reload
```

ブラウザで http://localhost:8000 を開く。

### 本物の Gemini を使う
1. `.env.example` をコピーして `.env` を作る
2. `GEMINI_API_KEY=` のあとにキーを貼る（**.env は Git に入らない。チャットや画面にも貼らない**）
3. `MIN_WAGE` を宮崎労働局で確認した最新の最低賃金にする

`.env` が無い、またはキーが空のときは、画面右上に「テスト用の仮AI」と出て、決まった下書きを返します。

### テスト
```bash
.venv/Scripts/python -m pytest -q
```

## フォルダ構成
```
app/
├─ skima/
│  ├─ main.py      画面とAPIの入口
│  ├─ ai.py        Gemini 呼び出し（＋テスト用の仮AI）
│  ├─ rules.py     安全・法令の判定（AIに任せない部分）
│  ├─ schemas.py   AIが返す下書きの形（JSONスキーマ）
│  ├─ models.py    データベースの表（5つ）
│  ├─ jobs.py      下書き⇔求人の変換、読み上げ文
│  ├─ stats.py     日南の統計ひとこと
│  ├─ templates/   画面のHTML
│  └─ static/      CSS・JavaScript（録音・写真縮小）
└─ tests/          自動テスト
```

## 注意
- カメラ・マイクは **localhost か HTTPS** でないと使えない。スマホ実機で試すのは、EC2をHTTPS化してから（第2週）。
- 写真・音声はサーバーに保存せず、AIの解析後に捨てている。
