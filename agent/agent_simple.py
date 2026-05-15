"""
ITL.ControlPlane.Attestation Support Agent - Simple Version

Local AI assistant using OpenAI SDK (works with Ollama and Azure)
"""

import os
import asyncio
from pathlib import Path
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()


async def main():
    """Simple CLI chat with Ollama."""
    
    # Load documentation
    docs_path = Path(__file__).parent.parent / "docs"
    knowledge = load_docs(docs_path)
    
    # System prompt with documentation
    system_prompt = f"""You are an expert support agent for ITL.ControlPlane.Attestation - a TPM-based hardware identity registration and attestation service.

Help users with:
- Setup and configuration
- Troubleshooting TPM/registration issues  
- Understanding flows (USB agent, self-register)
- Environment variables
- API endpoints

Be concise, provide examples, reference documentation when helpful.

## Documentation

{knowledge}
"""
    
    # Setup OpenAI client (works with Ollama)
    endpoint = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434/v1")
    model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    
    client = AsyncOpenAI(
        base_url=endpoint,
        api_key="ollama",  # Ollama doesn't require real API key
    )
    
    print("🚀 Starting Attestation Support Agent (Ollama)")
    print(f"📍 Endpoint: {endpoint}")
    print(f"🤖 Model: {model}")
    print(f"📚 Loaded {len(list(docs_path.glob('*.md')))} documentation files")
    print()
    print("=" * 60)
    print("ITL.ControlPlane.Attestation Support Agent")
    print("=" * 60)
    print()
    print("Ask me anything about attestation setup, troubleshooting, or configuration.")
    print("Type 'exit' to quit")
    print()
    
    # Conversation history
    messages = [{"role": "system", "content": system_prompt}]
    
    # Chat loop
    while True:
        user_input = input("You: ").strip()
        
        if not user_input:
            continue
            
        if user_input.lower() in ["exit", "quit", "bye"]:
            print("\n👋 Goodbye!")
            break
        
        # Add user message
        messages.append({"role": "user", "content": user_input})
        
        # Get AI response
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
            )
            
            assistant_message = response.choices[0].message.content
            messages.append({"role": "assistant", "content": assistant_message})
            
            print(f"\nAgent: {assistant_message}\n")
            
        except Exception as e:
            print(f"\n❌ Error: {e}\n")


def load_docs(docs_path: Path) -> str:
    """Load documentation files."""
    knowledge = []
    
    doc_files = [
        "README.md",
        "ARCHITECTURE.md",
        "DEPLOYMENT.md",
        "OPERATIONS.md",
        "TPM_EXPLAINED.md",
        "ENDPOINTS.md",
        "WALKTHROUGH.md",
    ]
    
    for doc_file in doc_files:
        doc_path = docs_path / doc_file
        if doc_path.exists():
            try:
                content = doc_path.read_text(encoding="utf-8")
                # Truncate long docs to fit in context
                if len(content) > 5000:
                    content = content[:5000] + "\n\n[... truncated for brevity ...]"
                knowledge.append(f"### {doc_file}\n\n{content}")
            except Exception as e:
                print(f"⚠️  Could not read {doc_file}: {e}")
    
    return "\n\n---\n\n".join(knowledge) if knowledge else "No documentation available"


if __name__ == "__main__":
    asyncio.run(main())
