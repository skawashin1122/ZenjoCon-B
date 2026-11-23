# EC2 に公開する手順（AWS Academy Learner Lab）

所要時間：30〜45分。**先生と一緒に**行ってください（Learner Lab の操作・Gemini APIキーの入力があるため）。

## 0. 用意するもの
- AWS Academy Learner Lab（Start Lab で起動し、AWS が緑になってから）
- Gemini APIキー（`.env` に書くだけ。チャットや画面共有に出さない）
- GitHub リポジトリが**非公開**なら：EC2 から読めるようにする（下の「非公開リポジトリのとき」）
- Duck DNS のサブドメインとトークン（次の「0.5」）

## 0.5 Duck DNS でサブドメインを作る（無料）
1. https://www.duckdns.org を開き、先生のアカウント（GitHub・Google など）でサインイン
2. 「sub domain」に名前を入れて「add domain」（例：`skima-nichinan` → `skima-nichinan.duckdns.org`）
   - 英小文字・数字・ハイフンだけ。発表スライドにも載るので分かりやすい名前に
3. 画面上部の **token** を控えておく（パスワードと同じ扱い。チャット・スライド・Git に載せない）
4. IP の欄はそのままでOK（setup.sh が自動で登録する）

## 1. EC2 を起動する（AWSコンソール → EC2 → インスタンスを起動）
| 項目 | 設定 |
| :--- | :--- |
| 名前 | `skima` |
| AMI | Ubuntu Server 26.04 LTS |
| インスタンスタイプ | `t3.small`（無ければ `t2.micro`） |
| キーペア | `vockey`（Learner Lab の AWS Details から `labsuser.pem` をダウンロード） |
| セキュリティグループ | SSH(22)：マイIP、HTTP(80)：0.0.0.0/0、HTTPS(443)：0.0.0.0/0 |
| ストレージ | 16 GiB |
| 高度な詳細 → IAM インスタンスプロファイル | **`LabInstanceProfile`**（S3 を鍵なしで使うため） |
| 高度な詳細 → メタデータのバージョン | **V2 のみ（トークン必須）** |

## 2. Elastic IP を付ける
EC2 → Elastic IP → 割り当て → 作ったインスタンスに関連付け。
（Learner Lab のセッションが切れて EC2 が止まっても、IP が変わらなくなる）

## 3. 入る → セットアップ
```bash
ssh -i labsuser.pem ubuntu@<Elastic IP>
curl -fsSLO https://raw.githubusercontent.com/skawashin1122/ZenjoCon-B/main/app/deploy/setup.sh
sudo bash setup.sh skima-nichinan        # ← 0.5 で作ったサブドメイン
```
- 途中で「Duck DNS のトークン」を聞かれるので貼り付けて Enter（画面には表示されません）
  - トークンは `/etc/skima/duckdns.env`（root だけが読める）に保存されます
- Duck DNS に Elastic IP が登録され、以後は**起動時と30分ごとに自動更新**されます
- リポジトリが非公開だと `curl` が失敗します → 下の「非公開リポジトリのとき」を先に
- S3 バケット（公開ブロック・暗号化・1日で自動削除）も自動で作られます
- 最後に「`<サブドメイン>.duckdns.org → <IP>（Duck DNS OK）`」と出れば、次の HTTPS に進めます

## 4. Gemini APIキーを入れる
```bash
sudo nano /opt/skima/app/.env      # GEMINI_API_KEY= のあとに貼る
sudo systemctl restart skima
```

## 5. HTTPS にする
```bash
sudo certbot --nginx -d skima-nichinan.duckdns.org
```
証明書は90日ごとに自動で更新されます（certbot のタイマー）。
メールアドレスの入力と、Let's Encrypt の利用規約への同意を求められます（先生が行う）。

## 6. 確認
- スマホで `https://<ドメイン>/` → ログイン画面が出る
- 生産者でログイン → 「写真をとる」「話して伝える」が使える（HTTPS なのでカメラ・マイクが動く）
- 教員のパスコード：`sudo grep TEACHER_PASSCODE /opt/skima/app/.env`

## よくあること
| 症状 | 対処 |
| :--- | :--- |
| Learner Lab を再開したら開けない | Learner Lab で Start Lab → EC2 が「実行中」になるまで待つ（アプリは自動で起動する） |
| 下書きが作れない（502） | `sudo journalctl -u skima -n 50` でエラーを見る。APIキー・モデル名を確認 |
| S3 のエラー | EC2 に `LabInstanceProfile` が付いているか確認 |
| ドメインで開けない | `sudo systemctl start duckdns && journalctl -u duckdns -n 5` で「更新OK」か確認。失敗ならトークンを `/etc/skima/duckdns.env` で直す |
| certbot が失敗する | Duck DNS の登録直後は数分待つ。セキュリティグループで 80 番が開いているか確認 |
| コードを更新したい | `sudo -u skima git -C /opt/skima pull && sudo systemctl restart skima` |

## 非公開リポジトリのとき
いちばん簡単なのは、本選期間だけリポジトリを公開にすることです（`.env`・PDF は入っていません）。
公開したくない場合は、EC2 で `ssh-keygen` を作り、GitHub のリポジトリ設定 → Deploy keys に公開鍵（読み取り専用）を登録し、
`sudo REPO=git@github.com:skawashin1122/ZenjoCon-B.git bash setup.sh skima-nichinan` で実行します。
