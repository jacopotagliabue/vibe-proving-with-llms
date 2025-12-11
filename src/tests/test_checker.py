"""Tests for proof validity checking."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from proof_checker import (
    ProofChecker,
    InvalidProofError,
)


# --- Basic Valid Proofs ---


def test_and_introduction_valid():
    """And introduction: from A and B, derive A and B."""
    proof = """
1. A
2. B
_
3. A and B (1,2)
"""
    checker = ProofChecker(proof)
    assert checker.check() is True


def test_and_elimination_valid():
    """And elimination: from A and B, derive A (or B)."""
    proof = """
1. A and B
_
2. A (1)
"""
    checker = ProofChecker(proof)
    assert checker.check() is True


def test_or_introduction_valid():
    """Or introduction: from A, derive A or B."""
    proof = """
1. A
_
2. A or B (1)
"""
    checker = ProofChecker(proof)
    assert checker.check() is True


def test_complex_proof_valid():
    """Complex multi-step proof."""
    proof = """
1. P and Q
2. R
_
3. P (1)
4. Q (1)
5. P and R (3,2)
"""
    checker = ProofChecker(proof)
    assert checker.check() is True


def test_double_negation_valid():
    """Double negation: from not not A, derive A (classical logic)."""
    proof = """
1. not not A
_
2. A (1)
"""
    checker = ProofChecker(proof)
    assert checker.check() is True


def test_identity_valid():
    """Identity: from A, derive A."""
    proof = """
1. A
_
2. A (1)
"""
    checker = ProofChecker(proof)
    assert checker.check() is True


# --- Invalid Proofs ---


def test_and_introduction_missing_conjunct_invalid():
    """Cannot derive A and B from just A."""
    proof = """
1. A
_
2. A and B (1)
"""
    checker = ProofChecker(proof)
    with pytest.raises(InvalidProofError) as exc_info:
        checker.check()
    assert exc_info.value.line_number == 2
    assert exc_info.value.justification_lines == [1]


def test_or_elimination_invalid():
    """Cannot derive A from A or B alone."""
    proof = """
1. A or B
_
2. A (1)
"""
    checker = ProofChecker(proof)
    with pytest.raises(InvalidProofError) as exc_info:
        checker.check()
    assert exc_info.value.line_number == 2


def test_wrong_conclusion_invalid():
    """Cannot derive B from A."""
    proof = """
1. A
_
2. B (1)
"""
    checker = ProofChecker(proof)
    with pytest.raises(InvalidProofError) as exc_info:
        checker.check()
    assert exc_info.value.line_number == 2


def test_affirming_consequent_invalid():
    """Fallacy: cannot derive A from B (unrelated)."""
    proof = """
1. A and B
_
2. C (1)
"""
    checker = ProofChecker(proof)
    with pytest.raises(InvalidProofError) as exc_info:
        checker.check()
    assert exc_info.value.line_number == 2


def test_negation_from_positive_invalid():
    """Cannot derive not A from A."""
    proof = """
1. A
_
2. not A (1)
"""
    checker = ProofChecker(proof)
    with pytest.raises(InvalidProofError) as exc_info:
        checker.check()
    assert exc_info.value.line_number == 2


# --- Contradiction and Explosion ---


def test_explosion_valid():
    """From contradiction, anything follows (ex falso quodlibet)."""
    proof = """
1. ~
_
2. A (1)
"""
    checker = ProofChecker(proof)
    assert checker.check() is True


def test_explosion_any_formula_valid():
    """From contradiction, any complex formula follows."""
    proof = """
1. ~
_
2. A and B and C (1)
"""
    checker = ProofChecker(proof)
    assert checker.check() is True


# --- Indirect Proof (Reductio ad Absurdum) ---


def test_indirect_proof_basic():
    """Basic indirect proof: assume not A, derive contradiction, conclude A."""
    proof = """
1. A and B
_
2. | not A
3. | A (1)
4. | ~ (2,3)
__
5. A (2-4)
"""
    checker = ProofChecker(proof)
    assert checker.check() is True


def test_indirect_proof_assume_positive_conclude_negative():
    """Indirect proof: assume A, derive contradiction, conclude not A."""
    proof = """
1. not A
_
2. | A
3. | ~ (1,2)
__
4. not A (2-3)
"""
    checker = ProofChecker(proof)
    assert checker.check() is True


def test_indirect_proof_complex_formula():
    """Indirect proof with complex formula as assumption."""
    proof = """
1. not (A and B)
2. A
_
3. | A and B
4. | ~ (1,3)
__
5. not (A and B) (3-4)
"""
    checker = ProofChecker(proof)
    assert checker.check() is True


def test_indirect_proof_wrong_conclusion_invalid():
    """Invalid: conclusion doesn't match negation of assumption."""
    proof = """
1. A and B
_
2. | not A
3. | A (1)
4. | ~ (2,3)
__
5. B (2-4)
"""
    checker = ProofChecker(proof)
    with pytest.raises(InvalidProofError) as exc_info:
        checker.check()
    assert exc_info.value.line_number == 5


def test_indirect_proof_subproof_not_ending_in_contradiction_valid():
    """Subproof not ending in contradiction can still be valid if implication works.

    Note: 'not A -> A' is logically equivalent to 'A' (tautology),
    so this proof is actually valid!
    """
    proof = """
1. A and B
_
2. | not A
3. | A (1)
__
4. A (2-3)
"""
    checker = ProofChecker(proof)
    assert checker.check() is True


def test_subproof_implication_does_not_entail_unrelated_formula():
    """Invalid: conclusion doesn't follow from the subproof implication."""
    proof = """
1. A
_
2. | B
3. | A (1)
__
4. B (2-3)
"""
    checker = ProofChecker(proof)
    with pytest.raises(InvalidProofError) as exc_info:
        checker.check()
    assert exc_info.value.line_number == 4


def test_indirect_proof_lines_within_subproof_checked():
    """Lines within subproof are still checked for validity."""
    proof = """
1. A
_
2. | not A
3. | B (1)
4. | ~ (2,3)
__
5. A (2-4)
"""
    checker = ProofChecker(proof)
    with pytest.raises(InvalidProofError) as exc_info:
        checker.check()
    assert exc_info.value.line_number == 3


def test_indirect_proof_subproof_can_use_outer_premises():
    """Subproof lines can reference lines from outer proof."""
    proof = """
1. A and B
_
2. | not A
3. | A (1)
4. | ~ (2,3)
__
5. A (2-4)
"""
    checker = ProofChecker(proof)
    assert checker.check() is True


def test_indirect_proof_derive_double_negation():
    """Indirect proof can derive double negation."""
    proof = """
1. A
_
2. | not A
3. | ~ (1,2)
__
4. not not A (2-3)
"""
    checker = ProofChecker(proof)
    assert checker.check() is True


def test_indirect_proof_with_end_marker():
    """Indirect proof works with explicit __ marker."""
    proof = """
1. A and B
_
2. | not A
3. | A (1)
4. | ~ (2,3)
__
5. A (2-4)
"""
    checker = ProofChecker(proof)
    assert checker.check() is True


def test_multiple_sequential_subproofs():
    """Multiple subproofs in sequence with __ markers."""
    proof = """
1. A
2. B
_
3. | not A
4. | ~ (1,3)
__
5. not not A (3-4)
6. | not B
7. | ~ (2,6)
__
8. not not B (6-7)
"""
    checker = ProofChecker(proof)
    assert checker.check() is True


# --- Invalid Proof Taken from forallx ---


def test_invalid_and_elimination_from_disjunction():
    """Invalid proof from the book 'forallx', Chapter 17"""
    proof = """
1. (not L and A) or L
_
2. | not L and A
3. | not L (2)
4. | A (2)
__
5. | L
6. | ~ (3,5)
7. | A (6)
__
8. A (1, 2-4, 5-7)
"""
    checker = ProofChecker(proof)
    with pytest.raises(InvalidProofError) as exc_info:
        checker.check()
    assert exc_info.value.line_number == 6


# --- Or Elimination ---


def test_or_elimination_basic():
    """Basic or-elimination: from A or B, with both branches deriving A or B, conclude A or B."""
    proof = """
1. A or B
_
2. | A
3. | A or B (2)
__
4. | B
5. | A or B (4)
__
6. A or B (1, 2-3, 4-5)
"""
    checker = ProofChecker(proof)
    assert checker.check() is True


def test_or_elimination_identity_in_branches():
    """Or-elimination where branches just use the assumption directly."""
    proof = """
1. A or A
_
2. | A
3. | A (2)
__
4. | A
5. | A (4)
__
6. A (1, 2-3, 4-5)
"""
    checker = ProofChecker(proof)
    assert checker.check() is True


def test_or_elimination_with_premises():
    """Or-elimination using additional premises in the branches."""
    proof = """
1. A or B
2. A and C
3. B and C
_
4. | A
5. | C (2)
__
6. | B
7. | C (3)
__
8. C (1, 4-5, 6-7)
"""
    checker = ProofChecker(proof)
    assert checker.check() is True


def test_or_elimination_wrong_conclusion_invalid():
    """Invalid: conclusion doesn't match what both branches establish."""
    proof = """
1. A or B
2. A and C
3. B and D
_
4. | A
5. | C (2)
__
6. | B
7. | D (3)
__
8. C (1, 4-5, 6-7)
"""
    checker = ProofChecker(proof)
    with pytest.raises(InvalidProofError) as exc_info:
        checker.check()
    assert exc_info.value.line_number == 8


def test_or_elimination_missing_disjunction_invalid():
    """Invalid: or-elimination without the disjunction premise."""
    proof = """
1. A and C
2. B and C
_
3. | A
4. | C (1)
__
5. | B
6. | C (2)
__
7. C (3-4, 5-6)
"""
    checker = ProofChecker(proof)
    with pytest.raises(InvalidProofError) as exc_info:
        checker.check()
    assert exc_info.value.line_number == 7


def test_or_elimination_complex_formulas():
    """Or-elimination with complex formulas."""
    proof = """
1. (A and B) or (C and D)
_
2. | A and B
3. | A (2)
4. | A or C (3)
__
5. | C and D
6. | C (5)
7. | A or C (6)
__
8. A or C (1, 2-4, 5-7)
"""
    checker = ProofChecker(proof)
    assert checker.check() is True


def test_or_elimination_derive_or_from_branches():
    """Or-elimination where conclusion is itself a disjunction."""
    proof = """
1. A or B
_
2. | A
3. | A or B (2)
__
4. | B
5. | A or B (4)
__
6. A or B (1, 2-3, 4-5)
"""
    checker = ProofChecker(proof)
    assert checker.check() is True


def test_or_elimination_branches_derive_contradiction():
    """Or-elimination where both branches derive contradiction."""
    proof = """
1. A or B
2. not A
3. not B
_
4. | A
5. | ~ (2, 4)
__
6. | B
7. | ~ (3, 6)
__
8. ~ (1, 4-5, 6-7)
"""
    checker = ProofChecker(proof)
    assert checker.check() is True
