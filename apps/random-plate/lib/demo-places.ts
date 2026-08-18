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

/**
 * 중심좌표 주변에 데모 가게를 결정론적으로 배치한다.
 * 황금각(137.5°) 분산 + 인덱스 기반 반지름이라 같은 좌표면 항상 같은 결과가 나온다.
 */
export function demoPlaces(center: Coords, radiusM: number): Place[] {
  const out: Place[] = [];

  for (let i = 0; i < DEMO.length; i++) {
    const [name, category] = DEMO[i];
    const angle = (i * 137.508 * Math.PI) / 180;
    // 반지름을 sqrt로 분포시켜야 원 안에 고르게 퍼진다
    const r = radiusM * Math.sqrt(((i * 37) % 100) / 100) * 0.95 + 40;

    const dLat = (r * Math.cos(angle)) / 111_320;
    const dLng =
      (r * Math.sin(angle)) /
      (111_320 * Math.cos((center.lat * Math.PI) / 180) || 1);

    const lat = center.lat + dLat;
    const lng = center.lng + dLng;
    const distanceM = distanceMeters(center, { lat, lng });
    if (distanceM > radiusM) continue;

    out.push({
      id: `demo-${i}`,
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

  return out.sort((a, b) => a.distanceM - b.distanceM);
}
