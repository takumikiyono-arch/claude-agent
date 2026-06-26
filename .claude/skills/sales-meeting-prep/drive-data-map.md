# Drive データマップ（この環境の SFDC 一次データ）

この環境には `sf` CLI も Salesforce MCP も無い。代わりに、ユーザーが **`sf` CLI（Mac, `--target-org prod`）で抽出した SFDC データを Google Drive に置いている**。本スキルはそれを **Google Drive MCP** で読む。

> 検証日: 2026-06-26（このマップのファイルIDは「その時点のスナップショット」。CSV/JSON は再生成され ID が変わりうるので、**まず `search_files` でタイトル検索 → `modifiedTime` 最新を採用**する。ID は当たりを付ける用のヒント）。

## アクセス手段（重要・検証済み）

- **JSON / CSV / Google スプレッドシート** → `read_file_content(fileId)` でテキストが返る。
- **大きいファイル（>~25k tokens, 例: opp_draft.json=718KB, draft_june.json=30MB）** → `read_file_content` は結果を**ローカルファイルに自動保存**し、そのパスを返す。**丸ごと読まず**、返ってきたパスを `Grep`（取引先名・`Opportunity__r` 等）/ `Read`（offset/limit）で**絞って**読む。
- **`.soql` ファイル** → mime が `application/octet-stream` で `read_file_content` 不可。`download_file_content(fileId)`（base64）で取得しデコード。中身を読みたい時だけ。
- **`.xlsx`** → `read_file_content` で可（必要なら `download_file_content`＋変換）。

## オブジェクト別データソース

### Account（取引先）
| ファイル | fileId / 探し方 | 備考 |
|---|---|---|
| `SFDC企業一覧_Sales&CS`（スプレッドシート） | `1opbCMVyQPFDyCN7M2KNP3d_blSTRgRqJnxICJG-sWB8` | 取引先名検索の主ソース。列は実物の先頭で確認（取引先名/Site/所有者 等） |
| `企業所有者リスト.xlsx` 他 | SFDCフォルダ `1AWa3TeVOEq89Kyo3rZB2_UDCmU2v41Rf` 配下 | 所有者・企業一覧の補助 |
| `sfdc_updates_acc.json` | 検索 `title='sfdc_updates_acc.json'` | 直近更新の差分のみ（全件ではない） |

Account の標準項目（`queries.md` の SOQL 準拠）: `Name, Site, BillingState/City, Company__c, Company__r.Name, Owner.Name, LastActivityDate`。
※ `CompanyGroup__c` / `Account_Type__c` は **存在しない**。グループは `Company__c → Company__r` 経由。

### Opportunity（商談）
| ファイル | fileId / 探し方 | 備考 |
|---|---|---|
| `【データ定期保存】商談（当会計年度・翌会計年度）レポート簡易版-YYYY-MM-DD-….csv` | フォルダ `1A24srh5fwFzPHdC2Z1OU6e7Z2vplf964`。`title contains '【データ定期保存】商談'` で検索し**最新日付**を採用（例 2026-06-26 版 = `1olZvy2uRPSeaEapRP0TKh3pFC5bcDMg1`） | 当/翌FYの商談一覧。日次更新。**簡易版**＝列は限定的、先頭行で列名確認 |
| `FY12_実績データベース（商談）` | `1kZzYrH5gx_5GROi4FfC7O2Ic-TDuPJ2P-AvQZVWQ3x0` | 今期実績 |
| `FY11_実績データベース（商談）` | `1LhoIidQohGU06a2yni03G1TISvL3LVAVyeDIJv3J7VU` | 前期実績（Dead/成立の履歴） |
| `sfdc_updates_opp.json` | 検索 | 直近更新の差分Idのみ |

Opportunity 標準項目（`queries.md` 準拠）: `Name, AccountId, Account.Name, Account.Site, StageName, CloseDate, Probability, IsClosed, IsWon, Amount, MRR__c, Related_Opportunities_MRR__c, ProductName__c, RecordType.Name, RecordType_Name__c, Owner.Name, Description, ParentOpportunity__c/__r.Name`。
分類: 進行中=`IsClosed=false` / 成立=`IsWon=true` / Dead=`IsClosed=true & IsWon=false`。

### OpportunityDraft__c（商談ドラフト＝文字起こし `meetingNote__c`）★最重要
| ファイル | fileId / 探し方 | 備考 |
|---|---|---|
| `opp_draft.json`（718KB, 日次更新） | フォルダ `1agdISJSC90pHPMcBvJVDfUV5zhLPAr0r` / `1I5fV89tNZXcoOPM2L_KTqhFi5Il_ma6J` | 主ソース。レコード構造（検証済み）: `Id, Opportunity__c, Opportunity__r{Name}, meetingNote__c, (各種 Stage/Product __c), AmptalkURL__c, CreatedDate, CreatedBy.Name` |
| `draft_june.json`（**30MB**） | `1JYnXBWXhr9YEU5Qvknc2bnjpGprB1LDj` | 6月の大量ドラフト。**丸ごと読まない**。保存ファイルを Grep で取引先名・商談名で絞る |
| `draft.json` / `act_draft.json` | 各フォルダ | 案件・プロジェクト別の追加ドラフト。必要時のみ |
| `no_draft.csv` | `1-Z6xRaBwkh1iTXbfuY14hfL-QRbrEDbm` | ドラフトが**無い**商談の一覧（穴の把握用） |

**取引先での絞り込み手順**:
1. `read_file_content(opp_draft.json)` → 大きいので保存パスが返る。
2. そのパスを `Grep` で `Opportunity__r` の `Name` または `meetingNote__c` 本文に**取引先名/会社名**を含むレコードを特定（社名は本文中にも頻出）。
3. 該当レコードの `meetingNote__c`（文字起こし本文）と `Opportunity__c`（商談Id, URL化に使用）を抽出。`drafts/<Opportunity__c>.txt` に保存。

### 活動（Task=架電 / EmailMessage / Event）
| ファイル | fileId | 備考 |
|---|---|---|
| `email_tasks.json` | `1zBTD9b8i6ujDZo_HUIZvje8tgAz3zolJ` | メール送受信タスク |
| `phone_events.json` | `1opmJ4WH3ts2MFtiulS2MW6sJyPICeGfb` | 架電 |
| `sfdc_updates_task.json` | `15o649Y3Mg19Z_zTO4W3i2hZR-xaTaZT5` | タスク差分（Dead前後の活動深掘りに） |

### Users（OwnerId → 氏名）
`users.json`（`1aHux3kllYF1G5AP23TxcNNJjwhRJwOn7`）。`OwnerId`/`CreatedById` を氏名へ変換。

### スキル正本（参考）
`_sales-meeting-prep-skill/`（`1Vefo900fjbgaC9s8XRdHiyW7I5NdGVpD`）に正本 `SKILL.md` / `output-template.md` / `queries.md` / `INSTALL.md`。データ置き場 `sales-meeting-prep/`（`1jioxHIXCm5hwGluM6Jj8P85oq9zVmbre`）。

---

## レコードURL（SFDC Lightning）
ベース: `https://hacobu.lightning.force.com/lightning/r/`
- Account: `.../Account/{Id}/view`
- Opportunity: `.../Opportunity/{Id}/view`
- OpportunityDraft__c: `.../OpportunityDraft__c/{Id}/view`

## 運用の推奨（“定位置”）
データが複数のプロジェクト用フォルダに散在し命名もまちまち。確実性を上げるなら、
**商談準備用の固定フォルダ**（例: `_sales-meeting-prep-skill/sales-meeting-prep/data/`）に、対象取引先の
`accounts.json` / `opportunities.json` / `opp_draft.json` を置く運用にすると、スキルは検索不要で確定的に読める。
現状はそれが無いので、本スキルは **タイトル検索＋最新採用＋本文Grep** で動的に解決する。
