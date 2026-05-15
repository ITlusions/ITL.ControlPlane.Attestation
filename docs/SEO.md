# SEO Configuration Guide

This directory contains SEO optimization files for the ITL.ControlPlane.Attestation documentation site.

## Files

### sitemap.xml
XML sitemap listing all documentation pages with metadata:
- **Location**: Root of docs/ directory
- **URL**: https://itlusions.github.io/ITL.ControlPlane.Attestation/sitemap.xml
- **Purpose**: Helps search engines discover and index all documentation pages

**Update when:**
- Adding new documentation pages
- Changing page URLs or structure
- Major content updates (update `<lastmod>` date)

**Priority levels:**
- 1.0 = Landing page (index.html)
- 0.9 = Critical documentation (ARCHITECTURE, SECURITY, EXTENSIONS)
- 0.8 = Important guides (ENDPOINTS, DEPLOYMENT, OPERATIONS, TPM_EXPLAINED)
- 0.7 = Supporting pages (WALKTHROUGH, README)

### robots.txt
Crawler directives file:
- **Location**: Root of docs/ directory
- **URL**: https://itlusions.github.io/ITL.ControlPlane.Attestation/robots.txt
- **Purpose**: Controls search engine crawler behavior

**Contains:**
- Allow all search engines (Google, Bing, DuckDuckGo, etc.)
- Sitemap location reference
- Polite crawl delay (1 second)
- Optional AI training bot blocking (commented out)

### index.html SEO Elements

**Meta tags added:**
- Description (160 characters max for search results)
- Keywords (relevant terms for discovery)
- Author attribution
- Canonical URL (prevents duplicate content issues)
- Robots directive (index, follow)
- Theme color for mobile browsers

**Open Graph tags** (for social media sharing):
- og:type, og:url, og:title, og:description, og:site_name
- Optimized for Facebook, LinkedIn, Slack previews

**Twitter Card tags** (for Twitter sharing):
- twitter:card, twitter:url, twitter:title, twitter:description
- Uses summary_large_image format

**Structured Data (JSON-LD)**:
- Schema.org SoftwareApplication markup
- Helps Google understand the application type
- Enables rich search results and knowledge graph

## Maintenance Tasks

### When adding a new documentation page:

1. **Update sitemap.xml:**
   ```xml
   <url>
     <loc>https://itlusions.github.io/ITL.ControlPlane.Attestation/NEW_PAGE</loc>
     <lastmod>YYYY-MM-DD</lastmod>
     <changefreq>monthly</changefreq>
     <priority>0.8</priority>
   </url>
   ```

2. **Update index.html docs grid** (if user-facing):
   Add link card in the docs section

3. **Update lastmod dates** in sitemap.xml when making significant content changes

### When deploying to production:

1. Submit sitemap to search engines:
   - **Google Search Console**: https://search.google.com/search-console
   - **Bing Webmaster Tools**: https://www.bing.com/webmasters
   
2. Verify robots.txt is accessible:
   ```bash
   curl https://itlusions.github.io/ITL.ControlPlane.Attestation/robots.txt
   ```

3. Verify sitemap is accessible:
   ```bash
   curl https://itlusions.github.io/ITL.ControlPlane.Attestation/sitemap.xml
   ```

4. Validate structured data:
   - Use Google's Rich Results Test: https://search.google.com/test/rich-results
   - Test URL: https://itlusions.github.io/ITL.ControlPlane.Attestation/

## Monitoring

### Search Console Metrics (check monthly):
- Total impressions and clicks
- Average position in search results
- Click-through rate (CTR)
- Coverage issues (404s, indexing errors)
- Mobile usability warnings

### Target Keywords:
- "TPM attestation"
- "Kubernetes hardware security"
- "TPM 2.0 Kubernetes"
- "Talos Linux attestation"
- "hardware root of trust"
- "EK fingerprint verification"
- "zero-trust Kubernetes"

## SEO Best Practices Applied

**Semantic HTML**: Proper heading hierarchy (h1 → h2 → h3)  
**Meta descriptions**: Unique, 150-160 characters, includes target keywords  
**Canonical URLs**: Prevents duplicate content penalties  
**Mobile-friendly**: Responsive viewport meta tag  
**Structured data**: JSON-LD for rich search results  
**Internal linking**: All docs accessible from landing page  
**Fast loading**: Inline CSS, no external dependencies  
**Sitemap**: XML sitemap with all pages  
**Robots.txt**: Clear crawler directives  
**Social meta tags**: Optimized for sharing on social platforms  

## GitHub Pages Configuration

Ensure your repository has GitHub Pages enabled:

1. Go to repository Settings → Pages
2. Source: Deploy from branch `main` (or `gh-pages`)
3. Folder: `/docs`
4. Custom domain (optional): Configure CNAME file

## Performance Tips

- Keep sitemap under 50,000 URLs
- Update `<lastmod>` dates to signal freshness
- Use descriptive, keyword-rich URLs
- Maintain fast page load times (<3 seconds)
- Ensure all links are valid (no 404s)

---

**Last updated**: 2026-05-15  
**Maintained by**: ITLusions Platform Team
