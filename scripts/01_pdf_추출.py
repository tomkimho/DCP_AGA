"""
=============================================================
01_pdf_추출.py
=============================================================
용도: 716건 PDF에서 텍스트를 자동으로 추출합니다.
실행: 명령 프롬프트(cmd)에서 python 01_pdf_추출.py

실행하면:
  - 'txt_추출결과' 폴더가 자동 생성됩니다
  - 각 PDF의 텍스트가 .txt 파일로 저장됩니다
  - 진행 상황이 화면에 표시됩니다
  - 실패한 파일 목록도 알려줍니다

소요 시간: 약 1-3시간 (716건 기준)
=============================================================
"""

import os
import sys
import time

# ─── 설정 ────────────────────────────────────────────────
# PDF가 들어있는 폴더 경로
# ★ 아래 경로를 본인 폴더로 바꾸세요 ★
# 예: PDF_FOLDER = r"C:\Users\KIM\Documents\문헌데이터_탈모"
# 예: PDF_FOLDER = r"D:\연구자료\AGA_논문"
PDF_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 결과를 저장할 폴더 (자동 생성됨)
OUTPUT_FOLDER = os.path.join(PDF_FOLDER, "txt_추출결과")
# ─────────────────────────────────────────────────────────

def main():
    # pdfplumber 설치 확인
    try:
        import pdfplumber
    except ImportError:
        print("pdfplumber가 설치되지 않았습니다!")
        print("아래 명령어를 cmd에 입력하세요:")
        print("  pip install pdfplumber")
        sys.exit(1)

    # 출력 폴더 생성
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # PDF 파일 목록
    pdf_files = sorted([f for f in os.listdir(PDF_FOLDER) if f.lower().endswith('.pdf')])
    total = len(pdf_files)

    print("=" * 60)
    print(f"  PDF 텍스트 추출 시작")
    print(f"  PDF 폴더: {PDF_FOLDER}")
    print(f"  총 {total}건의 PDF를 처리합니다")
    print("=" * 60)
    print()

    success = 0
    failed = []
    start_time = time.time()

    for i, filename in enumerate(pdf_files, 1):
        pdf_path = os.path.join(PDF_FOLDER, filename)
        txt_filename = os.path.splitext(filename)[0] + ".txt"
        txt_path = os.path.join(OUTPUT_FOLDER, txt_filename)

        # 이미 처리된 파일은 건너뜀
        if os.path.exists(txt_path):
            print(f"  [{i}/{total}] 이미 처리됨: {filename[:50]}...")
            success += 1
            continue

        try:
            text_parts = []
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)

            full_text = "\n\n".join(text_parts)

            if len(full_text.strip()) < 100:
                print(f"  [{i}/{total}] 경고(텍스트 부족): {filename[:50]}...")
                failed.append((filename, "텍스트가 거의 없음 (이미지 PDF일 수 있음)"))
                continue

            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(full_text)

            success += 1
            # 진행률 표시
            elapsed = time.time() - start_time
            avg_time = elapsed / i
            remaining = avg_time * (total - i)
            mins = int(remaining // 60)
            print(f"  [{i}/{total}] 완료: {filename[:50]}... (남은시간: 약 {mins}분)")

        except Exception as e:
            failed.append((filename, str(e)[:100]))
            print(f"  [{i}/{total}] 실패: {filename[:50]}... ({str(e)[:50]})")

    # 결과 요약
    elapsed = time.time() - start_time
    print()
    print("=" * 60)
    print(f"  처리 완료!")
    print(f"  성공: {success}건 / 실패: {len(failed)}건 / 전체: {total}건")
    print(f"  소요 시간: {int(elapsed//60)}분 {int(elapsed%60)}초")
    print(f"  결과 폴더: {OUTPUT_FOLDER}")
    print("=" * 60)

    # 실패 목록 저장
    if failed:
        fail_path = os.path.join(OUTPUT_FOLDER, "_실패목록.txt")
        with open(fail_path, "w", encoding="utf-8") as f:
            f.write("PDF 텍스트 추출 실패 목록\n")
            f.write("=" * 60 + "\n\n")
            for fname, reason in failed:
                f.write(f"파일: {fname}\n이유: {reason}\n\n")
        print(f"\n  실패 목록이 저장되었습니다: {fail_path}")

    print()
    print("  다음 단계: 02_정보추출.py 를 실행하세요.")
    print("  (Claude API 키가 필요합니다)")


if __name__ == "__main__":
    main()
