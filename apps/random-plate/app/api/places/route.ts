import { NextResponse } from "next/server";
import { cacheKey, distanceMeters, snapToGrid } from "@/lib/grid";
import { demoPlaces } from "@/lib/demo-places";
import type { Coords, Place, PlacesResponse } from "@/lib/types";

export const dynamic = "force-dynamic";

const KAKAO_ENDPOINT = "https://dapi.kakao.com/v2/local/search/category.json";
const CATEGORY_GROUP = "FD6"; // 음식점
const PAGES = 3; // 15개 × 3페이지 = 최대 45곳 후보 풀
const TTL_MS = 7 * 24 * 60 * 60 * 1000;

/**
 * 기획서 §3.3의 place_cache를 프로세스 메모리로 구현한 것.
 *
 * 서버리스라 인스턴스마다 따로 존재하고 콜드스타트에 사라진다.
 * Stage 2에서 Supabase place_cache 테이블로 교체될 자리이며,
 * 지금 단계의 목적은 "리롤이 API 호출을 유발하지 않는다"는
 * 핵심 설계를 실제로 성립시키는 것이다.
 */
const cache = new Map<string, { at: number; places: Place[] }>();

type KakaoDoc = {
  id: string;
  place_name: string;
  category_name: string;
  road_address_name: string;
  address_name: string;
  place_url: string;
  x: string; // 경도
  y: string; // 위도
  distance: string;
};

/** "음식점 > 한식 > 국밥" → "국밥" */
function leafCategory(raw: string): string {
  const parts = raw.split(">").map((s) => s.trim()).filter(Boolean);
  return parts[parts.length - 1] || "음식점";
}

async function fetchKakao(
  key: string,
  center: Coords,
  radiusM: number
): Promise<Place[]> {
  const seen = new Set<string>();
  const places: Place[] = [];

  for (let page = 1; page <= PAGES; page++) {
    const url = new URL(KAKAO_ENDPOINT);
    url.searchParams.set("category_group_code", CATEGORY_GROUP);
    url.searchParams.set("x", String(center.lng));
    url.searchParams.set("y", String(center.lat));
    url.searchParams.set("radius", String(radiusM));
    url.searchParams.set("sort", "distance");
    url.searchParams.set("size", "15");
    url.searchParams.set("page", String(page));

    const res = await fetch(url, {
      headers: { Authorization: `KakaoAK ${key}` },
      cache: "no-store",
    });

    if (!res.ok) {
      // 첫 페이지부터 실패하면 호출자가 데모로 폴백하도록 던진다.
      // 2페이지 이후 실패는 이미 모은 결과로 진행한다.
      if (page === 1) {
        throw new Error(`kakao ${res.status}: ${await res.text()}`);
      }
      break;
    }

    const body = (await res.json()) as {
      documents: KakaoDoc[];
      meta?: { is_end?: boolean };
    };

    for (const d of body.documents ?? []) {
      if (seen.has(d.id)) continue;
      seen.add(d.id);
      places.push({
        id: d.id,
        name: d.place_name,
        category: leafCategory(d.category_name),
        roadAddress: d.road_address_name || d.address_name || null,
        placeUrl: d.place_url,
        lat: Number(d.y),
        lng: Number(d.x),
        distanceM: d.distance
          ? Number(d.distance)
          : distanceMeters(center, { lat: Number(d.y), lng: Number(d.x) }),
      });
    }

    if (body.meta?.is_end) break;
  }

  return places.sort((a, b) => a.distanceM - b.distanceM);
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const lat = Number(url.searchParams.get("lat"));
  const lng = Number(url.searchParams.get("lng"));
  const radiusM = Math.min(
    3000,
    Math.max(200, Number(url.searchParams.get("radius")) || 800)
  );

  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    return NextResponse.json({ error: "invalid coords" }, { status: 400 });
  }

  // §9 — 정밀 좌표는 여기서 버리고, 이후 모든 처리는 격자 좌표로만 한다.
  const center = snapToGrid({ lat, lng });
  const key = cacheKey(center, radiusM);
  const kakaoKey = process.env.KAKAO_REST_API_KEY;

  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < TTL_MS) {
    return NextResponse.json({
      places: hit.places,
      demo: !kakaoKey,
      cached: true,
    } satisfies PlacesResponse);
  }

  let places: Place[];
  let demo = false;

  if (kakaoKey) {
    try {
      places = await fetchKakao(kakaoKey, center, radiusM);
      if (places.length === 0) {
        // 키는 유효한데 반경 내 결과가 0인 경우 — 데모로 덮지 않고 그대로 알린다
        return NextResponse.json({
          places: [],
          demo: false,
          cached: false,
        } satisfies PlacesResponse);
      }
    } catch (e) {
      console.error("[places] kakao 호출 실패, 데모로 폴백:", e);
      places = demoPlaces(center, radiusM);
      demo = true;
    }
  } else {
    places = demoPlaces(center, radiusM);
    demo = true;
  }

  if (!demo) cache.set(key, { at: Date.now(), places });

  return NextResponse.json({
    places,
    demo,
    cached: false,
  } satisfies PlacesResponse);
}
