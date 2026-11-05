import type { FacilityBasisGroup, FacilityZoneResponse, RoutePeriod } from "@/lib/api";
import { factorNames } from "@/lib/zoneDisplay";
import styles from "./FacilityBasisPicker.module.css";

const DAYS = ["월", "화", "수", "목", "금", "토", "일"];

export function FacilityBasisPicker({ period, onPeriod, basisId, onBasis, report, changedGroups }: {
  period?: RoutePeriod;
  onPeriod: (period: RoutePeriod | undefined) => void;
  basisId?: string;
  onBasis: (basis: string | undefined) => void;
  report?: FacilityZoneResponse | null;
  changedGroups?: FacilityBasisGroup[] | null;
}) {
  const groups = changedGroups ?? report?.groups ?? [];
  return (
    <div className={styles.controls}>
      <label>대표 시각
        <select value={period ?? ""} onChange={event => onPeriod((event.target.value || undefined) as RoutePeriod | undefined)}>
          <option value="">현재 시간대</option>
          <option value="day">낮 12시</option>
          <option value="night">밤 23시</option>
        </select>
      </label>
      {(groups.length > 0 || changedGroups) && (
        <label>순위 비교 집합
          <select value={changedGroups ? "changed" : basisId ?? report?.basis_id ?? "default"}
            onChange={event => onBasis(event.target.value === "default" ? undefined : event.target.value)}>
            {changedGroups && <option value="changed" disabled>다시 선택해 주세요</option>}
            <option value="default">기본 비교 집합</option>
            {groups.map(group => <option key={group.basis_id} value={group.basis_id}>
              {factorNames(group.used_factors)} ({group.zone_count}개 동)
            </option>)}
          </select>
        </label>
      )}
      {report && <p>{DAYS[report.weekday]}요일 {report.reference_hour}:00 기준 · 공개 자료와 지도에 있는 보행로 기준</p>}
    </div>
  );
}
