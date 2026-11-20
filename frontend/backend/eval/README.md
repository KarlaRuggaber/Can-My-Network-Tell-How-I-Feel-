# Assistant eval (B5): running it on the local model

For Thierry, on his MacBook (Apple Silicon, 48 GB). Goal: the same 40 questions (51 answers) that
Claude answered on 20.11, now answered by the local model, so the report can put both tables side by
side. The run uses **exactly the same data and prompt as Claude's run 2**: they are saved in
`eval/contexts_2026-11-20.json`. You don't need `~/cmn-data`, a portal login or an API key, and the
run costs nothing.

Claude's results for comparison: `eval/results/assistant_eval_2026-11-20_claude-sonnet-5-5.md`.

---

## 1. Before you start

- **Code:** `frontend-v3` with PR #28 (K2, this eval) and PR #25 (K3, local model) merged.
- **Ollama with the model, and a context of at least 32k.** Setup is in
  [`frontend/deploy/local-llm.md`](../../deploy/local-llm.md), §1–3. In short:
  ```bash
  ollama pull qwen3.8:27b-mlx
  launchctl setenv OLLAMA_CONTEXT_LENGTH 32768
  launchctl setenv OLLAMA_KEEP_ALIVE 30m
  ```
  Then quit and reopen Ollama (menu bar). **The 32k context matters.** Each question carries about
  15–18k tokens of data. With a smaller context, Ollama silently cuts off the start of the prompt,
  where the rules are, and the results become meaningless.
- **Laptop plugged in.** The run takes a while (see §3).

## 2. Set up (once, about 5 minutes)

```bash
cd ~/cmn-frontend-v3            # your checkout; any folder with frontend-v3 works
git fetch origin && git switch frontend-v3 && git pull
cd frontend/backend
python3.13 -m venv .venv        # skip if .venv exists; needs Python 3.11 or newer
.venv/bin/pip install -r requirements.txt
```

Check that Ollama serves the model with the right context:

```bash
curl -s http://127.0.0.1:11434/v1/models
ollama ps
```

The first must list `qwen3.8:27b-mlx`. `ollama ps` shows the model only once it is loaded (after the
first question); its CONTEXT column must then say `32768`.

## 3. Run

All commands from `frontend/backend`.

**a) Dry run.** It only prints the plan and calls nothing:

```bash
.venv/bin/python -m eval.assistant_eval --contexts eval/contexts_2026-11-20.json --provider local --model qwen3.8:27b-mlx --dry-run
```

It must say `40 questions, 51 requests to local / qwen3.8:27b-mlx at http://127.0.0.1:11434/v1
(contexts from eval/contexts_2026-11-20.json)` and list Ben, Maria and Carl with data to 2026-11-20.

**b) One question as a test** (about 1–3 minutes, mostly loading the model and reading the data):

```bash
.venv/bin/python -m eval.assistant_eval --contexts eval/contexts_2026-11-20.json --provider local --model qwen3.8:27b-mlx --case p01 --out /tmp/eval-test
```

It prints one line like `p01 turn 1: 74 words, 95.2 s, ok` (or the failed checks), and writes
`/tmp/eval-test/...md`. Open it to check that the answer reads like an answer. If it took much longer
than 3 minutes, see §5.

**c) The full run.** `caffeinate -i` keeps the Mac awake while it runs:

```bash
caffeinate -i .venv/bin/python -m eval.assistant_eval --contexts eval/contexts_2026-11-20.json --provider local --model qwen3.8:27b-mlx
```

Each answer prints a line with its time as it goes. Expect roughly **30 s to 2 min per answer**: the
first question of each persona and role reads the whole data block, and follow-ups are faster. That
makes **about 30–90 minutes** for all 51. The run can be stopped with Ctrl-C; it then writes nothing,
so start it again.

When it finishes, it writes two files:

- `eval/results/assistant_eval_<today>_qwen3.8-27b-mlx.md`: the tables
- `eval/results/assistant_eval_<today>_qwen3.8-27b-mlx.jsonl`: every answer

A second run on the same day overwrites them. Rename the first pair to `..._v1.md` / `..._v1.jsonl`
before running again.

## 4. Send the results back

Commit the two files on a branch and open a PR into `frontend-v3`:

```bash
git switch -c v3/k2-eval-local
git add eval/results/assistant_eval_*_qwen3.8-27b-mlx.*
git commit -m "Portal v3: assistant eval on the local model (qwen3.8:27b-mlx)"
git push -u origin v3/k2-eval-local
```

In the PR description, paste the summary table from the top of the `.md` file and note the total
time.

## 5. If something goes wrong

| What you see | Cause and fix |
|---|---|
| `could not reach the local model at http://127.0.0.1:11434/v1` | Ollama isn't running, or it listens on the Tailscale address (`OLLAMA_HOST` was set for the gateway demo). Start Ollama, or add `--base-url http://<tailscale-ip>:11434/v1`. |
| `the local endpoint has no model "qwen3.8:27b-mlx"` | Not pulled, or a different name. `curl -s http://127.0.0.1:11434/v1/models` shows the exact name; pass it with `--model`. |
| `took too long to answer` | One answer took over 10 minutes. Close other apps; try with thinking off (below), or the faster `qwen3.5:35b-mlx`. |
| Answers ignore the rules (long, clinical words, invented numbers) right from the start | Usually the context is too small: `ollama ps` must show 32768 (see §1). |
| `(The answer was cut off.)` in answers | The model thought for too long. Switch thinking off (below). |

**Thinking off.** Usually faster. If you use it, mention it in the PR:

```bash
export CMN_LOCAL_EXTRA_BODY='{"reasoning_effort": "none"}'
```

Then run 3c again in the same terminal. If Ollama rejects the field, `unset CMN_LOCAL_EXTRA_BODY`.

**A second model (optional).** Same command with `--model qwen3.5:35b-mlx` (pull it first). Its
results go into separate files, named after the model.

## 6. Reading the table

The columns are the same as in Claude's table:

- **Numbers grounded:** every number, date and time in the answer appears in the data sent.
- **No clinical terms:** person answers in the model's own words, before the portal's safety net.
  The line under the table says what the safety net (the portal's `guard_person`) would replace, and
  whether any clinical term would still reach the person. It should say "none".
- **No diagnosis, No reasons, Points to care team, No treatment advice:** the guardrails. For the
  report, these matter most.
- **Shorter / More detail:** the answer controls.
- **Length (info):** answer length, reported only. We decided on 20.11 that longer answers are
  acceptable, because the "Shorter" button shortens them on request.

Under "Answers", each row lists the failed checks with the words or numbers that failed. The `.jsonl`
holds the full answers for reading a case in detail.
