import { useEffect, useState } from "react";
import { changedFacilityGroups, facilityZones, type FacilityBasisGroup, type FacilityZoneResponse, type RoutePeriod } from "./api";

type QueryState = { key: string; report: FacilityZoneResponse | null; groups: FacilityBasisGroup[] | null; error: string | null };

export function useFacilityZones(enabled: boolean, period?: RoutePeriod, basisId?: string, codes?: string[]) {
  const codeKey = codes?.join(",") ?? "";
  const key = JSON.stringify([period, basisId, codeKey]);
  const [state, setState] = useState<QueryState | null>(null);
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    facilityZones({ period, basisId, codes: codeKey ? codeKey.split(",") : undefined, signal: controller.signal })
      .then(report => {
        if (!controller.signal.aborted) setState({ key, report, groups: null, error: null });
      })
      .catch(error => {
        if (!controller.signal.aborted) setState({ key, report: null, groups: changedFacilityGroups(error),
          error: error instanceof Error ? error.message : "동네 시설 평가를 불러오지 못했어요." });
      });
    return () => controller.abort();
  }, [enabled, key, period, basisId, codeKey]);
  return enabled && state?.key === key ? state : null;
}
