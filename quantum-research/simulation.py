import numpy as np
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

    return {
        "alignment_score": float(np.mean(similarities)),
        "coincidence_count": int(len(synchronicities)),
        "entropy": float(-np.sum(similarities * np.log(similarities + 1e-9)) / len(similarities))
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


if __name__ == "__main__":
    print("NC-LOG: Initiating Quantum Synchronicity Simulation...")
    reality = generate_reality_stream()
    results = calculate_synchronicity(reality)

    print("--- EXPERIMENT RESULTS ---")
    print(f"Average Vibrational Resonance: {results['alignment_score']:.4f}")
    print(f"Observed Synchronicities: {results['coincidence_count']}")
    print(f"System Entropy: {results['entropy']:.4f}")

    if results['coincidence_count'] > 5:
        print("SIGNAL DETECTED: Pattern alignment exceeds random noise probability.")
