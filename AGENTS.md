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

## 実装状況（2026-10-17 時点）

PLAN.md の実装順はすべて完了し、12章のデモ（P12陽性 → Trace depth2 → Find source → Ask）が最後まで通る。テストは28件すべて通過。詳しい使い方・API・画面の説明は **README.md**（英語）にある。

- 起動手順：`docker compose up -d` → `.venv/bin/python data/generate.py` → `.venv/bin/python -m backend.load` → `.venv/bin/python -m uvicorn backend.main:app --port 8000` → http://localhost:8000
- Claude Code のプレビューでは `.claude/launch.json` の `wardtrace`（uvicorn、ポート 8000、`--reload` 付き）で起動できる。`frontend/` を作ったあとは、`main.py` が読み込まれ直すまで `/` が配信されない（`--reload` は .py の変更で再起動する）
- PLAN.md からの追加・変更（PLAN.md にも反映済み）
  - `/api/persons` は `test_date` と `onset_date` も返す
  - `/api/trace` は `second_gen_if_time_ignored`（時間順の条件だけを外した2段目の人数。depth 1 は null）も返す
  - 7-1：2段目から外すのは「感染可能期間内に起点と濃厚接触した人」だけ（期間外の接触だけの人は2段目に出る）
  - 7-2：発熱陰性者は `x.status <> "fever_negative"` で候補からも明示的に除外
  - 追跡後のレイアウトは concentric（起点を中心に1段目・2段目・無関係の順で外側へ）。初期表示は cose。追跡後は右上に最初の配置の縮小図（Ward overview）を出し、全体図とのつながりを残す
- ai&：本命 `openai/gpt-oss-120b`（日英6問で正解、1問2〜4秒）。予備 `deepseek-ai/deepseek-v4-flash` も6問正解だが遅い。ユーザーは gpt-oss を希望。回答の言語は Python 側で判定して指示している
- 期待される数字（違ったら Reset）
  - 初期データ：陽性者は P05・P18 の2人。**P12 は untested**（検査日 10/16・発症日 10/15 は記録済み、隔離日は空）でグラフでは灰色。感染源は N07 だけ（2人と接触）
  - デモで P12 を Mark positive した後：P12 が赤くなる。P12 起点の感染可能期間 10/13〜10/16、1段目6人（D01, N05, N07, P08, P25, R01）、2段目26人（時間順を無視すると34人）。感染源は N07 だけ（P05・P12・P18 の3人と接触）。P03・P22 は出ない
  - グラフ：45人、濃厚接触のペア304本
  - Ask「Who did N07 care for on night shifts?」→ 患者18人

## 画面の操作（ブラウザを操作する AI 向け）

画面は1枚（1440×900 想定）。英語のラベルの横に（）で日本語の説明がある。操作に使う要素：

| 要素 | セレクタ | 動き |
| --- | --- | --- |
| 対象者 | `#person`（select） | 値は ID（例 `P12`）。初期値は P12。変えると検査日・発症日が自動で入る（記録済みの日付があればそれ、なければ検査日 2026-10-16・発症日は空）。選ばれている人はグラフで青く点滅する（クラス `picked`、700ms ごとに `pulse-on` を切り替え） |
| 検査日・発症日 | `#test-date`, `#onset-date`（date） | `YYYY-MM-DD`。発症日は任意 |
| Mark positive | `#mark` | `POST /api/positive` のあと、選択中の depth で追跡するが、**元の配置のまま見せるところ（Step 1、depth 2 なら Step 2）で止める**。輪への並べ替えはしない（depth 1 なら約2秒）。データが変わるので、終わったら Reset する |
| Depth | `input[name=depth]`（value `1` / `2`） | 初期値は 1。Reset で 1 に戻る |
| Trace contacts | `#trace` | `#person` の人を起点に `POST /api/trace`。表 `#tab-contacts` とステータスはすぐ出る。グラフは3段階で見せる：① 最初の配置のまま起点と1段目にズーム → ② 2段目を追加（depth 2 のみ）→ ③ 起点中心の輪に並べ替え。各段階の説明は字幕 `#caption`（左上）。depth 2 で約8〜10秒、終わるまでボタンは無効 |
| Find source | `#source` | `GET /api/source`。候補を太い赤枠、陽性者への線を赤にする。結果は `#tab-source` |
| 質問欄 | `#question`（textarea） | 空のまま送ると placeholder の質問を送る |
| 質問の候補 | `.chip`（`data-q` に質問文） | 押すとすぐ送信 |
| Ask | `#ask` | `POST /api/ask`。2〜4秒かかる。結果は `#tab-ask`（回答 `.answer`、Cypher は `<details>` の中） |
| Reset | `#reset` | `POST /api/reset` で初期データに戻し、グラフも描き直す。人数表示を隠し、depth を 1 に戻す |
| 人数表示 | `#counts`（グラフの上の行） | 追跡すると出る。例 `P12 1st gen 6 / 2nd gen 26 (34 without time order)`。1段目をクリック中は `· via N07: 8` が付く。感染源推定・質問・Reset で隠れる |
| 1段目のノード | `cy.getElementById('N07').emit('tap')` | depth 2 の追跡後、その人を経由する2段目だけ濃くし（他は `faint` クラスで薄い）、経路の線（`via-path`）を出し、2段目の表を絞る。同じノード・起点・背景をもう一度押すと全員に戻る。1段目以外のノードは今までどおり接触一覧を出す |
| ステータス | `#status` | 直前の操作の結果（例 `Traced P12: 6 first-gen, 26 second-gen (34 if time order ignored)`）。エラーは `Error: ...` |
| タブ | `.tabs button[data-tab=contacts\|source\|ask]` | 結果パネルの切り替え |
| 病棟全体の縮小図 | `#mini-wrap`（中の図は `#mini`、変数 `mini`） | 追跡すると右上に出る。最初の配置のまま、メインと同じ色で強調する。クリックするとメインの図を最初の配置に戻し（色はそのまま）、縮小図は隠れる。Reset でも隠れる |
| グラフ | `#cy`（Cytoscape。ページ上の変数 `cy`） | ノードをクリックすると、その人の接触一覧が `#tab-contacts` に出る。表の行をクリックするとそのノードに移動する |

- 処理中はボタンが無効になり、文言が `Tracing…` などに変わる。元の文言に戻るまで待つ
- 追跡のアニメーションは約8〜10秒かかる。完了は `#trace` が押せる状態（`disabled` でない）に戻ったことで判定する。スクリーンショットを撮ると描画が遅れることがあるので、途中経過は `#caption` のテキストで確かめる
- 表示の確認は、スクリーンショットより `#status` と各タブのテキストを読むほうが確実

## コミットのルール

- コミットメッセージや PR に Claude のクレジット（`Co-Authored-By: Claude` など）を入れない
- push の前に、個人情報（下の章）と API キーが入っていないか確認する

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
