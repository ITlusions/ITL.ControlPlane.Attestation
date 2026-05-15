---
layout: default
title: Documentation Index
description: Complete documentation for ITL.ControlPlane.Attestation
---

# Documentation Index

{% include breadcrumb.html path="Home,Documentation" %}

{% include alert.html type="info" content="This index ensures all documentation pages are included in the Jekyll build and search index." %}

---

## 📖 Core Documentation

{% capture core_docs %}
{% include link-card.html 
   title="Architecture" 
   description="System architecture, data flow, and design decisions"
   link="ARCHITECTURE"
   icon="🏗️"
%}

{% include link-card.html 
   title="API Reference" 
   description="Complete REST API endpoint documentation"
   link="ENDPOINTS"
   icon="🔌"
%}

{% include link-card.html 
   title="TPM Explained" 
   description="Understanding TPM 2.0, EK certificates, and hardware security"
   link="TPM_EXPLAINED"
   icon="🔒"
%}

{% include link-card.html 
   title="Security Policy" 
   description="Security model, threat analysis, and reporting vulnerabilities"
   link="SECURITY"
   icon="🛡️"
%}
{% endcapture %}
{% include grid.html content=core_docs columns="2" %}

---

## 🚀 Getting Started

{% capture getting_started %}
{% include link-card.html 
   title="Deployment Guide" 
   description="Deploy the attestation service from scratch"
   link="DEPLOYMENT"
   icon="🚢"
%}

{% include link-card.html 
   title="Walkthrough" 
   description="Step-by-step guide to first machine registration"
   link="WALKTHROUGH"
   icon="👣"
%}

{% include link-card.html 
   title="Operations Guide" 
   description="Day-to-day operations, monitoring, and troubleshooting"
   link="OPERATIONS"
   icon="⚙️"
%}
{% endcapture %}
{% include grid.html content=getting_started columns="3" %}

---

## 🔧 Advanced Topics

{% capture advanced %}
{% include link-card.html 
   title="Extensions" 
   description="Custom authentication providers and integrations"
   link="EXTENSIONS"
   icon="🔌"
%}

{% include link-card.html 
   title="Component Migration" 
   description="Migrate documentation to use reusable components"
   link="MIGRATION_GUIDE"
   icon="🔄"
%}

{% include link-card.html 
   title="Component Demo" 
   description="Live examples of all documentation components"
   link="COMPONENTS_DEMO"
   icon="🎨"
%}

{% include link-card.html 
   title="SEO Optimization" 
   description="Search engine optimization setup and verification"
   link="SEO"
   icon="🔍"
%}
{% endcapture %}
{% include grid.html content=advanced columns="2" %}

---

## 📊 Quick Stats

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin: 2rem 0;">
  <div style="background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.5rem; text-align: center;">
    <div style="font-size: 2rem; font-weight: 700; color: #58a6ff;">12</div>
    <div style="font-size: 0.85rem; color: #8b949e; margin-top: 0.25rem;">Documentation Pages</div>
  </div>
  <div style="background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.5rem; text-align: center;">
    <div style="font-size: 2rem; font-weight: 700; color: #3fb950;">8</div>
    <div style="font-size: 0.85rem; color: #8b949e; margin-top: 0.25rem;">Reusable Components</div>
  </div>
  <div style="background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.5rem; text-align: center;">
    <div style="font-size: 2rem; font-weight: 700; color: #d29922;">15+</div>
    <div style="font-size: 0.85rem; color: #8b949e; margin-top: 0.25rem;">API Endpoints</div>
  </div>
</div>

---

## 🔗 External Resources

{% capture external %}
{% include link-card.html 
   title="GitHub Repository" 
   description="View source code and contribute"
   link="https://github.com/ITlusions/ITL.ControlPlane.Attestation"
   icon="🐙"
   external="true"
%}

{% include link-card.html 
   title="ITL Component Library" 
   description="Reusable Jekyll components for all ITL projects"
   link="https://github.com/ITlusions/ITL.Github"
   icon="📦"
   external="true"
%}
{% endcapture %}
{% include grid.html content=external columns="2" %}

---

## 📝 About This Site

{% include alert.html type="success" title="Jekyll-powered Documentation" content="This site is built with Jekyll and uses the ITL component library for consistent styling across all ITL projects." %}

**Features:**
- 🎨 Azure Portal dark theme
- 📱 Fully responsive design
- 🔍 SEO optimized with structured data
- 🚀 Deployed automatically via GitHub Actions
- ♿ WCAG 2.1 AA accessibility compliant

---

<div style="margin-top: 3rem; text-align: center;">
{% include button.html text="Return to Home" link="./" style="primary" icon="🏠" %}
{% include button.html text="View on GitHub" link="https://github.com/ITlusions/ITL.ControlPlane.Attestation" style="secondary" icon="🐙" target="_blank" %}
</div>
