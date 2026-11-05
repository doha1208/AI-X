import type { LiveFacilityReport, SafeHaven } from "@/lib/api";
import { bestHaven, HAVEN_LABEL, havenAvailabilityText, havenDirectionsUrl } from "@/lib/havens";
import { formatDistance } from "@/lib/routeGuidance";
import { facilityAlertText, type FacilityAlert } from "@/lib/facility_alerts";
import styles from "./SafetyAlerts.module.css";

type Props = {
  facilityAlert: FacilityAlert | null;
  haven: SafeHaven | null;
  // 예상 도착 시간이 지났는지.
  overdue: boolean;
  onSnooze: () => void;
  onNotifyGuardians: () => void;
};

function HavenDetails({ haven }: { haven: SafeHaven | null }) {
  if (!haven) return <p className={styles.text}>현재 자료에서 가까운 안심 거점을 확인하지 못했어요.</p>;
  const status = havenAvailabilityText(haven);
  return <p className={styles.text}>
    {HAVEN_LABEL[haven.kind]} <strong>{formatDistance(haven.distance_m)}</strong>
    {status && ` · ${status}`}{" "}
    <a href={havenDirectionsUrl(haven)} target="_blank" rel="noopener noreferrer">위치 보기</a>
  </p>;
}

const LOCAL_FACTORS: Record<string, string> = { cctv: "CCTV", lighting: "보안등", open_store: "영업 확인 상점" };

export function LiveFacilityDetails({ report }: { report: LiveFacilityReport | null }) {
  const point = report?.local_environment;
  const factors = point?.period === "night" ? ["lighting", "open_store"] : ["cctv", "open_store"];
  const moment = report ? new Date(report.evaluated_at) : null;
  const kst = moment && Number.isFinite(moment.getTime())
    ? new Date(moment.getTime() + 9 * 60 * 60 * 1000).toISOString().slice(0, 19).replace("T", " ") : null;
  const assessment = point ?? report?.assessment;
  return <details className={styles.liveDetails}>
    <summary>실시간 시설 정보</summary>
    {report && <p className={styles.text}>실제 평가: {kst ? `KST ${kst}` : "시각 미확인"} · {report.period === "night" ? "밤" : "낮"}{report.status === "pending" ? " · 시설 근거 준비 중" : ""}</p>}
    {report && <p className={styles.text}>모델 {assessment?.model_version ?? "미확인"} · 정책 {assessment?.policy_version ?? "미확인"} · 산출물 {report.artifact_version ?? "미준비"}</p>}
    {point ? factors.map(factor => {
      const state = point.factors[factor]?.state;
      const label = state === "present" ? "인접 근거 있음" : state === "absent_in_verified_inventory"
        ? "검증 목록에서 인접 시설 미관측" : "자료 미확인";
      return <p className={styles.text} key={factor}>{LOCAL_FACTORS[factor]}: {label}</p>;
    }) : <p className={styles.text}>현재 시각의 시설 근거를 확인하지 못했어요.</p>}
    <HavenDetails haven={report ? bestHaven(report.havens) : null} />
  </details>;
}

export function SafetyAlerts({ facilityAlert, haven, overdue, onSnooze, onNotifyGuardians }: Props) {
  if (!facilityAlert && !overdue) return null;
  return (
    <div className={styles.stack}>
      {overdue && (
        <section className={`${styles.card} ${styles.overdue}`} role="alert">
          <p className={styles.title}>예상 도착 시간이 지났어요. 괜찮으세요?</p>
          <div className={styles.actions}>
            <button type="button" className={styles.secondary} onClick={onSnooze}>
              괜찮아요 (10분 더)
            </button>
            <button type="button" className={styles.primary} onClick={onNotifyGuardians}>
              보호자에게 알리기
            </button>
          </div>
        </section>
      )}
      {facilityAlert && (
        <section className={styles.card} role="status">
          <p className={styles.title}>{facilityAlertText(facilityAlert)}</p>
          <HavenDetails haven={haven} />
        </section>
      )}
    </div>
  );
}
