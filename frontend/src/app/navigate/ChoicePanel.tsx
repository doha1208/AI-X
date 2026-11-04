"use client";

import type { Place } from "@/lib/place";
import { environmentAssessmentNote, formatDistance, walkingMinutes, type GuideKind, type GuideOption } from "@/lib/routeGuidance";
import { RouteEnvironmentDetails, RouteEnvironmentSummary } from "@/components/RouteEnvironmentSummary";
import type { RoutePeriod } from "@/lib/api";
import type { LatLng } from "@/lib/kakao";
import styles from "./navigate.module.css";

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

// 비교용 일반 경로는 별도 선택 카드로 만들지 않는다.
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
            {choice.options.filter((option) => option.kind !== "shortest").map((option) => {
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
                      <RouteEnvironmentSummary assessment={option.environmentAssessment} />
                    </span>
                    {!selected && <span className={styles.choiceHint}>눌러서 지도에서 보기</span>}
                  </button>
                  {selected && (
                    <RouteEnvironmentDetails assessment={option.environmentAssessment} />
                  )}
                  {selected && (
                    <button type="button" className={styles.choiceStart} onClick={() => onChoose(option)}>
                      이 길로 안내 시작
                    </button>
                  )}
                </div>
              );
            })}
          </div>
          {!choice.safetyWeighted && (
            <p className={styles.choiceNote}>{environmentAssessmentNote(safeOption?.environmentAssessment)}</p>
          )}
        </>
      )}
    </div>
  );
}
