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
BASE_FOLDER = _search_dirs[0]
for d in _search_dirs:
    if not os.path.isdir(d):
        continue
    for name in EXCEL_NAMES:
        candidate = os.path.join(d, name)
        if os.path.exists(candidate):
            EXCEL_PATH = candidate
            BASE_FOLDER = d
            break
    if EXCEL_PATH:
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
    if not os.path.exists(EXCEL_PATH):
        return None
    df = pd.read_excel(EXCEL_PATH)
    # 관련도를 숫자로 변환
    df["관련도"] = pd.to_numeric(df["관련도(1-5)"], errors="coerce").fillna(0).astype(int)
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


# ============================================================
# 헤더
# ============================================================
st.markdown("""
<div style='background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
     padding: 20px 30px; border-radius: 12px; margin-bottom: 20px;'>
    <h1 style='color: #e94560; margin:0; font-size: 28px;'>🧬 AGA Drug Discovery Platform</h1>
    <p style='color: #a8a8a8; margin: 5px 0 0 0; font-size: 14px;'>
        Androgenetic Alopecia 신약개발 문헌 데이터베이스 &nbsp;|&nbsp;
        {total}건 논문 분석 완료 &nbsp;|&nbsp; Lab-in-the-loop 기반
    </p>
</div>
""".format(total=len(df_ok)), unsafe_allow_html=True)


# ============================================================
# 사이드바: 글로벌 필터
# ============================================================
with st.sidebar:
    st.markdown("### 🔍 필터")

    # 연구 유형
    study_types = sorted(df_ok["연구유형"].dropna().unique().tolist())
    selected_studies = st.multiselect("연구 유형", study_types, default=study_types)

    # 문서 유형
    doc_types = sorted(df_ok["문서유형"].dropna().unique().tolist())
    selected_docs = st.multiselect("문서 유형", doc_types, default=doc_types)

    # 관련도
    min_rel = st.slider("최소 관련도", 1, 5, 1)

    # 키워드 필터
    keyword_filter = st.text_input("키워드 필터", placeholder="예: Wnt, minoxidil, DHT...")

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
# 탭 구성
# ============================================================
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11 = st.tabs([
    "📊 대시보드",
    "📋 문헌 검색",
    "🎯 타겟 분석",
    "💊 화합물 분석",
    "🔗 Target-Compound 매트릭스",
    "🤖 AI 질의응답",
    "🔬 Dark Targets",
    "💡 AI 신약 후보",
    "🧬 바이오마커",
    "📈 연구 동향",
    "🏢 Control Center",
])


# ============================================================
# 탭 1: 대시보드
# ============================================================
with tab1:
    import plotly.express as px
    import plotly.graph_objects as go

    # 상단 KPI
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("총 문헌", f"{len(df_ok)}")
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
# 탭 6: AI 질의응답 (RAG)
# ============================================================
with tab6:
    st.markdown("### 🤖 AI 질의응답")
    st.caption("709건 논문 데이터베이스를 기반으로 AI가 답변합니다.")

    # 예시 질문
    st.markdown("**예시 질문:**")
    example_qs = [
        "AGA에서 Wnt/β-catenin 경로를 타겟으로 하는 novel compound는?",
        "Finasteride와 Dutasteride의 차이점을 논문 근거로 설명해줘",
        "Hair follicle stem cell을 타겟으로 하는 전임상 연구는?",
        "JAK inhibitor의 AGA 치료 가능성은?",
        "국소 약물전달시스템(DDS)으로 개발된 AGA 치료제는?",
    ]
    for q in example_qs:
        st.caption(f"  • {q}")

    st.markdown("---")

    # 채팅 히스토리
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    question = st.chat_input("질문을 입력하세요...")

    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        # 관련 논문 검색 (키워드 매칭)
        keywords = [kw for kw in question.lower().split() if len(kw) > 1]
        relevant = df_ok[df_ok.apply(
            lambda row: sum(1 for kw in keywords if kw in str(row.values).lower()) >= 1,
            axis=1
        )].sort_values("관련도", ascending=False).head(15)

        # 컨텍스트 구성
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

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

            prompt = f"""You are an expert in AGA (Androgenetic Alopecia) drug development.
Below is information retrieved from a database of {len(df_ok)} AGA-related papers and patents.
Answer the question based on this information. Answer in Korean.
Always cite the source paper filenames as evidence.
If the data is insufficient, say so honestly.

[Retrieved Paper Data]
{context}

[Question]
{question}"""

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )

            answer = response.content[0].text

        except ImportError:
            answer = f"anthropic 라이브러리가 필요합니다. `pip install anthropic` 실행 후 재시도하세요."
        except Exception as e:
            answer = f"오류: {str(e)[:200]}\n\n키워드 검색 결과 {len(relevant)}건의 관련 논문이 있습니다."

        st.session_state.messages.append({"role": "assistant", "content": answer})
        with st.chat_message("assistant"):
            st.markdown(answer)


# ============================================================
# 탭 7: 🔬 Dark Targets (미개척 타겟 발굴)
# ============================================================
with tab7:
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
# 탭 8: 💡 AI 신약 후보 (Novel Compound Discovery)
# ============================================================
with tab8:
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
# 탭 9: 🧬 바이오마커 분석
# ============================================================
with tab9:
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
# 탭 10: 📈 연구 동향 (Research Trends)
# ============================================================
with tab10:
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
# 탭 11: 🏢 Control Center (픽셀 아트 가상 사무실)
# ============================================================
with tab11:
    st.markdown("### 🏢 AGA Research Control Center")
    st.caption("AI 에이전트들이 자동으로 논문을 수집·분석하고 있습니다.")

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
