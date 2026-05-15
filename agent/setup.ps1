# Quick Setup Script for Attestation Support Agent
# This script helps you get started with the agent

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "ITL.ControlPlane.Attestation Support Agent - Setup" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""

# Check Python
Write-Host "🔍 Checking Python installation..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python not found. Please install Python 3.10+ first." -ForegroundColor Red
    exit 1
}

# Check if virtual environment exists
if (Test-Path "venv") {
    Write-Host "✅ Virtual environment already exists" -ForegroundColor Green
} else {
    Write-Host "📦 Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
    Write-Host "✅ Virtual environment created" -ForegroundColor Green
}

# Activate virtual environment
Write-Host "🔧 Activating virtual environment..." -ForegroundColor Yellow
& ".\venv\Scripts\Activate.ps1"

# Install dependencies
Write-Host "📥 Installing dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt --quiet
Write-Host "✅ Dependencies installed" -ForegroundColor Green

# Create .env if it doesn't exist
if (-not (Test-Path ".env")) {
    Write-Host "📝 Creating .env file from template..." -ForegroundColor Yellow
    Copy-Item ".env.template" ".env"
    Write-Host "✅ .env file created" -ForegroundColor Green
} else {
    Write-Host "✅ .env file already exists" -ForegroundColor Green
}

Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "Setup Complete! 🎉" -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""

# Check for Ollama
Write-Host "🔍 Checking for Ollama (local model)..." -ForegroundColor Yellow
try {
    $ollamaCheck = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -Method GET -UseBasicParsing -ErrorAction Stop
    $models = ($ollamaCheck.Content | ConvertFrom-Json).models
    
    if ($models -and $models.name -contains "llama3.2:3b") {
        Write-Host "✅ Ollama is running with llama3.2:3b model" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Ollama is running but llama3.2:3b model not found" -ForegroundColor Yellow
        Write-Host "   Run: ollama pull llama3.2:3b" -ForegroundColor Cyan
    }
} catch {
    Write-Host "❌ Ollama not detected. Install it to use local mode:" -ForegroundColor Red
    Write-Host "   https://ollama.com/download/windows" -ForegroundColor Cyan
    Write-Host "   Then run: ollama pull llama3.2:3b" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. If using local mode (default):" -ForegroundColor White
Write-Host "   - Make sure Ollama is running: ollama serve" -ForegroundColor Cyan
Write-Host "   - Pull a model: ollama pull llama3.2:3b" -ForegroundColor Cyan
Write-Host ""
Write-Host "2. Start the agent:" -ForegroundColor White
Write-Host "   - CLI mode:    python agent.py --cli" -ForegroundColor Cyan
Write-Host "   - Server mode: python agent.py --server" -ForegroundColor Cyan
Write-Host ""
Write-Host "3. Or press F5 in VS Code to debug" -ForegroundColor White
Write-Host ""
Write-Host "For help: python agent.py --help" -ForegroundColor Yellow
Write-Host ""
