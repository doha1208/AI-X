import { FACILITY_ALERT_POLICY } from "@/lib/facility_alerts";

/** Explanations only; calculation versions and results come from each API response. */
export function AssessmentExplanation({ textClassName }: { textClassName?: string }) {
  return <>
    <p className={textClassName}><strong>지역 통계 지수</strong>는 행정동의 시설 밀도·범죄율·경찰서/비상벨/사고지역 거리·야간 유동인구를 비교하는 상대 지수입니다. 기본 프로필은 default-v3이며 관리자 적용 프로필에 따라 달라집니다. 거주지의 기본 순위에 사용하고 경로 점수에는 합산하지 않습니다.</p>
    <p className={textClassName}><strong>보행 시설 접근성</strong>은 경로·집 주변·동별 보행로를 같은 facility-access-v1 모델로 평가합니다. environment-v1-draft 정책은 CCTV 60m·보안등 40m·영업시간이 확인된 상점 50m·비상벨 200m를 사용합니다. 낮에는 보안등을 제외합니다. 거리로 가중한 지표별 인접 비율을 공통 지표끼리 동일 비중으로 평균합니다. 둘 이상이면 종합 점수, 하나면 단일 지표 참고, 일부 구간만 확인되면 부분자료 범위로 구분합니다. 미확인을 부재나 0점으로 채우지 않습니다.</p>
    <p className={textClassName}>주야간 경계는 KST 22시~다음 날 6시입니다. 수동 경로·주변·동별 비교는 해당 날짜/요일의 낮 12시·밤 23시를 기준으로 하며 실시간 안내는 현재 시각을 사용합니다. 평가별 모델·정책·자료 버전과 기준 시각이 다르므로 같은 기준끼리 비교하세요.</p>
    <p className={textClassName}><strong>실시간 시설 공백 안내</strong>는 {FACILITY_ALERT_POLICY.version} 정책을 사용합니다. 전방 {FACILITY_ALERT_POLICY.lookaheadM}m의 확인된 야간 조명 공백이 {FACILITY_ALERT_POLICY.triggerM}m 이상이면 안내하고, {FACILITY_ALERT_POLICY.clearM}m 미만이면 해제합니다. 음성은 공백 시작 {FACILITY_ALERT_POLICY.startProximityM}m 이내에서, 같은 공백은 {FACILITY_ALERT_POLICY.cooldownMs / 1000}초 간격으로 제한합니다. 비상벨 점수가 높아도 조명 공백은 따로 안내하며 미확인은 위험으로 단정하지 않습니다.</p>
    <p className={textClassName}>시설 좌표·공개 시간표는 현재 영업·유인·작동 상태를 보장하지 않습니다. 시설 반경과 알림 기준은 시제품 정책값이며 안전 확률이 아닙니다. 공개 자료 기반 참고 정보로 실제 안전을 보장하지 않습니다.</p>
  </>;
}
