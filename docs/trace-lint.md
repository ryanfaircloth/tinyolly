# Trace Lint

The Trace Lint feature helps you identify and improve the quality of your OpenTelemetry traces by analyzing trace structures and providing actionable feedback.

## Overview

Trace Lint analyzes traces to:

1. **Identify Unique Trace Flows**: Groups traces with similar structures together by computing a hash based on span hierarchy, service names, operations, and logic-affecting attributes (while excluding identifiers like IPs and user agents).

2. **Detect Issues**: Provides lint findings for:
   - Semantic convention violations (e.g., using `http_method` instead of `http.method`)
   - Missing required attributes (e.g., HTTP spans without `http.method`)
   - Auto-instrumentation opportunities
   - Field naming issues

## Using Trace Lint

### Viewing Trace Flows

1. Navigate to the **Trace Lint** tab in the TinyOlly UI
2. View the list of unique trace flow patterns
3. Each flow shows:
   - Flow hash (unique identifier)
   - Root operation and service
   - HTTP method and route (if applicable)
   - Number of spans and traces
   - Finding count with severity indicators

### Analyzing a Flow

Click on any flow to see detailed information:

- **Flow Summary**: Key metrics and service chain
- **Lint Findings**: Categorized by severity (error, warning, info)
- **Example Traces**: Sample trace IDs matching this flow pattern

### Understanding Findings

#### Severity Levels

- **Error**: Critical issues that should be fixed immediately
- **Warning**: Issues that may cause problems or violate best practices
- **Info**: Suggestions for improvements or optimizations

#### Common Finding Types

**Naming Issues**:
```
Attribute 'http_method' should use semantic convention 'http.method'
Suggestion: Rename 'http_method' to 'http.method'
```

**Missing Attributes**:
```
HTTP span 'GET /api/users' missing http.method attribute
Suggestion: Add http.method or http.request.method attribute
```

**Auto-instrumentation Opportunities**:
```
HTTP span 'GET /api/users' may benefit from auto-instrumentation
Suggestion: Consider using OpenTelemetry auto-instrumentation
```

## API Endpoints

### List Trace Flows

```http
GET /api/trace-flows?limit=50
```

Returns a list of unique trace flow structures with summaries.

**Response**:
```json
[
  {
    "flow_hash": "a1b2c3d4e5f6g7h8",
    "root_span_name": "GET /api/users",
    "root_service": "frontend",
    "span_count": 5,
    "service_chain": ["frontend", "backend", "database"],
    "http_method": "GET",
    "http_route": "/api/users",
    "status_code": 200,
    "trace_count": 42,
    "example_trace_id": "trace-xyz",
    "finding_count": 3,
    "severity_counts": {
      "error": 0,
      "warning": 1,
      "info": 2
    }
  }
]
```

### Get Flow Details

```http
GET /api/trace-flows/{flow_hash}
```

Returns detailed information about a specific trace flow including lint findings.

**Response**:
```json
{
  "flow_hash": "a1b2c3d4e5f6g7h8",
  "summary": { ... },
  "lint_result": {
    "trace_id": "trace-xyz",
    "flow_hash": "a1b2c3d4e5f6g7h8",
    "findings": [
      {
        "severity": "warning",
        "type": "naming",
        "message": "Attribute 'http_method' should use semantic convention 'http.method'",
        "suggestion": "Rename 'http_method' to 'http.method'",
        "span_name": "GET /api/users"
      }
    ],
    "span_count": 5,
    "severity_counts": {
      "error": 0,
      "warning": 1,
      "info": 0
    }
  },
  "example_traces": ["trace-xyz", "trace-abc"]
}
```

### Lint a Specific Trace

```http
GET /api/traces/{trace_id}/lint
```

Returns lint findings for a specific trace.

## How It Works

### Flow Hash Computation

The flow hash is computed by:

1. Extracting structural elements from each span:
   - Span name
   - Span kind (internal, server, client, producer, consumer)
   - Service name
   - Logic-affecting attributes (status codes, errors, operations)

2. Excluding identifiers:
   - IP addresses
   - UUIDs
   - User agents
   - Session IDs

3. Creating a deterministic JSON representation
4. Computing a SHA-256 hash

This ensures that traces with the same logical structure are grouped together, even if they have different identifiers or timestamps.

### Lint Rules

Trace Lint applies several categories of rules:

**Semantic Conventions**: Checks for compliance with [OpenTelemetry Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/).

**Attribute Naming**: Detects non-standard naming patterns (underscores vs dots).

**Missing Attributes**: Identifies spans that should have specific attributes based on their type (HTTP, database, RPC, etc.).

**Auto-instrumentation**: Suggests using OpenTelemetry auto-instrumentation for common frameworks and libraries.

## Best Practices

1. **Review Regularly**: Check the Trace Lint tab regularly to identify new issues
2. **Start with Errors**: Address errors first, then warnings, then info-level findings
3. **Use Semantic Conventions**: Follow OpenTelemetry semantic conventions for attribute naming
4. **Enable Auto-instrumentation**: Use auto-instrumentation libraries when available
5. **Document Custom Attributes**: If using custom attributes, document them in your team's instrumentation guide

## Integration with Development Workflow

Consider integrating Trace Lint into your development workflow:

1. **Local Development**: Check trace quality during development
2. **CI/CD**: Monitor trace patterns in staging environments
3. **Production**: Track trends in trace quality over time

## Limitations

- Trace Lint analyzes structure and attributes, but cannot verify business logic
- Some findings may be false positives depending on your specific use case
- Flow hashing works best with consistent instrumentation practices
- Ephemeral storage (30-minute TTL) means historical trends are not tracked
