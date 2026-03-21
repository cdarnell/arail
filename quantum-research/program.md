# Program: Refine the Research (Resident Mentor)

Purpose
- Run the `simulation.py` experiment autonomously and iteratively refine the `INTENT_VECTOR` to maximize the "Alignment Score" and increase `coincidence_count`.

Tasks for the Resident Mentor
1. Run the simulation to gather baseline statistics:

   - `python simulation.py`

2. Iteratively adjust `INTENT_VECTOR` (in `simulation.py`) or script a tuner to propose small variations.

3. Evaluate results:

   - Treat increases in `coincidence_count` as a "Successful Discovery".
   - Record the `alignment_score` and `entropy` for each trial.

4. Commit improvements:

   - If a new `INTENT_VECTOR` yields a higher `coincidence_count`, commit that change with message:
     `git commit -am "chore(quantum): successful-discovery - increased coincidence_count"`

Automation suggestions
- Wrap the single-run experiment in a small loop that generates candidate vectors, evaluates them, and persists candidates that improve `coincidence_count`.
- Log trials to `trials.log` with timestamp, vector, and metrics.

Notes
- Respect the Observer Effect: changing the intent or observation procedure may alter subsequent outcomes.
- Use `requirements.txt` to prepare the environment: `pip install -r requirements.txt`.
