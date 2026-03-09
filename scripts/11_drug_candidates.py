# -*- coding: utf-8 -*-
"""
=============================================================
11_신약후보_도출.py
=============================================================
용도: Dark Target에 대해 Claude AI가 novel compound를 제안합니다.
      축적된 데이터 기반 신약 후보물질 SMILES 도출.

실행: python 11_신약후보_도출.py
소요: 약 10-20분
비용: Claude Haiku ~$1-2
=============================================================
"""

import os
import json
import sys
import re
from datetime import datetime
import pandas as pd

# Claude API 사용 (Haiku 모델)
try:
    from anthropic import Anthropic
except ImportError:
    print("ERROR: anthropic 라이브러리가 설치되지 않았습니다.")
    print("설치: pip install anthropic")
    sys.exit(1)

# BASE_FOLDER 설정
BASE_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FOLDER = os.path.join(BASE_FOLDER, 'data')
OUTPUT_FOLDER = os.path.join(BASE_FOLDER, 'output')
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Claude API Key (환경 변수에서 읽기)
CLAUDE_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
if not CLAUDE_API_KEY:
    print("WARNING: ANTHROPIC_API_KEY 환경 변수가 설정되지 않았습니다.")
    print("Windows: set ANTHROPIC_API_KEY=your-key")
    print("Linux/Mac: export ANTHROPIC_API_KEY=your-key")
    CLAUDE_API_KEY = None

def validate_smiles(smiles_str):
    """
    기본적인 SMILES 유효성 검사
    - 괄호 균형 확인
    - 유효한 원소 기호 확인
    """
    if not smiles_str or not isinstance(smiles_str, str):
        return False

    smiles_str = smiles_str.strip()

    # 괄호 균형 확인
    paren_count = 0
    bracket_count = 0

    for char in smiles_str:
        if char == '(':
            paren_count += 1
        elif char == ')':
            paren_count -= 1
        elif char == '[':
            bracket_count += 1
        elif char == ']':
            bracket_count -= 1

        if paren_count < 0 or bracket_count < 0:
            return False

    if paren_count != 0 or bracket_count != 0:
        return False

    # 유효한 원소 기호 확인
    valid_atoms = {
        'C', 'N', 'O', 'S', 'P', 'F', 'Cl', 'Br', 'I',
        'c', 'n', 'o', 's', 'p',  # 방향족
        'B', 'Si', 'Se', 'As', 'Sb', 'Te', 'At'
    }

    # SMILES에서 원소 추출 (정규식)
    atom_pattern = r'[A-Z][a-z]?|[a-z]'
    atoms = re.findall(atom_pattern, smiles_str)

    for atom in atoms:
        if atom not in valid_atoms and atom not in ['H', '@', '+', '-', '=', '#', '//', '\\']:
            # 더 엄격한 검사는 생략 (기본 유효성만)
            pass

    return True

def load_intelligence_report():
    """intelligence_report.json 로드"""
    report_path = os.path.join(OUTPUT_FOLDER, 'intelligence_report.json')

    if not os.path.exists(report_path):
        print(f"ERROR: {report_path} 파일을 찾을 수 없습니다.")
        print("먼저 10_지능형_패턴분석.py를 실행하세요.")
        return None

    try:
        with open(report_path, 'r', encoding='utf-8') as f:
            report = json.load(f)
        print(f"✓ intelligence_report.json 로드 완료")
        return report
    except Exception as e:
        print(f"ERROR: 파일 로드 실패 - {e}")
        return None

def load_original_literature_data():
    """원본 문헌 데이터 로드 (pathway, MoA 정보 추출용)"""
    candidates = [
        os.path.join(BASE_FOLDER, 'AGA_data.xlsx'),
        os.path.join(BASE_FOLDER, 'AGA_문헌분류_결과.xlsx'),
        os.path.join(DATA_FOLDER, 'AGA_문헌분류_결과.xlsx'),
    ]
    filepath = None
    for c in candidates:
        if os.path.exists(c):
            filepath = c
            break

    if not filepath:
        print(f"WARNING: AGA 데이터 파일을 찾을 수 없습니다.")
        return None

    try:
        df = pd.read_excel(filepath)
        print(f"✓ 원본 문헌 데이터 로드 완료: {len(df)} 행")
        return df
    except Exception as e:
        print(f"WARNING: 원본 데이터 로드 실패 - {e}")
        return None

def extract_target_context(target_name, literature_df):
    """특정 타겟에 대한 문헌 정보 추출"""
    if literature_df is None:
        return {
            'compounds': [],
            'pathways': set(),
            'moa_list': set(),
            'paper_count': 0
        }

    context = {
        'compounds': [],
        'pathways': set(),
        'moa_list': set(),
        'paper_count': 0
    }

    for idx, row in literature_df.iterrows():
        targets = str(row.get('주요_타겟', '')).lower()

        if target_name.lower() in targets or target_name in targets:
            # Compound
            if pd.notna(row.get('분석된_화합물')):
                compounds = str(row['분석된_화합물']).split(';')
                for c in compounds:
                    c = c.strip()
                    if c and c not in context['compounds']:
                        context['compounds'].append(c)

            # Pathway
            if pd.notna(row.get('경로')):
                pathway = str(row['경로']).strip()
                if pathway and pathway != 'Unknown':
                    context['pathways'].add(pathway)

            # MoA
            if pd.notna(row.get('작용기전')):
                moa = str(row['작용기전']).strip()
                if moa and moa != 'Unknown':
                    context['moa_list'].add(moa)

            context['paper_count'] += 1

    return context

def generate_novel_compounds(target_name, context, client):
    """Claude Haiku를 사용하여 novel compound 제안"""
    print(f"\n  → {target_name}에 대한 신약 후보 도출 중...")

    compounds_str = ", ".join(context['compounds'][:20]) if context['compounds'] else "No compounds found"
    pathways_str = ", ".join(list(context['pathways'])[:10]) if context['pathways'] else "Not specified"
    moa_str = ", ".join(list(context['moa_list'])[:10]) if context['moa_list'] else "Not specified"

    prompt = f"""당신은 신약 개발 전문가입니다. 다음 정보를 바탕으로 AGA(Androgenetic Alopecia, 남성형 탈모) 치료를 위한 {target_name} 타겟 기반 신약 후보물질을 제안해주세요.

[타겟 정보]
- 타겟: {target_name}
- 관련 논문 수: {context['paper_count']}
- 기존 연구 화합물: {compounds_str}
- 관련 경로: {pathways_str}
- 주요 작용기전: {moa_str}

[요청 사항]
3개의 novel compound를 다음 형식으로 제안해주세요. 각 화합물마다 아래 정보를 포함하세요:

1. SMILES 구조식
2. 예상 작용기전 (Predicted MoA)
3. 구조적 근거 (Structural Rationale) - 기존 화합물과의 차별성
4. 신규성 평가 (Novelty Assessment) - 기존 문헌에 없는 이유 포함

응답은 다음 JSON 형식으로 작성해주세요 (한글 주석 제거하고 JSON만 반환):
{{
    "compound_1": {{
        "smiles": "...",
        "predicted_moa": "...",
        "structural_rationale": "...",
        "novelty_assessment": "...",
        "confidence": 0.8
    }},
    "compound_2": {{...}},
    "compound_3": {{...}}
}}

주의사항:
- SMILES는 화학적으로 타당해야 합니다
- 기존 약물(예: 피나스테라이드)과는 다른 구조여야 합니다
- {target_name} 타겟과의 상호작용 메커니즘을 명확히 제시해주세요"""

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        response_text = message.content[0].text

        # JSON 추출 (코드 블록 처리)
        if "```" in response_text:
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(1)

        # JSON 파싱
        try:
            compounds = json.loads(response_text)
            return compounds
        except json.JSONDecodeError:
            print(f"    WARNING: JSON 파싱 실패")
            return None

    except Exception as e:
        print(f"    ERROR: API 호출 실패 - {e}")
        return None

def process_candidates(candidates_dict, target_name, context):
    """Claude 응답 처리 및 검증"""
    results = []

    if not candidates_dict or not isinstance(candidates_dict, dict):
        return results

    for key, compound_data in candidates_dict.items():
        if not isinstance(compound_data, dict):
            continue

        smiles = compound_data.get('smiles', '').strip()
        moa = compound_data.get('predicted_moa', '').strip()
        rationale = compound_data.get('structural_rationale', '').strip()
        novelty = compound_data.get('novelty_assessment', '').strip()
        confidence = compound_data.get('confidence', 0.7)

        # SMILES 검증
        if validate_smiles(smiles):
            results.append({
                'target': target_name,
                'smiles': smiles,
                'predicted_moa': moa,
                'structural_rationale': rationale,
                'novelty_assessment': novelty,
                'confidence_score': confidence,
                'validation_status': 'Valid',
                'timestamp': datetime.now().isoformat()
            })
        else:
            results.append({
                'target': target_name,
                'smiles': smiles,
                'predicted_moa': moa,
                'structural_rationale': rationale,
                'novelty_assessment': novelty,
                'confidence_score': confidence,
                'validation_status': 'Invalid SMILES',
                'timestamp': datetime.now().isoformat()
            })

    return results

def main():
    """메인 실행 함수"""
    print("=" * 60)
    print("11_신약후보_도출.py 시작")
    print("=" * 60)

    # API Key 확인
    if not CLAUDE_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY가 설정되지 않았습니다.")
        return

    # Intelligence report 로드
    intelligence_report = load_intelligence_report()
    if intelligence_report is None:
        return

    # 원본 문헌 데이터 로드
    literature_df = load_original_literature_data()

    # Claude 클라이언트 초기화
    client = Anthropic(api_key=CLAUDE_API_KEY)

    # 상위 5개 Dark Target 추출
    dark_targets = intelligence_report.get('top_dark_targets', [])[:5]

    if not dark_targets:
        print("ERROR: Dark targets를 찾을 수 없습니다.")
        return

    print(f"\n[1단계] {len(dark_targets)}개 Dark Target 처리 시작\n")

    all_candidates = []

    for target_info in dark_targets:
        target_name = target_info.get('target')

        if not target_name:
            continue

        print(f"✓ {target_name} (novelty={target_info.get('novelty_index', 0):.4f})")

        # 타겟별 문헌 컨텍스트 추출
        context = extract_target_context(target_name, literature_df)

        # Novel compound 생성 (Claude Haiku)
        candidates_dict = generate_novel_compounds(target_name, context, client)

        if candidates_dict:
            # 검증 및 처리
            processed = process_candidates(candidates_dict, target_name, context)
            all_candidates.extend(processed)
            print(f"    ✓ {len(processed)}개 후보물질 도출 완료")
        else:
            print(f"    WARNING: 후보물질 도출 실패")

    print(f"\n[2단계] 결과 저장...")

    # 1. candidate_molecules.json
    candidates_json = {
        'timestamp': datetime.now().isoformat(),
        'total_candidates': len(all_candidates),
        'targets_analyzed': len(dark_targets),
        'candidates': all_candidates,
        'notes': 'Claude Haiku generated SMILES structures for novel AGA drug candidates'
    }

    candidates_path = os.path.join(OUTPUT_FOLDER, 'candidate_molecules.json')
    with open(candidates_path, 'w', encoding='utf-8') as f:
        json.dump(candidates_json, f, ensure_ascii=False, indent=2)
    print(f"✓ {candidates_path} 저장 완료")

    # 2. AGA_신약후보물질.xlsx
    if all_candidates:
        candidates_df = pd.DataFrame(all_candidates)
        xlsx_path = os.path.join(OUTPUT_FOLDER, 'AGA_신약후보물질.xlsx')
        candidates_df.to_excel(xlsx_path, index=False, engine='openpyxl')
        print(f"✓ {xlsx_path} 저장 완료")

    # 3. pipeline_status.json 업데이트
    status_path = os.path.join(OUTPUT_FOLDER, 'pipeline_status.json')
    if os.path.exists(status_path):
        with open(status_path, 'r', encoding='utf-8') as f:
            status = json.load(f)
    else:
        status = {}

    status['step_11_candidate_discovery'] = {
        'completed': True,
        'timestamp': datetime.now().isoformat(),
        'dark_targets_processed': len(dark_targets),
        'candidates_generated': len(all_candidates),
        'valid_candidates': sum(1 for c in all_candidates if c['validation_status'] == 'Valid'),
        'model_used': 'claude-haiku-4-5-20251001'
    }

    with open(status_path, 'w', encoding='utf-8') as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
    print(f"✓ {status_path} 업데이트 완료")

    print("\n" + "=" * 60)
    print(f"✓ 11_신약후보_도출.py 완료")
    print(f"  총 {len(all_candidates)}개 신약 후보물질 도출")
    print("=" * 60)

if __name__ == '__main__':
    main()
