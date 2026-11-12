"use client";

import { useCallback, useEffect, useRef } from "react";
import { COLORS } from "@/lib/games";
import { distanceMeters } from "@/lib/grid";
import type { Coords } from "@/lib/types";
import type { MapViewProps } from "./types";

/**
 * 구글 지도 키가 없을 때 쓰는 폴백 지도.
 *
 * 타일이 없으므로 도로나 건물은 없지만, 실제 위경도를 그대로 투영하므로
 * 거리와 방위는 정확하다. 격자와 축척 막대로 축척 감각을 준다.
 */
export default function MapCanvas({
  center,
  radiusM,
  places,
  slots = [],
  winner = null,
  userAt = null,
  interactive = false,
  onCenterChange,
  className,
}: MapViewProps) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  const drag = useRef<{ active: boolean; last: [number, number] } | null>(null);

  const metersPerPx = useCallback(
    (w: number, h: number) => (radiusM * 1.22) / (Math.min(w, h) / 2),
    [radiusM]
  );

  const draw = useCallback(() => {
    const cv = ref.current;
    if (!cv) return;
    const w = cv.offsetWidth;
    const h = cv.offsetHeight;
    if (!w || !h) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = w * dpr;
    cv.height = h * dpr;
    const g = cv.getContext("2d");
    if (!g) return;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);

    const m = metersPerPx(w, h);
    const cos = Math.cos((center.lat * Math.PI) / 180) || 1;
    const project = (p: Coords): [number, number] => [
      w / 2 + ((p.lng - center.lng) * 111_320 * cos) / m,
      h / 2 - ((p.lat - center.lat) * 111_320) / m,
    ];

    g.fillStyle = "#0a0710";
    g.fillRect(0, 0, w, h);

    // 200m 격자
    const step = 200 / m;
    g.strokeStyle = "rgba(158,147,184,.09)";
    g.lineWidth = 1;
    g.beginPath();
    for (let x = (w / 2) % step; x < w; x += step) {
      g.moveTo(x, 0);
      g.lineTo(x, h);
    }
    for (let y = (h / 2) % step; y < h; y += step) {
      g.moveTo(0, y);
      g.lineTo(w, y);
    }
    g.stroke();

    // 거리 링
    g.strokeStyle = "rgba(158,147,184,.16)";
    for (let r = 200; r < radiusM; r += 200) {
      g.beginPath();
      g.arc(w / 2, h / 2, r / m, 0, Math.PI * 2);
      g.stroke();
    }

    // 반경
    const rp = radiusM / m;
    g.fillStyle = "rgba(255,176,32,.055)";
    g.beginPath();
    g.arc(w / 2, h / 2, rp, 0, Math.PI * 2);
    g.fill();
    g.strokeStyle = "rgba(255,176,32,.65)";
    g.lineWidth = 1.5;
    g.setLineDash([5, 5]);
    g.beginPath();
    g.arc(w / 2, h / 2, rp, 0, Math.PI * 2);
    g.stroke();
    g.setLineDash([]);

    g.font = "700 10px system-ui, sans-serif";
    g.fillStyle = "rgba(255,176,32,.8)";
    g.textAlign = "center";
    g.fillText(`${radiusM}m`, w / 2, h / 2 - rp - 6);

    // 주변 가게
    const slotIds = new Set(slots.map((s) => s.id));
    for (const p of places) {
      if (slotIds.has(p.id)) continue;
      const [x, y] = project(p);
      if (x < -20 || x > w + 20 || y < -20 || y > h + 20) continue;
      const inside = p.distanceM <= radiusM;
      g.beginPath();
      g.arc(x, y, inside ? 3.2 : 2.2, 0, Math.PI * 2);
      g.fillStyle = inside ? "rgba(242,236,255,.6)" : "rgba(158,147,184,.26)";
      g.fill();
    }

    // 이번 판 후보
    g.textBaseline = "middle";
    slots.forEach((p, i) => {
      const [x, y] = project(p);
      const win = winner?.id === p.id;
      const r = win ? 12 : 9;
      g.beginPath();
      g.arc(x, y, r + 3, 0, Math.PI * 2);
      g.fillStyle = "rgba(10,7,16,.85)";
      g.fill();
      g.beginPath();
      g.arc(x, y, r, 0, Math.PI * 2);
      g.fillStyle = win ? "#ffb020" : COLORS[i % COLORS.length];
      g.fill();
      g.fillStyle = "#191322";
      g.font = `900 ${win ? 13 : 10}px system-ui, sans-serif`;
      g.textAlign = "center";
      g.fillText(String(i + 1), x, y + 0.5);
    });
    g.textBaseline = "alphabetic";

    // 내 위치
    if (userAt) {
      const [ux, uy] = project(userAt);
      g.beginPath();
      g.arc(ux, uy, 13, 0, Math.PI * 2);
      g.fillStyle = "rgba(61,220,151,.18)";
      g.fill();
      g.beginPath();
      g.arc(ux, uy, 5, 0, Math.PI * 2);
      g.fillStyle = "#3ddc97";
      g.fill();
      g.lineWidth = 2;
      g.strokeStyle = "#0a0710";
      g.stroke();
    }

    // 중심 십자선
    g.strokeStyle = "rgba(242,236,255,.55)";
    g.lineWidth = 1.5;
    g.beginPath();
    g.moveTo(w / 2 - 8, h / 2);
    g.lineTo(w / 2 - 3, h / 2);
    g.moveTo(w / 2 + 3, h / 2);
    g.lineTo(w / 2 + 8, h / 2);
    g.moveTo(w / 2, h / 2 - 8);
    g.lineTo(w / 2, h / 2 - 3);
    g.moveTo(w / 2, h / 2 + 3);
    g.lineTo(w / 2, h / 2 + 8);
    g.stroke();

    // 축척
    const barPx = 200 / m;
    if (barPx < w * 0.6) {
      const bx = 12;
      const by = h - 14;
      g.strokeStyle = "rgba(242,236,255,.5)";
      g.lineWidth = 2;
      g.beginPath();
      g.moveTo(bx, by);
      g.lineTo(bx + barPx, by);
      g.moveTo(bx, by - 4);
      g.lineTo(bx, by + 4);
      g.moveTo(bx + barPx, by - 4);
      g.lineTo(bx + barPx, by + 4);
      g.stroke();
      g.fillStyle = "rgba(242,236,255,.6)";
      g.font = "700 10px system-ui, sans-serif";
      g.textAlign = "left";
      g.fillText("200m", bx, by - 8);
    }

    g.fillStyle = "rgba(158,147,184,.55)";
    g.font = "800 11px system-ui, sans-serif";
    g.textAlign = "right";
    g.fillText("N ↑", w - 12, 20);
  }, [center, radiusM, places, slots, winner, userAt, metersPerPx]);

  useEffect(() => {
    draw();
  }, [draw]);

  useEffect(() => {
    const onResize = () => draw();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [draw]);

  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!interactive || !onCenterChange) return;
    drag.current = { active: true, last: [e.clientX, e.clientY] };
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drag.current?.active || !onCenterChange) return;
    const cv = e.currentTarget;
    const m = metersPerPx(cv.offsetWidth, cv.offsetHeight);
    const [lx, ly] = drag.current.last;
    const dx = e.clientX - lx;
    const dy = e.clientY - ly;
    drag.current.last = [e.clientX, e.clientY];

    const cos = Math.cos((center.lat * Math.PI) / 180) || 1;
    let lat = center.lat + (dy * m) / 111_320;
    let lng = center.lng - (dx * m) / (111_320 * cos);

    // 내 위치에서 너무 멀어지면 "근처 점심"이 아니게 된다
    if (userAt) {
      const d = distanceMeters(userAt, { lat, lng });
      if (d > 1500) {
        const t = 1500 / d;
        lat = userAt.lat + (lat - userAt.lat) * t;
        lng = userAt.lng + (lng - userAt.lng) * t;
      }
    }
    onCenterChange({ lat, lng });
  };

  const endDrag = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drag.current) return;
    drag.current.active = false;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* 이미 해제된 경우 — 무시 */
    }
  };

  return (
    <canvas
      ref={ref}
      className={className}
      style={{
        touchAction: interactive ? "none" : undefined,
        cursor: interactive ? "grab" : undefined,
      }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      aria-hidden
    />
  );
}
