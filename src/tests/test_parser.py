"""Tests for the proof checker parser."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from proof_checker import (
    ProofChecker,
    ProofParseError,
    FormulaError,
    TooManyVariablesError,
    MAX_VARIABLES,
)


# --- Parentheses in Formulas ---


def test_formula_with_parentheses_identifies_line_dependency():
    """Parentheses in formula don't confuse line dependency parsing."""
    proof = """
1. A
2. B
_
3. (A and B) (1,2)
"""
    checker = ProofChecker(proof)
    line3 = checker.get_line(3)
    assert line3.formula == "(A and B)"
    assert line3.justification_lines == [1, 2]


def test_multiple_parenthesized_subformulas():
    """Multiple parenthesized parts in formula work correctly."""
    proof = """
1. A
2. B
3. C
4. D
_
5. (A and B) or (C and D) (1,2,3,4)
"""
    checker = ProofChecker(proof)
    line5 = checker.get_line(5)
    assert line5.formula == "(A and B) or (C and D)"
    assert line5.justification_lines == [1, 2, 3, 4]


# --- Zero Premises ---


def test_zero_premises_valid():
    """A proof can have zero premises - must actually prove the tautology."""
    proof = """
_
1. | not (A or not A)
2. || A
3. || A or not A (2)
4. || ~ (1,3)
__
5. | not A (2-4)
6. | A or not A (5)
7. | ~ (1,6)
__
8. A or not A (1-7)
"""
    checker = ProofChecker(proof)
    assert checker.check() is True
    # Verify no premises
    premises = [ln for ln in checker.lines if ln.is_premise]
    assert len(premises) == 0
    # Final conclusion
    assert checker.lines[-1].formula == "A or not A"


# --- No Conclusion Invalid ---


def test_no_conclusion_raises_error():
    """Proof with no lines after _ should raise error."""
    proof = """
1. A
2. B
_
"""
    with pytest.raises(ProofParseError, match="at least one derived line"):
        ProofChecker(proof)


# --- Formula Validation: Valid Formulas ---


def test_simple_variable():
    """Single uppercase variable is valid."""
    proof = """
1. A
_
2. A (1)
"""
    checker = ProofChecker(proof)
    assert checker.get_line(1).formula == "A"


def test_multi_letter_variable():
    """Multi-letter uppercase variable is valid."""
    proof = """
1. ABC
_
2. ABC (1)
"""
    checker = ProofChecker(proof)
    assert checker.get_line(1).formula == "ABC"


def test_and_operator():
    """'and' operator is valid."""
    proof = """
1. A and B
_
2. A (1)
"""
    checker = ProofChecker(proof)
    assert checker.get_line(1).formula == "A and B"


def test_or_operator():
    """'or' operator is valid."""
    proof = """
1. A or B
_
2. A or B (1)
"""
    checker = ProofChecker(proof)
    assert checker.get_line(1).formula == "A or B"


def test_not_operator():
    """'not' operator is valid."""
    proof = """
1. not A
_
2. not A (1)
"""
    checker = ProofChecker(proof)
    assert checker.get_line(1).formula == "not A"


def test_complex_formula_with_all_operators():
    """Complex formula with and, or, not is valid."""
    proof = """
1. (A and B) or (not C)
_
2. (A and B) or (not C) (1)
"""
    checker = ProofChecker(proof)
    assert checker.get_line(1).formula == "(A and B) or (not C)"


def test_deeply_nested_parentheses():
    """Deeply nested parentheses are valid."""
    proof = """
1. (((A and B)))
_
2. (((A and B))) (1)
"""
    checker = ProofChecker(proof)
    assert checker.get_line(1).formula == "(((A and B)))"


def test_multiple_variables():
    """Multiple different variables are valid."""
    proof = """
1. P and Q and R and S
_
2. P (1)
"""
    checker = ProofChecker(proof)
    assert checker.get_line(1).formula == "P and Q and R and S"


def test_whitespace_normalized():
    """Extra whitespace is normalized."""
    proof = """
1. A   and    B
_
2. A (1)
"""
    checker = ProofChecker(proof)
    assert "A" in checker.get_line(1).formula
    assert "B" in checker.get_line(1).formula


# --- Formula Validation: Invalid Formulas ---


def test_lowercase_variable_rejected():
    """Lowercase variable (not an operator) is rejected."""
    proof = """
1. a
_
2. a (1)
"""
    with pytest.raises(FormulaError, match="Invalid token"):
        ProofChecker(proof)


def test_mixed_case_variable_rejected():
    """Mixed case variable like 'Ab' is rejected."""
    proof = """
1. Ab
_
2. Ab (1)
"""
    with pytest.raises(FormulaError, match="Invalid token"):
        ProofChecker(proof)


def test_number_in_formula_rejected():
    """Numbers in formula are rejected."""
    proof = """
1. A1
_
2. A1 (1)
"""
    with pytest.raises(FormulaError, match="invalid characters"):
        ProofChecker(proof)


def test_special_characters_rejected():
    """Special characters like & are rejected."""
    ops = ["||", "!", "&&"]
    for op in ops:
        proof = f"""
1. A {op} B
_
2. A (1)
"""
        with pytest.raises(FormulaError, match="invalid characters"):
            ProofChecker(proof)


def test_AND_uppercase_rejected():
    """'AND' uppercase is rejected (operators must be lowercase)."""
    proof = """
1. A AND B
_
2. A (1)
"""
    with pytest.raises(FormulaError, match="Invalid token"):
        ProofChecker(proof)


def test_Or_mixed_case_rejected():
    """'Or' mixed case is rejected."""
    proof = """
1. A Or B
_
2. A (1)
"""
    with pytest.raises(FormulaError, match="Invalid token"):
        ProofChecker(proof)


# --- Missing Separator ---


def test_no_separator_raises_error():
    """Proof without _ raises error."""
    proof = """
1. A
2. B
3. A and B (1,2)
"""
    with pytest.raises(ProofParseError, match="separator"):
        ProofChecker(proof)


# --- Contradiction Symbol ---


def test_contradiction_symbol_allowed():
    """Contradiction symbol ~ is a valid formula."""
    proof = """
1. A and not A
_
2. ~ (1)
"""
    checker = ProofChecker(proof)
    assert checker.get_line(2).formula == "~"


# --- Too Many Variables ---


def test_too_many_variables_raises_error():
    """Proof with more than MAX_VARIABLES variables should raise error."""
    variables = [chr(ord("A") + i) for i in range(MAX_VARIABLES + 1)]
    premises = "\n".join(f"{i + 1}. {v}" for i, v in enumerate(variables))
    conclusion_line = len(variables) + 1
    proof = f"""
{premises}
_
{conclusion_line}. {variables[0]} (1)
"""
    with pytest.raises(TooManyVariablesError, match=f"{MAX_VARIABLES + 1} variables"):
        ProofChecker(proof)


def test_exactly_max_variables_allowed():
    """Proof with exactly MAX_VARIABLES variables should be allowed."""
    variables = [chr(ord("A") + i) for i in range(MAX_VARIABLES)]
    premises = "\n".join(f"{i + 1}. {v}" for i, v in enumerate(variables))
    conclusion_line = len(variables) + 1
    proof = f"""
{premises}
_
{conclusion_line}. {variables[0]} (1)
"""
    checker = ProofChecker(proof)
    assert len(checker.lines) == MAX_VARIABLES + 1


# --- Subproof Parsing ---


def test_single_subproof_depth():
    """Single | indicates subproof depth 1."""
    proof = """
1. A and B
_
2. | not A
3. | A (1)
4. | ~ (2,3)
5. A (4)
"""
    checker = ProofChecker(proof)
    assert checker.get_line(1).subproof_depth == 0
    assert checker.get_line(2).subproof_depth == 1
    assert checker.get_line(3).subproof_depth == 1
    assert checker.get_line(4).subproof_depth == 1
    assert checker.get_line(5).subproof_depth == 0


def test_subproof_formula_extracted_correctly():
    """Formula is extracted without the | prefix."""
    proof = """
1. A
_
2. | not A
3. | ~ (1,2)
4. A (3)
"""
    checker = ProofChecker(proof)
    assert checker.get_line(2).formula == "not A"
    assert checker.get_line(3).formula == "~"


def test_nested_subproof_depth():
    """|| indicates subproof depth 2."""
    proof = """
1. A
_
2. | B
3. || C
4. || C (3)
5. | C (4)
6. C (5)
"""
    checker = ProofChecker(proof)
    assert checker.get_line(1).subproof_depth == 0
    assert checker.get_line(2).subproof_depth == 1
    assert checker.get_line(3).subproof_depth == 2
    assert checker.get_line(4).subproof_depth == 2
    assert checker.get_line(5).subproof_depth == 1
    assert checker.get_line(6).subproof_depth == 0


def test_triple_nested_subproof():
    """||| indicates subproof depth 3."""
    proof = """
1. A
_
2. ||| B
3. ||| B (2)
4. B (3)
"""
    checker = ProofChecker(proof)
    assert checker.get_line(2).subproof_depth == 3
    assert checker.get_line(3).subproof_depth == 3


def test_subproof_assumption_no_justification():
    """First line of subproof (assumption) has no justification."""
    proof = """
1. A
_
2. | not A
3. | ~ (1,2)
4. A (3)
"""
    checker = ProofChecker(proof)
    line2 = checker.get_line(2)
    assert line2.subproof_depth == 1
    assert line2.justification_lines == []
    assert line2.formula == "not A"


def test_subproof_with_justification():
    """Subproof lines can have justifications."""
    proof = """
1. A and B
_
2. | not A
3. | A (1)
4. | ~ (2,3)
5. A (4)
"""
    checker = ProofChecker(proof)
    line3 = checker.get_line(3)
    assert line3.subproof_depth == 1
    assert line3.justification_lines == [1]
    assert line3.formula == "A"


def test_subproof_repr():
    """__repr__ shows subproof depth with | characters."""
    proof = """
1. A
_
2. | not A
3. A (2)
"""
    checker = ProofChecker(proof)
    repr_str = repr(checker)
    assert "| not A" in repr_str


def test_main_proof_lines_have_depth_zero():
    """Lines without | prefix have subproof_depth 0."""
    proof = """
1. A
2. B
_
3. A and B (1,2)
"""
    checker = ProofChecker(proof)
    for line in checker.lines:
        assert line.subproof_depth == 0


# --- Subproof End Marker ---


def test_subproof_end_marker_parsed():
    """__ is recognized and skipped during parsing."""
    proof = """
1. A or B
_
2. | A
3. | C (2)
__
4. | B
5. | C (4)
__
6. C (1, 2-3, 4-5)
"""
    checker = ProofChecker(proof)
    assert len(checker.lines) == 6


def test_separate_subproofs_have_different_ids():
    """Subproofs separated by __ have different subproof_ids."""
    proof = """
1. A or B
_
2. | A
3. | C (2)
__
4. | B
5. | C (4)
__
6. C (1, 2-3, 4-5)
"""
    checker = ProofChecker(proof)
    line2 = checker.get_line(2)
    line3 = checker.get_line(3)
    line4 = checker.get_line(4)
    line5 = checker.get_line(5)

    assert line2.subproof_id == line3.subproof_id
    assert line4.subproof_id == line5.subproof_id
    assert line2.subproof_id != line4.subproof_id


def test_main_proof_lines_have_subproof_id_zero():
    """Lines at depth 0 have subproof_id 0."""
    proof = """
1. A or B
_
2. | A
3. | C (2)
__
4. C (2-3)
"""
    checker = ProofChecker(proof)
    assert checker.get_line(1).subproof_id == 0
    assert checker.get_line(4).subproof_id == 0


def test_subproof_without_end_marker():
    """Subproof without __ still works (implicit end at depth change)."""
    proof = """
1. A and B
_
2. | not A
3. | A (1)
4. | ~ (2,3)
5. A (2-4)
"""
    checker = ProofChecker(proof)
    assert checker.get_line(2).subproof_id == checker.get_line(3).subproof_id
    assert checker.get_line(3).subproof_id == checker.get_line(4).subproof_id
    assert checker.get_line(5).subproof_id == 0


def test_subproof_ref_parsing():
    """Subproof references are parsed correctly."""
    proof = """
1. A or B
_
2. | A
3. | C (2)
__
4. | B
5. | C (4)
__
6. C (1, 2-3, 4-5)
"""
    checker = ProofChecker(proof)
    line6 = checker.get_line(6)
    assert line6.justification_lines == [1]
    assert len(line6.justification_subproofs) == 2
    assert line6.justification_subproofs[0].start == 2
    assert line6.justification_subproofs[0].end == 3
    assert line6.justification_subproofs[1].start == 4
    assert line6.justification_subproofs[1].end == 5
