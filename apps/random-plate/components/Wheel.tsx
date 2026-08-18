"use client";

import { useEffect, useRef, useState } from "react";
import type { Place } from "@/lib/types";

export const SECTORS = 8;
const ANGLE = 360 / SECTORS;

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

/** 12시 방향을 0도로 두고 시계방향으로 도는 좌표계 */
function point(cx: number, cy: number, r: number, clockDeg: number) {
  const rad = ((clockDeg - 90) * Math.PI) / 180;
  return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)] as const;
}

function sectorPath(i: number) {
  const cx = 160;
  const cy = 160;
  const r = 150;
  const start = i * ANGLE - ANGLE / 2;
  const end = i * ANGLE + ANGLE / 2;
  const [x0, y0] = point(cx, cy, r, start);
  const [x1, y1] = point(cx, cy, r, end);
  return `M ${cx} ${cy} L ${x0} ${y0} A ${r} ${r} 0 0 1 ${x1} ${y1} Z`;
}

type Props = {
  /** 섹터 개수 검증용 — 라벨은 휠 밖 목록에서 렌더한다 */
  slots: Place[];
  spinning: boolean;
  /** 당첨시킬 슬롯 인덱스. spinning이 true로 바뀔 때 읽는다. */
  targetIndex: number;
  onSettled: () => void;
};

export default function Wheel({
  slots,
  spinning,
  targetIndex,
  onSettled,
}: Props) {
  const [rotation, setRotation] = useState(0);
  const wasSpinning = useRef(false);

  useEffect(() => {
    if (!spinning || wasSpinning.current) {
      wasSpinning.current = spinning;
      return;
    }
    wasSpinning.current = true;

    // 12시 포인터 아래로 targetIndex 섹터를 데려오는 최소 회전량
    const targetMod = (((-targetIndex * ANGLE) % 360) + 360) % 360;
    const currentMod = ((rotation % 360) + 360) % 360;
    let delta = targetMod - currentMod;
    if (delta < 0) delta += 360;

    // 섹터 정중앙에 딱 멈추면 기계적으로 보이므로 살짝 흔든다
    const jitter = (Math.random() - 0.5) * (ANGLE - 10);

    setRotation(rotation + 360 * 5 + delta + jitter);
  }, [spinning, targetIndex, rotation]);

  return (
    <div className="relative mx-auto w-full max-w-[320px] aspect-square select-none">
      {/* 12시 포인터 */}
      <div className="absolute left-1/2 -top-1 z-10 -translate-x-1/2">
        <div
          className="h-0 w-0 drop-shadow-lg"
          style={{
            borderLeft: "13px solid transparent",
            borderRight: "13px solid transparent",
            borderTop: "26px solid #fff",
          }}
        />
      </div>

      <svg
        viewBox="0 0 320 320"
        className="wheel-spin h-full w-full"
        style={{ transform: `rotate(${rotation}deg)` }}
        onTransitionEnd={onSettled}
        aria-hidden
      >
        {Array.from({ length: SECTORS }).map((_, i) => {
          const [tx, ty] = point(160, 160, 104, i * ANGLE);
          return (
            <g key={i}>
              <path
                d={sectorPath(i)}
                fill={COLORS[i % COLORS.length]}
                stroke="rgba(0,0,0,0.28)"
                strokeWidth={2}
              />
              {/*
                상호명을 새기면 휠이 돌 때 글자가 뒤집히고, 7자로 잘려 읽히지도
                않는다. 섹터에는 번호만 두고 이름은 아래 목록에서 읽게 한다.
              */}
              <text
                x={tx}
                y={ty}
                textAnchor="middle"
                dominantBaseline="central"
                fill="#191322"
                fontSize={26}
                fontWeight={900}
              >
                {i + 1}
              </text>
            </g>
          );
        })}
        <circle cx={160} cy={160} r={30} fill="#0b0b12" />
        <circle
          cx={160}
          cy={160}
          r={30}
          fill="none"
          stroke="rgba(255,255,255,0.25)"
          strokeWidth={2}
        />
      </svg>
    </div>
  );
}
