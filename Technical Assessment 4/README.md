# Technical Assessment 4

## Knowledge Representation Rule Based Reasoning and Case Based Reasoning

This submission uses an illustrative LGU disaster-planning scenario to compare RBR and CBR on the same facts. The report follows the supplied assessment template and includes the actual program source, RBR and CBR output captures, the knowledge-base description, and all four reflection answers.

## Files to submit

- `TA4_Valencia.pdf` - compiled report with code, outputs, and reflections.
- `ta4_reasoning.py` - complete runnable Python program.
- `TA4_Valencia.docx` - editable report copy.

The collaborator and professor fields are left blank if their names were not supplied; fill these on the cover before final submission.

## Run

Requires Python 3.10 or later. No additional packages or internet connection are needed.

```powershell
python ta4_reasoning.py
python ta4_reasoning.py --part rbr
python ta4_reasoning.py --part cbr
```

On macOS/Linux, use `python3` if that is the Python command installed on your computer.

The default demo uses a temporary library, explicitly applies a worked revision, writes and reloads the learned case, and shows a 100% match for the identical query. It does not change your persistent case library.

For manual revision and persistent retention:

```powershell
python ta4_reasoning.py --part cbr --interactive
```

Press Enter to keep proposed resource counts or strategy. Record a classroom-review or outcome note and explicitly confirm retention. This mode writes `cases.json` beside the script. An identical problem is rejected as a duplicate. To try another scenario, change the `FACTS` definition; to use another practice library, add `--data-file practice.json`.

## Requirement coverage

- Task 1A: eight facts in three dictionary categories: weather, community, and resources.
- Task 2A: five separate IF-THEN rule functions.
- Task 2B: an inference loop evaluates every rule against a copied working memory.
- Task 2C: prints all inferred actions with an execution trace.
- Task 3A: four invented cases containing problem features and matching solutions.
- Retrieve: weighted, normalized similarity and a same-hazard filter; deterministic ranking.
- Task 3C: reuses the closest solution and adapts its resource counts.
- Task 3D: accepts manual edits or unchanged values; the default demo labels its worked revision.
- Task 3E: retains the reviewed experience in JSON and verifies retrieval after reload.
- Part 4: answers all four comparative reflection questions in the report.

## Actual sample results

RBR fires all five rules. It identifies a 500-place shelter gap when accounting for all 1,200 affected people and one additional team under the classroom rule of one team per 200 people.

CBR ranks TYPHOON-01 at 90.1% and TYPHOON-02 at 89.1%. Adapting TYPHOON-01 proposes 1,104 shelter places and 9 teams. The worked revision adds one coordination team, resulting in 10. Retention increases the temporary case base from 4 to 5 cases, and the identical query retrieves LEARNED-05 at 100% after reloading.

The two methods differ because RBR applies fixed exercise assumptions while CBR scales a previous case. Neither output is a validated emergency plan. All cases, resource ratios, and actions are illustrative classroom examples.

## Output evidence

`outputs/rbr-output.png` and `outputs/cbr-output.png` are browser screenshots displaying stdout captured from actual Python executions. The matching `.txt` files contain the same output; `.html` files provide the readable capture pages. `outputs/all-output.txt` contains a combined run.
