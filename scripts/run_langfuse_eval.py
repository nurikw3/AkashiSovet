"""CLI для запуска Langfuse LLM-as-judge eval pipeline."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bot.config import config  # noqa: E402
from bot.logger import prepare_log_storage, setup_logging  # noqa: E402
from stdlib.services.eval_service import (  # noqa: E402
    build_run_summary,
    run_experiment_for_dataset,
    run_experiment_for_file,
)


def parse_args() -> argparse.Namespace:
    """Разбирает аргументы CLI."""
    parser = argparse.ArgumentParser(description="Run Langfuse LLM-as-judge evaluation")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--dataset-name",
        help="Имя уже существующего dataset в Langfuse",
    )
    source.add_argument(
        "--data-file",
        help="Локальный JSON/JSONL файл с eval-кейсами",
    )
    parser.add_argument(
        "--experiment-name",
        default="akashisovet-llm-eval",
        help="Логическое имя эксперимента",
    )
    parser.add_argument(
        "--run-name",
        default=f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        help="Имя конкретного запуска",
    )
    parser.add_argument(
        "--description",
        default="LLM-as-judge evaluation pipeline for AkashiSovet",
        help="Описание запуска",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=config.LANGFUSE_EVAL_MAX_CONCURRENCY,
        help="Максимальный параллелизм task/evaluator",
    )
    return parser.parse_args()


def main() -> int:
    """Запускает eval pipeline и печатает сводку."""
    args = parse_args()

    prepare_log_storage(
        log_dir=config.LOG_DIR,
        clean_on_start=config.LOG_CLEAN_ON_START,
        max_total_mb=config.LOG_MAX_TOTAL_MB,
    )
    setup_logging(
        level=config.LOG_LEVEL,
        file_level=config.LOG_FILE_LEVEL,
        error_level=config.LOG_ERROR_LEVEL,
        log_dir=config.LOG_DIR,
        rotation_mb=config.LOG_ROTATION_MB,
        retention_days=config.LOG_RETENTION_DAYS,
        errors_rotation_mb=config.LOG_ERRORS_ROTATION_MB,
        errors_retention_days=config.LOG_ERRORS_RETENTION_DAYS,
    )

    metadata = {
        "judge_model": config.LANGFUSE_EVAL_JUDGE_MODEL,
        "pass_threshold": str(config.LANGFUSE_EVAL_PASS_THRESHOLD),
    }

    if args.dataset_name:
        result = run_experiment_for_dataset(
            dataset_name=args.dataset_name,
            experiment_name=args.experiment_name,
            run_name=args.run_name,
            description=args.description,
            metadata=metadata,
            max_concurrency=args.max_concurrency,
        )
    else:
        result = run_experiment_for_file(
            data_path=args.data_file,
            experiment_name=args.experiment_name,
            run_name=args.run_name,
            description=args.description,
            metadata=metadata,
            max_concurrency=args.max_concurrency,
        )

    summary = build_run_summary(result)
    print(result.format())
    print("")
    print(f"Experiment: {summary.experiment_name}")
    print(f"Run: {summary.run_name}")
    print(f"Items: {summary.item_count}")
    print(f"Average judge score: {summary.average_score if summary.average_score is not None else 'n/a'}")
    print(f"Pass rate: {summary.pass_rate if summary.pass_rate is not None else 'n/a'}")
    if summary.dataset_run_url:
        print(f"Dataset run URL: {summary.dataset_run_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
