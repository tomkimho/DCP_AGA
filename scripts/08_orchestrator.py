#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
=============================================================
08_자동처리_오케스트레이터.py
=============================================================
용도: 전체 AGA 연구 파이프라인을 자동으로 실행합니다.
      논문 수집 → 텍스트 추출 → AI 분석 → 구조 수집
      → 패턴 분석 → 신약 후보 도출 → 바이오마커 분석

실행: python 08_orchestrator.py
      python 08_orchestrator.py --append    (증분 모드)
      python 08_orchestrator.py --weekly    (주간 분석 포함)
소요: 약 30분-2시간 (수집량에 따라)
=============================================================
"""

import os
import sys
import json
import subprocess
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict

# ============================================================
# CLI 인자 파싱
# ============================================================
parser = argparse.ArgumentParser(description="AGA 파이프라인 오케스트레이터")
parser.add_argument("--append", action="store_true", help="APPEND 모드 (증분 처리)")
parser.add_argument("--weekly", action="store_true", help="주간 분석 포함 (패턴분석 + 신약후보)")
parser.add_argument("--skip-collect", action="store_true", help="수집 단계 스킵")
args, _ = parser.parse_known_args()

# ============================================================
# 기본 설정
# ============================================================

BASE_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_FOLDER = os.path.join(BASE_FOLDER, 'scripts')
NEW_PAPERS_FOLDER = os.path.join(BASE_FOLDER, 'new_papers')
OUTPUT_FOLDER = os.path.join(BASE_FOLDER, 'output')
LOGS_FOLDER = os.path.join(BASE_FOLDER, 'logs')
STATUS_FILE = os.path.join(BASE_FOLDER, 'pipeline_status.json')

# 폴더 생성
os.makedirs(LOGS_FOLDER, exist_ok=True)
os.makedirs(NEW_PAPERS_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# 로그 파일 설정
LOG_DATE = datetime.now().strftime('%Y-%m-%d_%H%M%S')
LOG_FILE = os.path.join(LOGS_FOLDER, f'pipeline_log_{LOG_DATE}.txt')

# 로거 설정
logger = logging.getLogger('AGA_Pipeline')
logger.setLevel(logging.DEBUG)

fh = logging.FileHandler(LOG_FILE, encoding='utf-8')
fh.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

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
        if os.path.exists(self.status_file):
            try:
                with open(self.status_file, 'r', encoding='utf-8') as f:
                    self.status = json.load(f)
            except Exception:
                self.status = self._init_status()
        else:
            self.status = self._init_status()

    def _init_status(self) -> Dict:
        return {
            "overall_status": "idle",
            "current_step": "",
            "last_run": "",
            "start_time": "",
            "end_time": "",
            "steps_completed": 0,
            "total_steps": 0,
            "total_papers_new": 0,
            "total_papers_processed": 0,
            "estimated_cost_usd": 0,
            "errors": [],
            "step_details": {}
        }

    def update(self, **kwargs):
        self.status.update(kwargs)
        self.save()

    def update_step(self, step_name: str, status: str, details: Dict = None):
        if "step_details" not in self.status:
            self.status["step_details"] = {}
        self.status["step_details"][step_name] = {
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "details": details or {}
        }
        self.save()

    def add_error(self, error: str):
        self.status.setdefault("errors", []).append({
            "timestamp": datetime.now().isoformat(),
            "error": error
        })
        self.save()

    def save(self):
        try:
            with open(self.status_file, 'w', encoding='utf-8') as f:
                json.dump(self.status, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"상태 파일 저장 실패: {e}")


# ============================================================
# 파이프라인 오케스트레이터
# ============================================================

class PipelineOrchestrator:

    def __init__(self):
        self.status = PipelineStatus(STATUS_FILE)
        self.start_time = None

    def _count_new_papers(self) -> int:
        """new_papers/ 폴더의 PDF 파일 수"""
        if not os.path.isdir(NEW_PAPERS_FOLDER):
            return 0
        return len([f for f in os.listdir(NEW_PAPERS_FOLDER) if f.endswith('.pdf')])

    def _count_new_txt(self) -> int:
        """new_papers_txt/ 폴더의 TXT 파일 수"""
        txt_folder = os.path.join(BASE_FOLDER, "new_papers_txt")
        if not os.path.isdir(txt_folder):
            return 0
        return len([f for f in os.listdir(txt_folder) if f.endswith('.txt')])

    def run(self):
        """전체 파이프라인 실행"""
        logger.info("=" * 60)
        logger.info("AGA Drug Discovery 자동처리 파이프라인 시작")
        logger.info(f"  APPEND 모드: {args.append}")
        logger.info(f"  주간 분석: {args.weekly}")
        logger.info(f"  수집 스킵: {args.skip_collect}")
        logger.info("=" * 60)

        self.start_time = datetime.now()

        # 파이프라인 단계 정의
        steps = []

        # Phase A: 수집 단계 (--skip-collect로 스킵 가능)
        if not args.skip_collect:
            steps.extend([
                ("PubMed 논문 수집", "05_pubmed_collect.py", [], {}),
                ("특허 자동 수집", "06_patent_collect.py", [], {}),
                ("BioRxiv 사전인쇄 수집", "07_biorxiv_collect.py", [], {}),
            ])

        # Phase B: 처리 단계
        extract_args = ["--append"] if args.append else []
        extract_env = {"APPEND_MODE": "true"} if args.append else {}

        steps.extend([
            ("PDF 텍스트 추출", "01_pdf_extract.py", [], {}),
            ("정보 AI 분석", "02_info_extract.py", extract_args, extract_env),
            ("화합물 구조 수집", "03_compound_structure.py", [], {}),
        ])

        # Phase C: 주간 고급 분석 (--weekly 또는 월요일)
        is_monday = datetime.now().weekday() == 0
        if args.weekly or is_monday:
            steps.extend([
                ("지능형 패턴 분석", "10_pattern_analysis.py", [], {}),
                ("AI 신약 후보 도출", "11_drug_candidates.py", [], {}),
            ])

        # Phase D: 바이오마커 분석 (항상 실행)
        steps.append(("바이오마커 분석", "12_biomarker_analysis.py", [], {}))

        # Phase E: 최종 정리
        steps.append(("파이프라인 최종 정리", None, [], {}))

        total_steps = len(steps)
        self.status.update(
            overall_status="running",
            last_run=self.start_time.isoformat(),
            start_time=self.start_time.isoformat(),
            errors=[],
            steps_completed=0,
            total_steps=total_steps
        )

        try:
            for idx, (step_name, script_name, extra_args, extra_env) in enumerate(steps, 1):
                logger.info(f"\n[{idx}/{total_steps}] {step_name}...")
                self.status.update(current_step=step_name)

                if script_name is None:
                    self._finalize_pipeline()
                    self.status.update_step(step_name, "completed")
                else:
                    script_path = os.path.join(SCRIPTS_FOLDER, script_name)
                    if not os.path.exists(script_path):
                        logger.warning(f"  스크립트 없음: {script_name} → 스킵")
                        self.status.update_step(step_name, "skipped")
                        continue

                    success = self._run_step(step_name, script_name, extra_args, extra_env)
                    if success:
                        self.status.update(steps_completed=idx)
                        self.status.update_step(step_name, "completed")
                    else:
                        self.status.update_step(step_name, "failed")
                        logger.warning(f"  {step_name} 실패 (계속 진행)")

            # 완료
            end_time = datetime.now()
            duration = (end_time - self.start_time).total_seconds()

            logger.info("\n" + "=" * 60)
            logger.info(f"파이프라인 완료 ({duration:.0f}초 = {duration/60:.1f}분)")
            logger.info("=" * 60)

            self.status.update(
                overall_status="completed",
                end_time=end_time.isoformat(),
                steps_completed=total_steps
            )
            return True

        except Exception as e:
            logger.error(f"파이프라인 예외: {e}", exc_info=True)
            self.status.update(overall_status="error")
            self.status.add_error(str(e))
            return False

    def _run_step(self, step_name: str, script_name: str,
                  extra_args: list = None, extra_env: dict = None) -> bool:
        """개별 단계 실행"""
        script_path = os.path.join(SCRIPTS_FOLDER, script_name)

        try:
            step_start = datetime.now()
            cmd = [sys.executable, script_path] + (extra_args or [])
            env = os.environ.copy()
            if extra_env:
                env.update(extra_env)

            result = subprocess.run(
                cmd,
                cwd=SCRIPTS_FOLDER,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                env=env,
                timeout=3600  # 1시간 타임아웃
            )

            step_duration = (datetime.now() - step_start).total_seconds()

            if result.stdout:
                logger.debug(f"[{script_name}] stdout:\n{result.stdout[-2000:]}")
            if result.stderr:
                logger.debug(f"[{script_name}] stderr:\n{result.stderr[-2000:]}")

            if result.returncode == 0:
                logger.info(f"  ✓ {step_name} 성공 ({step_duration:.0f}초)")
                self.status.update_step(step_name, "completed",
                    {"duration": step_duration, "script": script_name})
                return True
            else:
                logger.warning(f"  ✗ {step_name} 실패 (code={result.returncode})")
                self.status.add_error(f"{step_name} 실패 (code={result.returncode})")
                self.status.update_step(step_name, "failed",
                    {"duration": step_duration, "exit_code": result.returncode})
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"  {step_name} 타임아웃")
            self.status.add_error(f"{step_name} 타임아웃")
            return False
        except Exception as e:
            logger.error(f"  {step_name} 예외: {e}", exc_info=True)
            self.status.add_error(str(e))
            return False

    def _finalize_pipeline(self):
        """파이프라인 최종 정리 + 비용 추정"""
        logger.info("최종 정리...")

        new_papers = self._count_new_papers()
        new_txt = self._count_new_txt()
        est_cost = new_txt * 0.05  # ~$0.05/paper (Haiku)

        self.status.update(
            total_papers_new=new_papers,
            total_papers_processed=new_txt,
            estimated_cost_usd=round(est_cost, 2)
        )

        logger.info(f"  PDF: {new_papers}개, TXT: {new_txt}개, 예상비용: ${est_cost:.2f}")


# ============================================================
# 메인 실행
# ============================================================

def main():
    try:
        orchestrator = PipelineOrchestrator()
        success = orchestrator.run()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"예상치 못한 오류: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
