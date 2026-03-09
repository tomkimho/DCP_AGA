"""
=============================================================
07_biorxiv_수집.py
=============================================================
용도: bioRxiv/medRxiv에서 AGA 관련 프리프린트를 자동 수집합니다.

실행: python 07_biorxiv_수집.py
소요: 약 3-5분
비용: 무료 (bioRxiv API)
=============================================================
"""

import os
import json
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

# UTF-8 인코딩 설정
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


class BioRxivCollector:
    """bioRxiv/medRxiv 프리프린트 수집 클래스"""

    def __init__(self, base_folder):
        self.base_folder = base_folder
        self.data_folder = os.path.join(base_folder, "data")
        self.new_papers_folder = os.path.join(self.data_folder, "new_papers")
        self.logs_folder = os.path.join(self.data_folder, "logs")

        # 폴더 생성
        os.makedirs(self.new_papers_folder, exist_ok=True)
        os.makedirs(self.logs_folder, exist_ok=True)

        self.log_file = os.path.join(self.logs_folder, "collection_log.json")
        self.status_file = os.path.join(self.data_folder, "pipeline_status.json")

        # AGA 관련 키워드
        self.keywords = [
            "alopecia", "hair loss", "hair growth", "hair follicle",
            "dermal papilla", "5alpha-reductase", "minoxidil", "finasteride",
            "dutasteride", "androgenetic", "baldness", "scalp", "DHT",
            "dihydrotestosterone"
        ]

        # 기존 로그 로드
        self.existing_dois = self._load_existing_dois()
        self.papers_found = 0

    def _load_existing_dois(self):
        """기존 수집된 논문의 DOI 로드 (중복 제거용)"""
        if not os.path.exists(self.log_file):
            return set()

        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                log_data = json.load(f)
                if isinstance(log_data, list):
                    return {item['doi'] for item in log_data if 'doi' in item}
                elif isinstance(log_data, dict) and 'papers' in log_data:
                    return {item['doi'] for item in log_data['papers'] if 'doi' in item}
        except Exception as e:
            print(f"[경고] 기존 로그 로드 실패: {e}")

        return set()

    def _fetch_json(self, url, timeout=15):
        """URL에서 JSON 데이터 가져오기 (urllib 사용)"""
        try:
            req = urllib.request.Request(
                url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = response.read().decode('utf-8')
                return json.loads(data)
        except urllib.error.HTTPError as e:
            print(f"[HTTP 오류] {url}: {e.code}")
            return None
        except urllib.error.URLError as e:
            print(f"[URL 오류] {url}: {e.reason}")
            return None
        except json.JSONDecodeError as e:
            print(f"[JSON 파싱 오류] {url}: {e}")
            return None
        except Exception as e:
            print(f"[오류] {url}: {e}")
            return None

    def _keyword_in_text(self, text):
        """텍스트에 AGA 관련 키워드가 포함되어 있는지 확인"""
        if not text:
            return False
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.keywords)

    def _download_pdf(self, doi, version=1, source='biorxiv'):
        """PDF 다운로드 (bioRxiv/medRxiv)"""
        try:
            if source == 'biorxiv':
                pdf_url = f"https://www.biorxiv.org/content/{doi}v{version}.full.pdf"
            else:  # medRxiv
                pdf_url = f"https://www.medrxiv.org/content/{doi}v{version}.full.pdf"

            filename = f"{doi.replace('/', '_')}_v{version}.pdf"
            pdf_path = os.path.join(self.new_papers_folder, filename)

            # 이미 다운로드된 파일 확인
            if os.path.exists(pdf_path):
                print(f"  [PDF] 이미 다운로드됨: {filename}")
                return pdf_path

            print(f"  [PDF] 다운로드 중: {filename}")
            req = urllib.request.Request(
                pdf_url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )

            with urllib.request.urlopen(req, timeout=20) as response:
                pdf_data = response.read()
                with open(pdf_path, 'wb') as f:
                    f.write(pdf_data)

            print(f"  [PDF] 저장 완료: {filename}")
            return pdf_path

        except Exception as e:
            print(f"  [PDF 다운로드 실패] {doi}: {e}")
            return None

    def _collect_from_server(self, server, start_date, end_date, cursor=0):
        """bioRxiv/medRxiv에서 프리프린트 수집"""
        papers = []

        if server == 'biorxiv':
            api_url_template = "https://api.biorxiv.org/details/biorxiv/{start}/{end}/{cursor}"
            base_url = "https://www.biorxiv.org/content/"
        else:  # medRxiv
            api_url_template = "https://api.medrxiv.org/details/medrxiv/{start}/{end}/{cursor}"
            base_url = "https://www.medrxiv.org/content/"

        print(f"\n[{server.upper()}] {start_date} ~ {end_date} 범위 수집 시작...")

        max_iterations = 100
        iteration = 0

        while iteration < max_iterations:
            url = api_url_template.format(start=start_date, end=end_date, cursor=cursor)
            print(f"[{server.upper()}] 조회 중 (cursor: {cursor})...")

            data = self._fetch_json(url)
            if not data:
                break

            # API 응답 구조 확인
            if 'collection' not in data or not data['collection']:
                print(f"[{server.upper()}] 더 이상의 결과 없음")
                break

            for item in data['collection']:
                # 필드 추출
                doi = item.get('doi', '').strip()
                title = item.get('title', '').strip()
                abstract = item.get('abstract', '').strip()
                authors = item.get('authors', [])
                pub_date = item.get('date', '').strip()
                category = item.get('category', '').strip()

                # 필수 필드 확인
                if not doi or not title:
                    continue

                # 중복 확인
                if doi in self.existing_dois:
                    print(f"  [스킵] 이미 수집됨: {doi}")
                    continue

                # 키워드 필터링
                if not self._keyword_in_text(title) and not self._keyword_in_text(abstract):
                    continue

                # URL 생성
                if 'version' in item:
                    version = item['version']
                    paper_url = f"{base_url}{doi}v{version}"
                else:
                    version = 1
                    paper_url = f"{base_url}{doi}v{version}"

                paper_info = {
                    'doi': doi,
                    'title': title,
                    'authors': authors,
                    'abstract': abstract,
                    'pub_date': pub_date,
                    'category': category,
                    'url': paper_url,
                    'source': server,
                    'collected_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'pdf_path': None
                }

                # PDF 다운로드 시도
                pdf_path = self._download_pdf(doi, version, server)
                if pdf_path:
                    paper_info['pdf_path'] = pdf_path

                papers.append(paper_info)
                self.papers_found += 1
                self.existing_dois.add(doi)

                print(f"  [수집] {doi} - {title[:60]}...")

                # Rate limiting: 1 request per second
                time.sleep(1)

            # 다음 cursor 확인
            if 'messages' in data and len(data['messages']) > 0:
                messages = data['messages']
                if isinstance(messages, list) and len(messages) > 0:
                    msg = messages[0]
                    if 'cursor' in msg:
                        cursor = msg['cursor']
                    else:
                        break
                else:
                    break
            else:
                break

            iteration += 1

        print(f"[{server.upper()}] 수집 완료: {len(papers)}개 논문")
        return papers

    def _save_papers(self, papers):
        """논문 정보를 로그에 저장"""
        if not papers:
            return

        # 기존 로그 로드
        existing_papers = []
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    log_data = json.load(f)
                    if isinstance(log_data, list):
                        existing_papers = log_data
                    elif isinstance(log_data, dict) and 'papers' in log_data:
                        existing_papers = log_data['papers']
            except Exception as e:
                print(f"[경고] 기존 로그 로드 실패: {e}")

        # 새 논문 추가
        existing_papers.extend(papers)

        # 로그 저장
        try:
            with open(self.log_file, 'w', encoding='utf-8') as f:
                json.dump(existing_papers, f, ensure_ascii=False, indent=2)
            print(f"[저장] 로그 파일 업데이트: {self.log_file}")
        except Exception as e:
            print(f"[오류] 로그 저장 실패: {e}")

    def _update_status(self, status, last_run):
        """파이프라인 상태 업데이트"""
        try:
            status_data = {
                "agent": "biorxiv_searcher",
                "status": status,
                "last_run": last_run,
                "papers_found": self.papers_found
            }

            with open(self.status_file, 'w', encoding='utf-8') as f:
                json.dump(status_data, f, ensure_ascii=False, indent=2)

            print(f"[상태] 파이프라인 상태 업데이트: {status}")
        except Exception as e:
            print(f"[오류] 상태 저장 실패: {e}")

    def run(self, days=30):
        """메인 실행 함수"""
        print("\n" + "="*60)
        print("bioRxiv/medRxiv AGA 관련 프리프린트 수집")
        print("="*60)

        start_time = datetime.now()

        # 날짜 범위 설정
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')

        print(f"[설정] 범위: {start_date_str} ~ {end_date_str}")
        print(f"[설정] 키워드: {', '.join(self.keywords)}")

        all_papers = []

        # bioRxiv 수집
        papers = self._collect_from_server('biorxiv', start_date_str, end_date_str)
        all_papers.extend(papers)

        # medRxiv 수집
        papers = self._collect_from_server('medrxiv', start_date_str, end_date_str)
        all_papers.extend(papers)

        # 논문 저장
        if all_papers:
            self._save_papers(all_papers)

        # 상태 업데이트
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        self._update_status(
            "completed" if self.papers_found > 0 else "no_results",
            end_time.strftime('%Y-%m-%d %H:%M:%S')
        )

        # 최종 보고
        print("\n" + "="*60)
        print(f"[완료] 총 {self.papers_found}개 논문 수집")
        print(f"[시간] {duration:.1f}초 소요")
        print(f"[로그] {self.log_file}")
        print("="*60 + "\n")

        return self.papers_found


def main():
    """메인 함수"""
    try:
        # BASE_FOLDER 설정
        script_dir = os.path.dirname(os.path.abspath(__file__))
        base_folder = os.path.dirname(script_dir)

        # 수집기 실행
        collector = BioRxivCollector(base_folder)
        papers_found = collector.run(days=30)

        return 0 if papers_found >= 0 else 1

    except KeyboardInterrupt:
        print("\n[중단] 사용자 중단")
        return 130
    except Exception as e:
        print(f"\n[오류] {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
