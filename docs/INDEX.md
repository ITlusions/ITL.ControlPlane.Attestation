---
layout: default
title: Documentation Index
description: Complete documentation for ITL.ControlPlane.Attestation
---

# Documentation Index

> This index ensures all documentation pages are included in the Jekyll build and search index.

---

## Core Documentation

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.5rem; margin: 2rem 0;">
  <a href="{{ '/ARCHITECTURE' | relative_url }}" style="display: block; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.5rem; text-decoration: none; transition: all 0.2s;">
    <h3 style="color: var(--accent2); margin: 0 0 0.5rem 0; font-size: 1.1rem;">Architecture</h3>
    <p style="color: var(--muted); margin: 0; font-size: 0.9rem;">System architecture, data flow, and design decisions</p>
  </a>
  
  <a href="{{ '/ENDPOINTS' | relative_url }}" style="display: block; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.5rem; text-decoration: none; transition: all 0.2s;">
    <h3 style="color: var(--accent2); margin: 0 0 0.5rem 0; font-size: 1.1rem;">API Reference</h3>
    <p style="color: var(--muted); margin: 0; font-size: 0.9rem;">Complete REST API endpoint documentation</p>
  </a>
  
  <a href="{{ '/TPM_EXPLAINED' | relative_url }}" style="display: block; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.5rem; text-decoration: none; transition: all 0.2s;">
    <h3 style="color: var(--accent2); margin: 0 0 0.5rem 0; font-size: 1.1rem;">TPM Explained</h3>
    <p style="color: var(--muted); margin: 0; font-size: 0.9rem;">Understanding TPM 2.0, EK certificates, and hardware security</p>
  </a>
  
  <a href="{{ '/SECURITY' | relative_url }}" style="display: block; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.5rem; text-decoration: none; transition: all 0.2s;">
    <h3 style="color: var(--accent2); margin: 0 0 0.5rem 0; font-size: 1.1rem;">Security Policy</h3>
    <p style="color: var(--muted); margin: 0; font-size: 0.9rem;">Security model, threat analysis, and reporting vulnerabilities</p>
  </a>
</div>

<style>
  a[style*="background: var(--surface)"]:hover {
    background: var(--surface2) !important;
    border-color: var(--accent) !important;
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(31, 111, 235, 0.2);
  }
</style>

---

## Getting Started

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.5rem; margin: 2rem 0;">
  <a href="{{ '/DEPLOYMENT' | relative_url }}" style="display: block; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.5rem; text-decoration: none; transition: all 0.2s;">
    <h3 style="color: var(--accent2); margin: 0 0 0.5rem 0; font-size: 1.1rem;">Deployment Guide</h3>
    <p style="color: var(--muted); margin: 0; font-size: 0.9rem;">Deploy the attestation service from scratch</p>
  </a>
  
  <a href="{{ '/WALKTHROUGH' | relative_url }}" style="display: block; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.5rem; text-decoration: none; transition: all 0.2s;">
    <h3 style="color: var(--accent2); margin: 0 0 0.5rem 0; font-size: 1.1rem;">Walkthrough</h3>
    <p style="color: var(--muted); margin: 0; font-size: 0.9rem;">Step-by-step guide to first machine registration</p>
  </a>
  
  <a href="{{ '/OPERATIONS' | relative_url }}" style="display: block; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.5rem; text-decoration: none; transition: all 0.2s;">
    <h3 style="color: var(--accent2); margin: 0 0 0.5rem 0; font-size: 1.1rem;">Operations Guide</h3>
    <p style="color: var(--muted); margin: 0; font-size: 0.9rem;">Day-to-day operations, monitoring, and troubleshooting</p>
  </a>
</div>

---

## Advanced Topics

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.5rem; margin: 2rem 0;">
  <a href="{{ '/EXTENSIONS' | relative_url }}" style="display: block; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.5rem; text-decoration: none; transition: all 0.2s;">
    <h3 style="color: var(--accent2); margin: 0 0 0.5rem 0; font-size: 1.1rem;">Extensions</h3>
    <p style="color: var(--muted); margin: 0; font-size: 0.9rem;">Custom authentication providers and integrations</p>
  </a>
  
  <a href="{{ '/COMPONENTS_DEMO' | relative_url }}" style="display: block; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.5rem; text-decoration: none; transition: all 0.2s;">
    <h3 style="color: var(--accent2); margin: 0 0 0.5rem 0; font-size: 1.1rem;">Component Demo</h3>
    <p style="color: var(--muted); margin: 0; font-size: 0.9rem;">Live examples of all documentation components</p>
  </a>
</div>

---

## Quick Stats

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin: 2rem 0;">
  <div style="background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 2rem; text-align: center;">
    <div style="font-size: 2.5rem; font-weight: 700; color: var(--accent2);">12</div>
    <div style="font-size: 0.9rem; color: var(--muted); margin-top: 0.5rem;">Documentation Pages</div>
  </div>
  <div style="background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 2rem; text-align: center;">
    <div style="font-size: 2.5rem; font-weight: 700; color: var(--success);">9</div>
    <div style="font-size: 0.9rem; color: var(--muted); margin-top: 0.5rem;">Navigation Links</div>
  </div>
  <div style="background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 2rem; text-align: center;">
    <div style="font-size: 2.5rem; font-weight: 700; color: #d29922;">15+</div>
    <div style="font-size: 0.9rem; color: var(--muted); margin-top: 0.5rem;">API Endpoints</div>
  </div>
</div>

---

## External Resources

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.5rem; margin: 2rem 0;">
  <a href="https://github.com/ITlusions/ITL.ControlPlane.Attestation" target="_blank" rel="noopener" style="display: flex; align-items: center; gap: 1rem; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.5rem; text-decoration: none; transition: all 0.2s;">
    <svg width="40" height="40" viewBox="0 0 24 24" fill="currentColor" style="color: var(--muted); flex-shrink: 0;">
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844a9.59 9.59 0 0 1 2.504.337c1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.02 10.02 0 0 0 22 12.017C22 6.484 17.522 2 12 2z"/>
    </svg>
    <div>
      <h3 style="color: var(--accent2); margin: 0 0 0.25rem 0; font-size: 1.1rem;">GitHub Repository</h3>
      <p style="color: var(--muted); margin: 0; font-size: 0.85rem;">View source code and contribute</p>
    </div>
  </a>
  
  <a href="https://github.com/ITlusions/ITL.Github" target="_blank" rel="noopener" style="display: flex; align-items: center; gap: 1rem; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.5rem; text-decoration: none; transition: all 0.2s;">
    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color: var(--muted); flex-shrink: 0;">
      <path d="M12 2L2 7l10 5 10-5-10-5z"/>
      <path d="M2 17l10 5 10-5"/>
      <path d="M2 12l10 5 10-5"/>
    </svg>
    <div>
      <h3 style="color: var(--accent2); margin: 0 0 0.25rem 0; font-size: 1.1rem;">ITL Component Library</h3>
      <p style="color: var(--muted); margin: 0; font-size: 0.85rem;">Reusable Jekyll components for all ITL projects</p>
    </div>
  </a>
</div>

---

## About This Site

> **Jekyll-powered Documentation** — This site is built with Jekyll and uses a custom dark theme inspired by Azure Portal for consistent styling across all ITL projects.

**Features:**
- **Azure Portal dark theme** — Professional dark mode with blue accents
- **Fully responsive design** — Works perfectly on mobile, tablet, and desktop
- **SEO optimized** — Structured data and meta tags for search engines
- **Auto-deployed** — GitHub Actions automatically build and deploy
- **Accessible** — WCAG 2.1 AA compliant design

---

<div style="display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap; margin-top: 3rem;">
  <a href="{{ '/' | relative_url }}" style="display: inline-flex; align-items: center; gap: 0.5rem; background: var(--accent); color: white; padding: 0.75rem 1.5rem; border-radius: 6px; text-decoration: none; font-weight: 600; transition: all 0.2s;">
    ← Return to Home
  </a>
  <a href="https://github.com/ITlusions/ITL.ControlPlane.Attestation" target="_blank" rel="noopener" style="display: inline-flex; align-items: center; gap: 0.5rem; background: var(--surface); border: 1px solid var(--border); color: var(--text); padding: 0.75rem 1.5rem; border-radius: 6px; text-decoration: none; font-weight: 600; transition: all 0.2s;">
    View on GitHub →
  </a>
</div>
