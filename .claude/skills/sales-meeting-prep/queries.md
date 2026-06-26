# 商談事前準備 SOQL パターン（この環境では「項目仕様書」として参照）

> **本環境では `sf` CLI を実行しない**（無いため）。以下の SOQL は、ユーザーが Mac の `sf` で抽出して
> **Google Drive に置いた各エクスポートに、どの項目が含まれるか**を示す仕様書として使う。
> 実データの所在・取得手順は **`drive-data-map.md`** を参照。

## 1. 取引先（Account）の特定
```soql
SELECT Id, Name, Site, BillingState, BillingCity, Phone,
       Company__c, Company__r.Name,
       OwnerId, Owner.Name,
       LastActivityDate, CreatedDate
FROM Account
WHERE Name LIKE '%取引先名%'
  AND IsDeleted = false
ORDER BY Name, Site NULLS FIRST
LIMIT 100
```
**実在しないフィールドに注意**:
- `CompanyGroup__c` は **Account に存在しない**（過去にクエリ失敗の原因）
- `Account_Type__c` も **存在しない**
- 企業グループは `Company__c → Company__r.CompanyGroup__c` 経由で辿る
- personaccount: 原則 除外条件を入れず取得し、結果から目視で除外

→ 本環境では `SFDC企業一覧_Sales&CS` シート等（`drive-data-map.md`）から同等項目を取得。

## 2. Account 配下の商談一覧
```soql
SELECT Id, Name, AccountId, Account.Name, Account.Site,
       StageName, CloseDate, Probability, IsClosed, IsWon,
       Amount, MRR__c, Related_Opportunities_MRR__c,
       ProductName__c, RecordType.Name, RecordType_Name__c,
       OwnerId, Owner.Name, Description,
       ParentOpportunity__c, ParentOpportunity__r.Name,
       CreatedDate, LastModifiedDate, CloseDate
FROM Opportunity
WHERE AccountId IN :accountIds
  AND IsDeleted = false
ORDER BY CloseDate DESC NULLS LAST, CreatedDate DESC
LIMIT 1000
```
| 状態 | 条件 |
|------|------|
| 進行中 | `IsClosed = false` |
| 成立 | `IsWon = true` |
| Dead | `IsClosed = true AND IsWon = false` |

→ 本環境では `【データ定期保存】商談…簡易版CSV`（最新）＋ `FY11/FY12実績DB` から取得。簡易版CSVは列が限定的なので、無い項目は「(要確認)」。

## 3. 商談ドラフトの文字起こし（OpportunityDraft__c.meetingNote__c）
### 軽量版（一覧把握）
```soql
SELECT Id, Name, Opportunity__c, Opportunity__r.Name,
       StageBeforeAppointment__c, StageAfterAppointment__c,
       ProductBeforeAppointment__c, ProductAfterAppointment__c,
       OppIntegrateDataTime__c, IsOppIntegrated__c,
       CreatedDate, CreatedBy.Name
FROM OpportunityDraft__c
WHERE Opportunity__c IN :opportunityIds
  AND IsDeleted = false
ORDER BY OppIntegrateDataTime__c DESC NULLS LAST, CreatedDate DESC
LIMIT 100
```
### 全文取得（meetingNote__c を含む）
```soql
SELECT Id, Name, Opportunity__c, Opportunity__r.Name,
       meetingNote__c,
       StageBeforeAppointment__c, StageAfterAppointment__c,
       ProductBeforeAppointment__c, ProductAfterAppointment__c,
       OppIntegrateDataTime__c, IsOppIntegrated__c,
       CreatedDate, CreatedBy.Name
FROM OpportunityDraft__c
WHERE Id IN :draftIds
  AND IsDeleted = false
ORDER BY OppIntegrateDataTime__c DESC NULLS LAST
LIMIT 30
```
**重要**: `meetingNote__c` は文字起こしで1レコード数万文字になりうる。

→ 本環境では `opp_draft.json`（主）/ `draft_june.json`（30MB・要絞り込み）を Grep で取引先名・`Opportunity__r.Name` で絞り、`meetingNote__c` を `drafts/<Opportunity__c>.txt` に保存（`drive-data-map.md`）。

## 4. 関連の Task（架電）
```soql
SELECT Id, WhatId, Subject, Type, Description, ActivityDate, Status,
       WhoId, Who.Name, OwnerId, Owner.Name, CreatedDate
FROM Task
WHERE WhatId IN :opportunityIds AND Type = 'Call' AND IsDeleted = false
ORDER BY ActivityDate DESC NULLS LAST, CreatedDate DESC
LIMIT 200
```
→ 本環境: `phone_events.json` / `sfdc_updates_task.json`。

## 5. 関連の EmailMessage
```soql
SELECT Id, RelatedToId, Subject, TextBody,
       FromAddress, ToAddress, CcAddress, MessageDate, CreatedDate
FROM EmailMessage
WHERE RelatedToId IN :opportunityIds
ORDER BY MessageDate DESC NULLS LAST, CreatedDate DESC
LIMIT 200
```
→ 本環境: `email_tasks.json`。

## 6. OpportunityHistory（フェーズ変遷）
```soql
SELECT Id, OpportunityId, Opportunity.Name,
       StageName, Amount, Probability, CloseDate,
       CreatedDate, CreatedById, CreatedBy.Name
FROM OpportunityHistory
WHERE OpportunityId IN :opportunityIds
ORDER BY OpportunityId, CreatedDate DESC
LIMIT 1000
```
→ 本環境: `FY11/FY12実績DB` や差分JSONで代替（Dead/フェーズ停滞の把握）。

---

## 原典の実行手順（Mac用・本環境では実行しない）
オリジナルは Mac の zsh で以下を実行していた（参考）:
- `/usr/local/bin/sf data query --file /tmp/q.soql --target-org prod --result-format json 1> out.json 2>/dev/null`
- `--query` ではなく **必ず `--file`**（zsh の `!` 展開対策）、出力は `1> out.json 2>/dev/null`（Warning混入防止）

**本環境ではこれを実行できない**。同等の出力（out.json 群）が Drive に置かれているので、`drive-data-map.md` の手順で読む。
