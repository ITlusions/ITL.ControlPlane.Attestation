# Navigation Maintenance Guide

The site navigation is now managed via Jekyll data files for easy maintenance.

## Location

`docs/_data/navigation.yml`

## Structure

```yaml
main:
  - title: Page Title
    url: /PAGE_URL
    
external:
  - title: Link Title
    url: https://external-url.com
    icon: github  # optional
```

## Adding a New Page

1. Open `docs/_data/navigation.yml`
2. Add a new entry under `main:`:
   ```yaml
   - title: New Page
     url: /NEW_PAGE
   ```
3. The page will automatically appear in:
   - Top navigation bar
   - Left sidebar
   - Mobile menu

## Reordering Pages

Simply drag and drop entries in the YAML file. The order in the file is the order shown on the site.

## Adding External Links

Add entries under `external:` section:

```yaml
external:
  - title: Documentation
    url: https://docs.example.com
    icon: github  # currently only 'github' icon is supported
```

## Removing Pages

Delete or comment out (with `#`) the entry in `navigation.yml`:

```yaml
# - title: Old Page
#   url: /OLD_PAGE
```

## Active State Detection

The active page is automatically highlighted based on URL matching. No manual configuration needed.

## Benefits

- **Single source of truth** — edit once, updates everywhere
- **No layout editing** — never touch `_layouts/default.html` for nav changes
- **Easy maintenance** — simple YAML syntax
- **Version controlled** — track navigation changes in Git
- **Extensible** — easy to add metadata like icons, descriptions, or badges in the future
