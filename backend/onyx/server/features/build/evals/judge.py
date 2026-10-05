"""Scoring engine for craft eval cases: two layers, one score.

Deterministic layer (mechanical, no LLM): expected-path existence,
``{{placeholder}}`` residue, JSON value anchors (the anti-hallucination
numeric check), and — when the case references a report contract — the
platform's own ``check_report_markdown`` postcheck.

LLM layer (fresh context): one structured call per case. The judge sees
only the original task, the rubric criteria, and the delivered artifact
text — never the agent transcript — so a persuasive process can't buy a
pass. Fail-closed: a judge timeout or unparseable verdict raises
``JudgeError`` and the runner records the case as ERROR (never PASS).

Score = weighted pass ratio across both layers. Deterministic checks are
hard gates (weight 2) so format violations can't be averaged away.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.db.enums import CraftEvalCaseStatus
from onyx.db.models import LLMProvider
from onyx.llm.factory import LLMProviderView, get_default_llm, llm_from_provider
from onyx.llm.interfaces import LLM
from onyx.llm.models import (
    LanguageModelInput,
    SystemMessage,
    UserMessage,
)
from onyx.llm.utils import llm_response_to_string
from onyx.report_templates.postcheck import check_report_markdown
from onyx.server.features.build.configs import (
    CRAFT_EVAL_JUDGE_MODEL,
    CRAFT_EVAL_JUDGE_PROVIDER,
    CRAFT_EVAL_JUDGE_TIMEOUT_SECONDS,
    CRAFT_EVAL_PASS_THRESHOLD,
)
from onyx.system_catalog.builtin.evals.loader import EvalCase
from onyx.system_catalog.builtin.manifest import BUILT_IN_REPORT_TEMPLATE_ENTRIES
from onyx.utils.logger import setup_logger
from onyx.utils.text_processing import parse_llm_json_response

logger = setup_logger()


class JudgeError(Exception):
    """Judge LLM failed or produced an unusable verdict — case must ERROR."""


# Hard gates outweigh a single rubric criterion (default weight 1).
_DETERMINISTIC_WEIGHT = 2.0

_PLACEHOLDER_PATTERN = re.compile(r"\{\{[^}]{0,80}")

# Artifact text budget for the judge prompt: markdown gets the lion's
# share, structured files are truncated harder.
_MD_BUDGET_CHARS = 24_000
_STRUCT_BUDGET_CHARS = 4_000

_JUDGE_SYSTEM_PROMPT = (
    "你是一名严格的交付质量评审。你会拿到:一个任务的原始要求、若干条评分判据、"
    "以及 agent 交付的产物文本。你的工作是对每条判据独立给出 pass / partial / fail "
    "判定,并引用产物中的具体证据(原文片段或缺失说明)。\n"
    "规则:\n"
    "1. 只依据给出的产物文本判定,不脑补交付物之外的内容。\n"
    "2. 判据要求的事实若在产物中找不到依据,判 fail,而不是 partial。\n"
    "3. partial 仅用于判据部分满足且未满足部分不属于核心要求的情形。\n"
    "4. evidence 必须具体:引用原文片段、数字或明确指出缺失点,不得只写「符合」。\n"
    "5. 不要因为报告写得长或语气自信而放松判定。"
)


@dataclass
class CaseJudgement:
    status: CraftEvalCaseStatus
    score: float
    deterministic: dict[str, Any]
    judge: dict[str, Any]


def resolve_judge_llm() -> LLM:
    """Judge model: explicit env pair if configured, tenant default else."""
    if CRAFT_EVAL_JUDGE_PROVIDER and CRAFT_EVAL_JUDGE_MODEL:
        with get_session_with_current_tenant() as db_session:
            provider = _lookup_provider_by_name(db_session, CRAFT_EVAL_JUDGE_PROVIDER)
            if provider is None:
                raise JudgeError(
                    f"CRAFT_EVAL_JUDGE_PROVIDER {CRAFT_EVAL_JUDGE_PROVIDER!r} "
                    "matches no LLM provider"
                )
            return llm_from_provider(
                model_name=CRAFT_EVAL_JUDGE_MODEL,
                llm_provider=provider,
                timeout=CRAFT_EVAL_JUDGE_TIMEOUT_SECONDS,
                temperature=0.0,
            )
    return get_default_llm(timeout=CRAFT_EVAL_JUDGE_TIMEOUT_SECONDS, temperature=0.0)


def _lookup_provider_by_name(db_session: Any, name: str) -> LLMProviderView | None:
    rows = list(db_session.scalars(select(LLMProvider).where(LLMProvider.name == name)))
    if len(rows) != 1:
        return None
    return LLMProviderView.from_model(rows[0])


def judge_case(case: EvalCase, artifacts: dict[str, str]) -> CaseJudgement:
    """Score one case's deliverables.

    Fail-closed: when the LLM judge layer fails (timeout, unparseable
    verdict) the returned judgement is ERROR with score 0 — the
    deterministic findings are still included so the failure is
    diagnosable from the case result alone.
    """
    deterministic = _run_deterministic_checks(case, artifacts)
    try:
        judge_verdict = _run_llm_judge(case, artifacts)
    except JudgeError as exc:
        logger.warning("eval judge failed for %s: %s", case.slug, exc)
        return CaseJudgement(
            status=CraftEvalCaseStatus.ERROR,
            score=0.0,
            deterministic=deterministic,
            judge={"error": str(exc)},
        )

    weight_sum = 0.0
    weighted = 0.0
    for finding in deterministic["findings"]:
        weight_sum += _DETERMINISTIC_WEIGHT
        if finding["passed"]:
            weighted += _DETERMINISTIC_WEIGHT
    for check in judge_verdict["checks"]:
        criterion = next((c for c in case.rubric if c.id == check["id"]), None)
        weight = criterion.weight if criterion else 1.0
        ratio = {"pass": 1.0, "partial": 0.5, "fail": 0.0}.get(check["verdict"], 0.0)
        weight_sum += weight
        weighted += weight * ratio

    score = weighted / weight_sum if weight_sum > 0 else 0.0
    status = (
        CraftEvalCaseStatus.PASS
        if score >= CRAFT_EVAL_PASS_THRESHOLD
        else CraftEvalCaseStatus.FAIL
    )
    return CaseJudgement(
        status=status,
        score=round(score, 4),
        deterministic=deterministic,
        judge=judge_verdict,
    )


# --------------------------------------------------------------------------- #
# Deterministic layer
# --------------------------------------------------------------------------- #


def _run_deterministic_checks(
    case: EvalCase, artifacts: dict[str, str]
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []

    for path in case.expected_paths:
        present = path in artifacts
        findings.append(
            {
                "check": f"exists:{path}",
                "passed": present,
                "detail": "present" if present else "missing deliverable",
                "weight": _DETERMINISTIC_WEIGHT,
            }
        )
        if not present:
            continue
        leftover = _PLACEHOLDER_PATTERN.findall(artifacts[path])
        findings.append(
            {
                "check": f"placeholders:{path}",
                "passed": not leftover,
                "detail": (
                    "no placeholder residue"
                    if not leftover
                    else f"leftover placeholders: {leftover[:5]}"
                ),
                "weight": _DETERMINISTIC_WEIGHT,
            }
        )

    findings.extend(
        _check_anchor(anchor.path, anchor.json_path, anchor.equals, artifacts)
        for anchor in case.value_anchors
    )

    report_path = _report_artifact_path(case)
    if case.report_contract_slug and report_path:
        contract = _load_report_contract(case.report_contract_slug)
        if contract is None:
            findings.append(
                {
                    "check": "postcheck:contract",
                    "passed": False,
                    "detail": (
                        f"unknown report contract slug: {case.report_contract_slug}"
                    ),
                    "weight": _DETERMINISTIC_WEIGHT,
                }
            )
        else:
            findings.extend(
                {
                    "check": f"postcheck:{finding.check}",
                    "passed": finding.passed,
                    "detail": finding.detail,
                    "weight": _DETERMINISTIC_WEIGHT,
                }
                for finding in check_report_markdown(
                    artifacts.get(report_path, ""), contract
                )
            )

    passed = sum(1 for f in findings if f["passed"])
    return {
        "findings": findings,
        "passed": passed,
        "total": len(findings),
    }


def _check_anchor(
    path: str, json_path: str, equals: Any, artifacts: dict[str, str]
) -> dict[str, Any]:
    raw = artifacts.get(path)
    if raw is None:
        return {
            "check": f"anchor:{path}:{json_path}",
            "passed": False,
            "detail": "deliverable missing",
            "weight": _DETERMINISTIC_WEIGHT,
        }
    try:
        document = json.loads(raw)
        actual = _resolve_json_path(document, json_path)
    except (ValueError, KeyError, TypeError) as exc:
        return {
            "check": f"anchor:{path}:{json_path}",
            "passed": False,
            "detail": f"unreadable: {exc}",
            "weight": _DETERMINISTIC_WEIGHT,
        }
    if _values_equal(actual, equals):
        detail = f"== {equals!r}"
        passed = True
    else:
        detail = f"expected {equals!r}, got {actual!r}"
        passed = False
    return {
        "check": f"anchor:{path}:{json_path}",
        "passed": passed,
        "detail": detail,
        "weight": _DETERMINISTIC_WEIGHT,
    }


def _resolve_json_path(document: Any, json_path: str) -> Any:
    current: Any = document
    for segment in json_path.split("."):
        if isinstance(current, dict):
            current = current[segment]
        elif isinstance(current, list):
            current = current[int(segment)]
        else:
            raise KeyError(f"cannot descend into {type(current).__name__}")
    return current


def _values_equal(actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return actual is expected
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if math.isnan(float(expected)) or math.isnan(float(actual)):
            return False
        # Tolerate float formatting noise only; 203300.001 != 203300.0.
        return math.isclose(float(actual), float(expected), rel_tol=1e-9, abs_tol=0.005)
    if isinstance(actual, str) and isinstance(expected, str):
        return actual.strip() == expected.strip()
    return actual == expected


def _report_artifact_path(case: EvalCase) -> str | None:
    for path in case.expected_paths:
        if path.endswith(".md"):
            return path
    return None


def _load_report_contract(slug: str) -> dict[str, Any] | None:
    for entry in BUILT_IN_REPORT_TEMPLATE_ENTRIES:
        if entry.slug == slug:
            return entry.read_contract()
    return None


# --------------------------------------------------------------------------- #
# Fresh-context LLM layer
# --------------------------------------------------------------------------- #


def _run_llm_judge(case: EvalCase, artifacts: dict[str, str]) -> dict[str, Any]:
    llm = resolve_judge_llm()
    prompt = _build_judge_prompt(case, artifacts)
    messages: LanguageModelInput = [
        SystemMessage(content=_JUDGE_SYSTEM_PROMPT),
        UserMessage(content=prompt),
    ]
    try:
        # No structured_response_format: providers disagree on its dialect
        # (e.g. DeepSeek rejects OpenAI-style {"type": "object"}). The
        # prompt pins the JSON shape and the parser tolerates fences.
        response = llm.invoke(messages)
    except Exception as exc:
        raise JudgeError(f"judge invoke failed: {exc}") from exc

    raw = llm_response_to_string(response)
    try:
        payload = parse_llm_json_response(raw) or {}
    except Exception as exc:
        raise JudgeError(f"judge response unparseable: {exc}") from exc
    checks = payload.get("checks")
    if not isinstance(checks, list) or not checks:
        raise JudgeError("judge returned no checks")

    known_ids = {c.id for c in case.rubric}
    by_id: dict[str, dict[str, Any]] = {}
    for check in checks:
        if not isinstance(check, dict):
            continue
        check_id = check.get("id")
        verdict = check.get("verdict")
        if check_id in known_ids and verdict in ("pass", "partial", "fail"):
            by_id[check_id] = {
                "id": check_id,
                "verdict": verdict,
                "evidence": str(check.get("evidence", ""))[:2000],
                "confidence": str(check.get("confidence", "medium")),
            }

    # Fail-closed: a criterion the judge skipped counts as fail, and the
    # omission is recorded rather than hidden.
    ordered: list[dict[str, Any]] = []
    omitted: list[str] = []
    for criterion in case.rubric:
        if criterion.id in by_id:
            ordered.append(by_id[criterion.id])
        else:
            omitted.append(criterion.id)
            ordered.append(
                {
                    "id": criterion.id,
                    "verdict": "fail",
                    "evidence": "judge omitted this criterion (fail-closed)",
                    "confidence": "high",
                }
            )
    return {
        "checks": ordered,
        "omitted": omitted,
        "comment": str(payload.get("comment", ""))[:2000],
        "model": _judge_model_label(),
    }


def _judge_model_label() -> str:
    if CRAFT_EVAL_JUDGE_PROVIDER and CRAFT_EVAL_JUDGE_MODEL:
        return f"{CRAFT_EVAL_JUDGE_PROVIDER}/{CRAFT_EVAL_JUDGE_MODEL}"
    return "tenant-default"


def _build_judge_prompt(case: EvalCase, artifacts: dict[str, str]) -> str:
    sections: list[str] = []

    sections.append("【任务原始要求】\n" + case.user_prompt.strip())

    criteria_lines = "\n".join(f"- [{c.id}] {c.criterion}" for c in case.rubric)
    sections.append("【评分判据】(逐条判定)\n" + criteria_lines)

    artifact_parts: list[str] = []
    md_budget = _MD_BUDGET_CHARS
    for path in case.expected_paths:
        content = artifacts.get(path)
        if content is None:
            artifact_parts.append(f"--- 交付物 {path}:缺失 ---")
            continue
        if path.endswith(".md"):
            budget = min(md_budget, len(content))
            md_budget -= budget
        else:
            budget = min(_STRUCT_BUDGET_CHARS, len(content))
        text = content[:budget]
        note = "" if budget >= len(content) else "\n…(已截断)"
        artifact_parts.append(
            f"--- 交付物 {path} 开始 ---\n{text}{note}\n--- 交付物 {path} 结束 ---"
        )
    sections.append(
        "【交付物】(评分对象;图片等二进制产物未包含,判据涉及时依据文本中的"
        "图注与引用判定)\n" + "\n\n".join(artifact_parts)
    )

    sections.append(
        "对上述每一条评分判据输出判定,并给一段总体 comment。"
        "只输出一个 JSON 对象,不要输出任何其他文本,格式为:\n"
        '{"checks": [{"id": "<判据id>", "verdict": "pass|partial|fail", '
        '"evidence": "<具体证据>", "confidence": "high|medium|low"}], '
        '"comment": "<总体评语>"}'
    )
    return "\n\n".join(sections)
