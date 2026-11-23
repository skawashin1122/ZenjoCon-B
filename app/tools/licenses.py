"""使っているオープンソース（Pythonのライブラリ）のライセンス一覧を作る。

使い方: .venv/Scripts/python -X utf8 tools/licenses.py > THIRD_PARTY_LICENSES.md
仮想環境に入っているライブラリを全部（間接的に使うものも）調べる。
"""
import re
from importlib.metadata import distributions

# EC2（Linux）でだけ入れるもの（パソコンの仮想環境には無いので手で書く）
PROD_ONLY = {
    "gunicorn": ("MIT", "https://gunicorn.org"),
    "psycopg": ("LGPL-3.0-only", "https://www.psycopg.org"),
    "psycopg-binary": ("LGPL-3.0-only", "https://www.psycopg.org"),
}
SKIP = {"pip", "setuptools", "wheel"}


def license_of(meta) -> str:
    if meta.get("License-Expression"):
        return meta["License-Expression"]
    classifiers = [c.split(" :: ")[-1] for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
    if classifiers:
        return " / ".join(dict.fromkeys(classifiers))
    lic = (meta.get("License") or "").strip()
    if lic and len(lic) < 60 and "\n" not in lic:
        return lic
    return "（不明：配布元で確認）"


def homepage(meta) -> str:
    for url in meta.get_all("Project-URL") or []:
        label, _, link = url.partition(",")
        if re.search(r"home|source|repository|documentation", label, re.I):
            return link.strip()
    return (meta.get("Home-page") or "").strip()


rows = {}
for d in distributions():
    name = d.metadata["Name"]
    if not name or name.lower() in SKIP:
        continue
    rows[name.lower()] = (name, d.version, license_of(d.metadata), homepage(d.metadata))
for name, (lic, url) in PROD_ONLY.items():
    rows.setdefault(name, (name, "（EC2で導入）", lic, url))

print("# 使用しているオープンソースソフトウェアのライセンス一覧")
print()
print("スキマ日南ファーム＆シーは、次のオープンソースソフトウェアを利用しています。")
print("この一覧は `tools/licenses.py` で自動生成しています（Pythonのライブラリ。間接的に使うものを含む）。")
print()
print("| ライブラリ | バージョン | ライセンス | 配布元 |")
print("| :--- | :--- | :--- | :--- |")
for key in sorted(rows):
    name, ver, lic, url = rows[key]
    print(f"| {name} | {ver} | {lic} | {url} |")
print()
print("## サーバーのソフトウェア（EC2・Ubuntu のパッケージ）")
print()
print("| ソフトウェア | ライセンス |")
print("| :--- | :--- |")
print("| Ubuntu Server 26.04 LTS | 各パッケージのライセンス（主に GPL ほか） |")
print("| Nginx | BSD-2-Clause |")
print("| PostgreSQL | PostgreSQL License |")
print("| Certbot | Apache-2.0 |")
print()
print("## 外部サービス（利用規約に従って利用）")
print()
print("- Google Gemini API（Google の利用規約・Gemini API 追加利用規約）")
print("- LINE Messaging API（LINE ヤフーの利用規約）")
print("- Amazon Web Services（AWS Academy の利用条件）")
print("- Duck DNS、Let's Encrypt")
print()
print("## 発表スライド")
print()
print("| 素材 | ライセンス |")
print("| :--- | :--- |")
print("| アイコン：Font Awesome Free（react-icons 経由で画像化） | CC BY 4.0（https://fontawesome.com/license/free） |")
print("| フォント：BIZ UDPゴシック（Morisawa） | SIL Open Font License 1.1 |")
print()
print("## データ")
print()
print("- 統計：日南市ミニ統計 令和4年版〜令和8年版（日南市総合政策課）")
print("- 画面のアイコンは Unicode の絵文字（端末の標準フォントで表示）。画像素材は使用していません。")
