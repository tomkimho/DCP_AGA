"""
=============================================================
03_화합물구조.py
=============================================================
용도: 논문에서 추출된 화합물 이름으로 PubChem에서
      SMILES, 분자식, 분자량, 2D 구조 이미지를 자동 수집

실행: python 03_화합물구조.py
소요: 약 10-20분 (인터넷 필요)
비용: 무료 (PubChem은 공개 데이터베이스)
=============================================================
"""

import os
import sys
import json
import time
import urllib.request
import urllib.parse
import urllib.error

# Windows 인코딩
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ─── 설정 ────────────────────────────────────────────────
BASE_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCEL_PATH = os.path.join(BASE_FOLDER, "AGA_문헌분류_결과.xlsx")
OUTPUT_JSON = os.path.join(BASE_FOLDER, "compound_structures.json")
OUTPUT_EXCEL = os.path.join(BASE_FOLDER, "AGA_화합물_구조정보.xlsx")
IMG_FOLDER = os.path.join(BASE_FOLDER, "compound_images")
# ─────────────────────────────────────────────────────────

# PubChem에서 검색하면 안 되는 항목들 (일반 명사, 숫자 등)
SKIP_LIST = {"1", "2", "3", "4", "5", "nan", "None", "N/A", "",
             "Platelet-rich plasma (PRP)", "Platelet-Rich Plasma (PRP)",
             "PRP", "Cas9 protein", "siRNA", "shRNA", "miRNA"}


def fetch_pubchem(compound_name):
    """PubChem에서 화합물 정보를 가져옵니다"""
    try:
        # URL 인코딩
        encoded = urllib.parse.quote(compound_name)

        # 1. 기본 속성 가져오기 (SMILES, 분자식, 분자량)
        url = (f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
               f"{encoded}/property/"
               f"CanonicalSMILES,IsomericSMILES,MolecularFormula,"
               f"MolecularWeight,IUPACName/JSON")

        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'AGA-Drug-Discovery/1.0')

        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        props = data["PropertyTable"]["Properties"][0]
        cid = props.get("CID", "")

        result = {
            "name": compound_name,
            "CID": cid,
            "SMILES": props.get("CanonicalSMILES", ""),
            "IsomericSMILES": props.get("IsomericSMILES", ""),
            "MolecularFormula": props.get("MolecularFormula", ""),
            "MolecularWeight": props.get("MolecularWeight", ""),
            "IUPACName": props.get("IUPACName", ""),
            "image_url": f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/PNG?image_size=300x300" if cid else "",
            "pubchem_url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}" if cid else "",
            "status": "found"
        }

        return result

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"name": compound_name, "status": "not_found"}
        return {"name": compound_name, "status": f"error_{e.code}"}
    except Exception as e:
        return {"name": compound_name, "status": f"error: {str(e)[:80]}"}


def download_image(url, filepath):
    """이미지를 다운로드합니다"""
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'AGA-Drug-Discovery/1.0')
        with urllib.request.urlopen(req, timeout=15) as resp:
            with open(filepath, 'wb') as f:
                f.write(resp.read())
        return True
    except Exception:
        return False


def main():
    import pandas as pd

    # 엑셀에서 화합물 목록 추출
    if not os.path.exists(EXCEL_PATH):
        print("엑셀 파일이 없습니다. 02_정보추출.py를 먼저 실행하세요.")
        sys.exit(1)

    df = pd.read_excel(EXCEL_PATH)

    # 고유 화합물 추출
    all_compounds = set()
    for val in df["화합물(Compound)"].dropna():
        for item in str(val).split(","):
            item = item.strip()
            if item and len(item) > 2 and item not in SKIP_LIST:
                all_compounds.add(item)

    compounds = sorted(all_compounds)
    total = len(compounds)

    print("=" * 60)
    print(f"  화합물 구조 정보 수집 (PubChem)")
    print(f"  총 {total}개 고유 화합물")
    print(f"  예상 소요 시간: 약 {total * 2 // 60}분")
    print(f"  비용: 무료")
    print("=" * 60)
    print()

    # 이미지 폴더 생성
    os.makedirs(IMG_FOLDER, exist_ok=True)

    # 이전 결과 불러오기
    existing = {}
    if os.path.exists(OUTPUT_JSON):
        with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
            existing_list = json.load(f)
        for item in existing_list:
            existing[item["name"]] = item
        print(f"  기존 데이터 {len(existing)}개 로드")

    results = []
    found = 0
    not_found = 0
    skipped = 0

    for i, name in enumerate(compounds, 1):
        # 이미 수집된 항목은 건너뜀 (found든 not_found든)
        if name in existing:
            results.append(existing[name])
            if existing[name].get("status") == "found":
                found += 1
            else:
                not_found += 1
            skipped += 1
            continue

        try:
            print(f"  [{i}/{total}] {name[:50]}...", end="", flush=True)

            result = fetch_pubchem(name)
            results.append(result)

            if result["status"] == "found":
                found += 1
                print(f" -> Found (MW: {result.get('MolecularWeight', '?')})")

                # 이미지 다운로드
                if result.get("image_url"):
                    img_path = os.path.join(IMG_FOLDER, f"{result['CID']}.png")
                    if not os.path.exists(img_path):
                        download_image(result["image_url"], img_path)
            else:
                not_found += 1
                print(f" -> {result['status']}")

            # PubChem API 속도 제한 (초당 5요청 제한)
            time.sleep(0.3)

        except KeyboardInterrupt:
            print("\n\n  사용자 중단. 지금까지 결과를 저장합니다...")
            break
        except Exception as e:
            print(f" -> ERROR: {str(e)[:60]}")
            results.append({"name": name, "status": f"error: {str(e)[:80]}"})
            not_found += 1
            time.sleep(1)  # 에러 시 잠시 대기

        # 50개마다 중간 저장
        if i % 50 == 0:
            with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"      (중간 저장: {i}/{total})")

    if skipped > 0:
        print(f"\n  (이전 실행에서 {skipped}개 건너뜀)")

    # 최종 저장 (JSON)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # 엑셀로 저장
    rows = []
    for r in results:
        if r.get("status") == "found":
            rows.append({
                "화합물명": r["name"],
                "PubChem_CID": r.get("CID", ""),
                "SMILES": r.get("SMILES", ""),
                "Isomeric_SMILES": r.get("IsomericSMILES", ""),
                "분자식": r.get("MolecularFormula", ""),
                "분자량(g/mol)": r.get("MolecularWeight", ""),
                "IUPAC_Name": r.get("IUPACName", ""),
                "PubChem_URL": r.get("pubchem_url", ""),
                "구조_이미지_URL": r.get("image_url", ""),
            })

    if rows:
        result_df = pd.DataFrame(rows)
        result_df.to_excel(OUTPUT_EXCEL, index=False, engine="openpyxl")

    print()
    print("=" * 60)
    print(f"  완료!")
    print(f"  PubChem 검색 성공: {found}개")
    print(f"  검색 실패: {not_found}개")
    print(f"  구조 데이터: {OUTPUT_JSON}")
    print(f"  엑셀 파일: {OUTPUT_EXCEL}")
    print(f"  구조 이미지: {IMG_FOLDER}/ ({found}개)")
    print()
    print("  다음 단계:")
    print("  1. AGA_화합물_구조정보.xlsx 를 열어서 확인하세요")
    print("  2. compound_images/ 폴더에서 구조 이미지를 확인하세요")
    print("  3. streamlit run 09_웹사이트.py 로 웹사이트에서 확인하세요")
    print("=" * 60)


if __name__ == "__main__":
    main()
