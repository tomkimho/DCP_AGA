"""
=============================================================
06_특허_자동수집.py
=============================================================
용도: USPTO/EPO에서 AGA 관련 새 특허를 자동 검색합니다.

실행: python 06_특허_자동수집.py
소요: 약 2-3분
비용: 무료 (USPTO PatentsView API)
=============================================================
"""

import os
import sys
import json
import urllib.request
import urllib.error
import urllib.parse
import time
from datetime import datetime, timedelta
from pathlib import Path

# 인코딩 설정 (Windows 호환)
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


class PatentCollector:
    """USPTO PatentsView API를 사용하여 특허 메타데이터 수집"""

    def __init__(self, base_folder):
        self.base_folder = base_folder
        self.new_papers_folder = os.path.join(base_folder, 'new_papers')
        self.status_file = os.path.join(base_folder, 'pipeline_status.json')
        self.collection_log = os.path.join(base_folder, 'collection_log.json')
        self.api_url = "https://api.patentsview.org/patents/query"

        # 폴더 생성
        os.makedirs(self.new_papers_folder, exist_ok=True)

    def load_existing_patents(self):
        """기존 수집된 특허 번호 로드"""
        existing = set()
        if os.path.exists(self.collection_log):
            try:
                with open(self.collection_log, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            if 'patent_number' in item:
                                existing.add(item['patent_number'])
            except Exception as e:
                print(f"경고: collection_log 로드 실패 - {e}")

        return existing

    def search_patents(self):
        """USPTO PatentsView API에서 특허 검색"""
        print("\n[특허 수집] USPTO PatentsView API 검색 중...")

        # 최근 90일 기준 날짜 계산
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)

        # 검색 쿼리 구성
        query = {
            "q": {
                "_or": [
                    {"_text_any": {"patent_abstract": "androgenetic alopecia hair loss treatment baldness"}},
                    {"_text_any": {"patent_title": "androgenetic alopecia hair loss treatment"}}
                ]
            },
            "f": [
                "patent_number",
                "patent_title",
                "patent_abstract",
                "patent_date",
                "inventor_last_name",
                "patent_type"
            ],
            "o": {
                "per_page": 50,
                "page": 1
            },
            "s": [{"patent_date": "desc"}]
        }

        try:
            # API 요청
            query_json = json.dumps(query).encode('utf-8')
            headers = {'Content-Type': 'application/json'}
            req = urllib.request.Request(
                self.api_url,
                data=query_json,
                headers=headers,
                method='POST'
            )

            print(f"  검색 기간: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")
            print(f"  API 요청: {self.api_url}")

            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))

            patents = data.get('patents', [])
            print(f"  검색 결과: {len(patents)}개 특허")

            return patents

        except urllib.error.URLError as e:
            print(f"  에러: 네트워크 오류 - {e}")
            return []
        except Exception as e:
            print(f"  에러: API 요청 실패 - {e}")
            return []

    def process_patents(self, patents):
        """특허 메타데이터 처리 및 중복 제거"""
        print("\n[데이터 처리] 특허 메타데이터 정제 중...")

        existing_patents = self.load_existing_patents()
        new_count = 0
        dedup_count = 0

        new_patents_list = []

        for patent in patents:
            patent_number = patent.get('patent_number', 'UNKNOWN')

            # 중복 확인
            if patent_number in existing_patents:
                dedup_count += 1
                continue

            # 메타데이터 정제
            patent_record = {
                'patent_number': patent_number,
                'patent_title': patent.get('patent_title', ''),
                'patent_abstract': patent.get('patent_abstract', ''),
                'patent_date': patent.get('patent_date', ''),
                'inventor_name': patent.get('inventor_last_name', ''),
                'patent_type': patent.get('patent_type', ''),
                'source': 'USPTO PatentsView API',
                'collection_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'has_pdf': False
            }

            new_patents_list.append(patent_record)
            existing_patents.add(patent_number)
            new_count += 1

        print(f"  신규: {new_count}개 / 중복: {dedup_count}개")

        return new_patents_list

    def save_patents(self, new_patents):
        """특허 메타데이터 저장"""
        print("\n[저장] 특허 메타데이터 저장 중...")

        if not new_patents:
            print("  저장할 신규 특허 없음")
            return 0

        # 기존 컬렉션 로드
        existing_collection = []
        if os.path.exists(self.collection_log):
            try:
                with open(self.collection_log, 'r', encoding='utf-8') as f:
                    existing_collection = json.load(f)
                    if not isinstance(existing_collection, list):
                        existing_collection = []
            except:
                existing_collection = []

        # 신규 특허 병합 (새 것을 앞에 배치)
        updated_collection = new_patents + existing_collection

        # collection_log.json 저장
        try:
            with open(self.collection_log, 'w', encoding='utf-8') as f:
                json.dump(updated_collection, f, ensure_ascii=False, indent=2)
            print(f"  ✓ {self.collection_log} 저장 완료 ({len(updated_collection)}개)")
        except Exception as e:
            print(f"  에러: 저장 실패 - {e}")
            return 0

        # new_papers 폴더에도 JSON 저장 (메타데이터만)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        json_filename = f"patents_{timestamp}.json"
        json_path = os.path.join(self.new_papers_folder, json_filename)

        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(new_patents, f, ensure_ascii=False, indent=2)
            print(f"  ✓ {json_path} 저장 완료")
        except Exception as e:
            print(f"  경고: new_papers 저장 실패 - {e}")

        return len(new_patents)

    def update_pipeline_status(self, new_count):
        """파이프라인 상태 업데이트"""
        print("\n[상태 업데이트] pipeline_status.json 갱신 중...")

        status = {}
        if os.path.exists(self.status_file):
            try:
                with open(self.status_file, 'r', encoding='utf-8') as f:
                    status = json.load(f)
            except:
                status = {}

        # patent_searcher 상태 업데이트
        status['patent_searcher'] = {
            'last_run': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'new_patents': new_count,
            'status': 'completed' if new_count >= 0 else 'failed'
        }

        try:
            with open(self.status_file, 'w', encoding='utf-8') as f:
                json.dump(status, f, ensure_ascii=False, indent=2)
            print(f"  ✓ 상태 업데이트 완료")
        except Exception as e:
            print(f"  경고: 상태 업데이트 실패 - {e}")

    def run(self):
        """전체 수집 프로세스 실행"""
        print("=" * 60)
        print("특허 자동 수집 시작")
        print("=" * 60)

        start_time = time.time()

        # 1. 특허 검색
        patents = self.search_patents()

        if not patents:
            print("\n검색 결과 없음")
            self.update_pipeline_status(0)
            return

        # 2. 메타데이터 처리
        new_patents = self.process_patents(patents)

        # 3. 저장
        saved_count = self.save_patents(new_patents)

        # 4. 상태 업데이트
        self.update_pipeline_status(saved_count)

        elapsed = time.time() - start_time
        print("\n" + "=" * 60)
        print(f"특허 수집 완료 ({elapsed:.1f}초)")
        print("=" * 60)

        return saved_count


def main():
    """메인 함수"""
    # 기본 폴더 경로 설정
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_folder = os.path.dirname(script_dir)

    # 수집기 실행
    collector = PatentCollector(base_folder)
    saved_count = collector.run()

    print(f"\n최종 결과: {saved_count}개의 신규 특허 수집")

    return 0 if saved_count > 0 else 1


if __name__ == '__main__':
    sys.exit(main())
