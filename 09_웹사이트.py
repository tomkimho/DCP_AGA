"""
=============================================================
09_웹사이트.py - AGA Drug Discovery Knowledge Platform
=============================================================
용도: 709건 논문 분석 결과를 웹 플랫폼으로 제공
      타겟 발굴, 화합물 탐색, Target-Compound 매트릭스,
      AI 기반 질의응답, 보고서 자동 생성 기능

실행 방법:
  1. pip install streamlit plotly anthropic openpyxl
  2. streamlit run 09_웹사이트.py
=============================================================
"""

import streamlit as st
import pandas as pd
import os
import sys
import re
import io
import json
from collections import Counter
from datetime import datetime

# Windows 인코딩 문제 해결
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ─── 설정 ────────────────────────────────────────────────
EXCEL_NAMES = ["AGA_data.xlsx", "AGA_문헌분류_결과.xlsx"]

# 여러 경로에서 엑셀 파일 찾기 (로컬 + 클라우드 모두 지원)
_script_dir = os.path.dirname(os.path.abspath(__file__))
_search_dirs = [
    os.path.dirname(_script_dir),   # 로컬: scripts의 상위 폴더
    _script_dir,                      # 같은 폴더 (scripts/)
    os.getcwd(),                      # 현재 작업 디렉토리 (Streamlit Cloud)
    "/mount/src/dcp_aga",             # Streamlit Cloud 기본 마운트 경로
    "/app",                           # Streamlit Cloud 대안 경로
]
# 중복 제거
_search_dirs = list(dict.fromkeys(_search_dirs))

EXCEL_PATH = None
EXCEL_PATHS = []  # 발견된 모든 엑셀 파일(두 개 모두 로드)
BASE_FOLDER = _search_dirs[0]
for d in _search_dirs:
    if not os.path.isdir(d):
        continue
    for name in EXCEL_NAMES:
        candidate = os.path.join(d, name)
        if os.path.exists(candidate) and candidate not in EXCEL_PATHS:
            EXCEL_PATHS.append(candidate)
            if EXCEL_PATH is None:
                EXCEL_PATH = candidate
                BASE_FOLDER = d
    if EXCEL_PATHS:
        break

if EXCEL_PATH is None:
    # 디버그 정보 표시 (배포 시 문제 진단용)
    import streamlit as _st_debug
    _st_debug.error("데이터 파일을 찾을 수 없습니다.")
    _st_debug.code(f"검색한 디렉토리:\n" + "\n".join(
        f"  {d} -> {'EXISTS' if os.path.isdir(d) else 'NOT FOUND'}" +
        (f"\n    files: {os.listdir(d)[:10]}" if os.path.isdir(d) else "")
        for d in _search_dirs
    ))
    EXCEL_PATH = os.path.join(_search_dirs[0], EXCEL_NAMES[0])

TXT_FOLDER = os.path.join(BASE_FOLDER, "txt_추출결과")

# Claude API 키 (Streamlit Cloud 배포 시 secrets에서 / 로컬에서는 02_info_extract.py에서 가져옴)
def load_api_key():
    # 1순위: Streamlit secrets (배포용)
    try:
        return st.secrets["CLAUDE_API_KEY"]
    except Exception:
        pass
    # 2순위: 로컬 파일에서 읽기
    script_path = os.path.join(BASE_FOLDER, "scripts", "02_info_extract.py")
    if os.path.exists(script_path):
        with open(script_path, "r", encoding="utf-8") as f:
            content = f.read()
        match = re.search(r'CLAUDE_API_KEY\s*=\s*"([^"]+)"', content)
        if match:
            return match.group(1)
    return ""

CLAUDE_API_KEY = load_api_key()
# ─────────────────────────────────────────────────────────


# ============================================================
# 페이지 설정
# ============================================================
st.set_page_config(
    page_title="AGA Drug Discovery Platform",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# 타겟 이름 정규화 (중복 통합)
# ============================================================
TARGET_NORMALIZE = {
    "Androgen Receptor (AR)": "Androgen Receptor",
    "Androgen receptor": "Androgen Receptor",
    "androgen receptor": "Androgen Receptor",
    "AR": "Androgen Receptor",
    "5-alpha reductase": "5α-Reductase",
    "5-alpha Reductase": "5α-Reductase",
    "5-Alpha Reductase": "5α-Reductase",
    "5α-Reductase Type 2": "5α-Reductase Type II",
    "SRD5A2 (5-alpha reductase type 2)": "5α-Reductase Type II",
    "SRD5A2": "5α-Reductase Type II",
    "Wnt/β-catenin pathway": "Wnt/β-catenin",
    "Wnt/β-catenin signaling": "Wnt/β-catenin",
    "Wnt/β-catenin signaling pathway": "Wnt/β-catenin",
    "Wnt/beta-catenin": "Wnt/β-catenin",
    "Hair follicle stem cells": "Hair Follicle Stem Cells",
    "Dermal papilla cells": "Dermal Papilla Cells",
    "Dermal Papilla Cells (DPC)": "Dermal Papilla Cells",
}

def normalize_target(name):
    name = name.strip()
    return TARGET_NORMALIZE.get(name, name)


# ============================================================
# 데이터 로딩 및 전처리
# ============================================================
@st.cache_data
def load_data():
    # 발견된 모든 엑셀 파일(AGA_data.xlsx + AGA_문헌분류_결과.xlsx) 병합
    paths = EXCEL_PATHS if EXCEL_PATHS else ([EXCEL_PATH] if EXCEL_PATH and os.path.exists(EXCEL_PATH) else [])
    if not paths:
        return None
    dfs = []
    for p in paths:
        try:
            dfs.append(pd.read_excel(p))
        except Exception:
            continue
    if not dfs:
        return None
    df = pd.concat(dfs, ignore_index=True)
    # 파일명 기준 중복 제거(동일 논문이 두 파일에 모두 있는 경우)
    if "파일명" in df.columns:
        df = df.drop_duplicates(subset=["파일명"], keep="first").reset_index(drop=True)
    # 관련도를 숫자로 변환
    df["관련도"] = pd.to_numeric(df.get("관련도(1-5)"), errors="coerce").fillna(0).astype(int)
    return df


@st.cache_data
def build_target_index(df):
    """타겟별 인덱스 구축"""
    target_map = {}
    for idx, row in df.iterrows():
        targets = str(row.get("타겟(Target)", ""))
        if targets == "nan":
            continue
        for t in targets.split(","):
            t = normalize_target(t)
            if len(t) > 1:
                if t not in target_map:
                    target_map[t] = []
                target_map[t].append(idx)
    return target_map


@st.cache_data
def build_compound_index(df):
    """화합물별 인덱스 구축"""
    compound_map = {}
    for idx, row in df.iterrows():
        compounds = str(row.get("화합물(Compound)", ""))
        if compounds == "nan":
            continue
        for c in compounds.split(","):
            c = c.strip()
            if len(c) > 1:
                if c not in compound_map:
                    compound_map[c] = []
                compound_map[c].append(idx)
    return compound_map


def get_top_items(df, column, top_n=20, normalize_fn=None):
    """컬럼에서 상위 항목 추출"""
    counter = Counter()
    for val in df[column].dropna():
        for item in str(val).split(","):
            item = item.strip()
            if normalize_fn:
                item = normalize_fn(item)
            if len(item) > 1:
                counter[item] += 1
    return counter.most_common(top_n)


# ============================================================
# 화합물 구조 데이터 로딩
# ============================================================
@st.cache_data
def load_structures():
    """compound_structures.json 로딩"""
    for d in _search_dirs:
        candidate = os.path.join(d, "compound_structures.json")
        if os.path.exists(candidate):
            with open(candidate, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {item["name"]: item for item in data if item.get("status") == "found"}
    return {}


@st.cache_data
def load_natural_products():
    """natural_product_actives.json 로딩"""
    for d in _search_dirs:
        candidate = os.path.join(d, "natural_product_actives.json")
        if os.path.exists(candidate):
            with open(candidate, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
    return {}


# ============================================================
# 데이터 로딩
# ============================================================
df = load_data()

if df is None:
    st.error("데이터가 없습니다. 02_info_extract.py를 먼저 실행하세요.")
    st.stop()

target_index = build_target_index(df)
compound_index = build_compound_index(df)
structures = load_structures()
np_data = load_natural_products()

# 성공 데이터만 사용
df_ok = df[df["처리상태"] == "성공"].copy()

# KB 벡터 수 동적 로드
def _kb_vector_count():
    try:
        meta_path = os.path.join(BASE_FOLDER, "aga_knowledge_db", "metadata.json")
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                m = json.load(f)
            return int(m.get("total_chunks", 0))
    except Exception:
        pass
    return 0

_kb_vec = _kb_vector_count()
_kb_vec_label = f"{_kb_vec/1000:.0f}K+ vectors" if _kb_vec >= 1000 else "vectors"


# ============================================================
# 헤더
# ============================================================
st.markdown("""
<div style='background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
     padding: 20px 30px; border-radius: 12px; margin-bottom: 20px;'>
    <h1 style='color: #e94560; margin:0; font-size: 28px;'>🧬 AGA Drug Discovery Platform</h1>
    <p style='color: #a8a8a8; margin: 5px 0 0 0; font-size: 14px;'>
        Androgenetic Alopecia 신약개발 문헌 데이터베이스 &nbsp;|&nbsp;
        {total:,}건 논문 분석 완료 &nbsp;|&nbsp; RAG AI Expert ({kbvec}) &nbsp;|&nbsp; Lab-in-the-loop 기반
    </p>
</div>
""".format(total=len(df_ok), kbvec=_kb_vec_label), unsafe_allow_html=True)


# ============================================================
# 사이드바: 글로벌 필터
# ============================================================
with st.sidebar:
    # 필터 전체를 접을 수 있는 익스팬더로 감싸기 (기본: 펼침)
    with st.expander("🔍 필터", expanded=True):
        # 연구 유형
        study_types = sorted(df_ok["연구유형"].dropna().unique().tolist())
        with st.expander("연구 유형", expanded=False):
            selected_studies = st.multiselect(
                "연구 유형", study_types, default=study_types,
                label_visibility="collapsed"
            )

        # 문서 유형
        doc_types = sorted(df_ok["문서유형"].dropna().unique().tolist())
        with st.expander("문서 유형", expanded=False):
            selected_docs = st.multiselect(
                "문서 유형", doc_types, default=doc_types,
                label_visibility="collapsed"
            )

        # 관련도
        with st.expander("최소 관련도", expanded=False):
            min_rel = st.slider("최소 관련도", 1, 5, 1, label_visibility="collapsed")

        # 키워드 필터
        with st.expander("키워드 필터", expanded=False):
            keyword_filter = st.text_input(
                "키워드 필터",
                placeholder="예: Wnt, minoxidil, DHT...",
                label_visibility="collapsed"
            )

    st.markdown("---")

    # 필터 적용
    filtered = df_ok.copy()
    filtered = filtered[filtered["연구유형"].isin(selected_studies)]
    filtered = filtered[filtered["문서유형"].isin(selected_docs)]
    filtered = filtered[filtered["관련도"] >= min_rel]

    if keyword_filter:
        mask = filtered.apply(
            lambda row: keyword_filter.lower() in str(row.values).lower(), axis=1
        )
        filtered = filtered[mask]

    st.metric("검색 결과", f"{len(filtered)} / {len(df_ok)}건")
    st.caption(f"마지막 업데이트: {datetime.now().strftime('%Y-%m-%d')}")


# ============================================================
# AGA 주요 타겟 PDB 매핑 (3D 구조 시각화용)
# ============================================================
AGA_TARGET_PDB = {
    "Androgen Receptor (AR)": {"pdb": "1E3G", "uniprot": "P10275",
        "desc": "Androgen Receptor - DHT 결합으로 탈모 유발 핵심 타겟",
        "binding_residues": "L704,N705,R752,F764,M780,T877"},
    "5α-Reductase Type II (SRD5A2)": {"pdb": "7BW1", "uniprot": "P31213",
        "desc": "Steroid 5-alpha Reductase 2 - Testosterone→DHT 변환 효소",
        "binding_residues": "L20,G22,F118,Y91,E57,N160,R171"},
    "Wnt/β-catenin (CTNNB1)": {"pdb": "1JDH", "uniprot": "P35222",
        "desc": "β-Catenin - 모낭 줄기세포 활성화 및 모발 재생 핵심 경로",
        "binding_residues": "K312,K345,R376,R386,N387,N426"},
    "JAK1/2": {"pdb": "6BBU", "uniprot": "P23458",
        "desc": "Janus Kinase 1/2 - JAK-STAT 면역/염증 신호전달",
        "binding_residues": "L881,G884,V889,A906,K908,E925,L959"},
    "STAT3": {"pdb": "6NJS", "uniprot": "P40763",
        "desc": "Signal Transducer and Activator of Transcription 3",
        "binding_residues": "R609,S611,S613,E612,T620"},
    "PTGDR2 (PGD2 receptor)": {"pdb": "6OIK", "uniprot": "Q9Y5Y4",
        "desc": "Prostaglandin D2 Receptor 2 - 모낭 퇴행 유도",
        "binding_residues": "R106,T185,Y186,K210,E268"},
    "VEGFA/VEGFR": {"pdb": "1FLT", "uniprot": "P15692",
        "desc": "Vascular Endothelial Growth Factor A - 모유두 혈관신생",
        "binding_residues": "C26,R46,E64,K84,N85"},
    "IGF-1/IGF-1R": {"pdb": "1IMX", "uniprot": "P05019",
        "desc": "Insulin-like Growth Factor 1 - 모발 성장 촉진 인자",
        "binding_residues": "G1,P2,E3,T4,L5,C6"},
    "SHH (Sonic Hedgehog)": {"pdb": "3N1G", "uniprot": "Q15465",
        "desc": "Sonic Hedgehog - 모낭 형태형성 및 재생 신호",
        "binding_residues": "H134,D147,H180,E176"},
    "TGF-β1": {"pdb": "3KFD", "uniprot": "P01137",
        "desc": "Transforming Growth Factor Beta 1 - 모낭 퇴행(catagen) 유도",
        "binding_residues": "R25,K26,W32,L45,V77,A84"},
    "BMP2/4": {"pdb": "3BMP", "uniprot": "P12643",
        "desc": "Bone Morphogenetic Protein 2/4 - 모낭 휴지기 유지",
        "binding_residues": "W28,F41,H54,D53,S57,L51"},
    "DKK1": {"pdb": "3S2K", "uniprot": "O94907",
        "desc": "Dickkopf-1 - Wnt 길항제, 모낭 축소(miniaturization) 촉진",
        "binding_residues": "H204,S205,F207,R236,E243"},
    "IL-6": {"pdb": "1ALU", "uniprot": "P05231",
        "desc": "Interleukin-6 - 모낭 주위 염증 매개 사이토카인",
        "binding_residues": "R24,Q28,Y31,D34,S118,R179"},
    "TNF-α": {"pdb": "1TNF", "uniprot": "P01375",
        "desc": "Tumor Necrosis Factor Alpha - 모발 성장 억제 염증인자",
        "binding_residues": "Y59,S60,Y119,L120,G121,Y151"},
    "FGF7 (KGF)": {"pdb": "1QQK", "uniprot": "P21781",
        "desc": "Fibroblast Growth Factor 7 (KGF) - 모낭 상피세포 성장 촉진",
        "binding_residues": "K18,R19,K127,R135,K138,K143"},
}

# AGA 화합물-타겟 결합 매핑
AGA_COMPOUND_TARGET_MAP = {
    "Finasteride": {"targets": ["5α-Reductase Type II (SRD5A2)"], "type": "Small molecule",
        "moa": "5α-Reductase Type II 경쟁적 억제제 - DHT 생성 차단",
        "indication": "AGA (남성형 탈모), BPH",
        "phase": "Approved (1mg Propecia)",
        "pubchem_cid": "57363", "smiles": "CC12CCC3C(C1CCC2C(=O)NC)C=CC4NC(=O)C=CC34",
        "binding_sites": {"5α-Reductase Type II (SRD5A2)": "L20,G22,F118,Y91"}},
    "Dutasteride": {"targets": ["5α-Reductase Type II (SRD5A2)"], "type": "Small molecule",
        "moa": "5α-Reductase Type I/II 이중 억제제 - DHT 강력 차단",
        "indication": "AGA (남성형 탈모), BPH",
        "phase": "Approved (0.5mg Avodart)",
        "pubchem_cid": "6918296", "smiles": "CC12CCC3C(C1CCC2C(=O)NC)CCC4NC(=O)C(=C34)C(F)(F)C5=CC(=CC=C5)CF",
        "binding_sites": {"5α-Reductase Type II (SRD5A2)": "L20,G22,E57,N160"}},
    "Minoxidil": {"targets": ["VEGFA/VEGFR"], "type": "Small molecule",
        "moa": "KATP 채널 개방 - 모유두 혈류 증가 및 VEGF 발현 유도",
        "indication": "AGA (남성형/여성형 탈모)",
        "phase": "Approved (2%/5% topical)",
        "pubchem_cid": "4201", "smiles": "NC1=NC(=CC(N)=N1)N1CCCCC1",
        "binding_sites": {"VEGFA/VEGFR": "C26,R46,E64"}},
    "Ruxolitinib": {"targets": ["JAK1/2"], "type": "Small molecule",
        "moa": "JAK1/2 선택적 억제제 - 면역 매개 탈모 차단",
        "indication": "Alopecia Areata, AGA (연구중)",
        "phase": "Approved (AA) / Phase 2 (AGA)",
        "pubchem_cid": "25126798", "smiles": "N#CC1=CC=C(C=C1)C1=NC(=NC=C1)NC1CC1C1CCCC=C1",
        "binding_sites": {"JAK1/2": "L881,V889,A906,K908"}},
    "Tofacitinib": {"targets": ["JAK1/2"], "type": "Small molecule",
        "moa": "Pan-JAK 억제제 - JAK-STAT 경로 차단",
        "indication": "Alopecia Areata, RA",
        "phase": "Approved (AA/RA)",
        "pubchem_cid": "9926791", "smiles": "CC1CCN(CC1NC(=O)C1=NC=CC(=N1)N)C(=O)CC#N",
        "binding_sites": {"JAK1/2": "L881,G884,E925,L959"}},
    "Setipiprant": {"targets": ["PTGDR2 (PGD2 receptor)"], "type": "Small molecule",
        "moa": "PTGDR2 (CRTh2) 길항제 - PGD2 매개 모낭 퇴행 차단",
        "indication": "AGA (Phase 2)",
        "phase": "Phase 2",
        "pubchem_cid": "11549559",
        "binding_sites": {"PTGDR2 (PGD2 receptor)": "R106,T185,Y186"}},
    "Valproic acid": {"targets": ["Wnt/β-catenin (CTNNB1)"], "type": "Small molecule",
        "moa": "HDAC 억제 + Wnt/β-catenin 활성화 - 모낭 줄기세포 촉진",
        "indication": "AGA (전임상)",
        "phase": "Preclinical (AGA)",
        "pubchem_cid": "3121", "smiles": "CCCC(CCC)C(=O)O",
        "binding_sites": {"Wnt/β-catenin (CTNNB1)": "K312,K345,R376"}},
    "Bimatoprost": {"targets": ["VEGFA/VEGFR"], "type": "Small molecule",
        "moa": "Prostaglandin F2α 유사체 - 모발 성장기(anagen) 연장",
        "indication": "Eyelash hypotrichosis, AGA (연구중)",
        "phase": "Approved (eyelash) / Phase 2 (AGA)",
        "pubchem_cid": "5311027",
        "binding_sites": {"VEGFA/VEGFR": "R46,K84,N85"}},
    "CXXC5-Dvl PPI inhibitor": {"targets": ["Wnt/β-catenin (CTNNB1)", "DKK1"], "type": "Small molecule",
        "moa": "CXXC5-Dvl 상호작용 차단 - Wnt/β-catenin 활성화",
        "indication": "AGA (전임상, 연세대/서울대 연구)",
        "phase": "Preclinical",
        "pubchem_cid": None,
        "binding_sites": {"Wnt/β-catenin (CTNNB1)": "R386,N387,N426", "DKK1": "H204,S205,F207"}},
    "Cetirizine": {"targets": ["PTGDR2 (PGD2 receptor)"], "type": "Small molecule",
        "moa": "H1 항히스타민 + PGD2 경로 간접 억제",
        "indication": "AGA (topical, off-label)",
        "phase": "Off-label / Phase 2",
        "pubchem_cid": "2678", "smiles": "OC(=O)COCCN1CCN(CC1)C(C1=CC=CC=C1)C1=CC=C(Cl)C=C1",
        "binding_sites": {"PTGDR2 (PGD2 receptor)": "K210,E268"}},
}

# ============================================================
# 탭 구성
# ============================================================
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11, tab12, tab13, tab14 = st.tabs([
    "📊 대시보드",
    "📋 문헌 검색",
    "🎯 타겟 분석",
    "💊 화합물 분석",
    "🔗 Target-Compound 매트릭스",
    "🧫 3D CPI Binding",
    "🤖 AI 질의응답",
    "🔬 Dark Targets",
    "💡 AI 신약 후보",
    "🧬 바이오마커",
    "📈 연구 동향",
    "⚡ AGA-성기능장애 공동타겟",
    "🏢 Control Center",
    "🎯 자체 타깃 검증",
])


# ============================================================
# 탭 1: 대시보드
# ============================================================
with tab1:
    import plotly.express as px
    import plotly.graph_objects as go

    # ─── Knowledge Base 통계 로드 ──────────────────
    _kb_meta = {}
    for _kb_dir in [os.path.join(BASE_FOLDER, "aga_knowledge_db")]:
        _kb_meta_path = os.path.join(_kb_dir, "metadata.json")
        if os.path.exists(_kb_meta_path):
            with open(_kb_meta_path, "r", encoding="utf-8") as _f:
                _kb_meta = json.load(_f)
            break

    # 논문 카운트: 로컬 디렉토리 우선, 없으면 metadata.json 사용 (Streamlit Cloud)
    _txt_dirs = [
        os.path.join(BASE_FOLDER, "new_papers_txt"),
        os.path.join(BASE_FOLDER, "txt_추출결과"),
        os.path.join(BASE_FOLDER, "성기능장애", "txt"),
    ]
    _pdf_dirs = [
        os.path.join(BASE_FOLDER, "new_papers"),
        os.path.join(BASE_FOLDER, "성기능장애", "pdf"),
    ]
    _local_txt_count = sum(
        sum(1 for f in files if f.endswith('.txt'))
        for d in _txt_dirs if os.path.isdir(d)
        for _, _, files in os.walk(d)
    )
    _local_pdf_count = sum(
        sum(1 for f in files if f.endswith('.pdf'))
        for d in _pdf_dirs if os.path.isdir(d)
        for _, _, files in os.walk(d)
    )
    # Streamlit Cloud에서는 디렉토리가 없으므로 metadata.json 사용
    _new_papers_count = _local_txt_count if _local_txt_count > 0 else _kb_meta.get("text_files", 0)
    _new_pdf_count = _local_pdf_count if _local_pdf_count > 0 else _kb_meta.get("pdf_files", 10281)

    # ─── 데이터 성장 배너 ──────────────────────────
    _initial_papers = 709  # 초기 구축 시 논문 수
    _current_structured = len(df_ok)
    _growth_pct = round((_new_papers_count / _initial_papers - 1) * 100, 1) if _initial_papers > 0 and _new_papers_count > 0 else 0

    st.markdown(f"""
    <div style='background: linear-gradient(135deg, #0d1117 0%, #161b22 50%, #1a2332 100%);
         padding: 16px 24px; border-radius: 10px; margin-bottom: 16px;
         border-left: 4px solid #58a6ff;'>
        <div style='display: flex; justify-content: space-between; align-items: center;'>
            <div>
                <span style='color: #58a6ff; font-size: 13px; font-weight: 600;'>DATA GROWTH</span>
                <span style='color: #8b949e; font-size: 12px; margin-left: 12px;'>
                    Initial: {_initial_papers} papers &rarr; Current: {_new_papers_count:,} papers
                    ({'+' if _growth_pct > 0 else ''}{_growth_pct}%)
                </span>
            </div>
            <div style='color: #3fb950; font-size: 14px; font-weight: 600;'>
                +{_new_papers_count - _initial_papers:,} papers added
            </div>
        </div>
        <div style='margin-top: 10px; display: flex; gap: 32px;'>
            <div style='text-align: center;'>
                <div style='color: #e6edf3; font-size: 22px; font-weight: 700;'>{_current_structured:,}</div>
                <div style='color: #8b949e; font-size: 11px;'>AI Analyzed</div>
            </div>
            <div style='text-align: center;'>
                <div style='color: #e6edf3; font-size: 22px; font-weight: 700;'>{_new_papers_count:,}</div>
                <div style='color: #8b949e; font-size: 11px;'>Total Papers</div>
            </div>
            <div style='text-align: center;'>
                <div style='color: #e6edf3; font-size: 22px; font-weight: 700;'>{_new_pdf_count:,}</div>
                <div style='color: #8b949e; font-size: 11px;'>Full-text PDFs</div>
            </div>
            <div style='text-align: center;'>
                <div style='color: #e6edf3; font-size: 22px; font-weight: 700;'>{_kb_meta.get("total_chunks", 0):,}</div>
                <div style='color: #8b949e; font-size: 11px;'>KB Vectors</div>
            </div>
            <div style='text-align: center;'>
                <div style='color: #e6edf3; font-size: 22px; font-weight: 700;'>20</div>
                <div style='color: #8b949e; font-size: 11px;'>Target Genes</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 상단 KPI
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("총 문헌 (분석완료)", f"{len(df_ok)}")
    c2.metric("논문", f"{len(df_ok[df_ok['문서유형']=='Paper'])}")
    c3.metric("특허", f"{len(df_ok[df_ok['문서유형']=='Patent'])}")
    c4.metric("고유 타겟", f"{len(target_index)}")
    c5.metric("고유 화합물", f"{len(compound_index)}")

    st.markdown("---")

    col_l, col_r = st.columns(2)

    with col_l:
        # 연구유형 파이차트
        study_dist = df_ok["연구유형"].value_counts().reset_index()
        study_dist.columns = ["연구유형", "건수"]
        fig1 = px.pie(study_dist, values="건수", names="연구유형",
                      title="연구 유형 분포", hole=0.4,
                      color_discrete_sequence=px.colors.qualitative.Set2)
        fig1.update_layout(height=350, margin=dict(t=40, b=20, l=20, r=20))
        st.plotly_chart(fig1, use_container_width=True)

    with col_r:
        # 관련도 분포
        rel_dist = df_ok["관련도"].value_counts().sort_index().reset_index()
        rel_dist.columns = ["관련도 점수", "건수"]
        fig2 = px.bar(rel_dist, x="관련도 점수", y="건수",
                      title="관련도 점수 분포",
                      color="건수", color_continuous_scale="Reds")
        fig2.update_layout(height=350, margin=dict(t=40, b=20, l=20, r=20))
        st.plotly_chart(fig2, use_container_width=True)

    # Top 타겟 바 차트
    top_targets = get_top_items(df_ok, "타겟(Target)", 15, normalize_target)
    if top_targets:
        tgt_df = pd.DataFrame(top_targets, columns=["타겟", "논문수"])
        fig3 = px.bar(tgt_df, x="논문수", y="타겟", orientation="h",
                      title="Top 15 Drug Targets",
                      color="논문수", color_continuous_scale="Blues")
        fig3.update_layout(height=450, yaxis=dict(autorange="reversed"),
                          margin=dict(t=40, b=20, l=20, r=20))
        st.plotly_chart(fig3, use_container_width=True)

    # Top 화합물 바 차트
    top_compounds = get_top_items(df_ok, "화합물(Compound)", 15)
    if top_compounds:
        comp_df = pd.DataFrame(top_compounds, columns=["화합물", "논문수"])
        fig4 = px.bar(comp_df, x="논문수", y="화합물", orientation="h",
                      title="Top 15 Compounds",
                      color="논문수", color_continuous_scale="Greens")
        fig4.update_layout(height=450, yaxis=dict(autorange="reversed"),
                          margin=dict(t=40, b=20, l=20, r=20))
        st.plotly_chart(fig4, use_container_width=True)


# ============================================================
# 탭 2: 문헌 검색
# ============================================================
with tab2:
    st.markdown("### 📋 문헌 검색 및 상세 조회")

    search_q = st.text_input("🔍 검색어 입력", placeholder="타겟, 화합물, 기전, 키워드 등...")

    display = filtered.copy()
    if search_q:
        mask = display.apply(lambda r: search_q.lower() in str(r.values).lower(), axis=1)
        display = display[mask]

    st.write(f"**{len(display)}건** 검색됨")

    # 표시할 컬럼 선택
    show_cols = ["파일명", "문서유형", "연구유형", "타겟(Target)", "화합물(Compound)",
                 "기전(MoA)", "핵심발견", "관련도"]

    st.dataframe(
        display[show_cols],
        use_container_width=True,
        height=500,
        column_config={
            "관련도": st.column_config.ProgressColumn("관련도", min_value=0, max_value=5, format="%d"),
            "파일명": st.column_config.TextColumn("파일명", width="medium"),
        }
    )

    # 논문 상세 보기
    st.markdown("---")
    st.markdown("#### 📄 논문 상세 보기")
    if len(display) > 0:
        paper_names = display["파일명"].tolist()
        selected_paper = st.selectbox("논문 선택", paper_names)

        if selected_paper:
            row = display[display["파일명"] == selected_paper].iloc[0]
            col_a, col_b = st.columns(2)

            with col_a:
                st.markdown(f"**문서유형:** {row.get('문서유형', '')}")
                st.markdown(f"**연구유형:** {row.get('연구유형', '')}")
                st.markdown(f"**타겟:** {row.get('타겟(Target)', '')}")
                st.markdown(f"**화합물:** {row.get('화합물(Compound)', '')}")
                st.markdown(f"**관련도:** {'⭐' * int(row.get('관련도', 0))}")

            with col_b:
                st.markdown(f"**기전 (MoA):** {row.get('기전(MoA)', '')}")
                st.markdown(f"**신호전달경로:** {row.get('신호전달경로', '')}")
                st.markdown(f"**세포/모델:** {row.get('세포/모델', '')}")
                st.markdown(f"**바이오마커:** {row.get('바이오마커', '')}")

            st.markdown("**핵심 발견:**")
            st.info(row.get("핵심발견", ""))

            # 원문 텍스트 보기
            txt_file = os.path.join(TXT_FOLDER, selected_paper)
            if os.path.exists(txt_file):
                with st.expander("📖 원문 텍스트 보기"):
                    with open(txt_file, "r", encoding="utf-8") as f:
                        st.text(f.read()[:5000] + "\n... (이하 생략)")

    # 다운로드
    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        csv_data = display[show_cols].to_csv(index=False, encoding="utf-8-sig")
        st.download_button("📥 CSV 다운로드", csv_data.encode("utf-8-sig"),
                          "AGA_검색결과.csv", "text/csv")
    with col_dl2:
        buf = io.BytesIO()
        display[show_cols].to_excel(buf, index=False, engine="openpyxl")
        st.download_button("📥 Excel 다운로드", buf.getvalue(),
                          "AGA_검색결과.xlsx",
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ============================================================
# 탭 3: 타겟 분석
# ============================================================
with tab3:
    import plotly.express as px

    st.markdown("### 🎯 타겟 심층 분석")

    # 타겟 목록 (논문수 순 정렬)
    target_counts = {t: len(idxs) for t, idxs in target_index.items() if len(t) > 1}
    sorted_targets = sorted(target_counts.keys(), key=lambda x: target_counts[x], reverse=True)

    # 상위 50개만 선택지로
    top50 = sorted_targets[:50]
    selected_target = st.selectbox("타겟 선택 (논문수 순)", top50,
                                   format_func=lambda x: f"{x} ({target_counts.get(x,0)}건)")

    if selected_target:
        idxs = target_index.get(selected_target, [])
        t_papers = df_ok.loc[df_ok.index.isin(idxs)]

        c1, c2, c3 = st.columns(3)
        c1.metric("관련 논문 수", f"{len(t_papers)}건")
        avg_rel = t_papers["관련도"].mean()
        c2.metric("평균 관련도", f"{avg_rel:.1f}")
        c3.metric("고관련도(4+)", f"{len(t_papers[t_papers['관련도']>=4])}건")

        st.markdown("---")

        col_l, col_r = st.columns(2)

        with col_l:
            st.markdown("#### 연관 화합물")
            t_comp = get_top_items(t_papers, "화합물(Compound)", 10)
            if t_comp:
                t_comp_df = pd.DataFrame(t_comp, columns=["화합물", "건수"])
                fig = px.bar(t_comp_df, x="건수", y="화합물", orientation="h",
                            color="건수", color_continuous_scale="Oranges")
                fig.update_layout(height=300, yaxis=dict(autorange="reversed"),
                                margin=dict(t=10, b=10))
                st.plotly_chart(fig, use_container_width=True)

        with col_r:
            st.markdown("#### 관련 신호전달 경로")
            t_path = get_top_items(t_papers, "신호전달경로", 10)
            if t_path:
                for pw, cnt in t_path:
                    st.write(f"- **{pw}** ({cnt}건)")

            st.markdown("#### 연구유형 분포")
            st_dist = t_papers["연구유형"].value_counts()
            for stype, cnt in st_dist.items():
                st.write(f"- {stype}: {cnt}건")

        # ─── 3D 단백질 구조 ──────────────────────────
        st.markdown("---")
        st.markdown("#### 🧬 3D 단백질 구조")

        # 선택된 타겟과 PDB 매핑 찾기
        _matched_pdb = None
        _matched_pdb_key = None
        for pdb_key, pdb_info in AGA_TARGET_PDB.items():
            # 타겟 이름이 PDB 키에 포함되거나 PDB 키가 타겟 이름에 포함되는지 확인
            if (selected_target.lower() in pdb_key.lower() or
                pdb_key.split(" (")[0].lower() in selected_target.lower() or
                selected_target.split(" ")[0].lower() in pdb_key.lower()):
                _matched_pdb = pdb_info
                _matched_pdb_key = pdb_key
                break

        if _matched_pdb:
            _pdb_id = _matched_pdb["pdb"]
            _col3d, _colinfo = st.columns([2, 1])

            with _col3d:
                _html_3d = f"""
                <!DOCTYPE html>
                <html><head>
                <style>
                  body {{ margin:0; padding:0; background:#0a0e27; overflow:hidden; }}
                  #container {{ width:100%; height:420px; position:relative; }}
                  #viewer {{ width:100%; height:380px; }}
                  #info {{ text-align:center; padding:6px; color:#8b949e; font-size:11px; }}
                  #info a {{ color:#58a6ff; }}
                  #loading {{ position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); color:#58a6ff; font-size:14px; }}
                </style>
                </head><body>
                <div id="container">
                  <div id="viewer"></div>
                  <div id="loading">⏳ Loading 3D structure...</div>
                  <div id="info">
                    PDB: <a href="https://www.rcsb.org/structure/{_pdb_id}" target="_blank">{_pdb_id}</a>
                    | UniProt: <a href="https://www.uniprot.org/uniprot/{_matched_pdb.get('uniprot','')}" target="_blank">{_matched_pdb.get('uniprot','')}</a>
                    | {_matched_pdb.get('desc','')}
                  </div>
                </div>
                <script src="https://3Dmol.org/build/3Dmol-min.js"></script>
                <script>
                function initViewer() {{
                  if (typeof $3Dmol === 'undefined') {{
                    setTimeout(initViewer, 200);
                    return;
                  }}
                  var el = document.getElementById("viewer");
                  var viewer = $3Dmol.createViewer(el, {{ backgroundColor: 0x0a0e27, antialias: true }});
                  fetch("https://files.rcsb.org/download/{_pdb_id}.pdb")
                    .then(function(r) {{ return r.text(); }})
                    .then(function(data) {{
                      document.getElementById("loading").style.display = "none";
                      viewer.addModel(data, "pdb");
                      viewer.setStyle({{}}, {{cartoon: {{color: "spectrum", opacity: 0.85}}}});
                      var bindRes = "{_matched_pdb.get('binding_residues', '')}";
                      if (bindRes) {{
                        var nums = bindRes.split(",").map(function(s) {{ return parseInt(s.replace(/[^0-9]/g, "")); }}).filter(function(n) {{ return !isNaN(n); }});
                        if (nums.length > 0) {{
                          viewer.addStyle({{resi: nums}}, {{stick: {{colorscheme: "orangeCarbon", radius: 0.15}}}});
                          viewer.addSurface($3Dmol.SurfaceType.VDW, {{opacity: 0.2, color: "#e94560"}}, {{resi: nums}});
                        }}
                      }}
                      viewer.zoomTo();
                      viewer.spin("y", 0.5);
                      viewer.render();
                    }})
                    .catch(function(err) {{
                      document.getElementById("loading").innerHTML = "❌ PDB load failed: " + err.message;
                    }});
                }}
                initViewer();
                </script>
                </body></html>
                """
                st.components.v1.html(_html_3d, height=460)

            with _colinfo:
                st.markdown(f"**{_matched_pdb_key}**")
                st.caption(_matched_pdb.get("desc", ""))
                st.markdown(f"- **PDB ID:** [{_pdb_id}](https://www.rcsb.org/structure/{_pdb_id})")
                st.markdown(f"- **UniProt:** [{_matched_pdb.get('uniprot','')}](https://www.uniprot.org/uniprot/{_matched_pdb.get('uniprot','')})")
                _af_uni = _matched_pdb.get("uniprot", "")
                if _af_uni:
                    st.markdown(f"- **AlphaFold:** [{_af_uni}](https://alphafold.ebi.ac.uk/entry/{_af_uni})")
                br = _matched_pdb.get("binding_residues", "")
                if br:
                    st.markdown(f"- **Binding Residues:** `{br}`")
                    st.caption("(3D 뷰에서 빨간 surface로 표시)")
        else:
            st.caption(f"ℹ️ '{selected_target}'의 PDB 3D 구조가 매핑되어 있지 않습니다.")

        # 핵심 발견
        st.markdown("#### 핵심 발견 (고관련도 순)")
        high_rel = t_papers.sort_values("관련도", ascending=False)
        for _, row in high_rel.head(8).iterrows():
            finding = row.get("핵심발견", "")
            if finding and str(finding) != "nan":
                rel = int(row.get("관련도", 0))
                st.markdown(f"{'⭐'*rel} **{row['파일명'][:60]}...**")
                st.caption(finding)

        # 타겟 프로파일 내보내기
        st.markdown("---")
        profile_text = f"""# {selected_target} - Target Profile Report
생성일: {datetime.now().strftime('%Y-%m-%d')}

## 기본 정보
- 관련 논문 수: {len(t_papers)}건
- 평균 관련도: {avg_rel:.1f}/5.0
- 고관련도(4+) 논문: {len(t_papers[t_papers['관련도']>=4])}건

## 연관 화합물
"""
        for comp, cnt in (t_comp if t_comp else []):
            profile_text += f"- {comp} ({cnt}건)\n"

        profile_text += "\n## 관련 신호전달 경로\n"
        for pw, cnt in (t_path if t_path else []):
            profile_text += f"- {pw} ({cnt}건)\n"

        profile_text += "\n## 주요 연구 발견\n"
        for _, row in high_rel.head(5).iterrows():
            f = row.get("핵심발견", "")
            if f and str(f) != "nan":
                profile_text += f"- [{row['파일명'][:50]}] {f}\n\n"

        st.download_button("📥 타겟 프로파일 다운로드 (.md)",
                          profile_text, f"{selected_target}_profile.md", "text/markdown")


# ============================================================
# 탭 4: 화합물 분석
# ============================================================
with tab4:
    import plotly.express as px

    st.markdown("### 💊 화합물 심층 분석")

    comp_counts = {c: len(idxs) for c, idxs in compound_index.items() if len(c) > 1}
    sorted_compounds = sorted(comp_counts.keys(), key=lambda x: comp_counts[x], reverse=True)

    top50c = sorted_compounds[:50]
    selected_compound = st.selectbox("화합물 선택 (논문수 순)", top50c,
                                     format_func=lambda x: f"{x} ({comp_counts.get(x,0)}건)")

    if selected_compound:
        c_idxs = compound_index.get(selected_compound, [])
        c_papers = df_ok.loc[df_ok.index.isin(c_idxs)]

        # ── 화합물 구조 카드 ──
        struct = structures.get(selected_compound, {})
        if struct:
            st.markdown("#### 🧪 화합물 구조 정보")
            img_col, info_col = st.columns([1, 2])

            with img_col:
                img_url = struct.get("image_url", "")
                if img_url:
                    st.image(img_url, caption=f"{selected_compound} 2D Structure",
                             width=250)

            with info_col:
                st.markdown(f"**분자식:** {struct.get('MolecularFormula', '-')}")
                st.markdown(f"**분자량:** {struct.get('MolecularWeight', '-')} g/mol")
                st.markdown(f"**SMILES:** `{struct.get('SMILES', '-')}`")
                st.markdown(f"**PubChem CID:** [{struct.get('CID', '')}]({struct.get('pubchem_url', '')})")
                iupac = struct.get("IUPACName", "")
                if iupac:
                    st.caption(f"IUPAC: {iupac}")

            st.markdown("---")

        # ── 천연물인 경우: 활성 성분 카드 ──
        np_mapping = np_data.get("natural_product_mapping", {})
        np_actives_db = np_data.get("active_compounds", {})
        active_list = np_mapping.get(selected_compound, [])

        if not active_list:
            # 부분 매칭 시도
            for np_name, actives in np_mapping.items():
                if np_name in selected_compound or selected_compound in np_name:
                    active_list = actives
                    break

        if active_list and not struct:
            st.markdown("#### 🌿 천연물 활성 성분 (Active Compounds)")
            st.caption(f"'{selected_compound}'의 주요 활성 성분과 구조 정보입니다.")

            for act_name in active_list:
                act_info = np_actives_db.get(act_name, {})
                if act_info.get("status") == "found":
                    with st.container():
                        act_img_col, act_info_col = st.columns([1, 3])
                        with act_img_col:
                            act_img = act_info.get("image_url", "")
                            if act_img:
                                st.image(act_img, caption=act_name, width=180)
                        with act_info_col:
                            st.markdown(f"**{act_name}**")
                            st.markdown(f"분자식: {act_info.get('MolecularFormula', '-')} · "
                                       f"분자량: {act_info.get('MolecularWeight', '-')} g/mol")
                            smiles = act_info.get("SMILES", "")
                            if smiles:
                                st.code(smiles, language=None)
                            cid = act_info.get("CID", "")
                            if cid:
                                st.markdown(f"[PubChem CID: {cid}]({act_info.get('pubchem_url', '')})")
                            # 알려진 타깃 표시
                            bio = act_info.get("bioactivity", {})
                            targets = bio.get("known_targets", [])
                            if targets:
                                st.markdown(f"**알려진 타깃:** {', '.join(targets[:5])}")
                else:
                    st.write(f"- {act_name} (PubChem 미등록)")

            st.markdown("---")

        c1, c2, c3 = st.columns(3)
        c1.metric("관련 논문 수", f"{len(c_papers)}건")
        c2.metric("평균 관련도", f"{c_papers['관련도'].mean():.1f}")
        clinical = len(c_papers[c_papers["연구유형"] == "Clinical"])
        c3.metric("임상 연구", f"{clinical}건")

        st.markdown("---")

        col_l, col_r = st.columns(2)

        with col_l:
            st.markdown("#### 타겟")
            c_tgt = get_top_items(c_papers, "타겟(Target)", 10, normalize_target)
            if c_tgt:
                c_tgt_df = pd.DataFrame(c_tgt, columns=["타겟", "건수"])
                fig = px.bar(c_tgt_df, x="건수", y="타겟", orientation="h",
                            color="건수", color_continuous_scale="Purples")
                fig.update_layout(height=300, yaxis=dict(autorange="reversed"),
                                margin=dict(t=10, b=10))
                st.plotly_chart(fig, use_container_width=True)

        with col_r:
            st.markdown("#### 기전 (MoA) 요약")
            for _, row in c_papers.head(5).iterrows():
                moa = row.get("기전(MoA)", "")
                if moa and str(moa) != "nan":
                    st.caption(f"• {moa}")

        # 관련 논문 테이블
        st.markdown("#### 관련 논문")
        st.dataframe(
            c_papers[["파일명", "연구유형", "타겟(Target)", "기전(MoA)", "관련도"]],
            use_container_width=True, height=300
        )

        # 화합물 프로파일 다운로드
        comp_profile = f"""# {selected_compound} - Compound Profile Report
생성일: {datetime.now().strftime('%Y-%m-%d')}

## 기본 정보
- 관련 논문: {len(c_papers)}건
- 평균 관련도: {c_papers['관련도'].mean():.1f}/5.0
- 임상 연구: {clinical}건

## 타겟
"""
        for tgt, cnt in (c_tgt if c_tgt else []):
            comp_profile += f"- {tgt} ({cnt}건)\n"

        comp_profile += "\n## 주요 MoA\n"
        for _, row in c_papers.head(5).iterrows():
            moa = row.get("기전(MoA)", "")
            if moa and str(moa) != "nan":
                comp_profile += f"- {moa}\n\n"

        st.download_button("📥 화합물 프로파일 다운로드 (.md)",
                          comp_profile, f"{selected_compound}_profile.md", "text/markdown")


# ============================================================
# 탭 5: Target-Compound 매트릭스
# ============================================================
with tab5:
    import plotly.graph_objects as go

    st.markdown("### 🔗 Target-Compound 관계 매트릭스")
    st.caption("타겟과 화합물 간 공출현(co-occurrence) 빈도를 히트맵으로 시각화합니다.")

    n_targets = st.slider("상위 타겟 수", 5, 20, 10)
    n_compounds = st.slider("상위 화합물 수", 5, 20, 10)

    # 상위 타겟/화합물 추출
    top_t = [t for t, _ in get_top_items(df_ok, "타겟(Target)", n_targets, normalize_target)]
    top_c = [c for c, _ in get_top_items(df_ok, "화합물(Compound)", n_compounds)]

    # 매트릭스 구축
    matrix = pd.DataFrame(0, index=top_t, columns=top_c)

    for _, row in df_ok.iterrows():
        targets = str(row.get("타겟(Target)", ""))
        compounds = str(row.get("화합물(Compound)", ""))
        if targets == "nan" or compounds == "nan":
            continue

        row_targets = [normalize_target(t) for t in targets.split(",") if t.strip()]
        row_compounds = [c.strip() for c in compounds.split(",") if c.strip()]

        for t in row_targets:
            for c in row_compounds:
                if t in matrix.index and c in matrix.columns:
                    matrix.loc[t, c] += 1

    fig = go.Figure(data=go.Heatmap(
        z=matrix.values,
        x=matrix.columns.tolist(),
        y=matrix.index.tolist(),
        colorscale="YlOrRd",
        text=matrix.values,
        texttemplate="%{text}",
        textfont={"size": 11},
        hovertemplate="타겟: %{y}<br>화합물: %{x}<br>공출현: %{z}건<extra></extra>"
    ))

    fig.update_layout(
        title="Target-Compound Co-occurrence Matrix",
        xaxis_title="Compounds",
        yaxis_title="Targets",
        height=500,
        margin=dict(t=60, b=20, l=20, r=20),
        yaxis=dict(autorange="reversed")
    )

    st.plotly_chart(fig, use_container_width=True)

    # 매트릭스 다운로드
    buf = io.BytesIO()
    matrix.to_excel(buf, engine="openpyxl")
    st.download_button("📥 매트릭스 Excel 다운로드", buf.getvalue(),
                      "Target_Compound_Matrix.xlsx",
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # 신규 타겟 후보 탐색
    st.markdown("---")
    st.markdown("#### 🔬 Novel Target 후보 (저빈도 + 고관련도)")
    st.caption("논문 수가 적지만 관련도가 높은 타겟 = 경쟁이 적은 유망 타겟")

    novel_candidates = []
    for t, idxs in target_index.items():
        if len(t) <= 2:
            continue
        papers = df_ok.loc[df_ok.index.isin(idxs)]
        if len(papers) < 5 and len(papers) >= 1:
            avg_r = papers["관련도"].mean()
            if avg_r >= 4.0:
                novel_candidates.append({
                    "타겟": t,
                    "논문수": len(papers),
                    "평균관련도": round(avg_r, 1),
                    "연관화합물": ", ".join([c for c, _ in get_top_items(papers, "화합물(Compound)", 3)])
                })

    if novel_candidates:
        novel_df = pd.DataFrame(novel_candidates).sort_values("평균관련도", ascending=False)
        st.dataframe(novel_df.head(20), use_container_width=True)

        buf2 = io.BytesIO()
        novel_df.to_excel(buf2, index=False, engine="openpyxl")
        st.download_button("📥 Novel Target 후보 다운로드", buf2.getvalue(),
                          "Novel_Target_Candidates.xlsx",
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ============================================================
# 탭 6: 3D CPI Binding Visualization
# ============================================================
with tab6:
    import streamlit.components.v1 as components

    st.markdown("### 🧫 Compound-Protein Interaction (CPI) 3D Binding Visualization")
    st.caption("3Dmol.js + RCSB PDB / PubChem 기반 — AGA 핵심 타겟 단백질과 약물 결합 시각화")

    CPI_COLORS = ["#00e676","#ffd740","#ff4081","#40c4ff","#ea80fc","#ff6e40","#69f0ae","#448aff"]

    cpi_mode = st.radio("분석 모드", ["약물 → 결합 타겟", "타겟 단백질 → 결합 약물"], horizontal=True)

    if cpi_mode == "약물 → 결합 타겟":
        cmp_list = list(AGA_COMPOUND_TARGET_MAP.keys())
        sel_cmp = st.selectbox("화합물 선택", cmp_list)

        if sel_cmp:
            cmp_info = AGA_COMPOUND_TARGET_MAP[sel_cmp]
            targets_for_cmp = cmp_info["targets"]

            col_info, col_3d = st.columns([1, 2])

            with col_info:
                st.markdown(f"#### {sel_cmp}")
                st.markdown(f"**Type:** {cmp_info.get('type', '')}")
                st.markdown(f"**Phase:** {cmp_info.get('phase', '')}")
                st.markdown(f"**Indication:** {cmp_info.get('indication', '')}")
                st.markdown(f"**MoA:** {cmp_info.get('moa', '')}")

                # 2D Structure from PubChem
                _cmp_cid = cmp_info.get("pubchem_cid")
                if _cmp_cid:
                    st.image(f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/CID/{_cmp_cid}/PNG?image_size=250x250",
                             caption="2D Structure (PubChem)", width=220)

                st.markdown("**결합 타겟:**")
                for t in targets_for_cmp:
                    tinfo = AGA_TARGET_PDB.get(t, {})
                    pdb_id = tinfo.get("pdb", "N/A")
                    st.markdown(f"- **{t}** (PDB: [{pdb_id}](https://www.rcsb.org/structure/{pdb_id}))")

            with col_3d:
                st.markdown("#### 3D Binding Visualization")
                sel_bind_target = st.selectbox("결합 타겟 선택", targets_for_cmp)

                tgt_pdb_info = AGA_TARGET_PDB.get(sel_bind_target, {})
                pdb_id = tgt_pdb_info.get("pdb", "")
                binding_res = cmp_info.get("binding_sites", {}).get(sel_bind_target, tgt_pdb_info.get("binding_residues", ""))

                if pdb_id:
                    _cmp_img_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/CID/{cmp_info.get('pubchem_cid','')}/PNG?image_size=120x120" if cmp_info.get("pubchem_cid") else ""

                    viewer_html = f"""
<html><head>
<script src="https://3Dmol.org/build/3Dmol-min.js"></script>
<style>
body {{ margin:0; background: #0a0e27; font-family: 'Segoe UI', sans-serif; }}
#viewer {{ width:100%; height:500px; position:relative; border-radius:10px; overflow:hidden; }}
.info-bar {{ padding:8px 14px; background:rgba(10,14,39,0.9); color:#c0cde0; font-size:12px;
    display:flex; justify-content:space-between; align-items:center; border-radius:0 0 10px 10px; }}
.info-bar a {{ color:#58a6ff; text-decoration:none; }}
#loading {{ position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); color:#58a6ff; font-size:14px; z-index:10; }}
.spinner {{ display:inline-block; width:18px; height:18px; border:3px solid rgba(88,166,255,0.3);
    border-top:3px solid #58a6ff; border-radius:50%; animation:spin 1s linear infinite; margin-right:8px; vertical-align:middle; }}
@keyframes spin {{ to {{ transform:rotate(360deg); }} }}
.legend {{ position:absolute; top:10px; right:10px; background:rgba(10,14,39,0.85); padding:8px 12px;
    border-radius:8px; color:#c0cde0; font-size:11px; z-index:5; }}
.legend div {{ margin:2px 0; }}
.dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }}
.cmp-card {{ position:absolute; bottom:10px; left:10px; background:rgba(10,14,39,0.9); padding:8px;
    border-radius:8px; z-index:5; display:flex; align-items:center; gap:8px; }}
.cmp-card img {{ width:60px; height:60px; border-radius:4px; }}
.cmp-card .name {{ color:#ffd740; font-size:11px; font-weight:600; }}
</style>
</head><body>
<div id="viewer">
    <div id="loading"><span class="spinner"></span>Loading PDB structure...</div>
    <div class="legend">
        <div><span class="dot" style="background:#4fc3f7;"></span>Protein (cartoon)</div>
        <div><span class="dot" style="background:#00e676;"></span>Binding site (stick)</div>
        <div><span class="dot" style="background:rgba(0,230,118,0.3);"></span>Binding surface</div>
    </div>
    {"<div class='cmp-card'><img src='" + _cmp_img_url + "' onerror='this.style.display=&quot;none&quot;'/><div><div class='name'>" + sel_cmp + "</div><div style='color:#8b949e;font-size:10px;'>" + cmp_info.get('type','') + "</div></div></div>" if _cmp_img_url else ""}
</div>
<div class="info-bar">
    <span>PDB: <a href="https://www.rcsb.org/structure/{pdb_id}" target="_blank">{pdb_id}</a> | UniProt: {tgt_pdb_info.get('uniprot', '')}</span>
    <span>{tgt_pdb_info.get('desc', '')}</span>
</div>
<script>
var el = document.getElementById("viewer");
var viewer = $3Dmol.createViewer(el, {{ backgroundColor: 0x0a0e27, antialias: true }});
fetch("https://files.rcsb.org/download/{pdb_id}.pdb")
    .then(r => r.text())
    .then(data => {{
        document.getElementById("loading").style.display = "none";
        viewer.addModel(data, "pdb");
        viewer.setStyle({{}}, {{ cartoon: {{ color: "spectrum", opacity: 0.82, thickness: 0.28 }} }});
        var bindRes = "{binding_res}";
        if (bindRes) {{
            var residues = bindRes.split(",");
            var nums = [];
            residues.forEach(function(rn) {{
                var num = parseInt(rn.replace(/[^0-9]/g, ""));
                if (num) {{
                    nums.push(num);
                    viewer.setStyle({{resi: num}}, {{
                        stick: {{ colorscheme: "greenCarbon", radius: 0.18 }},
                        cartoon: {{ color: "spectrum", opacity: 0.5 }}
                    }});
                    viewer.addLabel(rn, {{
                        fontSize: 10, fontColor: "#00e676",
                        backgroundColor: "rgba(0,0,0,0.6)",
                        backgroundOpacity: 0.6,
                        position: {{ x: 0, y: 0, z: 0 }}
                    }}, {{resi: num}});
                }}
            }});
            if (nums.length > 0) {{
                viewer.addSurface($3Dmol.SurfaceType.VDW, {{ opacity: 0.2, color: "#00e676" }}, {{resi: nums}});
            }}
        }}
        viewer.zoomTo(); viewer.render();
        function anim() {{ viewer.rotate(0.2, "y"); viewer.render(); requestAnimationFrame(anim); }}
        anim();
    }}).catch(err => {{
        document.getElementById("loading").innerHTML =
            '<span style="color:#e94560;">PDB load failed: ' + err.message + '</span>';
    }});
</script>
</body></html>"""
                    components.html(viewer_html, height=580)

                    # 추가 링크
                    _lc1, _lc2, _lc3 = st.columns(3)
                    _lc1.markdown(f"[RCSB PDB](https://www.rcsb.org/structure/{pdb_id})")
                    _lc2.markdown(f"[UniProt](https://www.uniprot.org/uniprot/{tgt_pdb_info.get('uniprot', '')})")
                    _af_uni = tgt_pdb_info.get("uniprot", "")
                    if _af_uni:
                        _lc3.markdown(f"[AlphaFold](https://alphafold.ebi.ac.uk/entry/{_af_uni})")
                else:
                    st.warning("이 타겟의 PDB 구조가 없습니다.")

    else:  # 타겟 단백질 → 결합 약물
        target_list = list(AGA_TARGET_PDB.keys())
        sel_tgt = st.selectbox("타겟 단백질 선택", target_list,
                               format_func=lambda x: f"{x} (PDB: {AGA_TARGET_PDB[x]['pdb']})")

        if sel_tgt:
            tgt_info = AGA_TARGET_PDB[sel_tgt]
            pdb_id = tgt_info["pdb"]

            # 이 타겟에 결합하는 모든 화합물 찾기
            binding_compounds = []
            for cname, cdata in AGA_COMPOUND_TARGET_MAP.items():
                if sel_tgt in cdata["targets"]:
                    binding_compounds.append({"name": cname, **cdata})

            col_3d, col_compounds = st.columns([2, 1])

            with col_3d:
                st.markdown(f"#### {sel_tgt} 3D Structure")

                # 각 화합물의 결합 잔기에 다른 색상 할당
                compound_residues_js = "["
                for ci, bc in enumerate(binding_compounds):
                    _bs = bc.get("binding_sites", {}).get(sel_tgt, "")
                    _color = CPI_COLORS[ci % len(CPI_COLORS)]
                    compound_residues_js += f'{{name:"{bc["name"]}",residues:"{_bs}",color:"{_color}"}},'
                compound_residues_js += "]"

                tgt_viewer_html = f"""
<html><head>
<script src="https://3Dmol.org/build/3Dmol-min.js"></script>
<style>
body {{ margin:0; background: #0a0e27; font-family: 'Segoe UI', sans-serif; }}
#viewer {{ width:100%; height:520px; position:relative; border-radius:10px; overflow:hidden; }}
.info-bar {{ padding:8px 14px; background:rgba(10,14,39,0.9); color:#c0cde0; font-size:12px;
    border-radius:0 0 10px 10px; }}
#loading {{ position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); color:#58a6ff; z-index:10; }}
.spinner {{ display:inline-block; width:18px; height:18px; border:3px solid rgba(88,166,255,0.3);
    border-top:3px solid #58a6ff; border-radius:50%; animation:spin 1s linear infinite; margin-right:8px; }}
@keyframes spin {{ to {{ transform:rotate(360deg); }} }}
.legend {{ position:absolute; top:10px; right:10px; background:rgba(10,14,39,0.85); padding:8px 12px;
    border-radius:8px; color:#c0cde0; font-size:11px; z-index:5; max-height:200px; overflow-y:auto; }}
.legend div {{ margin:3px 0; }}
.dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }}
</style>
</head><body>
<div id="viewer">
    <div id="loading"><span class="spinner"></span>Loading PDB structure...</div>
    <div class="legend" id="legend">
        <div><span class="dot" style="background:#4fc3f7;"></span>Protein backbone</div>
    </div>
</div>
<div class="info-bar">
    <span>PDB: {pdb_id} | UniProt: {tgt_info.get('uniprot', '')} | {tgt_info.get('desc', '')}</span>
</div>
<script>
var compounds = {compound_residues_js};
var legendEl = document.getElementById("legend");
compounds.forEach(function(c) {{
    var d = document.createElement("div");
    d.innerHTML = '<span class="dot" style="background:' + c.color + ';"></span>' + c.name;
    legendEl.appendChild(d);
}});
var el = document.getElementById("viewer");
var viewer = $3Dmol.createViewer(el, {{ backgroundColor: 0x0a0e27, antialias: true }});
fetch("https://files.rcsb.org/download/{pdb_id}.pdb")
    .then(r => r.text())
    .then(data => {{
        document.getElementById("loading").style.display = "none";
        viewer.addModel(data, "pdb");
        viewer.setStyle({{}}, {{ cartoon: {{ color: "#4fc3f7", opacity: 0.7, thickness: 0.25 }} }});
        compounds.forEach(function(cmp) {{
            if (!cmp.residues) return;
            var residues = cmp.residues.split(",");
            var nums = [];
            residues.forEach(function(rn) {{
                var num = parseInt(rn.replace(/[^0-9]/g, ""));
                if (num) {{
                    nums.push(num);
                    viewer.setStyle({{resi: num}}, {{
                        stick: {{ color: cmp.color, radius: 0.18 }},
                        cartoon: {{ color: "#4fc3f7", opacity: 0.4 }}
                    }});
                    viewer.addLabel(cmp.name + " " + rn, {{
                        fontSize: 9, fontColor: cmp.color,
                        backgroundColor: "rgba(0,0,0,0.7)",
                        backgroundOpacity: 0.7
                    }}, {{resi: num}});
                }}
            }});
            if (nums.length > 0) {{
                viewer.addSurface($3Dmol.SurfaceType.VDW, {{ opacity: 0.15, color: cmp.color }}, {{resi: nums}});
            }}
        }});
        viewer.zoomTo(); viewer.render();
        function anim() {{ viewer.rotate(0.2, "y"); viewer.render(); requestAnimationFrame(anim); }}
        anim();
    }}).catch(err => {{
        document.getElementById("loading").innerHTML =
            '<span style="color:#e94560;">PDB load failed: ' + err.message + '</span>';
    }});
</script>
</body></html>"""
                components.html(tgt_viewer_html, height=580)

                _lc1, _lc2, _lc3 = st.columns(3)
                _lc1.markdown(f"[RCSB PDB](https://www.rcsb.org/structure/{pdb_id})")
                _lc2.markdown(f"[UniProt](https://www.uniprot.org/uniprot/{tgt_info.get('uniprot', '')})")
                _lc3.markdown(f"[AlphaFold](https://alphafold.ebi.ac.uk/entry/{tgt_info.get('uniprot', '')})")

            with col_compounds:
                st.markdown(f"#### 결합 약물 ({len(binding_compounds)}개)")
                for ci, bc in enumerate(binding_compounds):
                    _color = CPI_COLORS[ci % len(CPI_COLORS)]
                    st.markdown(f"""
                    <div style='padding:10px; margin:6px 0; border-radius:8px;
                         background:rgba(255,255,255,0.05); border-left:3px solid {_color};'>
                        <div style='color:{_color}; font-weight:600; font-size:14px;'>{bc['name']}</div>
                        <div style='color:#8b949e; font-size:11px; margin-top:4px;'>{bc.get('moa', '')[:100]}</div>
                        <div style='color:#58a6ff; font-size:11px; margin-top:2px;'>{bc.get('phase', '')}</div>
                    </div>
                    """, unsafe_allow_html=True)

                    # 2D structure thumbnail
                    _bc_cid = bc.get("pubchem_cid")
                    if _bc_cid:
                        st.image(f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/CID/{_bc_cid}/PNG?image_size=160x160",
                                 caption=f"{bc['name']} 2D", width=140)

                if not binding_compounds:
                    st.info("이 타겟에 결합하는 알려진 약물이 없습니다.")


# ============================================================
# 탭 7: AI 질의응답 (RAG)
# ============================================================
with tab7:
    st.markdown("### 🤖 AGA AI Expert — RAG 기반 전문가 시스템")

    # Knowledge Base 상태 표시
    _kb_available = False
    _aga_expert = None
    try:
        import sys as _sys
        if _script_dir not in _sys.path:
            _sys.path.insert(0, _script_dir)
        from aga_ai_engine import AGA_AI_Expert
        _aga_expert = AGA_AI_Expert(api_key=CLAUDE_API_KEY)
        _kb_stats = _aga_expert.get_stats()
        _kb_available = _kb_stats["papers_chunks"] > 0

        if _kb_available:
            _c1, _c2, _c3 = st.columns(3)
            _c1.metric("논문 청크", f"{_kb_stats['papers_chunks']:,}")
            _c2.metric("구조화 데이터", f"{_kb_stats['structured_entries']:,}")
            _build_meta = _kb_stats.get("metadata", {})
            _c3.metric("원본 논문", f"{_build_meta.get('text_files', 'N/A'):,}")
            st.success("Knowledge Base 연결됨 — 508,572개 벡터 청크에서 시맨틱 검색")
        else:
            st.warning("Knowledge Base가 비어있습니다. build_knowledge_base.py를 먼저 실행하세요.")
    except Exception as _kb_err:
        st.info(f"Knowledge Base 미연결 — 기본 키워드 검색 모드로 작동합니다. ({_kb_err})")

    # 예시 질문
    st.markdown("**예시 질문:**")
    _ex_cols = st.columns(2)
    _example_qs = [
        "AGA에서 Wnt/β-catenin 경로를 타겟으로 하는 novel compound는?",
        "Finasteride와 Dutasteride의 차이점을 논문 근거로 설명해줘",
        "Hair follicle stem cell을 타겟으로 하는 전임상 연구는?",
        "JAK inhibitor의 AGA 치료 가능성은?",
        "국소 약물전달시스템(DDS)으로 개발된 AGA 치료제는?",
        "Dermal papilla cell에서 발현되는 핵심 성장인자는?",
        "miRNA 기반 탈모 치료 접근법의 최신 연구는?",
        "Prostaglandin D2/E2의 모발 성장 조절 기전은?",
    ]
    for _qi, _q in enumerate(_example_qs):
        _ex_cols[_qi % 2].caption(f"  • {_q}")

    st.markdown("---")

    # 채팅 히스토리
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    question = st.chat_input("AGA 신약개발에 대해 무엇이든 질문하세요...")

    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("508,572개 논문 청크에서 관련 정보 검색 중..."):
                try:
                    if _kb_available and _aga_expert and CLAUDE_API_KEY:
                        # RAG 모드: 벡터 검색 + Claude
                        result = _aga_expert.ask(question, n_papers=15, n_structured=8)
                        answer = result["answer"]
                        sources = result.get("sources", {})
                        tokens = result.get("tokens_used", 0)

                        st.markdown(answer)

                        # 출처 표시
                        with st.expander(f"📚 참조 논문 ({len(sources.get('papers', []))}건) | 토큰: {tokens:,}"):
                            if sources.get("structured"):
                                st.markdown("**구조화 데이터:**")
                                for _si, _s in enumerate(sources["structured"], 1):
                                    st.caption(f"[S{_si}] {_s['text'][:150]}...")
                            if sources.get("papers"):
                                st.markdown("**논문 텍스트:**")
                                for _pi, _p in enumerate(sources["papers"], 1):
                                    st.caption(f"[P{_pi}] {_p['source'][:80]} (PMID: {_p.get('pmid','')}, relevance: {_p.get('relevance','')})")

                    elif _kb_available and _aga_expert:
                        # KB 있지만 API 키 없음: 검색만
                        result = _aga_expert.ask(question, n_papers=10, n_structured=5)
                        answer = result["answer"]
                        st.markdown(answer)
                        st.warning("Claude API 키를 설정하면 AI 전문가 답변을 받을 수 있습니다.")

                    else:
                        # 기본 모드: 키워드 매칭 + Claude
                        keywords = [kw for kw in question.lower().split() if len(kw) > 1]
                        relevant = df_ok[df_ok.apply(
                            lambda row: sum(1 for kw in keywords if kw in str(row.values).lower()) >= 1,
                            axis=1
                        )].sort_values("관련도", ascending=False).head(15)

                        context_parts = []
                        for _, row in relevant.iterrows():
                            parts = []
                            for col in ["파일명", "타겟(Target)", "화합물(Compound)", "기전(MoA)",
                                        "핵심발견", "신호전달경로", "바이오마커"]:
                                val = row.get(col, "")
                                if val and str(val) != "nan":
                                    parts.append(f"{col}: {val}")
                            context_parts.append("\n".join(parts))
                        context = "\n---\n".join(context_parts)

                        if CLAUDE_API_KEY:
                            import anthropic
                            client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
                            prompt = f"""You are an expert in AGA drug development.
Below is data from {len(df_ok)} papers. Answer in Korean with citations.

[Data]
{context}

[Question]
{question}"""
                            response = client.messages.create(
                                model="claude-haiku-4-5-20251001",
                                max_tokens=2000,
                                messages=[{"role": "user", "content": prompt}]
                            )
                            answer = response.content[0].text
                        else:
                            answer = f"키워드 검색 결과 {len(relevant)}건의 관련 논문이 있습니다.\n\nClaude API 키를 설정하면 AI 답변을 받을 수 있습니다."
                        st.markdown(answer)

                except Exception as e:
                    answer = f"오류가 발생했습니다: {str(e)[:300]}"
                    st.error(answer)

        st.session_state.messages.append({"role": "assistant", "content": answer if 'answer' in locals() else "오류가 발생했습니다."})


# ============================================================
# 탭 8: 🔬 Dark Targets (미개척 타겟 발굴)
# ============================================================
with tab8:
    st.markdown("### 🔬 Dark Targets — 미개척 타겟 발굴")
    st.caption("Novelty Index가 높은 '다크 타겟'을 발견하고, 연구 공백을 분석합니다.")

    # intelligence_report.json 로드
    _intel_report = None
    for d in _search_dirs + [os.path.join(d, 'output') for d in _search_dirs]:
        ir_path = os.path.join(d, 'intelligence_report.json')
        if os.path.exists(ir_path):
            try:
                with open(ir_path, 'r', encoding='utf-8') as f:
                    _intel_report = json.load(f)
                break
            except Exception:
                pass

    if _intel_report:
        ts = _intel_report.get('timestamp', '')
        st.success(f"마지막 분석: {ts[:19] if ts else 'N/A'}")

        # Dark Targets 랭킹
        dark_targets = _intel_report.get('top_dark_targets', [])
        if dark_targets:
            st.markdown("#### 🏆 Dark Target 랭킹 (Novelty Index)")
            dt_rows = []
            for i, dt in enumerate(dark_targets[:20], 1):
                dt_rows.append({
                    "순위": i,
                    "타겟": dt.get('target', ''),
                    "Novelty Index": round(dt.get('novelty_index', 0), 4),
                    "논문 수": dt.get('paper_count', 0),
                    "관련도": round(dt.get('avg_relevance', 0), 1),
                    "경로 다양성": round(dt.get('pathway_diversity', 0), 2),
                })
            st.dataframe(pd.DataFrame(dt_rows), use_container_width=True, hide_index=True)

            # Top 5 설명
            st.markdown("#### 📋 Top 5 Dark Target 상세")
            for dt in dark_targets[:5]:
                with st.expander(f"🎯 {dt.get('target', '')} (NI={dt.get('novelty_index', 0):.4f})"):
                    st.markdown(f"**논문 수:** {dt.get('paper_count', 0)}건")
                    st.markdown(f"**평균 관련도:** {dt.get('avg_relevance', 0):.1f}/5")
                    pathways = dt.get('pathways', [])
                    if pathways:
                        st.markdown(f"**관련 경로:** {', '.join(pathways[:5])}")
                    compounds = dt.get('compounds', [])
                    if compounds:
                        st.markdown(f"**관련 화합물:** {', '.join(compounds[:5])}")

        # Gap Analysis
        gaps = _intel_report.get('top_gaps', [])
        if gaps:
            st.markdown("#### 🕳️ Gap Analysis — 미탐색 타겟-화합물 조합")
            gap_rows = []
            for g in gaps[:20]:
                gap_rows.append({
                    "타겟": g.get('target', ''),
                    "화합물": g.get('compound', ''),
                    "Gap Score": round(g.get('gap_score', 0), 3),
                })
            st.dataframe(pd.DataFrame(gap_rows), use_container_width=True, hide_index=True)

        # Multi-target Synergy
        synergies = _intel_report.get('top_synergies', [])
        if synergies:
            st.markdown("#### 🔄 Multi-target Synergy")
            syn_rows = []
            for s in synergies[:10]:
                syn_rows.append({
                    "타겟 1": s.get('target1', ''),
                    "타겟 2": s.get('target2', ''),
                    "시너지 점수": round(s.get('synergy_score', 0), 3),
                    "공유 경로": ', '.join(s.get('shared_pathways', [])[:3]),
                })
            st.dataframe(pd.DataFrame(syn_rows), use_container_width=True, hide_index=True)
    else:
        st.info("🔬 아직 패턴 분석이 실행되지 않았습니다.")
        st.markdown("""
        **실행 방법:**
        - 로컬: `python scripts/10_pattern_analysis.py`
        - 자동: 매주 월요일 GitHub Actions에서 자동 실행
        """)


# ============================================================
# 탭 9: 💡 AI 신약 후보 (Novel Compound Discovery)
# ============================================================
with tab9:
    st.markdown("### 💡 AI 신약 후보물질")
    st.caption("Dark Target에 대해 Claude AI가 제안한 novel compound 후보입니다.")

    _candidates_data = None
    for d in _search_dirs + [os.path.join(d, 'output') for d in _search_dirs]:
        cm_path = os.path.join(d, 'candidate_molecules.json')
        if os.path.exists(cm_path):
            try:
                with open(cm_path, 'r', encoding='utf-8') as f:
                    _candidates_data = json.load(f)
                break
            except Exception:
                pass

    if _candidates_data:
        ts = _candidates_data.get('timestamp', '')
        total = _candidates_data.get('total_candidates', 0)
        st.success(f"총 {total}개 후보물질 | 마지막 생성: {ts[:19] if ts else 'N/A'}")

        candidates = _candidates_data.get('candidates', [])
        if candidates:
            # 타겟별 그룹
            from collections import defaultdict
            by_target = defaultdict(list)
            for c in candidates:
                by_target[c.get('target', 'Unknown')].append(c)

            for target, cands in by_target.items():
                st.markdown(f"#### 🎯 {target}")
                for i, c in enumerate(cands, 1):
                    valid = c.get('validation_status', '') == 'Valid'
                    status_icon = "✅" if valid else "⚠️"
                    smiles = c.get('smiles', 'N/A')
                    with st.expander(f"{status_icon} 후보 #{i}: {smiles[:50]}{'...' if len(smiles) > 50 else ''}"):
                        st.code(smiles, language=None)
                        st.markdown(f"**근거:** {c.get('rationale', 'N/A')}")
                        st.markdown(f"**Novelty Score:** {c.get('novelty_score', 'N/A')}")
                        st.markdown(f"**검증 상태:** {c.get('validation_status', 'N/A')}")
                        if c.get('mechanism'):
                            st.markdown(f"**기전:** {c.get('mechanism')}")
    else:
        st.info("💡 아직 신약 후보 도출이 실행되지 않았습니다.")
        st.markdown("""
        **실행 방법:**
        1. 먼저 `10_pattern_analysis.py`를 실행하세요 (Dark Target 발굴)
        2. 그 다음 `python scripts/11_drug_candidates.py` 실행
        - 자동: 매주 월요일 GitHub Actions에서 자동 실행
        """)


# ============================================================
# 탭 10: 🧬 바이오마커 분석
# ============================================================
with tab10:
    st.markdown("### 🧬 바이오마커 분석")
    st.caption("AGA 관련 바이오마커의 분포, 타겟 연관성, 경로 분석")

    _biomarker_data = None
    for d in _search_dirs + [os.path.join(d, 'output') for d in _search_dirs]:
        bm_path = os.path.join(d, 'biomarker_analysis.json')
        if os.path.exists(bm_path):
            try:
                with open(bm_path, 'r', encoding='utf-8') as f:
                    _biomarker_data = json.load(f)
                break
            except Exception:
                pass

    if _biomarker_data:
        total_bm = _biomarker_data.get('total_biomarkers', 0)
        st.success(f"총 {total_bm}종 바이오마커 분석 완료")

        # Top 바이오마커
        top_bm = _biomarker_data.get('top_biomarkers', [])
        if top_bm:
            st.markdown("#### 📊 바이오마커 빈도 Top 20")
            import plotly.express as px
            bm_df = pd.DataFrame(top_bm[:20])
            if not bm_df.empty:
                fig = px.bar(bm_df, x='name', y='count',
                           title='AGA 바이오마커 출현 빈도',
                           labels={'name': '바이오마커', 'count': '출현 횟수'},
                           color='count', color_continuous_scale='Viridis')
                fig.update_layout(xaxis_tickangle=-45, height=400)
                st.plotly_chart(fig, use_container_width=True)

        # 카테고리별 분류
        categories = _biomarker_data.get('categories', {})
        if categories:
            st.markdown("#### 📋 카테고리별 바이오마커")
            for cat, items in categories.items():
                with st.expander(f"**{cat}** ({len(items)}종)"):
                    for item in items:
                        st.markdown(f"- **{item['name']}** ({item['count']}건)")

        # 바이오마커-타겟 매트릭스
        bm_target = _biomarker_data.get('biomarker_target_matrix', {})
        if bm_target:
            st.markdown("#### 🔗 바이오마커-타겟 연관성")
            # 상위 10개 바이오마커만
            top_bm_names = [b['name'] for b in top_bm[:10]]
            for bm_name in top_bm_names:
                targets = bm_target.get(bm_name, {})
                if targets:
                    with st.expander(f"🧬 {bm_name} → 관련 타겟"):
                        for t, cnt in sorted(targets.items(), key=lambda x: -x[1])[:5]:
                            st.markdown(f"- **{t}** ({cnt}건)")

        # 바이오마커-경로
        bm_pathways = _biomarker_data.get('biomarker_pathways', {})
        if bm_pathways:
            st.markdown("#### 🛤️ 바이오마커-경로 연관성")
            for bm_name in top_bm_names[:5]:
                paths = bm_pathways.get(bm_name, {})
                if paths:
                    with st.expander(f"🧬 {bm_name} → 관련 경로"):
                        for p, cnt in sorted(paths.items(), key=lambda x: -x[1]):
                            st.markdown(f"- {p} ({cnt}건)")
    else:
        st.info("🧬 아직 바이오마커 분석이 실행되지 않았습니다.")
        st.markdown("""
        **실행 방법:**
        - 로컬: `python scripts/12_biomarker_analysis.py`
        - 자동: 매일 GitHub Actions에서 자동 실행
        """)


# ============================================================
# 탭 11: 📈 연구 동향 (Research Trends)
# ============================================================
with tab11:
    st.markdown("### 📈 AGA 연구 동향")
    st.caption("논문 수집 트렌드, 핫 키워드, 연도별 분포 분석")

    # collection_log.json 로드
    _trend_log = []
    for d in _search_dirs:
        cl_path = os.path.join(d, "collection_log.json")
        if os.path.exists(cl_path):
            try:
                with open(cl_path, "r", encoding="utf-8") as f:
                    _trend_log = json.load(f)
                break
            except Exception:
                pass

    if _trend_log and len(_trend_log) > 0:
        st.success(f"총 {len(_trend_log)}건 수집 기록")

        # 수집 출처별 분류
        papers = sum(1 for x in _trend_log if 'pmid' in x)
        patents = sum(1 for x in _trend_log if 'patent_number' in x)
        biorxiv = sum(1 for x in _trend_log if x.get('source') == 'biorxiv')
        other = len(_trend_log) - papers - patents - biorxiv

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📄 논문", papers)
        c2.metric("📜 특허", patents)
        c3.metric("🔬 Preprint", biorxiv)
        c4.metric("📁 기타", other)

        # 수집 날짜별 트렌드
        import plotly.express as px

        dates = []
        for entry in _trend_log:
            d_str = entry.get('collected_at', entry.get('date', ''))
            if d_str:
                try:
                    dates.append(d_str[:10])
                except Exception:
                    pass

        if dates:
            date_counts = Counter(dates)
            date_df = pd.DataFrame([
                {"날짜": k, "수집 건수": v}
                for k, v in sorted(date_counts.items())
            ])
            if not date_df.empty:
                st.markdown("#### 📅 일별 수집 현황")
                fig = px.bar(date_df, x='날짜', y='수집 건수',
                           title='일별 논문/특허 수집 현황')
                fig.update_layout(height=350)
                st.plotly_chart(fig, use_container_width=True)

        # 핫 키워드 분석 (제목에서 추출)
        all_titles = []
        for entry in _trend_log:
            title = entry.get('title', '')
            if title:
                all_titles.append(title.lower())

        if all_titles:
            # 핫 키워드 추출
            import re as _re
            stop_words = {'the', 'a', 'an', 'of', 'in', 'for', 'and', 'or', 'to', 'with',
                         'by', 'on', 'is', 'are', 'was', 'were', 'from', 'at', 'as', 'its',
                         'that', 'this', 'be', 'it', 'not', 'but', 'has', 'have', 'had',
                         'no', 'can', 'may', 'via', 'through', 'between', 'using', 'based'}
            word_counts = Counter()
            for title in all_titles:
                words = _re.findall(r'[a-z]{3,}', title)
                for w in words:
                    if w not in stop_words:
                        word_counts[w] += 1

            if word_counts:
                st.markdown("#### 🔥 핫 키워드 (제목 기반)")
                kw_df = pd.DataFrame([
                    {"키워드": k, "빈도": v}
                    for k, v in word_counts.most_common(30)
                ])
                fig = px.bar(kw_df, x='빈도', y='키워드', orientation='h',
                           title='제목에서 추출된 핵심 키워드 Top 30',
                           color='빈도', color_continuous_scale='Reds')
                fig.update_layout(height=600, yaxis={'categoryorder': 'total ascending'})
                st.plotly_chart(fig, use_container_width=True)

        # 연도별 분포 (출판 연도)
        years = []
        for entry in _trend_log:
            year = entry.get('year', entry.get('pub_year', ''))
            if year:
                try:
                    years.append(int(str(year)[:4]))
                except Exception:
                    pass

        if years:
            year_counts = Counter(years)
            year_df = pd.DataFrame([
                {"연도": k, "논문 수": v}
                for k, v in sorted(year_counts.items())
                if k >= 2000
            ])
            if not year_df.empty:
                st.markdown("#### 📅 연도별 출판 분포")
                fig = px.line(year_df, x='연도', y='논문 수',
                            title='AGA 관련 논문 출판 연도 분포',
                            markers=True)
                fig.update_layout(height=350)
                st.plotly_chart(fig, use_container_width=True)
    else:
        # collection_log.json이 없어도 AGA_data.xlsx에서 기본 통계
        st.info("📈 수집 로그가 없습니다. 기본 문헌 통계를 표시합니다.")
        if 'df_ok' in dir():
            c1, c2 = st.columns(2)
            c1.metric("총 문헌 수", len(df_ok))
            doc_types = df_ok['문서유형'].value_counts() if '문서유형' in df_ok.columns else pd.Series()
            if not doc_types.empty:
                c2.metric("문서 유형 수", len(doc_types))


# ============================================================
# 탭 12: ⚡ AGA-성기능장애 공동 타겟/바이오마커
# ============================================================
with tab12:
    import plotly.express as px
    import plotly.graph_objects as go

    st.markdown("### ⚡ AGA-성기능장애 공동 타겟 & 바이오마커 발굴")
    st.caption("AGA(탈모) 치료제의 성기능 부작용 메커니즘 분석 — 5α-Reductase 억제제(Finasteride/Dutasteride)를 중심으로")

    # ─── 공동 타겟 데이터 ──────────────────────────
    SHARED_TARGETS = {
        "5α-Reductase (SRD5A1/2)": {
            "pdb": "7BW1", "uniprot": "P31213",
            "aga_role": "Testosterone → DHT 변환 효소. AGA에서 DHT가 모낭 miniaturization 유발",
            "sd_role": "DHT는 음경 해면체 NO/cGMP 경로 유지, 전립선 기능 조절에 필수. 억제 시 발기부전 유발 가능",
            "drugs": ["Finasteride (1mg)", "Dutasteride (0.5mg)"],
            "mechanism": "Type II 억제 → 혈중 DHT 60-70% 감소 → 모낭 보호 but 해면체 기능 저하",
            "evidence": "Post-Finasteride Syndrome (PFS): 복용 중단 후에도 지속되는 성기능장애",
            "category": "Enzyme",
            "color": "#e94560",
        },
        "Androgen Receptor (AR)": {
            "pdb": "1E3G", "uniprot": "P10275",
            "aga_role": "DHT 결합 → 모유두세포 apoptosis, 모낭 축소 신호 전달",
            "sd_role": "음경 해면체 평활근, 전립선 상피세포의 정상 기능 유지. AR signaling 저하 → 발기부전, 사정장애",
            "drugs": ["Enzalutamide", "Bicalutamide", "Abiraterone"],
            "mechanism": "AR antagonism → AGA 개선 but 성기능 전반 저하",
            "evidence": "전립선암 ADT(Androgen Deprivation Therapy) 환자 80%+ 성기능장애 보고",
            "category": "Nuclear Receptor",
            "color": "#ff6b35",
        },
        "PDE5 (Phosphodiesterase 5)": {
            "pdb": "1TBF", "uniprot": "O76074",
            "aga_role": "모유두 혈관 확장 → 모낭 영양공급. Minoxidil과 유사 메커니즘 (혈류 개선)",
            "sd_role": "cGMP 분해 효소. PDE5 억제 → cGMP 축적 → 해면체 평활근 이완 → 발기 유지",
            "drugs": ["Sildenafil (Viagra)", "Tadalafil (Cialis)", "Vardenafil (Levitra)"],
            "mechanism": "PDE5i → NO/cGMP ↑ → 혈관 확장 (발기 + 모낭 혈류 동시 개선 가능)",
            "evidence": "Tadalafil daily (5mg)가 BPH+ED 동시 치료. 두피 혈류 개선 AGA 임상 시도 중",
            "category": "Enzyme",
            "color": "#4ecdc4",
        },
        "Nitric Oxide Synthase (NOS/eNOS)": {
            "pdb": "4D1O", "uniprot": "P29474",
            "aga_role": "NO 생성 → 모유두 혈관확장, 모낭 성장기(anagen) 촉진. Minoxidil의 핵심 작용점",
            "sd_role": "해면체 신경 말단 NO 방출 → cGMP 생성 → 발기 핵심 신호. eNOS 저하 = ED",
            "drugs": ["Minoxidil (간접)", "L-Arginine", "L-Citrulline"],
            "mechanism": "NO pathway는 모발 성장과 발기 기능 모두의 공통 필수 경로",
            "evidence": "eNOS knockout mice: 탈모 + ED 동시 발현",
            "category": "Enzyme",
            "color": "#45b7d1",
        },
        "TGF-β1": {
            "pdb": "3KFD", "uniprot": "P01137",
            "aga_role": "모낭 퇴행기(catagen) 유도, 모유두세포 apoptosis 촉진",
            "sd_role": "해면체 섬유화(fibrosis) 유발 → 평활근 대체 → 정맥 폐쇄 부전 → ED",
            "drugs": ["Pirfenidone", "Losartan (간접)"],
            "mechanism": "TGF-β1 과발현 → 모낭 위축 + 해면체 섬유화 (공통 조직 리모델링)",
            "evidence": "Peyronie's disease(음경 섬유화)와 AGA 동시 이환율 높음",
            "category": "Growth Factor",
            "color": "#96ceb4",
        },
        "Testosterone / DHT": {
            "pdb": None, "uniprot": None,
            "aga_role": "DHT가 모낭 AR 활성화 → miniaturization. 핵심 병인 호르몬",
            "sd_role": "Testosterone: 성욕(libido), 발기기능, 정자생성에 필수. DHT: 전립선 성장 조절",
            "drugs": ["TRT (Testosterone Replacement)", "Finasteride", "Dutasteride"],
            "mechanism": "5ARI로 DHT 억제 → AGA 치료 but T/DHT 균형 파괴 → 성기능장애",
            "evidence": "Finasteride 복용자 2-5% 성기능장애 보고. 일부에서 복용 중단 후에도 지속(PFS)",
            "category": "Hormone",
            "color": "#ffeaa7",
        },
        "Wnt/β-catenin": {
            "pdb": "1JDH", "uniprot": "P35222",
            "aga_role": "모낭 줄기세포 활성화, 모발 신생(neogenesis) 핵심 경로",
            "sd_role": "해면체 평활근 재생, 전립선 상피세포 분화에 관여",
            "drugs": ["Valproic acid", "CXXC5-Dvl PPI inhibitor", "Lithium"],
            "mechanism": "Wnt 활성화 → 모낭 재생 + 해면체 조직 항상성 유지",
            "evidence": "Wnt agonist가 해면체 평활근 재생 촉진 (전임상)",
            "category": "Signaling Pathway",
            "color": "#dfe6e9",
        },
        "JAK-STAT Pathway": {
            "pdb": "6BBU", "uniprot": "P23458",
            "aga_role": "면역세포 매개 모낭 공격(Alopecia Areata). AGA에서도 미세염증 기여",
            "sd_role": "전립선 염증, 해면체 염증 → ED. JAK 억제제가 항염증으로 ED 개선 가능성",
            "drugs": ["Ruxolitinib", "Tofacitinib", "Baricitinib"],
            "mechanism": "JAK-STAT 억제 → 모낭 주위 & 해면체 염증 동시 완화",
            "evidence": "Ruxolitinib topical이 AA 치료 승인. ED 동반 환자에서 효과 관찰 사례",
            "category": "Signaling Pathway",
            "color": "#a29bfe",
        },
        "VEGF/VEGFR": {
            "pdb": "1FLT", "uniprot": "P15692",
            "aga_role": "모유두 혈관신생(angiogenesis) → 모낭 영양공급. Minoxidil 작용 경로",
            "sd_role": "해면체 혈관내피 기능 유지. VEGF 저하 → 해면체 혈류 부족 → ED",
            "drugs": ["Minoxidil", "Bevacizumab (anti-VEGF, ED 유발)"],
            "mechanism": "VEGF signaling이 모낭과 해면체 모두에서 혈관 항상성 유지",
            "evidence": "항암 anti-VEGF 치료 환자에서 탈모 + ED 동시 발생",
            "category": "Growth Factor",
            "color": "#fd79a8",
        },
        "IL-6 / TNF-α (Inflammatory Cytokines)": {
            "pdb": "1ALU", "uniprot": "P05231",
            "aga_role": "모낭 주위 미세염증(perifollicular inflammation) → 모낭 퇴행 촉진",
            "sd_role": "해면체 내피세포 손상, eNOS 발현 억제 → NO 감소 → ED",
            "drugs": ["Anti-IL-6 (Tocilizumab)", "Anti-TNF-α (Adalimumab)"],
            "mechanism": "만성 저등급 염증이 모낭 위축과 혈관내피 기능장애를 동시에 유발",
            "evidence": "MetS(대사증후군) 환자에서 AGA+ED 동시 이환율 현저히 높음",
            "category": "Cytokine",
            "color": "#fab1a0",
        },
    }

    SHARED_BIOMARKERS = [
        {"name": "혈중 DHT", "type": "Hormonal", "aga": "↑ 두피 → 모낭 축소", "sd": "↓ 전신 → 성기능저하",
         "clinical": "5ARI 복용 후 60-70% 감소. 모니터링 필수"},
        {"name": "Free Testosterone", "type": "Hormonal", "aga": "→ DHT 전구체", "sd": "↓ → 성욕감퇴, ED",
         "clinical": "5ARI 복용 시 Free T 변화 모니터링"},
        {"name": "eNOS 활성도", "type": "Enzymatic", "aga": "↓ → 모유두 혈류 감소", "sd": "↓ → 해면체 NO 감소 → ED",
         "clinical": "FMD(Flow-Mediated Dilation) 검사로 간접 평가"},
        {"name": "PDE5 발현", "type": "Enzymatic", "aga": "모유두 혈관 긴장도 조절", "sd": "해면체 cGMP 분해 조절",
         "clinical": "PDE5i 반응성 예측 바이오마커"},
        {"name": "TGF-β1", "type": "Growth Factor", "aga": "↑ → catagen 유도", "sd": "↑ → 해면체 섬유화",
         "clinical": "혈청/조직 TGF-β1로 섬유화 진행 평가"},
        {"name": "IL-6 / hs-CRP", "type": "Inflammatory", "aga": "↑ → 미세염증", "sd": "↑ → 내피기능장애",
         "clinical": "만성 염증 바이오마커. MetS 동반 시 특히 유용"},
        {"name": "IIEF-5 Score", "type": "Clinical", "aga": "N/A (간접 모니터링)", "sd": "발기기능 정량 평가",
         "clinical": "5ARI 처방 전후 IIEF-5 비교 필수"},
        {"name": "SHBG (Sex Hormone-Binding Globulin)", "type": "Hormonal", "aga": "Free T 조절", "sd": "↑ → Free T ↓ → 성기능 저하",
         "clinical": "호르몬 패널에 포함. 5ARI 영향 모니터링"},
        {"name": "Neurosteroid Panel (Allopregnanolone)", "type": "Neurological", "aga": "5α-Reductase 관여", "sd": "↓ → 우울, 성욕감퇴 (PFS 핵심)",
         "clinical": "PFS 진단 후보 바이오마커. CSF/혈청 측정"},
    ]

    # ─── 개요 카드 ──────────────────────────
    st.markdown("""
    <div style='background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
         padding: 20px; border-radius: 12px; margin-bottom: 20px; border-left: 4px solid #e94560;'>
        <h4 style='color: #e94560; margin:0 0 8px 0;'>왜 AGA와 성기능장애를 함께 연구하는가?</h4>
        <p style='color: #eee; font-size: 14px; line-height: 1.7; margin:0;'>
        AGA 1차 치료제인 <b>Finasteride</b>와 <b>Dutasteride</b>는 5α-Reductase를 억제하여 DHT 생성을 차단합니다.
        그러나 DHT는 모낭뿐 아니라 <b>음경 해면체, 전립선, 신경스테로이드 합성</b>에도 핵심 역할을 합니다.<br>
        복용자의 2-5%에서 <b>발기부전, 성욕감퇴, 사정장애</b>가 보고되며, 일부에서는 복용 중단 후에도
        증상이 지속되는 <b>Post-Finasteride Syndrome(PFS)</b>이 발생합니다.<br><br>
        이 탭에서는 AGA와 성기능장애의 <b>공유 분자 타겟</b>과 <b>바이오마커</b>를 분석하여,
        <b>성기능 부작용 없는 차세대 AGA 치료제</b> 개발 전략을 도출합니다.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ─── 공동 타겟 개수 KPI ──────────────────────────
    _cat_counts = {}
    for t, info in SHARED_TARGETS.items():
        cat = info["category"]
        _cat_counts[cat] = _cat_counts.get(cat, 0) + 1

    kpi_cols = st.columns(5)
    kpi_cols[0].metric("공동 타겟", f"{len(SHARED_TARGETS)}개")
    kpi_cols[1].metric("공동 바이오마커", f"{len(SHARED_BIOMARKERS)}개")
    kpi_cols[2].metric("관련 약물", f"{sum(len(v['drugs']) for v in SHARED_TARGETS.values())}종")
    kpi_cols[3].metric("Enzyme 타겟", f"{_cat_counts.get('Enzyme', 0)}개")
    kpi_cols[4].metric("Pathway 타겟", f"{_cat_counts.get('Signaling Pathway', 0)}개")

    st.markdown("---")

    # ─── 공동 타겟 네트워크 시각화 ──────────────────
    st.markdown("#### 🕸️ AGA ↔ 성기능장애 공동 타겟 네트워크")

    # Sankey Diagram
    labels = ["AGA (탈모)"] + list(SHARED_TARGETS.keys()) + ["성기능장애 (ED)"]
    source_idx = []
    target_idx = []
    values = []
    colors = []

    for i, (tname, tinfo) in enumerate(SHARED_TARGETS.items()):
        mid_idx = i + 1
        # AGA → Target
        source_idx.append(0)
        target_idx.append(mid_idx)
        values.append(len(tinfo["drugs"]) + 1)
        colors.append(tinfo["color"])
        # Target → SD
        source_idx.append(mid_idx)
        target_idx.append(len(SHARED_TARGETS) + 1)
        values.append(len(tinfo["drugs"]) + 1)
        colors.append(tinfo["color"])

    fig_sankey = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15, thickness=20,
            label=labels,
            color=["#e94560"] + [v["color"] for v in SHARED_TARGETS.values()] + ["#4ecdc4"],
        ),
        link=dict(source=source_idx, target=target_idx, value=values, color=colors),
    )])
    fig_sankey.update_layout(
        title="AGA ← 공동 타겟 → 성기능장애 (Sankey Diagram)",
        height=500, font=dict(size=12),
        paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
        font_color="#e6edf3",
    )
    st.plotly_chart(fig_sankey, use_container_width=True)

    # ─── 타겟 상세 카드 ──────────────────────────
    st.markdown("---")
    st.markdown("#### 🎯 공동 타겟 상세 분석")

    sel_shared = st.selectbox("공동 타겟 선택", list(SHARED_TARGETS.keys()),
                              format_func=lambda x: f"{x} ({SHARED_TARGETS[x]['category']})")

    if sel_shared:
        sinfo = SHARED_TARGETS[sel_shared]

        # 2열: 정보 + 3D 구조
        col_detail, col_3d = st.columns([1, 1])

        with col_detail:
            st.markdown(f"""
            <div style='background: #161b22; padding: 16px; border-radius: 10px; border-left: 4px solid {sinfo["color"]};'>
                <h4 style='color: {sinfo["color"]}; margin:0 0 10px 0;'>{sel_shared}</h4>
                <p style='color: #8b949e; font-size: 12px;'>Category: {sinfo["category"]}
                {f' | PDB: {sinfo["pdb"]}' if sinfo["pdb"] else ''}
                {f' | UniProt: {sinfo["uniprot"]}' if sinfo["uniprot"] else ''}</p>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("##### AGA에서의 역할")
            st.info(sinfo["aga_role"])

            st.markdown("##### 성기능장애에서의 역할")
            st.warning(sinfo["sd_role"])

            st.markdown("##### 작용 메커니즘 (교차점)")
            st.success(sinfo["mechanism"])

            st.markdown("##### 근거 (Evidence)")
            st.caption(sinfo["evidence"])

            st.markdown("##### 관련 약물")
            for drug in sinfo["drugs"]:
                st.markdown(f"- 💊 **{drug}**")

        with col_3d:
            if sinfo["pdb"]:
                st.markdown(f"##### {sel_shared} 3D 단백질 구조")
                pdb_id = sinfo["pdb"]
                _viewer_html = f"""
                <!DOCTYPE html>
                <html><head>
                <style>
                  body {{ margin:0; padding:0; background:#0a0e27; overflow:hidden; }}
                  #viewer {{ width:100%; height:440px; }}
                  #info {{ text-align:center; padding:6px; color:#8b949e; font-size:11px; }}
                  #info a {{ color:#58a6ff; }}
                  #loading {{ position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); color:#58a6ff; font-size:14px; }}
                </style>
                </head><body>
                <div style="position:relative; width:100%; height:480px;">
                  <div id="viewer"></div>
                  <div id="loading">⏳ Loading 3D structure...</div>
                  <div id="info">
                    PDB: <a href="https://www.rcsb.org/structure/{pdb_id}" target="_blank">{pdb_id}</a>
                    {f' | UniProt: <a href="https://www.uniprot.org/uniprot/{sinfo["uniprot"]}" target="_blank">{sinfo["uniprot"]}</a>' if sinfo["uniprot"] else ''}
                  </div>
                </div>
                <script src="https://3Dmol.org/build/3Dmol-min.js"></script>
                <script>
                function initViewer() {{
                  if (typeof $3Dmol === 'undefined') {{
                    setTimeout(initViewer, 200);
                    return;
                  }}
                  var el = document.getElementById("viewer");
                  var viewer = $3Dmol.createViewer(el, {{ backgroundColor: 0x0a0e27, antialias: true }});
                  fetch("https://files.rcsb.org/download/{pdb_id}.pdb")
                    .then(function(r) {{ return r.text(); }})
                    .then(function(data) {{
                      document.getElementById("loading").style.display = "none";
                      viewer.addModel(data, "pdb");
                      viewer.setStyle({{}}, {{cartoon: {{color: "spectrum", opacity: 0.85}}}});
                      viewer.addSurface($3Dmol.SurfaceType.VDW, {{opacity: 0.12, color: "{sinfo['color']}"}});
                      viewer.zoomTo();
                      viewer.spin("y", 0.5);
                      viewer.render();
                    }})
                    .catch(function(err) {{
                      document.getElementById("loading").innerHTML = "❌ PDB load failed: " + err.message;
                    }});
                }}
                initViewer();
                </script>
                </body></html>
                """
                st.components.v1.html(_viewer_html, height=520)

                _lc1, _lc2, _lc3 = st.columns(3)
                _lc1.markdown(f"[🔗 RCSB PDB](https://www.rcsb.org/structure/{pdb_id})")
                if sinfo["uniprot"]:
                    _lc2.markdown(f"[🔗 UniProt](https://www.uniprot.org/uniprot/{sinfo['uniprot']})")
                    _lc3.markdown(f"[🔗 AlphaFold](https://alphafold.ebi.ac.uk/entry/{sinfo['uniprot']})")
            else:
                st.info(f"{sel_shared}는 호르몬/대사체로 단일 단백질 구조가 아닙니다.")
                st.markdown("관련 수용체(AR)의 3D 구조를 참조하세요.")

    # ─── 공동 바이오마커 테이블 ──────────────────────
    st.markdown("---")
    st.markdown("#### 🧬 공동 바이오마커 패널")
    st.caption("AGA 치료 시 성기능 부작용 모니터링을 위한 바이오마커")

    bm_df = pd.DataFrame(SHARED_BIOMARKERS)
    bm_df.columns = ["바이오마커", "유형", "AGA 의의", "성기능장애 의의", "임상적 활용"]

    st.dataframe(bm_df, use_container_width=True, height=400,
                 column_config={
                     "바이오마커": st.column_config.TextColumn("바이오마커", width="medium"),
                     "유형": st.column_config.TextColumn("유형", width="small"),
                     "AGA 의의": st.column_config.TextColumn("AGA", width="large"),
                     "성기능장애 의의": st.column_config.TextColumn("성기능장애", width="large"),
                     "임상적 활용": st.column_config.TextColumn("임상 활용", width="large"),
                 })

    # ─── 치료 전략 제안 ──────────────────────────
    st.markdown("---")
    st.markdown("#### 💡 차세대 AGA 치료 전략 (성기능 부작용 최소화)")

    strategies = [
        {"전략": "Topical 5ARI (두피 국소 투여)",
         "원리": "Finasteride/Dutasteride를 나노캐리어(리포좀, PLGA)로 모낭 표적 전달 → 전신 DHT 영향 최소화",
         "장점": "모낭 DHT만 선택적 억제, 혈중 DHT 유지 → 성기능 보존",
         "근거": "Topical Finasteride 0.25% Phase 3: 두피 DHT 40% ↓, 혈중 DHT 불변",
         "단계": "Phase 3"},
        {"전략": "Selective AR Modulators (SARMs for scalp)",
         "원리": "모낭 AR만 선택적 길항 → 해면체/전립선 AR 기능 유지",
         "장점": "조직 선택적 안드로겐 조절",
         "근거": "GT-0918 (Proxalutamide) 탈모 적응증 연구 중",
         "단계": "Preclinical"},
        {"전략": "Wnt Agonist + PDE5i 병용",
         "원리": "Wnt 활성화(모낭 재생) + PDE5i(혈류 개선) → 모발 성장 + 발기기능 동시 개선",
         "장점": "5ARI 없이 모발 성장 촉진 + 성기능 보호",
         "근거": "Valproic acid(Wnt) + Tadalafil(PDE5i) 전임상 시너지 확인",
         "단계": "Preclinical"},
        {"전략": "JAK Inhibitor (Topical)",
         "원리": "모낭 주위 미세염증 억제 → 모낭 보호, 해면체 염증도 완화",
         "장점": "호르몬 경로 비의존적 → 성기능 부작용 없음",
         "근거": "Ruxolitinib cream (AA 승인), AGA Phase 2 진행 중",
         "단계": "Phase 2"},
        {"전략": "Neurosteroid 보충 (PFS 대응)",
         "원리": "Allopregnanolone 보충 → 5ARI로 감소된 neurosteroid 복원",
         "장점": "PFS 증상(우울, 성기능장애) 직접 개선",
         "근거": "Brexanolone (allopregnanolone) FDA 승인 (PPD). PFS 적용 연구 중",
         "단계": "Phase 1 (PFS)"},
    ]

    for i, s in enumerate(strategies, 1):
        with st.expander(f"전략 {i}: {s['전략']} ({s['단계']})", expanded=(i <= 2)):
            st.markdown(f"**원리:** {s['원리']}")
            st.markdown(f"**장점:** {s['장점']}")
            st.markdown(f"**근거:** {s['근거']}")

    # ─── 데이터 내보내기 ──────────────────────────
    st.markdown("---")
    report_text = f"""# AGA-성기능장애 공동 타겟 분석 보고서
생성일: {datetime.now().strftime('%Y-%m-%d')}

## 공동 타겟 ({len(SHARED_TARGETS)}개)
"""
    for tname, tinfo in SHARED_TARGETS.items():
        report_text += f"""
### {tname} ({tinfo['category']})
- **AGA 역할:** {tinfo['aga_role']}
- **성기능장애 역할:** {tinfo['sd_role']}
- **메커니즘:** {tinfo['mechanism']}
- **근거:** {tinfo['evidence']}
- **관련 약물:** {', '.join(tinfo['drugs'])}
"""

    report_text += f"""
## 공동 바이오마커 ({len(SHARED_BIOMARKERS)}개)
"""
    for bm in SHARED_BIOMARKERS:
        report_text += f"- **{bm['name']}** ({bm['type']}): AGA={bm['aga']} / SD={bm['sd']} / 활용={bm['clinical']}\n"

    st.download_button("📥 공동타겟 보고서 다운로드 (.md)",
                      report_text, "AGA_SD_shared_targets_report.md", "text/markdown")


# ============================================================
# 탭 13: 🏢 Control Center (픽셀 아트 가상 사무실)
# ============================================================
with tab13:
    st.markdown("### 🏢 AGA Research Control Center")
    st.caption("AI 에이전트들이 자동으로 논문을 수집·분석하고 있습니다.")

    # ── 자동 수집 버튼 & 스냅샷 기록 ─────────────────────
    import subprocess as _subp

    _snap_path = os.path.join(BASE_FOLDER, "aga_knowledge_db", "snapshot_history.json")
    _kb_meta_path = os.path.join(BASE_FOLDER, "aga_knowledge_db", "metadata.json")

    def _load_snapshots():
        if os.path.exists(_snap_path):
            try:
                with open(_snap_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save_snapshots(snaps):
        try:
            os.makedirs(os.path.dirname(_snap_path), exist_ok=True)
            with open(_snap_path, "w", encoding="utf-8") as f:
                json.dump(snaps, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _current_snapshot():
        total_chunks = 0
        if os.path.exists(_kb_meta_path):
            try:
                with open(_kb_meta_path, "r", encoding="utf-8") as f:
                    m = json.load(f)
                total_chunks = int(m.get("total_chunks", 0))
            except Exception:
                pass
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "time": datetime.now().strftime("%H:%M:%S"),
            "ai_analyzed": int(len(df_ok)),
            "total_chunks": int(total_chunks),
        }

    def _record_snapshot_if_new():
        """오늘 스냅샷이 없거나 값이 변했으면 추가"""
        snaps = _load_snapshots()
        cur = _current_snapshot()
        if snaps:
            last = snaps[-1]
            if (last.get("date") == cur["date"]
                and last.get("ai_analyzed") == cur["ai_analyzed"]
                and last.get("total_chunks") == cur["total_chunks"]):
                return snaps
            # 같은 날짜에 값이 바뀐 경우 업데이트(교체)
            if last.get("date") == cur["date"]:
                snaps[-1] = cur
                _save_snapshots(snaps)
                return snaps
        snaps.append(cur)
        _save_snapshots(snaps)
        return snaps

    snapshots = _record_snapshot_if_new()

    # 수집 버튼 UI
    bc1, bc2 = st.columns([1, 3])
    with bc1:
        collect_clicked = st.button("🚀 자동 수집 시작", type="primary", use_container_width=True)
    with bc2:
        st.caption("PubMed/특허/bioRxiv → PDF 추출 → AI 분석 → Foundation Model 반영")

    if collect_clicked:
        # 실행 전 스냅샷 저장
        before = _current_snapshot()
        orch_path = os.path.join(BASE_FOLDER, "scripts", "08_orchestrator.py")
        log_dir = os.path.join(BASE_FOLDER, "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file_path = os.path.join(log_dir, f"auto_collect_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

        if os.path.exists(orch_path):
            try:
                # 백그라운드 실행 (오케스트레이터 + KB 재빌드)
                py = sys.executable or "python3"
                cmd = (
                    f'"{py}" "{orch_path}" > "{log_file_path}" 2>&1 && '
                    f'"{py}" "{os.path.join(BASE_FOLDER, "scripts", "build_knowledge_base.py")}" >> "{log_file_path}" 2>&1'
                )
                _subp.Popen(cmd, shell=True, cwd=BASE_FOLDER,
                           stdout=_subp.DEVNULL, stderr=_subp.DEVNULL,
                           start_new_session=True)
                st.session_state["collect_log_path"] = log_file_path
                st.session_state["collecting"] = True
            except Exception as e:
                st.error(f"실행 실패: {e}")
                st.info("Streamlit Cloud 환경에서는 로컬 실행이 제한될 수 있습니다. "
                       "GitHub Actions `workflow_dispatch`로 수동 트리거하거나 로컬에서 실행하세요.")
        else:
            st.error(f"오케스트레이터를 찾을 수 없습니다: {orch_path}")

    # ── 🎮 마인크래프트 스타일 실시간 수집 모니터 ──
    if st.session_state.get("collecting"):
        _log_path = st.session_state.get("collect_log_path", "")
        last_lines = []
        if _log_path and os.path.exists(_log_path):
            try:
                with open(_log_path, "r", encoding="utf-8", errors="ignore") as _lf:
                    _all = _lf.readlines()
                last_lines = [ln.rstrip() for ln in _all[-12:] if ln.strip()]
            except Exception:
                pass

        # 현재 단계 감지
        joined = "\n".join(last_lines).lower()
        if "build_knowledge_base" in joined or "chunk" in joined or "phase" in joined:
            stage_icon = "🧠"
            stage_label = "Foundation Model 반영 중"
            char_mode = "brain"
        elif "pdf" in joined or "extract" in joined or "text" in joined:
            stage_icon = "📄"
            stage_label = "PDF 텍스트 추출 중"
            char_mode = "mine"
        elif "claude" in joined or "analyz" in joined or "ai" in joined:
            stage_icon = "🤖"
            stage_label = "AI 정보 분석 중"
            char_mode = "craft"
        elif "patent" in joined or "특허" in joined:
            stage_icon = "📜"
            stage_label = "특허 데이터 수집 중"
            char_mode = "walk"
        elif "pubmed" in joined or "biorxiv" in joined or "download" in joined or "수집" in joined:
            stage_icon = "🔍"
            stage_label = "PubMed/bioRxiv 논문 수집 중"
            char_mode = "walk"
        elif last_lines:
            stage_icon = "⚙️"
            stage_label = "파이프라인 실행 중"
            char_mode = "walk"
        else:
            stage_icon = "🚀"
            stage_label = "시작 중..."
            char_mode = "idle"

        log_html = "<br>".join(
            f"<span style='color:#8be9fd;'>&gt;</span> {ln.replace('<','&lt;').replace('>','&gt;')[:120]}"
            for ln in last_lines[-8:]
        ) or "<span style='color:#666;'>로그 대기 중...</span>"

        st.markdown(f"""
        <style>
        @keyframes mc-walk {{
            0%, 100% {{ transform: translateX(0) translateY(0); }}
            25% {{ transform: translateX(2px) translateY(-2px); }}
            50% {{ transform: translateX(4px) translateY(0); }}
            75% {{ transform: translateX(2px) translateY(-2px); }}
        }}
        @keyframes mc-swing {{
            0%, 100% {{ transform: rotate(-20deg); }}
            50% {{ transform: rotate(40deg); }}
        }}
        @keyframes mc-bob {{
            0%, 100% {{ transform: translateY(0); }}
            50% {{ transform: translateY(-4px); }}
        }}
        @keyframes mc-blink {{
            0%, 90%, 100% {{ opacity: 1; }}
            95% {{ opacity: 0; }}
        }}
        @keyframes item-fall {{
            0% {{ transform: translateY(-30px); opacity: 0; }}
            20% {{ opacity: 1; }}
            100% {{ transform: translateY(60px); opacity: 0; }}
        }}
        @keyframes cloud-move {{
            0% {{ transform: translateX(-40px); }}
            100% {{ transform: translateX(360px); }}
        }}
        .mc-box {{
            background: linear-gradient(180deg, #87ceeb 0%, #87ceeb 55%, #8b6f47 55%, #8b6f47 70%, #5d4a2e 70%, #5d4a2e 100%);
            border: 4px solid #2c1810;
            border-radius: 6px;
            width: 100%;
            max-width: 640px;
            height: 220px;
            position: relative;
            overflow: hidden;
            box-shadow: inset 0 0 0 2px #d4a373, 0 4px 12px rgba(0,0,0,0.4);
            font-family: 'Courier New', monospace;
            image-rendering: pixelated;
        }}
        .mc-cloud {{
            position: absolute; top: 15px; left: 0;
            width: 50px; height: 14px;
            background: #fff;
            box-shadow: 10px -6px 0 #fff, 26px -6px 0 #fff, 18px -12px 0 #fff,
                        -4px 0 0 #fff, 54px 0 0 #fff;
            animation: cloud-move 18s linear infinite;
        }}
        .mc-cloud.c2 {{ top: 38px; animation-duration: 26s; animation-delay: -8s; }}
        .mc-sun {{
            position: absolute; top: 12px; right: 20px;
            width: 28px; height: 28px;
            background: #ffd93d;
            border: 3px solid #f9a825;
            box-shadow: 0 0 16px rgba(255,217,61,0.6);
        }}
        .mc-stage-label {{
            position: absolute; top: 8px; left: 12px;
            color: #fff; font-size: 14px; font-weight: bold;
            text-shadow: 2px 2px 0 #000, -1px -1px 0 #000, 1px -1px 0 #000, -1px 1px 0 #000;
            z-index: 5;
        }}
        .mc-char {{
            position: absolute; bottom: 62px; left: 48%;
            width: 24px; height: 48px;
            animation: {"mc-walk 0.6s steps(2) infinite" if char_mode=="walk" else "mc-bob 1.2s ease-in-out infinite"};
            z-index: 3;
        }}
        .mc-head {{
            position: absolute; top: 0; left: 2px;
            width: 20px; height: 20px;
            background: #c68642;
            border: 1px solid #5d3a1a;
            animation: mc-blink 4s infinite;
        }}
        .mc-head::before {{
            content: ''; position: absolute; top: 5px; left: 3px;
            width: 3px; height: 4px; background: #fff;
            box-shadow: 8px 0 0 #fff, 3px 0 0 #000, 11px 0 0 #000;
        }}
        .mc-head::after {{
            content: ''; position: absolute; top: 13px; left: 6px;
            width: 8px; height: 2px; background: #5d3a1a;
        }}
        .mc-body {{
            position: absolute; top: 20px; left: 4px;
            width: 16px; height: 18px;
            background: #00aced;
            border: 1px solid #004d66;
        }}
        .mc-legs {{
            position: absolute; top: 38px; left: 4px;
            width: 16px; height: 10px;
            background: #3a3a8a;
            border: 1px solid #1a1a4a;
        }}
        .mc-arm {{
            position: absolute; top: 20px; right: -4px;
            width: 6px; height: 14px;
            background: #c68642;
            border: 1px solid #5d3a1a;
            transform-origin: top center;
            animation: {"mc-swing 0.4s ease-in-out infinite" if char_mode in ("mine","craft","brain") else "none"};
        }}
        .mc-tool {{
            position: absolute; top: 30px; right: -14px;
            font-size: 18px;
            transform-origin: left center;
            animation: {"mc-swing 0.4s ease-in-out infinite" if char_mode in ("mine","craft","brain") else "none"};
        }}
        .mc-item {{
            position: absolute; top: 50px;
            font-size: 18px;
            animation: item-fall 1.8s ease-in infinite;
        }}
        .mc-item.i1 {{ left: 20%; animation-delay: 0s; }}
        .mc-item.i2 {{ left: 35%; animation-delay: 0.4s; }}
        .mc-item.i3 {{ left: 65%; animation-delay: 0.8s; }}
        .mc-item.i4 {{ left: 80%; animation-delay: 1.2s; }}
        .mc-chest {{
            position: absolute; bottom: 20px; right: 30px;
            width: 36px; height: 28px;
            background: linear-gradient(180deg, #a0522d 0%, #a0522d 40%, #8b4513 40%, #8b4513 100%);
            border: 2px solid #3e2311;
            box-shadow: inset 0 0 0 2px #d2691e;
            animation: mc-bob 2s ease-in-out infinite;
        }}
        .mc-chest::before {{
            content: '🔒'; position: absolute; top: 8px; left: 12px;
            font-size: 10px;
        }}
        .mc-tree {{
            position: absolute; bottom: 58px; left: 20px;
            width: 6px; height: 16px; background: #5d3a1a;
        }}
        .mc-tree::before {{
            content: ''; position: absolute; top: -22px; left: -11px;
            width: 28px; height: 28px; background: #228b22;
            box-shadow: -6px 4px 0 #228b22, 6px 4px 0 #228b22,
                        0 -6px 0 #2e8b2e;
        }}
        .mc-log-box {{
            background: #0d0d0d;
            border: 2px solid #3e3e3e;
            border-top: 2px solid #00ff41;
            border-radius: 4px;
            padding: 10px 12px;
            margin-top: 8px;
            font-family: 'Courier New', monospace;
            font-size: 11px;
            color: #00ff41;
            max-width: 640px;
            max-height: 150px;
            overflow-y: auto;
            line-height: 1.6;
        }}
        .mc-pulse {{
            display: inline-block;
            width: 8px; height: 8px;
            background: #ff3860;
            border-radius: 50%;
            margin-right: 6px;
            animation: mc-bob 1s ease-in-out infinite;
        }}
        </style>

        <div class="mc-box">
            <div class="mc-stage-label"><span class="mc-pulse"></span>{stage_icon} {stage_label}</div>
            <div class="mc-sun"></div>
            <div class="mc-cloud"></div>
            <div class="mc-cloud c2"></div>
            <div class="mc-tree"></div>

            <div class="mc-item i1">📄</div>
            <div class="mc-item i2">📚</div>
            <div class="mc-item i3">🧬</div>
            <div class="mc-item i4">💊</div>

            <div class="mc-char">
                <div class="mc-head"></div>
                <div class="mc-body"></div>
                <div class="mc-legs"></div>
                <div class="mc-arm"></div>
                <div class="mc-tool">⛏️</div>
            </div>

            <div class="mc-chest"></div>
        </div>

        <div class="mc-log-box">
            {log_html}
        </div>
        """, unsafe_allow_html=True)

        _rc1, _rc2, _rc3 = st.columns([1, 1, 4])
        with _rc1:
            if st.button("🔄 새로고침", key="refresh_collect"):
                st.rerun()
        with _rc2:
            if st.button("✖️ 숨기기", key="hide_collect"):
                st.session_state["collecting"] = False
                st.rerun()
        with _rc3:
            st.caption(f"📝 로그: `{os.path.basename(_log_path) if _log_path else '-'}`")

    # ── 성장 비교 카드 (4/3 100 >> 4/4 200 스타일) ──
    if len(snapshots) >= 2:
        last = snapshots[-1]
        prev = snapshots[-2]

        def _mmdd(d):
            try:
                p = d.split("-")
                return f"{int(p[1])}/{int(p[2])}"
            except Exception:
                return d

        d1 = _mmdd(prev.get("date", ""))
        d2 = _mmdd(last.get("date", ""))
        a1 = prev.get("ai_analyzed", 0)
        a2 = last.get("ai_analyzed", 0)
        c1 = prev.get("total_chunks", 0)
        c2 = last.get("total_chunks", 0)
        diff_a = a2 - a1
        diff_c = c2 - c1
        sign_a = f"+{diff_a}" if diff_a >= 0 else str(diff_a)
        sign_c = f"+{diff_c:,}" if diff_c >= 0 else f"{diff_c:,}"
        color_a = "#4CAF50" if diff_a > 0 else ("#9E9E9E" if diff_a == 0 else "#F44336")
        color_c = "#4CAF50" if diff_c > 0 else ("#9E9E9E" if diff_c == 0 else "#F44336")

        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                    border-radius: 12px; padding: 18px; margin: 12px 0;
                    border: 1px solid rgba(233, 69, 96, 0.3);">
          <div style="color: #888; font-size: 12px; margin-bottom: 8px;">📈 Foundation Model 성장</div>
          <div style="color: #fff; font-size: 20px; font-weight: bold;">
            🧬 AI 분석 논문: {d1} {a1:,} &nbsp;&raquo;&raquo;&nbsp; {d2} {a2:,}개
            <span style="color: {color_a}; font-size: 16px; margin-left: 8px;">({sign_a})</span>
          </div>
          <div style="color: #fff; font-size: 16px; margin-top: 6px;">
            🧠 Vector Chunks: {d1} {c1:,} &nbsp;&raquo;&raquo;&nbsp; {d2} {c2:,}
            <span style="color: {color_c}; font-size: 14px; margin-left: 8px;">({sign_c})</span>
          </div>
        </div>
        """, unsafe_allow_html=True)
    elif len(snapshots) == 1:
        s = snapshots[0]
        st.info(f"📊 현재 상태 저장됨: {s['date']} | AI 분석 {s['ai_analyzed']:,}건 | "
               f"{s['total_chunks']:,} chunks · 수집 후 다시 방문하면 증가분이 표시됩니다.")

    # pipeline_status.json 로딩
    pipeline_status = {}
    for d in _search_dirs:
        ps_path = os.path.join(d, "pipeline_status.json")
        if os.path.exists(ps_path):
            with open(ps_path, "r", encoding="utf-8") as f:
                pipeline_status = json.load(f)
            break

    # collection_log.json 로딩 (수집 통계용)
    collection_log = []
    for d in _search_dirs:
        cl_path = os.path.join(d, "collection_log.json")
        if os.path.exists(cl_path):
            try:
                with open(cl_path, "r", encoding="utf-8") as f:
                    collection_log = json.load(f)
            except Exception:
                pass
            break

    # 에이전트 정의
    agents = [
        {"id": "paper_searcher", "name": "Paper Scout", "icon": "🔍",
         "role": "PubMed/bioRxiv 논문 검색", "desk_color": "#2196F3"},
        {"id": "patent_searcher", "name": "Patent Hunter", "icon": "📜",
         "role": "USPTO/EPO 특허 검색", "desk_color": "#FF9800"},
        {"id": "text_extractor", "name": "Text Miner", "icon": "📄",
         "role": "PDF 텍스트 추출", "desk_color": "#4CAF50"},
        {"id": "claude_analyzer", "name": "AI Analyst", "icon": "🤖",
         "role": "Claude AI 정보 분석", "desk_color": "#E91E63"},
        {"id": "compound_fetcher", "name": "Chem Detective", "icon": "💊",
         "role": "PubChem 구조 수집", "desk_color": "#9C27B0"},
        {"id": "deploy_manager", "name": "Deploy Bot", "icon": "🚀",
         "role": "Streamlit 배포 관리", "desk_color": "#00BCD4"},
    ]

    # 에이전트 상태 결정
    def get_agent_status(agent_id):
        overall = pipeline_status.get("overall_status", "idle")
        current = pipeline_status.get("current_step", "")
        agent_stat = pipeline_status.get(agent_id, {})

        if isinstance(agent_stat, dict):
            return agent_stat.get("status", "idle")

        # 오케스트레이터 상태에서 유추
        step_map = {
            "paper_searcher": "05_pubmed",
            "patent_searcher": "06_특허",
            "text_extractor": "01_pdf",
            "claude_analyzer": "02_정보추출",
            "compound_fetcher": "03_화합물",
            "deploy_manager": "deploy",
        }
        if overall == "running" and step_map.get(agent_id, "") in current:
            return "working"
        return "idle"

    # 상태별 애니메이션 CSS
    status_styles = {
        "working": ("⚡ 작업 중", "#4CAF50", "pulse 1.5s ease-in-out infinite"),
        "searching": ("🔍 검색 중", "#2196F3", "pulse 1.5s ease-in-out infinite"),
        "completed": ("✅ 완료", "#8BC34A", "none"),
        "idle": ("💤 대기 중", "#9E9E9E", "none"),
        "error": ("❌ 오류", "#F44336", "shake 0.5s ease-in-out infinite"),
    }

    # CSS 애니메이션
    st.markdown("""
    <style>
    @keyframes pulse {
        0%, 100% { transform: scale(1); opacity: 1; }
        50% { transform: scale(1.05); opacity: 0.85; }
    }
    @keyframes shake {
        0%, 100% { transform: translateX(0); }
        25% { transform: translateX(-3px); }
        75% { transform: translateX(3px); }
    }
    @keyframes float {
        0%, 100% { transform: translateY(0px); }
        50% { transform: translateY(-5px); }
    }
    @keyframes typing {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.3; }
    }
    .pixel-office {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 60%, #1a1a2e 100%);
        border-radius: 16px;
        padding: 20px;
        margin: 10px 0;
    }
    .agent-desk {
        background: rgba(255,255,255,0.05);
        border-radius: 12px;
        padding: 15px;
        text-align: center;
        border: 2px solid rgba(255,255,255,0.1);
        transition: all 0.3s ease;
        min-height: 180px;
    }
    .agent-desk:hover {
        border-color: rgba(255,255,255,0.3);
        background: rgba(255,255,255,0.08);
    }
    .agent-icon {
        font-size: 48px;
        display: block;
        margin-bottom: 8px;
    }
    .agent-icon.working {
        animation: float 2s ease-in-out infinite;
    }
    .agent-name {
        color: #ffffff;
        font-weight: bold;
        font-size: 14px;
        margin-bottom: 4px;
    }
    .agent-role {
        color: #888;
        font-size: 11px;
        margin-bottom: 8px;
    }
    .status-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 11px;
        font-weight: bold;
    }
    .stat-card {
        background: rgba(255,255,255,0.05);
        border-radius: 10px;
        padding: 12px 16px;
        text-align: center;
        border: 1px solid rgba(255,255,255,0.1);
    }
    .stat-number {
        color: #e94560;
        font-size: 28px;
        font-weight: bold;
    }
    .stat-label {
        color: #888;
        font-size: 12px;
    }
    .log-entry {
        color: #aaa;
        font-size: 12px;
        padding: 4px 0;
        border-bottom: 1px solid rgba(255,255,255,0.05);
    }
    </style>
    """, unsafe_allow_html=True)

    # ── 가상 사무실 ──
    st.markdown('<div class="pixel-office">', unsafe_allow_html=True)

    # 에이전트 그리드 (2행 3열)
    row1 = st.columns(3)
    row2 = st.columns(3)
    all_cols = row1 + row2

    for i, agent in enumerate(agents):
        with all_cols[i]:
            status = get_agent_status(agent["id"])
            status_label, status_color, anim = status_styles.get(status, status_styles["idle"])
            icon_class = "working" if status in ("working", "searching") else ""

            st.markdown(f"""
            <div class="agent-desk" style="border-color: {agent['desk_color']}40;">
                <span class="agent-icon {icon_class}">{agent['icon']}</span>
                <div class="agent-name">{agent['name']}</div>
                <div class="agent-role">{agent['role']}</div>
                <span class="status-badge" style="background: {status_color}20; color: {status_color};">
                    {status_label}
                </span>
            </div>
            """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    # ── 통계 카드 ──
    st.markdown("---")
    total_collected = len(collection_log)
    total_processed = len(df_ok)
    new_this_week = sum(1 for p in collection_log
                       if isinstance(p, dict) and p.get("collected_date", "")[:10] >= (datetime.now().strftime('%Y-%m-%d')[:8] + "01"))

    last_run = pipeline_status.get("last_run", "아직 실행 안 됨")
    steps_done = pipeline_status.get("steps_completed", 0)

    sc1, sc2, sc3, sc4 = st.columns(4)
    with sc1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{total_processed}</div>
            <div class="stat-label">총 분석 논문</div>
        </div>""", unsafe_allow_html=True)
    with sc2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{total_collected}</div>
            <div class="stat-label">자동 수집 논문</div>
        </div>""", unsafe_allow_html=True)
    with sc3:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{len(target_index)}</div>
            <div class="stat-label">발견된 타겟</div>
        </div>""", unsafe_allow_html=True)
    with sc4:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{len(compound_index)}</div>
            <div class="stat-label">발견된 화합물</div>
        </div>""", unsafe_allow_html=True)

    # ── 파이프라인 상태 ──
    st.markdown("---")
    st.markdown("#### 📋 파이프라인 실행 상태")

    overall = pipeline_status.get("overall_status", "대기 중")
    overall_color = {"running": "🟢", "completed": "🔵", "error": "🔴"}.get(overall, "⚪")
    st.markdown(f"{overall_color} **전체 상태:** {overall}")
    st.markdown(f"**마지막 실행:** {last_run}")

    # 단계별 상태
    step_names = [
        ("05_pubmed", "PubMed 논문 수집"),
        ("06_특허", "특허 검색"),
        ("07_biorxiv", "bioRxiv 프리프린트"),
        ("01_pdf", "PDF 텍스트 추출"),
        ("02_정보추출", "Claude AI 분석"),
        ("03_화합물", "PubChem 구조 수집"),
    ]

    steps_status = pipeline_status.get("steps", {})
    for step_id, step_label in step_names:
        step_info = steps_status.get(step_id, {})
        if isinstance(step_info, dict):
            s_status = step_info.get("status", "pending")
            s_duration = step_info.get("duration", "")
            icon = {"completed": "✅", "running": "🔄", "error": "❌"}.get(s_status, "⬜")
            dur_text = f" ({s_duration})" if s_duration else ""
            st.caption(f"{icon} {step_label}{dur_text}")
        else:
            st.caption(f"⬜ {step_label}")

    # ── 최근 활동 로그 ──
    st.markdown("---")
    st.markdown("#### 📊 최근 수집 활동")

    if collection_log:
        # 최근 20건 표시
        recent = sorted(
            [p for p in collection_log if isinstance(p, dict) and p.get("collected_date")],
            key=lambda x: x.get("collected_date", ""),
            reverse=True
        )[:20]

        if recent:
            log_rows = []
            for p in recent:
                log_rows.append({
                    "수집일": p.get("collected_date", "")[:10],
                    "출처": p.get("source", "PubMed"),
                    "제목": (p.get("title", "") or "")[:80],
                    "PDF": "✅" if p.get("pdf_path") else "❌",
                })
            st.dataframe(pd.DataFrame(log_rows), use_container_width=True, height=300)
        else:
            st.info("아직 자동 수집된 논문이 없습니다. 파이프라인을 실행하세요.")
    else:
        st.info("아직 자동 수집된 논문이 없습니다.")
        st.markdown("""
        **시작하는 방법:**
        1. 로컬에서: `python scripts/08_orchestrator.py`
        2. GitHub Actions: 매일 오후 3시(KST) 자동 실행 (설정 필요)
        """)

    # ── GitHub Actions 설정 안내 ──
    with st.expander("⚙️ 자동화 설정 안내"):
        st.markdown("""
        **GitHub Actions로 매일 자동 실행하려면:**

        1. GitHub repo (DCP_AGA)에 아래 파일들을 업로드하세요:
           - `scripts/05_pubmed_collect.py`
           - `scripts/06_patent_collect.py`
           - `scripts/07_biorxiv_collect.py`
           - `scripts/08_orchestrator.py`
           - `.github/workflows/daily_pipeline.yml`

        2. GitHub Secrets 설정 (Settings → Secrets and variables → Actions):
           - `CLAUDE_API_KEY`: Claude API 키
           - `NCBI_API_KEY`: NCBI API 키 (ncbi.nlm.nih.gov에서 무료 발급)

        3. GitHub Actions 탭에서 워크플로우 활성화

        매일 오후 3시(KST)에 자동으로 새 논문을 수집하고 분석합니다.
        """)


# ============================================================
# 탭 14: 🎯 자체 타깃 검증 (내부 발굴 보고서 업로드 → RAG 검증)
# ============================================================
with tab14:
    st.markdown("### 🎯 자체 발굴 타깃 검증")
    st.caption("문헌이 아닌 내부에서 직접 발굴한 타깃 보고서를 업로드하면, "
               "Foundation Model(22K+ 논문 RAG)로 자동 검증·보완합니다.")

    _custom_dir = os.path.join(BASE_FOLDER, "custom_targets")
    os.makedirs(_custom_dir, exist_ok=True)

    # 입력 방식 선택
    input_mode = st.radio(
        "입력 방식",
        ["📄 보고서 업로드 (PDF/DOCX/TXT/MD)", "📝 직접 입력"],
        horizontal=True,
        label_visibility="collapsed",
    )

    report_text = ""
    report_source = ""

    if input_mode.startswith("📄"):
        up = st.file_uploader(
            "보고서 업로드",
            type=["pdf", "docx", "txt", "md"],
            help="내부 발굴 타깃 보고서 파일",
            label_visibility="collapsed",
        )
        if up is not None:
            report_source = up.name
            try:
                name_lower = up.name.lower()
                raw = up.read()
                if name_lower.endswith(".pdf"):
                    try:
                        import pdfplumber
                        import io as _io
                        with pdfplumber.open(_io.BytesIO(raw)) as _pdf:
                            pages = [(p.extract_text() or "") for p in _pdf.pages]
                        report_text = "\n\n".join(pages).strip()
                    except ImportError:
                        st.error("pdfplumber가 필요합니다: `pip install pdfplumber`")
                elif name_lower.endswith(".docx"):
                    try:
                        from docx import Document
                        import io as _io
                        doc = Document(_io.BytesIO(raw))
                        report_text = "\n".join(p.text for p in doc.paragraphs).strip()
                    except ImportError:
                        st.error("python-docx가 필요합니다: `pip install python-docx`")
                else:
                    report_text = raw.decode("utf-8", errors="ignore").strip()
            except Exception as e:
                st.error(f"파일 읽기 실패: {e}")

            if report_text:
                st.success(f"✅ `{up.name}` 로드 완료 ({len(report_text):,} 문자)")
                with st.expander("미리보기 (앞 1,000자)"):
                    st.text(report_text[:1000])
    else:
        col_a, col_b = st.columns(2)
        with col_a:
            _t_name = st.text_input("타깃명", placeholder="예: PRLR, IGFBP5, HSPB1")
            _t_moa = st.text_area("가설 MoA / 기전", height=80,
                                  placeholder="예: PRLR 신호 저해로 DHT 독립적 모낭 위축 억제...")
            _t_pathway = st.text_input("관련 신호전달경로",
                                       placeholder="예: JAK2/STAT5, AR, Wnt/β-catenin")
        with col_b:
            _t_evidence = st.text_area("내부 발굴 근거", height=80,
                                       placeholder="예: 자체 RNA-seq에서 AGA 환자 모낭 2.3배 up-regulated...")
            _t_compound = st.text_input("제안 화합물/modality",
                                        placeholder="예: small-molecule antagonist, siRNA, mAb")
            _t_biomarker = st.text_input("예상 바이오마커",
                                         placeholder="예: 혈중 prolactin, phospho-STAT5")
        if any([_t_name, _t_moa, _t_evidence]):
            report_source = f"manual_{_t_name or 'target'}"
            report_text = (
                f"Target: {_t_name}\n"
                f"Mechanism of Action: {_t_moa}\n"
                f"Pathway: {_t_pathway}\n"
                f"Internal Evidence: {_t_evidence}\n"
                f"Proposed Compound/Modality: {_t_compound}\n"
                f"Biomarker: {_t_biomarker}\n"
            )

    # 검증 실행
    st.markdown("---")
    run = st.button("🔬 자동 검증 실행", type="primary", disabled=not report_text)

    if run and report_text:
        # 1) Knowledge Base 연결
        _expert = None
        try:
            import sys as _sys_v
            _script_dir_v = os.path.join(BASE_FOLDER, "scripts")
            if _script_dir_v not in _sys_v.path:
                _sys_v.path.insert(0, _script_dir_v)
            from aga_ai_engine import AGA_AI_Expert
            _expert = AGA_AI_Expert(api_key=CLAUDE_API_KEY)
        except Exception as _ee:
            st.error(f"Knowledge Base 연결 실패: {_ee}")

        verification_result = {
            "source": report_source,
            "timestamp": datetime.now().isoformat(),
            "entities": {},
            "evidence_papers": [],
            "evidence_structured": [],
            "verification": "",
        }

        # 2) Claude로 엔티티 추출
        entities = {}
        if CLAUDE_API_KEY:
            try:
                import anthropic as _anth
                _client = _anth.Anthropic(api_key=CLAUDE_API_KEY)
                _trim = report_text[:12000]
                extract_prompt = f"""Extract structured entities from this internal target discovery report. Respond ONLY in valid JSON.

Fields:
- targets: list of drug targets (gene/protein names)
- compounds: list of proposed compounds/modalities
- mechanism_of_action: 1-2 sentence MoA summary (Korean)
- pathways: list of signaling pathways
- cell_types: list of cell lines/models mentioned
- biomarkers: list of biomarkers
- key_claims: list of 3-5 core scientific claims (Korean, each 1 sentence)

Report:
{_trim}
"""
                with st.spinner("🧬 보고서에서 핵심 엔티티 추출 중..."):
                    _msg = _client.messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=1500,
                        messages=[{"role": "user", "content": extract_prompt}],
                    )
                    _txt = _msg.content[0].text.strip()
                    if _txt.startswith("```"):
                        _txt = _txt.split("```")[1]
                        if _txt.startswith("json"):
                            _txt = _txt[4:]
                    entities = json.loads(_txt)
                    verification_result["entities"] = entities
            except Exception as _e:
                st.warning(f"엔티티 추출 실패 (계속 진행): {str(_e)[:200]}")

        if entities:
            st.markdown("#### 📋 추출된 핵심 엔티티")
            e1, e2 = st.columns(2)
            with e1:
                st.markdown(f"**🎯 타깃:** {', '.join(entities.get('targets', []) or ['-'])}")
                st.markdown(f"**💊 화합물:** {', '.join(entities.get('compounds', []) or ['-'])}")
                st.markdown(f"**🧪 경로:** {', '.join(entities.get('pathways', []) or ['-'])}")
                st.markdown(f"**🔬 모델:** {', '.join(entities.get('cell_types', []) or ['-'])}")
            with e2:
                st.markdown(f"**📊 바이오마커:** {', '.join(entities.get('biomarkers', []) or ['-'])}")
                st.markdown(f"**⚙️ MoA:** {entities.get('mechanism_of_action', '-')}")
            if entities.get("key_claims"):
                st.markdown("**핵심 주장:**")
                for _ci, _claim in enumerate(entities["key_claims"], 1):
                    st.caption(f"{_ci}. {_claim}")

        # 3) Foundation Model RAG 검증
        papers_hits, struct_hits = [], []
        if _expert:
            try:
                query_parts = []
                if entities:
                    query_parts += (entities.get("targets") or [])
                    query_parts += (entities.get("compounds") or [])
                    query_parts += (entities.get("pathways") or [])
                    if entities.get("mechanism_of_action"):
                        query_parts.append(entities["mechanism_of_action"])
                if not query_parts:
                    query_parts = [report_text[:500]]
                query = " ".join(str(x) for x in query_parts)[:1500]

                with st.spinner("🔎 Foundation Model에서 근거 검색 중 (22K+ 논문)..."):
                    rag = _expert.retrieve(query, n_papers=15, n_structured=8)
                papers_hits = rag.get("papers", []) or []
                struct_hits = rag.get("structured", []) or []
                verification_result["evidence_papers"] = [
                    {"source": p.get("source", ""), "pmid": p.get("pmid", ""),
                     "text": (p.get("text", "") or "")[:500]}
                    for p in papers_hits
                ]
                verification_result["evidence_structured"] = [
                    {"source": s.get("source", ""),
                     "text": (s.get("text", "") or "")[:500]}
                    for s in struct_hits
                ]
            except Exception as _re:
                st.warning(f"RAG 검색 실패: {str(_re)[:200]}")

        # 4) Claude로 검증 리포트 생성
        verification_md = ""
        if CLAUDE_API_KEY and (papers_hits or struct_hits):
            try:
                evidence_text = ""
                for i, p in enumerate(papers_hits[:12], 1):
                    evidence_text += f"\n[P{i}] {p.get('source','')} (PMID:{p.get('pmid','')})\n{(p.get('text','') or '')[:400]}\n"
                for i, s in enumerate(struct_hits[:8], 1):
                    evidence_text += f"\n[S{i}] {s.get('source','')}\n{(s.get('text','') or '')[:300]}\n"

                verify_prompt = f"""당신은 AGA 신약개발 전문가입니다. 내부에서 발굴된 타깃 보고서를 Foundation Model(22K+ 논문 Knowledge Base)에서 검색된 근거로 검증하세요.

[내부 보고서]
{report_text[:8000]}

[추출된 엔티티]
{json.dumps(entities, ensure_ascii=False, indent=2) if entities else "N/A"}

[Knowledge Base 검색 결과]
{evidence_text[:10000]}

아래 형식의 한국어 검증 리포트를 Markdown으로 작성하세요:

## ✅ 지지 근거 (Supporting Evidence)
- 보고서의 주장을 뒷받침하는 KB 근거를 [P#]/[S#] 인용으로 나열

## ⚠️ 상충·주의 근거 (Conflicting / Caveats)
- 보고서와 상충되거나 반대 결과가 있는 근거

## 🆕 미확보 영역 (Evidence Gaps)
- KB에서 검증되지 않은 주장과 그 이유

## 💡 보완 제안 (Recommendations)
- 추가 확인 실험, 추가 타깃, 관련 문헌 검색 키워드 3-5개
- AGA-성기능장애 공동 타깃 관점에서의 시사점(해당하는 경우)

## 🔢 신뢰도 평가
- 전반 신뢰도: (높음/중간/낮음) + 1-2줄 사유
- KB 근거 논문수: {len(papers_hits)}건, 구조화 데이터: {len(struct_hits)}건
"""
                with st.spinner("🤖 Claude가 검증 리포트 작성 중..."):
                    _vmsg = _client.messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=3000,
                        messages=[{"role": "user", "content": verify_prompt}],
                    )
                    verification_md = _vmsg.content[0].text
                    verification_result["verification"] = verification_md
            except Exception as _ve:
                st.error(f"검증 리포트 생성 실패: {str(_ve)[:200]}")

        # 5) 결과 표시
        if verification_md:
            st.markdown("---")
            st.markdown("#### 🧾 Foundation Model 검증 리포트")
            st.markdown(verification_md)
        elif not (papers_hits or struct_hits):
            st.info("Knowledge Base에서 관련 근거를 찾지 못했습니다. 완전히 새로운 타깃일 수 있습니다 (novelty 높음).")

        # 6) 근거 테이블
        if papers_hits or struct_hits:
            st.markdown("---")
            st.markdown("#### 📚 참조 근거 테이블")
            ev_rows = []
            for i, p in enumerate(papers_hits, 1):
                ev_rows.append({
                    "번호": f"P{i}", "유형": "논문",
                    "출처": (p.get("source") or "")[:80],
                    "PMID": p.get("pmid", ""),
                    "발췌": (p.get("text", "") or "")[:200],
                })
            for i, s in enumerate(struct_hits, 1):
                ev_rows.append({
                    "번호": f"S{i}", "유형": "구조화",
                    "출처": (s.get("source") or "")[:80],
                    "PMID": "",
                    "발췌": (s.get("text", "") or "")[:200],
                })
            st.dataframe(pd.DataFrame(ev_rows), use_container_width=True, height=360)

        # 7) AGA-SD 공동 타깃 교차 체크
        try:
            ent_targets = [str(t).upper() for t in (entities.get("targets") or [])]
            if ent_targets and "SHARED_TARGETS" in globals():
                overlap = [k for k in SHARED_TARGETS.keys() if k.upper() in ent_targets]
                if overlap:
                    st.success(f"⚡ **AGA-성기능장애 공동 타깃 매칭:** {', '.join(overlap)} "
                              f"— '⚡ 공동타겟' 탭에서 상세 정보 확인 가능")
        except Exception:
            pass

        # 8) 저장
        try:
            fname = f"verify_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{(report_source or 'report')[:40]}.json"
            fname = "".join(c if c.isalnum() or c in "._-" else "_" for c in fname)
            save_path = os.path.join(_custom_dir, fname)
            with open(save_path, "w", encoding="utf-8") as _f:
                json.dump(verification_result, _f, ensure_ascii=False, indent=2)
            st.caption(f"💾 검증 결과 저장: `custom_targets/{fname}`")

            if verification_md:
                st.download_button(
                    "📥 검증 리포트 다운로드 (.md)",
                    verification_md,
                    file_name=fname.replace(".json", ".md"),
                    mime="text/markdown",
                )
        except Exception as _se:
            st.caption(f"(저장 실패: {str(_se)[:100]})")

    # 이전 검증 이력
    st.markdown("---")
    with st.expander("📂 이전 검증 이력", expanded=False):
        try:
            files = sorted(
                [f for f in os.listdir(_custom_dir) if f.endswith(".json")],
                reverse=True,
            )[:20]
            if files:
                for f in files:
                    st.caption(f"• `{f}`")
            else:
                st.caption("아직 검증된 보고서가 없습니다.")
        except Exception:
            st.caption("이력을 읽을 수 없습니다.")


# ============================================================
# 하단
# ============================================================
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; font-size: 12px; padding: 10px;'>
    AGA Drug Discovery Platform v3.0 &nbsp;|&nbsp;
    BasGenBio &nbsp;|&nbsp;
    AIxBio Lab-in-the-loop Framework &nbsp;|&nbsp;
    Powered by Claude AI &nbsp;|&nbsp;
    Auto-Updated Daily
</div>
""", unsafe_allow_html=True)
