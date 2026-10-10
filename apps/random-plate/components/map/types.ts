import type { Coords, Place } from "@/lib/types";

export type MapViewProps = {
  center: Coords;
  radiusM: number;
  /** 반경 안팎의 주변 가게 — 흐린 점으로 깔린다 */
  places: Place[];
  /** 이번 판 후보 — 번호가 붙은 색 핀 */
  slots?: Place[];
  winner?: Place | null;
  /** GPS로 잡은 실제 내 위치. 지도를 끌어 중심을 옮겨도 이 점은 그대로 있다 */
  userAt?: Coords | null;
  /** false면 보기 전용(사이드바 미니맵) */
  interactive?: boolean;
  onCenterChange?: (c: Coords) => void;
  className?: string;
};
