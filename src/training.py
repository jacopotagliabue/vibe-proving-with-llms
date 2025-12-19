"""
RL Training for Proof Generation using Tinker.

Uses reinforcement learning to train an LLM to generate valid propositional
logic proofs. The proof checker provides binary reward (1.0 for valid proofs,
0.0 for invalid).

By default, loads training data from:
  - training_data.jsonl
  - forallx.jsonl
  - lpl_1.jsonl
  - lpl_2.jsonl

Usage:
    uv run python src/training.py
    uv run python src/training.py dataset_paths='["custom.jsonl"]'
"""

import json
import logging
import os
import random
import re
import time
from concurrent.futures import Future
from pathlib import Path

import chz
import tinker
import torch
from dotenv import load_dotenv
from tinker import types
from tinker.types.tensor_data import TensorData

from proof_checker import (
    FormulaError,
    ProofChecker,
    ProofParseError,
    TooManyVariablesError,
    InvalidProofError,
)

# Load environment variables from .env files
load_dotenv(Path(__file__).parent / ".env")

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARN)

# Load the prompt template
PROMPT_TEMPLATE = (Path(__file__).parent / "prompt.md").read_text()


# Default log path - local training_logs folder next to this file
DEFAULT_LOG_PATH = str(Path(__file__).parent / "training_logs")


# Default dataset files
DEFAULT_DATASET_PATHS = [
    str(Path(__file__).parent / "training_data.jsonl"),
    str(Path(__file__).parent / "forallx.jsonl"),
    str(Path(__file__).parent / "lpl_1.jsonl"),
    str(Path(__file__).parent / "lpl_2.jsonl"),
]


def _default_dataset_paths() -> list[str]:
    return list(DEFAULT_DATASET_PATHS)


@chz.chz
class Config:
    """Training configuration."""

    base_url: str | None = None
    log_path: str = DEFAULT_LOG_PATH
    model_name: str = "openai/gpt-oss-20b"
    dataset_paths: list[str] = chz.field(default_factory=_default_dataset_paths)
    batch_size: int = 8
    group_size: int = 4
    learning_rate: float = 1e-5
    lora_rank: int = 32
    save_every: int = 10
    max_tokens: int = 4096
    num_epochs: int = 1
    seed: int = 42  # Random seed for reproducibility


def load_dataset(paths: list[str]) -> list[dict]:
    """Load JSONL datasets with premises and conclusions from multiple files."""
    examples = []
    for path in paths:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    examples.append(json.loads(line))
    return examples


def format_premises(premises: list[str]) -> str:
    """Format premises list as a readable string."""
    return ", ".join(premises)


def build_prompt(premises: list[str], conclusion: str) -> str:
    """Build the full prompt for proof generation."""
    return PROMPT_TEMPLATE.format(
        premises=format_premises(premises),
        conclusion=conclusion,
    )


def verify_proof(proof_text: str, premises: list[str], conclusion: str) -> bool:
    """
    Verify that a generated proof is valid.

    Checks:
    1. Proof parses correctly
    2. Proof premises match expected premises
    3. Proof conclusion matches expected conclusion
    4. All inference steps are valid
    """
    try:
        # Clean up the proof text (remove markdown code blocks if present)
        proof_text = proof_text.strip()
        if proof_text.startswith("```"):
            lines = proof_text.split("\n")
            # Remove first and last lines if they're code fence markers
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            proof_text = "\n".join(lines)

        checker = ProofChecker(proof_text)

        # Check that the proof is valid (raises InvalidProofError if invalid)
        checker.check()

        # Check that premises match
        proof_premises = [line.formula for line in checker.lines if line.is_premise]
        # Normalize for comparison
        expected_premises_normalized = [p.strip() for p in premises]
        proof_premises_normalized = [p.strip() for p in proof_premises]

        if set(expected_premises_normalized) != set(proof_premises_normalized):
            return False

        # Check that conclusion matches
        derived_lines = [line for line in checker.lines if not line.is_premise]
        if not derived_lines:
            return False

        final_conclusion = derived_lines[-1].formula.strip()
        if final_conclusion != conclusion.strip():
            return False

        return True

    except (ProofParseError, FormulaError, TooManyVariablesError, InvalidProofError):
        return False
    except Exception:
        return False


def parse_response(response_text: str) -> tuple[str | None, str | None]:
    """
    Parse the model response to extract reasoning and proof sections.

    Finds the LAST occurrence of <reasoning>...</reasoning> and <proof>...</proof>
    tags, ignoring any garbage text before or after. This handles cases where
    the model outputs internal tokens or multiple attempts before the final answer.

    Returns:
        Tuple of (reasoning, proof) - both None if structure is invalid.
    """
    # Find ALL reasoning and proof matches, take the last valid ones
    reasoning_matches = list(
        re.finditer(r"<reasoning>(.*?)</reasoning>", response_text, re.DOTALL)
    )
    proof_matches = list(re.finditer(r"<proof>(.*?)</proof>", response_text, re.DOTALL))

    if reasoning_matches and proof_matches:
        # Take the last match of each (the final "real" output)
        reasoning = reasoning_matches[-1].group(1).strip()
        proof = proof_matches[-1].group(1).strip()
        return reasoning, proof

    return None, None


def get_reward(
    response_text: str, premises: list[str], conclusion: str
) -> tuple[float, str | None, str | None]:
    """
    Compute reward for a generated response.

    Returns:
        Tuple of (reward, reasoning, proof_text).
        reward is 0.0 if structure is invalid or proof fails verification.
    """
    reasoning, proof_text = parse_response(response_text)

    # If structure is invalid, return 0 reward
    if reasoning is None or proof_text is None:
        return 0.0, None, None

    # Verify the extracted proof
    if verify_proof(proof_text, premises, conclusion):
        return 1.0, reasoning, proof_text

    return 0.0, reasoning, proof_text


def extract_job_id(tinker_path: str) -> str:
    """Extract job ID from a Tinker path like 'tinker://UUID:train:0/weights/...'."""
    # Format: tinker://UUID:train:N/...
    if tinker_path.startswith("tinker://"):
        # Remove 'tinker://' prefix
        path_part = tinker_path[9:]
        # Extract UUID (everything before first ':')
        job_id = path_part.split(":")[0]
        return job_id
    return "unknown"


def main(config: Config):
    """Main training loop."""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Set random seed for reproducibility
    random.seed(config.seed)
    logger.info(f"Random seed set to {config.seed}")

    # Ensure API key is set
    api_key = os.environ.get("TINKER_API_KEY")
    if not api_key:
        raise ValueError(
            "TINKER_API_KEY environment variable not set. "
            "Please set it in src/local.env or environment."
        )

    logger.info(f"Loading dataset from {len(config.dataset_paths)} files...")
    for path in config.dataset_paths:
        logger.info(f"  - {path}")
    dataset = load_dataset(config.dataset_paths)
    logger.info(f"Loaded {len(dataset)} examples total")

    if not dataset:
        raise ValueError(f"No examples found in {config.dataset_paths}")

    # Initialize Tinker client
    service_client = tinker.ServiceClient(base_url=config.base_url)

    # Create training client
    logger.info(f"Creating LoRA training client for {config.model_name}")
    training_client = service_client.create_lora_training_client(
        base_model=config.model_name,
        rank=config.lora_rank,
    )

    # Get job ID from Tinker and create job-specific log directory
    # We need to save initial state to get the job ID
    initial_state_path = training_client.save_state(name="init").result().path
    job_id = extract_job_id(initial_state_path)
    logger.info(f"Tinker job ID: {job_id}")

    # Create job-specific output directory
    job_log_path = Path(config.log_path) / job_id
    job_log_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Saving logs to: {job_log_path}")

    # Get tokenizer from training client (no HuggingFace needed!)
    logger.info("Getting tokenizer from training client...")
    tokenizer = training_client.get_tokenizer()

    # Sampling parameters
    sampling_params = types.SamplingParams(
        max_tokens=config.max_tokens,
        temperature=0.7,
        stop=["</proof>"],  # Stop after closing proof tag
    )

    # Optimizer parameters
    adam_params = types.AdamParams(
        learning_rate=config.learning_rate,
        beta1=0.9,
        beta2=0.95,
        eps=1e-8,
    )

    n_batches = len(dataset) // config.batch_size
    if n_batches == 0:
        n_batches = 1

    logger.info(
        f"Training for {n_batches * config.num_epochs} batches ({config.num_epochs} epochs)"
    )
    logger.info(f"Batch size: {config.batch_size}, Group size: {config.group_size}")

    global_step = 0
    metrics_history = []
    # Save generated proofs to the job-specific folder
    samples_log_path = job_log_path / "generated_proofs.jsonl"
    metrics_path = job_log_path / "metrics.jsonl"

    # Save job info at the start (so we can check config while training)
    job_info_path = job_log_path / "job_info.json"
    job_info = {
        "job_id": job_id,
        "model_name": config.model_name,
        "dataset_paths": config.dataset_paths,
        "num_examples": len(dataset),
        "batch_size": config.batch_size,
        "group_size": config.group_size,
        "learning_rate": config.learning_rate,
        "lora_rank": config.lora_rank,
        "num_epochs": config.num_epochs,
        "seed": config.seed,
        "final_checkpoint": None,  # Will be updated at the end
    }
    with open(job_info_path, "w") as f:
        json.dump(job_info, f, indent=2)
    logger.info(f"Job info saved to {job_info_path}")

    for epoch in range(config.num_epochs):
        # Shuffle dataset at the start of each epoch
        random.shuffle(dataset)
        logger.info(f"=== Epoch {epoch + 1}/{config.num_epochs} (shuffled) ===")

        for batch_idx in range(n_batches):
            t_start = time.time()

            # Save checkpoint periodically
            if (
                config.save_every > 0
                and global_step % config.save_every == 0
                and global_step > 0
            ):
                logger.info(f"Saving checkpoint at step {global_step}")
                state_path = (
                    training_client.save_state(name=f"step_{global_step:06d}")
                    .result()
                    .path
                )
                logger.info(f"Checkpoint saved to {state_path}")

            # Get batch examples
            batch_start = batch_idx * config.batch_size
            batch_end = min((batch_idx + 1) * config.batch_size, len(dataset))
            batch_examples = dataset[batch_start:batch_end]

            # Get sampling client with current weights
            sampling_client = training_client.save_weights_and_get_sampling_client(
                name=f"step_{global_step:06d}"
            )

            training_datums: list[types.Datum] = []
            batch_rewards: list[float] = []
            batch_futures: list[list[Future[types.SampleResponse]]] = []
            batch_prompts: list[list[int]] = []
            batch_metadata: list[dict] = []
            batch_samples: list[dict] = []  # Store generated samples for logging

            # Submit all sampling requests
            for example in batch_examples:
                premises = example["premises"]
                conclusion = example["conclusion"]
                prompt_text = build_prompt(premises, conclusion)

                # Tokenize the prompt
                prompt_tokens = tokenizer.encode(prompt_text, add_special_tokens=True)
                model_input = types.ModelInput.from_ints(tokens=prompt_tokens)

                sample_futures: list[Future[types.SampleResponse]] = []
                for _ in range(config.group_size):
                    sample_futures.append(
                        sampling_client.sample(
                            prompt=model_input,
                            num_samples=1,
                            sampling_params=sampling_params,
                        )
                    )

                batch_futures.append(sample_futures)
                batch_prompts.append(prompt_tokens)
                batch_metadata.append({"premises": premises, "conclusion": conclusion})

            # Collect results and compute rewards
            for sample_futures, prompt_tokens, metadata in zip(
                batch_futures, batch_prompts, batch_metadata
            ):
                group_rewards: list[float] = []
                group_tokens: list[list[int]] = []
                group_logprobs: list[list[float]] = []
                group_ob_lens: list[int] = []

                for sample_idx, future in enumerate(sample_futures):
                    sample_result = future.result()
                    sampled_tokens = sample_result.sequences[0].tokens
                    sampled_logprobs = sample_result.sequences[0].logprobs
                    assert sampled_logprobs is not None

                    all_tokens = prompt_tokens + sampled_tokens
                    group_tokens.append(all_tokens)
                    group_ob_lens.append(len(prompt_tokens) - 1)
                    group_logprobs.append(sampled_logprobs)

                    # Decode generated text and compute reward
                    generated_text = tokenizer.decode(sampled_tokens)
                    reward, reasoning, proof_text = get_reward(
                        generated_text,
                        metadata["premises"],
                        metadata["conclusion"],
                    )
                    group_rewards.append(reward)

                    # Store first sample from each example for logging
                    if sample_idx == 0:
                        batch_samples.append(
                            {
                                "step": global_step,
                                "premises": metadata["premises"],
                                "conclusion": metadata["conclusion"],
                                "raw_response": generated_text,
                                "reasoning": reasoning,
                                "proof": proof_text,
                                "reward": reward,
                                "valid_structure": reasoning is not None,
                            }
                        )

                # Compute advantages (reward - mean)
                mean_reward = (
                    sum(group_rewards) / len(group_rewards) if group_rewards else 0.0
                )
                advantages = [reward - mean_reward for reward in group_rewards]
                batch_rewards.append(mean_reward)

                # Skip if all advantages are zero (no signal to learn from)
                if all(advantage == 0.0 for advantage in advantages):
                    continue

                # Create training datums
                for tokens, logprob, advantage, ob_len in zip(
                    group_tokens, group_logprobs, advantages, group_ob_lens
                ):
                    input_tokens = [int(t) for t in tokens[:-1]]
                    target_tokens = tokens[1:]
                    all_logprobs = [0.0] * ob_len + list(logprob)
                    all_advantages = [0.0] * ob_len + [advantage] * (
                        len(input_tokens) - ob_len
                    )

                    # Ensure lengths match
                    min_len = min(
                        len(input_tokens),
                        len(target_tokens),
                        len(all_logprobs),
                        len(all_advantages),
                    )
                    input_tokens = input_tokens[:min_len]
                    target_tokens = target_tokens[:min_len]
                    all_logprobs = all_logprobs[:min_len]
                    all_advantages = all_advantages[:min_len]

                    datum = types.Datum(
                        model_input=types.ModelInput.from_ints(tokens=input_tokens),
                        loss_fn_inputs={
                            "target_tokens": TensorData.from_torch(
                                torch.tensor(target_tokens)
                            ),
                            "logprobs": TensorData.from_torch(
                                torch.tensor(all_logprobs, dtype=torch.float32)
                            ),
                            "advantages": TensorData.from_torch(
                                torch.tensor(all_advantages, dtype=torch.float32)
                            ),
                        },
                    )
                    training_datums.append(datum)

            # Perform training step if we have data
            if training_datums:
                fwd_bwd_future = training_client.forward_backward(
                    training_datums, loss_fn="importance_sampling"
                )
                optim_step_future = training_client.optim_step(adam_params)
                _fwd_bwd_result = fwd_bwd_future.result()
                _optim_result = optim_step_future.result()

            # Compute metrics
            elapsed = time.time() - t_start
            mean_batch_reward = (
                sum(batch_rewards) / len(batch_rewards) if batch_rewards else 0.0
            )
            success_rate = (
                sum(1 for r in batch_rewards if r > 0) / len(batch_rewards)
                if batch_rewards
                else 0.0
            )

            metrics = {
                "step": global_step,
                "epoch": epoch + 1,
                "batch": batch_idx,
                "reward": mean_batch_reward,
                "success_rate": success_rate,
                "time": elapsed,
                "num_datums": len(training_datums),
            }
            metrics_history.append(metrics)

            # Write metrics incrementally (append mode)
            with open(metrics_path, "a") as f:
                f.write(json.dumps(metrics) + "\n")

            logger.info(
                f"Step {global_step}: reward={mean_batch_reward:.3f}, "
                f"success={success_rate:.1%}, time={elapsed:.1f}s, "
                f"datums={len(training_datums)}"
            )

            # Save samples to file and print example
            with open(samples_log_path, "a") as f:
                for sample in batch_samples:
                    f.write(json.dumps(sample) + "\n")

            # Print one example from this batch
            if batch_samples:
                example = batch_samples[0]
                logger.info(f"--- Example from step {global_step} ---")
                logger.info(f"Premises: {example['premises']}")
                logger.info(f"Conclusion: {example['conclusion']}")
                logger.info(f"Valid structure: {example['valid_structure']}")
                if example["valid_structure"]:
                    logger.info(
                        f"Reasoning: {example['reasoning'][:200] if example['reasoning'] else 'N/A'}..."
                    )
                    logger.info(f"Proof:\n{example['proof']}")
                else:
                    logger.info(
                        f"Raw response (invalid structure):\n{example['raw_response'][:500]}"
                    )
                logger.info(f"Reward: {example['reward']}")
                logger.info("--- End example ---")

            global_step += 1

    # Save final checkpoint
    logger.info("Saving final checkpoint...")
    final_path = training_client.save_state(name="final").result().path
    logger.info(f"Final checkpoint saved to {final_path}")

    # Final weights are already saved via save_state above
    logger.info(f"Final weights available at {final_path}")

    # Metrics already written incrementally, just log the paths
    logger.info(f"Metrics saved to {metrics_path}")
    logger.info(f"Generated proofs saved to {samples_log_path}")

    # Update job info with final checkpoint
    job_info["final_checkpoint"] = final_path
    with open(job_info_path, "w") as f:
        json.dump(job_info, f, indent=2)
    logger.info(f"Job info updated with final checkpoint")

    logger.info("Training completed!")


if __name__ == "__main__":
    chz.nested_entrypoint(main)
