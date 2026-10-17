# AGENTS.md

- 仕様は `PLAN.md` が正。迷ったら PLAN.md に従い、変えるときは PLAN.md も更新する
- 締切は 16:00。**動くものを最優先**。PLAN.md 11章の「削る順番」に従ってスコープを削る
- 実装順：data/generate.py → backend/load.py → queries.py → main.py → llm.py → frontend
- 各段階で動作確認してから次へ。5章「期待される結果」（N07 が感染源1位）をテストとして使う
- Claude API は使わない。LLM は ai&（OpenAI互換、環境変数で base_url とモデルを指定）
- LLM が生成した Cypher は必ず読み取り専用で実行（PLAN.md 9-2）
- 依存は requirements.txt のものだけ。フロントはビルドなしの HTML＋素のJS＋Cytoscape.js
- ファイルは差分ではなく完全な形で書く
- 複数のエージェント（Claude Code / Codex）で分担する場合、担当外のファイルは編集しない。API の形（PLAN.md 8章）を変えるときは PLAN.md を先に更新する

## 環境（前日 2026-10-16 に準備済み）

- このフォルダがリポジトリのルート（PLAN.md 3章の `wardtrace/` に当たる）
- **Python**：`.venv/`（Python 3.14）に requirements.txt の6パッケージを導入済み。実行は `.venv/bin/python`、または `source .venv/bin/activate` してから。入ったバージョンは `requirements.lock.txt` に記録
- **Neo4j**：Docker イメージ `neo4j:5`（Community 5.26.32）を取得済みで、オフラインでも起動できる。認証は `neo4j/wardtrace123`、ポートは 7474（Browser）／7687（bolt）で接続を確認済み
- **Docker CLI** は `~/.docker/bin/docker`。新しいシェルなら PATH に入っている。見つからないときは `export PATH="$HOME/.docker/bin:$PATH"`
- **Cytoscape.js**：`vendor/cytoscape.min.js`（v3.34.3）をローカルに保存済み。CDN で読み込むときも同じ版（`cytoscape@3.34.3`）を使い、会場のネットが落ちたらこのファイルに切り替える
- **パッケージを追加・更新しない**。必要になったら先に人に確認する
- テスト：`requirements-dev.txt`（pytest・httpx）を `.venv` に導入済み。`.venv/bin/python -m pytest -q tests` で 5章のシナリオを確認できる（Neo4j の起動が必要。テストは `/api/reset` でデータを入れ直す）

## GitHub に上げないもの（`.gitignore` 設定済み）

- `.venv/`：各自 `pip install -r requirements.txt` で作り直せる
- `neo4j-data/`：docker compose が作る DB のファイル
- `.env`：**ai& の API キーが入る。絶対にコミットしない**。リポジトリには値を空にした `.env.example` だけを置く
- コードや README、ログに API キーを直接書かない

## 個人情報を公開しない（公開リポジトリ）

- リポジトリは `https://github.com/MyriaMontis/wardtrace`（公開）。push したものは誰でも見られる
- 作者の本名・メールアドレス・大学名・学籍番号、PC のユーザー名や絶対パス（`/Users/...`）を、コード・README・コミットメッセージに書かない
- コミットの作者は、このリポジトリだけの設定（`git config` のローカル設定）で `MyriaMontis` と GitHub の noreply アドレスにしてある。**変更しない・`--author` で上書きしない**
- 提出フォームに書くチーム名やメールアドレスは、リポジトリに入れない
- push の前に `git diff --cached` で、上のような情報が入っていないか確認する
