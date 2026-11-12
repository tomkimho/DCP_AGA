export type Place = {
  /** 공급자 고유 ID (kakao place id 또는 demo-*) */
  id: string;
  name: string;
  /** "음식점 > 한식 > 국밥" 중 말단 한 조각만 정규화해서 담는다 */
  category: string;
  roadAddress: string | null;
  placeUrl: string;
  lat: number;
  lng: number;
  /** 직선거리(m). 도보 실거리가 아니므로 UI에서 "약"으로 표기할 것 */
  distanceM: number;
};

export type PlacesResponse = {
  places: Place[];
  /** true면 카카오 키가 없어 데모 데이터를 반환한 것 */
  demo: boolean;
  /** 캐시 히트 여부 — §3.3 캐싱 설계 검증용 */
  cached: boolean;
};

export type Coords = { lat: number; lng: number };
