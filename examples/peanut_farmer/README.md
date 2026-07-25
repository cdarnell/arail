# PeanutLab — the offline lab walkthrough

A self-contained example that runs the **whole ARAIL research loop —
goal → curated data → experiments → observations → results — with no model
loaded and no network**. It is the fastest way to see how the lab thinks before
you point it at your own domain.

Everything here uses the same primitives the real lab uses: the offline goal
parser (`arail.skills.goal_parser`) and the experiment tracker
(`arail.skills.experiment_tracker`). Nothing is mocked.

## Run it

```bash
python3 examples/peanut_farmer/run.py
```

No `pip install -e .` required — `run.py` puts the repo root on `sys.path`
itself. It finishes in under a second.

## What each step shows

| Step | What happens | Which lab primitive |
|------|--------------|---------------------|
| 1 · Parse your goal | A plain-English goal ("grow the best peanuts in Georgia with sustainable practices") is parsed **offline** into a domain, objective, and entities — no LLM call. | `GoalParser.parse_offline` |
| 2 · Curate data | Four illustrative source summaries (USDA NASS, NOAA, NRCS Soil, Extension) stand in for the knowledge the lab would gather. | *(hardcoded demo data)* |
| 3 · Set up experiments | Two hypotheses become tracked experiments with methodology, variables, metrics, and a duration. | `ExperimentTracker.create` |
| 4 · Run the season | Observations are logged over the run and one experiment is completed with results. | `.start` / `.observe` / `.complete` |
| 5 · Summarize | The tracker reports totals and the latest result. | `.list_all` |

## Honest about the numbers

**Step 4 is explicitly a *simulation*** — the yield figures (4,320 lbs/acre,
+12.5 %) are illustrative demo values written into the tracker to show the shape
of a completed run, **not measurements**. A peanut season takes 180 days; this
example fast-forwards it so the workflow is visible in one screen. When the real
lab runs experiments it *measures* outcomes on your machine (see the
Autoresearch surface and `src/arail/research/mini_experiments.py`) — this demo
just exercises the plumbing.

## Where it writes

The tracker persists to **`./experiments/`** relative to your current working
directory (with a small LanceDB cache under `experiments/.cache/`). Delete it
when you're done:

```bash
rm -rf experiments/
```

## Make it yours

This is the "fork and adapt" starting point the lab is designed for. Copy
`run.py`, change the goal string in Step 1 and the hypotheses in Step 3 to your
own domain, and you have a runnable skeleton for your own lab loop — no model,
no cloud account, no setup. When you're ready for measured (not simulated)
results, move the same goals into the Autoresearch surface in the portal.
