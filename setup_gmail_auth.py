#!/usr/bin/env python3
"""
Gmail OAuth 初回認証セットアップ
---------------------------------
このスクリプトを一度だけ手動で実行してください。
ブラウザが開き、Google アカウントへのアクセスを許可すると
gmail_token.json が生成されます。以降は自動的にトークンが更新されます。

使い方:
  1. Google Cloud Console で OAuth 2.0 クライアント ID (デスクトップアプリ) を作成
  2. credentials.json をこのスクリプトと同じディレクトリに置く
  3. python3 setup_gmail_auth.py を実行し、ブラウザで認証
  4. gmail_token.json が生成されれば完了

環境変数:
  GMAIL_CREDENTIALS_FILE  credentials.json のパス (デフォルト: ./credentials.json)
  GMAIL_TOKEN_FILE        保存先トークンパス     (デフォルト: ./gmail_token.json)
"""

import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES               = ["https://www.googleapis.com/auth/gmail.readonly"]
CREDENTIALS_FILE     = os.environ.get("GMAIL_CREDENTIALS_FILE",
                                      os.path.join(os.path.dirname(__file__), "credentials.json"))
TOKEN_FILE           = os.environ.get("GMAIL_TOKEN_FILE",
                                      os.path.join(os.path.dirname(__file__), "gmail_token.json"))


def main() -> None:
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"[ERROR] credentials.json が見つかりません: {CREDENTIALS_FILE}")
        print()
        print("Google Cloud Console でのセットアップ手順:")
        print("  1. https://console.cloud.google.com/ にアクセス")
        print("  2. プロジェクトを選択（または新規作成）")
        print("  3. 「API とサービス」→「ライブラリ」→「Gmail API」を有効化")
        print("  4. 「認証情報」→「認証情報を作成」→「OAuth クライアント ID」")
        print("  5. アプリの種類: 「デスクトップ アプリ」を選択")
        print("  6. 作成後、JSON をダウンロードして credentials.json として保存")
        return

    print("ブラウザで Google アカウントの認証画面を開きます...")
    flow  = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

    print(f"[OK] トークンを保存しました: {TOKEN_FILE}")
    print("これ以降、check_awaiting_replies.py が自動的に Gmail を確認します。")


if __name__ == "__main__":
    main()
