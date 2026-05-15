#!/bin/bash
# Quick Setup Script for Attestation Support Agent

echo "====================================================================="
echo "ITL.ControlPlane.Attestation Support Agent - Setup"
echo "====================================================================="
echo ""

# Check Python
echo "🔍 Checking Python installation..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo "✅ $PYTHON_VERSION"
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_VERSION=$(python --version)
    echo "✅ $PYTHON_VERSION"
    PYTHON_CMD="python"
else
    echo "❌ Python not found. Please install Python 3.10+ first."
    exit 1
fi

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo "✅ Virtual environment already exists"
else
    echo "📦 Creating virtual environment..."
    $PYTHON_CMD -m venv venv
    echo "✅ Virtual environment created"
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt --quiet
echo "✅ Dependencies installed"

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file from template..."
    cp .env.template .env
    echo "✅ .env file created"
else
    echo "✅ .env file already exists"
fi

echo ""
echo "====================================================================="
echo "Setup Complete! 🎉"
echo "====================================================================="
echo ""

# Check for Ollama
echo "🔍 Checking for Ollama (local model)..."
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    MODELS=$(curl -s http://localhost:11434/api/tags | grep -o '"llama3.2:3b"')
    if [ -n "$MODELS" ]; then
        echo "✅ Ollama is running with llama3.2:3b model"
    else
        echo "⚠️  Ollama is running but llama3.2:3b model not found"
        echo "   Run: ollama pull llama3.2:3b"
    fi
else
    echo "❌ Ollama not detected. Install it to use local mode:"
    echo "   macOS: brew install ollama"
    echo "   Linux: curl -fsSL https://ollama.com/install.sh | sh"
    echo "   Then run: ollama pull llama3.2:3b"
fi

echo ""
echo "====================================================================="
echo "Next Steps:"
echo "====================================================================="
echo ""
echo "1. If using local mode (default):"
echo "   - Make sure Ollama is running: ollama serve"
echo "   - Pull a model: ollama pull llama3.2:3b"
echo ""
echo "2. Start the agent:"
echo "   - CLI mode:    python agent.py --cli"
echo "   - Server mode: python agent.py --server"
echo ""
echo "3. Or press F5 in VS Code to debug"
echo ""
echo "For help: python agent.py --help"
echo ""
