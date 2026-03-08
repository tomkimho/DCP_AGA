"""
02_리셋.py - 진행상황을 초기화합니다
실행: python 02_리셋.py
그 다음: python 02_정보추출.py
"""
import os
import json

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRESS = os.path.join(BASE, "scripts", "_진행상황.json")

if os.path.exists(PROGRESS):
    os.remove(PROGRESS)
    print("  진행상황 파일을 삭제했습니다.")
    print("  이제 python 02_정보추출.py 를 실행하세요.")
else:
    print("  진행상황 파일이 없습니다. 바로 02_정보추출.py 를 실행하세요.")
