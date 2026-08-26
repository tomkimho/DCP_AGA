#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""주간 업무보고 대시보드 생성기

Google Docs '주간 업무보고' 문서를 마크다운으로 내려받아 단일 HTML 대시보드로
변환한다. 회의 회차별 표(조직 x 진행현황/진행계획)를 파싱해 조직·카테고리·
프로젝트 축으로 재구성한다.

  python3 scripts/13_업무대시보드.py <input.md> [-o output.html]

주의: 입력 문서와 생성된 HTML에는 고객사·계약·인사 정보가 포함되므로
      저장소(공개)에 커밋하지 않는다. output/ 경로는 .gitignore 대상이다.
"""

import argparse
import collections
import json
import os
import re
import sys

# ---------------------------------------------------------------- 카테고리

CATEGORIES = [
    ("sales", "매출"),
    ("gov", "정부지원사업"),
    ("tech", "기술개발"),
    ("biz", "영업·마케팅·행사"),
    ("etc", "기타"),
]
CATEGORY_LABEL = dict(CATEGORIES)

# 표 안에서 프로젝트명처럼 보이지만 실제로는 소제목인 토큰
SECTION_LABELS = {
    "기획", "개발", "검증", "자료관리", "설치", "내부운영", "과제운영",
    "수요조사", "운영", "코드 아카이빙", "상품기획", "기타",
}

EVENT_DATE_RE = re.compile(r"\d{1,2}/\d{1,2}")


def category_of(title):
    t = title.replace(" ", "")
    if "매출" in t:
        return "sales"
    if "정부" in t or "지원사업" in t:
        return "gov"
    if "기술개발" in t or "DEEP" in t.upper():
        return "tech"
    if "영업" in t or "마케팅" in t or "행사" in t:
        return "biz"
    return "etc"


# ---------------------------------------------------------------- 텍스트 정리

def unescape(s):
    s = s.replace("\\\\", "\x00")
    s = re.sub(r"\\([\\`*_{}\[\]()#+\-.!<>~|&$])", r"\1", s)
    return s.replace("\x00", "").replace("\\*", "*")


def clean_cell(s):
    s = unescape(s).replace("**", "\x01")  # 볼드 표식은 자리표시자로 보존
    return re.sub(r"\s+", " ", s).strip()


def split_categories(text):
    """셀 본문을 '1. 매출 / 2. 정부지원사업 / ...' 단위로 자른다."""
    marks = [
        (m.start(), m.group(1), m.group(2).strip())
        for m in re.finditer(r"(?<![\d\-])([1-9])[.]\s*([가-힣A-Za-z,\s/]{1,12})", text)
    ]
    kept, expect = [], 1
    for pos, num, title in marks:
        if int(num) == expect:
            kept.append((pos, title))
            expect += 1
    if not kept:
        return {"etc": text.strip()} if text.strip() else {}

    out = collections.OrderedDict()
    for i, (pos, title) in enumerate(kept):
        end = kept[i + 1][0] if i + 1 < len(kept) else len(text)
        body = re.sub(r"^[1-9][.]\s*", "", text[pos:end].strip())
        if body.startswith(title):
            body = body[len(title):].strip()
        key = category_of(title)
        out[key] = (out.get(key, "") + " " + body).strip()
    return out


def bulletize(text):
    """카테고리 본문을 읽을 수 있는 줄 단위로 쪼갠다."""
    t = text.replace("\x01", "\x02")
    t = re.sub(r"\s*○\s*", "\n○ ", t)
    t = re.sub(r"\s*※\s*", "\n※ ", t)
    t = re.sub(r"\s*-\s+", "\n- ", t)
    # \x02(...)\x02 = 원문에서 볼드 처리된 프로젝트/과제명
    t = re.sub(r"\x02\s*\(([^)]{1,60})\)\s*\x02", "\n\x03" + r"\1" + "\x03", t)
    t = t.replace("\x02", "")
    t = re.sub(r"\*+", "", t)  # 짝이 맞지 않아 남은 강조 표식 제거
    lines = [re.sub(r"\s+", " ", p).strip(" -").strip() for p in t.split("\n")]
    return [l for l in lines if l and l not in ("○", "※")]


# ---------------------------------------------------------------- 파싱

def parse(raw):
    lines = raw.split("\n")
    heads = [
        (i, l.strip().lstrip("#").strip())
        for i, l in enumerate(lines)
        if re.match(r"^#\s+\d{4}-\d{2}-\d{2}\s*$", l.strip())
    ]
    meetings = []
    for idx, (start, date) in enumerate(heads):
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if lines[j].startswith("# "):
                end = j
                break
        meetings.append(parse_block(lines[start:end], date))
    return meetings


def parse_block(block, date):
    weekday, presenters = "", []
    for l in block[:14]:
        m = re.match(r"^\d{4}-\d{2}-\d{2}\s*\((.)\)", l.strip())
        if m:
            weekday = m.group(1)
        if "발표순서" in l:
            tail = unescape(l).split(":", 1)[-1]
            presenters = [x.strip() for x in re.split(r"[>》]", tail) if x.strip()]

    rows, current = [], None
    for l in block:
        if not l.startswith("|"):
            continue
        cols = l.split("|")
        if len(cols) < 4:
            continue
        c1, c2, c3 = clean_cell(cols[1]), clean_cell(cols[2]), clean_cell(cols[3])
        if c1 in ("", ":-:", "진행 현황") or c1.startswith(":"):
            if current and (c2 or c3):  # 같은 셀이 여러 줄로 쪼개진 경우
                current["done_raw"] += " " + c2
                current["plan_raw"] += " " + c3
            continue
        if c2 == "진행 현황":
            continue
        name = c1.replace("\x01", "")
        m = re.search(r"\(([^()]+)\)\s*$", name)
        person = m.group(1) if m else ""
        org = re.sub(r"\(([^()]+)\)\s*$", "", name).strip().strip("-").strip()
        org = re.sub(r"\s*-\s*", " - ", org)
        current = {"org": org, "person": person, "done_raw": c2, "plan_raw": c3}
        rows.append(current)

    for r in rows:
        for src, dst in (("done_raw", "done"), ("plan_raw", "plan")):
            cats = split_categories(r.pop(src))
            r[dst] = {k: b for k, b in ((k, bulletize(v)) for k, v in cats.items()) if b}

    # 이슈/지시사항 블록은 '상위 줄 + 딸린 목록' 구조라 맥락을 붙여야 읽힌다.
    #   § 행사명   → 뒤따르는 최상위 항목들의 맥락
    #   본부명     → 들여쓴 하위 항목들의 맥락
    issues, directives, bucket = [], [], None
    section, group = "", ""
    for l in block:
        raw = unescape(l)
        s = raw.strip()
        if not s:
            continue
        if s.startswith("○ 이슈사항"):
            bucket, section, group = issues, "", ""
            continue
        if s.startswith("○ 대표님"):
            bucket, section, group = directives, "", ""
            continue
        if s.startswith("#") or s.startswith("|"):
            bucket = None
            continue
        if bucket is None:
            continue
        if s.startswith("-"):
            v = re.sub(r"\s+", " ", s.lstrip("-").strip())
            if not v:
                continue
            indented = raw[:1].isspace()
            ctx = group if indented else section
            bucket.append(f"{ctx} › {v}" if ctx else v)
        elif s.startswith("§"):
            section = re.sub(r"^§\s*", "", re.sub(r"\s+", " ", s)).strip()
        else:
            group = re.sub(r"\s+", " ", s).strip()
            section = ""

    return {
        "date": date,
        "weekday": weekday,
        "presenters": presenters,
        "rows": rows,
        "issues": issues,
        "directives": directives,
    }


# ---------------------------------------------------------------- 집계

def collapse_notes(notes):
    """같은 문구가 여러 회차에 그대로 반복되면 한 줄로 접고 회차를 모은다.

    주간보고 특성상 동일 문장이 몇 주씩 이월되는데, 그대로 나열하면 이력이
    읽히지 않는다. 접어두면 '몇 주째 같은 문구'라는 정체 신호가 드러난다.
    """
    groups = {}
    order = []
    for nt in notes:
        key = (nt["text"], nt["org"], nt["kind"])
        if key not in groups:
            groups[key] = {"text": nt["text"], "org": nt["org"], "kind": nt["kind"],
                           "cat": nt["cat"], "dates": []}
            order.append(key)
        if nt["date"] not in groups[key]["dates"]:
            groups[key]["dates"].append(nt["date"])
    out = [groups[k] for k in order]
    out.sort(key=lambda g: g["dates"][-1], reverse=True)
    return out[:120]


def build_projects(meetings):
    """볼드로 표기된 프로젝트/과제/고객사를 회차별로 집계한다.

    원문은 '**(고객사명)**' 같은 제목 줄을 두고 그 아래 세부 항목을 잇는
    구조이므로, 제목 줄 이후의 항목은 다음 제목이 나올 때까지 같은 건으로
    귀속시킨다.
    """
    acc = {}
    for mi, mt in enumerate(meetings):
        for row in mt["rows"]:
            for key in ("done", "plan"):
                for cat, bullets in row[key].items():
                    current = None  # 카테고리가 바뀌면 귀속 대상도 초기화
                    for b in bullets:
                        m = re.match(r"\x03([^\x03]+)\x03", b)
                        body = b
                        if m:
                            name = m.group(1).strip()
                            body = b[m.end():].strip(" -:")
                            current = None if name in SECTION_LABELS else name
                        if not current:
                            continue
                        p = acc.setdefault(current, {
                            "name": current,
                            "cats": collections.Counter(),
                            "orgs": collections.Counter(),
                            "series": [0] * len(meetings),
                            "notes": [],
                        })
                        p["cats"][cat] += 1
                        p["orgs"][row["org"]] += 1
                        p["series"][mi] += 1
                        if body and not re.match(r"^[○※]?\s*[^:：]{0,14}[:：]\s*$", body):
                            p["notes"].append({
                                "date": mt["date"], "org": row["org"],
                                "kind": key, "cat": cat, "text": body,
                            })

    projects = []
    for p in acc.values():
        p["notes"] = collapse_notes(p["notes"])
        cat = p["cats"].most_common(1)[0][0]
        is_event = bool(EVENT_DATE_RE.search(p["name"]))
        kind = "event" if is_event else {"sales": "client", "gov": "grant",
                                         "tech": "product"}.get(cat, "other")
        seen = [i for i, v in enumerate(p["series"]) if v]
        projects.append({
            "name": p["name"],
            "kind": kind,
            "cat": cat,
            "count": sum(p["series"]),
            "series": p["series"],
            "orgs": [o for o, _ in p["orgs"].most_common()],
            "first": seen[0] if seen else 0,
            "last": seen[-1] if seen else 0,
            "notes": p["notes"],
        })
    projects.sort(key=lambda x: (-x["count"], x["name"]))
    return projects


def build_register(meetings, field):
    """이슈·지시사항은 해결될 때까지 매주 그대로 이월된다.

    회차마다 나열하면 같은 문장이 반복될 뿐이므로 항목 단위로 묶어
    '언제 처음 올라와 몇 회차째 남아 있는지'를 보이게 한다.
    """
    reg = collections.OrderedDict()
    for mi, mt in enumerate(meetings):
        for text in mt[field]:
            r = reg.setdefault(text, {"text": text, "idx": []})
            if mi not in r["idx"]:
                r["idx"].append(mi)

    last_idx = len(meetings) - 1
    out = []
    for r in reg.values():
        idx = r["idx"]
        # 마지막 등장 시점까지 끊기지 않고 이어진 회차 수
        streak = 1
        for a, b in zip(reversed(idx), reversed(idx[:-1])):
            if a - b == 1:
                streak += 1
            else:
                break
        out.append({
            "text": r["text"],
            "first": meetings[idx[0]]["date"],
            "last": meetings[idx[-1]]["date"],
            "count": len(idx),
            "streak": streak,
            "open": idx[-1] == last_idx,
            "new": idx[0] == last_idx,
        })
    out.sort(key=lambda x: (not x["open"], -x["streak"], x["first"]))
    return out


def build_payload(meetings):
    orgs = collections.OrderedDict()
    for mt in meetings:
        for r in mt["rows"]:
            o = orgs.setdefault(r["org"], {"org": r["org"], "people": [], "meetings": 0})
            o["meetings"] += 1
            if r["person"] and r["person"] not in o["people"]:
                o["people"].append(r["person"])

    # 회차 x 조직 활동량(불릿 수) — 히트맵 원본
    activity = {}
    for mi, mt in enumerate(meetings):
        for r in mt["rows"]:
            n = sum(len(v) for v in r["done"].values()) + sum(len(v) for v in r["plan"].values())
            activity.setdefault(r["org"], [0] * len(meetings))[mi] += n

    return {
        "generated": None,  # 호출부에서 채움
        "dates": [m["date"] for m in meetings],
        "meetings": meetings,
        "orgs": list(orgs.values()),
        "activity": activity,
        "projects": build_projects(meetings),
        "issues": build_register(meetings, "issues"),
        "directives": build_register(meetings, "directives"),
        "categories": CATEGORIES,
    }


# ---------------------------------------------------------------- 렌더링

def render(payload):
    tpl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "assets", "dashboard_template.html")
    with open(tpl_path, encoding="utf-8") as f:
        tpl = f.read()
    # ensure_ascii=True: 한글을 \\uXXXX로 이스케이프한다. 뷰어가 인코딩을 잘못
    # 잡아도 데이터는 ASCII라 깨지지 않고, 화면에는 정상 한글로 복원된다.
    data = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    data = data.replace("</", "<\\/")  # </script> 조기 종료 방지
    return tpl.replace("/*__DATA__*/null", data)


def main():
    ap = argparse.ArgumentParser(description="주간 업무보고 대시보드 생성")
    ap.add_argument("input", help="Google Docs에서 내려받은 마크다운 파일")
    ap.add_argument("-o", "--output", default="output/업무대시보드.html")
    ap.add_argument("--stamp", default="", help="생성 시각 표기 (예: 2026-08-19)")
    args = ap.parse_args()

    with open(args.input, encoding="utf-8") as f:
        raw = f.read()

    meetings = parse(raw)
    if not meetings:
        sys.exit("회의 블록(# YYYY-MM-DD)을 찾지 못했습니다. 입력 형식을 확인하세요.")

    payload = build_payload(meetings)
    payload["generated"] = args.stamp

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(render(payload))

    print(f"회의 {len(meetings)}회 · 조직 {len(payload['orgs'])}개 · "
          f"프로젝트 {len(payload['projects'])}건 → {args.output}")


if __name__ == "__main__":
    main()
