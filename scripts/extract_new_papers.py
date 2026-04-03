"""
=============================================================
extract_new_papers.py
=============================================================
용도: new_papers/ 폴더의 PDF에서 텍스트를 추출하여
      new_papers_txt/ 폴더에 저장합니다.
      (이미 .txt가 있는 PMID는 건너뜁니다)

실행: python scripts/extract_new_papers.py
소요: 약 3-6시간 (10,000건 기준)
=============================================================
"""

import os
import sys
import time
import json
from concurrent.futures import ProcessPoolExecutor, as_completed

# ─── 설정 ────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(BASE_DIR, "new_papers")
TXT_DIR = os.path.join(BASE_DIR, "new_papers_txt")
LOG_DIR = os.path.join(BASE_DIR, "logs")
WORKERS = 4  # 병렬 처리 수

os.makedirs(TXT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)


def extract_one(pdf_path, txt_path):
    """하나의 PDF에서 텍스트 추출"""
    try:
        import pdfplumber
        texts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    texts.append(t)
        full_text = "\n\n".join(texts)
        if len(full_text.strip()) < 50:
            return "empty"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(full_text)
        return "ok"
    except Exception as e:
        return f"error: {str(e)[:80]}"


def main():
    # pdfplumber 확인
    try:
        import pdfplumber
    except ImportError:
        print("pdfplumber 설치 필요: pip install pdfplumber")
        sys.exit(1)

    # PDF 목록 수집 (루트 + 날짜별 하위 폴더 모두 탐색)
    pdf_files = []
    for root, dirs, files in os.walk(PDF_DIR):
        for f in files:
            if f.lower().endswith('.pdf'):
                pdf_files.append(os.path.join(root, f))
    total = len(pdf_files)

    # 이미 추출된 파일 확인 (PMID 기반, 루트 + 하위 폴더)
    existing_txt = set()
    for root, dirs, files in os.walk(TXT_DIR):
        for f in files:
            if f.endswith('.txt'):
                pmid = f.split('_')[0] if '_' in f else f.replace('.txt', '')
                existing_txt.add(pmid)

    # 처리할 PDF 필터링
    todo = []
    for pdf_path in pdf_files:
        f = os.path.basename(pdf_path)
        pmid = f.split('_')[0] if '_' in f else f.replace('.pdf', '')
        if pmid not in existing_txt:
            txt_name = os.path.splitext(f)[0] + ".txt"
            txt_path = os.path.join(TXT_DIR, txt_name)
            todo.append((pdf_path, txt_path, f))

    print("=" * 60)
    print(f"  PDF 텍스트 추출 (new_papers → new_papers_txt)")
    print(f"  전체 PDF: {total}건")
    print(f"  이미 추출됨: {total - len(todo)}건")
    print(f"  추출 대상: {len(todo)}건")
    print(f"  병렬 처리: {WORKERS} workers")
    print("=" * 60)
    print()

    if len(todo) == 0:
        print("  모든 PDF가 이미 추출되었습니다!")
        return

    start_time = time.time()
    success = 0
    empty = 0
    failed = []
    processed = 0

    # 로그 파일
    ts = time.strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(LOG_DIR, f"pdf_extract_{ts}.log")

    with open(log_path, "w", encoding="utf-8") as log_f:
        log_f.write(f"PDF Extract Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_f.write(f"Total: {len(todo)} PDFs\n\n")

        # 병렬 처리
        with ProcessPoolExecutor(max_workers=WORKERS) as executor:
            futures = {}
            for pdf_path, txt_path, fname in todo:
                future = executor.submit(extract_one, pdf_path, txt_path)
                futures[future] = fname

            for future in as_completed(futures):
                fname = futures[future]
                processed += 1
                try:
                    result = future.result(timeout=120)  # 2분 타임아웃
                except Exception as e:
                    result = f"timeout: {str(e)[:50]}"

                if result == "ok":
                    success += 1
                elif result == "empty":
                    empty += 1
                else:
                    failed.append((fname, result))

                # 진행률 출력 (100건마다)
                if processed % 100 == 0 or processed == len(todo):
                    elapsed = time.time() - start_time
                    rate = processed / elapsed if elapsed > 0 else 0
                    remaining = (len(todo) - processed) / rate if rate > 0 else 0
                    mins = int(remaining // 60)
                    pct = processed / len(todo) * 100

                    status = f"[{processed}/{len(todo)}] {pct:.1f}% | OK:{success} Empty:{empty} Fail:{len(failed)} | ~{mins}min left"
                    print(f"  {status}")
                    log_f.write(f"{time.strftime('%H:%M:%S')} {status}\n")
                    log_f.flush()

    # 결과 요약
    elapsed = time.time() - start_time
    print()
    print("=" * 60)
    print(f"  추출 완료!")
    print(f"  성공: {success}건")
    print(f"  비어있음: {empty}건 (이미지 PDF)")
    print(f"  실패: {len(failed)}건")
    print(f"  소요 시간: {int(elapsed//3600)}시간 {int((elapsed%3600)//60)}분")
    print(f"  결과 폴더: {TXT_DIR}")
    print("=" * 60)

    # 실패 목록 저장
    if failed:
        fail_path = os.path.join(LOG_DIR, f"pdf_extract_failures_{ts}.json")
        with open(fail_path, "w", encoding="utf-8") as f:
            json.dump(failed, f, ensure_ascii=False, indent=2)
        print(f"  실패 목록: {fail_path}")

    print()
    print("  다음 단계: python scripts/02_info_extract.py --append")


if __name__ == "__main__":
    main()
