"""
=============================================================
00_환경테스트.py
=============================================================
용도: Python과 필수 라이브러리가 제대로 설치되었는지 확인하는 스크립트
실행: 명령 프롬프트(cmd)에서 python 00_환경테스트.py
=============================================================
"""

import sys

print("=" * 60)
print("  AGA Foundation Model - 환경 테스트")
print("=" * 60)
print()

# 1. Python 버전 확인
print(f"[1] Python 버전: {sys.version}")
if sys.version_info >= (3, 9):
    print("    → OK! Python 3.9 이상입니다.")
else:
    print("    → 경고: Python 3.9 이상을 권장합니다.")
print()

# 2. 필수 라이브러리 확인
libraries = {
    "pandas": "데이터를 엑셀처럼 다루는 도구",
    "openpyxl": "엑셀 파일을 만드는 도구",
    "pdfplumber": "PDF에서 텍스트를 뽑는 도구",
}

print("[2] 필수 라이브러리 확인:")
missing = []
for lib, desc in libraries.items():
    try:
        __import__(lib)
        print(f"    {lib}: OK  ({desc})")
    except ImportError:
        print(f"    {lib}: 미설치!  ({desc})")
        missing.append(lib)
print()

# 3. 선택 라이브러리 확인 (나중에 필요)
optional = {
    "anthropic": "Claude AI API (3-4주차에 사용)",
    "openai": "OpenAI API (7-8주차에 RAG용)",
    "networkx": "네트워크 그래프 (5-6주차에 사용)",
}

print("[3] 선택 라이브러리 확인 (지금 없어도 괜찮음):")
for lib, desc in optional.items():
    try:
        __import__(lib)
        print(f"    {lib}: OK  ({desc})")
    except ImportError:
        print(f"    {lib}: 미설치  ({desc}) ← 나중에 설치하면 됩니다")
print()

# 4. PDF 폴더 확인
import os
pdf_folder = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pdf_count = len([f for f in os.listdir(pdf_folder) if f.endswith('.pdf')])
print(f"[4] PDF 파일 확인:")
print(f"    폴더: {pdf_folder}")
print(f"    PDF 파일 수: {pdf_count}개")
print()

# 5. 결과 요약
print("=" * 60)
if missing:
    print("  아직 설치 안 된 라이브러리가 있습니다!")
    print(f"  아래 명령어를 cmd에 입력하세요:")
    print(f"  pip install {' '.join(missing)}")
else:
    print("  모든 필수 라이브러리가 설치되어 있습니다!")
    print("  다음 단계: 01_pdf_추출.py 를 실행하세요.")
print("=" * 60)
