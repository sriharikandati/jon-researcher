# Researcher Working Diagram

This diagram shows how Jon handles a question from the terminal prompt through model selection, research tools, streaming output, and the in-memory conversation thread.

```mermaid
flowchart TD
    User["User enters a question"] --> Prompt["you > prompt"]
    Prompt --> Config["Load local config<br/>~/.local/share/jon-researcher/config.json"]
    Config --> ModelCheck["Check Ollama models<br/>completion + tools capabilities"]
    ModelCheck --> Session["Create in-memory checkpoint thread<br/>keeps context until exit"]
    Session --> ResearchIntent{"Question asks for<br/>search, latest, web, news, trends?"}

    ResearchIntent -- "yes" --> Preflight["Run research_search preflight"]
    Preflight --> ToolLog["Render tool activity<br/>tool > using ..."]
    ToolLog --> Agent["LangChain agent"]

    ResearchIntent -- "no" --> Agent
    Agent --> Ollama["ChatOllama selected model"]
    Ollama --> Decision{"Agent needs a tool?"}

    Decision -- "yes" --> ToolCall["Call enabled research tool<br/>research_search or research_fetch"]
    ToolCall --> ToolLog
    ToolLog --> Ollama

    Decision -- "no" --> Stream["Stream answer tokens"]
    Stream --> Markdown["Render Markdown in live jon box"]
    Markdown --> Footer["Append Tools used footer"]
    Footer --> Done["Return to you > prompt"]
```

## Flow Notes

- Jon starts directly at the `you >` prompt and accepts slash commands such as `/help`, `/configure`, `/researcher`, `/status`, and `/exit`.
- First-time setup asks the user to select an installed Ollama model that reports both `completion` and `tools` capabilities.
- Search-like questions trigger a free research preflight before the model writes the answer.
- Tool calls are shown in the terminal as they happen, then summarized at the end of the rendered answer.
- Conversation context is held in memory for the current run only. After exit, the next run starts without previous chat history.
