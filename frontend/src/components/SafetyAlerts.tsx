import type { SafeHaven } from "@/lib/api";
import { HAVEN_LABEL, havenDirectionsUrl } from "@/lib/havens";
import { formatDistance } from "@/lib/routeGuidance";
import styles from "./SafetyAlerts.module.css";

type Props = {
  // 지금 자리 점수가 낮을 때 보여줄 가장 가까운 안심 거점(없으면 경고만).
  lowSpot: boolean;
  haven: SafeHaven | null;
  // 예상 도착 시간이 지났는지.
  overdue: boolean;
  onSnooze: () => void;
  onNotifyGuardians: () => void;
};

export function SafetyAlerts({ lowSpot, haven, overdue, onSnooze, onNotifyGuardians }: Props) {
  if (!lowSpot && !overdue) return null;
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
      {lowSpot && (
        <section className={styles.card} role="status">
          <p className={styles.title}>지금 지나는 길은 밝은 시설이 적어요</p>
          {haven ? (
            <p className={styles.text}>
              가장 가까운 {HAVEN_LABEL[haven.kind]} <strong>{formatDistance(haven.distance_m)}</strong>{" "}
              <a href={havenDirectionsUrl(haven)} target="_blank" rel="noopener noreferrer">
                위치 보기
              </a>
            </p>
          ) : (
            <p className={styles.text}>근처 1.5km 안에 파출소·24시 편의점이 없어요. 큰길로 걸어 주세요.</p>
          )}
        </section>
      )}
    </div>
  );
}
