# Jekyll Components Documentation

This directory contains reusable Jekyll components (Liquid includes) for the ITL.ControlPlane.Attestation documentation.

## Available Components

### 1. Alert (`alert.html`)
Display informational, warning, success, or danger alerts.

```liquid
{% include alert.html type="info" title="Note" content="Your message here" %}
{% include alert.html type="warning" content="Warning message" %}
{% include alert.html type="success" title="Success!" content="Operation completed" %}
{% include alert.html type="danger" content="Critical issue" %}
```

**Parameters:**
- `type`: `info` | `warning` | `success` | `danger` (default: `info`)
- `title`: Optional heading text
- `content`: Alert message (required)
- `icon`: Optional custom icon (default: auto based on type)

---

### 2. Button (`button.html`)
Styled action buttons with multiple styles.

```liquid
{% include button.html text="Get Started" link="/docs" style="primary" %}
{% include button.html text="View on GitHub" link="https://github.com/..." style="secondary" icon="🔗" %}
{% include button.html text="Download" link="/releases" style="success" target="_blank" %}
```

**Parameters:**
- `text`: Button label (required)
- `link`: URL (required)
- `style`: `primary` | `secondary` | `success` | `danger` | `outline` (default: `primary`)
- `icon`: Optional icon/emoji before text
- `target`: Optional link target (`_blank`, `_self`, etc.)
- `size`: `small` | `medium` | `large` (default: `medium`)

---

### 3. Card (`card.html`)
Feature cards with icon, title, description, and tags.

```liquid
{% include card.html 
   title="Secret Vault" 
   icon="🔒"
   description="TPM-bound encrypted secrets with AES-256-GCM"
   link="/docs/secret-vault"
   tags="encryption,TPM,secrets"
   badge="v2.0.0"
   badge_color="success"
%}
```

**Parameters:**
- `title`: Card heading (required)
- `icon`: Icon/emoji (optional)
- `description`: Card description text (required)
- `link`: Optional link URL
- `tags`: Comma-separated tags (optional)
- `badge`: Optional badge text (e.g., "v2.0.0", "New", "Beta")
- `badge_color`: `success` | `warning` | `info` (default: `info`)

---

### 4. Badge (`badge.html`)
Small status/version badges.

```liquid
{% include badge.html text="v2.0.0" color="success" %}
{% include badge.html text="Beta" color="warning" %}
{% include badge.html text="Deprecated" color="danger" %}
{% include badge.html text="New" color="info" icon="✨" %}
```

**Parameters:**
- `text`: Badge text (required)
- `color`: `success` | `warning` | `danger` | `info` | `muted` (default: `info`)
- `icon`: Optional icon/emoji before text
- `size`: `small` | `medium` | `large` (default: `medium`)

---

### 5. Code Block (`code-block.html`)
Syntax-highlighted code blocks with copy button.

```liquid
{% capture code %}
git clone https://github.com/ITlusions/ITL.ControlPlane.Attestation.git
cd ITL.ControlPlane.Attestation
docker compose up -d
{% endcapture %}
{% include code-block.html code=code language="bash" title="Installation" %}
```

**Parameters:**
- `code`: Code content (required)
- `language`: `bash` | `python` | `yaml` | `json` | `powershell` (default: `bash`)
- `title`: Optional code block title
- `filename`: Optional filename to display

---

### 6. Breadcrumb (`breadcrumb.html`)
Navigation breadcrumbs.

```liquid
{% include breadcrumb.html path="Home,Documentation,Architecture" %}
```

**Parameters:**
- `path`: Comma-separated breadcrumb items

---

### 7. Grid (`grid.html`)
Responsive grid layout for cards and other content.

```liquid
{% capture grid_content %}
  {% include card.html title="Card 1" description="..." %}
  {% include card.html title="Card 2" description="..." %}
  {% include card.html title="Card 3" description="..." %}
{% endcapture %}
{% include grid.html content=grid_content columns="3" gap="large" %}
```

**Parameters:**
- `content`: HTML content to wrap in grid (required)
- `columns`: `1` | `2` | `3` | `4` | `auto` (default: `3`)
- `gap`: `small` | `medium` | `large` (default: `medium`)

---

### 8. Link Card (`link-card.html`)
Clickable card for documentation links.

```liquid
{% include link-card.html 
   title="Architecture Guide" 
   description="System design and technical architecture"
   link="/ARCHITECTURE"
   icon="🏗️"
%}
```

**Parameters:**
- `title`: Link title (required)
- `description`: Description text (required)
- `link`: Target URL (required)
- `icon`: Icon/emoji (optional)
- `external`: `true`/`false` - adds external link indicator (default: `false`)

---

## Usage in Markdown Files

Add to your Markdown file front matter:

```yaml
---
layout: default
title: My Page
---
```

Then use components anywhere in the Markdown:

```markdown
# My Documentation Page

{% include alert.html type="info" content="This is important information" %}

## Installation

{% capture install_code %}
docker compose up -d
{% endcapture %}
{% include code-block.html code=install_code language="bash" %}

## Features

{% capture features %}
  {% include card.html title="Feature 1" description="Description 1" %}
  {% include card.html title="Feature 2" description="Description 2" %}
  {% include card.html title="Feature 3" description="Description 3" %}
{% endcapture %}
{% include grid.html content=features columns="3" %}
```

---

## Color Palette

Components use these standard colors:

- **Primary**: `#1f6feb` (Azure blue)
- **Success**: `#3fb950` (green)
- **Warning**: `#d29922` (yellow/orange)
- **Danger**: `#f85149` (red)
- **Info**: `#58a6ff` (light blue)
- **Muted**: `#8b949e` (gray)
- **Background**: `#0d1117` (dark)
- **Surface**: `#161b22` (dark gray)
- **Border**: `#30363d` (medium gray)
- **Text**: `#e6edf3` (white)

---

## Examples

See `docs/index.html` for live examples of all components in use.
