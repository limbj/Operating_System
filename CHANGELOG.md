# Integration Notes

## Final integrated version

- `develop_Lim`의 알고리즘별 파일 구조를 정리하고 공통 엔진을 `scheduler.py`로 통합
- `develop_SJ`의 PyQt GUI와 이미지 리소스를 복원하고 실제 스케줄러에 연결
- `master` / `optical_Power`에서 사용하던 P-Core / E-Core 전력 계산과 결과 지표 반영
- `E_Core_Conditions` 및 개발 문서의 P/E-Core 배치 조건을 DRR 정책에 반영
- RR 고정 Time Quantum과 DRR Dynamic Time Quantum 분리
- FCFS / RR / SPN / SRTN / HRRN / DRR 모두 동일한 결과 모델 사용
- AT / BT / WT / TT / NTT / Completion Time 계산 일원화
- Core별 Gantt timeline 및 누적 전력 기록 일원화
- BT >= 30인 DRR 프로세스는 30 work unit 처리 시 강제 종료
- P-Core 최대 3개, E-Core 최대 1개 제한 추가
- 사용하지 않는 Core에 전력이 잘못 계산되던 문제 방지
- 기존 알고리즘 파일의 `main(Info)` 호출 형식을 wrapper로 유지
- 단위 테스트 추가
- 불필요한 Office 임시 파일과 빈 `scheduler.py` 제거
