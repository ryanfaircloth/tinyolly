# Static File Cache Busting

## Problem

Browser caching of JavaScript and CSS files can cause users to see outdated code after deployments, leading to errors or stale functionality.

## Solution

TinyOlly implements **automatic cache busting** using URL versioning with proper HTTP headers.

### How It Works

1. **Version Generation**: Each build gets a unique `STATIC_VERSION` timestamp (format: `YYYYMMDDHHMM`)
   - Auto-generated from build time if not set
   - Override with `STATIC_VERSION` environment variable for reproducible builds

2. **URL Versioning**: All static files are served with version query parameter
   - Example: `/static/tinyolly.js?v=202501121430`
   - Managed by Jinja2 `static_url()` helper function
   - Automatically updates across all templates

3. **Cache Headers**: `CachedStaticFiles` class adds HTTP headers for long-term caching
   - `Cache-Control: public, max-age=31536000, immutable`
   - Browsers cache versioned URLs for 1 year
   - New version = new URL = cache miss = fresh download

### Usage in Templates

```django
<!-- Old way (manual, error-prone) -->
<script src="/static/tinyolly.js?v=20251122b"></script>

<!-- New way (automatic) -->
<script src="{{ static_url('tinyolly.js') }}"></script>

<!-- Also works for images and other assets -->
<img src="{{ static_url('logo.svg') }}" alt="Logo">
```

### Configuration

```bash
# Optional: Set explicit version (for CI/CD reproducibility)
export STATIC_VERSION="202501121430"

# Or let it auto-generate from build time (default)
```

### Benefits

1. **Automatic**: No manual version updates in templates
2. **Aggressive Caching**: 1-year cache for performance (safe with versioning)
3. **Instant Updates**: New deployments = new version = bypass cache
4. **Debugging**: Console logs show current version: `TinyOlly static version: 202501121430`
5. **Reproducible**: Set `STATIC_VERSION` env var for consistent builds

### Testing

After deployment:

```bash
# Check version in browser console
# Should log: TinyOlly static version: <timestamp>

# Verify headers
curl -I http://localhost:5002/static/tinyolly.js?v=202501121430
# Should show: Cache-Control: public, max-age=31536000, immutable

# Hard refresh to test (Cmd+Shift+R on Mac, Ctrl+Shift+R on Windows/Linux)
```

### Alternative Approaches Considered

1. **Content Hash Versioning**: More complex, requires build-time hashing (overkill for this project)
2. **ETags Only**: Requires server round-trip (slower than cache miss)
3. **Short Max-Age**: Defeats caching benefits, increases server load
4. **Service Workers**: Over-engineered for simple cache busting

### Implementation Files

- [app/config.py](app/config.py) - `STATIC_VERSION` setting
- [app/main.py](app/main.py) - `CachedStaticFiles` class + Jinja2 helper
- [templates/tinyolly.html](templates/tinyolly.html) - Main template using `static_url()`
- [templates/partials/*.html](templates/partials/) - Partial templates using `static_url()`
