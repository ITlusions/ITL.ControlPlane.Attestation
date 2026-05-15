---
layout: default
title: Component Demo
---

# Component Demo

This page demonstrates all available Jekyll components.

{% include breadcrumb.html path="Home,Documentation,Component Demo" %}

---

## Alerts

{% include alert.html type="info" title="Information" content="This is an informational alert. Use it to highlight important details." %}

{% include alert.html type="warning" content="This is a warning alert without a title. Be cautious!" %}

{% include alert.html type="success" title="Success!" content="Your operation completed successfully. Everything is working as expected." %}

{% include alert.html type="danger" title="Critical Error" content="This is a critical error that requires immediate attention." %}

---

## Buttons

<div style="display: flex; gap: 1rem; flex-wrap: wrap; margin: 2rem 0;">
{% include button.html text="Primary Button" link="#" style="primary" %}
{% include button.html text="Secondary" link="#" style="secondary" %}
{% include button.html text="Success" link="#" style="success" %}
{% include button.html text="Danger" link="#" style="danger" %}
{% include button.html text="Outline" link="#" style="outline" %}
</div>

<div style="display: flex; gap: 1rem; flex-wrap: wrap; margin: 2rem 0;">
{% include button.html text="Small" link="#" style="primary" size="small" %}
{% include button.html text="Medium" link="#" style="primary" size="medium" %}
{% include button.html text="Large" link="#" style="primary" size="large" %}
</div>

<div style="display: flex; gap: 1rem; flex-wrap: wrap; margin: 2rem 0;">
{% include button.html text="With Icon" link="#" style="primary" %}
{% include button.html text="GitHub" link="https://github.com" style="secondary" target="_blank" %}
</div>

---

## Badges

<div style="display: flex; gap: 0.75rem; flex-wrap: wrap; margin: 2rem 0;">
{% include badge.html text="v2.0.0" color="success" %}
{% include badge.html text="Beta" color="warning" %}
{% include badge.html text="Deprecated" color="danger" %}
{% include badge.html text="New Feature" color="info" %}
{% include badge.html text="Stable" color="muted" %}
</div>

<div style="display: flex; gap: 0.75rem; flex-wrap: wrap; margin: 2rem 0;">
{% include badge.html text="Small" color="info" size="small" %}
{% include badge.html text="Medium" color="info" size="medium" %}
{% include badge.html text="Large" color="info" size="large" %}
</div>

---

## Cards

{% capture cards %}
{% include card.html 
   title="Secret Vault" 
   description="TPM-bound encrypted secrets with AES-256-GCM encryption. Hardware-rooted key derivation using HKDF-SHA256."
   link="/EXTENSIONS#secret-vault"
   tags="encryption,TPM,secrets"
   badge="v2.0.0"
   badge_color="success"
%}

{% include card.html 
   title="Webhooks" 
   description="HTTP webhook delivery for attestation events with HMAC-SHA256 signatures for secure event notifications."
   link="/EXTENSIONS#webhooks"
   tags="webhooks,events,HMAC"
   badge="v1.0.0"
   badge_color="info"
%}

{% include card.html 
   title="Metrics" 
   description="Prometheus-compatible metrics endpoint exposing attestation statistics and operational metrics."
   link="/EXTENSIONS#metrics"
   tags="metrics,prometheus,monitoring"
   badge="v1.0.0"
   badge_color="info"
%}
{% endcapture %}
{% include grid.html content=cards columns="3" gap="large" %}

---

## Link Cards

{% include link-card.html 
   title="Architecture Documentation" 
   description="Complete system design, extension architecture, and technical specifications"
   link="/ARCHITECTURE"
%}

{% include link-card.html 
   title="Security Guide" 
   description="Threat model, security controls, and hardening recommendations"
   link="/SECURITY"
%}

{% include link-card.html 
   title="GitHub Repository" 
   description="Source code, issues, and contributions"
   link="https://github.com/ITlusions/ITL.ControlPlane.Attestation"
   external="true"
%}

---

## Code Blocks

{% capture bash_code %}
# Clone repository
git clone https://github.com/ITlusions/ITL.ControlPlane.Attestation.git
cd ITL.ControlPlane.Attestation

# Start services
docker compose up -d

# View logs
docker compose logs -f attestation
{% endcapture %}
{% include code-block.html code=bash_code language="bash" title="Installation" %}

{% capture python_code %}
from attestation.core.app import create_app

# Create FastAPI application
app = create_app()

# Register machine
@app.post("/register")
async def register_machine(ek_cert: str):
    return {"status": "registered"}
{% endcapture %}
{% include code-block.html code=python_code language="python" filename="main.py" %}

{% capture yaml_code %}
version: '3.8'
services:
  attestation:
    image: itlusions/attestation:latest
    ports:
      - "9000:9000"
    environment:
      - DATABASE_URL=postgresql://...
{% endcapture %}
{% include code-block.html code=yaml_code language="yaml" filename="docker-compose.yml" %}

---

## Grid Layouts

### 2-Column Grid

{% capture two_col %}
{% include card.html title="Column 1" description="First column content with equal width distribution" %}
{% include card.html title="Column 2" description="Second column content with responsive layout" %}
{% endcapture %}
{% include grid.html content=two_col columns="2" gap="medium" %}

### 4-Column Grid

{% capture four_col %}
{% include card.html title="Col 1" description="Small card" %}
{% include card.html title="Col 2" description="Small card" %}
{% include card.html title="Col 3" description="Small card" %}
{% include card.html title="Col 4" description="Small card" %}
{% endcapture %}
{% include grid.html content=four_col columns="4" gap="small" %}

---

## Combining Components

You can nest components for rich layouts:

{% include alert.html type="info" title="Quick Start Guide" content="Follow these steps to get started with ITL.ControlPlane.Attestation." %}

{% capture install %}
docker compose up -d
{% endcapture %}
{% include code-block.html code=install language="bash" title="Step 1: Start Services" %}

{% capture verify %}
curl http://localhost:9000/health
{% endcapture %}
{% include code-block.html code=verify language="bash" title="Step 2: Verify Installation" %}

<div style="margin-top: 2rem;">
{% include button.html text="View Full Documentation" link="/README" style="primary" %}
{% include button.html text="API Reference" link="/ENDPOINTS" style="secondary" %}
</div>

---

## Documentation

For component usage and parameters, see {% include badge.html text="COMPONENTS.md" color="info" %} in the `_includes` directory.
