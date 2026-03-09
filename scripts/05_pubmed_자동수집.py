"""
=============================================================
05_pubmed_자동수집.py
=============================================================
용도: PubMed에서 AGA 관련 새 논문을 자동 검색하고
      Full Text PDF를 다운로드합니다.

      Full Text 다운로드 소스 (우선순위):
      1. PubMed Central (PMC) — OpenAccess 논문
      2. Unpaywall API — 합법적 OA 사본 (출판사/저장소)
      3. Europe PMC — 유럽 OA 저장소
      4. CORE API — 전 세계 OA 저장소 통합

실행: python 05_pubmed_자동수집.py
      python 05_pubmed_자동수집.py --all     # 과거 30년 전체
      python 05_pubmed_자동수집.py --years 5  # 최근 5년
소요: 약 5-30분 (검색 범위에 따라)
비용: 무료 (모든 API 무료)
=============================================================
"""

import os
import sys
import json
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import platform

# Windows UTF-8 인코딩 처리
if platform.system() == "Windows":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    sys.stdout.reconfigure(encoding="utf-8")


class PubMedPaperCollector:
    """PubMed에서 AGA 관련 논문을 수집하는 메인 클래스"""

    # NCBI API 설정
    NCBI_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    NCBI_EMAIL = "researcher@example.com"  # NCBI에 요청 시 필수

    # Unpaywall API 설정 (이메일만 필요, 무료)
    UNPAYWALL_EMAIL = "researcher@example.com"

    # CORE API 설정 (무료, API key 있으면 더 빠름)
    CORE_API_URL = "https://api.core.ac.uk/v3"

    def __init__(self, base_folder: str, days_back: int = 7, max_results: int = 500):
        """
        Args:
            base_folder: 문헌데이터_탈모 폴더 경로
            days_back: 몇 일 전부터 검색할지 (기본값: 7일)
            max_results: 최대 검색 결과 수 (기본값: 500, 전체검색 시 10000)
        """
        self.base_folder = base_folder
        self.days_back = days_back
        self.max_results = max_results

        # API Key 설정 (환경변수 또는 빈 문자열)
        self.api_key = os.getenv("NCBI_API_KEY", "")
        self.core_api_key = os.getenv("CORE_API_KEY", "")

        # Rate limiting 설정 (초당 요청 수)
        self.rate_limit = 3 if self.api_key else 1
        self.request_interval = 1.0 / self.rate_limit
        self.last_request_time = 0

        # 폴더 설정
        self.new_papers_folder = os.path.join(self.base_folder, "new_papers")
        self.new_papers_txt_folder = os.path.join(self.base_folder, "new_papers_txt")
        self.collection_log_path = os.path.join(self.base_folder, "collection_log.json")
        self.pipeline_status_path = os.path.join(self.base_folder, "pipeline_status.json")

        # 폴더 생성
        os.makedirs(self.new_papers_folder, exist_ok=True)
        os.makedirs(self.new_papers_txt_folder, exist_ok=True)

        # 통계
        self.papers_found = 0
        self.papers_downloaded = 0
        self.papers_abstract_only = 0
        self.papers_skipped = 0
        self.pmids_collected = set()

        # 다운로드 소스별 통계
        self.download_stats = {
            "pmc": 0,
            "unpaywall": 0,
            "europe_pmc": 0,
            "core": 0,
            "abstract_only": 0,
        }

        # 이전 수집 데이터 로드
        self._load_existing_pmids()

        print(f"[초기화] 기본 폴더: {self.base_folder}")
        print(f"[초기화] 검색 기간: 지난 {days_back}일")
        print(f"[초기화] NCBI API Key: {'있음' if self.api_key else '없음 (1req/sec 제한)'}")
        print(f"[초기화] CORE API Key: {'있음' if self.core_api_key else '없음'}")
        print(f"[초기화] 이미 수집된 논문: {len(self.pmids_collected)}개")
        print(f"[초기화] Full Text 소스: PMC → Unpaywall → Europe PMC → CORE")
        print()

    def _load_existing_pmids(self):
        """collection_log.json에서 기존 PMID 로드"""
        if not os.path.exists(self.collection_log_path):
            return

        try:
            with open(self.collection_log_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    self.pmids_collected = {str(item.get("pmid")) for item in data}
        except Exception as e:
            print(f"[경고] 기존 collection_log.json 읽기 실패: {e}")

    def _rate_limit_wait(self):
        """Rate limiting 적용"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.request_interval:
            time.sleep(self.request_interval - elapsed)
        self.last_request_time = time.time()

    def _build_search_query(self) -> str:
        """PubMed 검색 쿼리 구성"""
        query = (
            "(androgenetic alopecia[Title/Abstract] OR male pattern baldness[Title/Abstract] "
            "OR AGA hair loss[Title/Abstract] OR hair loss treatment[Title/Abstract]) "
            "AND (drug OR compound OR target OR inhibitor OR mechanism OR pathway)"
        )
        return query

    def _build_date_range(self) -> str:
        """날짜 범위 쿼리 구성 (mindate:maxdate)"""
        today = datetime.now()
        start_date = today - timedelta(days=self.days_back)

        min_date = start_date.strftime("%Y/%m/%d")
        max_date = today.strftime("%Y/%m/%d")

        return f"{min_date}:{max_date}"

    def search_pubmed(self) -> List[str]:
        """
        PubMed에서 AGA 관련 논문 검색 (XML 파싱)

        Returns:
            PMID 리스트
        """
        print("[검색] PubMed 검색 시작...")

        query = self._build_search_query()
        date_range = self._build_date_range()

        params = {
            "db": "pubmed",
            "term": query,
            "datetype": "pdat",
            "mindate": date_range.split(":")[0],
            "maxdate": date_range.split(":")[1],
            "retmax": self.max_results,
            "usehistory": "y",
            "tool": "AGA_PaperCollector",
            "email": self.NCBI_EMAIL,
        }

        if self.api_key:
            params["api_key"] = self.api_key

        url = f"{self.NCBI_BASE_URL}/esearch.fcgi?" + urllib.parse.urlencode(params)

        try:
            self._rate_limit_wait()
            print(f"[검색] URL: {url[:120]}...")
            with urllib.request.urlopen(url, timeout=60) as response:
                xml_data = response.read().decode("utf-8")

            # XML 파싱
            root = ET.fromstring(xml_data)

            # 총 결과 수
            count_elem = root.find("Count")
            total_count = int(count_elem.text) if count_elem is not None else 0

            # PMID 리스트 추출
            pmids = []
            id_list = root.find("IdList")
            if id_list is not None:
                for id_elem in id_list.findall("Id"):
                    if id_elem.text:
                        pmids.append(id_elem.text)

            self.papers_found = len(pmids)

            print(f"[검색] PubMed 총 결과: {total_count}개")
            print(f"[검색] 가져온 PMID: {self.papers_found}개")
            print(f"[검색] 검색 기간: {date_range}")

            return pmids

        except Exception as e:
            print(f"[오류] PubMed 검색 실패: {e}")
            import traceback
            traceback.print_exc()
            return []

    def fetch_paper_details(self, pmid: str) -> Optional[Dict]:
        """
        PubMed esummary (JSON) + efetch (XML for abstract)로 논문 상세 정보 가져오기
        """
        # esummary는 JSON을 지원함 (retmode=json)
        params = {
            "db": "pubmed",
            "id": pmid,
            "retmode": "json",
            "tool": "AGA_PaperCollector",
            "email": self.NCBI_EMAIL,
        }

        if self.api_key:
            params["api_key"] = self.api_key

        url = f"{self.NCBI_BASE_URL}/esummary.fcgi?" + urllib.parse.urlencode(params)

        try:
            self._rate_limit_wait()
            with urllib.request.urlopen(url, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))

            article = data.get("result", {}).get(pmid, {})
            if not article or "error" in article:
                return None

            # DOI 추출
            doi = None
            article_ids = article.get("articleids", [])
            for aid in article_ids:
                if aid.get("idtype") == "doi":
                    doi = aid.get("value")
                    break

            # PMC ID 추출
            pmc_id = None
            for aid in article_ids:
                if aid.get("idtype") == "pmc":
                    pmc_val = aid.get("value", "")
                    pmc_id = pmc_val.replace("PMC", "")
                    break

            # 저자 추출
            authors_list = article.get("authors", [])
            author_names = [a.get("name", "") for a in authors_list[:5]]
            authors_str = ", ".join(author_names)
            if len(authors_list) > 5:
                authors_str += ", et al."

            paper_info = {
                "pmid": pmid,
                "title": article.get("title", ""),
                "authors": authors_str,
                "abstract": "",  # esummary에는 abstract 없음
                "journal": article.get("source", ""),
                "pub_date": article.get("pubdate", ""),
                "doi": doi,
                "pmc_id": pmc_id,
                "collected_date": datetime.now().isoformat(),
                "pdf_downloaded": False,
            }

            # Abstract는 efetch XML로 별도 조회
            abstract = self._fetch_abstract(pmid)
            if abstract:
                paper_info["abstract"] = abstract

            return paper_info

        except Exception as e:
            print(f"[오류] PMID {pmid} 상세 정보 조회 실패: {e}")
            return None

    def _fetch_abstract(self, pmid: str) -> str:
        """efetch XML에서 Abstract 추출"""
        params = {
            "db": "pubmed",
            "id": pmid,
            "rettype": "abstract",
            "retmode": "xml",
            "tool": "AGA_PaperCollector",
            "email": self.NCBI_EMAIL,
        }

        if self.api_key:
            params["api_key"] = self.api_key

        url = f"{self.NCBI_BASE_URL}/efetch.fcgi?" + urllib.parse.urlencode(params)

        try:
            self._rate_limit_wait()
            with urllib.request.urlopen(url, timeout=30) as response:
                xml_data = response.read().decode("utf-8")

            root = ET.fromstring(xml_data)

            # Abstract 텍스트 추출
            abstract_parts = []
            for article in root.iter("PubmedArticle"):
                for abs_elem in article.iter("AbstractText"):
                    label = abs_elem.get("Label", "")
                    text = "".join(abs_elem.itertext()).strip()
                    if label:
                        abstract_parts.append(f"{label}: {text}")
                    else:
                        abstract_parts.append(text)

            return " ".join(abstract_parts)

        except Exception:
            return ""

    def get_pmc_id(self, pmid: str) -> Optional[str]:
        """
        PubMed ID로 PMC ID 찾기 (elink XML)
        esummary에서 못 찾은 경우에만 사용
        """
        params = {
            "dbfrom": "pubmed",
            "db": "pmc",
            "id": pmid,
            "retmode": "xml",
            "tool": "AGA_PaperCollector",
            "email": self.NCBI_EMAIL,
        }

        if self.api_key:
            params["api_key"] = self.api_key

        url = f"{self.NCBI_BASE_URL}/elink.fcgi?" + urllib.parse.urlencode(params)

        try:
            self._rate_limit_wait()
            with urllib.request.urlopen(url, timeout=30) as response:
                xml_data = response.read().decode("utf-8")

            root = ET.fromstring(xml_data)

            # LinkSetDb에서 PMC ID 추출
            for linksetdb in root.iter("LinkSetDb"):
                for link in linksetdb.iter("Link"):
                    id_elem = link.find("Id")
                    if id_elem is not None and id_elem.text:
                        return id_elem.text

            return None

        except Exception as e:
            print(f"[경고] PMID {pmid}의 PMC ID 조회 실패: {e}")
            return None

    def _make_safe_filename(self, pmid: str, title: str) -> str:
        """안전한 파일명 생성"""
        safe_title = "".join(c for c in title if c.isalnum() or c in " -_")[:50]
        return f"{pmid}_{safe_title}.pdf"

    def _download_pdf_url(self, url: str, pdf_path: str, source: str, pmid: str) -> bool:
        """URL에서 PDF를 다운로드하는 공통 함수"""
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "AGA-Drug-Discovery/1.0 (mailto:researcher@example.com)")
            with urllib.request.urlopen(req, timeout=30) as response:
                pdf_data = response.read()

            if len(pdf_data) < 1000:
                return False

            # PDF 시그니처 확인 (%PDF)
            if not pdf_data[:4] == b"%PDF":
                # HTML이나 다른 형식일 수 있음
                if b"<html" in pdf_data[:500].lower() or b"<!doctype" in pdf_data[:500].lower():
                    return False

            with open(pdf_path, "wb") as f:
                f.write(pdf_data)

            size_mb = len(pdf_data) / (1024 * 1024)
            print(f"    ✓ [{source}] PDF 저장 ({size_mb:.1f}MB)")
            return True

        except Exception:
            return False

    def download_fulltext(self, pmid: str, title: str, doi: Optional[str] = None,
                          pmc_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        여러 소스에서 Full Text PDF 다운로드 시도 (우선순위 순서)

        Args:
            pmid: PubMed ID
            title: 논문 제목
            doi: DOI (있는 경우)
            pmc_id: PMC ID (있는 경우)

        Returns:
            (성공여부, 다운로드 소스)
        """
        pdf_filename = self._make_safe_filename(pmid, title)
        pdf_path = os.path.join(self.new_papers_folder, pdf_filename)

        # 이미 다운로드된 PDF가 있으면 건너뜀
        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 1000:
            return True, "cached"

        # ── 소스 1: PubMed Central (PMC) ──────────────────────
        if pmc_id:
            self._rate_limit_wait()
            url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/pdf/"
            if self._download_pdf_url(url, pdf_path, "PMC", pmid):
                self.download_stats["pmc"] += 1
                return True, "pmc"

        # ── 소스 2: Unpaywall (DOI 필요) ──────────────────────
        if doi:
            pdf_url = self._try_unpaywall(doi)
            if pdf_url:
                self._rate_limit_wait()
                if self._download_pdf_url(pdf_url, pdf_path, "Unpaywall", pmid):
                    self.download_stats["unpaywall"] += 1
                    return True, "unpaywall"

        # ── 소스 3: Europe PMC ────────────────────────────────
        if pmc_id or pmid:
            pdf_url = self._try_europe_pmc(pmid, pmc_id)
            if pdf_url:
                self._rate_limit_wait()
                if self._download_pdf_url(pdf_url, pdf_path, "EuropePMC", pmid):
                    self.download_stats["europe_pmc"] += 1
                    return True, "europe_pmc"

        # ── 소스 4: CORE (DOI 또는 제목 검색) ─────────────────
        if doi or title:
            pdf_url = self._try_core(doi, title)
            if pdf_url:
                self._rate_limit_wait()
                if self._download_pdf_url(pdf_url, pdf_path, "CORE", pmid):
                    self.download_stats["core"] += 1
                    return True, "core"

        # ── Full text를 못 받은 경우: Abstract만 텍스트로 저장 ──
        self.download_stats["abstract_only"] += 1
        return False, "none"

    def _try_unpaywall(self, doi: str) -> Optional[str]:
        """
        Unpaywall API로 합법적 OA PDF URL 찾기
        https://unpaywall.org/products/api (무료, 이메일만 필요)
        """
        try:
            encoded_doi = urllib.parse.quote(doi, safe="")
            url = f"https://api.unpaywall.org/v2/{encoded_doi}?email={self.UNPAYWALL_EMAIL}"

            self._rate_limit_wait()
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "AGA-Drug-Discovery/1.0")

            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))

            # best_oa_location에서 PDF URL 추출
            best_oa = data.get("best_oa_location")
            if best_oa:
                pdf_url = best_oa.get("url_for_pdf")
                if pdf_url:
                    return pdf_url

                # PDF URL이 없으면 landing page URL이라도 확인
                landing_url = best_oa.get("url_for_landing_page")
                # landing page는 PDF가 아닐 수 있으므로 스킵

            # 다른 OA locations도 확인
            for loc in data.get("oa_locations", []):
                pdf_url = loc.get("url_for_pdf")
                if pdf_url:
                    return pdf_url

            return None

        except Exception:
            return None

    def _try_europe_pmc(self, pmid: str, pmc_id: Optional[str] = None) -> Optional[str]:
        """
        Europe PMC에서 Full Text PDF URL 찾기
        https://europepmc.org/RestfulWebService (무료)
        """
        try:
            # PMC ID가 있으면 직접 PDF URL 시도
            if pmc_id:
                return f"https://europepmc.org/backend/ptpmcrender.fcgi?accid=PMC{pmc_id}&blobtype=pdf"

            # PMID로 Europe PMC 검색
            url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:{pmid}&format=json"

            self._rate_limit_wait()
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "AGA-Drug-Discovery/1.0")

            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))

            results = data.get("resultList", {}).get("result", [])
            if results:
                result = results[0]
                # isOpenAccess 체크
                if result.get("isOpenAccess") == "Y":
                    epmc_id = result.get("pmcid", "")
                    if epmc_id:
                        return f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={epmc_id}&blobtype=pdf"

            return None

        except Exception:
            return None

    def _try_core(self, doi: Optional[str] = None, title: Optional[str] = None) -> Optional[str]:
        """
        CORE API에서 Full Text PDF URL 찾기
        https://core.ac.uk/services/api (무료, API key 있으면 속도 빠름)
        """
        try:
            # DOI로 먼저 검색
            if doi:
                encoded_doi = urllib.parse.quote(doi, safe="")
                url = f"{self.CORE_API_URL}/search/works?q=doi:{encoded_doi}&limit=1"
            elif title:
                # 제목으로 검색 (제목이 길면 앞부분만)
                short_title = title[:100] if len(title) > 100 else title
                encoded_title = urllib.parse.quote(short_title, safe="")
                url = f"{self.CORE_API_URL}/search/works?q={encoded_title}&limit=1"
            else:
                return None

            self._rate_limit_wait()
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "AGA-Drug-Discovery/1.0")
            if self.core_api_key:
                req.add_header("Authorization", f"Bearer {self.core_api_key}")

            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))

            results = data.get("results", [])
            if results:
                result = results[0]
                # downloadUrl 확인
                download_url = result.get("downloadUrl")
                if download_url and download_url.endswith(".pdf"):
                    return download_url

                # sourceFulltextUrls 확인
                source_urls = result.get("sourceFulltextUrls", [])
                for surl in source_urls:
                    if surl and (".pdf" in surl.lower()):
                        return surl

            return None

        except Exception:
            return None

    def save_abstract_as_text(self, paper_info: Dict):
        """
        PDF를 받지 못한 경우 Abstract를 텍스트 파일로 저장
        (나중에 02_정보추출.py에서 처리할 수 있도록)
        """
        pmid = paper_info.get("pmid", "unknown")
        abstract = paper_info.get("abstract", "")
        title = paper_info.get("title", "")

        if not abstract and not title:
            return

        safe_title = "".join(c for c in title if c.isalnum() or c in " -_")[:50]
        txt_filename = f"{pmid}_{safe_title}.txt"
        txt_path = os.path.join(self.new_papers_txt_folder, txt_filename)

        try:
            content = f"PMID: {pmid}\n"
            content += f"Title: {title}\n"
            content += f"Authors: {paper_info.get('authors', '')}\n"
            content += f"Journal: {paper_info.get('journal', '')}\n"
            content += f"Date: {paper_info.get('pub_date', '')}\n"
            content += f"DOI: {paper_info.get('doi', '')}\n"
            content += f"\n{'='*60}\nAbstract:\n{'='*60}\n\n"
            content += abstract if abstract else "(No abstract available)"
            content += "\n"

            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(content)

        except Exception as e:
            print(f"    [경고] Abstract 저장 실패: {e}")

    def save_to_collection_log(self, paper_info: Dict):
        """
        논문 정보를 collection_log.json에 저장

        Args:
            paper_info: 논문 정보 딕셔너리
        """
        # 기존 데이터 로드
        collection = []
        if os.path.exists(self.collection_log_path):
            try:
                with open(self.collection_log_path, "r", encoding="utf-8") as f:
                    collection = json.load(f)
            except Exception as e:
                print(f"[경고] collection_log.json 읽기 실패: {e}")

        # 데이터 추가
        collection.append(paper_info)

        # 파일 저장
        try:
            with open(self.collection_log_path, "w", encoding="utf-8") as f:
                json.dump(collection, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[오류] collection_log.json 저장 실패: {e}")

    def update_pipeline_status(self, status: str, error_msg: Optional[str] = None):
        """
        pipeline_status.json 업데이트

        Args:
            status: "searching", "idle", 또는 "error"
            error_msg: 에러 메시지 (status가 "error"일 때)
        """
        pipeline_status = {
            "agent": "paper_searcher",
            "status": status,
            "last_run": datetime.now().isoformat(),
            "papers_found": self.papers_found,
            "papers_downloaded": self.papers_downloaded,
            "papers_skipped": self.papers_skipped,
        }

        if error_msg:
            pipeline_status["error"] = error_msg

        try:
            with open(self.pipeline_status_path, "w", encoding="utf-8") as f:
                json.dump(pipeline_status, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[경고] pipeline_status.json 저장 실패: {e}")

    def run(self):
        """메인 실행 함수"""
        try:
            self.update_pipeline_status("searching")

            # 1. PubMed 검색
            pmids = self.search_pubmed()

            if not pmids:
                print("[결과] 새로운 논문이 없습니다.")
                self.update_pipeline_status("idle")
                return

            print(f"\n[처리] {len(pmids)}개 논문 처리 시작...\n")

            # 2. 각 논문 처리
            for i, pmid in enumerate(pmids, 1):
                print(f"[{i}/{len(pmids)}] PMID {pmid} 처리 중...")

                # 이미 수집했는지 확인
                if pmid in self.pmids_collected:
                    print(f"  → 이미 수집된 논문입니다.")
                    self.papers_skipped += 1
                    continue

                try:
                    # 상세 정보 조회
                    paper_info = self.fetch_paper_details(pmid)
                    if not paper_info:
                        print(f"  → 상세 정보 조회 실패")
                        continue

                    # PMC ID 찾기 (esummary에서 이미 가져온 경우 스킵)
                    pmc_id = paper_info.get("pmc_id")
                    if not pmc_id:
                        pmc_id = self.get_pmc_id(pmid)
                        if pmc_id:
                            paper_info["pmc_id"] = pmc_id

                    # Full Text PDF 다운로드 (4개 소스 순차 시도)
                    doi = paper_info.get("doi")
                    pdf_success, source = self.download_fulltext(
                        pmid, paper_info["title"], doi=doi, pmc_id=pmc_id
                    )

                    paper_info["pdf_downloaded"] = pdf_success
                    paper_info["download_source"] = source

                    if pdf_success:
                        self.papers_downloaded += 1
                    else:
                        # PDF를 못 받으면 Abstract라도 텍스트로 저장
                        self.save_abstract_as_text(paper_info)
                        self.papers_abstract_only += 1
                        print(f"    → Full text 없음. Abstract만 저장.")

                    # collection_log.json에 저장
                    self.save_to_collection_log(paper_info)

                    # 수집 목록에 추가
                    self.pmids_collected.add(pmid)

                    # 짧은 정보 출력
                    print(f"  → 제목: {paper_info['title'][:60]}...")
                    author_first = paper_info['authors'].split(',')[0] if paper_info['authors'] else 'N/A'
                    print(f"  → 저자: {author_first} | DOI: {doi or 'N/A'}")
                    print()

                except KeyboardInterrupt:
                    print("\n\n  사용자 중단. 지금까지 결과를 저장합니다...")
                    break
                except Exception as e:
                    print(f"  → ERROR: {str(e)[:80]}")
                    continue

            # 최종 상태 업데이트
            self.update_pipeline_status("idle")

            # 최종 통계 출력
            print("\n" + "="*60)
            print("[완료] PubMed 논문 수집 완료")
            print("="*60)
            print(f"  발견된 논문: {self.papers_found}개")
            print(f"  건너뛴 논문 (기존): {self.papers_skipped}개")
            print(f"  Full Text PDF 다운로드: {self.papers_downloaded}개")
            print(f"  Abstract만 저장: {self.papers_abstract_only}개")
            print()
            print(f"  ── 다운로드 소스별 통계 ──")
            print(f"  PMC (PubMed Central):  {self.download_stats['pmc']}개")
            print(f"  Unpaywall:             {self.download_stats['unpaywall']}개")
            print(f"  Europe PMC:            {self.download_stats['europe_pmc']}개")
            print(f"  CORE:                  {self.download_stats['core']}개")
            print(f"  Full text 없음:        {self.download_stats['abstract_only']}개")
            print()
            total_with_text = self.papers_downloaded + self.papers_abstract_only
            if total_with_text > 0:
                ft_rate = self.papers_downloaded / total_with_text * 100
                print(f"  Full Text 확보율: {ft_rate:.1f}%")
            print()
            print(f"  총 수집된 논문: {len(self.pmids_collected)}개")
            print(f"  PDF 저장 위치: {self.new_papers_folder}")
            print(f"  Abstract 저장: {self.new_papers_txt_folder}")
            print(f"  로그 파일: {self.collection_log_path}")
            print("="*60 + "\n")

        except Exception as e:
            print(f"\n[오류] 수집 중 오류 발생: {e}")
            self.update_pipeline_status("error", str(e))


def main():
    """메인 진입점"""
    import argparse

    parser = argparse.ArgumentParser(description="PubMed AGA 논문 자동 수집")
    parser.add_argument("--days", type=int, default=7,
                       help="검색 기간 (일). 기본값: 7일")
    parser.add_argument("--all", action="store_true",
                       help="과거 논문 전체 검색 (최근 30년)")
    parser.add_argument("--years", type=int, default=None,
                       help="검색 기간 (년). 예: --years 10 → 최근 10년")
    args = parser.parse_args()

    # BASE_FOLDER 설정
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_folder = os.path.dirname(script_dir)  # 문헌데이터_탈모 폴더

    # 검색 기간 및 결과 수 결정
    max_results = 500  # 기본값
    if args.all:
        days_back = 365 * 30  # 30년 = 사실상 전체
        max_results = 10000
        print("=" * 60)
        print("  [전체 검색 모드] 과거 30년간 모든 AGA 논문을 검색합니다.")
        print("  PubMed 최대 10,000건까지 수집 가능합니다.")
        print("  소요 시간: 약 30분-1시간 (논문 수에 따라)")
        print("=" * 60)
        print()
    elif args.years:
        days_back = 365 * args.years
        max_results = 5000
        print(f"  [기간 검색] 최근 {args.years}년간 AGA 논문을 검색합니다.")
    else:
        days_back = args.days

    # 수집 시작
    collector = PubMedPaperCollector(base_folder, days_back=days_back, max_results=max_results)
    collector.run()


if __name__ == "__main__":
    main()
