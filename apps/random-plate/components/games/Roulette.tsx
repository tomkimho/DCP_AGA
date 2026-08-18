"use client";

import { useEffect, useRef, useState } from "react";
import type { GameProps } from "@/lib/games";
import * as sound from "@/lib/sound";

const SECTORS = 8;
const ANGLE = 360 / SECTORS;
const DURATION_MS = 4600;

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
  const [cx, cy, r] = [160, 160, 150];
  const [x0, y0] = point(cx, cy, r, i * ANGLE - ANGLE / 2);
  const [x1, y1] = point(cx, cy, r, i * ANGLE + ANGLE / 2);
  return `M ${cx} ${cy} L ${x0} ${y0} A ${r} ${r} 0 0 1 ${x1} ${y1} Z`;
}

export default function Roulette({
  slots,
  onResult,
  onRunningChange,
}: GameProps) {
  const [rotation, setRotation] = useState(0);
  const [spinning, setSpinning] = useState(false);
  const target = useRef(0);
  const cancelTicks = useRef<() => void>(() => {});

  useEffect(() => () => cancelTicks.current(), []);

  const spin = () => {
    if (spinning || slots.length === 0) return;
    sound.unlock();
    sound.blip();

    const idx = Math.floor(Math.random() * Math.min(SECTORS, slots.length));
    target.current = idx;

    // 12시 포인터 아래로 idx 섹터를 데려오는 최소 회전량
    const targetMod = (((-idx * ANGLE) % 360) + 360) % 360;
    const currentMod = ((rotation % 360) + 360) % 360;
    let delta = targetMod - currentMod;
    if (delta < 0) delta += 360;

    // 섹터 정중앙에 딱 멈추면 기계적으로 보이므로 살짝 흔든다
    const jitter = (Math.random() - 0.5) * (ANGLE - 10);
    const total = 360 * 5 + delta + jitter;

    cancelTicks.current = sound.scheduleWheelTicks(total, DURATION_MS, ANGLE);
    setRotation((r) => r + total);
    setSpinning(true);
    onRunningChange(true);
  };

  const settle = () => {
    if (!spinning) return;
    cancelTicks.current();
    setSpinning(false);
    onRunningChange(false);
    onResult(target.current);
  };

  return (
    <div className="flex w-full flex-col items-center gap-6">
      <div className="relative mx-auto aspect-square w-full max-w-[min(84vw,320px)] select-none lg:max-w-[380px]">
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
          onTransitionEnd={settle}
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
                  상호명을 새기면 휠이 돌 때 글자가 뒤집히고 잘려서 읽히지 않는다.
                  섹터에는 번호만 두고 이름은 아래 목록에서 읽게 한다.
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

      <button
        onClick={spin}
        disabled={spinning}
        className="btn-primary w-full"
      >
        {spinning ? "돌리는 중…" : "🎡 돌리기"}
      </button>
    </div>
  );
}
