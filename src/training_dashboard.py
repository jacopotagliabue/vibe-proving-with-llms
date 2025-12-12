"""
Streamlit dashboard for visualizing proof training progress.

Run with: uv run streamlit run src/training_dashboard.py
"""

import json
import random
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.express as px

# Paths to log files
LOG_DIR = Path(__file__).parent / "training_logs"


def get_available_jobs() -> list[str]:
    """Get list of available job IDs (subdirectories in training_logs)."""
    if not LOG_DIR.exists():
        return []

    jobs = []
    for item in LOG_DIR.iterdir():
        if item.is_dir():
            # Check if it has metrics or proofs files
            if (item / "metrics.jsonl").exists() or (
                item / "generated_proofs.jsonl"
            ).exists():
                jobs.append(item.name)

    # Sort by modification time (most recent first)
    jobs.sort(key=lambda x: (LOG_DIR / x).stat().st_mtime, reverse=True)
    return jobs


def load_job_info(job_id: str) -> dict:
    """Load job info if available."""
    job_info_path = LOG_DIR / job_id / "job_info.json"
    if job_info_path.exists():
        with open(job_info_path) as f:
            return json.load(f)
    return {}


def load_metrics(job_id: str) -> pd.DataFrame:
    """Load training metrics from JSONL file for a specific job."""
    metrics_path = LOG_DIR / job_id / "metrics.jsonl"
    if not metrics_path.exists():
        return pd.DataFrame()

    metrics = []
    with open(metrics_path) as f:
        for line in f:
            if line.strip():
                metrics.append(json.loads(line))

    if not metrics:
        return pd.DataFrame()

    return pd.DataFrame(metrics)


def load_proofs(job_id: str) -> list[dict]:
    """Load generated proofs from JSONL file for a specific job."""
    proofs_path = LOG_DIR / job_id / "generated_proofs.jsonl"
    if not proofs_path.exists():
        return []

    proofs = []
    with open(proofs_path) as f:
        for line in f:
            if line.strip():
                proofs.append(json.loads(line))

    return proofs


def main():
    st.set_page_config(
        page_title="Proof Training Dashboard",
        page_icon="🧠",
        layout="wide",
    )

    st.title("🧠 Proof Training Dashboard")

    # Get available jobs
    available_jobs = get_available_jobs()

    if not available_jobs:
        st.warning("No training jobs found. Run training first to generate logs.")
        st.info(f"Expected log directory: `{LOG_DIR}`")
        return

    # Job selector in sidebar
    st.sidebar.header("Select Training Job")

    # Create display labels with job info
    job_labels = {}
    for job_id in available_jobs:
        job_info = load_job_info(job_id)
        if job_info:
            model = job_info.get("model_name", "unknown").split("/")[-1]
            num_examples = job_info.get("num_examples", "?")
            epochs = job_info.get("num_epochs", "?")
            label = f"{job_id[:8]}... ({model}, {num_examples} ex, {epochs} ep)"
        else:
            label = f"{job_id[:8]}..."
        job_labels[job_id] = label

    selected_job = st.sidebar.selectbox(
        "Training Job:",
        available_jobs,
        format_func=lambda x: job_labels.get(x, x),
    )

    # Show job info in sidebar
    job_info = load_job_info(selected_job)
    if job_info:
        st.sidebar.divider()
        st.sidebar.subheader("Job Details")
        st.sidebar.markdown(f"**Model:** `{job_info.get('model_name', 'N/A')}`")
        st.sidebar.markdown(f"**Examples:** {job_info.get('num_examples', 'N/A')}")
        st.sidebar.markdown(f"**Batch Size:** {job_info.get('batch_size', 'N/A')}")
        st.sidebar.markdown(f"**Epochs:** {job_info.get('num_epochs', 'N/A')}")
        st.sidebar.markdown(
            f"**Learning Rate:** {job_info.get('learning_rate', 'N/A')}"
        )
        st.sidebar.markdown(f"**LoRA Rank:** {job_info.get('lora_rank', 'N/A')}")

        if job_info.get("final_checkpoint"):
            st.sidebar.divider()
            st.sidebar.markdown("**Final Checkpoint:**")
            st.sidebar.code(job_info["final_checkpoint"], language=None)

    # Load data for selected job
    metrics_df = load_metrics(selected_job)
    proofs = load_proofs(selected_job)

    if metrics_df.empty and not proofs:
        st.warning(f"No data found for job {selected_job}")
        return

    # Create tabs
    tab1, tab2 = st.tabs(["📊 Training Progress", "🔍 Proof Explorer"])

    # Tab 1: Training Progress Charts
    with tab1:
        if not metrics_df.empty:
            st.header("Training Metrics Over Time")

            col1, col2 = st.columns(2)

            with col1:
                # Success rate over steps
                fig_success = px.line(
                    metrics_df,
                    x="step",
                    y="success_rate",
                    title="Success Rate Over Training Steps",
                    labels={"step": "Training Step", "success_rate": "Success Rate"},
                )
                fig_success.update_traces(line=dict(color="#00CC96", width=2))
                fig_success.update_layout(yaxis_tickformat=".0%")
                st.plotly_chart(fig_success, use_container_width=True)

            with col2:
                # Reward over steps
                fig_reward = px.line(
                    metrics_df,
                    x="step",
                    y="reward",
                    title="Average Reward Over Training Steps",
                    labels={"step": "Training Step", "reward": "Average Reward"},
                )
                fig_reward.update_traces(line=dict(color="#636EFA", width=2))
                st.plotly_chart(fig_reward, use_container_width=True)

            # Summary stats
            st.subheader("Summary Statistics")
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric(
                    "Total Steps",
                    len(metrics_df),
                )
            with col2:
                st.metric(
                    "Best Success Rate",
                    f"{metrics_df['success_rate'].max():.1%}",
                )
            with col3:
                st.metric(
                    "Final Success Rate",
                    f"{metrics_df['success_rate'].iloc[-1]:.1%}"
                    if len(metrics_df) > 0
                    else "N/A",
                )
            with col4:
                st.metric(
                    "Avg Time/Step",
                    f"{metrics_df['time'].mean():.1f}s"
                    if "time" in metrics_df.columns
                    else "N/A",
                )

            # Epoch breakdown
            if "epoch" in metrics_df.columns:
                st.subheader("Performance by Epoch")
                epoch_stats = (
                    metrics_df.groupby("epoch")
                    .agg(
                        {
                            "success_rate": ["mean", "max"],
                            "reward": ["mean", "max"],
                        }
                    )
                    .round(3)
                )
                epoch_stats.columns = [
                    "Avg Success Rate",
                    "Max Success Rate",
                    "Avg Reward",
                    "Max Reward",
                ]
                st.dataframe(epoch_stats, use_container_width=True)
        else:
            st.info("No metrics data available yet.")

    # Tab 2: Proof Explorer
    with tab2:
        if proofs:
            st.header("Generated Proofs Explorer")

            # Stats
            total_proofs = len(proofs)
            valid_structure = sum(1 for p in proofs if p.get("valid_structure", False))
            rewarded = sum(1 for p in proofs if p.get("reward", 0) > 0)

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Samples", total_proofs)
            with col2:
                st.metric(
                    "Valid Structure",
                    f"{valid_structure} ({100 * valid_structure / total_proofs:.1f}%)",
                )
            with col3:
                st.metric(
                    "Correct Proofs",
                    f"{rewarded} ({100 * rewarded / total_proofs:.1f}%)",
                )

            st.divider()

            # "I Feel Lucky" button
            col1, col2 = st.columns([1, 3])
            with col1:
                if st.button("🎲 I Feel Lucky!", use_container_width=True):
                    st.session_state.selected_proof = random.choice(proofs)

            with col2:
                filter_option = st.selectbox(
                    "Filter proofs:",
                    ["All", "Valid & Correct", "Valid but Wrong", "Invalid Structure"],
                )

            # Filter proofs based on selection
            if filter_option == "Valid & Correct":
                filtered_proofs = [p for p in proofs if p.get("reward", 0) > 0]
            elif filter_option == "Valid but Wrong":
                filtered_proofs = [
                    p
                    for p in proofs
                    if p.get("valid_structure", False) and p.get("reward", 0) == 0
                ]
            elif filter_option == "Invalid Structure":
                filtered_proofs = [
                    p for p in proofs if not p.get("valid_structure", False)
                ]
            else:
                filtered_proofs = proofs

            # Display selected proof or pick from filtered list
            if "selected_proof" in st.session_state:
                display_proof(st.session_state.selected_proof)
            elif filtered_proofs:
                # Show slider to browse proofs
                idx = st.slider(
                    "Browse proofs:",
                    0,
                    len(filtered_proofs) - 1,
                    0,
                    key="proof_slider",
                )
                display_proof(filtered_proofs[idx])
            else:
                st.info("No proofs match the current filter.")
        else:
            st.info("No generated proofs available yet.")


def display_proof(proof: dict):
    """Display a single proof with nice formatting."""
    st.divider()

    # Header with validity status
    is_valid = proof.get("reward", 0) > 0
    valid_structure = proof.get("valid_structure", False)

    if is_valid:
        status = "✅ Valid & Correct"
        status_color = "green"
    elif valid_structure:
        status = "⚠️ Valid Structure, Wrong Proof"
        status_color = "orange"
    else:
        status = "❌ Invalid Structure"
        status_color = "red"

    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader(f"Step {proof.get('step', 'N/A')}")
    with col2:
        st.markdown(f"**Status:** :{status_color}[{status}]")

    # Premises and Conclusion
    st.markdown("### Problem")
    premises = proof.get("premises", [])
    conclusion = proof.get("conclusion", "N/A")

    st.markdown(f"**Premises:** `{', '.join(premises)}`")
    st.markdown(f"**Conclusion:** `{conclusion}`")

    # Reasoning
    st.markdown("### Reasoning")
    reasoning = proof.get("reasoning")
    if reasoning:
        st.markdown(f">{reasoning[:500]}{'...' if len(reasoning) > 500 else ''}")
    else:
        st.markdown("*No reasoning extracted*")

    # Proof
    st.markdown("### Proof")
    proof_text = proof.get("proof")
    if proof_text:
        # Check if proof text has garbage
        if any(
            phrase in proof_text.lower()
            for phrase in ["let's", "tags", "craft", "produce"]
        ):
            st.warning("Proof contains extraneous text (formatting issue)")
        st.code(proof_text[:1000] if proof_text else "N/A", language=None)
    else:
        st.markdown("*No proof extracted*")

    # Raw response (collapsed)
    with st.expander("View Raw Response"):
        raw = proof.get("raw_response", "N/A")
        st.text(raw[:2000] if raw else "N/A")


if __name__ == "__main__":
    main()
