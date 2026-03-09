"""
=============================================================
04_천연물활성성분.py
=============================================================
용도: 논문에서 추출된 천연물(natural product) 추출물 이름에서
      알려진 활성 성분(active compounds)을 매핑하고
      PubChem에서 구조/타깃 정보를 추가 수집

실행: python 04_천연물활성성분.py
소요: 약 5-10분 (인터넷 필요)
비용: 무료 (PubChem 공개 데이터베이스)
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
STRUCT_JSON = os.path.join(BASE_FOLDER, "compound_structures.json")
OUTPUT_JSON = os.path.join(BASE_FOLDER, "natural_product_actives.json")
OUTPUT_EXCEL = os.path.join(BASE_FOLDER, "AGA_천연물_활성성분.xlsx")
# ─────────────────────────────────────────────────────────


# ============================================================
# 주요 천연물 → 활성 성분 매핑 (AGA 관련 문헌 기반)
# ============================================================
NATURAL_PRODUCT_MAP = {
    # ─── 한약재 / 한방 추출물 ───
    "Eclipta prostrata": ["Wedelolactone", "Eclalbatin", "Luteolin"],
    "Eclipta prostrata (한련초)": ["Wedelolactone", "Eclalbatin", "Luteolin"],
    "Ecliptae Herba": ["Wedelolactone", "Eclalbatin"],
    "Ecliptae Herba (EH)": ["Wedelolactone", "Eclalbatin"],
    "Eclipta alba (한련초)": ["Wedelolactone", "Eclalbatin"],
    "Eclipta prostrata L. extract": ["Wedelolactone", "Eclalbatin"],

    "Coptis chinensis extract": ["Berberine", "Coptisine", "Palmatine"],
    "Coptis chinensis extract (황련 추출물)": ["Berberine", "Coptisine", "Palmatine"],

    "Cornus officinalis": ["Loganin", "Morroniside", "Ursolic acid"],
    "Cornus officinalis (CO)": ["Loganin", "Morroniside", "Ursolic acid"],
    "Corni Fructus (산수유)": ["Loganin", "Morroniside", "Ursolic acid"],

    "Cynanchum wilfordii (백하수오)": ["Cynandione A", "Acetophenone"],
    "Cynanchum wilfordii (Baekhasueoul)": ["Cynandione A"],
    "Cynanchi wilfordii": ["Cynandione A"],

    "Drynaria fortunei (보골지)": ["Naringin", "Neoeriocitrin"],

    "Corydalis yanhusuo (현호색)": ["Tetrahydropalmatine", "Corydaline", "Berberine"],

    "Crataegus pinnatifida extract": ["Vitexin", "Hyperoside", "Chlorogenic acid"],

    # ─── 주요 식물 추출물 ───
    "Curcumin derivatives": ["Curcumin", "Demethoxycurcumin", "Bisdemethoxycurcumin"],

    "Saw palmetto": ["Beta-sitosterol", "Lauric acid", "Oleic acid"],
    "Saw Palmetto": ["Beta-sitosterol", "Lauric acid", "Oleic acid"],
    "Serenoa repens": ["Beta-sitosterol", "Lauric acid"],
    "Saw palmetto extract": ["Beta-sitosterol", "Lauric acid", "Oleic acid"],

    "Green tea extract": ["Epigallocatechin gallate", "Epicatechin", "Catechin"],
    "EGCG (Epigallocatechin gallate)": ["Epigallocatechin gallate"],

    "Panax ginseng": ["Ginsenoside Rg1", "Ginsenoside Rb1", "Ginsenoside Rg3"],
    "Red ginseng": ["Ginsenoside Rg3", "Ginsenoside Rh2", "Compound K"],
    "Korean Red Ginseng": ["Ginsenoside Rg3", "Ginsenoside Rb1"],

    "Polygonum multiflorum": ["Emodin", "Stilbene glycoside", "Resveratrol"],
    "He Shou Wu": ["Emodin", "Stilbene glycoside"],

    "Pumpkin seed oil": ["Beta-sitosterol", "Delta-7-stigmastenol"],
    "Cucurbita pepo extract": ["Beta-sitosterol", "Cucurbitacin"],

    "Rosemary extract": ["Rosmarinic acid", "Carnosic acid", "Carnosol"],
    "Rosmarinus officinalis": ["Rosmarinic acid", "Carnosic acid"],

    "Grape seed extract": ["Proanthocyanidin", "Resveratrol", "Catechin"],

    "Licorice extract": ["Glycyrrhizin", "Glabridin", "Liquiritigenin"],
    "Glycyrrhiza glabra": ["Glycyrrhizin", "Glabridin"],

    "Sophora flavescens": ["Matrine", "Oxymatrine", "Kurarinone"],

    "Thuja orientalis": ["Kaempferol", "Isoquercetin", "Hinokiflavone"],
    "Platycladus orientalis": ["Kaempferol", "Hinokiflavone"],

    "Capsaicin cream": ["Capsaicin"],
    "Capsicum extract": ["Capsaicin", "Dihydrocapsaicin"],

    "Ginkgo biloba": ["Ginkgolide A", "Ginkgolide B", "Bilobalide"],
    "Ginkgo biloba extract": ["Ginkgolide A", "Ginkgolide B", "Bilobalide"],

    "Aloe vera": ["Aloin", "Acemannan", "Aloe-emodin"],
    "Aloe vera extract": ["Aloin", "Aloe-emodin"],

    "Centella asiatica": ["Asiaticoside", "Madecassoside", "Asiatic acid"],
    "Centella asiatica extract": ["Asiaticoside", "Madecassoside"],

    "Pueraria lobata": ["Puerarin", "Daidzein", "Genistein"],

    "Dendropanax morbifera extract": ["Rutin", "Chlorogenic acid"],

    "Camellia sinensis": ["Epigallocatechin gallate", "Caffeine", "Theanine"],

    "Allium cepa extract": ["Quercetin", "Kaempferol"],

    "Elephant garlic extract (Allium ampeloprasum var. )": ["Allicin", "Ajoene"],

    "Crinum asiaticum extract": ["Lycorine", "Crinamine"],
    "Crinum asiaticum var. japonicum (문주란) extract": ["Lycorine"],

    "Eggplant extract": ["Nasunin", "Chlorogenic acid"],

    "Cyperus Rotundus Root Extract (향부자추출물)": ["Alpha-cyperone", "Rotundone"],

    "Connarus semidecandrus Jack ethanol extract (Cs-EE": ["Rhamnetin"],
    "Connarus semidecandrus Jack. extract": ["Rhamnetin"],

    "Coprinus comatus extract": ["Ergothioneine"],
    "Cuscuta reflexa Roxb. ethanolic extract": ["Kaempferol", "Quercetin"],

    "Dandel extract (민들레 추출물)": ["Taraxasterol", "Luteolin"],
    "Dandelion extract (민들레 추출물)": ["Taraxasterol", "Luteolin"],

    "Diospyros kaki": ["Gallic acid", "Kaempferol"],
    "Diospyros kaki leaf (감잎)": ["Gallic acid", "Kaempferol", "Astragalin"],

    "Duchesnea indica (Indian strawberry) extract": ["Ellagic acid"],

    "Dioscorea polystachya (노랑하늘타리) extract": ["Diosgenin", "Allantoin"],

    # ─── 해조류 / 해양 천연물 ───
    "DPHC (diphlorethohydroxycarmalol)": ["Diphlorethohydroxycarmalol"],

    # ─── 성장인자/펩타이드 ───
    "EGF": ["Epidermal growth factor"],
    "EGF (Epidermal Growth Factor)": ["Epidermal growth factor"],
    "Concentrated Growth Factor (CGF)": ["Platelet-derived growth factor"],

    # ─── 지방산 ───
    "Conjugated linoleic acid (CLA)": ["Conjugated linoleic acid"],
    "Docosahexaenoic acid (DHA)": ["Docosahexaenoic acid"],
    "Eicosapentaenoic acid (EPA)": ["Eicosapentaenoic acid"],

    # ─── 호르몬/스테로이드 ───
    "DHT (Dihydrotestosterone)": ["Dihydrotestosterone"],
    "Corticotropin-releasing hormone (CRH)": ["Corticotropin-releasing hormone"],

    # ─── 면역조절/화학요법 ───
    "Cyclophosphamide (CTX)": ["Cyclophosphamide"],
    "Cyclophosphamide (CYP)": ["Cyclophosphamide"],
    "Cyclosporin A (CsA)": ["Cyclosporine"],
    "Doxorubicin (DOX)": ["Doxorubicin"],
    "Dinitrochlorobenzene (DNCB)": ["Dinitrochlorobenzene"],
    "Diphencyprone (DPCP)": ["Diphencyprone"],
    "Diphenyleneiodonium (DPI)": ["Diphenyleneiodonium"],

    # ─── 기타 천연 화합물 ───
    "Cycloastragenol (CAG)": ["Cycloastragenol"],
    "Copper ions (Cu2+)": ["Copper gluconate"],
    "Cu-GHK peptide": ["Copper peptide GHK-Cu"],
    "Cucumber extract": ["Cucurbitacin E"],
    "Dried brewer's yeast": ["Beta-glucan", "Biotin"],
    "Enterococcus faecalis": ["Lipoteichoic acid"],
}


def fetch_pubchem(compound_name):
    """PubChem에서 화합물 정보를 가져옵니다"""
    try:
        encoded = urllib.parse.quote(compound_name)
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

        return {
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
    except urllib.error.HTTPError:
        return None
    except Exception:
        return None


def fetch_pubchem_bioactivity(cid):
    """PubChem에서 화합물의 생체활성/타깃 정보를 가져옵니다"""
    try:
        url = (f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}"
               f"/assaysummary/JSON")
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'AGA-Drug-Discovery/1.0')

        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        # 활성 있는(active) assay만 추출
        assays = data.get("Table", {}).get("Row", [])
        targets = set()
        active_count = 0

        for row in assays[:50]:  # 최대 50개만
            cells = row.get("Cell", [])
            if len(cells) >= 4:
                outcome = str(cells[2].get("Value", ""))
                target = str(cells[3].get("Value", ""))
                if "Active" in outcome and target and target != "None":
                    targets.add(target)
                    active_count += 1

        return {
            "active_assay_count": active_count,
            "known_targets": list(targets)[:10]  # 상위 10개
        }
    except Exception:
        return {"active_assay_count": 0, "known_targets": []}


def main():
    import pandas as pd

    print("=" * 60)
    print("  천연물 활성 성분 매핑 및 구조 정보 수집")
    print("=" * 60)
    print()

    # 1) 03에서 not_found였던 화합물 로드
    not_found_names = set()
    if os.path.exists(STRUCT_JSON):
        with open(STRUCT_JSON, "r", encoding="utf-8") as f:
            struct_data = json.load(f)
        for item in struct_data:
            if item.get("status") != "found":
                not_found_names.add(item["name"])
        print(f"  03_화합물구조.py에서 미발견: {len(not_found_names)}개")
    else:
        # STRUCT_JSON 없으면 엑셀에서 직접 추출
        if os.path.exists(EXCEL_PATH):
            df = pd.read_excel(EXCEL_PATH)
            for val in df["화합물(Compound)"].dropna():
                for item in str(val).split(","):
                    item = item.strip()
                    if item and len(item) > 2:
                        not_found_names.add(item)
        print(f"  엑셀에서 추출된 화합물: {len(not_found_names)}개")

    # 2) 매핑 가능한 항목 필터링
    mappable = {}
    for name in not_found_names:
        # 정확히 매칭
        if name in NATURAL_PRODUCT_MAP:
            mappable[name] = NATURAL_PRODUCT_MAP[name]
            continue
        # 부분 매칭 (extract, 추출물 등 제거 후)
        for key, actives in NATURAL_PRODUCT_MAP.items():
            if key in name or name in key:
                mappable[name] = actives
                break

    print(f"  매핑 가능한 천연물: {len(mappable)}개")
    print(f"  내장 매핑 DB: {len(NATURAL_PRODUCT_MAP)}개 천연물")
    print()

    # 3) 활성 성분의 PubChem 구조 수집
    all_actives = set()
    for actives in mappable.values():
        for a in actives:
            all_actives.add(a)

    print(f"  수집할 고유 활성 성분: {len(all_actives)}개")
    print()

    # 이전 결과 로드
    existing = {}
    if os.path.exists(OUTPUT_JSON):
        with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
            existing = json.load(f)
        print(f"  기존 데이터 로드: {len(existing.get('active_compounds', {}))}개")

    active_data = existing.get("active_compounds", {})
    results = []
    found = 0

    for i, active_name in enumerate(sorted(all_actives), 1):
        if active_name in active_data and active_data[active_name].get("status") == "found":
            found += 1
            continue

        print(f"  [{i}/{len(all_actives)}] {active_name}...", end="", flush=True)

        try:
            result = fetch_pubchem(active_name)
            if result and result.get("status") == "found":
                active_data[active_name] = result
                found += 1
                print(f" -> Found (CID: {result['CID']}, MW: {result.get('MolecularWeight', '?')})")

                # 생체활성 정보도 수집
                time.sleep(0.3)
                bio = fetch_pubchem_bioactivity(result["CID"])
                active_data[active_name]["bioactivity"] = bio
                if bio["known_targets"]:
                    print(f"       Targets: {', '.join(bio['known_targets'][:3])}")
            else:
                active_data[active_name] = {"name": active_name, "status": "not_found"}
                print(f" -> not_found")

            time.sleep(0.3)

        except KeyboardInterrupt:
            print("\n\n  사용자 중단. 저장 중...")
            break
        except Exception as e:
            print(f" -> ERROR: {str(e)[:60]}")
            active_data[active_name] = {"name": active_name, "status": f"error: {str(e)[:80]}"}
            time.sleep(1)

    # 4) 결과 구성
    output = {
        "metadata": {
            "total_natural_products_mapped": len(mappable),
            "total_active_compounds": len(all_actives),
            "found_in_pubchem": found,
            "generated_date": time.strftime("%Y-%m-%d %H:%M:%S")
        },
        "natural_product_mapping": {
            name: actives for name, actives in sorted(mappable.items())
        },
        "active_compounds": active_data
    }

    # 5) 저장 (JSON)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # 6) 엑셀 저장
    rows = []
    for np_name, actives in sorted(mappable.items()):
        for active_name in actives:
            info = active_data.get(active_name, {})
            rows.append({
                "천연물": np_name,
                "활성성분": active_name,
                "PubChem_CID": info.get("CID", ""),
                "SMILES": info.get("SMILES", ""),
                "분자식": info.get("MolecularFormula", ""),
                "분자량(g/mol)": info.get("MolecularWeight", ""),
                "IUPAC_Name": info.get("IUPACName", ""),
                "PubChem_URL": info.get("pubchem_url", ""),
                "구조이미지URL": info.get("image_url", ""),
                "알려진_타깃": ", ".join(info.get("bioactivity", {}).get("known_targets", [])),
                "활성_Assay수": info.get("bioactivity", {}).get("active_assay_count", 0),
                "검색상태": info.get("status", "not_found"),
            })

    if rows:
        result_df = pd.DataFrame(rows)
        result_df.to_excel(OUTPUT_EXCEL, index=False, engine="openpyxl")

    # 7) 결과 요약
    print()
    print("=" * 60)
    print(f"  완료!")
    print(f"  매핑된 천연물: {len(mappable)}개")
    print(f"  고유 활성 성분: {len(all_actives)}개")
    print(f"  PubChem 검색 성공: {found}개")
    print(f"  JSON: {OUTPUT_JSON}")
    print(f"  Excel: {OUTPUT_EXCEL}")
    print()
    print("  주요 매핑 예시:")
    for name, actives in list(mappable.items())[:8]:
        found_actives = [a for a in actives if active_data.get(a, {}).get("status") == "found"]
        print(f"    {name[:40]:40s} -> {', '.join(found_actives[:3])}")
    print()
    print("  다음 단계:")
    print("  1. AGA_천연물_활성성분.xlsx 를 열어서 확인하세요")
    print("  2. streamlit run 09_웹사이트.py 로 웹사이트에서 확인하세요")
    print("=" * 60)


if __name__ == "__main__":
    main()
