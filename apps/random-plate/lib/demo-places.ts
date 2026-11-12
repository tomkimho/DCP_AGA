import { distanceMeters } from "./grid";
import type { Coords, Place } from "./types";

/**
 * KAKAO_REST_API_KEY가 없을 때 쓰는 데모 데이터.
 *
 * 실제 상호가 아니라 "흔한 업종 + 일반 명사" 조합으로 만든 가상의 가게다.
 * 실존 업소를 사칭하지 않기 위한 의도적 선택이며, UI에서 항상
 * "데모 데이터" 배지를 함께 노출한다.
 */
const DEMO: Array<[string, string]> = [
  ["소문난 순대국밥", "한식"],
  ["황금돼지 김치찌개", "한식"],
  ["할매 손칼국수", "한식"],
  ["돌솥비빔밥 정식", "한식"],
  ["장인 갈비탕", "한식"],
  ["청년 제육볶음", "한식"],
  ["가마솥 설렁탕", "한식"],
  ["도리도리 닭갈비", "한식"],
  ["미소 라멘", "일식"],
  ["스시 오마카세 런치", "일식"],
  ["텐동 하나로", "일식"],
  ["가츠동 공방", "일식"],
  ["사보리 우동", "일식"],
  ["불맛 짬뽕관", "중식"],
  ["사천 마라탕", "중식"],
  ["옛날 짜장", "중식"],
  ["딤섬 한접시", "중식"],
  ["멘보샤 하우스", "중식"],
  ["트러플 크림파스타", "양식"],
  ["화덕 마르게리타", "양식"],
  ["수제버거 공장", "양식"],
  ["리조또 다이닝", "양식"],
  ["스테이크 런치셋", "양식"],
  ["쌀국수 한그릇", "아시아음식"],
  ["팟타이 스트리트", "아시아음식"],
  ["나시고랭 하우스", "아시아음식"],
  ["커리 앤 난", "아시아음식"],
  ["포케 볼", "샐러드"],
  ["그린 샐러드바", "샐러드"],
  ["연어 포케 정식", "샐러드"],
  ["매콤 떡볶이 분식", "분식"],
  ["김밥 한줄", "분식"],
  ["튀김 우동 분식", "분식"],
  ["직화 제육 도시락", "도시락"],
  ["한상 백반집", "한식"],
  ["콩나물 국밥", "한식"],
  ["부대찌개 전문", "한식"],
  ["감자탕 큰솥", "한식"],
  ["오늘의 덮밥", "일식"],
  ["소바 한사발", "일식"],
  ["양꼬치 거리", "중식"],
  ["훠궈 한상", "중식"],
  ["빠네 파스타", "양식"],
  ["브런치 플레이트", "양식"],
  ["치킨 텐더 플래터", "치킨"],
];

/** 격자 한 칸의 크기(m). 이 간격으로 가게 자리가 잡힌다. */
const CELL_M = 130;
const LAT_CELL = CELL_M / 111_320;
/** 경도 칸 크기는 위도에 따라 변하지만, 기준 위도를 고정해야 격자가 전역에서 안정적이다 */
const LNG_CELL = CELL_M / (111_320 * Math.cos((37.5 * Math.PI) / 180));

/**
 * FNV 계열 정수 해시 — 같은 칸이면 항상 같은 값.
 *
 * salt로 서로 독립인 값을 두 개 뽑는다. 하나로 밀도와 이름을 동시에
 * 정하면 안 된다: 밀도가 h % 3, 이름이 h % 45(= 3 × 15)라면
 * 3의 배수인 h만 남으므로 45개 중 15개 이름만 영원히 뽑힌다.
 */
function cellHash(i: number, j: number, salt: number): number {
  let h = 2166136261 ^ salt ^ Math.imul(i, 374761393) ^ Math.imul(j, 668265263);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h = Math.imul(h ^ (h >>> 15), 2246822519);
  return (h ^ (h >>> 16)) >>> 0;
}

/**
 * 절대 좌표 격자 위에 데모 가게를 결정론적으로 배치한다.
 *
 * 중심 기준으로 생성하면 지도를 움직일 때 가게가 따라와서 지도처럼 보이지
 * 않는다. 칸마다 위치가 고정되어 있어야 내가 움직이고 가게는 그대로 있다.
 */
export function demoPlaces(center: Coords, radiusM: number): Place[] {
  const span = Math.ceil(radiusM / CELL_M) + 1;
  const ci = Math.round(center.lat / LAT_CELL);
  const cj = Math.round(center.lng / LNG_CELL);

  const found: Place[] = [];

  for (let di = -span; di <= span; di++) {
    for (let dj = -span; dj <= span; dj++) {
      const i = ci + di;
      const j = cj + dj;
      if (cellHash(i, j, 0) % 3 !== 0) continue; // 세 칸에 한 곳쯤

      const h = cellHash(i, j, 0x9e3779b9);
      // 격자 티가 나지 않게 칸 안에서 흔든다
      const jx = (((h >>> 8) % 100) / 100 - 0.5) * 0.7;
      const jy = (((h >>> 16) % 100) / 100 - 0.5) * 0.7;

      const lat = (i + jy) * LAT_CELL;
      const lng = (j + jx) * LNG_CELL;
      const distanceM = distanceMeters(center, { lat, lng });
      if (distanceM > radiusM) continue;

      const [name, category] = DEMO[h % DEMO.length];
      found.push({
        id: `demo-${i}-${j}`,
        name,
        category,
        roadAddress: null,
        // 실제 좌표 링크가 아니라 이름 검색 링크 — 데모임을 숨기지 않기 위함
        placeUrl: `https://map.kakao.com/link/search/${encodeURIComponent(name)}`,
        lat,
        lng,
        distanceM,
      });
    }
  }

  found.sort((a, b) => a.distanceM - b.distanceM);

  // 같은 이름이 여러 칸에 나올 수 있다. 룰렛에 같은 가게가 두 번 뜨면
  // 결과를 신뢰할 수 없으므로 가까운 쪽만 남긴다.
  const seen = new Set<string>();
  return found.filter((p) => {
    if (seen.has(p.name)) return false;
    seen.add(p.name);
    return true;
  });
}
