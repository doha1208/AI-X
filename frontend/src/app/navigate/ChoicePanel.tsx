"use client";

import type { Place } from "@/lib/place";
import { formatDistance, walkingMinutes, zoneSummary, type GuideKind, type GuideOption } from "@/lib/routeGuidance";
import type { RoutePeriod } from "@/lib/api";
import type { LatLng } from "@/lib/kakao";
import styles from "./navigate.module.css";

function scoreTone(score: number): string {
  if (score >= 70) return styles.toneSafe;
  if (score >= 40) return styles.toneCaution;
  return styles.toneWarning;
}

export type Choice = { options: GuideOption[]; safetyWeighted: boolean; period: RoutePeriod };

// 경로 이름. 비교 경로는 Tmap 도보 길찾기 결과라 안전 경로보다 길 때도 있다 — 실제로 짧을 때만 "최단"이라 부른다.
export function choiceTitle(option: GuideOption, choice: Choice, safeOption: GuideOption | undefined): string {
  if (option.kind === "safe") return choice.safetyWeighted ? "데이터 기반 추천 경로" : "도보 경로";
  const reallyShortest = !safeOption || option.distanceM < safeOption.distanceM;
  return reallyShortest ? "최단 경로" : "일반 도보 경로";
}

type Props = {
  destination: Place | null;
  choice: Choice | null;
  safeOption: GuideOption | undefined;
  previewOption: GuideOption | undefined;
  myLocation: LatLng | undefined;
  routeError: string | null;
  onPreview: (kind: GuideKind) => void;
  onChoose: (option: GuideOption) => void;
  onRetry: () => void;
  onCancel: () => void;
};

// 길안내에서 목적지를 정한 뒤 "안전 경로 vs 최단 경로"를 비교해 고르는 화면.
export function ChoicePanel({
  destination,
  choice,
  safeOption,
  previewOption,
  myLocation,
  routeError,
  onPreview,
  onChoose,
  onRetry,
  onCancel,
}: Props) {
  return (
    <div className={styles.choicePanelContent}>
      <div className={styles.choiceHeader}>
        <div>
          <h1 className={styles.choiceTitle}>
            어떤 길로 안내할까요?
            {choice && (
              <span className={`${styles.periodBadge} ${choice.period === "night" ? styles.periodNight : ""}`}>
                {choice.period === "night" ? "야간 기준" : "주간 기준"}
              </span>
            )}
          </h1>
          <p className={styles.choiceSub}>목적지 · {destination?.label}</p>
        </div>
        <button type="button" className={styles.ghostButton} onClick={onCancel}>
          취소
        </button>
      </div>

      {routeError ? (
        <div className={styles.choiceStatus} role="alert">
          <p className={styles.error}>경로를 찾지 못했어요: {routeError}</p>
          <button type="button" className={styles.startButton} onClick={onRetry}>
            다시 시도
          </button>
        </div>
      ) : !choice ? (
        <p className={styles.choiceStatus} role="status">
          {myLocation ? "데이터 기반 추천 경로와 최단 경로를 비교하는 중..." : "현재 위치를 찾는 중..."}
        </p>
      ) : (
        <>
          <div className={styles.choiceList}>
            {choice.options.map((option) => {
              const summary = zoneSummary(option.zones);
              const isSafe = option.kind === "safe";
              const title = choiceTitle(option, choice, safeOption);
              const selected = option === previewOption;
              return (
                <div key={option.kind} className={`${styles.choiceCard} ${selected ? styles.choiceCardSelected : ""}`}>
                  <button
                    type="button"
                    className={styles.choiceSelect}
                    onClick={() => onPreview(option.kind)}
                    aria-pressed={selected}
                  >
                    <span className={styles.choiceKind}>
                      <span className={selected ? styles.swatchLine : styles.swatchDash} aria-hidden />
                      {title}
                      {isSafe && choice.safetyWeighted && <span className={styles.recommendTag}>추천</span>}
                    </span>
                    <span className={styles.choiceTime}>
                      {walkingMinutes(option.distanceM)}분 <small>{formatDistance(option.distanceM)}</small>
                    </span>
                    <span className={styles.choiceMeta}>
                      {summary.average !== null && (
                        <span className={scoreTone(summary.average)}>지나는 동 평균 {summary.average.toFixed(0)}점</span>
                      )}
                      <span>{summary.cautionCount > 0 ? `주의 구역 ${summary.cautionCount}곳` : "주의 구역 없음"}</span>
                    </span>
                    {!selected && <span className={styles.choiceHint}>눌러서 지도에서 보기</span>}
                  </button>
                  {selected && (
                    <button type="button" className={styles.choiceStart} onClick={() => onChoose(option)}>
                      이 길로 안내 시작
                    </button>
                  )}
                </div>
              );
            })}
          </div>
          {!choice.safetyWeighted ? (
            <p className={styles.choiceNote}>데이터 기반 추천 경로를 찾지 못해 일반 도보 경로로만 안내할 수 있어요.</p>
          ) : (
            choice.options.length === 1 && (
              <p className={styles.choiceNote}>최단 경로를 가져오지 못해 데이터 기반 추천 경로로만 안내할 수 있어요.</p>
            )
          )}
          <p className={styles.choiceNote}>공개 데이터 기반 참고 정보이며, 실제 안전을 보장하지 않아요.</p>
        </>
      )}
    </div>
  );
}
