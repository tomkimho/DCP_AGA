#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
=============================================================
08_자동처리_오케스트레이터.py
=============================================================
용도: 전체 AGA 연구 파이프라인을 자동으로 실행합니다.
      논문 수집 → 텍스트 추출 → AI 분석 → 구조 수집

실행: python 08_자동처리_오케스트레이터.py
소요: 약 30분-2시간 (수집량에 따라)
=============================================================
"""

import os
import sys
import json
import subprocess
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# ============================================================
# 기본 설정
# ============================================================

BASE_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_FOLDER = os.path.join(BASE_FOLDER, 'scripts')
DATA_FOLDER = os.path.join(BASE_FOLDER, 'data')
NEW_PAPERS_FOLDER = os.path.join(DATA_FOLDER, 'new_papers')
LOGS_FOLDER = os.path.join(BASE_FOLDER, 'logs')
STATUS_FILE = os.path.join(BASE_FOLDER, 'pipeline_status.json')

# 로그 폴더 생성
os.makedirs(LOGS_FOLDER, exist_ok=True)
os.makedirs(NEW_PAPERS_FOLDER, exist_ok=True)

# 로그 파일 설정
LOG_DATE = datetime.now().strftime('%Y-%m-%d_%H%M%S')
LOG_FILE = os.path.join(LOGS_FOLDER, f'pipeline_log_{LOG_DATE}.txt')

# 로거 설정
logger = logging.getLogger('AGA_Pipeline')
logger.setLevel(logging.DEBUG)

# 파일 핸들러 (UTF-8 인코딩)
fh = logging.FileHandler(LOG_FILE, encoding='utf-8')
fh.setLevel(logging.DEBUG)

# 콘솔 핸들러
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

# 포매터
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')
fh.setFormatter(formatter)
ch.setFormatter(formatter)

logger.addHandler(fh)
logger.addHandler(ch)

# ============================================================
# 파이프라인 상태 관리
# ============================================================

class PipelineStatus:
    """파이프라인 상태를 관리하는 클래스"""

    def __init__(self, status_file: str):
        self.status_file = status_file
        self.load()

    def load(self):
        """상태 파일에서 현재 상태를 로드"""
        if os.path.exists(self.status_file):
            try:
                with open(self.status_file, 'r', encoding='utf-8') as f:
                    self.status = json.load(f)
            except Exception as e:
                logger.warning(f"상태 파일 로드 실패: {e}")
                self.status = self._init_status()
        else:
            self.status = self._init_status()

    def _init_status(self) -> Dict:
        """초기 상태 생성"""
        return {
            "overall_status": "idle",
            "current_step": "",
            "last_run": "",
            "start_time": "",
            "end_time": "",
            "steps_completed": 0,
            "total_steps": 7,
            "total_papers_new": 0,
            "total_papers_processed": 0,
            "errors": [],
            "step_details": {}
        }

    def update(self, **kwargs):
        """상태 업데이트"""
        self.status.update(kwargs)
        self.save()

    def update_step(self, step_name: str, status: str, details: Dict = None):
        """단계별 상태 업데이트"""
        if "step_details" not in self.status:
            self.status["step_details"] = {}

        self.status["step_details"][step_name] = {
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "details": details or {}
        }
        self.save()

    def add_error(self, error: str):
        """에러 추가"""
        self.status["errors"].append({
            "timestamp": datetime.now().isoformat(),
            "error": error
        })
        self.save()

    def save(self):
        """상태 파일에 저장"""
        try:
            with open(self.status_file, 'w', encoding='utf-8') as f:
                json.dump(self.status, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"상태 파일 저장 실패: {e}")

# ============================================================
# 파이프라인 단계 실행
# ============================================================

class PipelineOrchestrator:
    """파이프라인 오케스트레이터"""

    def __init__(self):
        self.status = PipelineStatus(STATUS_FILE)
        self.start_time = None
        self.end_time = None
        self.steps_results = []

    def run(self):
        """전체 파이프라인 실행"""
        logger.info("=" * 60)
        logger.info("AGA Drug Discovery 자동처리 파이프라인 시작")
        logger.info("=" * 60)

        self.start_time = datetime.now()
        self.status.update(
            overall_status="running",
            last_run=self.start_time.isoformat(),
            start_time=self.start_time.isoformat(),
            errors=[],
            steps_completed=0
        )

        # 파이프라인 단계 정의
        steps = [
            ("PubMed 논문 수집", "05_pubmed_자동수집.py"),
            ("특허 자동 수집", "06_특허_자동수집.py"),
            ("BioRxiv 사전인쇄 수집", "07_biorxiv_수집.py"),
            ("PDF 텍스트 추출", "01_pdf_추출.py"),
            ("정보 AI 분석", "02_정보추출.py"),
            ("화합물 구조 수집", "03_화합물구조.py"),
            ("파이프라인 최종 정리", None),
        ]

        try:
            for idx, (step_name, script_name) in enumerate(steps, 1):
                logger.info(f"\n[단계 {idx}/{len(steps)}] {step_name} 실행 중...")
                self.status.update(current_step=step_name)

                if script_name is None:
                    # 최종 정리 단계
                    self._finalize_pipeline()
                    self.status.update_step(step_name, "completed")
                else:
                    # 스크립트 실행
                    success = self._run_step(step_name, script_name, idx)

                    if success:
                        self.status.update(steps_completed=idx)
                        self.status.update_step(step_name, "completed")
                    else:
                        self.status.update_step(step_name, "failed")
                        logger.warning(f"⚠️ {step_name} 단계 실패 (계속 진행...)")

            # 전체 완료
            self.end_time = datetime.now()
            duration = (self.end_time - self.start_time).total_seconds()

            logger.info("\n" + "=" * 60)
            logger.info(f"파이프라인 완료")
            logger.info(f"소요 시간: {duration:.1f}초 ({duration/60:.1f}분)")
            logger.info("=" * 60)

            self.status.update(
                overall_status="completed",
                end_time=self.end_time.isoformat(),
                steps_completed=len(steps)
            )

            return True

        except Exception as e:
            logger.error(f"파이프라인 실행 중 예외 발생: {e}", exc_info=True)
            self.status.update(overall_status="error")
            self.status.add_error(str(e))
            return False

    def _run_step(self, step_name: str, script_name: str, step_num: int) -> bool:
        """개별 단계 실행"""
        script_path = os.path.join(SCRIPTS_FOLDER, script_name)

        if not os.path.exists(script_path):
            error_msg = f"스크립트를 찾을 수 없음: {script_path}"
            logger.error(error_msg)
            self.status.add_error(error_msg)
            return False

        try:
            step_start = datetime.now()

            # 스크립트 실행
            result = subprocess.run(
                [sys.executable, script_path],
                cwd=SCRIPTS_FOLDER,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=3600  # 1시간 타임아웃
            )

            step_end = datetime.now()
            step_duration = (step_end - step_start).total_seconds()

            # 출력 로깅
            if result.stdout:
                logger.debug(f"[{script_name}] 표준출력:\n{result.stdout}")

            if result.stderr:
                logger.debug(f"[{script_name}] 표준오류:\n{result.stderr}")

            # 결과 확인
            if result.returncode == 0:
                logger.info(f"✓ {step_name} 성공 ({step_duration:.1f}초)")
                self.status.update_step(
                    step_name,
                    "completed",
                    {"duration": step_duration, "script": script_name}
                )
                return True
            else:
                error_msg = f"{step_name} 실패 (종료코드: {result.returncode})"
                logger.warning(f"✗ {error_msg}")
                self.status.add_error(error_msg)
                self.status.update_step(
                    step_name,
                    "failed",
                    {"duration": step_duration, "exit_code": result.returncode, "script": script_name}
                )
                return False

        except subprocess.TimeoutExpired:
            error_msg = f"{step_name} 타임아웃 (1시간 초과)"
            logger.error(error_msg)
            self.status.add_error(error_msg)
            return False

        except Exception as e:
            error_msg = f"{step_name} 실행 중 예외: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.status.add_error(error_msg)
            return False

    def _finalize_pipeline(self):
        """파이프라인 최종 정리"""
        logger.info("파이프라인 최종 정리 중...")

        try:
            # 처리된 파일 통계 수집
            new_papers_count = 0
            if os.path.exists(NEW_PAPERS_FOLDER):
                new_papers_count = len([f for f in os.listdir(NEW_PAPERS_FOLDER)
                                       if f.endswith('.pdf')])

            self.status.update(
                total_papers_new=new_papers_count,
                total_papers_processed=new_papers_count
            )

            logger.info(f"✓ 최종 정리 완료 (수집된 새 논문: {new_papers_count})")

        except Exception as e:
            logger.warning(f"최종 정리 중 오류: {e}")

# ============================================================
# 메인 실행
# ============================================================

def main():
    """메인 함수"""
    try:
        orchestrator = PipelineOrchestrator()
        success = orchestrator.run()
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"예상치 못한 오류: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
