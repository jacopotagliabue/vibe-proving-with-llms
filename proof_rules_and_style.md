## Justification Syntax

References in parentheses can be:
- **Single line numbers**: `(1,2,3)` - reference individual lines
- **Subproof ranges**: `(2-4)` - reference a subproof from line 2 to line 4
- **Mixed**: `(1, 2-3, 4-5)` - reference line 1 plus two subproofs

When referencing a subproof `(start-end)`, the proof checker treats it as establishing
the implication: assumption → conclusion (where assumption is the formula at `start`
and conclusion is the formula at `end`).

---

RULE 1: and introduction

1. A
2. B
3. C
_
4. A and B (1,2)
5. (A and B) and C (4,3)

RULE 2: and elimination

1. A and B
_
2. A (1)
3. B (1)

RULE 3: negation elimination

1. not A
2. A
_
3. ~ (1,2)

RULE 4: explosion

1. ~
_
2. A (1)

RULE 5: indirect proof (reductio)

Assume X, derive contradiction (~), conclude `not X`.
The subproof `(start-end)` establishes: `X → ~`, which is equivalent to `not X`.

Example 1: Deriving A from A and B (assume not A, get contradiction)
1. A and B
_
2. | not A
3. | A (1)
4. | ~ (2,3)
__
5. A (2-4)

Example 2: Deriving A from not not A (double negation elimination)
1. not not A
_
2. | not A
3. | ~ (1,2)
__
4. A (2-3)

RULE 6: or introduction

1. A
_
2. A or B (1)

RULE 7: or elimination

From a disjunction `A or B`, if both branches lead to the same conclusion `C`,
we can conclude `C`. References:
- Line 1: the disjunction `A or B`
- Subproof `(4-5)`: establishes `A → C`
- Subproof `(6-7)`: establishes `B → C`

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