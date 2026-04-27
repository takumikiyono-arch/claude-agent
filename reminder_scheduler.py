#!/usr/bin/env python3
"""
Slack Mention Reminder Scheduler
毎時0分に check_slack_mentions.py を実行する。
8〜19時の時間帯のみ実行し、それ以外はスキップ。
"""

import os
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import schedule
import time

SCRIPT_DIR = Path(__file__).parent
PID_FILE   = SCRIPT_DIR / "scheduler.pid"
LOG_FILE   = SCRIPT_DIR / "scheduler.log"


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def run_check() -> None:
    hour = datetime.now().hour
    if hour < 8 or hour >= 20:
        log(f"時間外（{hour}時）のためスキップ")
        return

    log("Slackメンションチェック開始")
    env = os.environ.copy()

    # .env ファイルがあれば読み込む
    env_file = SCRIPT_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                env.setdefault(key.strip(), val.strip())

    python = SCRIPT_DIR / ".venv" / "bin" / "python3"
    if not python.exists():
        python = Path(sys.executable)

    result = subprocess.run(
        [str(python), str(SCRIPT_DIR / "check_slack_mentions.py")],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        log(result.stdout.rstrip())
    if result.stderr:
        log(f"[STDERR] {result.stderr.rstrip()}")
    if result.returncode != 0:
        log(f"[ERROR] 終了コード {result.returncode}")


def handle_signal(sig, frame):
    log("シャットダウンシグナルを受信。終了します。")
    PID_FILE.unlink(missing_ok=True)
    sys.exit(0)


def main() -> None:
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    PID_FILE.write_text(str(os.getpid()))
    log(f"スケジューラー起動 (PID {os.getpid()})")

    # 毎時0分に実行
    schedule.every().hour.at(":00").do(run_check)

    log("スケジュール登録完了：毎時0分、8〜19時のみ実行")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
