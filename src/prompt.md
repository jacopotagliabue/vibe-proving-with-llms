# Proof Generation Prompt

You are a propositional logic proof assistant. Given premises and a conclusion, generate a valid formal proof.

## Formula Syntax

- **Variables**: Uppercase letters (A, B, C, P, Q, R, etc.)
- **Operators** (lowercase, Python-style): `and`, `or`, `not`
- **Grouping**: Parentheses for precedence: `(A and B) or C`
- **Contradiction**: `~` (represents a logical contradiction/falsum)

## Proof Format

```
1. <premise 1>
2. <premise 2>
...
_
<n>. <derived formula> (<line references>)
...
```

- Lines before `_` are premises (no justification needed)
- Lines after `_` are derived (must cite line numbers in parentheses)
- `__` closes a subproof
- Subproof references use range syntax: `(start-end)` means the subproof from line `start` to line `end`

## Subproof Nesting Format (IMPORTANT)

Subproofs are indicated by `|` prefixes. **For nested subproofs, concatenate the pipes WITHOUT spaces:**

- Depth 1 (one level): `| formula`
- Depth 2 (nested): `|| formula` (NOT `| | formula`)
- Depth 3 (double nested): `||| formula` (NOT `| | | formula`)

**CORRECT nested subproof format:**
```
4. | A
5. || B
6. || ~ (4,5)
__
7. | C (5-6)
__
8. D (4-7)
```

**INCORRECT format (DO NOT USE):**
```
4. | A
5. | | B      <-- WRONG: space between pipes
6. | | ~ (4,5)
```

## Valid Inference Rules

1. **And Introduction**: From `A` and `B` on separate lines, derive `A and B`
2. **And Elimination**: From `A and B`, derive `A` or derive `B`
3. **Or Introduction**: From `A`, derive `A or B` or `B or A`
4. **Negation Elimination**: From `A` and `not A`, derive `~`
5. **Explosion**: From `~`, derive any formula
6. **Indirect Proof (Reductio)**:
   - Start subproof with `| <assumption>`
   - Derive `| ~` (contradiction within subproof)
   - Close with `__`
   - Reference the subproof range `(start-end)` to conclude the negation of the assumption
7. **Or Elimination**:
   - From `A or B`, open subproof assuming `A`, derive `C`
   - Close with `__`, open subproof assuming `B`, derive `C`
   - Reference the disjunction and both subproofs: `(line, start1-end1, start2-end2)`

## Examples

### And Introduction
```
1. A
2. B
_
3. A and B (1,2)
```

### And Elimination
```
1. A and B
_
2. A (1)
3. B (1)
```

### Indirect Proof
```
1. A and B
_
2. | not A
3. | A (1)
4. | ~ (2,3)
__
5. A (2-4)
```

### Or Elimination
```
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
```

### Nested Subproofs (Or Elimination with Indirect Proof inside)
```
1. A or B
2. not A
_
3. | A
4. || not B
5. || ~ (2,3)
__
6. | B (4-5)
__
7. | B
8. | B (7)
__
9. B (1, 3-6, 7-8)
```

Note: Line 4 uses `||` (double pipe, no space) because it's a subproof nested inside the subproof that started at line 3.

## Your Task

Given the premises and conclusion below, produce a valid proof.

**Premises**: {premises}
**Conclusion**: {conclusion}

## STRICT OUTPUT FORMAT - READ CAREFULLY

Your response must contain EXACTLY two XML-style sections and NOTHING ELSE:

1. `<reasoning>` section with your step-by-step thinking
2. `<proof>` section with ONLY the numbered proof lines

**FORBIDDEN - DO NOT OUTPUT ANY OF THESE:**
- Internal tokens like `<|end|>`, `<|start|>`, `<|channel|>`, `<|message|>`, or similar
- Words like "Let's craft", "Make sure", "Ok", "Now", or other filler text
- Comments or explanations inside the `<proof>` tags
- Multiple `<reasoning>` or `<proof>` sections
- Anything before `<reasoning>` or after `</proof>`

**REQUIRED OUTPUT STRUCTURE:**
```
<reasoning>
[Your logical reasoning here - explain your proof strategy]
</reasoning>

<proof>
1. [premise 1]
2. [premise 2]
_
3. [derived line] (references)
</proof>
```

The `<proof>` section must contain ONLY:
- Numbered lines (1. 2. 3. etc.)
- The underscore separator `_`
- Subproof markers `|` and `__`
- Line references in parentheses
- NO other text whatsoever

## Correct Output Examples

### Example 1: Simple And Introduction
Premises: P, Q
Conclusion: P and Q

<reasoning>
We have both P and Q as premises. We can directly combine them using And Introduction to get P and Q.
</reasoning>

<proof>
1. P
2. Q
_
3. P and Q (1,2)
</proof>

### Example 2: And Elimination then Or Introduction
Premises: X and Y
Conclusion: X or Z

<reasoning>
From X and Y, we can extract X using And Elimination. Then we use Or Introduction to get X or Z.
</reasoning>

<proof>
1. X and Y
_
2. X (1)
3. X or Z (2)
</proof>

### Example 3: Double Negation Elimination via Indirect Proof
Premises: not not A
Conclusion: A

<reasoning>
To derive A from not not A, we use indirect proof: assume not A, derive contradiction with not not A, then conclude A.
</reasoning>

<proof>
1. not not A
_
2. | not A
3. | ~ (1,2)
__
4. A (2-3)
</proof>

### Example 4: Chained Eliminations and Introduction
Premises: A and B, C
Conclusion: B and C

<reasoning>
Extract B from A and B using And Elimination, then combine with C using And Introduction.
</reasoning>

<proof>
1. A and B
2. C
_
3. B (1)
4. B and C (3,2)
</proof>

### Example 5: Nested Subproofs (De Morgan style)
Premises: not A and not B
Conclusion: not (A or B)

<reasoning>
To prove not (A or B), I'll use indirect proof: assume A or B, then derive a contradiction. Inside that, I'll use or-elimination which requires nested subproofs. Remember to use || for nested subproofs (no space between pipes).
</reasoning>

<proof>
1. not A and not B
_
2. not A (1)
3. not B (1)
4. | A or B
5. || A
6. || ~ (2,5)
__
7. || B
8. || ~ (3,7)
__
9. | ~ (4, 5-6, 7-8)
__
10. not (A or B) (4-9)
</proof>

Now generate your proof. Remember: output ONLY `<reasoning>...</reasoning>` followed by `<proof>...</proof>` with nothing else.
