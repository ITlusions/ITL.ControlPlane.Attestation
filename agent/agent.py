"""
ITL.ControlPlane.Attestation Support Agent

Local AI assistant using OpenAI SDK (works with Ollama and Azure)

Features:
- Interactive CLI chat with documentation context
- Conversation memory (save/resume chat history)
- Model selection via --model flag
- Response streaming for better UX
- Auto-retry with exponential backoff
- Minimal logging (clean output)
"""

import os
import sys
import json
import asyncio
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()


class ConversationManager:
    """Manage conversation history with save/load to JSON."""
    
    def __init__(self, history_dir: Path):
        self.history_dir = history_dir
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.current_file: Optional[Path] = None
        self.messages: List[Dict[str, str]] = []
    
    def list_conversations(self) -> List[tuple[str, Path]]:
        """List all saved conversations."""
        conversations = []
        for file in sorted(self.history_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                timestamp = data.get("timestamp", file.stem)
                conversations.append((timestamp, file))
            except Exception:
                continue
        return conversations
    
    def load_conversation(self, file_path: Path) -> List[Dict[str, str]]:
        """Load conversation from JSON file."""
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            self.current_file = file_path
            self.messages = data.get("messages", [])
            return self.messages
        except Exception as e:
            print(f"⚠️  Could not load conversation: {e}")
            return []
    
    def save_conversation(self):
        """Save current conversation to JSON file."""
        if not self.messages:
            return
        
        try:
            if not self.current_file:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                self.current_file = self.history_dir / f"conversation_{timestamp}.json"
            
            data = {
                "timestamp": datetime.now().isoformat(),
                "model": os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
                "message_count": len(self.messages),
                "messages": self.messages,
            }
            
            self.current_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"⚠️  Could not save conversation: {e}")
    
    def add_message(self, role: str, content: str):
        """Add message to conversation."""
        self.messages.append({"role": role, "content": content})


async def chat_with_retry(
    client: AsyncOpenAI,
    model: str,
    messages: List[Dict[str, str]],
    max_retries: int = 3,
) -> Optional[str]:
    """Chat with Ollama with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
                stream=True,  # Enable streaming
            )
            
            # Collect streamed response
            full_response = ""
            print("\nAgent: ", end="", flush=True)
            
            async for chunk in response:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    print(content, end="", flush=True)
                    full_response += content
            
            print("\n")  # Newline after response
            return full_response
            
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                await asyncio.sleep(wait_time)
            else:
                print(f"\n❌ Error after {max_retries} attempts: {e}\n")
                return None


async def main():
    """Main CLI chat loop."""
    parser = argparse.ArgumentParser(
        description="ITL.ControlPlane.Attestation Support Agent"
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
        help="Ollama model to use (default: llama3.2:3b)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume previous conversation",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List saved conversations and exit",
    )
    
    args = parser.parse_args()
    
    # Setup conversation manager
    history_dir = Path(__file__).parent / "conversations"
    conv_manager = ConversationManager(history_dir)
    
    # List conversations and exit
    if args.list:
        conversations = conv_manager.list_conversations()
        if not conversations:
            print("No saved conversations found.")
            return
        
        print("\n📚 Saved Conversations:\n")
        for i, (timestamp, file_path) in enumerate(conversations, 1):
            print(f"  {i}. {timestamp} ({file_path.name})")
        print()
        return
    
    # Resume previous conversation
    if args.resume:
        conversations = conv_manager.list_conversations()
        if conversations:
            print("\n📚 Select conversation to resume:\n")
            for i, (timestamp, _) in enumerate(conversations, 1):
                print(f"  {i}. {timestamp}")
            print(f"  0. Start new conversation")
            print()
            
            try:
                choice = int(input("Choice: ").strip())
                if 1 <= choice <= len(conversations):
                    _, file_path = conversations[choice - 1]
                    messages = conv_manager.load_conversation(file_path)
                    print(f"\n✅ Resumed conversation from {file_path.name}\n")
                    
                    # Show conversation history
                    for msg in messages:
                        if msg["role"] == "user":
                            print(f"You: {msg['content']}")
                        elif msg["role"] == "assistant":
                            print(f"Agent: {msg['content']}\n")
            except (ValueError, KeyboardInterrupt):
                print("\nStarting new conversation...\n")
    
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
    
    client = AsyncOpenAI(
        base_url=endpoint,
        api_key="ollama",  # Ollama doesn't require real API key
    )
    
    print("🚀 ITL.ControlPlane.Attestation Support Agent")
    print(f"📍 Endpoint: {endpoint}")
    print(f"🤖 Model: {args.model}")
    print(f"📚 Loaded {len(list(docs_path.glob('*.md')))} documentation files")
    print(f"💾 Conversations saved to: {history_dir}")
    print()
    print("=" * 60)
    print("Ask me anything about attestation setup, troubleshooting, or configuration.")
    print()
    print("Commands:")
    print("  /save    - Save current conversation")
    print("  /clear   - Clear conversation history")
    print("  exit     - Quit (auto-saves)")
    print("=" * 60)
    print()
    
    # Initialize conversation if not resumed
    if not conv_manager.messages:
        conv_manager.add_message("system", system_prompt)
    
    # Chat loop
    try:
        while True:
            user_input = input("You: ").strip()
            
            if not user_input:
                continue
            
            # Handle commands
            if user_input.lower() == "/save":
                conv_manager.save_conversation()
                print("💾 Conversation saved!\n")
                continue
            
            if user_input.lower() == "/clear":
                conv_manager.messages = [{"role": "system", "content": system_prompt}]
                conv_manager.current_file = None
                print("🧹 Conversation cleared!\n")
                continue
            
            if user_input.lower() in ["exit", "quit", "bye"]:
                conv_manager.save_conversation()
                print("\n💾 Conversation saved!")
                print("👋 Goodbye!\n")
                break
            
            # Add user message
            conv_manager.add_message("user", user_input)
            
            # Get AI response with retry
            assistant_message = await chat_with_retry(
                client=client,
                model=args.model,
                messages=conv_manager.messages,
            )
            
            if assistant_message:
                conv_manager.add_message("assistant", assistant_message)
    
    except KeyboardInterrupt:
        conv_manager.save_conversation()
        print("\n\n💾 Conversation saved!")
        print("👋 Goodbye!\n")


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
            except Exception:
                pass  # Minimal logging - skip errors silently
    
    return "\n\n---\n\n".join(knowledge) if knowledge else "No documentation available"


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"\n❌ Fatal error: {e}\n", file=sys.stderr)
        sys.exit(1)
