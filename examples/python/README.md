# Python Examples

These files demonstrate AI API usage patterns that Inferency detects.

## Files

- **chatbot.py** — Three OpenAI GPT-4 calls (chat, summarize, classify). Inferency will flag that the classify function uses an expensive model for a simple task.
- **multi_provider.py** — Mixed OpenAI + Anthropic usage. Shows cross-provider detection.

## Try It

```bash
# Scan for AI API calls
inferency scan examples/python

# Get optimization report
inferency report examples/python

# Export as markdown
inferency report examples/python --format markdown -o report.md
```
