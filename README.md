# Jon the Researcher

`jon-researcher` is a local AI researcher CLI powered by Ollama, LangChain, and free-first web research tools. It opens into a `you >` prompt, streams Markdown answers in a live `jon` box, shows tool calls as they happen, and keeps conversation context only for the current session.

You can start it with either command:

```bash
jon-researcher
jon
```

See the [researcher working diagram](docs/researcher-flow.md) for the full flow from `you >` input to Ollama model calls, research tools, streamed Markdown output, and the final `Tools used:` footer.

## Developer Setup

1. Clone or open this project, then enter the app folder:

```bash
cd jon-researcher
```

2. Create the local environment and install dependencies:

```bash
uv sync --extra dev
```

If you are not using `uv`, use a normal virtual environment:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

3. Start Ollama:

```bash
ollama serve
```

4. Pull or confirm at least one Ollama model with tool support:

```bash
ollama pull llama3.1:8b
ollama list
```

5. Run Jon from the source checkout:

```bash
uv run jon
```

The full command also works:

```bash
uv run jon-researcher
```

6. On first run, Jon checks local Ollama, shows only installed models whose capabilities include both `completion` and `tools`, and asks you to select one with the arrow keys. The selection is saved at:

```text
~/.local/share/jon-researcher/config.json
```

7. Ask a question:

```text
you > search online and give me latest ai trends
```

## Requirements

- Python 3.11+
- Ollama running locally
- At least one installed Ollama model whose `/api/show` capabilities include both `completion` and `tools`
- Dependencies from `pyproject.toml`

Jon uses DuckDuckGo HTML search out of the box because it is free and needs no API key. `/researcher` can switch providers between DuckDuckGo, Brave Search, Tavily, SerpAPI, Exa, and Bing Web Search. Paid/API providers require their API key.

Set `JON_HOME` if you want the config file somewhere other than `~/.local/share/jon-researcher/config.json`.

## Configure The Model

Use `/configure` inside the `you >` prompt whenever you want to change model or runtime settings:

```text
you > /configure
```

Jon will ask for:

- Ollama URL, usually `http://localhost:11434`
- Timeout seconds
- Model with tool support, selected from installed Ollama models
- Max research tool rounds

## Configure Researcher

Use `/researcher` inside the `you >` prompt to choose the research provider and enabled tools:

```text
you > /researcher
```

Providers:

```text
DuckDuckGo       free, no API key
Brave Search    BRAVE_SEARCH_API_KEY
Tavily          TAVILY_API_KEY
SerpAPI         SERPAPI_API_KEY
Exa             EXA_API_KEY
Bing Web Search BING_SEARCH_API_KEY
```

For DuckDuckGo, select it and keep `research_search` / `research_fetch` enabled.

For paid/API providers, either enter the key when `/researcher` prompts you, or export the matching environment variable before starting Jon:

```bash
export BRAVE_SEARCH_API_KEY="..."
export TAVILY_API_KEY="..."
export SERPAPI_API_KEY="..."
export EXA_API_KEY="..."
export BING_SEARCH_API_KEY="..."
```

Research tools:

- `research_search` searches the configured provider.
- `research_fetch` fetches readable text from URLs when the model needs detail.

## CLI Flow

When Jon opens:

```text
Type /help for commands.

you >
```

Tool calls and answers look like this:

```text
you > search online and give me latest ai trends
jon > working...
tool > using research_search
tool > args {"max_results": 5, "query": "..."}
tool > research_search completed - Research results: ...
╭─ jon ─────────────────────────────────────────╮
│ the streamed Markdown answer                  │
│                                                │
│ ────────────────────────────────────────────── │
│ Tools used: research_search                    │
╰───────────────────────────────────────────────╯
```

After you press Enter, Jon shows `jon > working...` until it starts rendering the response. Whenever the agent calls a tool, Jon prints the tool name first, for example `tool > using research_search`. Search-like prompts that mention words such as `search`, `online`, `web`, `latest`, `current`, `recent`, `news`, or `trends` automatically run `research_search` before Jon answers. In an interactive terminal, Jon also renders small `Tool call` and `Tool result` blocks, streams the Markdown response inside a live `jon` box, and appends a `Tools used:` line at the end of the response.

Commands inside Jon:

```text
/help
/status
/configure
/researcher
/exit
```

`/status` shows the active config path, Ollama URL, selected model, model capability status, research provider, and enabled research tools.

Interactive conversations use an in-memory checkpoint thread, so follow-up questions keep context until you exit Jon. Chats are stateless across runs: once you exit, Jon does not persist chat history.

## Tests

```bash
uv run pytest -q
```

Or with the local venv:

```bash
.venv/bin/python -m pytest -q
```

## Bundle

Build the standalone binary:

```bash
uv run pyinstaller --clean jon.spec
```

Or:

```bash
.venv/bin/pyinstaller --clean jon.spec
```

Run the bundled binary:

```bash
./dist/jon-researcher
```

The bundled binary still expects Ollama to be installed and running on the target machine.

## Install Locally

Build the binary, install it to `~/.local/bin`, and add that directory to your shell PATH:

```bash
scripts/install.sh
```

The installer creates:

```text
~/.local/bin/jon-researcher
~/.local/bin/jon
```

Restart your shell, or run:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Then Jon is available from any directory:

```bash
jon
jon-researcher
```

To remove the local install and the managed PATH block:

```bash
scripts/uninstall.sh
```

## A Final Note

Jon Researcher is intentionally a small, focused project. Behind its compact scope are ideas shaped by broader experience with agentic systems: local model discovery, tool orchestration, streaming interfaces, conversation state, and application packaging. The aim is not to present a finished answer, but to turn those lessons into something approachable, useful, and easy to build upon.

There is plenty of room for this project to grow—from new research providers and tools to richer workflows and deeper local intelligence. Sometimes a small project is all an idea needs to find its wings. If Jon gives you a useful starting point for an experiment of your own, it has done its job.

If you genuinely enjoy the project or find the work useful, consider giving it a star. It is a small gesture, but it helps the project reach more curious builders and encourages its next chapter.
