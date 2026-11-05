"use client";

import { AppHeader } from "@/components/AppHeader";
import { InfoIcon } from "@/components/icons";
import { AssessmentExplanation } from "@/components/AssessmentExplanation";
import { userInitial, useSessionUser } from "@/lib/useSessionUser";
import styles from "../me/me.module.css";

// Regional inputs and facility collection dates are managed separately.
const SOURCES = [
  { item: "범죄 발생 건수", source: "경찰청 범죄 발생 지역별 통계 (공공데이터포털)", basis: "2024년", note: "시·군 단위 → 주민등록인구 1만 명당 범죄율" },
  { item: "주민등록인구", source: "행정안전부 주민등록 인구 및 세대현황", basis: "2024년 월평균", note: "범죄율의 분모" },
  { item: "CCTV (생활방범)", source: "전국CCTV표준데이터 (공공데이터포털)", basis: "2026년 9월 수집", note: "부천·광명·화성은 제출 자료가 거의 없어 제외" },
  { item: "보안등", source: "전국보안등정보표준데이터 OpenAPI", basis: "2026년 9월 수집", note: "" },
  { item: "안전비상벨", source: "전국안전비상벨위치표준데이터", basis: "2026년 9월 수집", note: "의정부·부천·광명·고양·오산·안성·화성·포천·여주·양평은 제출 자료가 거의 없어 제외" },
  { item: "교통사고 다발지역", source: "전국교통사고다발지역표준데이터", basis: "2022~2024년 사고", note: "최근 3년치만 사용" },
  { item: "상점·편의점", source: "소상공인시장진흥공단 상가(상권)정보", basis: "2026년 6월", note: "지역 통계의 상점 밀도에 사용. 길가(1층·지하1층) 음식·소매 상점만 셈. 영업시간 확인 근거는 별도" },
  { item: "야간 유동인구 (22~05시)", source: "경기데이터드림 유동인구_행정동 단위 집계 (KT 통신 데이터)", basis: "2026년 1~3월", note: "참여한 16개 시·군(367개 동)만 반영" },
  { item: "경찰서·지구대·파출소", source: "행정안전부 공통POI(경찰) (재난안전데이터 공유플랫폼)", basis: "2024년 3월 갱신분", note: "치안센터·안심부스는 제외" },
  { item: "주소 검색의 경기도 역 이름·위치", source: "OpenStreetMap", basis: "로컬 OSM 원본 추출", note: "초성 검색 후보에 사용" },
  { item: "행정동 경계", source: "통계청 SGIS 행정동 경계 (vuski/admdongkor 가공)", basis: "", note: "" },
];

// Verified from environment_sources.json collection receipts, 2026-11-04.
const FACILITY_SOURCES = [
  { item: "생활방범 CCTV", url: "https://www.data.go.kr/data/15013094/standard.do", source: "전국CCTV표준데이터 · LOCALDATA", basis: "기관별 기준일 2020-01-01~2026-06-01", note: "생활방범 목적만 사용. 지역별 좌표·조사 범위 확인 상태가 다릅니다." },
  { item: "안전비상벨", url: "https://www.data.go.kr/data/15028206/standard.do", source: "전국안전비상벨위치표준데이터 · LOCALDATA", basis: "기관별 기준일 2022-06-10~2026-06-30", note: "공식 고장 점검 코드는 접근성에서 제외합니다. 실시간 작동 확인 자료는 아닙니다." },
  { item: "보안등", url: "https://www.data.go.kr/data/15017320/standard.do", source: "전국보안등정보표준데이터 · 기관별 OpenAPI", basis: "기관별 기준일 2022-12-20~2026-10-27", note: "기관별 전체 페이지·좌표 누락을 검증하며 미확인 지역은 부재로 처리하지 않습니다." },
  { item: "매장 공개 영업시간", url: "https://m.emart24.co.kr/store", source: "이마트24 매장 찾기", basis: "2026-11-04 취득 · 일부 매장만 포함", note: "공개 시간표와 좌표를 연결합니다. 요일별 시간표 검증 여부를 구분하며 전체 편의점이 24시간 영업한다고 추정하지 않습니다." },
];

export default function DataSourcesPage() {
  const user = useSessionUser();
  if (!user) return null;

  return (
    <main className={styles.page}>
      <AppHeader userInitial={userInitial(user)} />
      <div className={styles.shell}>
        <section className={styles.infoCard}>
          <h1 className={styles.infoTitle}>
            <InfoIcon size={16} />
            데이터 출처와 기준
          </h1>
          <p className={styles.infoText}>
            지역 통계 지수와 보행 시설 접근성은 서로 다른 평가입니다. 새 시설 자료의 수집일이 기존 지역 통계의 갱신일을 뜻하지 않습니다. 시설 평가는 실제 사용한 출처 버전·평가 시각을 별도로 기록합니다.
          </p>
          <details><summary>계산 방식·시간대·알림 기준 상세</summary><AssessmentExplanation textClassName={styles.infoText} /></details>
        </section>

        <section className={styles.card}>
          <h2 className={styles.cardTitle}>보행 시설 자료 · 2026-11-04 수집 확인</h2>
          <p className={styles.infoText}>아래 날짜 범위는 현재 입력 명세에 기록된 기관별 원자료 기준일입니다. 수집일·기준일·평가 시각은 다릅니다. 경기도 기관별 공개 목록을 검증했으며 현실의 모든 시설을 전수조사했다는 의미는 아닙니다. 좌표가 일부 누락되면 확인된 시설의 존재만 사용하고 미관측 구간은 미상으로 둡니다. 이전 출처 미확인 좌표는 점수 근거로 사용하지 않습니다.</p>
          {FACILITY_SOURCES.map(({ item, url, source, basis, note }) => <details key={item}>
            <summary>{item} · {basis}</summary><p className={styles.infoText}><a href={url} target="_blank" rel="noreferrer">{source}</a> · {note}</p>
          </details>)}
          <p className={styles.infoText}>주변·동별 평가는 경기도 OSM 보행망에서 확보한 길을 기준으로 합니다(로컬 원본 2026년 9월). 현실의 모든 골목을 포함하지 않으며, 길이 없거나 경계를 연결하지 못한 경우 미상으로 표시합니다. 도로망·시설·행정동 경계 버전은 산출물별로 관리합니다.</p>
        </section>

        <section className={styles.card}>
          <h2 className={styles.cardTitle}>지역 통계 지수의 기존 자료</h2>
          <p className={styles.infoText}>아래 기존 기준일과 제출량 판정은 지역 통계에만 해당하며 위 시설 평가의 적용 지역을 뜻하지 않습니다. 미상 요인은 제외하고 남은 가중치를 재조정합니다. 모든 요인이 미상이면 프로필의 기본 중립값을 사용합니다.</p>
        </section>

        {SOURCES.map(({ item, source, basis, note }) => (
          <section key={item} className={styles.card}>
            <h2 className={styles.cardTitle}>{item}</h2>
            <p className={styles.infoText}>
              {source}
              {basis && <> · <strong>{basis}</strong></>}
            </p>
            {note && <p className={styles.infoText}>{note}</p>}
          </section>
        ))}

        <section className={styles.card}>
          <h2 className={styles.cardTitle}>별도 보존 원자료</h2>
          <p className={styles.infoText}>유흥주점·단란주점(지방행정 인허가, 2026년 10월 수집)과 공원·하천(OSM, 2026년 9월)은 원자료를 보존하며 새 시설 점수에는 사용하지 않습니다. 경찰 시설 위치는 지역 통계·도움 거점에 사용하며 새 시설 점수에는 합산하지 않습니다.</p>
        </section>

        <section className={styles.card}>
          <h2 className={styles.cardTitle}>저작권 표시</h2>
          <p className={styles.infoText}>
            경기데이터드림 유동인구 데이터: 공공누리 제2유형(출처표시, 상업적 이용금지). 지도 도로망·시설: © OpenStreetMap
            contributors (ODbL). 행정동 경계: 통계청 SGIS, vuski/admdongkor 가공 (CC BY 4.0).
          </p>
          <p className={styles.infoText}>이 점수와 추천 경로는 참고 정보이며, 실제 안전을 보장하지 않아요.</p>
        </section>
      </div>
    </main>
  );
}
