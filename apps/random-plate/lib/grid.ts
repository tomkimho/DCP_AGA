import type { Coords } from "./types";

/**
 * 기획서 §3.3 캐싱 설계 + §9 개인정보 최소화의 구현.
 *
 * 좌표를 소수점 3자리(약 110m) 격자로 반올림한다. 이 값이
 *   1) place_cache 키가 되어 API 호출을 격자 단위로 묶고
 *   2) 서버에 남는 유일한 위치 표현이 되어 정밀 위치를 저장하지 않게 한다.
 */
export function snapToGrid({ lat, lng }: Coords): Coords {
  return {
    lat: Math.round(lat * 1000) / 1000,
    lng: Math.round(lng * 1000) / 1000,
  };
}

export function cacheKey(c: Coords, radiusM: number): string {
  const g = snapToGrid(c);
  return `${g.lat.toFixed(3)},${g.lng.toFixed(3)}:${radiusM}`;
}

const R = 6371000;

/** 하버사인 직선거리(m). 도보 실거리가 아님. */
export function distanceMeters(a: Coords, b: Coords): number {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return Math.round(2 * R * Math.asin(Math.sqrt(h)));
}

/** 직선거리를 도보 시간으로 환산(성인 보행 약 67m/분 + 신호 대기 여유) */
export function walkMinutes(distanceM: number): number {
  return Math.max(1, Math.round(distanceM / 67));
}
