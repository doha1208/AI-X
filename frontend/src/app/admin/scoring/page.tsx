"use client";

import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import {
  applyScoringProfile,
  createScoringProfileDraft,
  listScoreBuilds,
  listScoringProfiles,
  type ScoreBuild,
  type ScoreWeights,
  type ScoringProfile,
} from "@/lib/api";
import { getToken } from "@/lib/auth";

const FACTORS = [
  ["cctv_count", "CCTV"],
  ["streetlight_count", "보안등"],
  ["crime_rate", "범죄율"],
  ["police_dist_m", "경찰서 거리"],
  ["store_count", "상점 수"],
  ["bell_dist_m", "비상벨 거리"],
] as const;

const DEFAULT_WEIGHTS: ScoreWeights = {
  day: { cctv_count: 0.25, streetlight_count: 0.1, crime_rate: 0.3, police_dist_m: 0.1, store_count: 0.15, bell_dist_m: 0.1 },
  night: { cctv_count: 0.15, streetlight_count: 0.25, crime_rate: 0.25, police_dist_m: 0.1, store_count: 0.1, bell_dist_m: 0.15 },
};

function subscribeToBrowserState() {
  return () => {};
}

function getServerToken() {
  return null;
}

function cloneWeights(weights: ScoreWeights): ScoreWeights {
  return { day: { ...weights.day }, night: { ...weights.night } };
}

export default function ScoringAdminPage() {
  const router = useRouter();
  const token = useSyncExternalStore(subscribeToBrowserState, getToken, getServerToken);
  const [profiles, setProfiles] = useState<ScoringProfile[]>([]);
  const [builds, setBuilds] = useState<ScoreBuild[]>([]);
  const [weights, setWeights] = useState<ScoreWeights>(() => cloneWeights(DEFAULT_WEIGHTS));
  const [version, setVersion] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [unknownScore, setUnknownScore] = useState(50);
  const [message, setMessage] = useState("관리자 권한을 확인하는 중입니다.");
  const [forbidden, setForbidden] = useState(false);

  const totals = useMemo(
    () => ({ day: Object.values(weights.day).reduce((sum, value) => sum + value, 0), night: Object.values(weights.night).reduce((sum, value) => sum + value, 0) }),
    [weights]
  );
  const pending = builds.some((build) => build.status === "queued" || build.status === "building");

  const refresh = useCallback(async (activeToken: string) => {
    try {
      const [nextProfiles, nextBuilds] = await Promise.all([listScoringProfiles(activeToken), listScoreBuilds(activeToken)]);
      setProfiles(nextProfiles);
      setBuilds(nextBuilds);
      setForbidden(false);
      setMessage("");
    } catch (error) {
      const text = error instanceof Error ? error.message : "관리자 정보를 불러오지 못했습니다.";
      setForbidden(text.includes("관리자 권한") || text.includes("Request failed: 403"));
      setMessage(text);
    }
  }, []);

  useEffect(() => {
    if (!token) {
      router.replace("/login");
      return;
    }
    const activeToken = token;
    let cancelled = false;
    async function load() {
      try {
        const [nextProfiles, nextBuilds] = await Promise.all([
          listScoringProfiles(activeToken),
          listScoreBuilds(activeToken),
        ]);
        if (cancelled) return;
        setProfiles(nextProfiles);
        setBuilds(nextBuilds);
        setForbidden(false);
        setMessage("");
      } catch (error) {
        if (cancelled) return;
        const text = error instanceof Error ? error.message : "관리자 정보를 불러오지 못했습니다.";
        setForbidden(text.includes("관리자 권한") || text.includes("Request failed: 403"));
        setMessage(text);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [router, token]);

  useEffect(() => {
    if (!token || !pending) return;
    const intervalId = window.setInterval(() => void refresh(token), 3000);
    return () => window.clearInterval(intervalId);
  }, [token, pending, refresh]);

  function updateWeight(period: "day" | "night", factor: string, value: number) {
    setWeights((current) => ({ ...current, [period]: { ...current[period], [factor]: value } }));
  }

  async function saveDraft() {
    if (!token) return;
    if (!version.trim() || !name.trim()) {
      setMessage("버전과 이름을 입력하세요.");
      return;
    }
    if (Math.abs(totals.day - 1) > 1e-9 || Math.abs(totals.night - 1) > 1e-9) {
      setMessage("낮과 밤 가중치 합계는 각각 1.0이어야 합니다.");
      return;
    }
    try {
      const profile = await createScoringProfileDraft(token, {
        version: version.trim(), name: name.trim(), description: description.trim() || null, weights, unknown_score: unknownScore,
      });
      setProfiles((current) => [profile, ...current]);
      setMessage("초안을 저장했습니다. 적용하면 현재 데이터로 새 산출물을 빌드합니다.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "초안 저장에 실패했습니다.");
    }
  }

  async function apply(profile: ScoringProfile) {
    if (!token) return;
    try {
      const build = await applyScoringProfile(token, profile.id);
      setBuilds((current) => [build, ...current]);
      setMessage(`${profile.version} 적용 작업을 대기열에 넣었습니다.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "적용 요청에 실패했습니다.");
    }
  }

  if (forbidden) return <main style={{ padding: 32 }}><h1>접근 권한 없음</h1><p>관리자만 점수 프로필을 변경할 수 있습니다.</p></main>;

  return (
    <main style={{ maxWidth: 1040, margin: "0 auto", padding: "32px 20px", display: "grid", gap: 24 }}>
      <header><h1>안전 점수 프로필 관리</h1><p>적용은 현재 데이터로 새 산출물을 빌드합니다. 성공한 빌드만 활성화되며 실패하면 기존 산출물을 유지합니다.</p></header>
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
