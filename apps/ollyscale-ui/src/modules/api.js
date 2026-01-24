/**
 * ollyScale v2 API Module
 *
 * Handles all backend API calls using POST-based search endpoints.
 * Copyright (c) 2026 Ryan Faircloth
 * AGPL-3.0 License
 */
import { renderSpans, renderTraces, renderLogs, renderMetrics, renderServiceMap } from './render.js';
import { renderServiceCatalog } from './serviceCatalog.js';
import { renderErrorState, renderLoadingState } from './utils.js';
import { filterOllyScaleData, filterOllyScaleTrace, filterOllyScaleMetric, shouldHideOllyScale } from './filter.js';
import { loadOpampStatus, initCollector } from './collector.js';

// ==================== API Helper Functions ====================

/**
 * Build a TimeRange for the last N minutes (in nanoseconds)
 */
function buildTimeRange(minutes = 30) {
    const now = Date.now() * 1000000; // Convert milliseconds to nanoseconds
    const start = now - (minutes * 60 * 1000000000);
    return {
        start_time: start,
        end_time: now
    };
}

/**
 * Build a search request with time range, filters, and pagination
 */
function buildSearchRequest(filters = [], limit = 100, cursor = null) {
    return {
        time_range: buildTimeRange(),
        filters: filters.length > 0 ? filters : null,
        pagination: {
            limit: limit,
            cursor: cursor
        }
    };
}

/**
 * POST request helper with JSON body
 */
async function postJSON(url, body) {
    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(body)
    });

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
}

// ==================== API Functions ====================

/**
 * Load recent traces using POST-based search
 */
export async function loadTraces() {
    try {
        const requestBody = buildSearchRequest([], 50);
        const result = await postJSON('/api/traces/search', requestBody);

        // V2 returns {traces: [...], pagination: {...}}
        let traces = result.traces || [];
        traces = traces.filter(filterOllyScaleTrace);

        renderTraces(traces);
    } catch (error) {
        console.error('Error loading traces:', error);
        document.getElementById('traces-container').innerHTML = renderErrorState('Error loading traces');
    }
}

/**
 * Load recent spans using POST-based trace search and extract spans
 */
export async function loadSpans(serviceName = null) {
    const container = document.getElementById('spans-container');
    if (!container) {
        console.error('Spans container not found');
        return;
    }

    container.innerHTML = renderLoadingState('Loading spans...');

    try {
        // Build filters
        const filters = [];
        if (serviceName) {
            filters.push({
                field: 'service.name',
                operator: 'eq',
                value: serviceName
            });
        }

        // Search traces (get more to extract enough spans)
        const requestBody = buildSearchRequest(filters, 100);
        const result = await postJSON('/api/traces/search', requestBody);

        // Extract spans from traces
        const allSpans = [];
        for (const trace of (result.traces || [])) {
            if (trace.spans && Array.isArray(trace.spans)) {
                allSpans.push(...trace.spans);
            }
        }

        // Filter and limit
        const spans = allSpans.filter(filterOllyScaleData).slice(0, 50);
        renderSpans(spans);
    } catch (error) {
        console.error('Error loading spans:', error);
        container.innerHTML = renderErrorState('Error loading spans: ' + error.message);
    }
}

/**
 * Load recent logs using POST-based search with optional trace_id filter
 */
export async function loadLogs(filterTraceId = null) {
    try {
        // Get trace ID from parameter or input field
        let traceId = filterTraceId;
        if (!traceId) {
            const input = document.getElementById('trace-id-filter');
            if (input && input.value) {
                traceId = input.value.trim();
            }
        }

        // Build filters
        const filters = [];
        if (traceId) {
            filters.push({
                field: 'trace_id',
                operator: 'eq',
                value: traceId
            });
        }

        const requestBody = buildSearchRequest(filters, 100);
        const result = await postJSON('/api/logs/search', requestBody);

        // V2 returns {logs: [...], pagination: {...}}
        let logs = result.logs || [];
        logs = logs.filter(filterOllyScaleData);

        renderLogs(logs, 'logs-container');
    } catch (error) {
        console.error('Error loading logs:', error);
        document.getElementById('logs-container').innerHTML = renderErrorState('Error loading logs');
    }
}

/**
 * Load recent metrics using POST-based search
 */
export async function loadMetrics() {
    const metricsTab = document.getElementById('metrics-content');
    if (!metricsTab || !metricsTab.classList.contains('active')) {
        return;
    }

    try {
        const requestBody = buildSearchRequest([], 100);
        const result = await postJSON('/api/metrics/search', requestBody);

        // V2 returns {metrics: [...], pagination: {...}}
        let metrics = result.metrics || [];
        metrics = metrics.filter(filterOllyScaleMetric);

        renderMetrics(metrics);
    } catch (error) {
        console.error('Error loading metrics:', error);
    }
}

/**
 * Load service dependency map using POST-based endpoint
 */
export async function loadServiceMap() {
    const loadingEl = document.getElementById('map-loading');
    if (loadingEl) loadingEl.style.display = 'flex';

    try {
        const timeRange = buildTimeRange(30);
        const result = await postJSON('/api/service-map', timeRange);

        // V2 returns {nodes: [...], edges: [...], time_range: {...}}
        let graph = {
            nodes: result.nodes || [],
            edges: result.edges || []
        };

        // Filter ollyScale services if toggle is active
        if (shouldHideOllyScale()) {
            const ollyscaleServices = ['ollyscale-ui', 'ollyscale-otlp-receiver', 'ollyscale-opamp-server', 'ollyscale-frontend'];

            // Filter edges
            graph.edges = graph.edges.filter(edge =>
                !ollyscaleServices.includes(edge.source) &&
                !ollyscaleServices.includes(edge.target)
            );

            // Build set of connected nodes
            const connectedNodes = new Set();
            graph.edges.forEach(edge => {
                connectedNodes.add(edge.source);
                connectedNodes.add(edge.target);
            });

            // Filter nodes
            graph.nodes = graph.nodes.filter(node =>
                !ollyscaleServices.includes(node.id) &&
                connectedNodes.has(node.id)
            );
        }

        renderServiceMap(graph);
    } catch (error) {
        console.error('Error loading service map:', error);
        if (loadingEl) loadingEl.style.display = 'none';
    }
}

/**
 * Fetch detailed trace information by trace ID
 */
export async function fetchTraceDetail(traceId) {
    const response = await fetch(`/api/traces/${traceId}`);
    return await response.json();
}

/**
 * Load service catalog with RED metrics
 */
export async function loadServiceCatalog() {
    try {
        const response = await fetch('/api/services');
        const result = await response.json();

        // V2 returns {services: [...], total_count: N}
        let services = result.services || [];
        services = services.filter(filterOllyScaleData);

        renderServiceCatalog(services);
    } catch (error) {
        console.error('Error loading service catalog:', error);
        document.getElementById('catalog-container').innerHTML = renderErrorState('Error loading service catalog');
    }
}
