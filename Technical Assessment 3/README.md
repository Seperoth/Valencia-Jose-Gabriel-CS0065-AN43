# Disaster DSS: Case-Based Reasoning

A local browser dashboard for the **Knowledge Representation & Reasoning** activity. It demonstrates structured cases, explainable similarity measures, adaptation, revision, and learning by retaining new cases. It uses Python's standard library only.

The nine starting cases are **invented classroom scenarios**, not records of actual disasters. Severity, weights, resource formulas, and priorities are exercise assumptions. This program is not suitable for real emergency decisions. No live warnings, maps, or emergency services are connected.

## Run

Requires **Python 3.10 or later**. Tested with Python 3.13.

On Windows, double-click **Run Disaster DSS.vbs** (or **Run Disaster DSS.cmd**). The dashboard opens in your default browser, with the Python server running in the background. No terminal interaction is needed. Use **Stop dashboard** in the top bar when finished; closing the browser tab alone leaves the local server running.

You can also start it from this folder:

```powershell
python main.py
```

For a complete demonstration without answering prompts:

```powershell
python main.py --demo
```

The demo writes and reloads a temporary case library, then removes it. The dashboard creates `data/cases.json` from the supplied seed on first use. Reviewed cases remain in that file after restarting. No npm installation, third-party Python packages, or internet connection is needed. The built-in server accepts connections only on `127.0.0.1` and chooses a free port automatically.

## Dashboard

1. **Analyze scenario:** fill in the disaster, severity, affected people, access, area, and available resources. **Use sample** fills and analyzes the worked flood example without saving anything.
2. **Retrieve:** compare the top three matching cases. Select a case and expand **Match details** to inspect every weighted feature contribution.
3. **Reuse & adapt:** choose **Use selected case** to calculate an illustrative proposal. Matches below 65% cannot be reused.
4. **Revise & retain:** edit priority, total resource counts, and review actions; add an outcome note, check the review confirmation, and select **Save case**. Resource gaps update as counts change. Duplicate scenarios cannot be retained.
5. **Case library:** search or filter saved cases and select **View case** to inspect the problem, solution, review note, and origin.

Use **Add plan manually** after retrieval to supply a reviewed solution yourself, including when a disaster type has no stored examples. Editing scenario inputs clears old matches and proposals so that they cannot be saved against a different problem.

For troubleshooting or a chosen port, run `python main.py --port 8765 --no-browser` and open the printed address. For a separate practice library, use `python main.py --data-file practice.json`. Startup errors are printed when launched this way. The original terminal interface remains available with `python main.py --cli`.

## Optional terminal menu (`--cli`)

1. **Analyze a new scenario:** represent a problem, retrieve similar cases, inspect the score, adapt a solution, then optionally revise and retain it.
2. **Inspect stored cases:** browse the library and view the complete JSON representation of a case.
3. **Add a reviewed case manually:** enter a problem, solution, and outcome, including disaster types without existing examples.
4. **Run the worked example:** demonstrate the entire cycle in an isolated library.
5. **Exit.**

Enter `:back` at a prompt to cancel an unfinished workflow. In revision prompts, press Enter to keep a suggested value. Retention requires an explicit yes after reviewing the solution and recording an outcome or classroom-review note.

## 1. Knowledge representation

A case has three central parts:

| Part | Stored knowledge |
| --- | --- |
| Problem | Disaster type, severity, affected people, road access, area type, available shelter places, available response teams |
| Solution | Planning priority, total proposed shelter places, total proposed response teams, review actions |
| Outcome | An observed result or a classroom-review note |

It also stores an ID, review status, source, timestamp, and the ID of the case from which it was adapted. `Problem`, `Solution`, and `Case` are Python dataclasses; JSON provides persistent storage. See `data/seed_cases.json` for all nine examples: three floods, three typhoons, and three earthquakes. Landslide is supported as an input to demonstrate the no-history situation.

Example problem:

```json
{
  "disaster_type": "flood",
  "severity": 5,
  "affected_people": 1200,
  "road_access": "restricted",
  "area_type": "urban",
  "available_shelter_places": 700,
  "available_response_teams": 5
}
```

Severity is an exercise scale from 1 to 5, not an official storm signal, earthquake magnitude, or warning level. Shelter capacity is measured in **people**; response resources are measured in **teams**. These are different units.

## 2. Similarity assessment and retrieval

Only reviewed cases of the **same disaster type** enter the candidate set. This prevents an earthquake plan from being reused directly for a flood. Candidates are ranked by a weighted sum:

```text
Similarity(new, stored) = sum(weight[i] * local_similarity[i])
```

| Feature | Weight | Local similarity |
| --- | ---: | --- |
| Disaster type | 0.25 | Exact match: 1, otherwise 0; also used as a candidate filter |
| Severity | 0.20 | `1 - abs(new - stored) / 4` |
| Affected people | 0.15 | `1 - abs(new - stored) / max(new, stored, 1)` |
| Road access | 0.15 | Encode open=0, restricted=1, blocked=2; then `1 - distance / 2` |
| Area type | 0.10 | Exact match: 1, otherwise 0 |
| Available shelter places | 0.10 | Relative numerical similarity, as above |
| Available response teams | 0.05 | Relative numerical similarity, as above |

Weights total 1. Every local similarity lies between 0 and 1. Two zero resource counts have similarity 1; zero and a positive count have similarity 0. Numerical features are normalized so a population count does not overwhelm a severity rating.

The program displays the top three cases and the contribution of every feature. Ties are broken by case ID for stable results. The user can inspect a candidate before reuse. Cases below **65% similarity** cannot be adapted automatically. If there are no suitable cases, the program directs the user to add a reviewed solution manually.

The threshold and weights are manually chosen for this exercise. They are not empirically calibrated. Similarity is **resemblance, not confidence or probability of success**. Disaster-type similarity is always 1 among eligible candidates; it contributes a fixed 0.25 and does not change their relative ordering.

## 3. The CBR cycle and adaptation

| CBR stage | What this program does |
| --- | --- |
| Retrieve | Finds comparable reviewed experiences using the similarity measures |
| Reuse / Adapt | Scales the selected solution to the new problem and explains the changes |
| Revise | Lets the user correct the proposed priority, resource counts, and review actions and record an outcome |
| Retain | Saves the reviewed problem-solution-outcome as a new case for future retrieval |

Representation supplies the knowledge on which this cycle operates. Reasoning is experience-based: the program explains which earlier scenario is relevant, then adapts that experience rather than deriving a solution entirely from general rules.

The illustrative adaptation rules are:

```text
population_factor = new_people / stored_people
severity_factor   = 1 + 0.15 * (new_severity - stored_severity)
scale             = population_factor * severity_factor

proposed_shelters = min(new_people, ceil(stored_shelters * scale))
proposed_teams    = max(1, ceil(stored_teams * scale))
```

Newly blocked road access adds one illustrative coordination team and a review action. Priority starts from the stored solution: increase it one level if severity rises or access becomes blocked; decrease it one level if severity falls and access is not blocked. Otherwise preserve the reviewed priority. This means an identical problem reuses the learned priority rather than overwriting it with a general rule. Resource shortfalls are `max(0, proposed_total - available)`.

These rules demonstrate **case adaptation**, not validated disaster-response resource ratios. The exact fractions used in calculations avoid floating-point errors when rounding resources up. A reviewer can replace the proposed values before retaining them.

## 4. Worked example and learning

Running `python main.py --demo` uses the sample problem above:

- Closest case: **FLOOD-002**, at **90.1%** similarity.
- Population factor: `1200 / 1000 = 1.20`.
- Severity factor: `1 + 0.15 * (5 - 4) = 1.15`.
- Adapted shelter places: `ceil(800 * 1.20 * 1.15) = 1104`, giving a shortfall of `404`.
- Adapted teams: `ceil(6 * 1.20 * 1.15) = 9`, giving a shortfall of `4`.
- Example revision: the reviewer changes the team count from 9 to 10.
- Retention increases the temporary library from 9 to 10 cases.
- Retrieving the identical problem now returns the learned case at **100%** similarity.

Learning here means **adding reviewed experiences to the case base**. The system does not train a neural network, change its weights automatically, or prove that an accepted solution is correct. Retaining a poorly reviewed solution can reduce the quality of future answers.

## Files and validation

| File | Purpose |
| --- | --- |
| `cbr.py` | Case models, validation, similarity, retrieval, adaptation, JSON persistence |
| `main.py` | Interactive interface and complete worked example |
| `dashboard.py` | Local HTTP server connecting the dashboard to the CBR engine |
| `web/` | Responsive dashboard HTML, CSS, and JavaScript |
| `Run Disaster DSS.vbs` | Windows launcher that opens the dashboard without a terminal window |
| `data/seed_cases.json` | Original synthetic case base; never modified by learning |
| `data/cases.json` | Local saved library, created automatically and ignored by Git |
| `tests/test_cbr.py` | Reasoning, persistence, failure handling, and interactive-flow checks |
| `tests/test_dashboard.py` | HTTP workflow, review guards, persistence, local request checks, and shutdown |
| `examples/demo-output.txt` | Captured output from the complete worked example |

Run the checks:

```powershell
python -m unittest discover -s tests -v
```

The program rejects invalid inputs, unreviewed retention, duplicate problems, weak analogies, and cross-disaster reuse. Writes replace the JSON file atomically. Corrupt saved files are reported instead of silently overwritten. This is a local, single-user case base; run one dashboard instance per data file.

## Suggested work split for a pair

- Partner 1: case representation, seed knowledge, similarity formulas, and retrieval explanations.
- Partner 2: adaptation, revision, retention, and the command-line interface.
- Both: test the example, change one input at a time, explain why rankings change, and demonstrate learning after a restart.

## Discussion questions

1. Why are population and severity not compared using raw differences alone?
2. What changes if population receives more weight than road access?
3. Why should an accepted case include an outcome rather than only a proposed solution?
4. What happens when no case covers a new disaster type?
5. Why does an identical-case similarity of 100% not establish that the solution is correct?

This is the standalone **Technical 3 - CBR System Development** project. Run the commands above from this folder, which contains `main.py` directly.
