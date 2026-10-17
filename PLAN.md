# WardTrace（仮）— 院内感染の接触追跡

> +81 Builders ハッカソン（2026-10-17）用の仕様書。Claude Code はこのファイルを正として実装する。

---

## 0. イベント情報

- **日時**：2026-10-17（土）09:30–17:30 / 開発 10:30–16:00（**提出締切 16:00**）
- **会場**：Good Space Kanda Tekko **5階**（階段のみ・4階と間違えない・ドアは必ず閉める）
- **形式**：ソロ／テーブルで一次審査（デモ3分＋質疑1〜2分）→ 上位5チームが決勝（プロジェクター、デモ3分＋質疑1分）
- **スポンサー要件**：1つ以上 → **Neo4j と ai& の両方を使う**
- **審査基準**（各5点）：本当の課題／動くか／技術（AIで良く・速く・簡単に）／発表の分かりやすさ／独創性
- **審査員**：英語圏寄り → デモは英語、UIは日英どちらでも可（ラベルは英語推奨）

---

## 1. プロダクト

**院内で陽性者が出たら、病室・勤務・検査室の記録をグラフでつなぎ、濃厚接触者の連鎖と感染源の候補を、漏れなく・時間順を守って出すツール。**

| 項目 | 内容 |
| --- | --- |
| 課題 | 院内アウトブレイク時、感染対策チーム（ICT）が紙やExcelで接触者を洗い出しており、遅く漏れやすい |
| ユーザー | 病院の感染対策チーム |
| 位置付け | **判断はしない**。洗い出しを速く・漏れなくする補助。最終判断は人 |
| 規模 | **院内（1病棟）に絞る**。日本全体はやらない（人口レベルの接触データは存在しない／定点観測は時系列集計でグラフの問題ではない） |
| 感染症 | **COVID-19** をモデルにする（誰でも分かる） |
| データ | 架空の病棟。個人情報なし |

### COCOAとの違い
COCOAは匿名で「近くにいたかも」を本人に通知するだけで、連鎖は追えなかった。WardTraceは病院が既に持っている記録から、**2段先まで時間順を守った連鎖**と、**複数の陽性者に共通する感染源の候補**を出す。

### 「なぜグラフDB／なぜLLMだけではダメか」
LLMに全記録を渡して「接触者を全部出して」と頼むと：
- 数千件の記録で**取りこぼし**が起きる（接触者の洗い出しで漏れは致命的）
- 同じ質問でも答えが変わる → **再現性・監査ができない**
- **時間順の制約**（BがCと会ったのは、AがBに移した後か？）を確実に守れない

→ **正確さは Neo4j、言葉の窓口は LLM（ai&）**。LLMが書いたCypherも画面に出して、何を調べたか見えるようにする。

---

## 2. 感染症モデル（COVID-19）

| パラメータ | 既定値 | 意味 |
| --- | --- | --- |
| `INFECTIOUS_LOOKBACK_DAYS` | 2 | 感染可能期間の始まり＝**発症日の2日前**（無症状なら検査日の2日前） |
| 感染可能期間の終わり | 隔離日 | 隔離後の接触は数えない |
| `INCUBATION_MIN_DAYS` | 2 | 潜伏期間の下限 |
| `INCUBATION_MAX_DAYS` | 7 | 潜伏期間の上限 |
| `LATENT_DAYS` | 1 | 接触者が他人に移しうるようになるまでの最短日数（2段目の時間順チェックに使う） |
| 濃厚接触の条件 | 下記 | `CONTACT.close = true` |

### 濃厚接触（close）の判定
- 同じ病室に同じ日に滞在（同室患者）→ close
- スタッフが患者を担当（ケア）→ close
- 検査室・X線室で時間が **15分以上** 重なった → close
- 同じ勤務帯のスタッフ同士 → close = false（接触としては記録するが濃厚ではない）

### 時間順を守る（ここが技術的な見せ場）
A（陽性）→ B → C と辿るとき、**B–C の接触日 ≥ A–B の接触日 + LATENT_DAYS** のものだけを2段目として出す。時間を無視すると偽の連鎖が大量に出る。

### 感染源の推定
陽性者 p の**感染した可能性のある期間**＝ `p.onset − INCUBATION_MAX_DAYS` 〜 `p.onset − INCUBATION_MIN_DAYS`（無症状なら検査日を使う）。
この期間内に **2人以上の陽性者と接触した人** を、接触した陽性者の数が多い順に並べる。

### コロナ以外の発熱者
発熱したが検査陰性の人を混ぜる。**起点は検査陽性者のみ**。発熱陰性者は画面上グレーの点線で表示し、感染源候補にも入らないことをデモで見せる。

---

## 3. 技術構成（費用ゼロ）

| 層 | 選択 | 費用 |
| --- | --- | --- |
| DB | Neo4j 5 Community（Docker でローカル起動） | 無料 |
| バックエンド | Python 3.11+ / FastAPI / uvicorn | 無料 |
| 画面 | HTML1枚＋素のJS＋Cytoscape.js（CDN）。FastAPI から静的配信 | 無料 |
| LLM | **ai& Inference**（OpenAI互換、`openai` SDK で base_url を差し替え） | 無料クレジット（足りなくても十数円） |
| 開発 | Claude Code | サブスク内 |

- **Claude API は使わない**
- モデル：本命 **`openai/gpt-oss-120b`**、予備 **`deepseek-ai/deepseek-v4-flash`**（環境変数で切り替え）
- Base URL：`https://api.aiand.com/v1`（OpenAI SDK の `base_url` に渡す）
- クレジット：プロモコードで ¥3,200 適用済み
- 会場Wi-Fiが落ちても DB と画面は動く。LLM はテザリングを予備に
- **LLMが落ちても、定型ボタン（接触者追跡・感染源推定）は Cypher 直実行なのでデモが止まらない**

### ディレクトリ構成

```
wardtrace/
├── README.md
├── .env.example
├── docker-compose.yml
├── requirements.txt
├── data/
│   ├── generate.py        # 架空データ生成（seed固定）→ data/out/*.json
│   └── out/
├── backend/
│   ├── main.py            # FastAPI。/api/* と frontend の静的配信
│   ├── config.py          # 環境変数・パラメータ
│   ├── db.py              # Neo4j ドライバ
│   ├── load.py            # JSON → Neo4j 投入、CONTACT の導出
│   ├── queries.py         # 接触追跡・感染源推定の Cypher
│   └── llm.py             # 自然文 → Cypher、結果の説明文
└── frontend/
    ├── index.html
    ├── app.js
    └── style.css
```

### docker-compose.yml

```yaml
services:
  neo4j:
    image: neo4j:5
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=neo4j/wardtrace123
    volumes:
      - ./neo4j-data:/data
```

### requirements.txt

```
fastapi
uvicorn[standard]
neo4j
openai
python-dotenv
pydantic
```

### .env.example

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=wardtrace123

# ai& Inference（console.aiand.com で発行。キーは sk- で始まり、表示は一度きり）
AIAND_BASE_URL=https://api.aiand.com/v1
AIAND_API_KEY=
AIAND_MODEL=openai/gpt-oss-120b
# 予備: deepseek-ai/deepseek-v4-flash
```

---

## 4. データモデル（Neo4j）

### ノード

```
(:Person:Patient {id, name, age, sex, admitted_date, room_id,
                  status, test_date, onset_date, isolated_date, fever_date})
(:Person:Staff   {id, name, role, status, test_date, onset_date, isolated_date})
(:Room {id, name, type})      // type: "ward" | "xray" | "lab" | "station"
```

- `status`：`"negative" | "positive" | "fever_negative" | "untested"`
- 日付は Neo4j の `date` 型で保存（`date("2026-10-14")`）
- `role`：`"nurse" | "doctor" | "radiographer"`

### 元記録のリレーション（病院が実際に持っている記録に相当）

```
(:Patient)-[:STAYED_IN {date}]->(:Room)                      // 1日1本
(:Staff)-[:CARED_FOR {date, shift}]->(:Patient)               // shift: "day" | "night"
(:Patient)-[:VISITED {date, start, end}]->(:Room)            // 検査室・X線室。start/end は "HH:MM"
(:Staff)-[:WORKED {date, shift}]->(:Room {type:"station"})
```

### 導出リレーション（load.py が元記録から作る。追跡はこれを使う）

```
(:Person)-[:CONTACT {date, type, minutes, room_id, close}]-(:Person)
```

- `type`：`"same_room" | "care" | "visit_overlap" | "same_shift"`
- 向きは意味を持たない（作成時は id の小さい方 → 大きい方、検索は無向）
- 同じペア・同じ日・同じ type は1本にまとめる

---

## 5. 架空データ（data/generate.py）

**seed 固定**（`random.seed(42)`）で毎回同じデータになること。

### 病棟
- 5階東病棟。病室 501〜508（4人部屋）＋ X線室 ＋ 検査室 ＋ ナースステーション
- 期間：**2026-10-10〜2026-10-16（7日間）**

### 人
- 患者 **30人**（P01〜P30）。途中入退院は数人だけ（なくても可）
- スタッフ **15人**：看護師 12（N01〜N12）、医師 2（D01〜D02）、放射線技師 1（R01）
- 名前は英字の架空名（英語デモ用。例：`Patient Sato` ではなく `P12 Tanaka` 程度でよい）
- 看護師は日勤／夜勤のシフト。1勤務で 4〜6人の患者を担当
- 医師は日勤で全員を回診（ただし `care` は1日あたり担当の数人のみ）
- 患者の 1/3 程度が期間中に1回、検査室かX線室へ（15〜40分）

### 仕込むシナリオ（正解）
- **感染源：夜勤看護師 N07**。10/11〜10/13 の夜勤で担当した患者に移した。本人は**未検査**（`status: "untested"`、onset_date なし）
- N07 から感染した3人（シナリオ上の陽性者）：
  - **P12**（502号室）：10/15 発症、10/16 検査 → **デモの起点（index）**。初期データでは **`status: "untested"`**（検査日・発症日は記録済み、隔離日は空）。デモで **Mark positive** を押すと陽性になり（隔離日＝検査日）、グラフで赤くなる
  - **P05**（501号室）：10/14 発症、10/15 検査陽性（初期データから positive）
  - **P18**（505号室）：10/15 発症、10/16 検査陽性（初期データから positive）
  - 3人は**別々の病室**で、**共通点は N07 の夜勤担当だけ**になるよう組む（同じ医師・同じ検査室時間にならないよう注意）
- 発熱陰性者 2人：**P03**、**P22**（発熱あり、検査陰性）
- それ以外の人は `negative` または `untested`（P05・P18 の同室者と日勤の受け持ち看護師は検査陰性。P12 はまだ陽性でないので、その同室者や受け持ちは untested）
- 隔離日：陽性判明日（test_date）

### 期待される結果（テストに使う）
- 初期データ（`/api/reset` 直後）：陽性者は P05・P18 の2人。`/api/source` は **N07 だけ**（2人と接触、`n = 2`）
- デモで P12 を Mark positive（検査 10/16・発症 10/15）した後：
  - `/api/trace`（P12起点）：感染可能期間 10/13〜10/16。同室の患者と、P12を担当したスタッフ（N07含む）が1段目に出る（D01, N05, N07, P08, P25, R01）。2段目は26人（時間順を無視すると34人）
  - `/api/source`：**N07 が1位**（陽性者3人全員と潜伏期間内に接触、`n = 3`）。P03・P22 は出ない

### 出力
`data/out/` に `patients.json` `staff.json` `rooms.json` `stays.json` `cares.json` `visits.json` `shifts.json`

---

## 6. 投入と CONTACT の導出（backend/load.py）

1. 全削除（`MATCH (n) DETACH DELETE n`）
2. 制約：`CREATE CONSTRAINT IF NOT EXISTS FOR (p:Person) REQUIRE p.id IS UNIQUE`、Room も同様
3. JSON からノードと元記録リレーションを作成
4. CONTACT を導出：
   - **same_room**：同じ日・同じ病室の患者同士 → close=true、minutes=1440
   - **care**：CARED_FOR からスタッフ–患者 → close=true、minutes=30
   - **visit_overlap**：同じ日・同じ部屋で時間が重なる患者同士。重なり ≥15分なら close=true
   - **same_shift**：同じ日・同じ勤務帯のスタッフ同士 → close=false
5. `python -m backend.load` で実行できること

---

## 7. 核の Cypher（backend/queries.py）

### 7-1. 接触者追跡（2段・時間順を守る）

```cypher
MATCH (a:Person {id: $index_id})
WITH a,
     coalesce(a.onset_date, a.test_date) - duration({days: $lookback}) AS ws,
     coalesce(a.isolated_date, date("2099-12-31")) AS we
MATCH (a)-[c1:CONTACT]-(b:Person)
WHERE c1.close AND ws <= c1.date <= we
OPTIONAL MATCH (b)-[c2:CONTACT]-(c:Person)
WHERE $depth >= 2 AND c2.close AND c <> a
  AND c2.date >= c1.date + duration({days: $latent})
  AND NOT EXISTS {
    MATCH (a)-[x:CONTACT]-(c)
    WHERE x.close AND ws <= x.date <= we
  }
RETURN a, ws, we, b, collect(DISTINCT c1) AS c1s,
       collect(DISTINCT {person: c, edge: c2}) AS second
```

- 1段目＝b、2段目＝c（経由した b を記録）
- 2段目から1段目に既に入っている人は除く（Python 側で重複排除してもよい）
- 除外するのは、**感染可能期間内**に起点と濃厚接触した人（＝1段目）だけ。期間外にしか起点と接触していない人は、1段目経由で2段目に入りうる。期間を見ずに「起点と一度でも接触した人」を除くと、その人が1段目にも2段目にも出ず漏れる（例：P08 起点で N07 が漏れる）

### 7-2. 感染源の推定

```cypher
MATCH (p:Person {status: "positive"})
WITH p, coalesce(p.onset_date, p.test_date) AS ref
MATCH (p)-[c:CONTACT]-(x:Person)
WHERE c.close AND x.status <> "fever_negative"
  AND ref - duration({days: $inc_max}) <= c.date <= ref - duration({days: $inc_min})
WITH x, collect(DISTINCT p.id) AS linked, collect(c) AS edges
WHERE size(linked) >= 2
RETURN x, linked, size(linked) AS n, edges
ORDER BY n DESC
LIMIT 10
```

- 陽性者自身も候補に入りうる（陽性者同士の連鎖）。それでよい
- 起点は `status = "positive"` のみ
- 発熱陰性者は `x.status <> "fever_negative"` で**候補からも明示的に除外**する（起点を陽性者に限るだけでは、発熱陰性者が陽性者2人と接触していれば候補に出てしまう）

### 7-3. 画面用グラフ

期間内の Person 全員と close な CONTACT を返す（Cytoscape 形式に変換）。

---

## 8. API（backend/main.py）

すべて JSON。`/` で `frontend/index.html` を返す。

| メソッド | パス | 入力 | 出力 |
| --- | --- | --- | --- |
| GET | `/api/persons` | — | `[{id, name, kind, role, status, room_id, test_date, onset_date}]` |
| GET | `/api/graph` | — | `{nodes: [...], edges: [...]}`（Cytoscape 形式） |
| POST | `/api/positive` | `{id, test_date, onset_date?}` | 更新後の person。`status="positive"`、`isolated_date=test_date` |
| POST | `/api/trace` | `{index_id, depth: 1\|2}` | 下記 |
| GET | `/api/source` | — | `[{person, linked_positive_ids, n, contacts:[...]}]` |
| POST | `/api/ask` | `{question}` | `{cypher, rows, answer}` |
| POST | `/api/reset` | — | データを初期状態に再投入 |

### `/api/trace` の出力

```json
{
  "index": {"id": "P12", "name": "...", "status": "positive"},
  "window": {"start": "2026-10-13", "end": "2026-10-16"},
  "first_gen": [
    {"id": "N07", "name": "...", "kind": "staff",
     "contacts": [{"date": "2026-10-14", "type": "care", "minutes": 30, "room_id": "502"}]}
  ],
  "second_gen": [
    {"id": "P07", "name": "...", "kind": "patient", "via": "N07", "vias": ["N07", "P08"],
     "contacts": [{"date": "2026-10-15", "type": "care"}]}
  ],
  "second_gen_if_time_ignored": 34,
  "counts": {"first_gen": 6, "second_gen": 26, "second_gen_if_time_ignored": 34},
  "graph": {"nodes": [...], "edges": [...]}
}
```

- `via`：その2段目の人に最も早くつながった1段目の人（表の「Via」列）
- `vias`：時間順を守ってその人につながる1段目の人の全員（ID順）。画面で1段目をクリックしたとき、その人を経由する2段目を強調するのに使う
- `second_gen_if_time_ignored`：時間順の条件（`c2.date >= c1.date + LATENT_DAYS`）を外した場合の2段目の人数。それ以外の条件（1段目と起点の除外など）は同じ。depth=1 のときは `null`。画面では「26 (34 without time order)」と出す。差の8人は時間順の条件を満たさないので今回の追跡から外れる、という意味で、感染していないとまでは言えない
- `counts`：人数のまとめ（`first_gen`、`second_gen`、`second_gen_if_time_ignored`）。depth=1 のとき `second_gen` は 0、`second_gen_if_time_ignored` は `null`。画面のグラフ上の人数表示に使う

### Cytoscape 形式

```json
{"data": {"id": "P12", "label": "P12", "kind": "patient", "status": "positive", "gen": 0}}
{"data": {"id": "e1", "source": "P12", "target": "N07", "type": "care", "date": "2026-10-14", "close": true}}
```

`gen`：0=起点、1=1段目、2=2段目、null=無関係

---

## 9. LLM（backend/llm.py）

```python
from openai import OpenAI
client = OpenAI(base_url=AIAND_BASE_URL, api_key=AIAND_API_KEY)
```

### 9-1. 自然文 → Cypher

- system プロンプトに入れるもの：
  - スキーマ（4章をそのまま）
  - パラメータの既定値（2章）
  - ルール：**読み取り専用**、`LIMIT 50` を必ず付ける、日付は `date("YYYY-MM-DD")`、`CONTACT` は無向で検索
  - few-shot 3つ（下記）
  - 出力は JSON `{"cypher": "..."}` のみ
- few-shot：
  1. 「P12と濃厚接触した人は？」→ 7-1 の1段目だけ版
  2. 「N07が10/12に担当した患者は？」→ CARED_FOR を引く
  3. 「陽性者に共通する接点は？」→ 7-2
- 日本語・英語どちらの質問でも動くこと

### 9-2. 安全策（必須）

- 生成された Cypher に `CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD|CALL dbms|apoc` が含まれたら拒否
- 実行は `session.execute_read(...)` で読み取り専用トランザクション
- `LIMIT` がなければ末尾に `LIMIT 50` を付ける
- 構文エラーなら、エラー文を添えて1回だけ再生成

### 9-3. 結果の説明文

- 入力：質問、Cypher、結果の行（先頭30行）
- 出力：質問と同じ言語で3文以内。**判断や指示はしない**（「〜を隔離すべき」ではなく「〜と接触しています」）
- 末尾に「最終判断は感染対策チームが行ってください」は付けない（UIに常時表示するので不要）

### 9-4. フォールバック

- `AIAND_API_KEY` が未設定、または呼び出し失敗時は `{cypher: null, rows: [], answer: "LLM unavailable"}` を返し、画面は定型ボタンで続行できる

---

## 10. 画面（frontend）

### レイアウト（1画面、横長 1440×900 想定）

```
┌───────────────────────────────────────────────────────────────┐
│ WardTrace   Ward 5E · Oct 10–16          [Reset]              │
├──────────────────┬────────────────────────────────────────────┤
│ ① Mark positive  │                                            │
│  [person ▼]      │           Cytoscape グラフ                  │
│  test [date]     │                                            │
│  onset [date]    │                                            │
│  [Mark positive] │                                            │
│                  │                                            │
│ ② Trace          │                                            │
│  depth (1)(2)    │                                            │
│  [Trace contacts]│                                            │
│                  ├────────────────────────────────────────────┤
│ ③ Find source    │ 結果パネル（タブ）                          │
│  [Find source]   │  Contacts | Source | Ask                    │
│                  │  ・1段目／2段目の表（日付・種類・部屋）      │
│ ④ Ask            │  ・感染源候補の表（n人の陽性者と接触）      │
│  [質問を入力   ] │  ・LLMの回答 ＋ 実行したCypher（折りたたみ）│
│  [Ask]           │                                            │
├──────────────────┴────────────────────────────────────────────┤
│ Decision support only. Final decisions are made by the ICT.   │
└───────────────────────────────────────────────────────────────┘
```

### グラフの見た目

| 対象 | 表現 |
| --- | --- |
| 患者 | 丸 |
| スタッフ | 四角 |
| 陽性 | 赤 |
| 1段目 | オレンジ |
| 2段目 | 黄 |
| 発熱陰性 | グレー＋点線の枠 |
| 無関係 | 薄いグレー（透明度を下げる） |
| close な接触 | 実線 |
| 感染源候補 | 太い赤枠＋点滅しない程度の強調 |
| Person 欄で選ばれている人 | 青い光がゆっくり点滅（0.7秒ごと）。Mark positive の前から誰を選んだか分かる |
| Ask の回答に出てきた人 | 青い枠 |

- 初期表示のレイアウトは `cose`（病棟全体の図）。この配置を「元の配置」として覚えておく
- ノードをクリックすると、その人の接触一覧が結果パネルに出る
- 英語のラベルの横に（）で日本語の使い方を添える（見出し・入力欄・説明・凡例・タブ・注意書き）。ボタン本体は英語のみ

### 追跡のアニメーション（Mark positive／Trace contacts）

何をしているか見て分かるように、3段階で見せる。グラフ左上の字幕（英語＋日本語）で各段階を説明する。表とステータスはすぐ出す。

- **Mark positive** は、陽性登録のあと選択中の depth で追跡し、**元の配置のまま見せる段階（Step 1、depth 2 なら Step 2）で止める**。輪への並べ替え（Step 3）はしない。depth 1 なら Mark positive の時点で depth 1 の追跡は完了している
- **Trace contacts** は Step 3（輪への並べ替え）まで行う。デモでは Mark positive のあと Depth を 2 にして Trace contacts を押す
- 画面のファイル（HTML・JS・CSS）は `Cache-Control: no-cache` で配信し、ブラウザに古い app.js が残らないようにする

1. **Step 1**：元の配置のまま、起点（赤）と1段目（オレンジ、線もオレンジ）以外を薄くして、起点と1段目にズーム。病棟の中のどこでつながったかが分かる
2. **Step 2**（depth 2 のみ）：2段目（黄、線も黄）を足して、関係者全体が入るまでズームアウト。字幕に「26人（時間順を無視すると34人）」を出す
3. **Step 3**：起点を中心にした輪に並べ替える（concentric。1段目が内側、2段目が外側、無関係は薄く外周）。輪の中心は起点の今の位置にして、図が大きく動かないようにする。depth 2 のとき、2段目はここから**薄く表示**する（色は黄のまま）

- 点の移動とカメラの移動は、同じ時間・同じ動き方で同時に行う（点だけ先に動かすと図が左右に揺れて見える）
- 全体で depth 2 なら約8〜10秒。終わるまでボタンは無効。字幕は小さく短くし（グラフをふさがない）、終わって2.5秒後に消す。「1段目をクリックすると経路が見える」という案内は、字幕ではなく2段目の表の見出しの下に常に出す
- タブが裏に回って描画が止まったら、予定の時間を1秒過ぎた時点で最後の状態へ飛ばす
- 途中で Find source・Ask・Reset を押したら、再生中のアニメーションは止める
- 追跡が終わったら、右上に**病棟全体の縮小図**（Ward overview）を出す。元の配置のまま、メインと同じ色で強調する。クリックするとメインの図を元の配置に戻す（色はそのまま）。Reset で隠す

### 人数表示と経路の強調

- グラフの上に人数の行を出す：「P12 1st gen 6 / 2nd gen 26 (34 without time order)」＋日本語。depth 1 は「2nd gen — (depth 1)」。API の `counts` を使う。感染源推定・質問・Reset で隠す
- depth 2 の追跡後、**1段目のノードをクリック**すると、その人を経由する2段目（API の `vias` に含まれる人）だけ濃くし、経路の線を黄色で出す。ほかの1段目は薄くする。人数の行に「· via N07: 8」を足し、2段目の表もその人を経由する人だけにする。同じノード・起点・背景をもう一度クリックすると全員に戻る
- 1段目以外のノードをクリックしたときは、今までどおりその人の接触一覧を出す
- 世代の色の意味は変えない（強調は濃さと線で表す）
- Reset で depth を 1 に戻す
- 人数の行を出し入れするとグラフ領域の高さが変わるので、Cytoscape の大きさを測り直す（`cy.resize()`）

### 結果パネル

- Contacts：感染可能期間、1段目の表、2段目の表。2段目の見出しは「26 time-respecting (34 if time order ignored)」（depth 1 は「(0, depth 1)」）
- Source：陽性者の一覧、発熱陰性者は起点にも候補にも入れないことの注記、候補の表（陽性者何人とつながったか、潜伏期間内の接触）
- Ask：質問、回答、実行した Cypher（折りたたみ）、結果の表

---

## 11. 当日の時間割

| 時刻 | やること | 完了の目安 |
| --- | --- | --- |
| 10:30–11:15 | docker compose up、generate.py、load.py | Neo4j Browser（localhost:7474）でグラフが見える |
| 11:15–12:30 | queries.py（7-1・7-2）と /api/trace・/api/source | **N07 が感染源1位に出る**（心臓部） |
| 12:30–13:30 | ランチ（食べながら ai& のクレジット設定） | |
| 13:30–14:15 | llm.py と /api/ask | 日英の質問で答えが返る |
| 14:15–15:15 | frontend（グラフ・ボタン・結果パネル） | デモの流れが1画面で通る |
| 15:15–15:40 | 通し練習 ×2、**画面録画の予備** | |
| 15:40–16:00 | README、リポジトリ公開、**提出** | 16:00 前に提出完了 |

### 時間が余ったら（追加要素）
1. **規模の切り替え**：`generate.py --scale hospital` で病院全体（10病棟・患者400人・スタッフ300人）を生成できるようにする。デモ本編は1病棟のまま、最後に「病院全体でも同じ結果が一瞬で出る」と見せて、「Excelで足りるのでは？」への答えにする
   - 仕込むシナリオ（N07 が感染源）は5階東病棟にそのまま残し、他の病棟は背景ノイズにする
   - 画面のグラフは関係者だけ表示（全ノードは描かない）
   - 追跡・感染源推定の処理時間を画面に表示する（例：`traced 700 people in 0.12s`）

### 削る順番（時間が押したら）
1. ノードクリックの詳細表示
2. 2段目（depth=2）
3. /api/ask（LLM）→ ただし**ai&を使わなくなるので最後の手段**
4. 見た目

**最後まで残すのは「P12を陽性に → 接触者が出る → 感染源 N07 が出る」の一本。**

---

## 12. 3分デモ（英語）

1. **Problem（30s）**：When COVID hits a hospital ward, the infection control team still traces contacts with paper and Excel. It's slow, and people get missed.
2. **Mark positive（30s）**：P12 tests positive. One click → P12 turns red, and contacts within the infectious window (from 2 days before onset) light up.
3. **Second generation（30s）**：Depth 2. Only time-respecting chains — B met C *after* A met B. Without this rule, 34 people; with it, 26 — eight don't fit the time order, so they drop out of this trace (that doesn't prove they're uninfected).
4. **Find source（45s）**：Three positives in three different rooms. The graph finds the one person linked to all three within the incubation window: night nurse N07 — untested. In this demo the trace starts only from test-positive cases, so fever patients who tested negative don't become candidates.
5. **Ask（30s）**：「Who did N07 care for on night shifts?」→ ai& turns it into Cypher; we show the query so it's auditable.
6. **Why（15s）**：Neo4j finds everyone the records connect, the same way every time; ai& (inference in Japan — patient data stays in the country) is the language layer. Decision support only — next step: a review-priority score from contact type, duration, PPE and procedures.

### 想定質問
- **医療情報の正確さは？** → 判断はしない。記録から事実のつながりを出すだけ。期間（発症2日前・潜伏期間2〜7日）は設定値で変えられる
- **実データは？** → 架空。実運用では電子カルテ・勤務表・検査予約から取り込む想定
- **なぜLLMだけでやらない？** → 1章
- **COCOAとの違いは？** → 1章
- **全員検査するのでは？** → する。このツールは記録の範囲で「全員」を洗い出し、感染源をさかのぼるためのもの
- **なぜ ai&？** → 患者データを国外に出さずに推論できる
- **日本全体に広げられる？** → 次は病院間（転院・共通の外来）。人口全体は接触データがないので対象外
- **26人も出たら使えなくない？** → 記録から拾う候補は広く残す。そのうえで経由者・日時・接触の種類で、誰の記録から確認するかを決められる。人数の多さだけで候補を削らない
- **34→26なら、8人は感染していない？** → そこまでは言えない。8人は今回の時間順の条件を満たさない、という結果
- **本当に漏れなく分かる？** → 入力された記録と設定した条件の範囲で抽出する。記録にない接触や感染経路までは保証しない
- **陰性者を除外して大丈夫？** → 陰性結果だけでは感染を否定できない。今は「検査陽性者を起点にする」というデモの仕様。実運用では検査の種類・採取日を考え、一律には除外しない
- **N07が出るように作っただけでは？** → その通りで、既知の筋書きを再現できるかの機能確認。精度の証明ではない。別の感染源・複数の感染源・記録の欠落でも評価が必要
- **距離や時間は評価しないの？** → 今は国の基準に近い二択（濃厚かどうか）。次は「確認優先度スコア」：接触の種類・実際の時間・防護・エアロゾル発生処置・発症前後かを点数で足し、高・中・低で表示。2段目は経路の弱い方の接触の点数を採る。不明な項目は0点にせず「評価未完了」と出す。重みは仮置きで、感染対策担当者の評価との一致と、重みを±1変えたときの順位の安定性で検証する。感染確率ではなく、確認の順番を決めるための目安
- **距離はどう測る？** → 距離は推定しない。担当・同室など記録にある接触状況を使う。将来はBLEバッジ等の実測も
- **AIは何を良くしている？** → 定型の探索はDBで実行し、AIは自由な質問を検索につなぎ、結果を説明する。生成した検索文（Cypher）も画面で確認できる

---

## 13. 提出物（16:00締切）

- チーム名・メンバー名・メールアドレス
- プロジェクト名と説明（1章の太字の一文＋COCOAとの違い）
- リポジトリURL（**公開設定**）
- スポンサーツールの使い方：
  - **Neo4j**：患者・スタッフ・病室の記録から接触グラフを作り、感染可能期間と時間順の制約つきで多段の接触追跡と、潜伏期間内の共通接点（感染源候補）の探索に使用
  - **ai&**：自然文の質問を Cypher に変換し、結果を説明する言語層。推論は国内で完結し、患者データが国外に出ない

---

## 14. 前日（今日）にやること

> コードを書くのは当日から。今日は環境の準備だけ（ルールに明記はないが公平性のため）。

- [x] Docker Desktop を起動できる状態に
- [x] `docker pull neo4j:5` を済ませておく（会場Wi-Fiで落とさない）
- [x] Python 3.11+ の確認、`pip download` か venv に requirements を入れておく（Python 3.14 の `.venv`）
- [x] Cytoscape.js は CDN 読み込み。念のため `cytoscape.min.js` をローカルにも保存しておく（`vendor/` から配信）
- [x] ai& のクレジット・セットアップガイドに目を通す（BASE_URL `https://api.aiand.com/v1`、モデル `openai/gpt-oss-120b`）
- [x] GitHub にリポジトリ `wardtrace` を作っておく（`MyriaMontis/wardtrace`、公開）
- [ ] 持ち物：HDMIアダプター、充電器、モバイルバッテリー、テザリング確認、PC フル充電
