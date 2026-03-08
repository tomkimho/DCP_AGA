#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
=============================================================
12_바이오마커_분석.py
=============================================================
용도: AGA_data.xlsx의 바이오마커 컬럼에서 바이오마커를 추출·정규화,
      바이오마커-타겟-경로 매트릭스를 생성합니다.

실행: python 12_biomarker_analysis.py
소요: 약 1-2분
비용: 무료 (로컬 분석)
=============================================================
"""

import os
import sys
import json
import re
from collections import Counter, defaultdict
from datetime import datetime

import pandas as pd

# BASE_FOLDER 설정
BASE_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_FOLDER = os.path.join(BASE_FOLDER, 'output')
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ============================================================
# 바이오마커 정규화 사전
# ============================================================
BIOMARKER_NORMALIZE = {
    'dht': 'DHT',
    'dihydrotestosterone': 'DHT',
    '5α-dihydrotestosterone': 'DHT',
    'testosterone': 'Testosterone',
    'vegf': 'VEGF',
    'vascular endothelial growth factor': 'VEGF',
    'igf-1': 'IGF-1',
    'igf1': 'IGF-1',
    'insulin-like growth factor 1': 'IGF-1',
    'tgf-β': 'TGF-β',
    'tgf-β1': 'TGF-β1',
    'tgfb1': 'TGF-β1',
    'bmp': 'BMP',
    'bmp2': 'BMP2',
    'bmp4': 'BMP4',
    'wnt': 'Wnt',
    'β-catenin': 'β-Catenin',
    'beta-catenin': 'β-Catenin',
    'pgd2': 'PGD2',
    'prostaglandin d2': 'PGD2',
    'pge2': 'PGE2',
    'prostaglandin e2': 'PGE2',
    'il-6': 'IL-6',
    'il-1β': 'IL-1β',
    'tnf-α': 'TNF-α',
    'tnf-alpha': 'TNF-α',
    'ki-67': 'Ki-67',
    'ki67': 'Ki-67',
    'dkk-1': 'DKK-1',
    'dkk1': 'DKK-1',
    'shh': 'Sonic Hedgehog',
    'sonic hedgehog': 'Sonic Hedgehog',
    'fgf-7': 'FGF-7',
    'fgf7': 'FGF-7',
    'kgf': 'FGF-7',
    'hgf': 'HGF',
    'hepatocyte growth factor': 'HGF',
    'ar': 'AR (Androgen Receptor)',
    'androgen receptor': 'AR (Androgen Receptor)',
    'minoxidil': 'Minoxidil (marker)',
    'atp': 'ATP',
    'ros': 'ROS',
    'reactive oxygen species': 'ROS',
    'nf-kb': 'NF-κB',
    'nf-κb': 'NF-κB',
    'jak': 'JAK-STAT',
    'stat': 'JAK-STAT',
    'jak-stat': 'JAK-STAT',
    'p53': 'p53',
    'caspase-3': 'Caspase-3',
    'bcl-2': 'Bcl-2',
    'mmp': 'MMPs',
    'mmp-1': 'MMP-1',
    'mmp-9': 'MMP-9',
}


def load_data():
    """AGA 데이터 로드"""
    candidates = [
        os.path.join(BASE_FOLDER, 'AGA_data.xlsx'),
        os.path.join(BASE_FOLDER, 'AGA_문헌분류_결과.xlsx'),
    ]
    for path in candidates:
        if os.path.exists(path):
            df = pd.read_excel(path, engine='openpyxl')
            print(f"✓ 데이터 로드: {path} ({len(df)}행)")
            return df
    print("ERROR: AGA 데이터 파일을 찾을 수 없습니다.")
    return None


def normalize_biomarker(name):
    """바이오마커 이름 정규화"""
    name = name.strip()
    key = name.lower().strip()
    return BIOMARKER_NORMALIZE.get(key, name)


def extract_biomarkers(df):
    """바이오마커 컬럼에서 바이오마커 추출 및 정규화"""
    print("\n[1단계] 바이오마커 추출...")

    biomarker_col = None
    for col in df.columns:
        if '바이오마커' in col.lower() or 'biomarker' in col.lower():
            biomarker_col = col
            break

    if not biomarker_col:
        print("WARNING: '바이오마커' 컬럼을 찾을 수 없습니다.")
        return [], {}

    all_biomarkers = Counter()
    biomarker_papers = defaultdict(list)  # biomarker → [paper indices]

    for idx, row in df.iterrows():
        val = str(row.get(biomarker_col, ''))
        if not val or val == 'nan' or val == '' or val == '[]':
            continue

        # 쉼표, 세미콜론, '/' 로 분리
        parts = re.split(r'[,;/]', val)
        for part in parts:
            part = part.strip()
            if len(part) < 2 or part.lower() in ('none', 'n/a', 'na', 'unknown', '없음'):
                continue
            normalized = normalize_biomarker(part)
            all_biomarkers[normalized] += 1
            biomarker_papers[normalized].append(idx)

    print(f"  총 {len(all_biomarkers)}종 바이오마커 발견")
    return all_biomarkers, biomarker_papers


def build_biomarker_target_matrix(df, biomarker_papers):
    """바이오마커-타겟 매트릭스 구축"""
    print("\n[2단계] 바이오마커-타겟 매트릭스 구축...")

    target_col = None
    for col in df.columns:
        if '타겟' in col.lower() or 'target' in col.lower():
            target_col = col
            break

    pathway_col = None
    for col in df.columns:
        if '경로' in col.lower() or 'pathway' in col.lower():
            pathway_col = col
            break

    matrix = {}  # {biomarker: {target: count}}
    biomarker_pathways = defaultdict(Counter)  # {biomarker: {pathway: count}}

    for biomarker, paper_indices in biomarker_papers.items():
        target_counts = Counter()
        for idx in paper_indices:
            if idx >= len(df):
                continue
            row = df.iloc[idx]

            # 타겟 추출
            if target_col:
                targets_str = str(row.get(target_col, ''))
                if targets_str and targets_str != 'nan':
                    for t in re.split(r'[,;]', targets_str):
                        t = t.strip()
                        if t and len(t) > 1:
                            target_counts[t] += 1

            # 경로 추출
            if pathway_col:
                pathways_str = str(row.get(pathway_col, ''))
                if pathways_str and pathways_str != 'nan':
                    for p in re.split(r'[,;]', pathways_str):
                        p = p.strip()
                        if p and len(p) > 1:
                            biomarker_pathways[biomarker][p] += 1

        if target_counts:
            matrix[biomarker] = dict(target_counts.most_common(10))

    print(f"  {len(matrix)}개 바이오마커-타겟 관계 구축")
    return matrix, biomarker_pathways


def categorize_biomarkers(all_biomarkers, biomarker_target_matrix):
    """바이오마커를 카테고리별로 분류"""
    print("\n[3단계] 바이오마커 카테고리 분류...")

    categories = {
        "Hormones": ['DHT', 'Testosterone', 'Estrogen', 'Cortisol', 'DHEA'],
        "Growth Factors": ['VEGF', 'IGF-1', 'FGF-7', 'HGF', 'EGF', 'TGF-β', 'TGF-β1', 'BMP2', 'BMP4', 'PDGF'],
        "Cytokines": ['IL-6', 'IL-1β', 'TNF-α', 'IL-8', 'IL-17', 'IFN-γ'],
        "Signaling": ['Wnt', 'β-Catenin', 'Sonic Hedgehog', 'JAK-STAT', 'NF-κB', 'DKK-1', 'Notch'],
        "Lipid Mediators": ['PGD2', 'PGE2', 'PGF2α', 'LTB4'],
        "Oxidative Stress": ['ROS', 'SOD', 'Catalase', 'GPx', 'MDA'],
        "Apoptosis": ['p53', 'Caspase-3', 'Bcl-2', 'Bax', 'Ki-67'],
        "Enzymes": ['MMPs', 'MMP-1', 'MMP-9', 'AR (Androgen Receptor)', '5α-Reductase', 'ATP'],
    }

    categorized = {}
    uncategorized = []

    for bm, count in all_biomarkers.most_common():
        found = False
        for cat, members in categories.items():
            if bm in members:
                categorized.setdefault(cat, []).append({"name": bm, "count": count})
                found = True
                break
        if not found:
            uncategorized.append({"name": bm, "count": count})

    if uncategorized:
        categorized["Other"] = uncategorized

    print(f"  {len(categories)}개 카테고리로 분류 완료")
    return categorized


def save_results(all_biomarkers, biomarker_target_matrix, biomarker_pathways, categorized):
    """결과 저장"""
    print("\n[4단계] 결과 저장...")

    result = {
        "generated_at": datetime.now().isoformat(),
        "total_biomarkers": len(all_biomarkers),
        "top_biomarkers": [
            {"name": name, "count": count}
            for name, count in all_biomarkers.most_common(50)
        ],
        "biomarker_target_matrix": biomarker_target_matrix,
        "biomarker_pathways": {
            bm: dict(pathways.most_common(5))
            for bm, pathways in biomarker_pathways.items()
        },
        "categories": categorized,
    }

    output_path = os.path.join(OUTPUT_FOLDER, 'biomarker_analysis.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"✓ {output_path} 저장 완료")

    # pipeline_status.json 업데이트
    status_path = os.path.join(BASE_FOLDER, 'pipeline_status.json')
    status = {}
    if os.path.exists(status_path):
        try:
            with open(status_path, 'r', encoding='utf-8') as f:
                status = json.load(f)
        except Exception:
            pass

    status['step_12_biomarker_analysis'] = {
        'completed': True,
        'timestamp': datetime.now().isoformat(),
        'total_biomarkers': len(all_biomarkers),
        'categories': len(categorized)
    }

    with open(status_path, 'w', encoding='utf-8') as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
    print(f"✓ pipeline_status.json 업데이트 완료")


def main():
    print("=" * 60)
    print("12_바이오마커_분석.py 시작")
    print("=" * 60)

    df = load_data()
    if df is None:
        return

    all_biomarkers, biomarker_papers = extract_biomarkers(df)
    if not all_biomarkers:
        print("바이오마커 데이터가 없습니다. 종료.")
        return

    biomarker_target_matrix, biomarker_pathways = build_biomarker_target_matrix(df, biomarker_papers)
    categorized = categorize_biomarkers(all_biomarkers, biomarker_target_matrix)
    save_results(all_biomarkers, biomarker_target_matrix, biomarker_pathways, categorized)

    print("\n" + "=" * 60)
    print(f"✓ 바이오마커 분석 완료: {len(all_biomarkers)}종")
    print("=" * 60)


if __name__ == "__main__":
    main()
