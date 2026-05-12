"""LLM-as-judge eval pipeline для Langfuse experiments."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

from bot.config import config
from bot.logger import logger
from stdlib.llm.client import langfuse, openai_client
from stdlib.llm.formatter import format_text
from stdlib.llm.free_form import process_free_form_chat
from stdlib.models import EvalDatasetItem, EvalRunSummary, EvalTaskInput, LLMJudgeScore


def _serialize_output(value: Any) -> str:
    """Приводит результат task/eval к строке для judge и логов."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if hasattr(value, "model_dump"):
        payload = value.model_dump(mode="json")
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
    return str(value)


def _coerce_case(
    *,
    input: Any,
    expected_output: Any = None,
    metadata: dict[str, Any] | None = None,
    item_id: str | None = None,
) -> EvalDatasetItem:
    """Нормализует кейс из local dataset или Langfuse dataset item."""
    return EvalDatasetItem.model_validate(
        {
            "id": item_id,
            "input": input,
            "expected_output": expected_output,
            "metadata": metadata or {},
        }
    )


def _build_judge_messages(
    *,
    task_input: EvalTaskInput,
    output: Any,
    expected_output: Any,
    metadata: dict[str, Any] | None,
) -> list[dict[str, str]]:
    """Собирает сообщения для judge-модели."""
    system = (
        "Ты оцениваешь качество ответа прикладной LLM-системы. "
        "Верни строгий JSON по схеме. "
        "Оцени по шкале от 0 до 1, где 1 — полностью корректный и полезный ответ. "
        "Учитывай точность, полноту, соответствие задаче, деловой стиль и отсутствие выдуманных фактов. "
        "Если expected_output отсутствует, оцени ответ по внутреннему качеству и соответствию задаче."
    )
    user_payload = {
        "task_type": task_input.task_type,
        "input": task_input.model_dump(mode="json"),
        "output": _serialize_output(output),
        "expected_output": expected_output,
        "metadata": metadata or {},
        "pass_threshold": config.LANGFUSE_EVAL_PASS_THRESHOLD,
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, indent=2)},
    ]


async def execute_eval_task(*, item: Any, **kwargs: dict[str, Any]) -> str:
    """Запускает целевой LLM-сценарий для одного eval-кейса."""
    del kwargs

    case = _coerce_case(
        input=item["input"] if isinstance(item, dict) else item.input,
        expected_output=item.get("expected_output") if isinstance(item, dict) else item.expected_output,
        metadata=item.get("metadata") if isinstance(item, dict) else item.metadata,
        item_id=item.get("id") if isinstance(item, dict) else getattr(item, "id", None),
    )
    task_input = case.input

    logger.info("Eval task start | task_type={} case_id={}", task_input.task_type, case.id)

    if task_input.task_type == "free_form":
        result = await process_free_form_chat(
            history=[msg.model_dump(mode="json") for msg in task_input.history],
            app_id=task_input.app_id,
            user_id=task_input.user_id,
        )
        return _serialize_output(result)

    result = await format_text(
        raw=task_input.raw,
        context_blocks=task_input.context_blocks,
        user_id=task_input.user_id,
        app_id=task_input.app_id,
        block_number=task_input.block_number,
        generate=task_input.generate,
    )
    return _serialize_output(result.text)


async def llm_as_judge_evaluator(
    *,
    input: Any,
    output: Any,
    expected_output: Any,
    metadata: dict[str, Any] | None,
    **kwargs: dict[str, Any],
) -> list[dict[str, Any]]:
    """Оценивает результат task через judge-модель и возвращает score'ы Langfuse."""
    del kwargs

    task_input = EvalTaskInput.model_validate(input)
    messages = _build_judge_messages(
        task_input=task_input,
        output=output,
        expected_output=expected_output,
        metadata=metadata,
    )
    response = await openai_client.beta.chat.completions.parse(
        model=config.LANGFUSE_EVAL_JUDGE_MODEL,
        messages=messages,
        response_format=LLMJudgeScore,
        temperature=config.LANGFUSE_EVAL_JUDGE_TEMPERATURE,
        max_tokens=config.LANGFUSE_EVAL_MAX_TOKENS,
    )
    judge = response.choices[0].message.parsed
    logger.info(
        "Eval judge done | task_type={} score={:.3f} passed={}",
        task_input.task_type,
        judge.score,
        judge.passed,
    )
    return [
        {
            "name": "llm_judge_score",
            "value": judge.score,
            "comment": judge.reasoning,
            "metadata": {
                "strengths": judge.strengths,
                "issues": judge.issues,
                "suggested_fix": judge.suggested_fix,
            },
        },
        {
            "name": "llm_judge_pass",
            "value": judge.passed,
            "comment": judge.reasoning,
            "metadata": {"threshold": config.LANGFUSE_EVAL_PASS_THRESHOLD},
        },
    ]


def load_eval_cases(path: str | Path) -> list[dict[str, Any]]:
    """Читает локальный eval dataset из JSON или JSONL."""
    file_path = Path(path)
    raw = file_path.read_text(encoding="utf-8").strip()
    if not raw:
        return []

    if file_path.suffix.lower() == ".jsonl":
        items = [json.loads(line) for line in raw.splitlines() if line.strip()]
    else:
        payload = json.loads(raw)
        items = payload if isinstance(payload, list) else payload.get("items", [])

    validated = [EvalDatasetItem.model_validate(item) for item in items]
    return [
        {
            "input": item.input.model_dump(mode="json"),
            "expected_output": item.expected_output,
            "metadata": item.metadata,
        }
        for item in validated
    ]


def build_run_summary(result: Any) -> EvalRunSummary:
    """Собирает компактную сводку по завершённому experiment."""
    judge_scores: list[float] = []
    pass_values: list[float] = []

    for item_result in getattr(result, "item_results", []):
        for evaluation in getattr(item_result, "evaluations", []):
            name = getattr(evaluation, "name", None)
            value = getattr(evaluation, "value", None)
            if name == "llm_judge_score" and isinstance(value, int | float):
                judge_scores.append(float(value))
            if name == "llm_judge_pass" and isinstance(value, bool):
                pass_values.append(1.0 if value else 0.0)

    return EvalRunSummary(
        experiment_name=getattr(result, "name", "langfuse-eval"),
        run_name=getattr(result, "run_name", "run"),
        item_count=len(getattr(result, "item_results", [])),
        average_score=mean(judge_scores) if judge_scores else None,
        pass_rate=mean(pass_values) if pass_values else None,
        dataset_run_url=getattr(result, "dataset_run_url", None),
    )


def _require_langfuse() -> Any:
    """Проверяет, что Langfuse настроен и доступен."""
    if langfuse is None:
        raise RuntimeError(
            "Langfuse не инициализирован. Проверьте LANGFUSE_PUBLIC_KEY и LANGFUSE_SECRET_KEY."
        )
    return langfuse


def run_experiment_for_dataset(
    *,
    dataset_name: str,
    experiment_name: str,
    run_name: str | None = None,
    description: str | None = None,
    metadata: dict[str, str] | None = None,
    max_concurrency: int | None = None,
) -> Any:
    """Запускает eval по существующему Langfuse dataset."""
    client = _require_langfuse()
    dataset = client.get_dataset(dataset_name)
    return dataset.run_experiment(
        name=experiment_name,
        run_name=run_name,
        description=description,
        task=execute_eval_task,
        evaluators=[llm_as_judge_evaluator],
        max_concurrency=max_concurrency or config.LANGFUSE_EVAL_MAX_CONCURRENCY,
        metadata=metadata,
    )


def run_experiment_for_file(
    *,
    data_path: str | Path,
    experiment_name: str,
    run_name: str | None = None,
    description: str | None = None,
    metadata: dict[str, str] | None = None,
    max_concurrency: int | None = None,
) -> Any:
    """Запускает eval по локальному JSON/JSONL набору кейсов."""
    client = _require_langfuse()
    data = load_eval_cases(data_path)
    if not data:
        raise ValueError(f"Eval dataset пуст: {data_path}")
    return client.run_experiment(
        name=experiment_name,
        run_name=run_name,
        description=description,
        data=data,
        task=execute_eval_task,
        evaluators=[llm_as_judge_evaluator],
        max_concurrency=max_concurrency or config.LANGFUSE_EVAL_MAX_CONCURRENCY,
        metadata=metadata,
    )
