---
layout: default
title: Documentation Index
description: Complete documentation for ITL.ControlPlane.Attestation
---

# Documentation Index

{% assign doc_pages = site.pages | where_exp: "p", "p.category != nil" | sort: "title" %}
{% assign categories = doc_pages | map: "category" | uniq | sort %}

{% for cat in categories %}
## {{ cat }}

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1rem; margin: 1.5rem 0 2.5rem;">
{% assign cat_pages = doc_pages | where: "category", cat %}
{% for p in cat_pages %}
  <a href="{{ p.url | relative_url }}" style="display: block; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem 1.5rem; text-decoration: none; transition: all 0.2s;">
    <strong style="color: var(--accent2); font-size: 1rem;">{{ p.title }}</strong>
    {% if p.description %}<p style="color: var(--muted); margin: 0.4rem 0 0; font-size: 0.875rem;">{{ p.description }}</p>{% endif %}
  </a>
{% endfor %}
</div>

{% endfor %}

<style>
  a[style*="background: var(--surface)"]:hover {
    background: var(--surface2) !important;
    border-color: var(--accent) !important;
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(31, 111, 235, 0.15);
  }
</style>
