#!/bin/bash
# 카탈로그 갱신 스케줄러 — cron 또는 Windows Task Scheduler에서 호출
# Windows 환경에서는 scripts/scheduler_control.bat 또는 직접 python 실행 권장
#
# cron 예시 (Linux/WSL):
#   # 주간 증분: 매주 일요일 03:00 KST
#   0 3 * * 0 /path/to/refresh_scheduler.sh
#
# 사용법:
#   ./refresh_scheduler.sh              # 자동 판단 (주간/월간)
#   ./refresh_scheduler.sh incremental  # 증분만
#   ./refresh_scheduler.sh full         # 전수 스캔

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"

# 가상환경 활성화
if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

MODE="${1:-auto}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Catalog refresh starting — mode: $MODE"

python "$PROJECT_ROOT/scripts/catalog_refresh.py" --mode "$MODE"

EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Catalog refresh completed successfully"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Catalog refresh failed with exit code $EXIT_CODE" >&2
fi

exit $EXIT_CODE
