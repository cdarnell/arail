import json
import time
import numpy as np
import os
from sklearn.metrics.pairwise import cosine_similarity

# Quantum Synchronicity — "Vibrational Correlation" engine
# References: Observer Effect, Vibrational Resonance, and Semantic Vector Alignment

# --- THE GROUND STATE ---
# Intent vector representing core qualities: [vibration, pattern, coincidence, noise]
INTENT_VECTOR = np.array([0.9, 0.8, 0.4, 0.1])


def generate_reality_stream(samples=1000, dim=4, seed=None):
    """Simulates a stream of random events as high-dimensional vectors.

    The stream represents a noisy "Reality" that the agent observes. The
    Observer Effect is acknowledged: observations and parameter adjustments
    may change subsequent measurements.
    """
    if seed is not None:
        np.random.seed(seed)
    return np.random.rand(samples, dim)


def calculate_synchronicity(stream, threshold=0.95):
    """Measures alignment between the global INTENT_VECTOR and each item in the stream.

    Returns an aggregate alignment score, number of high-confidence coincidences,
    and a simple entropy-like measure over similarity distribution.
    """
    similarities = cosine_similarity([INTENT_VECTOR], stream)[0]
    synchronicities = np.where(similarities > threshold)[0]

    alignment = float(np.mean(similarities))
    coincidence_count = int(len(synchronicities))
    entropy = float(-np.sum(similarities * np.log(similarities + 1e-9)) / len(similarities))

    return {
        "alignment_score": alignment,
        "coincidence_count": coincidence_count,
        "entropy": entropy,
    }


def auto_tune_intent(step=0.01, iterations=50, seed=None):
    """Simple hill-climb tuner that nudges INTENT_VECTOR elements to improve alignment.

    This demonstrates an AutoResearch loop: propose, evaluate, accept if better.
    """
    best = INTENT_VECTOR.copy()
    best_score = -np.inf

    for i in range(iterations):
        candidate = best + (np.random.randn(*best.shape) * step)
        candidate = np.clip(candidate, 0.0, 1.0)
        stream = generate_reality_stream(seed=seed)
        res = calculate_synchronicity(stream)
        score = res["alignment_score"]
        if score > best_score:
            best_score = score
            best = candidate

    return best, best_score


def _vibrational_frequency_from_alignment(alignment_score: float) -> float:
    """Derive a human-friendly vibrational frequency (Hz) from alignment score.

    This is a heuristic mapping to produce a stable numeric field for visualization.
    """
    base = 440.0  # A4 reference
    # Map alignment [0,1] to frequency range [110, 880] with small jitter
    freq = 110.0 + (alignment_score * (880.0 - 110.0))
    jitter = (np.random.rand() - 0.5) * 2.0  # +/-1 Hz jitter
    return float(freq + jitter)


if __name__ == "__main__":
    print("NC-LOG: Initiating Quantum Synchronicity Simulation...")

    # Live loop that emits structured JSON logs consumable by Loki
    sleep_seconds = int(os.environ.get("QR_SLEEP", 5))
    sample_count = int(os.environ.get("QR_SAMPLES", 500))

    while True:
        stream = generate_reality_stream(samples=sample_count)
        results = calculate_synchronicity(stream)
        alignment = results["alignment_score"]
        coincidence_count = results["coincidence_count"]
        entropy = results["entropy"]
        vibrational_frequency = _vibrational_frequency_from_alignment(alignment)

        payload = {
            "alignment_score": alignment,
            "coincidence_count": coincidence_count,
            "entropy": entropy,
            "vibrational_frequency": vibrational_frequency,
            "timestamp": int(time.time())
        }

        # Prefix required by Loki parsing pipeline
        print("QUANTUM_METRIC:" + json.dumps(payload), flush=True)

        time.sleep(sleep_seconds)
