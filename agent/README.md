# Attestation Support Agent

Local AI assistant for ITL.ControlPlane.Attestation that helps with setup, configuration, troubleshooting, and understanding the attestation service.

## Features

- ✅ **Setup Guidance** — Step-by-step configuration help
- ✅ **Troubleshooting** — Debug TPM, registration, and attestation issues
- ✅ **Flow Explanation** — Understand USB agent and self-register flows
- ✅ **Environment Variables** — Get correct config for your setup
- ✅ **API Documentation** — Interactive endpoint reference
- ✅ **Local First** — Runs with Ollama (no cloud required)
- ✅ **Conversation Memory** — Save/resume chat history
- ✅ **Model Selection** — Switch models with `--model` flag
- ✅ **Streaming Responses** — Real-time word-by-word output
- ✅ **Auto-Retry** — Exponential backoff for reliability

## Quick Start

### Prerequisites

**Option 1: Local Mode (Recommended)**
```bash
# Install Ollama
# Windows: https://ollama.com/download/windows
# macOS: brew install ollama
# Linux: curl -fsSL https://ollama.com/install.sh | sh

# Pull a small model
ollama pull llama3.2:3b
# OR
ollama pull phi3:mini
```

**Option 2: Foundry Mode**
```bash
# Requires Azure AI Foundry project with deployed model
# Configure in .env file
```

### Installation

```bash
cd agent/

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Configure
copy .env.template .env
# Edit .env if needed (defaults work for local Ollama)
```

### Run

```bash
# Start new conversation
python agent.py

# Use specific model
python agent.py --model phi3:mini

# Resume previous conversation
python agent.py --resume

# List saved conversations
python agent.py --list
```

## Usage Examples

### Basic Chat

```
You: How do I set up the attestation service?
Agent: Let me guide you through the setup process...

You: My TPM registration is failing, what should I check?
Agent: Let's troubleshoot this step by step...

You: What environment variables do I need?
Agent: Here are the key environment variables...

You: Explain the USB agent flow
Agent: The USB agent flow works like this...
```

### Commands

```
/save    — Save current conversation to JSON
/clear   — Clear conversation history and start fresh
exit     — Quit (auto-saves conversation)
```

### Conversation Memory

All conversations are automatically saved to `agent/conversations/` directory:

```bash
# Resume last conversation
python agent.py --resume

# List all saved conversations
python agent.py --list

# Conversations are saved as JSON with timestamps
# Example: conversation_20260515_143022.json
```

## Configuration

### Local Mode (Default)

Uses Ollama running locally. No cloud connection needed.

```env
USE_LOCAL_MODEL=true
OLLAMA_ENDPOINT=http://localhost:11434/v1
OLLAMA_MODEL=llama3.2:3b
```

**Recommended Models:**
- `llama3.2:3b` — Fast, accurate, 2GB RAM
- `phi3:mini` — Compact, efficient, 2GB RAM
- `llama3.2:1b` — Ultra-fast, 700MB RAM

### Foundry Mode

Uses Azure AI Foundry project with deployed model.

```env
USE_LOCAL_MODEL=false
AZURE_AI_PROJECT_ENDPOINT=https://your-project.api.azureml.ms
MODEL_DEPLOYMENT_NAME=gpt-4o-mini
```

## Debugging

VS Code launch configurations included for:
- **Local Debugging** — Run with breakpoints
- **AI Toolkit Agent Inspector** — Visual debugging UI

Press F5 in VS Code to start debugging.

## Knowledge Base

The agent has access to all documentation in `../docs/`:
- Architecture overview
- API endpoints
- Deployment guide
- Operations manual
- TPM explanation
- Walkthrough tutorials

## Troubleshooting

### Ollama not responding
```bash
# Check if Ollama is running
curl http://localhost:11434/v1/models

# Start Ollama
ollama serve
```

### Model not found
```bash
# List available models
ollama list

# Pull the model
ollama pull llama3.2:3b
```

### Import errors
```bash
# Reinstall dependencies
pip install -r requirements.txt --upgrade
```

## Architecture

```
agent.py
├── main() — Entry point, mode selection
├── Local Mode
│   ├── Ollama endpoint (localhost:11434)
│   └── AgentsClient with dummy credentials
└── Foundry Mode
    ├── Azure AI Project endpoint
    └── AIProjectClient with DefaultAzureCredential

Knowledge Base
├── load_knowledge_base() — Reads docs/*.md
└── Embedded in agent instructions

Interactive Loop
├── Create thread
├── User input
├── Create message
├── Run agent
└── Display response
```

## Contributing

To extend the agent's capabilities:
1. Update instructions in `agent.py`
2. Add new documentation to `../docs/`
3. Test with both local and Foundry modes

## License

See main project license.
