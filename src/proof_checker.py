"""
Proof Checker for propositional logic proofs.

Proofs follow a simple format:
- Lines before '_' are premises
- Lines after '_' are derived statements
- Each line has: number. formula (optional: comma-separated line references)

Example proof (and introduction):
    1. A
    2. B
    3. C
    _
    4. A and B (1,2)
    5. (A and B) and C (4,3)
"""

import re
from dataclasses import dataclass
from itertools import product


@dataclass
class SubproofRef:
    """Represents a reference to a subproof (start-end range)."""

    start: int
    end: int


@dataclass
class SubproofInfo:
    """Information about a subproof's structure."""

    id: int
    start_line: int
    end_line: int | None  # None if not yet closed
    depth: int
    parent_id: int | None  # None for top-level subproofs (parent is main proof)


@dataclass
class ProofLine:
    """Represents a single line in a proof."""

    line_number: int
    formula: str
    justification_lines: list[int]  # single line references, empty for premises
    justification_subproofs: list[SubproofRef]  # subproof references (start-end)
    is_premise: bool
    subproof_depth: int = 0  # 0 = main proof, 1 = one | prefix, 2 = || prefix, etc.
    subproof_id: int = 0  # unique ID for each subproof (0 = main proof)


class ProofParseError(Exception):
    """Raised when a proof cannot be parsed."""

    pass


class FormulaError(Exception):
    """Raised when a formula is invalid."""

    pass


class TooManyVariablesError(Exception):
    """Raised when a proof contains more than the maximum allowed variables."""

    pass


class InvalidProofError(Exception):
    """Raised when a proof step is invalid."""

    def __init__(self, message: str, line_number: int, justification_lines: list[int]):
        self.line_number = line_number
        self.justification_lines = justification_lines
        super().__init__(message)


MAX_VARIABLES = 8


class ProofChecker:
    """
    Checks propositional logic proofs.

    At init, parses the proof string into a structured representation.
    The check() method verifies each line follows from its justification.
    """

    def __init__(self, proof_string: str):
        """
        Initialize the checker with a proof string.

        Args:
            proof_string: Multi-line proof following the format in proof_rules_and_style.md
        """
        self.proof_string = proof_string
        self.lines: list[ProofLine] = []
        self.subproofs: dict[int, SubproofInfo] = {}  # subproof_id -> SubproofInfo
        self._parse()

    def _parse(self) -> None:
        """
        Parse the proof string into structured ProofLine objects.

        The proof format is:
        - Lines before '_' are premises (no justification needed)
        - Lines after '_' are derived (must have justification in parentheses)
        - '__' marks the end of a subproof
        - Each line: number. formula (line_refs)
        """
        raw_lines = self.proof_string.strip().split("\n")

        # Find the separator '_'
        separator_idx = None
        for i, line in enumerate(raw_lines):
            if line.strip() == "_":
                separator_idx = i
                break

        if separator_idx is None:
            raise ProofParseError(
                "Proof must contain '_' separator between premises and derivations"
            )

        # Parse premises (before separator)
        for line in raw_lines[:separator_idx]:
            if line.strip():  # skip empty lines
                parsed = self._parse_line(line, is_premise=True)
                self.lines.append(parsed)

        # Parse derived lines (after separator)
        # Track subproof structure properly for scoping rules
        next_subproof_id = 1  # 0 is reserved for main proof
        # Stack of currently open subproofs: list of (subproof_id, depth)
        open_subproof_stack: list[int] = []  # stack of subproof IDs
        # Track current subproof ID for each depth level
        current_subproof_at_depth: dict[int, int] = {}
        # Track if we just closed a subproof at each depth (need new ID for next one)
        closed_at_depth: set[int] = set()

        for line in raw_lines[separator_idx + 1 :]:
            stripped = line.strip()
            if not stripped:
                continue  # skip empty lines
            if stripped == "__":
                # Close the current subproof at the highest depth
                if self.lines:
                    last_line = self.lines[-1]
                    if last_line.subproof_depth > 0:
                        depth = last_line.subproof_depth
                        closed_at_depth.add(depth)
                        # Close the subproof in our tracking structure
                        if depth in current_subproof_at_depth:
                            sp_id = current_subproof_at_depth[depth]
                            if sp_id in self.subproofs:
                                self.subproofs[sp_id].end_line = last_line.line_number
                            # Remove from open stack
                            if open_subproof_stack and open_subproof_stack[-1] == sp_id:
                                open_subproof_stack.pop()
                continue

            parsed = self._parse_line(line, is_premise=False)

            # Assign subproof ID and track subproof structure
            if parsed.subproof_depth == 0:
                parsed.subproof_id = 0
            else:
                depth = parsed.subproof_depth
                # Check if we need a new subproof ID at this depth
                if depth in closed_at_depth or depth not in current_subproof_at_depth:
                    # Starting a new subproof
                    new_id = next_subproof_id
                    next_subproof_id += 1
                    current_subproof_at_depth[depth] = new_id
                    closed_at_depth.discard(depth)

                    # Determine parent: the subproof at depth-1, or None if depth==1
                    parent_id = None
                    if depth > 1 and (depth - 1) in current_subproof_at_depth:
                        parent_id = current_subproof_at_depth[depth - 1]

                    # Create subproof info
                    self.subproofs[new_id] = SubproofInfo(
                        id=new_id,
                        start_line=parsed.line_number,
                        end_line=None,  # Not closed yet
                        depth=depth,
                        parent_id=parent_id,
                    )
                    open_subproof_stack.append(new_id)

                parsed.subproof_id = current_subproof_at_depth[depth]

            self.lines.append(parsed)

        # Must have at least one derived line
        derived_lines = [ln for ln in self.lines if not ln.is_premise]
        if not derived_lines:
            raise ProofParseError("Proof must have at least one derived line after '_'")

        # Check total number of variables in the proof
        all_variables = set()
        for line in self.lines:
            all_variables.update(self._extract_variables(line.formula))
        if len(all_variables) > MAX_VARIABLES:
            raise TooManyVariablesError(
                f"Proof contains {len(all_variables)} variables, maximum allowed is {MAX_VARIABLES}"
            )

    def _parse_line(self, line: str, is_premise: bool) -> ProofLine:
        """
        Parse a single proof line.

        Format: number. [|*] formula (optional: refs)

        References can be:
            - Single line numbers: (1,2,3)
            - Subproof ranges: (2-4) meaning subproof from line 2 to 4
            - Mixed: (1, 2-4, 5-7) meaning line 1 plus two subproofs

        Examples:
            "1. A"
            "4. A and B (1,2)"
            "5. (A and B) and C (4,3)"
            "2. | not A"           (subproof depth 1)
            "3. || A and B (1,2)"  (subproof depth 2)
            "5. A (2-4)"           (conclusion from subproof 2-4)
            "6. C (1, 2-3, 4-5)"   (or-elimination with disjunction and two subproofs)
        """
        line = line.strip()

        # Match line number at start: "number."
        match = re.match(r"^(\d+)\.\s*", line)
        if not match:
            raise ProofParseError(f"Line must start with 'number. ': {line}")

        line_number = int(match.group(1))
        rest = line[match.end() :]

        # Check for subproof depth indicator (one or more | characters)
        subproof_depth = 0
        depth_match = re.match(r"^(\|+)\s*", rest)
        if depth_match:
            subproof_depth = len(depth_match.group(1))
            rest = rest[depth_match.end() :]

        # Extract justification references if present (at the end in parentheses)
        # Must be careful: formula itself can contain parentheses like "(A and B)"
        # Justification is always at the END and contains numbers, commas, and dashes
        justification_lines = []
        justification_subproofs = []
        formula = rest

        if not is_premise:
            # Look for justification pattern at end: (ref, ref, ...) where ref is number or number-number
            # Pattern matches: single numbers like "1" or ranges like "2-4"
            just_match = re.search(
                r"\((\s*\d+(?:\s*-\s*\d+)?(?:\s*,\s*\d+(?:\s*-\s*\d+)?)*\s*)\)\s*$",
                rest,
            )
            if just_match:
                refs_str = just_match.group(1)
                # Parse each reference (either single number or range)
                for ref in refs_str.split(","):
                    ref = ref.strip()
                    if "-" in ref:
                        # Subproof range: "2-4"
                        parts = ref.split("-")
                        start = int(parts[0].strip())
                        end = int(parts[1].strip())
                        justification_subproofs.append(
                            SubproofRef(start=start, end=end)
                        )
                    else:
                        # Single line reference
                        justification_lines.append(int(ref))
                formula = rest[: just_match.start()].strip()
            # No justification is allowed for subproof assumptions (first line of a subproof)
            # These are like premises within the subproof
            elif subproof_depth == 0:
                raise ProofParseError(
                    f"Derived line must have justification (line refs): {line}"
                )
            else:
                # Subproof line without justification - this is a subproof assumption
                formula = rest.strip()

        # Validate formula syntax
        self._validate_formula(formula)

        return ProofLine(
            line_number=line_number,
            formula=formula,
            justification_lines=justification_lines,
            justification_subproofs=justification_subproofs,
            is_premise=is_premise,
            subproof_depth=subproof_depth,
        )

    def _validate_formula(self, formula: str) -> None:
        """
        Validate that a formula contains only allowed tokens.

        Allowed:
        - Upper case letters for sentence variables (A-Z)
        - Lowercase boolean operators: and, or, not
        - Parentheses: ( )
        - Contradiction symbol: ~
        - Whitespace (normalized)
        """
        # Normalize whitespace
        normalized = " ".join(formula.split())

        if not normalized:
            raise FormulaError("Formula cannot be empty")

        # Special case: contradiction symbol alone
        if normalized == "~":
            return

        # Tokenize: split into words and parentheses
        # Pattern: words (and, or, not, A, B, etc.) or single parens
        tokens = re.findall(r"[A-Za-z]+|[()]", normalized)

        # Rebuild and compare to catch invalid characters
        rebuilt = "".join(tokens)
        stripped = normalized.replace(" ", "")
        if rebuilt != stripped:
            raise FormulaError(f"Formula contains invalid characters: {formula}")

        # Check each token
        allowed_operators = {"and", "or", "not"}
        reserved_words = {"AND", "OR", "NOT"}  # Uppercase versions are not allowed
        for token in tokens:
            if token in "()":
                continue
            if token in allowed_operators:
                continue
            if token in reserved_words:
                raise FormulaError(
                    f"Invalid token '{token}' in formula: {formula} (use lowercase '{token.lower()}')"
                )
            # Must be an uppercase variable (single or multiple letters)
            if token.isupper():
                continue
            raise FormulaError(f"Invalid token '{token}' in formula: {formula}")

    def check(self) -> bool:
        """
        Check if the proof is valid.

        For each derived line, verify it follows from its justification
        using truth table evaluation: the conclusion must be true whenever
        all premises are true.

        Justifications can be:
        - Single line references: the formula of that line is used directly
        - Subproof references (start-end): converted to an implication
          (assumption → conclusion), represented as (not assumption or conclusion)

        Returns True if valid.
        Raises InvalidProofError if any step is invalid.
        """
        for line in self.lines:
            if line.is_premise:
                continue

            # Subproof assumptions (first line of subproof, no justification) are valid by definition
            if (
                line.subproof_depth > 0
                and not line.justification_lines
                and not line.justification_subproofs
            ):
                continue

            # Build the list of effective premises (formulas to check against)
            effective_premises = []
            all_refs = []  # for error messages

            # Process single line references
            for ln in line.justification_lines:
                premise = self.get_line(ln)
                if premise is None:
                    raise InvalidProofError(
                        f"Line {line.line_number}: Referenced line {ln} does not exist",
                        line_number=line.line_number,
                        justification_lines=line.justification_lines,
                    )
                # Check accessibility (scoping rules)
                if not self._is_line_accessible(premise, line):
                    raise InvalidProofError(
                        f"Line {line.line_number}: Referenced line {ln} is not accessible "
                        f"(it is inside a closed subproof)",
                        line_number=line.line_number,
                        justification_lines=line.justification_lines,
                    )
                effective_premises.append(premise.formula)
                all_refs.append(str(ln))

            # Process subproof references - convert to implications
            for subproof_ref in line.justification_subproofs:
                assumption_line = self.get_line(subproof_ref.start)
                conclusion_line = self.get_line(subproof_ref.end)

                if assumption_line is None:
                    raise InvalidProofError(
                        f"Line {line.line_number}: Subproof start line {subproof_ref.start} does not exist",
                        line_number=line.line_number,
                        justification_lines=line.justification_lines,
                    )
                if conclusion_line is None:
                    raise InvalidProofError(
                        f"Line {line.line_number}: Subproof end line {subproof_ref.end} does not exist",
                        line_number=line.line_number,
                        justification_lines=line.justification_lines,
                    )

                # Validate that assumption_line is actually a subproof assumption
                if assumption_line.subproof_depth == 0:
                    raise InvalidProofError(
                        f"Line {line.line_number}: Line {subproof_ref.start} is not a subproof assumption",
                        line_number=line.line_number,
                        justification_lines=line.justification_lines,
                    )

                # Check subproof accessibility (scoping rules)
                accessible, error_msg = self._is_subproof_accessible(subproof_ref, line)
                if not accessible:
                    raise InvalidProofError(
                        f"Line {line.line_number}: Subproof {subproof_ref.start}-{subproof_ref.end} "
                        f"is not accessible: {error_msg}",
                        line_number=line.line_number,
                        justification_lines=line.justification_lines,
                    )

                # Build implication: assumption → conclusion
                # Represented as: (not assumption) or conclusion
                assumption = assumption_line.formula
                conclusion = conclusion_line.formula

                # Handle special case: if conclusion is contradiction (~),
                # the implication "A → ~" is equivalent to "not A"
                if conclusion.strip() == "~":
                    implication = f"not ({assumption})"
                else:
                    implication = f"(not ({assumption}) or ({conclusion}))"

                effective_premises.append(implication)
                all_refs.append(f"{subproof_ref.start}-{subproof_ref.end}")

            # Check if conclusion follows from effective premises
            if not self._check_entailment(effective_premises, line.formula):
                raise InvalidProofError(
                    f"Line {line.line_number}: '{line.formula}' does not follow from "
                    f"references ({', '.join(all_refs)})",
                    line_number=line.line_number,
                    justification_lines=line.justification_lines,
                )

        return True

    def _check_entailment(self, premises: list[str], conclusion: str) -> bool:
        """
        Check if conclusion follows from premises using truth table evaluation.

        The conclusion follows if: whenever all premises are True, conclusion is True.

        Args:
            premises: List of formula strings
            conclusion: The conclusion formula string
        """
        # Collect all variables from premises and conclusion
        variables = set()
        for formula in premises:
            variables.update(self._extract_variables(formula))
        variables.update(self._extract_variables(conclusion))

        variables = sorted(variables)  # Sort for consistent ordering

        # Handle case with no variables (e.g., just contradiction ~)
        if not variables:
            premise_values = [self._eval_formula(p, {}) for p in premises]
            if all(premise_values):
                return self._eval_formula(conclusion, {})
            return True  # Vacuously true if premises are false

        # Generate all truth assignments
        for assignment in product([False, True], repeat=len(variables)):
            var_assignment = dict(zip(variables, assignment))

            # Evaluate all premises
            premise_values = [self._eval_formula(p, var_assignment) for p in premises]

            # If all premises are True, conclusion must be True
            if all(premise_values):
                conclusion_value = self._eval_formula(conclusion, var_assignment)
                if not conclusion_value:
                    return False

        return True

    def _extract_variables(self, formula: str) -> set[str]:
        """Extract all uppercase variables from a formula."""
        tokens = re.findall(r"[A-Z]+", formula)
        return set(tokens)

    def _eval_formula(self, formula: str, assignment: dict[str, bool]) -> bool:
        """
        Evaluate a formula given a truth assignment.

        Uses Python's eval with the assignment as local variables.
        """
        # Contradiction is always False
        if formula.strip() == "~":
            return False

        # The formula uses 'and', 'or', 'not' which are Python keywords
        # We just need to substitute variable values
        return eval(formula, {"__builtins__": {}}, assignment)

    def get_line(self, line_number: int) -> ProofLine | None:
        """Get a proof line by its number."""
        for line in self.lines:
            if line.line_number == line_number:
                return line
        return None

    def _is_subproof_ancestor(
        self, potential_ancestor_id: int, descendant_id: int
    ) -> bool:
        """Check if potential_ancestor_id is an ancestor of descendant_id in the subproof tree."""
        if potential_ancestor_id == descendant_id:
            return True
        current_id = descendant_id
        while current_id in self.subproofs:
            parent = self.subproofs[current_id].parent_id
            if parent is None:
                return False
            if parent == potential_ancestor_id:
                return True
            current_id = parent
        return False

    def _is_line_accessible(self, ref_line: ProofLine, from_line: ProofLine) -> bool:
        """
        Check if ref_line is accessible from from_line.

        Rules for individual line citations:
        1. The line must come before the line where the rule is applied
        2. The line must not occur within a subproof that has been closed before
           the line where the rule is applied

        A line is accessible if:
        - It is a premise (always accessible), OR
        - It is in the main proof (subproof_id == 0), OR
        - It is in the same subproof as from_line, OR
        - It is in an ancestor subproof of from_line's subproof
        """
        # Rule 1: Referenced line must come before the current line
        if ref_line.line_number >= from_line.line_number:
            return False

        # Premises are always accessible
        if ref_line.is_premise:
            return True

        # Lines in main proof (depth 0) are always accessible from any line
        if ref_line.subproof_depth == 0:
            return True

        # If from_line is in main proof (depth 0), it cannot access lines in any subproof
        # (because by definition, any subproof before this line must be closed)
        if from_line.subproof_depth == 0:
            # ref_line is in a subproof (checked above), so it's not accessible
            return False

        # Both lines are in subproofs
        ref_subproof_id = ref_line.subproof_id
        from_subproof_id = from_line.subproof_id

        # Same subproof: accessible
        if ref_subproof_id == from_subproof_id:
            return True

        # Check if ref_line's subproof is an ancestor of from_line's subproof
        if self._is_subproof_ancestor(ref_subproof_id, from_subproof_id):
            return True

        # Check if ref_line's subproof has been closed before from_line
        if ref_subproof_id in self.subproofs:
            ref_subproof = self.subproofs[ref_subproof_id]
            if (
                ref_subproof.end_line is not None
                and ref_subproof.end_line < from_line.line_number
            ):
                # Subproof is closed, and from_line is not in it or a descendant
                return False

        return False

    def _is_subproof_accessible(
        self, subproof_ref: SubproofRef, from_line: ProofLine
    ) -> tuple[bool, str]:
        """
        Check if a subproof reference is accessible from from_line.

        Rules for subproof citations:
        1. The cited subproof must come entirely before the application of the rule
        2. The cited subproof must not lie within some other closed subproof
           which is closed at the line it is cited
        3. The last line of the cited subproof must not occur inside a nested subproof

        Returns (is_accessible, error_message) tuple.
        """
        start_line = self.get_line(subproof_ref.start)
        end_line = self.get_line(subproof_ref.end)

        if start_line is None or end_line is None:
            return False, "Subproof lines do not exist"

        # Rule 1: Subproof must come entirely before the current line
        if subproof_ref.end >= from_line.line_number:
            return False, "Subproof must end before the line citing it"

        # The start line must be a subproof assumption (has depth > 0)
        if start_line.subproof_depth == 0:
            return False, f"Line {subproof_ref.start} is not a subproof assumption"

        # Rule 3: The end line must be at the same depth as the start line
        # (not nested deeper inside another subproof)
        if end_line.subproof_depth != start_line.subproof_depth:
            return (
                False,
                f"Subproof end line {subproof_ref.end} is at depth {end_line.subproof_depth}, "
                f"but start line is at depth {start_line.subproof_depth}",
            )

        # Verify start and end are in the same subproof
        if start_line.subproof_id != end_line.subproof_id:
            return (
                False,
                f"Lines {subproof_ref.start} and {subproof_ref.end} are not in the same subproof",
            )

        # Rule 2: The cited subproof must not lie within another closed subproof
        # at the point where it's cited
        cited_subproof_id = start_line.subproof_id
        if cited_subproof_id in self.subproofs:
            cited_subproof = self.subproofs[cited_subproof_id]

            # Check if from_line is in main proof
            if from_line.subproof_depth == 0:
                # The cited subproof must be a top-level subproof (parent_id is None)
                if cited_subproof.parent_id is not None:
                    return (
                        False,
                        f"Subproof {subproof_ref.start}-{subproof_ref.end} is nested inside "
                        "another subproof and cannot be cited from main proof",
                    )
            else:
                # from_line is in a subproof
                # The cited subproof must either:
                # - Be a sibling subproof (same parent) at the same depth, OR
                # - Be a direct child subproof that was closed
                from_subproof_id = from_line.subproof_id
                from_subproof = self.subproofs.get(from_subproof_id)

                if from_subproof is not None:
                    # Check if they share the same parent (siblings)
                    # or if cited is a child of an ancestor
                    if cited_subproof.parent_id != from_subproof.parent_id:
                        # Not siblings - check if cited is accessible through ancestry
                        if not self._is_subproof_ancestor(
                            cited_subproof.parent_id
                            if cited_subproof.parent_id
                            else -1,
                            from_subproof_id,
                        ):
                            # Check for parent-child relationship
                            if cited_subproof.parent_id != from_subproof_id:
                                return (
                                    False,
                                    f"Subproof {subproof_ref.start}-{subproof_ref.end} is not "
                                    "accessible from current scope",
                                )

        return True, ""

    def __repr__(self) -> str:
        def format_refs(ln: ProofLine) -> str:
            """Format justification references for display."""
            refs = []
            refs.extend(str(line_num) for line_num in ln.justification_lines)
            refs.extend(f"{sp.start}-{sp.end}" for sp in ln.justification_subproofs)
            if refs:
                return f" ({', '.join(refs)})"
            return ""

        lines_repr = "\n".join(
            f"  {ln.line_number}. "
            + ("|" * ln.subproof_depth + " " if ln.subproof_depth > 0 else "")
            + ln.formula
            + format_refs(ln)
            + (" [premise]" if ln.is_premise else "")
            for ln in self.lines
        )
        return f"ProofChecker(\n{lines_repr}\n)"
