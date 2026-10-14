"use client";

import { useEffect, useRef, useState } from "react";
import { COLORS } from "@/lib/games";
import type { MapViewProps } from "./types";

/* eslint-disable @typescript-eslint/no-explicit-any */

declare global {
  interface Window {
    google?: any;
    gm_authFailure?: () => void;
    __rpMapsReady?: () => void;
  }
}

let loader: Promise<void> | null = null;

/** Maps JS API는 한 번만 붙인다. 두 번 붙이면 콘솔 경고와 함께 상태가 꼬인다. */
function loadMaps(key: string): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("no window"));
  if (window.google?.maps) return Promise.resolve();
  if (loader) return loader;

  loader = new Promise<void>((resolve, reject) => {
    window.__rpMapsReady = () => resolve();
    const s = document.createElement("script");
    s.async = true;
    s.src =
      "https://maps.googleapis.com/maps/api/js" +
      `?key=${encodeURIComponent(key)}` +
      "&language=ko&region=KR&loading=async&callback=__rpMapsReady";
    s.onerror = () => reject(new Error("Google Maps 스크립트를 불러오지 못했습니다"));
    document.head.appendChild(s);
  });
  return loader;
}

/** 앱 전체가 어두운 톤이라 기본 밝은 지도를 그대로 쓰면 화면이 두 개로 갈린다 */
const DARK_STYLE = [
  { elementType: "geometry", stylers: [{ color: "#16121f" }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#9e93b8" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: "#0e0b14" }] },
  { featureType: "poi", elementType: "labels.icon", stylers: [{ visibility: "off" }] },
  { featureType: "poi.park", elementType: "geometry", stylers: [{ color: "#16261e" }] },
  { featureType: "road", elementType: "geometry", stylers: [{ color: "#241d33" }] },
  { featureType: "road.arterial", elementType: "geometry", stylers: [{ color: "#2c2340" }] },
  { featureType: "road.highway", elementType: "geometry", stylers: [{ color: "#3a2f52" }] },
  { featureType: "transit", elementType: "geometry", stylers: [{ color: "#1e1730" }] },
  { featureType: "water", elementType: "geometry", stylers: [{ color: "#0d1626" }] },
];

type Props = MapViewProps & {
  apiKey: string;
  /** 키가 거부되거나 스크립트가 죽으면 부모가 캔버스 지도로 되돌린다 */
  onUnavailable: (reason: string) => void;
};

export default function GoogleMapView({
  apiKey,
  center,
  radiusM,
  places,
  slots = [],
  winner = null,
  userAt = null,
  interactive = false,
  onCenterChange,
  onUnavailable,
  className,
}: Props) {
  const host = useRef<HTMLDivElement | null>(null);
  const map = useRef<any>(null);
  const circle = useRef<any>(null);
  const markers = useRef<any[]>([]);
  const userDot = useRef<any>(null);
  const [ready, setReady] = useState(false);

  // 콜백을 ref로 잡아두지 않으면 부모 리렌더마다 지도 리스너를 다시 달게 된다
  const centerCb = useRef(onCenterChange);
  centerCb.current = onCenterChange;
  const unavailableCb = useRef(onUnavailable);
  unavailableCb.current = onUnavailable;

  // 1) 지도 생성 — 한 번만
  useEffect(() => {
    let dead = false;

    window.gm_authFailure = () =>
      unavailableCb.current(
        "구글 지도 키가 거부됐습니다. 키 제한(허용 도메인)과 결제 계정을 확인해 주세요."
      );

    loadMaps(apiKey)
      .then(() => {
        if (dead || !host.current || map.current) return;
        map.current = new window.google.maps.Map(host.current, {
          center: { lat: center.lat, lng: center.lng },
          zoom: 16,
          disableDefaultUI: true,
          gestureHandling: interactive ? "greedy" : "none",
          keyboardShortcuts: false,
          clickableIcons: false,
          styles: DARK_STYLE,
        });

        if (interactive) {
          map.current.addListener("idle", () => {
            const c = map.current.getCenter();
            if (!c) return;
            centerCb.current?.({ lat: c.lat(), lng: c.lng() });
          });
        }
        setReady(true);
      })
      .catch((e: Error) => {
        if (!dead) unavailableCb.current(e.message);
      });

    return () => {
      dead = true;
    };
    // apiKey/interactive가 바뀌는 경우는 없다. 중심은 아래 이펙트에서 따라간다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiKey]);

  // 2) 반경에 맞춰 줌을 맞춘다
  useEffect(() => {
    if (!ready || !map.current) return;
    const g = window.google.maps;
    if (!circle.current) {
      circle.current = new g.Circle({
        map: map.current,
        strokeColor: "#ffb020",
        strokeOpacity: 0.75,
        strokeWeight: 1.5,
        fillColor: "#ffb020",
        fillOpacity: 0.06,
      });
    }
    circle.current.setCenter({ lat: center.lat, lng: center.lng });
    circle.current.setRadius(radiusM);
    map.current.fitBounds(circle.current.getBounds(), 24);
  }, [ready, radiusM, center.lat, center.lng]);

  // 3) 핀 갱신
  useEffect(() => {
    if (!ready || !map.current) return;
    const g = window.google.maps;

    markers.current.forEach((m) => m.setMap(null));
    markers.current = [];

    const slotIds = new Set(slots.map((s) => s.id));

    for (const p of places) {
      if (slotIds.has(p.id)) continue;
      markers.current.push(
        new g.Marker({
          map: map.current,
          position: { lat: p.lat, lng: p.lng },
          title: p.name,
          icon: {
            path: g.SymbolPath.CIRCLE,
            scale: 3.2,
            fillColor: "#f2ecff",
            fillOpacity: 0.55,
            strokeWeight: 0,
          },
        })
      );
    }

    slots.forEach((p, i) => {
      const win = winner?.id === p.id;
      markers.current.push(
        new g.Marker({
          map: map.current,
          position: { lat: p.lat, lng: p.lng },
          title: p.name,
          zIndex: win ? 999 : 100 + i,
          icon: {
            path: g.SymbolPath.CIRCLE,
            scale: win ? 13 : 10,
            fillColor: win ? "#ffb020" : COLORS[i % COLORS.length],
            fillOpacity: 1,
            strokeColor: "#0b0b12",
            strokeWeight: 2,
          },
          label: {
            text: String(i + 1),
            color: "#191322",
            fontSize: win ? "13px" : "11px",
            fontWeight: "900",
          },
        })
      );
    });

    if (userAt) {
      userDot.current?.setMap(null);
      userDot.current = new g.Marker({
        map: map.current,
        position: { lat: userAt.lat, lng: userAt.lng },
        title: "내 위치",
        zIndex: 1000,
        icon: {
          path: g.SymbolPath.CIRCLE,
          scale: 6,
          fillColor: "#3ddc97",
          fillOpacity: 1,
          strokeColor: "#0a0710",
          strokeWeight: 2.5,
        },
      });
    }
  }, [ready, places, slots, winner, userAt]);

  useEffect(
    () => () => {
      markers.current.forEach((m) => m.setMap(null));
      markers.current = [];
      userDot.current?.setMap(null);
      circle.current?.setMap(null);
    },
    []
  );

  return <div ref={host} className={className} />;
}
