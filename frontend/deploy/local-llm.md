# Assistant on a local model (B6)

The portal's assistant (explanations, routine form, care-plan suggestions) can use a model running on
one of our own machines instead of Anthropic's Claude. Nothing is sent to an outside company. This file
says how to run the model on Thierry's MacBook (48 GB, Apple Silicon), check it, connect the portal on
a laptop and later on the gateway mini-PC over Tailscale, and run K2's eval against it.

Code: `backend/cmn_frontend/llm.py` (provider layer). The local path talks to any OpenAI-compatible
endpoint (`POST <base_url>/chat/completions`): Ollama, a llama.cpp server or LM Studio.

---

## 1. Which model

| Model (Ollama tag) | Download | Type | For us |
|---|---|---|---|
| **`qwen3.8:27b-mlx`** (recommended) | ≈ 18 GB | dense 27B, 4-bit MLX | best at following the rules (numbers only from `<results>`, no clinical terms for the person, no diagnosis); slower to read the long context |
| `qwen3.5:35b-mlx` | ≈ 22 GB | mixture of experts, ≈ 3B active | several times faster, weaker at following the rules; also takes images (not needed) |

Start with `qwen3.8:27b-mlx`. If the first answer takes too long for the demo (see §4), switch to
`qwen3.5:35b-mlx`. Only the model name in the settings changes.

**Context length matters.** The assistant sends the profile's results as one block. For a 4-week
profile that is about 18–21k tokens, plus the conversation. If Ollama's context is smaller, it
**silently drops the start of the prompt**, which is where the rules are. Always run it with at least
**32k**. Memory: model ≈ 18 GB + 32k context ≈ a few GB, so about 22–25 GB in total. That fits in 48 GB
next to normal work.

## 2. Install and start (once)

Requires a recent Ollama (MLX models need Apple Silicon and a current version: `ollama --version`;
update from ollama.com if `pull` says the model needs a newer version).

```bash
ollama pull qwen3.8:27b-mlx
```

Ollama settings (environment variables of the Ollama server):

| Variable | Value | Why |
|---|---|---|
| `OLLAMA_CONTEXT_LENGTH` | `32768` | see above; the OpenAI-compatible endpoint cannot set it per request |
| `OLLAMA_KEEP_ALIVE` | `30m` | the model stays loaded between questions; loading 18 GB takes a while |
| `OLLAMA_HOST` | leave unset (`127.0.0.1:11434`) | the gateway reaches it through `tailscale serve` (§5), so Ollama never listens on a network address |

**Ollama.app (menu bar):** set the variables for apps, then quit and reopen Ollama:

```bash
launchctl setenv OLLAMA_CONTEXT_LENGTH 32768
launchctl setenv OLLAMA_KEEP_ALIVE 30m
```

(`launchctl setenv` is lost on restart of the Mac; set it again before a demo.)

**Or in a terminal** (quit the menu-bar app first, so port 11434 is free):

```bash
OLLAMA_CONTEXT_LENGTH=32768 OLLAMA_KEEP_ALIVE=30m ollama serve
```

## 3. Check the model on its own

```bash
curl -s http://127.0.0.1:11434/v1/models
```

The list must contain `qwen3.8:27b-mlx`. Then one short answer:

```bash
curl -s http://127.0.0.1:11434/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "qwen3.8:27b-mlx",
  "messages": [{"role": "user", "content": "Say hello in five words."}]
}'
```

`ollama ps` shows the loaded model and its **CONTEXT** column. It must say 32768. If it says 4096 or
8192, the variable did not reach the server (see §2).

## 4. Connect the portal on the laptop

1. Start the portal as usual (backend + Vite, see `frontend/README.md`), log in as a multi-profile user.
2. **Settings → Assistant → Who answers: Local model**
   - Endpoint: `http://127.0.0.1:11434/v1`
   - Model name: `qwen3.8:27b-mlx`
   - **Check connection** must say "Reached the endpoint; it serves qwen3.8:27b-mlx."
   - Tick "Turn the assistant on", **Save**.
3. Try it:
   - open Ben, ask in the assistant "How were my nights last week?" (as the person) and "Why is C4
     present in the recent period?" (as the clinician);
   - Onboarding → describe a week ("School Monday to Friday 8 to 4, bed at 22:30, weekends free, iPhone
     and a shared iPad") → the routine form fills in.
4. Note the time to the first word. The first question of a profile reads the whole context (≈ 20k
   tokens). Follow-up questions reuse it and start much sooner. If the first one takes well over a
   minute, try `qwen3.5:35b-mlx`.

The same settings can come from the environment instead of the page (the page wins once saved):

```bash
export CMN_ASSISTANT=1 CMN_ASSISTANT_PROVIDER=local CMN_ASSISTANT_MODEL=qwen3.8:27b-mlx
export CMN_LOCAL_URL=http://127.0.0.1:11434/v1
```

### Thinking

Qwen 3.x models can "think" before answering. The portal shows only the answer, but thinking costs
time. To switch it off, start the backend with

```bash
export CMN_LOCAL_EXTRA_BODY='{"reasoning_effort": "none"}'
```

This JSON is merged into every request to the local model. If the answers then start sooner and still
pass the eval, keep it; if Ollama rejects the field, remove it.

### Other servers

- **LM Studio:** load the model, Developer → Start server (port 1234), context length 32768 in the
  model's load settings. Endpoint `http://127.0.0.1:1234/v1`, model name as LM Studio lists it.
- **llama.cpp:** `llama-server -m <model>.gguf -c 32768 --port 8080`, endpoint
  `http://127.0.0.1:8080/v1`.

For the routine form, the portal sends the form's JSON schema as `response_format: json_schema`. All
three servers turn that into a grammar, so the answer always parses. A server without it gets JSON
mode with the schema in the prompt.

## 5. Gateway mini-PC → laptop over Tailscale (set up 20.11)

The portal on the mini-PC runs with host networking, so it reaches every machine in our tailnet
directly. Ollama has **no login**, so it must only be reachable inside the tailnet, never on the home
or university Wi-Fi. Ollama itself stays on `127.0.0.1` (so the laptop's own portal keeps using
`http://127.0.0.1:11434/v1`); Tailscale forwards the port into the tailnet:

```bash
/Applications/Tailscale.app/Contents/MacOS/Tailscale serve --bg --tcp 11434 tcp://127.0.0.1:11434
```

This stays active across restarts of the Mac and of Tailscale. Check with `… serve status`: it must
say "(tailnet only)". Thierry's MacBook is `100.79.94.102` (`macbook-pro-von-thierry`). From the
mini-PC: `curl -s http://100.79.94.102:11434/v1/models`.

Gateway portal (v3): Settings → Assistant → **Local model**, endpoint `http://100.79.94.102:11434/v1`,
model `qwen3.5:35b-mlx`, **Check connection**, tick **"If the local model cannot be reached … let
Anthropic's Claude answer instead"**, Save. The container runs with thinking off
(`CMN_LOCAL_EXTRA_BODY` in `docker-compose.yml`).

**Fallback.** When the laptop is closed, offline or Ollama is not running, the connection fails
within a few seconds and Claude answers that question with the stored Claude key; the answer starts
with "(The local model was not reachable, so Claude (Anthropic) answered.)". With the local model
the assistant panel shows no notice (nothing leaves our computers); with Claude, one short line. Errors after the connection (wrong model name, cut-off answer) do not
fall back. Without the tick, the answer is just the error note.

Before a demo on the laptop: Ollama running with the 32k context (§2, after a restart of the Mac set
the `launchctl` values again), laptop awake and on Tailscale.

## 6. Run K2's eval on the local model

Once K2's `eval/assistant_eval.py` is on `frontend-v3`, with `~/cmn-data` present:

```bash
cd frontend/backend
export CMN_ASSISTANT=1 CMN_ASSISTANT_PROVIDER=local CMN_ASSISTANT_MODEL=qwen3.8:27b-mlx
export CMN_LOCAL_URL=http://127.0.0.1:11434/v1
.venv/bin/python -m eval.assistant_eval --dry-run    # contexts and number of requests
.venv/bin/python -m eval.assistant_eval              # the full run, writes eval/results/*.md
```

If `<home>/assistant.json` exists (settings saved in the portal), it wins over these variables. Then
set the provider there instead, or point `CMN_HOME` to an empty folder for the eval. The eval writes
`eval/results/assistant_eval_<date>_qwen3.8-27b-mlx.md`. That table goes next to Claude's in the PR
and the report. Expect it to take a while: about 40 questions with follow-ups, each reading ≈ 20k
tokens the first time per profile and role.

## 7. Afterwards

`ollama stop qwen3.5:35b-mlx` frees the memory. To take the laptop out of the tailnet path:
`/Applications/Tailscale.app/Contents/MacOS/Tailscale serve --tcp=11434 off` (the gateway then
falls back to Claude).
