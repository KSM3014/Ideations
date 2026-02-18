# Publisher

Phase 6 산출물 발행 스킬.

## 역할

최종 선별된 아이디어를 대시보드 배치로 기록하고, S/A급 아이디어를 Discord 웹훅으로 발송하며, 아카이브에 저장한다.

## 스크립트

| 파일 | 역할 |
|------|------|
| `dashboard_writer.py` | dashboard_batches.jsonl 원자적 배치 기록 |
| `discord_notifier.py` | Discord 웹훅 리치 embed 발송 (S/A급, 이상 알림) |
| `report_generator.py` | 일간/주간 누적 리포트 생성 |
| `archive_manager.py` | ideas_archive.jsonl 아카이브 관리 + 최근 서비스명 조회 |

## 호출자

`run_engine.py` Phase 6에서 호출:
1. `DashboardWriter.write_batch()` — JSONL 기록
2. `DiscordNotifier.notify_idea()` — S/A급 웹훅
3. `ArchiveManager.archive_ideas()` — 아카이브 저장

## Discord Embed

S급 발견 시 리치 embed 포맷:
- 서비스명, NUMR-V 점수, 구현 가능성, MVP 기간
- 문제/솔루션/시장 검증/API 구현 요약
- 트리거 신호

## 이상 알림

| 조건 | 알림 |
|------|------|
| 연속 3회 Phase 실패 | 시스템 경고 |
| 연속 6시간 0개 산출 | 품질 게이트 점검 |
| Claude CLI 3회 연속 파싱 실패 | 에스컬레이션 |
