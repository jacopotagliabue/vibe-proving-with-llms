"""Tests for textbook examples from forallx.jsonl, lpl_1.jsonl, and lpl_2.jsonl."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from proof_checker import ProofChecker


FORALLX_PATH = Path(__file__).parent.parent / "forallx.jsonl"
LPL_1_PATH = Path(__file__).parent.parent / "lpl_1.jsonl"
LPL_2_PATH = Path(__file__).parent.parent / "lpl_2.jsonl"


def build_minimal_proof(premises: list[str], conclusion: str) -> str:
    """Build a minimal proof string to test parsing."""
    lines = []
    line_num = 1

    for premise in premises:
        lines.append(f"{line_num}. {premise}")
        line_num += 1

    lines.append("_")

    if premises:
        refs = ",".join(str(i) for i in range(1, len(premises) + 1))
        lines.append(f"{line_num}. {conclusion} ({refs})")
    else:
        lines.append(f"{line_num}. | {conclusion}")
        lines.append(f"{line_num + 1}. | {conclusion} ({line_num})")
        lines.append("__")
        lines.append(f"{line_num + 2}. {conclusion} ({line_num}-{line_num + 1})")

    return "\n".join(lines)


def test_all_forallx_examples_are_parseable():
    """All forallx examples should be syntactically parseable."""
    with open(FORALLX_PATH) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            example = json.loads(line)
            premises = example["premises"]
            conclusion = example["conclusion"]

            proof_str = build_minimal_proof(premises, conclusion)
            checker = ProofChecker(proof_str)

            parsed_premises = [ln for ln in checker.lines if ln.is_premise]
            assert len(parsed_premises) == len(premises), (
                f"Line {line_num}: Expected {len(premises)} premises, got {len(parsed_premises)}"
            )
            assert checker.lines[-1].formula == conclusion, (
                f"Line {line_num}: Conclusion mismatch"
            )


def test_all_lpl_1_examples_are_parseable():
    """All lpl_1 examples (exercises 6.24-6.27) should be syntactically parseable."""
    with open(LPL_1_PATH) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            example = json.loads(line)
            premises = example["premises"]
            conclusion = example["conclusion"]

            proof_str = build_minimal_proof(premises, conclusion)
            checker = ProofChecker(proof_str)

            parsed_premises = [ln for ln in checker.lines if ln.is_premise]
            assert len(parsed_premises) == len(premises), (
                f"Line {line_num}: Expected {len(premises)} premises, got {len(parsed_premises)}"
            )
            assert checker.lines[-1].formula == conclusion, (
                f"Line {line_num}: Conclusion mismatch"
            )


def test_all_lpl_2_examples_are_parseable():
    """All lpl_2 examples (exercises 6.18-6.20) should be syntactically parseable."""
    with open(LPL_2_PATH) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            example = json.loads(line)
            premises = example["premises"]
            conclusion = example["conclusion"]

            proof_str = build_minimal_proof(premises, conclusion)
            checker = ProofChecker(proof_str)

            parsed_premises = [ln for ln in checker.lines if ln.is_premise]
            assert len(parsed_premises) == len(premises), (
                f"Line {line_num}: Expected {len(premises)} premises, got {len(parsed_premises)}"
            )
            assert checker.lines[-1].formula == conclusion, (
                f"Line {line_num}: Conclusion mismatch"
            )
