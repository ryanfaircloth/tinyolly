/*
 * BSD 3-Clause License
 *
 * Copyright (c) 2025, Infrastructure Architects, LLC
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright notice,
 *    this list of conditions and the following disclaimer.
 *
 * 2. Redistributions in binary form must reproduce the above copyright notice,
 *    this list of conditions and the following disclaimer in the documentation
 *    and/or other materials provided with the distribution.
 *
 * 3. Neither the name of the copyright holder nor the names of its
 *    contributors may be used to endorse or promote products derived from this
 *    software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
 * FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
 * CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
 * OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

/**
 * Trace Lint Module - Handles trace flow analysis and lint findings display
 */
import { renderEmptyState, renderErrorState, renderLoadingState, renderTableHeader } from './utils.js';

let currentFlowHash = null;

/**
 * Load and display trace flows
 */
export async function loadTraceFlows() {
    const container = document.getElementById('trace-flows-container');
    if (!container) {
        console.error('Trace flows container not found');
        return;
    }

    container.innerHTML = renderLoadingState('Loading trace flows...');

    try {
        const response = await fetch('/api/trace-flows?limit=50');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const flows = await response.json();
        renderTraceFlows(flows);
    } catch (error) {
        console.error('Error loading trace flows:', error);
        container.innerHTML = renderErrorState('Error loading trace flows');
    }
}

/**
 * Render trace flows list
 */
function renderTraceFlows(flows) {
    const container = document.getElementById('trace-flows-container');

    if (!flows || flows.length === 0) {
        container.innerHTML = renderEmptyState('No trace flows yet. Send some traces to get started!');
        return;
    }

    const headerRow = renderTableHeader([
        { label: 'Flow Hash', flex: '0 0 140px' },
        { label: 'Root Operation', flex: '1' },
        { label: 'Service', flex: '0 0 120px' },
        { label: 'Method', flex: '0 0 70px' },
        { label: 'Route', flex: '1' },
        { label: 'Spans', flex: '0 0 60px', align: 'right' },
        { label: 'Traces', flex: '0 0 70px', align: 'right' },
        { label: 'Findings', flex: '0 0 80px', align: 'right' }
    ]);

    const flowsHtml = flows.map(flow => {
        const findingCount = flow.finding_count || 0;
        const severityCounts = flow.severity_counts || { error: 0, warning: 0, info: 0 };
        
        // Determine color based on severity
        let findingColor = 'var(--text-muted)';
        if (severityCounts.error > 0) {
            findingColor = '#ef4444'; // Red for errors
        } else if (severityCounts.warning > 0) {
            findingColor = '#f59e0b'; // Orange for warnings
        } else if (severityCounts.info > 0) {
            findingColor = '#3b82f6'; // Blue for info
        }

        const method = flow.http_method || '';
        const route = flow.http_route || flow.root_span_name || '-';
        const service = flow.root_service || 'unknown';
        const flowHashShort = flow.flow_hash.substring(0, 12);

        return `
            <div class="trace-flow-item data-table-row" data-flow-hash="${flow.flow_hash}">
                <div class="flow-hash text-mono text-muted" style="flex: 0 0 140px; font-size: 0.85em;">${flowHashShort}...</div>
                <div class="flow-name font-medium text-truncate" style="flex: 1;" title="${flow.root_span_name}">${flow.root_span_name}</div>
                <div class="flow-service text-truncate" style="flex: 0 0 120px;" title="${service}">${service}</div>
                <div class="flow-method text-primary font-bold text-truncate" style="flex: 0 0 70px;">${method}</div>
                <div class="flow-route text-truncate" style="flex: 1;" title="${route}">${route}</div>
                <div class="flow-spans text-muted" style="flex: 0 0 60px; text-align: right;">${flow.span_count}</div>
                <div class="flow-trace-count text-muted" style="flex: 0 0 70px; text-align: right;">${flow.trace_count}</div>
                <div class="flow-findings font-medium" style="flex: 0 0 80px; text-align: right; color: ${findingColor};">
                    ${findingCount > 0 ? findingCount : '-'}
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = `
        <div class="data-table">
            ${headerRow}
            ${flowsHtml}
        </div>
    `;

    // Add click handlers
    document.querySelectorAll('.trace-flow-item').forEach(item => {
        item.addEventListener('click', () => {
            const flowHash = item.dataset.flowHash;
            showFlowDetail(flowHash);
        });
    });
}

/**
 * Show detailed view of a trace flow
 */
async function showFlowDetail(flowHash) {
    currentFlowHash = flowHash;
    
    const listView = document.getElementById('trace-flows-list-view');
    const detailView = document.getElementById('trace-flow-detail-view');
    const detailContainer = document.getElementById('trace-flow-detail-container');

    if (!listView || !detailView || !detailContainer) {
        console.error('Flow detail view containers not found');
        return;
    }

    // Show detail view
    listView.style.display = 'none';
    detailView.style.display = 'block';

    detailContainer.innerHTML = renderLoadingState('Loading flow details...');

    try {
        const response = await fetch(`/api/trace-flows/${flowHash}`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const flowDetail = await response.json();
        renderFlowDetail(flowDetail);
    } catch (error) {
        console.error('Error loading flow detail:', error);
        detailContainer.innerHTML = renderErrorState('Error loading flow details');
    }
}

/**
 * Render detailed flow view
 */
function renderFlowDetail(flowDetail) {
    const container = document.getElementById('trace-flow-detail-container');
    const summary = flowDetail.summary || {};
    const lintResult = flowDetail.lint_result || {};
    const findings = lintResult.findings || [];
    const exampleTraces = flowDetail.example_traces || [];

    // Back button
    const backButton = `
        <div style="margin-bottom: 20px;">
            <button onclick="window.backToTraceFlows()" class="btn-secondary">
                ← Back to Trace Flows
            </button>
        </div>
    `;

    // Summary section
    const summarySection = `
        <div class="card" style="margin-bottom: 20px;">
            <h3 style="margin: 0 0 15px 0;">Flow Summary</h3>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                <div>
                    <div class="text-muted" style="font-size: 0.85em; margin-bottom: 4px;">Flow Hash</div>
                    <div class="text-mono" style="font-size: 0.9em;">${summary.flow_hash || ''}</div>
                </div>
                <div>
                    <div class="text-muted" style="font-size: 0.85em; margin-bottom: 4px;">Root Operation</div>
                    <div class="font-medium">${summary.root_span_name || 'unknown'}</div>
                </div>
                <div>
                    <div class="text-muted" style="font-size: 0.85em; margin-bottom: 4px;">Root Service</div>
                    <div>${summary.root_service || 'unknown'}</div>
                </div>
                <div>
                    <div class="text-muted" style="font-size: 0.85em; margin-bottom: 4px;">HTTP Method</div>
                    <div class="text-primary font-bold">${summary.http_method || '-'}</div>
                </div>
                <div>
                    <div class="text-muted" style="font-size: 0.85em; margin-bottom: 4px;">HTTP Route</div>
                    <div>${summary.http_route || '-'}</div>
                </div>
                <div>
                    <div class="text-muted" style="font-size: 0.85em; margin-bottom: 4px;">Span Count</div>
                    <div>${summary.span_count || 0}</div>
                </div>
                <div>
                    <div class="text-muted" style="font-size: 0.85em; margin-bottom: 4px;">Trace Count</div>
                    <div>${summary.trace_count || 0}</div>
                </div>
                <div>
                    <div class="text-muted" style="font-size: 0.85em; margin-bottom: 4px;">Status Code</div>
                    <div>${summary.status_code || '-'}</div>
                </div>
            </div>
            ${summary.service_chain && summary.service_chain.length > 0 ? `
                <div style="margin-top: 15px;">
                    <div class="text-muted" style="font-size: 0.85em; margin-bottom: 8px;">Service Chain</div>
                    <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                        ${summary.service_chain.map(service => `
                            <span class="badge">${service}</span>
                        `).join('<span style="color: var(--text-muted);">→</span>')}
                    </div>
                </div>
            ` : ''}
        </div>
    `;

    // Lint findings section
    const severityCounts = lintResult.severity_counts || { error: 0, warning: 0, info: 0 };
    const findingsSection = `
        <div class="card" style="margin-bottom: 20px;">
            <h3 style="margin: 0 0 15px 0;">
                Lint Findings
                <span class="badge" style="background: ${severityCounts.error > 0 ? '#ef4444' : severityCounts.warning > 0 ? '#f59e0b' : '#3b82f6'}; color: white; margin-left: 10px;">
                    ${findings.length} total
                </span>
            </h3>
            ${findings.length === 0 ? `
                <div class="empty-state">
                    <div style="font-size: 2em; margin-bottom: 10px;">✓</div>
                    <div>No issues found. This trace flow follows best practices!</div>
                </div>
            ` : `
                <div style="display: flex; gap: 10px; margin-bottom: 15px;">
                    ${severityCounts.error > 0 ? `<span class="badge" style="background: #ef4444; color: white;">${severityCounts.error} errors</span>` : ''}
                    ${severityCounts.warning > 0 ? `<span class="badge" style="background: #f59e0b; color: white;">${severityCounts.warning} warnings</span>` : ''}
                    ${severityCounts.info > 0 ? `<span class="badge" style="background: #3b82f6; color: white;">${severityCounts.info} info</span>` : ''}
                </div>
                <div style="display: flex; flex-direction: column; gap: 12px;">
                    ${findings.map((finding, idx) => {
                        let severityColor = '#3b82f6'; // info
                        let severityIcon = 'ℹ️';
                        if (finding.severity === 'error') {
                            severityColor = '#ef4444';
                            severityIcon = '❌';
                        } else if (finding.severity === 'warning') {
                            severityColor = '#f59e0b';
                            severityIcon = '⚠️';
                        }

                        return `
                            <div class="finding-item" style="border-left: 3px solid ${severityColor}; padding: 12px; background: var(--card-bg); border-radius: 4px;">
                                <div style="display: flex; align-items: start; gap: 10px;">
                                    <div style="font-size: 1.2em; flex-shrink: 0;">${severityIcon}</div>
                                    <div style="flex: 1;">
                                        <div style="font-weight: 600; margin-bottom: 4px; color: ${severityColor}; text-transform: uppercase; font-size: 0.85em;">
                                            ${finding.severity} - ${finding.type}
                                        </div>
                                        <div style="margin-bottom: 8px;">${finding.message}</div>
                                        <div style="background: var(--code-bg); padding: 8px; border-radius: 4px; font-size: 0.9em; color: var(--text-muted);">
                                            <strong>Suggestion:</strong> ${finding.suggestion}
                                        </div>
                                        <div class="text-muted" style="font-size: 0.85em; margin-top: 6px;">
                                            Span: <span class="text-mono">${finding.span_name}</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            `}
        </div>
    `;

    // Example traces section
    const examplesSection = `
        <div class="card">
            <h3 style="margin: 0 0 15px 0;">Example Traces</h3>
            ${exampleTraces.length === 0 ? `
                <div class="empty-state">No example traces available</div>
            ` : `
                <div style="display: flex; flex-direction: column; gap: 8px;">
                    ${exampleTraces.map(traceId => `
                        <div class="example-trace-item" style="display: flex; justify-content: space-between; align-items: center; padding: 10px; background: var(--code-bg); border-radius: 4px;">
                            <div class="text-mono" style="font-size: 0.9em;">${traceId}</div>
                            <button class="btn-secondary btn-sm" onclick="window.viewTrace('${traceId}')">
                                View Trace →
                            </button>
                        </div>
                    `).join('')}
                </div>
            `}
        </div>
    `;

    container.innerHTML = backButton + summarySection + findingsSection + examplesSection;
}

/**
 * Go back to trace flows list
 */
export function backToTraceFlows() {
    const listView = document.getElementById('trace-flows-list-view');
    const detailView = document.getElementById('trace-flow-detail-view');

    if (listView && detailView) {
        listView.style.display = 'block';
        detailView.style.display = 'none';
        currentFlowHash = null;
    }
}

/**
 * View a specific trace (switches to traces tab)
 */
export function viewTrace(traceId) {
    // Import switchTab dynamically to avoid circular dependency
    import('./tabs.js').then(({ switchTab }) => {
        // Switch to traces tab
        const tracesTab = document.querySelector('[data-tab="traces"]');
        if (tracesTab) {
            switchTab('traces', tracesTab);
            
            // Trigger trace detail view
            setTimeout(() => {
                const traceItem = document.querySelector(`[data-trace-id="${traceId}"]`);
                if (traceItem) {
                    traceItem.click();
                }
            }, 100);
        }
    });
}

// Export for global access
window.backToTraceFlows = backToTraceFlows;
window.viewTrace = viewTrace;
