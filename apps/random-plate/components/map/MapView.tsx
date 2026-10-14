"use client";

import { useState } from "react";
import GoogleMapView from "./GoogleMapView";
import MapCanvas from "./MapCanvas";
import type { MapViewProps } from "./types";

/**
 * 구글 지도 키가 있으면 진짜 지도를, 없거나 거부되면 캔버스 지도를 쓴다.
 *
 * 키가 잘못돼도 화면이 회색 사각형으로 죽지 않게, 실패 사유를 받아
 * 폴백으로 되돌리고 그 사유를 화면에 그대로 보여준다.
 */
export default function MapView(props: MapViewProps) {
  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
  const [failure, setFailure] = useState<string | null>(null);

  if (apiKey && !failure) {
    return (
      <GoogleMapView
        {...props}
        apiKey={apiKey}
        onUnavailable={(reason) => setFailure(reason)}
      />
    );
  }

  return (
    <>
      <MapCanvas {...props} />
      {failure && (
        <p className="absolute inset-x-3 bottom-3 rounded-lg border border-red-400/30 bg-red-950/80 px-3 py-2 text-[11px] font-bold leading-snug text-red-200 backdrop-blur">
          {failure}
        </p>
      )}
    </>
  );
}
