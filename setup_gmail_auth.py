#!/usr/bin/env python3
"""
Gmail OAuth2 初回認証セットアップスクリプト
----------------------------------------------
Google Cloud Console で作成した credentials.json を用意してから実行:
  python3 setup_gmail_auth.py

環境変数で場所を変更できる:
  GMAIL_CREDENTIALS_FILE  credentials.json のパス (デフォルト: ~/.gmail_credentials.json)
  GMAIL_TOKEN_FILE        token.json の保存先   (デフォルト: ~/.gmail_token.json)

手順:
  1. https://console.cloud.google.com/ でプロジェクトを作成
  2. 「APIとサービス」→「ライブラリ」で Gmail API を有効化
  3. 「認証情報」→「OAuth 2.0 クライアント ID」を作成（デスクトップアプリ）
  4. 「OAuth同意画面」→ スコープに gmail.readonly を追加 → 自分のアドレスをテストユーザーに追加
  5. JSON をダウンロードして GMAIL_CREDENTIALS_FILE の場所に置く
  6. このスクリプトを実行するとブラウザが開き認証完了
"""

import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

CREDENTIALS_FILE = os.environ.get(
    "GMAIL_CREDENTIALS_FILE", str(Path.home() / ".gmail_credentials.json")
)
TOKEN_FILE = os.environ.get(
    "GMAIL_TOKEN_FILE", str(Path.home() / ".gmail_token.json")
)


def main() -> None:
    if not Path(CREDENTIALS_FILE).exists():
        print(f"[ERROR] credentials.json が見つかりません: {CREDENTIALS_FILE}")
        print("        Google Cloud Console からダウンロードして配置してください。")
        raise SystemExit(1)

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

    print(f"[OK] 認証完了。トークンを保存しました: {TOKEN_FILE}")
    print("     check_pending_replies.py でこのトークンが使用されます。")


if __name__ == "__main__":
    main()
