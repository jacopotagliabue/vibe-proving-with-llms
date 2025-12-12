"""
Playground script to demonstrate how the ProofChecker works.

Run this script to see the proof checker parse, display, and verify proofs.
"""

from proof_checker import ProofChecker, ProofParseError, InvalidProofError


def check_proof(name: str, proof_string: str, expected: bool) -> bool:
    """
    Parse, display, and verify a proof.

    Returns True if the result matches expected, False otherwise.
    """
    print("=" * 60)
    print(name)
    print("=" * 60)
    print(proof_string)

    checker = ProofChecker(proof_string)
    print("Parsed:")
    print(checker)

    try:
        checker.check()
        result = True
    except InvalidProofError as e:
        result = False
        print(f"Invalid: {e}")

    status = "PASS" if result == expected else "FAIL"
    print(f"Valid: {result} (expected: {expected}) [{status}]")
    print()

    return result == expected


def main():
    # List of (name, proof_string, expected_valid) tuples
    proofs = [
        (
            "And Introduction",
            """
1. A
2. B
3. C
_
4. A and B (1,2)
5. (A and B) and C (4,3)
""",
            True,
        ),
        (
            "Complex Proof",
            """
1. P and Q
2. R
_
3. P (1)
4. Q (1)
5. P and R (3,2)
6. (P and R) and Q (5,4)
""",
            True,
        ),
        (
            "Explosion (from contradiction)",
            """
1. ~
_
2. A (1)
""",
            True,
        ),
        (
            "INVALID: A does not imply A and B",
            """
1. A
_
2. A and B (1)
""",
            False,
        ),
        (
            "Indirect Proof (Reductio ad Absurdum)",
            """
1. A and B
_
2. | not A
3. | A (1)
4. | ~ (2,3)
__
5. A (2-4)
""",
            True,
        ),
        (
            "Or Elimination",
            """
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
""",
            True,
        ),
        (
            "INVALID Or Elimination: branches derive different conclusions",
            """
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
""",
            False,
        ),
    ]

    # Run all proofs
    for name, proof_string, expected in proofs:
        assert check_proof(name, proof_string, expected), f"Proof test failed: {name}"

    # Finally, demonstrate parse error handling
    print("\nError Handling Demo")
    print("-" * 40)

    bad_proof = """
1. A
2. B
3. A and B (1,2)
"""
    print("Proof without '_' separator:")
    try:
        ProofChecker(bad_proof)
        print("  ERROR: Should have raised ProofParseError!")
    except ProofParseError as e:
        print(f"  Caught expected error: {e}")

    return


if __name__ == "__main__":
    main()
