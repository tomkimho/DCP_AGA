"""
발기부전/성기능장애/전립선 관련 논문 다운로드
PubMed 다중 쿼리 검색 → 중복 제거 → PDF 다운로드 (실패 시 초록 텍스트 저장)

실행: python3 scripts/download_sexual_dysfunction.py --days 9125 --max 10000 --api-key YOUR_KEY --reset
"""
import os
import sys
import json
import time
import re
import argparse
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

# ─── 설정 ───────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
FOLDER_NAME = "성기능장애"
PDF_DIR = os.path.join(BASE_DIR, FOLDER_NAME, "pdf")
TXT_DIR = os.path.join(BASE_DIR, FOLDER_NAME, "txt")

os.makedirs(PDF_DIR, exist_ok=True)
os.makedirs(TXT_DIR, exist_ok=True)

# ─── 검색 쿼리 (5개 카테고리, 각각 검색 후 PMID 합침) ───
SEARCH_QUERIES = [
    # 1. 발기부전 약물/치료
    (
        "(erectile dysfunction[Title/Abstract]) AND "
        "(drug OR pharmacotherapy OR treatment OR therapy OR "
        "PDE5 OR sildenafil OR tadalafil OR vardenafil OR avanafil OR "
        "alprostadil OR shockwave OR stem cell OR platelet-rich plasma OR "
        "efficacy OR safety OR clinical trial OR randomized)"
    ),
    # 2. 성기능장애 약물/진단
    (
        "(sexual dysfunction[Title/Abstract]) AND "
        "(drug OR treatment OR therapy OR diagnosis OR diagnostic OR "
        "biomarker OR screening OR pharmacotherapy OR SSRI OR antidepressant OR "
        "hormonal OR testosterone OR androgen OR estrogen OR "
        "mechanism OR pathophysiology OR molecular target)"
    ),
    # 3. 전립선 약물 부작용 (성기능 관련)
    (
        "(prostate[Title/Abstract]) AND "
        "(sexual dysfunction OR erectile dysfunction OR sexual side effect OR "
        "sexual function OR libido OR ejaculatory dysfunction) AND "
        "(finasteride OR dutasteride OR tamsulosin OR alfuzosin OR "
        "alpha-blocker OR 5-alpha reductase OR "
        "androgen deprivation OR LHRH OR GnRH OR "
        "bicalutamide OR enzalutamide OR abiraterone OR "
        "radical prostatectomy OR radiation therapy)"
    ),
    # 4. 전립선암 치료와 성기능
    (
        "(prostate cancer[Title/Abstract] OR prostate neoplasm[Title/Abstract]) AND "
        "(sexual function[Title/Abstract] OR erectile function[Title/Abstract] OR "
        "sexual rehabilitation[Title/Abstract] OR penile rehabilitation[Title/Abstract]) AND "
        "(treatment OR therapy OR drug OR surgery OR recovery)"
    ),
    # 5. 약물 유발 성기능장애
    (
        "(drug-induced sexual dysfunction[Title/Abstract] OR "
        "medication-related sexual dysfunction[Title/Abstract] OR "
        "post-finasteride syndrome[Title/Abstract] OR "
        "PSSD[Title/Abstract] OR "
        "persistent sexual side effect[Title/Abstract] OR "
        "antidepressant sexual[Title/Abstract] OR "
        "antihypertensive sexual dysfunction[Title/Abstract] OR "
        "chemotherapy sexual function[Title/Abstract])"
    ),
]

# ─── 유틸리티 ───────────────────────────────────────
def rate_limit(api_key):
    time.sleep(0.35 if api_key else 1.1)

def safe_filename(pmid, title, ext="pdf"):
    title = title or "untitled"
    safe = "".join(c for c in title if c.isalnum() or c in " -_")[:50]
    return f"{pmid}_{safe}.{ext}"

def fetch_url(url, ua="AGA-DCP/1.0", timeout=60, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", ua)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            if attempt < retries - 1:
                wait = (attempt + 1) * 5
                print(f"  [재시도 {attempt+1}/{retries}] {str(e)[:60]}... {wait}초 대기")
                time.sleep(wait)
            else:
                raise

# ─── PubMed 검색 (다중 쿼리 + 중복 제거) ──────────
def search_pubmed_multi(queries, days_back, max_per_query, api_key):
    """여러 쿼리로 검색 후 PMID 합침 (중복 제거)"""
    all_pmids = set()

    today = datetime.now()
    start = today - timedelta(days=days_back)

    for qi, query in enumerate(queries, 1):
        print(f"\n[검색 {qi}/{len(queries)}] 쿼리 실행 중...")
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": max_per_query,
            "sort": "date",
            "retmode": "json",
            "datetype": "pdat",
            "mindate": start.strftime("%Y/%m/%d"),
            "maxdate": today.strftime("%Y/%m/%d"),
        }
        if api_key:
            params["api_key"] = api_key

        url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?{urllib.parse.urlencode(params)}"
        rate_limit(api_key)

        try:
            data = json.loads(fetch_url(url).decode())
            pmids = data.get("esearchresult", {}).get("idlist", [])
            total = data.get("esearchresult", {}).get("count", "0")
            new_count = len(set(pmids) - all_pmids)
            all_pmids.update(pmids)
            print(f"  총 {total}건 중 {len(pmids)}개 가져옴 (신규: {new_count}건)")
        except Exception as e:
            print(f"  [오류] {str(e)[:80]}")
            continue

    print(f"\n[검색 완료] 총 고유 PMID: {len(all_pmids)}건 (중복 제거 후)")
    return list(all_pmids)

# ─── 논문 상세정보 가져오기 ──────────────────────────
def fetch_details(pmids, api_key):
    """efetch로 논문 상세정보(제목, 초록, DOI, PMC ID) 가져오기"""
    papers = []
    batch_size = 50
    total_batches = (len(pmids) + batch_size - 1) // batch_size

    for bi, i in enumerate(range(0, len(pmids), batch_size), 1):
        batch = pmids[i:i+batch_size]
        params = {
            "db": "pubmed",
            "id": ",".join(batch),
            "rettype": "xml",
            "retmode": "xml",
        }
        if api_key:
            params["api_key"] = api_key

        url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?{urllib.parse.urlencode(params)}"
        rate_limit(api_key)

        if bi % 10 == 0 or bi == 1:
            print(f"  [상세정보] 배치 {bi}/{total_batches} 처리 중...")

        try:
            xml_data = fetch_url(url).decode()
        except Exception as e:
            print(f"  [배치 {bi} 오류] {str(e)[:60]} - 건너뜀")
            continue

        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError:
            print(f"  [배치 {bi}] XML 파싱 오류 - 건너뜀")
            continue

        for article in root.findall(".//PubmedArticle"):
            try:
                pmid_el = article.find(".//PMID")
                pmid = pmid_el.text if pmid_el is not None else ""

                title_el = article.find(".//ArticleTitle")
                # ArticleTitle에 자식 태그가 있으면 .text가 None → itertext 사용
                if title_el is not None:
                    title = "".join(title_el.itertext()).strip() or "No title"
                else:
                    title = "No title"

                abstract_parts = []
                for abs_el in article.findall(".//AbstractText"):
                    label = abs_el.get("Label", "")
                    text = "".join(abs_el.itertext())
                    if label:
                        abstract_parts.append(f"{label}: {text}")
                    else:
                        abstract_parts.append(text)
                abstract = "\n".join(abstract_parts)

                doi = ""
                for id_el in article.findall(".//ArticleId"):
                    if id_el.get("IdType") == "doi":
                        doi = id_el.text or ""

                pmc_id = ""
                for id_el in article.findall(".//ArticleId"):
                    if id_el.get("IdType") == "pmc":
                        pmc_id = (id_el.text or "").replace("PMC", "")

                authors = []
                for auth in article.findall(".//Author"):
                    last = auth.findtext("LastName", "")
                    init = auth.findtext("Initials", "")
                    if last:
                        authors.append(f"{last} {init}")

                journal = article.findtext(".//Journal/Title", "")
                year = article.findtext(".//PubDate/Year", "")
                month = article.findtext(".//PubDate/Month", "")

                papers.append({
                    "pmid": pmid,
                    "title": title,
                    "abstract": abstract,
                    "doi": doi,
                    "pmc_id": pmc_id,
                    "authors": ", ".join(authors[:5]),
                    "journal": journal,
                    "pub_date": f"{year} {month}".strip(),
                })
            except Exception as e:
                print(f"  [파싱 오류] {str(e)[:60]} - 건너뜀")
                continue

    return papers

# ─── PDF 다운로드 ────────────────────────────────────
def download_pdf(pmid, title, doi, pmc_id, api_key):
    """PDF 다운로드 시도 (PMC → Unpaywall → Europe PMC)"""
    title = title or "untitled"
    filename = safe_filename(pmid, title, "pdf")
    filepath = os.path.join(PDF_DIR, filename)
    if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
        return True, "cached"

    # 1. PMC OA
    if pmc_id:
        try:
            oa_url = f"https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id=PMC{pmc_id}"
            xml = fetch_url(oa_url).decode()
            m = re.search(r'href="(https?://[^"]+\.pdf)"', xml)
            if m:
                rate_limit(api_key)
                pdf_data = fetch_url(m.group(1))
                if len(pdf_data) > 1000 and pdf_data[:4] == b"%PDF":
                    with open(filepath, "wb") as f:
                        f.write(pdf_data)
                    return True, "pmc_oa"
        except Exception:
            pass

        # PMC direct
        try:
            rate_limit(api_key)
            url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/pdf/"
            pdf_data = fetch_url(url, ua="Mozilla/5.0")
            if len(pdf_data) > 5000 and pdf_data[:4] == b"%PDF":
                with open(filepath, "wb") as f:
                    f.write(pdf_data)
                return True, "pmc"
        except Exception:
            pass

    # 2. Unpaywall
    if doi:
        try:
            rate_limit(api_key)
            uurl = f"https://api.unpaywall.org/v2/{doi}?email=basgenbio@gmail.com"
            data = json.loads(fetch_url(uurl).decode())
            best = data.get("best_oa_location") or {}
            pdf_url = best.get("url_for_pdf") if best else None
            if pdf_url:
                rate_limit(api_key)
                pdf_data = fetch_url(pdf_url, ua="Mozilla/5.0")
                if len(pdf_data) > 1000 and pdf_data[:4] == b"%PDF":
                    with open(filepath, "wb") as f:
                        f.write(pdf_data)
                    return True, "unpaywall"
        except Exception:
            pass

    # 3. Europe PMC
    if pmc_id or pmid:
        try:
            rate_limit(api_key)
            epmc_url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=ext_id:{pmid}&format=json&resultType=core"
            data = json.loads(fetch_url(epmc_url).decode())
            result_list = data.get("resultList") or {}
            results = result_list.get("result") or []
            if results:
                ftl_wrapper = results[0].get("fullTextUrlList") or {}
                ftl = ftl_wrapper.get("fullTextUrl") or []
                for ft in ftl:
                    if ft.get("documentStyle") == "pdf" and ft.get("availability") != "Subscription required":
                        rate_limit(api_key)
                        pdf_data = fetch_url(ft["url"], ua="Mozilla/5.0")
                        if len(pdf_data) > 1000 and pdf_data[:4] == b"%PDF":
                            with open(filepath, "wb") as f:
                                f.write(pdf_data)
                            return True, "europe_pmc"
        except Exception:
            pass

    return False, "none"

# ─── 초록 텍스트 저장 ───────────────────────────────
def save_abstract(paper):
    title = paper.get("title") or "untitled"
    pmid = paper.get("pmid") or "unknown"
    filename = safe_filename(pmid, title, "txt")
    filepath = os.path.join(TXT_DIR, filename)
    if os.path.exists(filepath):
        return

    content = f"PMID: {pmid}\n"
    content += f"Title: {title}\n"
    content += f"Authors: {paper.get('authors', '')}\n"
    content += f"Journal: {paper.get('journal', '')}\n"
    content += f"Date: {paper.get('pub_date', '')}\n"
    content += f"DOI: {paper.get('doi', '')}\n"
    content += f"\n{'='*60}\nAbstract:\n{'='*60}\n\n"
    content += paper.get("abstract") or "(No abstract available)"
    content += "\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

# ─── 진행상황 저장/로드 (이어하기 지원) ─────────────
PROGRESS_FILE = os.path.join(BASE_DIR, FOLDER_NAME, "_progress.json")

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def save_progress(data):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ─── 메인 ───────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="발기부전/성기능장애/전립선 논문 다운로드")
    parser.add_argument("--days", type=int, default=9125, help="검색 기간 (일). 기본값: 9125일(~25년)")
    parser.add_argument("--max", type=int, default=10000, help="쿼리당 최대 결과. 기본값: 10000")
    parser.add_argument("--api-key", type=str, default="", help="NCBI API Key")
    parser.add_argument("--reset", action="store_true", help="진행상황 초기화 후 처음부터")
    args = parser.parse_args()

    api_key = args.api_key or os.getenv("NCBI_API_KEY", "")

    # 이어하기 확인
    progress = None if args.reset else load_progress()
    if progress and progress.get("papers"):
        done_pmids = set(progress.get("done_pmids", []))
        papers = progress["papers"]
        pdf_ok = progress.get("pdf_ok", 0)
        txt_ok = progress.get("txt_ok", 0)
        stats = progress.get("stats", {})
        remaining = [p for p in papers if p["pmid"] not in done_pmids]
        print("=" * 60)
        print("  논문 다운로드 (이어하기)")
        print("=" * 60)
        print(f"  전체: {len(papers)}건 | 완료: {len(done_pmids)}건 | 남은: {len(remaining)}건")
        print(f"  PDF: {pdf_ok}건 | TXT: {txt_ok}건")
        print("=" * 60)
        print()
    else:
        print("=" * 60)
        print("  발기부전/성기능장애/전립선 논문 다운로드")
        print("=" * 60)
        print(f"  검색 기간: 최근 {args.days}일 (~{args.days//365}년)")
        print(f"  쿼리당 최대: {args.max}건")
        print(f"  검색 카테고리: {len(SEARCH_QUERIES)}개")
        print(f"  API Key: {'있음' if api_key else '없음 (1req/sec 제한)'}")
        print(f"  PDF 저장: {PDF_DIR}")
        print(f"  TXT 저장: {TXT_DIR}")
        print("=" * 60)
        print()

        # 1. 다중 검색 (중복 제거)
        pmids = search_pubmed_multi(SEARCH_QUERIES, args.days, args.max, api_key)
        if not pmids:
            print("검색 결과가 없습니다.")
            return

        # 기존 다운로드된 파일의 PMID 체크 (중복 방지)
        existing_pmids = set()
        for f in os.listdir(PDF_DIR):
            parts = f.split("_", 1)
            if parts[0].isdigit():
                existing_pmids.add(parts[0])
        for f in os.listdir(TXT_DIR):
            parts = f.split("_", 1)
            if parts[0].isdigit():
                existing_pmids.add(parts[0])

        new_pmids = [p for p in pmids if p not in existing_pmids]
        print(f"\n[중복 제거] 기존 {len(existing_pmids)}건 제외 → 신규 {len(new_pmids)}건 처리 예정")

        # 2. 상세정보
        print(f"\n[상세] {len(new_pmids)}건 상세정보 가져오는 중...")
        papers = fetch_details(new_pmids, api_key)
        print(f"[상세] {len(papers)}건 처리 완료")

        done_pmids = set()
        pdf_ok = 0
        txt_ok = 0
        stats = {"pmc_oa": 0, "pmc": 0, "unpaywall": 0, "europe_pmc": 0, "cached": 0}
        remaining = papers

        # 상세정보 저장 (이어하기용)
        save_progress({
            "papers": papers,
            "done_pmids": [],
            "pdf_ok": 0,
            "txt_ok": 0,
            "stats": stats,
        })
        print("  [진행상황 저장됨 - 중단 후 다시 실행하면 이어서 진행]")

    # 3. PDF 다운로드 + 초록 저장
    total = len(papers)
    print(f"\n[다운로드] {len(remaining)}건 처리 시작...\n")

    try:
        for i, paper in enumerate(remaining, 1):
            pmid = paper.get("pmid") or "unknown"
            title = (paper.get("title") or "untitled")[:60]
            done_count = len(done_pmids) + i
            print(f"[{done_count}/{total}] PMID {pmid}: {title}...")

            try:
                success, source = download_pdf(
                    pmid, paper.get("title"), paper.get("doi", ""),
                    paper.get("pmc_id", ""), api_key
                )

                if success:
                    pdf_ok += 1
                    stats[source] = stats.get(source, 0) + 1
                    print(f"  ✓ PDF ({source})")
                else:
                    save_abstract(paper)
                    txt_ok += 1
                    print(f"  → 초록 저장 (TXT)")
            except Exception as e:
                print(f"  [오류] {str(e)[:60]} - 초록 저장으로 대체")
                try:
                    save_abstract(paper)
                    txt_ok += 1
                except Exception:
                    pass

            done_pmids.add(pmid)

            # 50건마다 진행상황 저장
            if i % 50 == 0:
                save_progress({
                    "papers": papers,
                    "done_pmids": list(done_pmids),
                    "pdf_ok": pdf_ok,
                    "txt_ok": txt_ok,
                    "stats": stats,
                })
                print(f"  --- 진행: {done_count}/{total} (PDF:{pdf_ok} TXT:{txt_ok}) ---")

    except KeyboardInterrupt:
        print("\n\n  중단됨! 진행상황 저장 중...")
    except Exception as e:
        print(f"\n\n  예상치 못한 오류: {e}\n  진행상황 저장 중...")

    # 진행상황 저장
    save_progress({
        "papers": papers,
        "done_pmids": list(done_pmids),
        "pdf_ok": pdf_ok,
        "txt_ok": txt_ok,
        "stats": stats,
    })

    # 4. 결과
    print()
    print("=" * 60)
    if len(done_pmids) < total:
        print(f"  중간 저장 완료! ({len(done_pmids)}/{total}건)")
        print(f"  → 같은 명령어로 다시 실행하면 이어서 진행됩니다")
    else:
        print("  다운로드 완료!")
    print("=" * 60)
    print(f"  총 논문: {total}건")
    print(f"  처리 완료: {len(done_pmids)}건")
    print(f"  PDF 다운로드: {pdf_ok}건")
    print(f"  초록 텍스트: {txt_ok}건")
    print(f"  ── 소스별 ──")
    for src, cnt in stats.items():
        if cnt > 0:
            print(f"  {src}: {cnt}건")
    print(f"\n  PDF 폴더: {PDF_DIR}")
    print(f"  TXT 폴더: {TXT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
