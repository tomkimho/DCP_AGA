# -*- coding: utf-8 -*-
"""
=============================================================
10_지능형_패턴분석.py
=============================================================
용도: 축적된 논문 데이터에서 패턴을 발견하고
      Dark Target(저빈도+고관련도 타겟)을 발굴합니다.

실행: python 10_지능형_패턴분석.py
소요: 약 5-10분
비용: 무료 (로컬 분석)
=============================================================
"""

import os
import json
import sys
from collections import Counter
import pandas as pd
import numpy as np
from datetime import datetime

# BASE_FOLDER 설정
BASE_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FOLDER = os.path.join(BASE_FOLDER, 'data')
OUTPUT_FOLDER = os.path.join(BASE_FOLDER, 'output')

# Target 정규화 사전 (09_웹사이트.py와 동일)
TARGET_NORMALIZE = {
    'ar': 'AR',
    'androgen receptor': 'AR',
    'dht receptor': 'AR',
    '5-alpha reductase': '5α-Reductase',
    '5α-reductase': '5α-Reductase',
    '5a-reductase': '5α-Reductase',
    'sar1': '5α-Reductase',
    'sar2': '5α-Reductase',
    'sar3': '5α-Reductase',
    'finasteride': '5α-Reductase',
    'wnt': 'Wnt/β-Catenin',
    'wnt/β-catenin': 'Wnt/β-Catenin',
    'wnt signaling': 'Wnt/β-Catenin',
    'lrp6': 'Wnt/β-Catenin',
    'fzd': 'Wnt/β-Catenin',
    'pparγ': 'PPARγ',
    'pparg': 'PPARγ',
    'peroxisome proliferator-activated receptor gamma': 'PPARγ',
    'tgf-β': 'TGF-β',
    'tgfb': 'TGF-β',
    'transforming growth factor beta': 'TGF-β',
    'bmp': 'BMP',
    'bone morphogenetic protein': 'BMP',
    'fgf': 'FGF',
    'fibroblast growth factor': 'FGF',
    'hedgehog': 'Hedgehog',
    'hh': 'Hedgehog',
    'notch': 'Notch',
    'egfr': 'EGFR',
    'epidermal growth factor receptor': 'EGFR',
}

def normalize_target(target_str):
    """타겟명을 정규화합니다."""
    if pd.isna(target_str):
        return None
    normalized = str(target_str).strip().lower()
    return TARGET_NORMALIZE.get(normalized, str(target_str).strip())

def calculate_pmi(target_freq, compound_freq, cooccurrence_freq, total_pairs):
    """
    Pointwise Mutual Information 계산
    PMI(target, compound) = log(P(target, compound) / (P(target) * P(compound)))
    """
    if cooccurrence_freq == 0:
        return 0

    p_both = cooccurrence_freq / total_pairs
    p_target = target_freq / total_pairs
    p_compound = compound_freq / total_pairs

    if p_target == 0 or p_compound == 0:
        return 0

    pmi = np.log(p_both / (p_target * p_compound))
    return max(0, pmi)  # Negative PMI를 0으로 처리

def load_literature_data():
    """AGA_문헌분류_결과.xlsx 파일을 로드합니다."""
    filepath = os.path.join(DATA_FOLDER, 'AGA_문헌분류_결과.xlsx')

    if not os.path.exists(filepath):
        print(f"ERROR: {filepath} 파일을 찾을 수 없습니다.")
        return None

    try:
        df = pd.read_excel(filepath)
        print(f"✓ 문헌 데이터 로드 완료: {len(df)} 행")
        return df
    except Exception as e:
        print(f"ERROR: 파일 로드 실패 - {e}")
        return None

def build_network_analysis(df):
    """Target-Compound 네트워크 분석"""
    print("\n[1단계] Target-Compound 네트워크 분석 시작...")

    # Target과 Compound 추출
    targets = []
    compounds = []
    target_relevance = {}
    compound_usage = Counter()
    target_usage = Counter()
    pathway_map = {}
    moa_map = {}
    cooccurrence_matrix = {}

    total_papers = len(df)

    for idx, row in df.iterrows():
        # Target 추출 및 정규화
        target_list = []
        if pd.notna(row.get('주요_타겟')):
            target_str = str(row['주요_타겟'])
            for t in target_str.split(';'):
                t = t.strip()
                if t:
                    normalized = normalize_target(t)
                    if normalized:
                        target_list.append(normalized)

        # Compound 추출
        compound_list = []
        if pd.notna(row.get('분석된_화합물')):
            compound_str = str(row['분석된_화합물'])
            for c in compound_str.split(';'):
                c = c.strip()
                if c:
                    compound_list.append(c)

        # Pathway 추출
        pathway = str(row.get('경로', 'Unknown')).strip() if pd.notna(row.get('경로')) else 'Unknown'

        # MoA 추출
        moa = str(row.get('작용기전', 'Unknown')).strip() if pd.notna(row.get('작용기전')) else 'Unknown'

        # Relevance 추출
        relevance = float(row.get('관련도_점수', 0.5)) if pd.notna(row.get('관련도_점수')) else 0.5

        # Target 관련도 저장
        for target in target_list:
            if target not in target_relevance:
                target_relevance[target] = []
            target_relevance[target].append(relevance)
            target_usage[target] += 1

            if target not in pathway_map:
                pathway_map[target] = set()
            pathway_map[target].add(pathway)

            if target not in moa_map:
                moa_map[target] = set()
            moa_map[target].add(moa)

        # Compound 사용횟수
        for compound in compound_list:
            compound_usage[compound] += 1

        # Co-occurrence 매트릭스 구축
        for target in target_list:
            if target not in cooccurrence_matrix:
                cooccurrence_matrix[target] = {}
            for compound in compound_list:
                if compound not in cooccurrence_matrix[target]:
                    cooccurrence_matrix[target][compound] = 0
                cooccurrence_matrix[target][compound] += 1

    # 평균 관련도 계산
    avg_target_relevance = {
        target: np.mean(scores)
        for target, scores in target_relevance.items()
    }

    print(f"✓ 발견된 타겟 수: {len(target_usage)}")
    print(f"✓ 발견된 화합물 수: {len(compound_usage)}")

    return {
        'target_usage': target_usage,
        'compound_usage': compound_usage,
        'avg_target_relevance': avg_target_relevance,
        'target_relevance': target_relevance,
        'pathway_map': pathway_map,
        'moa_map': moa_map,
        'cooccurrence_matrix': cooccurrence_matrix,
        'total_papers': total_papers
    }

def calculate_novelty_index(network_data):
    """Dark Target 발굴을 위한 Novelty Index 계산"""
    print("\n[2단계] Novelty Index 계산...")

    target_usage = network_data['target_usage']
    avg_target_relevance = network_data['avg_target_relevance']
    pathway_map = network_data['pathway_map']

    dark_targets = []

    for target in target_usage.keys():
        paper_count = target_usage[target]
        relevance = avg_target_relevance.get(target, 0.5)
        pathway_diversity = len(pathway_map.get(target, set()))

        # Novelty Index 계산
        # 낮은 빈도 + 높은 관련도 + 다양한 경로 = 높은 신규성
        frequency_score = 1.0 / (paper_count + 1)  # 낮은 빈도일수록 높은 점수
        novelty_index = frequency_score * relevance * max(1, pathway_diversity)

        dark_targets.append({
            'target': target,
            'paper_count': paper_count,
            'relevance_score': relevance,
            'pathway_diversity': pathway_diversity,
            'frequency_score': frequency_score,
            'novelty_index': novelty_index
        })

    # Novelty Index 기준 정렬 (내림차순)
    dark_targets.sort(key=lambda x: x['novelty_index'], reverse=True)

    print(f"✓ Top 10 Dark Targets:")
    for i, target in enumerate(dark_targets[:10], 1):
        print(f"  {i}. {target['target']}: novelty={target['novelty_index']:.4f}, "
              f"papers={target['paper_count']}, relevance={target['relevance_score']:.3f}")

    return dark_targets

def gap_analysis(network_data, top_n=20):
    """Target-Compound 미탐색 영역 분석"""
    print("\n[3단계] Gap Analysis (미탐색 기회 분석)...")

    target_usage = network_data['target_usage']
    compound_usage = network_data['compound_usage']
    cooccurrence_matrix = network_data['cooccurrence_matrix']

    # 상위 N개 타겟과 화합물
    top_targets = sorted(target_usage.items(), key=lambda x: x[1], reverse=True)[:top_n]
    top_compounds = sorted(compound_usage.items(), key=lambda x: x[1], reverse=True)[:top_n]

    top_target_names = [t[0] for t in top_targets]
    top_compound_names = [c[0] for c in top_compounds]

    gaps = []

    for target in top_target_names:
        target_importance = target_usage[target]

        for compound in top_compound_names:
            cooccurrence = cooccurrence_matrix.get(target, {}).get(compound, 0)

            if cooccurrence == 0:  # 미탐색 쌍
                compound_importance = compound_usage[compound]
                gap_score = target_importance * compound_importance

                gaps.append({
                    'target': target,
                    'compound': compound,
                    'target_importance': target_importance,
                    'compound_importance': compound_importance,
                    'gap_score': gap_score
                })

    # Gap Score 기준 정렬
    gaps.sort(key=lambda x: x['gap_score'], reverse=True)

    print(f"✓ 발견된 미탐색 기회: {len(gaps)}개")
    print(f"✓ Top 10 Gap Analysis:")
    for i, gap in enumerate(gaps[:10], 1):
        print(f"  {i}. {gap['target']} + {gap['compound']}: gap_score={gap['gap_score']}")

    return gaps

def multi_target_synergy(network_data):
    """다중 타겟 시너지 감지"""
    print("\n[4단계] 다중 타겟 시너지 분석...")

    pathway_map = network_data['pathway_map']
    target_usage = network_data['target_usage']

    synergies = []
    targets = list(target_usage.keys())

    for i, target1 in enumerate(targets):
        for target2 in targets[i+1:]:
            pathways1 = pathway_map.get(target1, set())
            pathways2 = pathway_map.get(target2, set())

            shared_pathways = pathways1 & pathways2

            if shared_pathways:
                synergy_score = (
                    target_usage[target1] * target_usage[target2] * len(shared_pathways)
                )

                synergies.append({
                    'target1': target1,
                    'target2': target2,
                    'shared_pathways': list(shared_pathways),
                    'synergy_score': synergy_score
                })

    synergies.sort(key=lambda x: x['synergy_score'], reverse=True)

    print(f"✓ 발견된 시너지 쌍: {len(synergies)}개")
    print(f"✓ Top 5 시너지:")
    for i, syn in enumerate(synergies[:5], 1):
        print(f"  {i}. {syn['target1']} + {syn['target2']}: "
              f"synergy_score={syn['synergy_score']}, pathways={syn['shared_pathways']}")

    return synergies

def save_results(dark_targets, gaps, synergies, network_data):
    """결과를 파일로 저장합니다."""
    print("\n[5단계] 결과 저장...")

    # 1. intelligence_report.json
    intelligence_report = {
        'timestamp': datetime.now().isoformat(),
        'total_papers_analyzed': network_data['total_papers'],
        'dark_targets_count': len(dark_targets),
        'top_dark_targets': dark_targets[:20],
        'gap_analysis_count': len(gaps),
        'top_gaps': gaps[:30],
        'synergy_analysis_count': len(synergies),
        'top_synergies': synergies[:15],
        'summary': {
            'total_unique_targets': len(network_data['target_usage']),
            'total_unique_compounds': len(network_data['compound_usage']),
            'methodology': 'PMI-based network analysis with novelty scoring'
        }
    }

    report_path = os.path.join(OUTPUT_FOLDER, 'intelligence_report.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(intelligence_report, f, ensure_ascii=False, indent=2)
    print(f"✓ {report_path} 저장 완료")

    # 2. AGA_Dark_Targets.xlsx
    dark_df = pd.DataFrame(dark_targets)
    dark_xlsx_path = os.path.join(OUTPUT_FOLDER, 'AGA_Dark_Targets.xlsx')
    dark_df.to_excel(dark_xlsx_path, index=False, engine='openpyxl')
    print(f"✓ {dark_xlsx_path} 저장 완료")

    # 3. AGA_Gap_Analysis.xlsx
    gap_df = pd.DataFrame(gaps)
    gap_xlsx_path = os.path.join(OUTPUT_FOLDER, 'AGA_Gap_Analysis.xlsx')
    gap_df.to_excel(gap_xlsx_path, index=False, engine='openpyxl')
    print(f"✓ {gap_xlsx_path} 저장 완료")

    # 4. pipeline_status.json 업데이트
    status_path = os.path.join(OUTPUT_FOLDER, 'pipeline_status.json')
    if os.path.exists(status_path):
        with open(status_path, 'r', encoding='utf-8') as f:
            status = json.load(f)
    else:
        status = {}

    status['step_10_intelligent_analysis'] = {
        'completed': True,
        'timestamp': datetime.now().isoformat(),
        'dark_targets_identified': len(dark_targets),
        'gaps_identified': len(gaps),
        'synergies_identified': len(synergies)
    }

    with open(status_path, 'w', encoding='utf-8') as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
    print(f"✓ {status_path} 업데이트 완료")

def main():
    """메인 실행 함수"""
    print("=" * 60)
    print("10_지능형_패턴분석.py 시작")
    print("=" * 60)

    # 데이터 로드
    df = load_literature_data()
    if df is None:
        return

    # 네트워크 분석
    network_data = build_network_analysis(df)

    # Novelty Index 계산
    dark_targets = calculate_novelty_index(network_data)

    # Gap Analysis
    gaps = gap_analysis(network_data)

    # 다중 타겟 시너지
    synergies = multi_target_synergy(network_data)

    # 결과 저장
    save_results(dark_targets, gaps, synergies, network_data)

    print("\n" + "=" * 60)
    print("✓ 10_지능형_패턴분석.py 완료")
    print("=" * 60)

if __name__ == '__main__':
    main()
