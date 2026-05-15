# Migration Guide: Using Reusable Components

This guide shows how to refactor existing documentation to use the new Jekyll components.

## Before: Plain Markdown

```markdown
## Warning: TPM Required

This service requires TPM 2.0 hardware. Ensure your hardware supports TPM before proceeding.

## Installation

\`\`\`bash
docker compose up -d
\`\`\`

## Features

- **Secret Vault** - TPM-bound encrypted secrets
- **Webhooks** - Event notifications
- **Metrics** - Prometheus monitoring
```

## After: With Components

```liquid
{% include alert.html 
   type="warning" 
   title="TPM Required" 
   content="This service requires TPM 2.0 hardware. Ensure your hardware supports TPM before proceeding." 
%}

## Installation

{% capture install_code %}
docker compose up -d
{% endcapture %}
{% include code-block.html code=install_code language="bash" title="Start Services" %}

## Features

{% capture features %}
{% include card.html 
   title="Secret Vault" 
   description="TPM-bound encrypted secrets with AES-256-GCM encryption"
   link="/EXTENSIONS#secret-vault"
   tags="encryption,TPM"
   badge="v2.0.0"
   badge_color="success"
%}

{% include card.html 
   title="Webhooks" 
   description="HTTP webhook delivery for attestation events with HMAC signatures"
   link="/EXTENSIONS#webhooks"
   tags="webhooks,events"
   badge="v1.0.0"
%}

{% include card.html 
   title="Metrics" 
   description="Prometheus-compatible metrics endpoint"
   link="/EXTENSIONS#metrics"
   tags="monitoring"
   badge="v1.0.0"
%}
{% endcapture %}
{% include grid.html content=features columns="3" %}
```

---

## Common Patterns

### 1. Callouts → Alerts

**Before:**
```markdown
> **Note:** This is important information
```

**After:**
```liquid
{% include alert.html type="info" content="This is important information" %}
```

---

### 2. Code Blocks → Code Component

**Before:**
```markdown
\`\`\`python
def hello():
    print("Hello")
\`\`\`
```

**After:**
```liquid
{% capture code %}
def hello():
    print("Hello")
{% endcapture %}
{% include code-block.html code=code language="python" filename="example.py" %}
```

**Benefits:** Copy button, language badge, optional title/filename

---

### 3. Links → Link Cards

**Before:**
```markdown
- [Architecture](ARCHITECTURE.md) - System design documentation
- [Security](SECURITY.md) - Security guide
```

**After:**
```liquid
{% include link-card.html 
   title="Architecture Documentation" 
   description="System design and technical specifications"
   link="/ARCHITECTURE"
%}

{% include link-card.html 
   title="Security Guide" 
   description="Threat model and security controls"
   link="/SECURITY"
%}
```

---

### 4. Feature Lists → Card Grid

**Before:**
```markdown
## Extensions

### Secret Vault
TPM-bound encrypted secrets.

### Webhooks
Event delivery system.

### Metrics
Prometheus monitoring.
```

**After:**
```liquid
## Extensions

{% capture extensions %}
{% include card.html title="Secret Vault" description="TPM-bound encrypted secrets" %}
{% include card.html title="Webhooks" description="Event delivery system" %}
{% include card.html title="Metrics" description="Prometheus monitoring" %}
{% endcapture %}
{% include grid.html content=extensions columns="3" %}
```

---

### 5. Buttons for CTAs

**Before:**
```markdown
[Get Started →](WALKTHROUGH.md)
```

**After:**
```liquid
{% include button.html text="Get Started" link="/WALKTHROUGH" style="primary" %}
```

---

## Example: Refactored Page

Here's a complete example of a refactored documentation page:

```liquid
---
layout: default
title: Quick Start Guide
---

# Quick Start Guide

{% include breadcrumb.html path="Home,Documentation,Quick Start" %}

{% include alert.html 
   type="info" 
   title="Prerequisites" 
   content="Ensure you have Docker, Docker Compose, and TPM 2.0 hardware available." 
%}

## Installation Steps

### 1. Clone Repository

{% capture clone %}
git clone https://github.com/ITlusions/ITL.ControlPlane.Attestation.git
cd ITL.ControlPlane.Attestation
{% endcapture %}
{% include code-block.html code=clone language="bash" title="Clone the repository" %}

### 2. Configure Environment

{% capture env %}
cp .env.example .env
# Edit .env with your settings
{% endcapture %}
{% include code-block.html code=env language="bash" title="Setup environment" %}

{% include alert.html 
   type="warning" 
   content="Never commit .env files containing secrets to version control." 
%}

### 3. Start Services

{% capture start %}
docker compose up -d
{% endcapture %}
{% include code-block.html code=start language="bash" title="Start all services" %}

### 4. Verify Installation

{% capture verify %}
curl http://localhost:9000/health
{% endcapture %}
{% include code-block.html code=verify language="bash" title="Health check" %}

{% include alert.html 
   type="success" 
   title="Installation Complete!" 
   content="Your attestation service is now running on port 9000." 
%}

## Next Steps

{% capture next_steps %}
{% include link-card.html 
   title="Architecture Guide" 
   description="Learn about the system design and components"
   link="/ARCHITECTURE"
%}

{% include link-card.html 
   title="API Documentation" 
   description="Explore available REST endpoints"
   link="/ENDPOINTS"
%}

{% include link-card.html 
   title="Security Guide" 
   description="Understand the security model"
   link="/SECURITY"
%}
{% endcapture %}
{% include grid.html content=next_steps columns="3" %}

<div style="margin-top: 3rem; text-align: center;">
{% include button.html text="View Full Documentation" link="/README" style="primary" %}
{% include button.html text="Report an Issue" link="https://github.com/ITlusions/ITL.ControlPlane.Attestation/issues" style="secondary" target="_blank" %}
</div>
```

---

## Tips

1. **Use `{%raw%}{% capture %}{%endraw%}` blocks** for multi-line code content
2. **Wrap multiple cards in grids** for consistent layouts
3. **Use alerts** instead of blockquotes for important callouts
4. **Add icons** to make content more scannable
5. **Use badges** to indicate versions, status, or categories
6. **Prefer link-cards over plain links** for richer navigation
7. **Add breadcrumbs** to all documentation pages

---

## Component Reference

See [COMPONENTS.md](_includes/COMPONENTS.md) for complete documentation of all available components and their parameters.
