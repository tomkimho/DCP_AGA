import type { Place } from "./types";

/** 후보 번호 색 — 룰렛 섹터, 목록 배지, 지도 핀이 전부 이 색을 공유한다 */
export const COLORS = [
  "#ff6b6b",
  "#ffa94d",
  "#ffd43b",
  "#69db7c",
  "#38d9a9",
  "#4dabf7",
  "#9775fa",
  "#f783ac",
];

export type GameId = "roulette" | "slot" | "revolver" | "cards";

export type GameDef = {
  id: GameId;
  name: string;
  emoji: string;
  /** 이 게임이 한 판에 올리는 후보 수 */
  slots: number;
  hint: string;
};

export const GAMES: GameDef[] = [
  {
    id: "roulette",
    name: "룰렛",
    emoji: "🎡",
    slots: 8,
    hint: "돌리고 멈출 때까지 기다리기",
  },
  {
    id: "slot",
    name: "슬롯머신",
    emoji: "🎰",
    slots: 8,
    hint: "릴 3개가 차례로 멈춥니다",
  },
  {
    id: "revolver",
    name: "러시안 룰렛",
    emoji: "🔫",
    slots: 6,
    hint: "실린더를 돌리고 방아쇠를",
  },
  {
    id: "cards",
    name: "카드 뽑기",
    emoji: "🃏",
    slots: 5,
    hint: "직접 한 장을 고릅니다",
  },
];

export function gameById(id: GameId): GameDef {
  return GAMES.find((g) => g.id === id) ?? GAMES[0];
}

export type GameProps = {
  slots: Place[];
  /** 게임이 결과를 확정했을 때 슬롯 인덱스를 넘긴다 */
  onResult: (index: number) => void;
  /** 진행 중에는 부모가 리롤/게임변경 버튼을 잠근다 */
  onRunningChange: (running: boolean) => void;
};
