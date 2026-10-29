#!/usr/bin/env bash
# 后台常驻启动（Linux / macOS）。用法：bash start.sh
# 挂了会自动拉起来；日志在 server.log。
cd "$(dirname "$0")" || exit 1

export DICE_HOST="${DICE_HOST:-127.0.0.1}"
export DICE_PORT="${DICE_PORT:-8790}"
# 挂在 nginx 等反代后面时取消下面这行注释，免得把反代的 127.0.0.1 误认成主人
# export DICE_BEHIND_PROXY=1

while true; do
  python3 server.py --host "$DICE_HOST" --port "$DICE_PORT" --quiet --no-browser >> server.log 2>&1
  echo "[$(date '+%F %T')] server exited (code $?), restarting in 3s" >> server.log
  sleep 3
done
