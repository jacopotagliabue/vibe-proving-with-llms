"""
Generate training set of premises-conclusion tuples using an LLM.

Uses litellm to call various LLM providers and generate valid
propositional logic proofs. Each proof is verified using the
ProofChecker before being added to the dataset.

The final dataset contains only premises and conclusions (not the proofs).
"""

import argparse
import json
import random
import litellm
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv

from proof_checker import (
    ProofChecker,
    ProofParseError,
    FormulaError,
    TooManyVariablesError,
    InvalidProofError,
)

# Load environment variables from .env file
load_dotenv()


SYSTEM_PROMPT = """You are an expert in propositional logic proofs. Generate valid proofs in the following syntax:

FORMULA SYNTAX:
- Uppercase letters for variables: A, B, C, P, Q, R, etc.
- Boolean operators (lowercase, Python style): and, or, not
- Parentheses for grouping: (A and B) or C
- Contradiction symbol: ~

PROOF SYNTAX:
- Each line starts with a number followed by a period: 1. 2. 3.
- Premises come first (no justification needed)
- Single underscore _ separates premises from derived lines
- Derived lines must have justification in parentheses: (1,2) means "from lines 1 and 2"
- Subproofs use | prefix: | formula
- Double underscore __ closes a subproof
- Subproof references use range syntax: (start-end) means the subproof from line start to end

VALID INFERENCE RULES:
1. And introduction: from A and B separately, derive A and B
2. And elimination: from A and B, derive A or derive B
3. Or introduction: from A, derive A or B
4. Negation elimination: from A and not A, derive ~ (contradiction)
5. Double negation: not not A is equivalent to A
6. Explosion: from ~, derive anything
7. Indirect proof: assume P, derive ~, reference subproof range (start-end) to conclude not P
8. Or elimination: from A or B, assume A derive C, assume B derive C, reference (line, start1-end1, start2-end2) to conclude C

EXAMPLE PROOFS:

Simple (and introduction):
```
1. A
2. B
_
3. A and B (1,2)
```

Simple (and elimination):
```
1. A and B
_
2. A (1)
3. B (1)
```

Medium (chained elimination and introduction):
```
1. A and B
2. C
_
3. A (1)
4. A and C (3,2)
```

Indirect proof:
```
1. A and B
_
2. | not A
3. | A (1)
4. | ~ (2,3)
__
5. A (2-4)
```

Or elimination:
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

For each proof, output a JSON object with:
- "proof": the complete proof as a string (including premises, _, and derived lines)
- "premises": list of the premise formulas (just the formulas, no line numbers)
- "conclusion": the final derived formula (just the formula)

Generate proofs of varying complexity (2-6 derived lines).
Output one JSON object per line (JSONL format), nothing else."""

USER_PROMPT_SIMPLE = """Generate 3 DIFFERENT SIMPLE valid propositional logic proofs.
Requirements for SIMPLE proofs:
- 2-3 derived lines maximum
- Use only basic rules: and introduction, and elimination, or introduction
- NO subproofs (no indirect proof, no or elimination with subproofs)

IMPORTANT: Each proof must be DISTINCT with different premises and conclusions.
Use varied variable names across proofs (A, B, C, P, Q, R).
Output 3 JSON objects, one per line (JSONL format), nothing else."""

USER_PROMPT_MEDIUM = """Generate 3 DIFFERENT MEDIUM complexity valid propositional logic proofs.
Requirements for MEDIUM proofs:
- 4-5 derived lines
- Use combinations of basic rules: and introduction, and elimination, or introduction, double negation
- May include ONE simple subproof (indirect proof)

IMPORTANT: Each proof must be DISTINCT with different premises and conclusions.
Use varied variable names across proofs (A, B, C, P, Q, R).
Output 3 JSON objects, one per line (JSONL format), nothing else."""

USER_PROMPT_HARD = """Generate 3 DIFFERENT COMPLEX valid propositional logic proofs.
Requirements for COMPLEX proofs:
- 6+ derived lines
- Use advanced rules: indirect proof, or elimination with multiple subproofs
- Include nested subproofs or multiple sequential subproofs

IMPORTANT: Each proof must be DISTINCT with different premises and conclusions.
Use varied variable names across proofs (A, B, C, P, Q, R).
Output 3 JSON objects, one per line (JSONL format), nothing else."""

DIFFICULTY_PROMPTS = {
    "simple": USER_PROMPT_SIMPLE,
    "medium": USER_PROMPT_MEDIUM,
    "hard": USER_PROMPT_HARD,
}


def generate_proofs_batch(model: str, difficulty: str) -> list[dict]:
    """Generate multiple proofs with specified difficulty."""
    prompt = DIFFICULTY_PROMPTS[difficulty]
    examples = []

    try:
        response = litellm.completion(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )

        content = response.choices[0].message.content.strip()
        assert "```" not in content, "Unexpected code block in LLM response"

        # Parse line by line (JSONL format - multiple JSON objects)
        for line in content.split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                example = json.loads(line)
                if (
                    "proof" in example
                    and "premises" in example
                    and "conclusion" in example
                ):
                    example["difficulty"] = difficulty
                    examples.append(example)
            except json.JSONDecodeError:
                continue

    except Exception as e:
        print(f"Error generating proofs: {e}")

    return examples


def generate_proofs_parallel(
    model: str,
    n: int,
    threads: int = 8,
    verbose: bool = False,
    distribution: tuple[int, int, int] = (33, 33, 34),
) -> list[dict]:
    """Generate proofs in parallel using a thread pool.

    Each worker generates ~3 proofs per call, so we need n/3 workers.

    Args:
        distribution: Tuple of (simple, medium, hard) percentages. Must sum to 100.
    """
    examples = []
    # Each call generates ~3 proofs, so we need fewer calls
    num_calls = max(1, (n + 2) // 3)

    difficulties = ["simple", "medium", "hard"]
    weights = list(distribution)

    def worker(task_id: int) -> tuple[int, list[dict]]:
        difficulty = random.choices(difficulties, weights=weights, k=1)[0]
        results = generate_proofs_batch(model, difficulty)
        return task_id, results

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {executor.submit(worker, i): i for i in range(num_calls)}

        completed = 0
        for future in as_completed(futures):
            completed += 1
            task_id, results = future.result()
            if results:
                examples.extend(results)
                if verbose:
                    print(
                        f"[{completed}/{num_calls}] Generated {len(results)} proofs ({results[0].get('difficulty', 'unknown')})"
                    )
            else:
                if verbose:
                    print(f"[{completed}/{num_calls}] Failed to generate proofs")

    return examples


def verify_proof(proof_string: str) -> tuple[bool, int]:
    """Verify a proof using the ProofChecker.

    Returns:
        Tuple of (is_valid, num_steps) where num_steps is the number of derived lines.
    """
    try:
        checker = ProofChecker(proof_string)
        is_valid = checker.check()
        # Count derived lines (non-premise lines)
        num_steps = sum(1 for line in checker.lines if not line.is_premise)
        return is_valid, num_steps
    except (ProofParseError, FormulaError, TooManyVariablesError, InvalidProofError):
        return False, 0


def verify_and_filter_examples(
    examples: list[dict], verbose: bool = False
) -> list[dict]:
    """Verify proofs and return only valid ones with premises, conclusion, num_steps."""
    valid_examples = []
    for i, example in enumerate(examples):
        proof_string = example.get("proof", "")
        is_valid, num_steps = verify_proof(proof_string)

        if verbose:
            status = "VALID" if is_valid else "INVALID"
            print(f"\n[{i + 1}] {status} ({num_steps} steps)")
            print(f"Proof:\n{proof_string}")
            print(f"Premises: {example.get('premises')}")
            print(f"Conclusion: {example.get('conclusion')}")

        if is_valid:
            valid_examples.append(
                {
                    "premises": example["premises"],
                    "conclusion": example["conclusion"],
                    "num_steps": num_steps,
                }
            )

    return valid_examples


def load_existing_examples(output_path: Path) -> list[dict]:
    """Load existing examples from a JSONL file."""
    if not output_path.exists():
        return []

    with open(output_path) as f:
        return [json.loads(line) for line in f if line.strip()]


def deduplicate_examples(examples: list[dict]) -> list[dict]:
    """Deduplicate examples by (premises, conclusion) tuple."""
    seen = set()
    unique_examples = []
    for ex in examples:
        key = (tuple(sorted(ex["premises"])), ex["conclusion"])
        if key not in seen:
            seen.add(key)
            unique_examples.append(ex)
    return unique_examples


def save_examples(examples: list[dict], output_path: Path) -> None:
    """Save examples to a JSONL file."""
    with open(output_path, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")


def print_step_distribution(examples: list[dict]) -> None:
    """Print the distribution of proof steps."""
    if not examples:
        return

    steps = [ex.get("num_steps", 0) for ex in examples]
    step_counts = Counter(steps)
    print("\nStep distribution:")
    for n_steps in sorted(step_counts.keys()):
        count = step_counts[n_steps]
        print(f"  {n_steps} steps: {count} examples ({100 * count / len(examples):.1f}%)")


def generate_batch(
    model: str,
    n: int,
    threads: int,
    verbose: bool,
    distribution: tuple[int, int, int],
) -> list[dict]:
    """Generate a single batch of proofs, verify them, and return valid examples."""
    print(f"Generating {n} proofs using {model} with {threads} threads...")
    print(
        f"Difficulty distribution: simple={distribution[0]}%, medium={distribution[1]}%, hard={distribution[2]}%"
    )

    examples = generate_proofs_parallel(
        model=model,
        n=n,
        threads=threads,
        verbose=verbose,
        distribution=distribution,
    )

    print(f"Received {len(examples)} examples from LLM")

    valid_examples = verify_and_filter_examples(examples, verbose=verbose)
    print(f"Verified: {len(valid_examples)}/{len(examples)} proofs passed")

    return valid_examples


def main(
    model: str,
    n: int,
    batches: int,
    threads: int,
    output: str,
    verbose: bool,
    distribution: tuple[int, int, int],
) -> list[dict]:
    """Main function to generate training data across multiple batches.

    Returns:
        List of all unique examples (including previously existing ones).
    """
    output_path = Path(output)

    # Load existing examples
    existing_examples = load_existing_examples(output_path)
    initial_count = len(existing_examples)
    if initial_count > 0:
        print(f"Loaded {initial_count} existing examples from {output}")

    all_examples = list(existing_examples)

    # Generate batches
    for batch in range(batches):
        print(f"\n=== Batch {batch + 1}/{batches} ===")
        batch_examples = generate_batch(
            model=model,
            n=n,
            threads=threads,
            verbose=verbose,
            distribution=distribution,
        )
        all_examples.extend(batch_examples)

    # Deduplicate and save
    unique_examples = deduplicate_examples(all_examples)
    save_examples(unique_examples, output_path)

    # Print summary
    print("\n=== Final Dataset ===")
    new_count = len(unique_examples) - initial_count
    print(f"Previously: {initial_count} examples")
    print(f"Added: {new_count} new unique examples")
    print(f"Total unique examples: {len(unique_examples)}")

    print_step_distribution(unique_examples)

    return unique_examples

    
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate training dataset for proof generation"
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-20250514",
        help="Model to use for generation",
    )
    parser.add_argument(
        "--n", type=int, default=30, help="Number of proofs to generate per batch"
    )
    parser.add_argument(
        "--batches", type=int, default=5, help="Number of batches to generate"
    )
    parser.add_argument(
        "--threads", type=int, default=8, help="Number of threads in worker pool"
    )
    parser.add_argument(
        "--output", default="training_data.jsonl", help="Output file path"
    )
    parser.add_argument("--verbose", action="store_true", help="Print each proof")
    parser.add_argument(
        "--distribution",
        type=str,
        default="33/33/34",
        help="Difficulty distribution as 'simple/medium/hard' percentages (must sum to 100)",
    )

    args = parser.parse_args()

    try:
        parts = args.distribution.split("/")
        assert len(parts) == 3
        distribution = tuple(int(x) for x in parts)
        assert sum(distribution) == 100
    except ValueError:
        raise ValueError("Distribution values must be THREE integers and sum to 100")

    main(
        model=args.model,
        n=args.n,
        batches=args.batches,
        threads=args.threads,
        output=args.output,
        verbose=args.verbose,
        distribution=distribution,
    )
