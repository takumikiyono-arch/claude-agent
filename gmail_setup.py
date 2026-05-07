#!/usr/bin/env python3
"""
Gmail OAuth 初回認証セットアップ
--------------------------------
このスクリプトを一度だけ対話的に実行し、Google アカウントの認証を完了させてください。
認証後は gmail_token.json にトークンが保存され、check_pending_replies.py が
そのトークンを使って無人でメールを取得します。

事前準備:
  1. Google Cloud Console でプロジェクトを作成し、Gmail API を有効化する。
  2. OAuth 同意画面を設定し、スコープ gmail.readonly を追加する。
  3. 「デスクトップ アプリ」の OAuth クライアント ID を作成し、
     credentials.json としてこのスクリプトと同じディレクトリに配置する。

実行方法:
  pip install google-auth-oauthlib google-api-python-client
  python gmail_setup.py
"""

from pathlib import Path

SCRIPT_DIR       = Path(__file__).parent
CREDENTIALS_PATH = SCRIPT_DIR / "gmail_credentials.json"
TOKEN_PATH       = SCRIPT_DIR / "gmail_token.json"
SCOPES           = ["https://www.googleapis.com/auth/gmail.readonly"]


def main() -> None:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("[ERROR] google-auth-oauthlib がインストールされていません。")
        print("  pip install google-auth-oauthlib google-api-python-client")
        raise SystemExit(1)

    if not CREDENTIALS_PATH.exists():
        print(f"[ERROR] {CREDENTIALS_PATH} が見つかりません。")
        print("  Google Cloud Console から credentials.json をダウンロードして配置してください。")
        raise SystemExit(1)

    flow  = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_PATH.write_text(creds.to_json())
    print(f"[OK] 認証完了。トークンを {TOKEN_PATH} に保存しました。")
    print("     次回以降は check_pending_replies.py が自動でトークンを使用します。")


if __name__ == "__main__":
    main()
