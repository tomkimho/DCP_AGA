"use client";

import { useEffect, useRef } from "react";

const COLORS = ["#ff6b6b", "#ffd43b", "#69db7c", "#4dabf7", "#9775fa", "#f783ac"];

type Bit = {
  x: number;
  y: number;
  vx: number;
  vy: number;
  rot: number;
  vr: number;
  w: number;
  h: number;
  color: string;
};

/** 라이브러리 없이 쓰는 축하 효과. 2초 남짓 뿌리고 스스로 멈춘다. */
export default function Confetti({ fire }: { fire: number }) {
  const ref = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    if (!fire) return;
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = (canvas.width = canvas.offsetWidth * dpr);
    const h = (canvas.height = canvas.offsetHeight * dpr);

    const bits: Bit[] = Array.from({ length: 110 }, () => ({
      x: w / 2 + (Math.random() - 0.5) * w * 0.5,
      y: h * 0.34 + (Math.random() - 0.5) * 40,
      vx: (Math.random() - 0.5) * 11 * dpr,
      vy: (Math.random() * -12 - 4) * dpr,
      rot: Math.random() * Math.PI,
      vr: (Math.random() - 0.5) * 0.32,
      w: (5 + Math.random() * 6) * dpr,
      h: (8 + Math.random() * 8) * dpr,
      color: COLORS[(Math.random() * COLORS.length) | 0],
    }));

    let raf = 0;
    const started = performance.now();

    const tick = (now: number) => {
      const elapsed = now - started;
      ctx.clearRect(0, 0, w, h);

      for (const b of bits) {
        b.vy += 0.42 * dpr;
        b.vx *= 0.995;
        b.x += b.vx;
        b.y += b.vy;
        b.rot += b.vr;

        ctx.save();
        ctx.translate(b.x, b.y);
        ctx.rotate(b.rot);
        ctx.globalAlpha = Math.max(0, 1 - elapsed / 2400);
        ctx.fillStyle = b.color;
        ctx.fillRect(-b.w / 2, -b.h / 2, b.w, b.h);
        ctx.restore();
      }

      if (elapsed < 2400) raf = requestAnimationFrame(tick);
      else ctx.clearRect(0, 0, w, h);
    };

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [fire]);

  return (
    <canvas
      ref={ref}
      className="pointer-events-none fixed inset-0 z-50 h-full w-full"
      aria-hidden
    />
  );
}
