---
name: sales-meeting-prep
description: >-
  商談・面談の事前準備サマリを作成するスキル。「〇〇の商談準備して」「〇〇社との面談準備」「〇〇さんの面談前に整理して」
  などのリクエスト時に使う。取引先名を入力として、Google Drive 上の SFDC エクスポート（取引先・商談・商談ドラフトの文字起こし）、
  Gmail、Notion、Slack を横断して情報を集め、ファクトベースで meeting-prep-summary.md にまとめ、必要に応じて Notion 議事メモを作成する。
  「先方の課題」と「自社の営業課題」を厳密に区別し、課題と必須要件・解決策を混在させない点が重要。
  （この環境では Salesforce に直接接続できないため、SFDC データは Google Drive 経由で読む。詳細は drive-data-map.md）
---

# 商談事前準備スキル（この環境向け再設定版 / Drive参照）

商談・面談の前に、取引先との過去の経緯・現在の取引状況・先方の課題仮説をファクトベースで整理する。

「次回の面談で何を話すべきか」「先方は何で困っているのか」を、**商談ドラフトの文字起こし（`meetingNote__c`）** や Gmail のやり取りから根拠を引いた状態で提示する。

> **このファイルについて**
> claude.ai 版「商談事前準備スキル」を、このリモート実行環境（Claude Code on the web）向けに再設定したもの。
> オリジナルは Mac 上の `sf` CLI（`--target-org prod`）で SFDC を直接クエリする前提だが、**本環境には `sf` CLI も Salesforce MCP も無い**。
> その代わり、ユーザーが `sf` CLI で抽出した **SFDC データを Google Drive に置いている**ので、本スキルは **Google Drive MCP 経由で SFDC データを読む**。
> 具体的なファイル所在・取得手順・絞り込み方は **`drive-data-map.md`** を必ず参照。

---

## ⚠️ この環境での前提（最初に必ず読む）

| オリジナルの依存 | 本環境での扱い |
|---|---|
| `sf data query`（SFDC ライブクエリ） | **不可**。代わりに **Google Drive 上の SFDC エクスポートを読む**（`drive-data-map.md`）。`queries.md` の SOQL は「各エクスポートに含まれる項目の仕様書」として参照する。 |
| Account / Opportunity / OpportunityDraft__c(`meetingNote__c`) / Task / EmailMessage | Drive の各 JSON / CSV / シートから取得（対応表は `drive-data-map.md`）。**文字起こしは `opp_draft.json` が主ソース**。 |
| 数値（`MRR__c` 等）の集計 | エクスポート時点のスナップショット。**取得元（ファイル名・抽出日）を出典に明記**。ライブ再集計はできないので「○○.csv（抽出YYYY-MM-DD）」と添える。 |
| 補助スキル5種・`.claude/rules/*`・`glossary.md` | 未導入/不在 → 要点を本 SKILL に転記。`queries.md`・`drive-data-map.md`・`output-template.md` は同梱。 |
| Gmail / Notion / Slack | ✓ 接続済み。そのまま使用。 |
| Google Calendar / Box / Drive | ✓ 接続済み。面談特定・資料収集・**SFDCデータの読み取り**に使用。 |

**読み取り専用**：Drive / SFDC / Notion 既存データは書き換えない。書き込みは Step 8 の Notion 議事メモ作成のみ（ユーザー確認後）。
**5原則・出力フォーマット・セルフチェックはオリジナルのまま維持**。変えたのは「SFDC データの取り方（ライブクエリ → Drive エクスポート読み取り）」。

---

## このスキルでやること / やらないこと

**やること**: Drive(SFDC) / Gmail / Notion / Slack / Box を横断して情報収集 → プロダクト別×フェーズ別の進捗・キーマン・競合・Dead理由を整理 → 先方の業務課題を根拠付きで抽出 → `<取引先名>-meeting-prep/meeting-prep-summary.md` 作成 → ユーザー確認後に Notion 議事メモ作成。

**やらないこと**: pptx 作成（別途依頼時のみ） / 提案ストーリー・営業戦略の組み立て（事実整理が主目的） / データ更新（読み取り専用）。

---

## 5つの原則（最重要）

毎回ここに立ち戻って自己チェックする。

### 原則1. 「先方の課題」と「自社の営業課題」を厳密に分離する
- 先方の課題＝お客様の業務上の困りごと・目指す姿。 自社の営業課題＝受注確度・提案戦略・競合・社内体制。
- サマリの「課題」は**先方の課題のみ**。営業課題は「戦略的ポイント」へ。
- ✗「Vista商談が過去2回Deadしている」（自社課題） ○「配車がベテラン3名に依存、3年内に全員退職予定」（先方課題）

### 原則2. ファクトベース：推測でデータを補完しない
- 固有名詞・数値・人名・システム名は一次情報（**`meetingNote__c` の文字起こし**、Gmail、SFDCエクスポート）から取り、引用元（ファイル名・日付・発言者）を添える。
- 取れない情報は「取得できない / 情報なし / 要確認」。**推測で埋めない**。
- 数値は**抽出元と抽出日**を必ず添える（例:「商談簡易版CSV（2026-06-26抽出）」）。

### 原則3. 課題と必須要件・前提を区別する
- 「これが無いと前に進めない」は**必須要件**であって課題ではない。別セクション「前提・必須要件」へ。

### 原則4. 提案・強み・解決策を課題スロットに混ぜない
- 課題セクションは課題のみ。プロダクト名（Vista/Berth/Fleet/Adapter 等）・提案は「提案状況」「アジェンダ」「戦略的ポイント」へ。

### 原則5. 取引先・金額・日付の表記規約（`.claude/rules/` が無いため転記）
- **取引先**: 「取引先名（部門名）」で識別。`常温福岡センター` のような**部門名単独は避け**、`ヤマエ久野（常温福岡センター）`。レコードURL併記（`drive-data-map.md` のURL形式）。
- **金額**: 万円・小数第1位。`MRR__c` が基本（親商談集計時のみ `Related_Opportunities_MRR__c`）。出典＝Driveのどのファイル・抽出日かを明記。Notion pptx の数字は転記しない。
- **日付**: `YYYY/MM/DD` または `YYYY-MM`。 **会計年度**: FY9 = 2023/6〜2024/5（6月始まり、以降1年スライド）。

---

## 実行手順（Drive参照版）

> SFDC 由来データは **`drive-data-map.md` の対応表**に従って Google Drive から取得する。可能な収集は並列で。

### Step 0: 面談対象の特定
ユーザー指定が曖昧／「次の面談の準備」の場合、**Google Calendar**（`list_events`、当日〜7日先）で対象面談（相手・日時・出席者・件名）を特定。出席者ドメインは Step 4(Gmail) の検索に使う。

### Step 1: 取引先（Account）を特定する
- `drive-data-map.md` の **Account ソース**（`SFDC企業一覧_Sales&CS` シート等）を取引先名（部分一致）で検索し、正式名称・Site（部門）・所有者・Idを得る。
- 併せて Notion `notion-search` でも取引先名を全文検索（企業攻略ボード等を拾う）。
- 複数該当 → ユーザーに確認、またはグループ全体を対象にするか提案（グループは `Company__c → Company__r` で辿る）。
- 取得行を `accounts.json`（取れた項目のみ）として保存してよい。

### Step 2: 商談（Opportunity）一覧の取得
- `drive-data-map.md` の **Opportunity ソース**＝**最新の `【データ定期保存】商談…簡易版CSV`** を読み、対象 Account の商談を抽出。`FY11/FY12 実績DB` で過去/Dead履歴を補う。
- 「案件 × プロダクト × ステータス × カウンターパート」一覧を作成。進行中/成立/Deadを分類。
- 取引規模と **MRRネット（有償新規＋追加成立 − 解約）を1行で算出**。各数値に**出典（ファイル名・抽出日）**を添える。簡易版CSVに無い項目は空欄＋「(要確認)」。
- 結果を `opportunities.json` として保存してよい。

### Step 3: 商談ドラフトの文字起こし（`meetingNote__c`）取得 ★最重要
- **主ソース `opp_draft.json`**（`drive-data-map.md`）。`read_file_content` で大きく保存される → 返ったパスを **`Grep`** で `Opportunity__r` の Name / `meetingNote__c` 本文に**取引先名・会社名**を含むレコードを特定。
- 該当の `meetingNote__c` を `drafts/<Opportunity__c>.txt` に保存（長文は分割読み）。`Opportunity__c` は商談Id（URL化用）。
- 広く拾うときは `draft_june.json`(30MB) を**丸ごと読まず Grep で絞る**。ドラフトが無い商談は `no_draft.csv` で把握。
- **必須取得**: 次回面談対象の案件 / 直近1年の Dead案件 / 進行中の重要案件。
- **Dead理由の深掘り**: ドラフトに理由が無ければ `email_tasks.json` / `phone_events.json`（Dead前後）と **Slack**（社内引継ぎ・懸念）を一次情報で当たる。不明は「要確認」。

### Step 4: Gmail の過去やり取り
`search_threads` で取引先名／相手ドメイン（Step0）を過去90日検索。主要スレッドを `get_thread` で取得し `gmail_threads.md` に要点。

### Step 5: Notion 議事メモ・関連ページ
`notion-search` で取引先名を検索。議事メモDB配下・企業攻略ボードから「未解決の論点」「過去合意」を `notion_pages.md` に要点。

### Step 6: Slack 社内議論（必須）
`slack_search_public_and_private` で **取引先名＋主要担当者名**を1回は検索。ヒット0件でも「検索済み・なし」と情報ソースに明記。

### Step 7: サマリ作成
`<取引先名>-meeting-prep/meeting-prep-summary.md` を **`output-template.md`** の構成で作成。出力は「事前MTGメモ形式」＝本番でそのまま話せる事実を会議で読める粒度で。
**セクション**: 1.概要 / 2.背景 / 3.提案状況全体像（MRRネット1行＋案件別詳細＝経緯・現状・先方の業務課題・根拠リンク） / 4.面談の趣旨とアジェンダ案 / 5.戦略的ポイント（自社課題はここだけ） / 6.準備事項 / 7.情報ソース（Drive各ファイル名＋抽出日／Gmail／Notion／Slack、ヒット0件・未取得も明記）。

**書き終えたらセルフチェック**:
- 課題セクションに必須要件と紛らわしい文言（「〜が必須」「〜しないと進まない」）が無いか → あれば「前提・必須要件」へ移動。
- 部門名単独表記（例 `常温福岡センター`）が残っていないか → 親会社名併記へ。
- プロダクト名（Vista/Berth/Adapter等）が課題セクションに無いか → 解決の方向性/提案状況へ。
- 数値に**出典（Driveファイル名・抽出日）**が添えてあるか。

### Step 8: Notion 議事メモを作成（ユーザー確認後）
`meeting-prep-summary.md` をユーザーに見せ、確認後に作成。
- 作成先: 議事メモ DB `collection://ff44bf23-9ca7-4d9d-955e-03c11acf1d98`（疎通確認済み）。「商談メモ」テンプレ `https://app.notion.com/p/131ee2118f7780819fc1ec05f9c8225e` に寄せる。
- タイトル「YYYY-MM-DD <取引先名> <面談趣旨>」。可能なら `企業DB` リレーション・`タグ=02.商談・Onb. Feedback`・`Date`・`参加者` を設定。

---

## アウトプットファイル構成
```
<取引先名>-meeting-prep/
├── meeting-prep-summary.md   # メイン（ユーザー確認用）
├── accounts.json             # Account（Drive企業一覧の該当行）
├── opportunities.json        # 商談一覧（Drive簡易版CSV等から）
├── drafts/<Opportunity__c>.txt  # 文字起こし（opp_draft.json から抽出）
├── gmail_threads.md
└── notion_pages.md
```

## 同梱・参照ファイル
| ファイル | 用途 |
|---|---|
| `drive-data-map.md` | **SFDCデータの所在・取得手順・絞り込み方（この環境の要）** |
| `queries.md` | 元のSOQL（＝各Driveエクスポートに含まれる項目の仕様書として参照） |
| `output-template.md` | meeting-prep-summary.md のテンプレート |

## 補助スキルの扱い（未導入 → インライン）
- Dead深掘り（旧 sales-opportunity-content-analysis）＝ Step3 の email_tasks/phone_events/Slack。
- 契約・プロダクト状況（旧 common-customer-analysis）＝ Step2 を手動整理。
- 定量整理（旧 sales-pipeline-analysis）＝ 簡易版CSV/実績DBの記載値ベース。
- IN句分割（旧 common-soql-constraints）＝ SOQL を実行しないため該当なし。
- グループ分析（旧 common-corporate-group-analysis）＝ `Company__c → Company__r` を手動で辿る。

## 注意
- 大きいDriveファイルは**丸ごと読まず Grep/Read で絞る**（context 保護）。
- 数値・ステータスは**スナップショット**。出典（ファイル名・抽出日）を必ず添える。
- 各 MCP/ファイルが取得不可なら「〈ソース〉取得できず」と情報ソースに明記。
