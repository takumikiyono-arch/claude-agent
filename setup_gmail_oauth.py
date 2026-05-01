#!/usr/bin/env python3
"""
Gmail OAuth 初期設定スクリプト
-------------------------------
初回のみ実行して token.json を生成する。

事前準備:
  1. Google Cloud Console でプロジェクトを作成し、Gmail API を有効化する
  2. 「OAuth 2.0 クライアント ID」を作成し、credentials.json をダウンロードする
  3. このスクリプトを実行してブラウザ認証を完了させる

使い方:
  python3 setup_gmail_oauth.py [--credentials credentials.json] [--token token.json]
"""

import argparse
import os


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Gmail OAuth トークンを生成する")
    parser.add_argument(
        "--credentials",
        default=os.environ.get("GMAIL_CREDENTIALS_PATH", "credentials.json"),
        help="Google Cloud からダウンロードした credentials.json のパス（デフォルト: credentials.json）",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("GMAIL_TOKEN_PATH", "token.json"),
        help="生成する token.json のパス（デフォルト: token.json）",
    )
    args = parser.parse_args()

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError:
        print(
            "[ERROR] Google ライブラリが未インストールです。\n"
            "  pip install google-auth google-auth-oauthlib google-api-python-client"
        )
        raise SystemExit(1)

    if not os.path.exists(args.credentials):
        print(
            f"[ERROR] credentials.json が見つかりません: {args.credentials}\n\n"
            "手順:\n"
            "  1. https://console.cloud.google.com/ にアクセス\n"
            "  2. プロジェクトを選択（または新規作成）\n"
            "  3. 「APIとサービス」→「ライブラリ」→ Gmail API を有効化\n"
            "  4. 「APIとサービス」→「認証情報」→「認証情報を作成」→「OAuth クライアント ID」\n"
            "  5. アプリケーションの種類: デスクトップアプリ\n"
            "  6. ダウンロードした JSON ファイルを credentials.json として保存\n"
        )
        raise SystemExit(1)

    creds = None
    if os.path.exists(args.token):
        creds = Credentials.from_authorized_user_file(args.token, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("[INFO] トークンを更新中...")
            creds.refresh(Request())
        else:
            print("[INFO] ブラウザを開いてGoogleアカウントで認証してください...")
            flow  = InstalledAppFlow.from_client_secrets_file(args.credentials, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(args.token, "w") as f:
            f.write(creds.to_json())
        print(f"[INFO] トークンを保存しました: {args.token}")
    else:
        print(f"[INFO] 既存の有効なトークンを確認しました: {args.token}")

    # 接続確認
    try:
        from googleapiclient.discovery import build
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        print(f"[INFO] 接続成功 — 認証アカウント: {profile['emailAddress']}")
    except Exception as e:
        print(f"[WARN] 接続確認に失敗しました: {e}")


if __name__ == "__main__":
    main()
