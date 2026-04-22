/* ===== TBM Admin Dashboard — Wave 4 ===== */
(function () {
    'use strict';

    const API = window.location.origin;
    let API_KEY = localStorage.getItem('tbm_admin_key') || '';
    let tenants = [];
    let currentTenant = null;
    let liveInterval = null;
    let lastLiveTimestamp = null;

    // ── Helpers ──────────────────────────────────────────────────────────
    function $(sel, ctx) { return (ctx || document).querySelector(sel); }
    function $$(sel, ctx) { return [...(ctx || document).querySelectorAll(sel)]; }

    function headers() { return { 'Content-Type': 'application/json', 'X-Admin-Key': API_KEY }; }

    async function api(path, opts = {}) {
        const url = API + path;
        const res = await fetch(url, { headers: headers(), ...opts });
        if (!res.ok) {
            const text = await res.text().catch(() => '');
            throw new Error(`API ${res.status}: ${text}`);
        }
        const ct = res.headers.get('content-type') || '';
        if (ct.includes('json')) return res.json();
        return res.text();
    }

    function toast(msg, type = 'info') {
        const el = document.createElement('div');
        el.className = `toast ${type}`;
        el.textContent = msg;
        $('#toast-container').appendChild(el);
        setTimeout(() => el.remove(), 4000);
    }

    function showModal(title, html) {
        $('#modal-title').textContent = title;
        $('#modal-body').innerHTML = html;
        $('#modal-overlay').classList.remove('hidden');
    }
    function hideModal() { $('#modal-overlay').classList.add('hidden'); }

    function timeAgo(dt) {
        const d = new Date(dt);
        const s = Math.floor((Date.now() - d) / 1000);
        if (s < 60) return 'just now';
        if (s < 3600) return Math.floor(s / 60) + 'm ago';
        if (s < 86400) return Math.floor(s / 3600) + 'h ago';
        return Math.floor(s / 86400) + 'd ago';
    }

    function esc(str) {
        const d = document.createElement('div');
        d.textContent = str || '';
        return d.innerHTML;
    }

    // ── Navigation ──────────���─────────────────────��─────────────────────
    function showPage(page) {
        $$('.page').forEach(p => p.classList.remove('active'));
        const el = $(`#page-${page}`);
        if (el) el.classList.add('active');
        $$('.nav-menu a').forEach(a => a.classList.toggle('active', a.dataset.page === page));
        if (page === 'overview') loadOverview();
        else if (page === 'tenants') loadTenants();
        else if (page === 'live') loadLiveSetup();
        else if (page === 'insights') loadInsightsSetup();
        else if (page === 'settings') loadSettings();
        // Stop live polling when leaving live page
        if (page !== 'live' && liveInterval) { clearInterval(liveInterval); liveInterval = null; }
    }

    // ── Auth ─────────────────────────────────────────────────────────────
    async function tryLogin(key) {
        API_KEY = key;
        try {
            await api('/api/admin/usage');
            localStorage.setItem('tbm_admin_key', key);
            $('#auth-screen').classList.remove('active');
            showPage('overview');
            return true;
        } catch {
            $('#auth-error').textContent = 'Invalid API key';
            return false;
        }
    }

    // ── Overview ──────────────────────────────���──────────────────────────
    async function loadOverview() {
        try {
            const [usage, health] = await Promise.all([api('/api/admin/usage'), api('/health')]);
            tenants = await api('/api/tenants');

            let totalConvs = 0, totalMsgs = 0, totalDocs = 0;
            usage.forEach(u => { totalConvs += u.total_conversations; totalMsgs += u.total_messages; totalDocs += u.documents_count; });

            const statsHtml = `
                <div class="stat-card accent"><span class="stat-label">Tenants</span><span class="stat-value">${tenants.length}</span></div>
                <div class="stat-card accent"><span class="stat-label">Conversations</span><span class="stat-value">${totalConvs}</span></div>
                <div class="stat-card accent"><span class="stat-label">Messages</span><span class="stat-value">${totalMsgs}</span></div>
                <div class="stat-card accent"><span class="stat-label">Documents</span><span class="stat-value">${totalDocs}</span></div>
                <div class="stat-card accent"><span class="stat-label">Uptime</span><span class="stat-value">${Math.floor(health.uptime_seconds / 3600)}h</span></div>
            `;
            $('#overview-stats').innerHTML = statsHtml;

            // Load chart for first tenant if available
            if (tenants.length > 0) {
                const analytics = await api(`/api/admin/analytics?tenant_id=${tenants[0].id}&days=30`);
                renderBarChart($('#messages-chart'), analytics.messages_per_day);
            }
        } catch (e) {
            toast('Failed to load overview: ' + e.message, 'error');
        }
    }

    function renderBarChart(container, data) {
        if (!data || !data.length) { container.innerHTML = '<div class="empty-state text-sm">No data yet</div>'; return; }
        const max = Math.max(...data.map(d => d.count), 1);
        container.innerHTML = data.map(d => {
            const pct = (d.count / max * 100).toFixed(0);
            return `<div class="bar" style="height:${Math.max(pct, 2)}%"><div class="bar-tooltip">${d.date}: ${d.count}</div></div>`;
        }).join('');
    }

    // ── Tenants List ─────────────────────────────────────────────────────
    async function loadTenants() {
        try {
            tenants = await api('/api/tenants');
            const usage = await api('/api/admin/usage');
            const usageMap = {};
            usage.forEach(u => usageMap[u.tenant_id] = u);

            if (!tenants.length) {
                $('#tenants-list').innerHTML = '<div class="empty-state"><div class="empty-icon">&#x1f3e2;</div><p>No tenants yet. Click "New Tenant" to get started.</p></div>';
                return;
            }

            let html = `<table><thead><tr><th>Name</th><th>Slug</th><th>Docs</th><th>Convos</th><th>Status</th><th></th></tr></thead><tbody>`;
            tenants.forEach(t => {
                const u = usageMap[t.id] || {};
                html += `<tr class="clickable" data-id="${t.id}">
                    <td><strong>${esc(t.name)}</strong></td>
                    <td><code>${esc(t.slug)}</code></td>
                    <td>${u.documents_count || 0}</td>
                    <td>${u.total_conversations || 0}</td>
                    <td><span class="tag ${t.active ? 'tag-success' : 'tag-danger'}">${t.active ? 'Active' : 'Inactive'}</span></td>
                    <td><button class="btn btn-sm btn-ghost btn-manage" data-id="${t.id}">Manage</button></td>
                </tr>`;
            });
            html += '</tbody></table>';
            $('#tenants-list').innerHTML = html;

            $$('.btn-manage', $('#tenants-list')).forEach(btn => {
                btn.addEventListener('click', e => { e.stopPropagation(); openTenantDetail(btn.dataset.id); });
            });
            $$('tr.clickable', $('#tenants-list')).forEach(tr => {
                tr.addEventListener('click', () => openTenantDetail(tr.dataset.id));
            });
        } catch (e) { toast('Failed to load tenants: ' + e.message, 'error'); }
    }

    // ── Tenant Detail ────────────────────────────────────────────────────
    async function openTenantDetail(tenantId) {
        try {
            currentTenant = await api(`/api/tenants/${tenantId}`);
        } catch (e) { toast('Failed to load tenant', 'error'); return; }

        $$('.page').forEach(p => p.classList.remove('active'));
        $('#page-tenant-detail').classList.add('active');

        $('#tenant-header').innerHTML = `
            <div class="flex justify-between items-center mb-2">
                <div><h2>${esc(currentTenant.name)}</h2><code class="text-muted">${esc(currentTenant.slug)}</code></div>
                <div class="flex gap-2">
                    <button class="btn btn-sm btn-warning" id="btn-export-csv">Export CSV</button>
                    <button class="btn btn-sm btn-ghost" id="btn-export-json">Export JSON</button>
                </div>
            </div>`;

        $('#btn-export-csv').addEventListener('click', () => exportConversations('csv'));
        $('#btn-export-json').addEventListener('click', () => exportConversations('json'));

        // Set active tab
        $$('.tab', $('#tenant-tabs')).forEach(t => t.classList.toggle('active', t.dataset.tab === 'config'));
        loadTenantTab('config');
    }

    async function exportConversations(format) {
        try {
            const url = `${API}/api/admin/export/conversations?tenant_id=${currentTenant.id}&format=${format}`;
            const res = await fetch(url, { headers: headers() });
            const blob = await res.blob();
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = `conversations_${currentTenant.slug}.${format}`;
            a.click();
            toast('Export downloaded!', 'success');
        } catch (e) { toast('Export failed: ' + e.message, 'error'); }
    }

    async function loadTenantTab(tab) {
        const container = $('#tenant-tab-content');
        container.innerHTML = '<div class="text-muted">Loading...</div>';

        switch (tab) {
            case 'config': return renderConfigTab(container);
            case 'documents': return renderDocumentsTab(container);
            case 'conversations': return renderConversationsTab(container);
            case 'contacts': return renderContactsTab(container);
            case 'feedback': return renderFeedbackTab(container);
            case 'unanswered': return renderUnansweredTab(container);
            case 'analytics': return renderAnalyticsTab(container);
            case 'ab-test': return renderABTestTab(container);
        }
    }

    // ── Config Tab ───���────────────────────────────────���──────────────────
    function renderConfigTab(container) {
        const t = currentTenant;
        const wc = t.widget_config || {};
        container.innerHTML = `
            <div class="card">
                <h3>Tenant Settings</h3>
                <div class="form-group"><label>System Prompt</label><textarea id="cfg-system-prompt" rows="3">${esc(t.system_prompt)}</textarea></div>
                <div class="form-group"><label>Guidance Rules</label><textarea id="cfg-guidance" rows="2">${esc(t.guidance_rules || '')}</textarea></div>
                <div class="form-group"><label>Support Email</label><input id="cfg-email" value="${esc(t.support_email || '')}"></div>
                <div class="form-row">
                    <div class="form-group" style="flex:1"><label>Quick Replies (comma-separated)</label><input id="cfg-quick" value="${(t.quick_replies || []).join(', ')}"></div>
                </div>
                <div class="form-row">
                    <div class="form-group"><label>Primary Color</label><input type="color" id="cfg-color" value="${wc.primary_color || '#2563eb'}"></div>
                    <div class="form-group" style="flex:1"><label>Welcome Message</label><input id="cfg-welcome" value="${esc(wc.welcome_message || '')}"></div>
                </div>
                <div class="form-row">
                    <div class="form-group"><label>Email Notifications</label><select id="cfg-email-notif"><option value="true" ${t.email_notifications_enabled ? 'selected' : ''}>Enabled</option><option value="false" ${!t.email_notifications_enabled ? 'selected' : ''}>Disabled</option></select></div>
                    <div class="form-group"><label>WhatsApp</label><select id="cfg-whatsapp"><option value="true" ${t.whatsapp_enabled ? 'selected' : ''}>Enabled</option><option value="false" ${!t.whatsapp_enabled ? 'selected' : ''}>Disabled</option></select></div>
                    <div class="form-group"><label>A/B Testing</label><select id="cfg-ab-test"><option value="true" ${t.ab_test_enabled ? 'selected' : ''}>Enabled</option><option value="false" ${!t.ab_test_enabled ? 'selected' : ''}>Disabled</option></select></div>
                </div>
                <div class="form-group"><label>Greeting Variants (one per line)</label><textarea id="cfg-greetings" rows="3">${(t.greeting_variants || []).join('\n')}</textarea></div>
                <div class="form-group"><label>Escalation Triggers (one per line)</label><textarea id="cfg-escalation" rows="2">${(t.escalation_triggers || []).join('\n')}</textarea></div>
                <div class="form-group"><label>Banned Words (one per line)</label><textarea id="cfg-banned" rows="2">${(t.banned_words || []).join('\n')}</textarea></div>
                <button class="btn btn-primary" id="btn-save-config">Save Changes</button>
            </div>`;

        $('#btn-save-config').addEventListener('click', saveConfig);
    }

    async function saveConfig() {
        const wc = { ...(currentTenant.widget_config || {}) };
        wc.primary_color = $('#cfg-color').value;
        wc.welcome_message = $('#cfg-welcome').value;

        const updates = {
            system_prompt: $('#cfg-system-prompt').value,
            guidance_rules: $('#cfg-guidance').value || null,
            support_email: $('#cfg-email').value || null,
            quick_replies: $('#cfg-quick').value.split(',').map(s => s.trim()).filter(Boolean),
            widget_config: wc,
            email_notifications_enabled: $('#cfg-email-notif').value === 'true',
            whatsapp_enabled: $('#cfg-whatsapp').value === 'true',
            ab_test_enabled: $('#cfg-ab-test').value === 'true',
            greeting_variants: $('#cfg-greetings').value.split('\n').map(s => s.trim()).filter(Boolean),
            escalation_triggers: $('#cfg-escalation').value.split('\n').map(s => s.trim()).filter(Boolean),
            banned_words: $('#cfg-banned').value.split('\n').map(s => s.trim()).filter(Boolean),
        };

        try {
            currentTenant = await api(`/api/tenants/${currentTenant.id}`, {
                method: 'PATCH',
                body: JSON.stringify(updates),
            });
            toast('Settings saved!', 'success');
        } catch (e) { toast('Save failed: ' + e.message, 'error'); }
    }

    // ── Documents Tab ──────────────────��─────────────────────────────────
    async function renderDocumentsTab(container) {
        try {
            const docs = await api(`/api/tenants/${currentTenant.id}/documents`);
            let html = `
                <div class="card mb-2">
                    <h3>Add Document</h3>
                    <div class="form-group"><label>Title</label><input id="doc-title" placeholder="Document title"></div>
                    <div class="form-group"><label>Content</label><textarea id="doc-content" rows="4" placeholder="Paste document content..."></textarea></div>
                    <div class="form-row">
                        <div class="form-group" style="flex:1"><label>Source URL</label><input id="doc-url" placeholder="https://..."></div>
                        <div class="form-group"><label>Category</label><input id="doc-category" placeholder="FAQ, Programs..."></div>
                    </div>
                    <div class="flex gap-2">
                        <button class="btn btn-primary" id="btn-add-doc">Add Document</button>
                        <button class="btn btn-success" id="btn-crawl-doc">Crawl URL</button>
                    </div>
                </div>
                <div class="card"><h3>Documents (${docs.length})</h3>`;

            if (docs.length) {
                html += '<table><thead><tr><th>Title</th><th>Status</th><th>Type</th><th>Category</th><th>Created</th><th></th></tr></thead><tbody>';
                docs.forEach(d => {
                    html += `<tr>
                        <td class="truncate">${esc(d.title)}</td>
                        <td><span class="tag ${d.status === 'ready' ? 'tag-success' : d.status === 'error' ? 'tag-danger' : 'tag-warning'}">${d.status}</span></td>
                        <td>${d.content_type}</td>
                        <td>${esc(d.category || '-')}</td>
                        <td class="text-muted text-sm">${timeAgo(d.created_at)}</td>
                        <td><button class="btn btn-sm btn-danger btn-del-doc" data-id="${d.id}">Delete</button></td>
                    </tr>`;
                });
                html += '</tbody></table>';
            } else {
                html += '<p class="text-muted">No documents yet.</p>';
            }
            html += '</div>';
            container.innerHTML = html;

            $('#btn-add-doc').addEventListener('click', addDocument);
            $('#btn-crawl-doc').addEventListener('click', crawlDocument);
            $$('.btn-del-doc').forEach(btn => btn.addEventListener('click', () => deleteDocument(btn.dataset.id)));
        } catch (e) { container.innerHTML = `<p class="text-muted">Error: ${esc(e.message)}</p>`; }
    }

    async function addDocument() {
        const title = $('#doc-title').value.trim();
        const content = $('#doc-content').value.trim();
        if (!title || !content) { toast('Title and content required', 'error'); return; }
        try {
            await api(`/api/tenants/${currentTenant.id}/documents`, {
                method: 'POST',
                body: JSON.stringify({
                    title, content,
                    source_url: $('#doc-url').value.trim() || null,
                    category: $('#doc-category').value.trim() || null,
                }),
            });
            toast('Document added! Processing...', 'success');
            loadTenantTab('documents');
        } catch (e) { toast('Failed: ' + e.message, 'error'); }
    }

    async function crawlDocument() {
        const url = $('#doc-url').value.trim();
        if (!url) { toast('Enter a URL to crawl', 'error'); return; }
        try {
            await api(`/api/tenants/${currentTenant.id}/documents/crawl`, {
                method: 'POST',
                body: JSON.stringify({
                    url,
                    category: $('#doc-category').value.trim() || null,
                }),
            });
            toast('URL crawled & document created!', 'success');
            loadTenantTab('documents');
        } catch (e) { toast('Crawl failed: ' + e.message, 'error'); }
    }

    async function deleteDocument(docId) {
        if (!confirm('Delete this document?')) return;
        try {
            await api(`/api/tenants/${currentTenant.id}/documents/${docId}`, { method: 'DELETE' });
            toast('Document deleted', 'success');
            loadTenantTab('documents');
        } catch (e) { toast('Delete failed: ' + e.message, 'error'); }
    }

    // ── Conversations Tab ────────────────────────────────────────────────
    async function renderConversationsTab(container) {
        try {
            const convos = await api(`/api/admin/tenants/${currentTenant.id}/conversations`);
            if (!convos.length) { container.innerHTML = '<div class="empty-state"><div class="empty-icon">&#x1f4ac;</div><p>No conversations yet.</p></div>'; return; }

            let html = '<table><thead><tr><th>Visitor</th><th>Messages</th><th>Tags</th><th>Channel</th><th>Summary</th><th>Last Active</th></tr></thead><tbody>';
            convos.forEach(c => {
                const tags = (c.tags || []).map(t => `<span class="tag">${esc(t)}</span>`).join(' ');
                html += `<tr class="clickable" data-conv="${c.id}">
                    <td>${esc(c.visitor_name || 'Anonymous')}<br><small class="text-muted">${esc(c.visitor_email || '')}</small></td>
                    <td>${c.message_count}</td>
                    <td>${tags || '-'}</td>
                    <td><span class="tag">${c.channel || 'web'}</span></td>
                    <td class="truncate text-sm">${esc(c.summary || '-')}</td>
                    <td class="text-muted text-sm">${timeAgo(c.last_message_at)}</td>
                </tr>`;
            });
            html += '</tbody></table>';
            container.innerHTML = html;

            $$('tr.clickable', container).forEach(tr => {
                tr.addEventListener('click', () => showConversation(tr.dataset.conv));
            });
        } catch (e) { container.innerHTML = `<p class="text-muted">Error: ${esc(e.message)}</p>`; }
    }

    async function showConversation(convId) {
        try {
            const msgs = await api(`/api/admin/conversations/${convId}/messages`);
            let html = msgs.map(m => `
                <div class="message-bubble ${m.role}">
                    ${esc(m.content)}
                    <div class="bubble-meta">${m.role} &middot; ${timeAgo(m.created_at)}${m.is_fallback ? ' &middot; <span class="tag tag-danger">fallback</span>' : ''}${m.response_time_ms ? ` &middot; ${m.response_time_ms}ms` : ''}</div>
                </div>
            `).join('');
            showModal('Conversation', html);
        } catch (e) { toast('Failed to load messages', 'error'); }
    }

    // ── Contacts Tab ────────────���───────────────────────────��────────────
    async function renderContactsTab(container) {
        try {
            const contacts = await api(`/api/admin/contacts?tenant_id=${currentTenant.id}`);
            if (!contacts.length) { container.innerHTML = '<div class="empty-state"><p>No contact requests yet.</p></div>'; return; }

            let html = '<table><thead><tr><th>Name</th><th>Email</th><th>Message</th><th>Status</th><th>When</th></tr></thead><tbody>';
            contacts.forEach(c => {
                html += `<tr>
                    <td>${esc(c.visitor_name)}</td>
                    <td><a href="mailto:${esc(c.visitor_email)}">${esc(c.visitor_email)}</a></td>
                    <td class="truncate">${esc(c.message)}</td>
                    <td><span class="tag">${c.status}</span></td>
                    <td class="text-muted text-sm">${timeAgo(c.created_at)}</td>
                </tr>`;
            });
            html += '</tbody></table>';
            container.innerHTML = html;
        } catch (e) { container.innerHTML = `<p class="text-muted">Error: ${esc(e.message)}</p>`; }
    }

    // ── Feedback Tab ─────────────────────────────────────────────────────
    async function renderFeedbackTab(container) {
        try {
            const feedback = await api(`/api/admin/feedback?tenant_id=${currentTenant.id}`);
            if (!feedback.length) { container.innerHTML = '<div class="empty-state"><p>No feedback yet.</p></div>'; return; }

            const pos = feedback.filter(f => f.rating === 'positive').length;
            const neg = feedback.length - pos;
            let html = `
                <div class="stats-grid mb-2">
                    <div class="stat-card"><span class="stat-label">Total</span><span class="stat-value">${feedback.length}</span></div>
                    <div class="stat-card"><span class="stat-label">Positive</span><span class="stat-value" style="color:var(--success)">${pos}</span></div>
                    <div class="stat-card"><span class="stat-label">Negative</span><span class="stat-value" style="color:var(--danger)">${neg}</span></div>
                    <div class="stat-card"><span class="stat-label">Approval Rate</span><span class="stat-value">${feedback.length ? Math.round(pos / feedback.length * 100) : 0}%</span></div>
                </div>
                <table><thead><tr><th>Rating</th><th>Message ID</th><th>When</th></tr></thead><tbody>`;
            feedback.slice(0, 50).forEach(f => {
                html += `<tr>
                    <td><span class="tag ${f.rating === 'positive' ? 'tag-success' : 'tag-danger'}">${f.rating === 'positive' ? 'Thumbs Up' : 'Thumbs Down'}</span></td>
                    <td class="mono text-sm">${String(f.message_id).slice(0, 8)}...</td>
                    <td class="text-muted text-sm">${timeAgo(f.created_at)}</td>
                </tr>`;
            });
            html += '</tbody></table>';
            container.innerHTML = html;
        } catch (e) { container.innerHTML = `<p class="text-muted">Error: ${esc(e.message)}</p>`; }
    }

    // ── Unanswered Tab ───────────────────���──────────────────���────────────
    async function renderUnansweredTab(container) {
        try {
            const items = await api(`/api/admin/unanswered?tenant_id=${currentTenant.id}`);
            if (!items.length) { container.innerHTML = '<div class="empty-state"><div class="empty-icon">&#x2705;</div><p>No unanswered questions — great coverage!</p></div>'; return; }

            let html = '<table><thead><tr><th>User Question</th><th>Bot Response</th><th>When</th></tr></thead><tbody>';
            items.forEach(q => {
                html += `<tr>
                    <td>${esc(q.user_question)}</td>
                    <td class="truncate text-muted">${esc(q.bot_response)}</td>
                    <td class="text-muted text-sm">${timeAgo(q.created_at)}</td>
                </tr>`;
            });
            html += '</tbody></table>';
            container.innerHTML = html;
        } catch (e) { container.innerHTML = `<p class="text-muted">Error: ${esc(e.message)}</p>`; }
    }

    // ── Analytics Tab ─────────────────────���──────────────────────────────
    async function renderAnalyticsTab(container) {
        try {
            const a = await api(`/api/admin/analytics?tenant_id=${currentTenant.id}&days=30`);
            container.innerHTML = `
                <div class="stats-grid mb-2">
                    <div class="stat-card accent"><span class="stat-label">Conversations</span><span class="stat-value">${a.total_conversations}</span></div>
                    <div class="stat-card accent"><span class="stat-label">Messages</span><span class="stat-value">${a.total_messages}</span></div>
                    <div class="stat-card accent"><span class="stat-label">Resolution Rate</span><span class="stat-value">${a.resolution_rate}%</span></div>
                    <div class="stat-card accent"><span class="stat-label">CSAT</span><span class="stat-value">${a.avg_csat_score !== null ? a.avg_csat_score + '/5' : 'N/A'}</span></div>
                    <div class="stat-card accent"><span class="stat-label">Avg Response</span><span class="stat-value">${a.avg_response_time_ms ? Math.round(a.avg_response_time_ms) + 'ms' : 'N/A'}</span></div>
                    <div class="stat-card accent"><span class="stat-label">Contact Requests</span><span class="stat-value">${a.total_contact_requests}</span></div>
                </div>
                <div class="card mb-2"><h3>Messages Per Day</h3><div id="analytics-chart" class="bar-chart"></div></div>
                <div class="card"><h3>Top Tags</h3>
                    ${a.top_tags.length ? a.top_tags.map(t => `<span class="tag" style="margin:2px">${esc(t.tag)} (${t.count})</span>`).join('') : '<p class="text-muted">No tags yet</p>'}
                </div>`;
            renderBarChart($('#analytics-chart'), a.messages_per_day);
        } catch (e) { container.innerHTML = `<p class="text-muted">Error: ${esc(e.message)}</p>`; }
    }

    // ── A/B Test Tab ─────────────────────────────────────────────────────
    async function renderABTestTab(container) {
        try {
            const results = await api(`/api/admin/ab-test-results?tenant_id=${currentTenant.id}`);
            if (!results.length) {
                container.innerHTML = `<div class="card">
                    <h3>A/B Test Results</h3>
                    <p class="text-muted">No A/B test data yet. Enable A/B testing and add greeting variants in the Config tab.</p>
                    <p class="text-muted text-sm mt-4">When enabled, the chatbot randomly assigns one of your greeting variants to each new conversation and tracks which leads to longer engagement.</p>
                </div>`;
                return;
            }

            let html = `<div class="card"><h3>A/B Test Results — Greeting Variants</h3>
                <table><thead><tr><th>Variant</th><th>Conversations</th><th>Avg Messages</th><th>Performance</th></tr></thead><tbody>`;
            const maxAvg = Math.max(...results.map(r => r.avg_messages));
            results.forEach(r => {
                const barWidth = maxAvg > 0 ? (r.avg_messages / maxAvg * 100) : 0;
                html += `<tr>
                    <td class="truncate">${esc(r.variant)}</td>
                    <td>${r.conversation_count}</td>
                    <td><strong>${r.avg_messages}</strong></td>
                    <td><div style="background:var(--primary-light);border-radius:4px;height:20px;width:100%;position:relative"><div style="background:var(--primary);height:100%;width:${barWidth}%;border-radius:4px"></div></div></td>
                </tr>`;
            });
            html += '</tbody></table></div>';
            container.innerHTML = html;
        } catch (e) { container.innerHTML = `<p class="text-muted">Error: ${esc(e.message)}</p>`; }
    }

    // ── Live Monitor ──────────────────────────────────────��──────────────
    async function loadLiveSetup() {
        tenants = await api('/api/tenants').catch(() => []);
        const sel = $('#live-tenant-select');
        sel.innerHTML = '<option value="">Select tenant...</option>' +
            tenants.map(t => `<option value="${t.id}">${esc(t.name)}</option>`).join('');
    }

    function startLiveMonitor(tenantId) {
        if (liveInterval) clearInterval(liveInterval);
        lastLiveTimestamp = null;
        $('#live-conversations').innerHTML = '<div class="text-muted">Connecting...</div>';

        async function poll() {
            try {
                const convos = await api(`/api/admin/tenants/${tenantId}/conversations`);
                let html = '';
                for (const c of convos.slice(0, 20)) {
                    const isNew = lastLiveTimestamp && new Date(c.last_message_at) > new Date(lastLiveTimestamp);
                    const tags = (c.tags || []).map(t => `<span class="tag">${esc(t)}</span>`).join(' ');
                    html += `<div class="live-card ${isNew ? 'new' : ''}" data-conv="${c.id}">
                        <div class="flex justify-between items-center">
                            <h4>${esc(c.visitor_name || 'Anonymous')}</h4>
                            <span class="text-muted text-sm">${c.message_count} msgs &middot; ${timeAgo(c.last_message_at)}</span>
                        </div>
                        <div class="live-meta">${tags} <span class="tag">${c.channel || 'web'}</span></div>
                    </div>`;
                }
                $('#live-conversations').innerHTML = html || '<p class="text-muted">No active conversations.</p>';
                if (convos.length) lastLiveTimestamp = convos[0].last_message_at;

                // Click to expand
                $$('.live-card', $('#live-conversations')).forEach(card => {
                    card.style.cursor = 'pointer';
                    card.addEventListener('click', () => showConversation(card.dataset.conv));
                });
            } catch (e) { /* ignore poll errors */ }
        }

        poll();
        liveInterval = setInterval(poll, 5000);
    }

    // ── Insights ──────────────���────────────────────────────���─────────────
    async function loadInsightsSetup() {
        tenants = await api('/api/tenants').catch(() => []);
        const sel = $('#insights-tenant-select');
        sel.innerHTML = '<option value="">Select tenant...</option>' +
            tenants.map(t => `<option value="${t.id}">${esc(t.name)}</option>`).join('');
    }

    async function loadInsights(tenantId) {
        try {
            const insights = await api(`/api/admin/insights?tenant_id=${tenantId}&days=30`);
            if (!insights.length) {
                $('#insights-list').innerHTML = '<div class="empty-state"><div class="empty-icon">&#x2728;</div><p>No insights available yet. Collect more data!</p></div>';
                return;
            }
            const typeLabels = { content_gap: 'Content Gap', performance: 'Performance', engagement: 'Engagement' };
            $('#insights-list').innerHTML = insights.map(i => `
                <div class="insight-card ${i.priority}">
                    <div class="insight-type">${typeLabels[i.type] || i.type}</div>
                    <h4>${esc(i.title)}</h4>
                    <p>${esc(i.description)}</p>
                </div>
            `).join('');
        } catch (e) { toast('Failed to load insights: ' + e.message, 'error'); }
    }

    // ── Settings ───────��─────────────────────────���───────────────────────
    async function loadSettings() {
        try {
            const health = await api('/health');
            $('#health-status').innerHTML = `
                <div class="stats-grid">
                    <div class="stat-card"><span class="stat-label">Status</span><span class="stat-value" style="color:${health.status === 'healthy' ? 'var(--success)' : 'var(--danger)'};">${health.status}</span></div>
                    <div class="stat-card"><span class="stat-label">Database</span><span class="stat-value" style="color:${health.db_connected ? 'var(--success)' : 'var(--danger)'};">${health.db_connected ? 'Connected' : 'Down'}</span></div>
                    <div class="stat-card"><span class="stat-label">Tenants</span><span class="stat-value">${health.total_tenants}</span></div>
                    <div class="stat-card"><span class="stat-label">Version</span><span class="stat-value">${health.version}</span></div>
                    <div class="stat-card"><span class="stat-label">Uptime</span><span class="stat-value">${Math.floor(health.uptime_seconds / 3600)}h ${Math.floor((health.uptime_seconds % 3600) / 60)}m</span></div>
                </div>`;
            $('#settings-api-key').value = API_KEY;
        } catch (e) { toast('Failed to load settings', 'error'); }
    }

    // ── Wizard (Feature 38) ────────────��─────────────────────────────────
    let wizardStep = 1;
    const WIZARD_STEPS = 5;

    function updateWizardUI() {
        $$('.wizard-progress .step').forEach(s => {
            const n = parseInt(s.dataset.step);
            s.classList.toggle('active', n === wizardStep);
            s.classList.toggle('done', n < wizardStep);
        });
        $$('.wizard-step').forEach(s => s.classList.toggle('active', parseInt(s.dataset.step) === wizardStep));
        $('#wiz-prev').disabled = wizardStep === 1;
        $('#wiz-next').textContent = wizardStep === WIZARD_STEPS ? 'Create Tenant' : 'Next';

        // Build review
        if (wizardStep === WIZARD_STEPS) {
            const name = $('#wiz-name').value || '(not set)';
            const slug = $('#wiz-slug').value || '(not set)';
            const email = $('#wiz-email').value || '(not set)';
            const color = $('#wiz-color').value;
            const welcome = $('#wiz-welcome').value;
            const urls = $('#wiz-urls').value.trim();
            const content = $('#wiz-content').value.trim();
            const qr = $('#wiz-quick-replies').value;

            $('#wiz-review').innerHTML = `
                <table>
                    <tr><td><strong>Name</strong></td><td>${esc(name)}</td></tr>
                    <tr><td><strong>Slug</strong></td><td><code>${esc(slug)}</code></td></tr>
                    <tr><td><strong>Email</strong></td><td>${esc(email)}</td></tr>
                    <tr><td><strong>Color</strong></td><td><span style="display:inline-block;width:20px;height:20px;background:${color};border-radius:4px;vertical-align:middle;"></span> ${color}</td></tr>
                    <tr><td><strong>Welcome</strong></td><td>${esc(welcome)}</td></tr>
                    <tr><td><strong>URLs to crawl</strong></td><td>${urls ? urls.split('\n').length + ' URL(s)' : 'None'}</td></tr>
                    <tr><td><strong>Direct content</strong></td><td>${content ? content.length + ' chars' : 'None'}</td></tr>
                    <tr><td><strong>Quick Replies</strong></td><td>${esc(qr) || 'None'}</td></tr>
                </table>`;
        }
    }

    async function createTenantFromWizard() {
        const name = $('#wiz-name').value.trim();
        const slug = $('#wiz-slug').value.trim();
        if (!name || !slug) { toast('Name and slug are required', 'error'); return; }

        try {
            // 1. Create tenant
            const tenant = await api('/api/tenants', {
                method: 'POST',
                body: JSON.stringify({
                    name, slug,
                    system_prompt: $('#wiz-system-prompt').value,
                    widget_config: {
                        primary_color: $('#wiz-color').value,
                        welcome_message: $('#wiz-welcome').value,
                    },
                }),
            });
            toast(`Tenant "${name}" created!`, 'success');

            // 2. Update with extra fields
            const qr = $('#wiz-quick-replies').value.split(',').map(s => s.trim()).filter(Boolean);
            const email = $('#wiz-email').value.trim();
            if (qr.length || email) {
                await api(`/api/tenants/${tenant.id}`, {
                    method: 'PATCH',
                    body: JSON.stringify({ quick_replies: qr, support_email: email || null }),
                });
            }

            // 3. Crawl URLs
            const urls = $('#wiz-urls').value.trim().split('\n').filter(u => u.trim());
            for (const url of urls) {
                try {
                    await api(`/api/tenants/${tenant.id}/documents/crawl`, {
                        method: 'POST',
                        body: JSON.stringify({ url: url.trim() }),
                    });
                    toast(`Crawled: ${url.trim().slice(0, 50)}...`, 'info');
                } catch (e) { toast(`Crawl failed for ${url}: ${e.message}`, 'error'); }
            }

            // 4. Direct content upload
            const content = $('#wiz-content').value.trim();
            if (content) {
                await api(`/api/tenants/${tenant.id}/documents`, {
                    method: 'POST',
                    body: JSON.stringify({ title: `${name} — Content`, content }),
                });
            }

            // Done — go to tenant detail
            wizardStep = 1;
            updateWizardUI();
            openTenantDetail(tenant.id);
        } catch (e) { toast('Failed: ' + e.message, 'error'); }
    }

    // ── Auto-slug ────────────────────────────────────────────────────────
    function autoSlug() {
        const name = $('#wiz-name').value;
        $('#wiz-slug').value = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
    }

    // ── Event Binding ────────────────────────────────────────────────────
    function init() {
        // Auth
        if (API_KEY) { tryLogin(API_KEY); }
        $('#btn-login').addEventListener('click', () => tryLogin($('#api-key-input').value.trim()));
        $('#api-key-input').addEventListener('keydown', e => { if (e.key === 'Enter') tryLogin(e.target.value.trim()); });

        // Navigation
        $$('.nav-menu a').forEach(a => a.addEventListener('click', e => {
            e.preventDefault();
            showPage(a.dataset.page);
        }));

        // Back button
        $('#btn-back-tenants').addEventListener('click', () => showPage('tenants'));

        // Tabs
        $$('.tab', $('#tenant-tabs')).forEach(t => t.addEventListener('click', () => {
            $$('.tab', $('#tenant-tabs')).forEach(x => x.classList.remove('active'));
            t.classList.add('active');
            loadTenantTab(t.dataset.tab);
        }));

        // Modal
        $('#modal-close').addEventListener('click', hideModal);
        $('#modal-overlay').addEventListener('click', e => { if (e.target === $('#modal-overlay')) hideModal(); });

        // Live monitor
        $('#live-tenant-select').addEventListener('change', e => {
            if (e.target.value) startLiveMonitor(e.target.value);
        });

        // Insights
        $('#insights-tenant-select').addEventListener('change', e => {
            if (e.target.value) loadInsights(e.target.value);
        });

        // Wizard
        $('#btn-new-tenant').addEventListener('click', () => {
            wizardStep = 1;
            updateWizardUI();
            $$('.page').forEach(p => p.classList.remove('active'));
            $('#page-wizard').classList.add('active');
        });
        $('#wiz-next').addEventListener('click', () => {
            if (wizardStep === WIZARD_STEPS) { createTenantFromWizard(); return; }
            wizardStep = Math.min(wizardStep + 1, WIZARD_STEPS);
            updateWizardUI();
        });
        $('#wiz-prev').addEventListener('click', () => {
            wizardStep = Math.max(wizardStep - 1, 1);
            updateWizardUI();
        });
        $('#wiz-name').addEventListener('input', autoSlug);
    }

    init();
})();
