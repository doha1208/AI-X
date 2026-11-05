"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  applyScoringProfile,
  createScoringProfileDraft,
  listScoreBuilds,
  listScoringProfiles,
  type ScoreBuild,
  type ScoreWeights,
  type ScoringProfile,
  assessmentStatus,
  type AssessmentStatus,
} from "@/lib/api";
import { FACILITY_ALERT_POLICY } from "@/lib/facility_alerts";
import { getSessionUser } from "@/lib/auth";

const FACTORS = [
  ["cctv_count", "CCTV"],
  ["streetlight_count", "보안등"],
  ["crime_rate", "범죄율"],
  ["police_dist_m", "경찰서 거리"],
  ["store_count", "상점 수"],
  ["bell_dist_m", "비상벨 거리"],
  ["accident_dist_m", "사고 다발지역 거리"],
  ["night_floating_pop", "야간 유동인구"],
] as const;

const DEFAULT_WEIGHTS: ScoreWeights = {
  day: { cctv_count: 0.2, streetlight_count: 0.15, crime_rate: 0.2, police_dist_m: 0.1, store_count: 0.15, bell_dist_m: 0.1, accident_dist_m: 0.1, night_floating_pop: 0 },
  night: { cctv_count: 0.15, streetlight_count: 0.25, crime_rate: 0.2, police_dist_m: 0.05, store_count: 0.05, bell_dist_m: 0.1, accident_dist_m: 0.1, night_floating_pop: 0.1 },
};

function cloneWeights(weights: ScoreWeights): ScoreWeights {
  return { day: { ...weights.day }, night: { ...weights.night } };
}

export default function ScoringAdminPage() {
  const router = useRouter();
  const [profiles, setProfiles] = useState<ScoringProfile[]>([]);
  const [builds, setBuilds] = useState<ScoreBuild[]>([]);
  const [weights, setWeights] = useState<ScoreWeights>(() => cloneWeights(DEFAULT_WEIGHTS));
  const [version, setVersion] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [unknownScore, setUnknownScore] = useState(50);
  const [message, setMessage] = useState("관리자 권한을 확인하는 중입니다.");
  const [forbidden, setForbidden] = useState(false);
  const [assessment, setAssessment] = useState<AssessmentStatus | null>(null);
  const [assessmentError, setAssessmentError] = useState(false);

  const refreshAssessment = useCallback(async () => {
    try { setAssessment(await assessmentStatus()); setAssessmentError(false); }
    catch { setAssessment(null); setAssessmentError(true); }
  }, []);

  const totals = useMemo(
    () => ({ day: Object.values(weights.day).reduce((sum, value) => sum + value, 0), night: Object.values(weights.night).reduce((sum, value) => sum + value, 0) }),
    [weights]
  );
  const pending = builds.some((build) => build.status === "queued" || build.status === "building");

  const refresh = useCallback(async () => {
    try {
      const [nextProfiles, nextBuilds] = await Promise.all([listScoringProfiles(), listScoreBuilds()]);
      setProfiles(nextProfiles);
      setBuilds(nextBuilds);
      setForbidden(false);
      setMessage("");
      void refreshAssessment();
    } catch (error) {
      const text = error instanceof Error ? error.message : "관리자 정보를 불러오지 못했습니다.";
      setForbidden(text.includes("관리자 권한") || text.includes("Request failed: 403"));
      setMessage(text);
    }
  }, [refreshAssessment]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        await getSessionUser();
        const [nextProfiles, nextBuilds] = await Promise.all([
          listScoringProfiles(),
          listScoreBuilds(),
        ]);
        if (cancelled) return;
        setProfiles(nextProfiles);
        setBuilds(nextBuilds);
        setForbidden(false);
        setMessage("");
        try { const status = await assessmentStatus(); if (!cancelled) { setAssessment(status); setAssessmentError(false); } }
        catch { if (!cancelled) setAssessmentError(true); }
      } catch (error) {
        if (cancelled) return;
        const text = error instanceof Error ? error.message : "관리자 정보를 불러오지 못했습니다.";
        if (text.includes("401")) {
          router.replace("/login");
          return;
        }
        setForbidden(text.includes("관리자 권한") || text.includes("Request failed: 403"));
        setMessage(text);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [router]);

  useEffect(() => {
    if (!pending) return;
    const intervalId = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(intervalId);
  }, [pending, refresh]);

  function updateWeight(period: "day" | "night", factor: string, value: number) {
    setWeights((current) => ({ ...current, [period]: { ...current[period], [factor]: value } }));
  }

  async function saveDraft() {
    if (!version.trim() || !name.trim()) {
      setMessage("버전과 이름을 입력하세요.");
      return;
    }
    if (Math.abs(totals.day - 1) > 1e-9 || Math.abs(totals.night - 1) > 1e-9) {
      setMessage("낮과 밤 가중치 합계는 각각 1.0이어야 합니다.");
      return;
    }
    try {
      const profile = await createScoringProfileDraft({
        version: version.trim(), name: name.trim(), description: description.trim() || null, weights, unknown_score: unknownScore,
      });
      setProfiles((current) => [profile, ...current]);
      setMessage("초안을 저장했습니다. 적용하면 현재 데이터로 새 산출물을 빌드합니다.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "초안 저장에 실패했습니다.");
    }
  }

  async function apply(profile: ScoringProfile) {
    try {
      const build = await applyScoringProfile(profile.id);
      setBuilds((current) => [build, ...current]);
      setMessage(`${profile.version} 적용 작업을 대기열에 넣었습니다.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "적용 요청에 실패했습니다.");
    }
  }

  if (forbidden) return <main style={{ padding: 32 }}><h1>접근 권한 없음</h1><p>관리자만 점수 프로필을 변경할 수 있습니다.</p></main>;

  return (
    <main style={{ maxWidth: 1040, margin: "0 auto", padding: "32px 20px", display: "grid", gap: 24 }}>
      <header><h1>지역 통계 지수 프로필 관리</h1><p>아래 가중치는 지역 통계 지수에만 적용합니다. 시설 반경·동일 비중 계산·실시간 알림 임계값은 변경하지 않습니다. 적용은 현재 데이터로 새 산출물을 빌드합니다. 성공한 빌드만 활성화되며 실패하면 기존 산출물을 유지합니다.</p></header>
      <section><h2>시설 평가·알림 정책 (조회 전용)</h2>
        {assessment ? <>
          <p>모델 {assessment.facility_assessment.model_version ?? "미적용"} · 정책 {assessment.facility_assessment.policy_version} · {assessment.facility_assessment.applied ? "적용됨" : "준비 중"} · 산출물 {assessment.facility_assessment.artifact_version ?? "없음"}</p>
          <p>{assessment.route_artifact.area_environment_ready ? "주변 평가 준비" : "주변 평가 준비 중"} · {assessment.route_artifact.zone_environment_ready ? "동별 평가 준비" : "동별 평가 준비 중"}</p>
        </> : <p>{assessmentError ? "시설 적용 상태를 확인하지 못했습니다." : "시설 적용 상태 확인 중"}</p>}
        <p>실시간 알림 {FACILITY_ALERT_POLICY.version} · 전방 {FACILITY_ALERT_POLICY.lookaheadM}m · 발동 {FACILITY_ALERT_POLICY.triggerM}m · 해제 {FACILITY_ALERT_POLICY.clearM}m · 반복 {FACILITY_ALERT_POLICY.cooldownMs / 1000}초 (현재 프런트엔드 정책)</p>
        <button type="button" onClick={() => void refreshAssessment()}>시설 상태 다시 확인</button>
      </section>
      {message && <p role="status">{message}</p>}
      <section style={{ display: "grid", gap: 12 }}>
        <h2>새 초안</h2>
        <label>버전 <input value={version} onChange={(event) => setVersion(event.target.value)} placeholder="2026-09-26-v1" /></label>
        <label>이름 <input value={name} onChange={(event) => setName(event.target.value)} placeholder="야간 보안등 강화" /></label>
        <label>설명 <input value={description} onChange={(event) => setDescription(event.target.value)} /></label>
        <label>중립 점수 <input type="number" min="0" max="100" value={unknownScore} onChange={(event) => setUnknownScore(Number(event.target.value))} /></label>
        <div style={{ overflowX: "auto" }}><table><thead><tr><th>요인</th><th>낮</th><th>밤</th></tr></thead><tbody>{FACTORS.map(([factor, label]) => <tr key={factor}><td>{label}</td>{(["day", "night"] as const).map((period) => <td key={period}><input aria-label={`${label} ${period}`} type="number" min="0" max="1" step="0.01" value={weights[period][factor]} onChange={(event) => updateWeight(period, factor, Number(event.target.value))} /></td>)}</tr>)}</tbody><tfoot><tr><th>합계</th><td>{totals.day.toFixed(2)}</td><td>{totals.night.toFixed(2)}</td></tr></tfoot></table></div>
        <button type="button" onClick={saveDraft}>초안 저장</button>
      </section>
      <section><h2>프로필 버전</h2><ul style={{ display: "grid", gap: 10 }}>{profiles.map((profile) => <li key={profile.id}><strong>{profile.version}</strong> · {profile.name} · {profile.status} <button type="button" onClick={() => void apply(profile)}>현재 데이터로 적용</button></li>)}</ul></section>
      <section><h2>빌드 상태 {pending ? "(자동 새로고침 중)" : ""}</h2><ul style={{ display: "grid", gap: 10 }}>{builds.map((build) => <li key={build.id}><strong>{build.profile_version}</strong> · {build.status}{build.artifact_version ? ` · ${build.artifact_version}` : ""}{build.error_code ? ` · ${build.error_code}` : ""}</li>)}</ul></section>
    </main>
  );
}
