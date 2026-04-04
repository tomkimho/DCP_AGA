"""
=============================================================
02_정보추출.py
=============================================================
용도: 각 논문 텍스트에서 타겟/화합물/기전을 Claude AI로 자동 추출
실행: python 02_정보추출.py

사전 준비:
  1. Claude API 키 필요 (console.anthropic.com에서 발급)
  2. pip install anthropic pandas openpyxl
  3. 01_pdf_추출.py 를 먼저 실행해서 txt 파일을 만들어야 합니다

실행하면:
  - 각 txt 파일을 Claude에게 보내서 핵심 정보를 추출합니다
  - 결과가 엑셀 파일로 자동 정리됩니다
  - 중간에 중단해도 이어서 실행할 수 있습니다 (이미 처리된 건 건너뜀)

소요 시간: 약 4-8시간 (716건 기준, 밤에 돌려놓으세요)
비용: 약 $30-80 (Claude API 사용료)
=============================================================
"""

import os
import sys
import json
import time

# ─── Windows 인코딩 문제 해결 ─────────────────────────────
# (이 부분이 없으면 한국어가 포함된 API 요청이 실패합니다)
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ─── 설정 ────────────────────────────────────────────────
# ★ 여기에 본인의 Claude API 키를 넣으세요 ★
CLAUDE_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# txt 파일이 들어있는 폴더
BASE_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TXT_FOLDER = os.path.join(BASE_FOLDER, "txt_추출결과")
NEW_PAPERS_TXT = os.path.join(BASE_FOLDER, "new_papers_txt")  # 새 논문 텍스트 (자동수집용)
SD_PAPERS_TXT = os.path.join(BASE_FOLDER, "성기능장애", "txt")  # 성기능장애 논문

# 결과 저장 경로
RESULT_EXCEL = os.path.join(BASE_FOLDER, "AGA_문헌분류_결과.xlsx")
PROGRESS_FILE = os.path.join(BASE_FOLDER, "scripts", "_진행상황.json")

# APPEND 모드: 환경 변수로 제어 (GitHub Actions에서 사용)
APPEND_MODE = os.environ.get("APPEND_MODE", "false").lower() == "true"
# ─────────────────────────────────────────────────────────

# Claude에게 보낼 프롬프트 (영어로 작성하여 인코딩 문제 방지)
EXTRACTION_PROMPT = """You are an expert in AGA (Androgenetic Alopecia) drug development AND sexual dysfunction (erectile dysfunction, post-finasteride syndrome).
Read the paper/patent text below, and extract the following information in JSON format.

Context: AGA treatments (Finasteride, Dutasteride) can cause sexual dysfunction side effects.
We study both AGA and sexual dysfunction to find shared molecular targets and safer therapies.

Items to extract:
1. document_type: "Paper" or "Patent" or "Review" or "Other"
2. study_type: "Clinical" or "Preclinical" or "In vitro" or "In silico" or "Review" or "Patent"
3. targets: list of drug targets (e.g. ["5a-Reductase Type 2", "Androgen Receptor", "PDE5", "eNOS"])
4. compounds: list of compound/drug names (e.g. ["Finasteride", "Sildenafil", "Tadalafil"])
5. mechanism_of_action: key mechanism description (1-2 sentences, in Korean)
6. pathways: related signaling pathways (e.g. ["Wnt/beta-catenin", "AR signaling", "NO/cGMP", "TGF-beta"])
7. cell_types: cell lines or animal models used (e.g. ["Dermal papilla cells", "Cavernous smooth muscle", "C3H mouse"])
8. key_findings: key findings (1-3 sentences, in Korean)
9. biomarkers: biomarkers (if any, e.g. ["DHT", "IIEF-5", "eNOS", "TGF-beta1"])
10. relevance_score: relevance to AGA drug development OR sexual dysfunction research (1-5, 5=highly relevant)

Respond ONLY with valid JSON. Do not include any other text.
For unknown items, use empty list [] or empty string "".

---
Paper/Patent text:
{text}
"""


def extract_info(client, text, filename):
    """하나의 논문 텍스트에서 정보를 추출합니다"""
    # 텍스트가 너무 길면 앞부분만 사용 (비용 절약)
    max_chars = 15000
    if len(text) > max_chars:
        # 앞부분(제목+초록) + 뒷부분(결론) 사용
        text = text[:10000] + "\n...(중략)...\n" + text[-5000:]

    try:
        prompt_text = EXTRACTION_PROMPT.format(text=text)
        # Ensure text is properly encoded as UTF-8 string
        if isinstance(prompt_text, bytes):
            prompt_text = prompt_text.decode('utf-8', errors='replace')

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[
                {"role": "user", "content": prompt_text}
            ]
        )
        response_text = message.content[0].text.strip()

        # JSON 파싱
        # 가끔 ```json ... ``` 로 감싸는 경우 처리
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]

        result = json.loads(response_text)
        result["filename"] = filename
        result["status"] = "성공"
        return result

    except json.JSONDecodeError:
        return {"filename": filename, "status": "JSON parse failed", "raw": response_text[:200]}
    except Exception as e:
        err_msg = str(e).encode('ascii', errors='replace').decode('ascii')
        return {"filename": filename, "status": f"Error: {err_msg[:100]}"}


def load_progress():
    """이전 진행 상황을 불러옵니다 (중단 후 재시작 지원)"""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"processed": [], "results": []}


def save_progress(progress):
    """진행 상황을 저장합니다"""
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def save_to_excel(results):
    """결과를 엑셀로 저장합니다"""
    import pandas as pd

    rows = []
    for r in results:
        rows.append({
            "파일명": r.get("filename", ""),
            "문서유형": r.get("document_type", ""),
            "연구유형": r.get("study_type", ""),
            "타겟(Target)": ", ".join(r.get("targets", [])) if isinstance(r.get("targets"), list) else str(r.get("targets", "")),
            "화합물(Compound)": ", ".join(r.get("compounds", [])) if isinstance(r.get("compounds"), list) else str(r.get("compounds", "")),
            "기전(MoA)": r.get("mechanism_of_action", ""),
            "신호전달경로": ", ".join(r.get("pathways", [])) if isinstance(r.get("pathways"), list) else str(r.get("pathways", "")),
            "세포/모델": ", ".join(r.get("cell_types", [])) if isinstance(r.get("cell_types"), list) else str(r.get("cell_types", "")),
            "핵심발견": r.get("key_findings", ""),
            "바이오마커": ", ".join(r.get("biomarkers", [])) if isinstance(r.get("biomarkers"), list) else str(r.get("biomarkers", "")),
            "관련도(1-5)": r.get("relevance_score", ""),
            "처리상태": r.get("status", ""),
        })

    df_new = pd.DataFrame(rows)

    # APPEND 모드: 기존 Excel이 있으면 합치기 (중복 파일명 제거)
    if APPEND_MODE and os.path.exists(RESULT_EXCEL):
        try:
            df_existing = pd.read_excel(RESULT_EXCEL, engine="openpyxl")
            existing_files = set(df_existing["파일명"].tolist())
            df_only_new = df_new[~df_new["파일명"].isin(existing_files)]
            if len(df_only_new) > 0:
                df_merged = pd.concat([df_existing, df_only_new], ignore_index=True)
                df_merged.to_excel(RESULT_EXCEL, index=False, engine="openpyxl")
                print(f"\n  엑셀 APPEND 저장: 기존 {len(df_existing)}건 + 신규 {len(df_only_new)}건 = {len(df_merged)}건")
            else:
                print(f"\n  신규 항목 없음. 기존 엑셀 유지: {len(df_existing)}건")
            return
        except Exception as e:
            print(f"\n  APPEND 실패, 전체 덮어쓰기: {str(e)[:60]}")

    df_new.to_excel(RESULT_EXCEL, index=False, engine="openpyxl")
    print(f"\n  엑셀 저장 완료: {RESULT_EXCEL}")


def main():
    # API 키 확인
    if CLAUDE_API_KEY == "여기에_API_키를_넣으세요":
        print("=" * 60)
        print("  Claude API 키를 설정해야 합니다!")
        print()
        print("  방법:")
        print("  1. console.anthropic.com 에 접속해서 가입")
        print("  2. Settings → API Keys → Create Key")
        print("  3. 이 파일을 열어서 CLAUDE_API_KEY = 부분에 키를 붙여넣기")
        print("=" * 60)
        sys.exit(1)

    # anthropic 라이브러리 확인
    try:
        import anthropic
    except ImportError:
        print("anthropic 라이브러리가 설치되지 않았습니다!")
        print("cmd에서: pip install anthropic")
        sys.exit(1)

    # Claude 클라이언트 생성
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    # txt 파일 목록 (기존 + 새로 수집된 논문)
    txt_files = sorted([f for f in os.listdir(TXT_FOLDER) if f.endswith('.txt') and not f.startswith('_')])
    # APPEND 모드에서는 new_papers_txt + 성기능장애/txt 폴더도 포함
    if APPEND_MODE and os.path.isdir(NEW_PAPERS_TXT):
        new_txts = sorted([
            os.path.relpath(os.path.join(root, f), NEW_PAPERS_TXT)
            for root, dirs, files in os.walk(NEW_PAPERS_TXT)
            for f in files
            if f.endswith('.txt') and not f.startswith('_')
        ])
        txt_files = txt_files + new_txts
        if new_txts:
            print(f"  APPEND 모드: 새 논문 {len(new_txts)}건 추가됨 (하위 폴더 포함)")

    # 성기능장애 논문도 항상 포함
    if os.path.isdir(SD_PAPERS_TXT):
        sd_txts = sorted([f for f in os.listdir(SD_PAPERS_TXT) if f.endswith('.txt') and not f.startswith('_')])
        txt_files = txt_files + sd_txts
        if sd_txts:
            print(f"  성기능장애 논문: {len(sd_txts)}건 추가됨")
    total = len(txt_files)

    print("=" * 60)
    print(f"  논문 정보 자동 추출 시작")
    print(f"  총 {total}건을 처리합니다")
    print(f"  예상 소요 시간: 약 {total * 30 // 3600}시간 {(total * 30 % 3600) // 60}분")
    print(f"  예상 비용: 약 ${total * 0.05:.0f}-${total * 0.15:.0f}")
    print()
    print("  Ctrl+C 로 중단해도 다음에 이어서 실행됩니다.")
    print("=" * 60)
    print()

    # 이전 진행 상황 불러오기
    progress = load_progress()
    processed = set(progress["processed"])
    results = progress["results"]

    if processed:
        print(f"  이전 진행 상황 불러옴: {len(processed)}건 처리 완료")
        print()

    try:
        for i, filename in enumerate(txt_files, 1):
            # 이미 처리된 파일 건너뜀
            if filename in processed:
                continue

            # 여러 폴더에서 txt 파일 찾기
            txt_path = None
            for _search_dir in [TXT_FOLDER, NEW_PAPERS_TXT, SD_PAPERS_TXT]:
                _candidate = os.path.join(_search_dir, filename)
                if os.path.exists(_candidate):
                    txt_path = _candidate
                    break
                # 하위 폴더도 검색
                for _root, _dirs, _files in os.walk(_search_dir):
                    if filename in _files or os.path.basename(filename) in _files:
                        txt_path = os.path.join(_root, os.path.basename(filename))
                        break
                if txt_path:
                    break
            if not txt_path or not os.path.exists(txt_path):
                print(f"  [{i}/{total}] 파일 없음: {filename[:50]}... → 건너뜀")
                continue
            with open(txt_path, "r", encoding="utf-8") as f:
                text = f.read()

            print(f"  [{i}/{total}] 처리 중: {filename[:50]}...", end="", flush=True)

            result = extract_info(client, text, filename)
            results.append(result)
            processed.add(filename)

            status = result.get("status", "")
            print(f" → {status}")

            # 10건마다 중간 저장
            if len(processed) % 10 == 0:
                progress["processed"] = list(processed)
                progress["results"] = results
                save_progress(progress)
                save_to_excel(results)
                print(f"      (중간 저장 완료: {len(processed)}/{total}건)")

            # API 속도 제한 방지 (1초 대기)
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\n  중단되었습니다. 진행 상황을 저장합니다...")

    # 최종 저장
    progress["processed"] = list(processed)
    progress["results"] = results
    save_progress(progress)
    save_to_excel(results)

    print()
    print("=" * 60)
    print(f"  처리 완료: {len(processed)}/{total}건")
    print(f"  결과 엑셀: {RESULT_EXCEL}")
    print()
    print("  다음 단계:")
    print("  1. 엑셀을 열어서 결과를 확인하세요")
    print("  2. 틀린 부분을 수정하세요 (이게 가장 중요합니다!)")
    print("  3. 수정이 끝나면 03_관계추출.py 를 실행하세요")
    print("=" * 60)


if __name__ == "__main__":
    main()
