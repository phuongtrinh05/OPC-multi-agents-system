const tableSelect = document.getElementById('tableSelect');
        const limitInput = document.getElementById('limitInput');
        const maskToggle = document.getElementById('maskToggle');
        const loadBtn = document.getElementById('loadBtn');
        const content = document.getElementById('content');
        const opportunitySelect = document.getElementById('opportunitySelect');
        const agentRunBtn = document.getElementById('agentRunBtn');
        const agentContent = document.getElementById('agentContent');
        let workflowData = null;
        let workflowStep = 0;
        let workflowRunning = false;
        let workflowRunningStep = null;
        let workflowId = null;
        let finalDecisionStatus = 'Pending';
        let releaseDecisionStatus = 'Pending';
        let riskGateStatus = 'Pending';
        let riskMitigationNote = '';
        let workflowErrorMessage = '';
        let previewContractId = '';
        let workflowStarted = false;

        async function loadOpportunities() {
            opportunitySelect.innerHTML = '<option value="">⏳ Đang tải...</option>';
            try {
                const res = await fetch('/api/opportunities?_t=' + Date.now());
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                if (data.error) throw new Error(data.error);

                opportunitySelect.innerHTML = '<option value="">-- Chọn cơ hội (' + data.opportunities.length + ') --</option>';
                data.opportunities.forEach(item => {
                    const opt = document.createElement('option');
                    opt.value = item.contract_id;
                    opt.textContent = `${opportunityCode(item.contract_id)} · ${item.customer_name} (${item.customer_type || item.status} - ${item.contract_id} - ${moneyCompact(item.contract_value)})`;
                    opportunitySelect.appendChild(opt);
                });

                if (data.opportunities.length > 0) {
                    opportunitySelect.value = data.opportunities[0].contract_id;
                    await loadSelectedOpportunityPreview();
                }
            } catch (err) {
                console.error('loadOpportunities error:', err);
                opportunitySelect.innerHTML = '<option value="">❌ Lỗi: ' + err.message + '</option>';
                agentContent.innerHTML = `<div class="error-message">❌ Không tải được cơ hội kinh doanh: ${esc(err.message)}</div>`;
            }
        }

        async function loadSelectedOpportunityPreview() {
            const contractId = opportunitySelect.value;
            if (!contractId) {
                agentContent.innerHTML = '<div class="state-message"><div class="icon">🧭</div><h3>Sẵn sàng tiếp nhận hợp đồng</h3><p>Chọn cơ hội kinh doanh để xem Input Data.</p></div>';
                return;
            }

            previewContractId = contractId;
            workflowStep = 0;
            workflowRunning = false;
            workflowRunningStep = null;
            workflowStarted = false;
            finalDecisionStatus = 'Pending';
            releaseDecisionStatus = 'Pending';
            riskGateStatus = 'Pending';
            riskMitigationNote = '';
            workflowErrorMessage = '';
            updateOpportunityStatus(null);
            agentContent.innerHTML = '<div class="state-message"><div class="icon">⏳</div><h3>Đang nạp Input Data</h3><p>Agent đang lấy contract, customer, orders và screening từ MotherDuck.</p></div>';

            try {
                const res = await fetch('/api/workflow/start', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({contract_id: contractId})
                });
                const data = await res.json();
                if (data.error) throw new Error(data.error);
                if (previewContractId !== contractId) return;
                workflowData = data;
                workflowId = data.workflow_id;
                renderWorkflow();
            } catch (err) {
                updateOpportunityStatus('Input error', 'reject');
                agentContent.innerHTML = `<div class="error-message">❌ Không nạp được Input Data: ${esc(err.message)}</div>`;
            }
        }

        async function runOpportunityAgent() {
            const contractId = opportunitySelect.value;
            if (!contractId) { alert('Vui lòng chọn một cơ hội kinh doanh!'); return; }

            agentRunBtn.classList.add('loading');
            agentRunBtn.disabled = true;
            workflowStarted = true;
            if (!workflowData || workflowData.contract_id !== contractId) {
                agentContent.innerHTML = '<div class="state-message"><div class="icon">⚙️</div><h3>Agent đang tiếp nhận hồ sơ</h3><p>Nếu dữ liệu đủ, hệ thống tự chạy tiếp Finance + AI/NLP, Risk và Decision. Chỉ dừng khi cần clarification hoặc hold/override.</p></div>';
            }

            try {
                const res = await fetch('/api/workflow/start', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({contract_id: contractId})
                });
                const data = await res.json();
                if (data.error) throw new Error(data.error);
                workflowData = data;
                workflowId = data.workflow_id;
                workflowStep = 0;
                workflowRunning = false;
                workflowRunningStep = null;
                workflowStarted = true;
                finalDecisionStatus = 'Pending';
                releaseDecisionStatus = 'Pending';
                riskGateStatus = 'Pending';
                riskMitigationNote = '';
                workflowErrorMessage = '';
                renderWorkflow();
                if (!intakeHumanTrigger(data)) {
                    await continueAutomaticWorkflow(1);
                }
            } catch (err) {
                agentContent.innerHTML = `<div class="error-message">❌ ${esc(err.message)}</div>`;
            }

            agentRunBtn.classList.remove('loading');
            agentRunBtn.disabled = false;
        }

        function renderDecision(data) {
            renderWorkflow(data);
        }

        function renderWorkflow(data = workflowData) {
            if (!data) return;
            const workflowStatus = data.decision_card ? 'Decision Ready' : 'Workflow In Progress';
            const pillClass = data.decision_card ? 'ok' : 'neutral';
            updateOpportunityStatus(workflowStarted ? workflowStatus : null, pillClass);
            const showWorkflow = workflowStarted || workflowStep > 0 || data.decision_card || data.risk || data.openai_reasoning;

            agentContent.innerHTML = `
                ${renderInputDataSection(data)}
                ${showWorkflow ? `
                    <section class="workflow-block">
                        <div class="input-kicker">Agent Workflow</div>
                        <div class="workflow-section">
                            ${workflowErrorMessage ? `<div class="error-message">${esc(workflowErrorMessage)}</div>` : ''}
                            ${renderAgentWorkflowBoard(data)}
                            ${renderWorkflowCheckpoint(data)}
                        </div>
                    </section>
                ` : ''}
                ${data.decision_card ? `
                    <section class="decision-dashboard-block">
                        <div class="input-kicker decision-kicker">Decision Dashboard</div>
                        ${renderDecisionGateScreen(data)}
                    </section>
                ` : ''}
            `;
        }

        function renderAgentWorkflowBoard(data) {
            const screening = data.screening || {};
            const reasoning = data.openai_reasoning || {};
            const risk = data.risk || {};
            const financing = data.financing || {};
            const partner = data.partner || {};
            const decision = data.decision_card || {};
            const intakeTrigger = intakeHumanTrigger(data);
            const waitingAtIntakeGate = intakeTrigger && !data.openai_reasoning;
            const agents = [
                {
                    key: 'data_finance_agent',
                    icon: 'bi-database-check',
                    title: 'Data & Finance Agent',
                    status: data.agent_outputs?.data_finance_agent
                        ? waitingAtIntakeGate ? 'risk' : data.risk ? 'done' : workflowStarted ? 'active' : 'done'
                        : 'pending',
                    bullets: [
                        `Opportunity profile: ${screening.data_readiness_status || 'Pending'}`,
                        `Screening: ${screening.preliminary_screening_result || 'Pending'}`,
                        `Funding need: ${data.finance?.funding_need || 'Waiting Finance'}`,
                        `AI/NLP tool: ${reasoning.provider ? `${reasoning.provider} / ${reasoning.ai_used ? 'used' : 'fallback'}` : 'Waiting'}`
                    ]
                },
                {
                    key: 'risk_compliance_agent',
                    icon: 'bi-shield-check',
                    title: 'Risk & Compliance Agent',
                    status: data.risk ? (risk.risk_level === 'High' ? 'risk' : 'done') : data.openai_reasoning ? 'active' : 'pending',
                    bullets: [
                        `Risk level: ${risk.risk_level || 'Pending'}`,
                        `Rules: ${(risk.applicable_risk_flags || []).map(r => r.rule_id).join(', ') || 'Waiting'}`,
                        `Mode: ${risk.agent_reasoning?.ai_used ? 'AI + guardrail' : 'Rule/Waiting'}`
                    ]
                },
                {
                    key: 'decision_partner_agent',
                    icon: 'bi-diagram-3',
                    title: 'Decision & Partner Agent',
                    status: data.decision_card ? 'done' : data.risk ? 'active' : 'pending',
                    bullets: [
                        `Financing: ${financing.financing_need_type || 'Pending'}`,
                        `Partner: ${partner.banking_fit_hint || 'Pending'}`,
                        `Recommendation: ${decision.recommendation || 'Pending'}`
                    ]
                }
            ];

            return `
                <div class="agent-flow-board">
                    ${agents.map(renderAgentFlowCard).join('')}
                </div>
                <div class="agent-flow-note">
                    <i class="bi ${waitingAtIntakeGate ? 'bi-pause-circle' : 'bi-bezier2'}"></i>
                    <span>${waitingAtIntakeGate
                        ? `Workflow đang dừng có chủ đích tại Intake vì ${esc(intakeTrigger)}. Founder chọn tiếp tục, yêu cầu bổ sung dữ liệu, hoặc Hold bên dưới.`
                        : 'Workflow tự chạy theo handoff 3 agent. AI/NLP là tool trong Data & Finance; Decision & Partner Agent mới mở dashboard đầy đủ.'}</span>
                </div>
            `;
        }

        function renderWorkflowCheckpoint(data) {
            const trigger = intakeHumanTrigger(data);
            if (!trigger || data.openai_reasoning) return '';
            return `
                <div class="workflow-hitl-card">
                    <div>
                        <span class="hitl-label"><i class="bi bi-person-check"></i> Human-in-the-loop checkpoint</span>
                        <h4>${esc(trigger)} tại Data & Finance Agent</h4>
                        <p>${trigger === 'Need Clarification'
                            ? 'Agent phát hiện dữ liệu còn thiếu/chưa chắc. Founder có thể yêu cầu bổ sung trước khi chạy Finance + AI/NLP.'
                            : 'Agent đề xuất tạm dừng vì kết quả screening là Hold. Founder vẫn có quyền override để tiếp tục phân tích nếu muốn xem toàn bộ Decision Card.'}</p>
                    </div>
                    <textarea id="hitl-note-step0" placeholder="Founder note: lý do tiếp tục, dữ liệu cần bổ sung, hoặc quyết định hold..."></textarea>
                    <div class="hitl-actions">
                        <button class="hitl-btn approve" onclick="continueAutomaticWorkflow(1)">Continue Analysis Anyway</button>
                        <button class="hitl-btn warn" onclick="holdWorkflow('step0', 'Need clarification: đã ghi nhận yêu cầu bổ sung dữ liệu trước khi phân tích sâu.')">Request Data</button>
                        <button class="hitl-btn reject" onclick="holdWorkflow('step0', 'Hold: workflow dừng tại intake theo quyết định Founder.')">Hold</button>
                    </div>
                    <div class="wizard-message" id="wizard-message-step0">Đang chờ Founder quyết định tại checkpoint này.</div>
                </div>
            `;
        }

        function renderAgentFlowCard(agent) {
            const template = document.getElementById('agent-flow-card-template');
            if (!template) {
                return `<button class="agent-flow-card ${agent.status}" onclick="openAgentPopup('${agent.key}')" type="button">${esc(agent.title)}</button>`;
            }
            const node = template.content.firstElementChild.cloneNode(true);
            node.classList.add(agent.status);
            node.setAttribute('onclick', `openAgentPopup('${agent.key}')`);
            node.querySelector('.agent-flow-icon i').classList.add(agent.icon);
            node.querySelector('[data-agent-title]').textContent = agent.title;
            node.querySelector('[data-agent-bullets]').innerHTML = agent.bullets
                .map(item => `<li>${esc(item)}</li>`)
                .join('');
            return node.outerHTML;
        }

        function updateOpportunityStatus(label, className = 'neutral') {
            const pill = document.getElementById('opportunityStatusPill');
            if (!pill) return;
            if (!label) {
                pill.className = 'opportunity-status-pill is-hidden';
                pill.innerHTML = '';
                return;
            }
            const icon = label === 'Decision Ready'
                ? 'bi-clipboard-check'
                : label === 'Accept'
                ? 'bi-check-circle'
                : label === 'Reject'
                    ? 'bi-x-circle'
                    : label === 'Workflow In Progress'
                        ? 'bi-hourglass-split'
                        : 'bi-shield-check';
            pill.className = `opportunity-status-pill ${className}`;
            pill.innerHTML = `<i class="bi ${icon}"></i><span>${esc(label)}</span>`;
        }

        function openAgentPopup(agentKey) {
            const modal = document.getElementById('agentModal');
            const content = document.getElementById('agentModalContent');
            if (!modal || !content || !workflowData) return;
            content.innerHTML = buildAgentPopupContent(agentKey, workflowData);
            modal.classList.add('open');
        }

        function closeAgentPopup(event) {
            if (event && event.target?.id !== 'agentModal') return;
            const modal = document.getElementById('agentModal');
            if (modal) modal.classList.remove('open');
        }

        function buildAgentPopupContent(agentKey, data) {
            const output = data.agent_outputs?.[agentKey] || {};
            const title = output.agent_name || agentTitle(agentKey);
            const role = output.role || 'Waiting for this agent to run.';
            const rows = agentPopupRows(agentKey, data);
            const technical = output.handoff_payload
                ? `<details class="technical-details"><summary>Technical handoff</summary><pre class="handoff">${esc(JSON.stringify(output.handoff_payload, null, 2))}</pre></details>`
                : '';
            const graphContext = output.knowledge_graph_context
                ? `<details class="technical-details"><summary>Knowledge graph view + SQL tools</summary><pre class="handoff">${esc(JSON.stringify({
                    graph_view: output.knowledge_graph_context.agent_view,
                    entities: output.knowledge_graph_context.entities,
                    relationships: output.knowledge_graph_context.relationships,
                    sql_tool_plan: output.sql_tool_plan || output.knowledge_graph_context.sql_tools
                }, null, 2))}</pre></details>`
                : '';
            return `
                <div class="agent-modal-head">
                    <span class="agent-flow-icon"><i class="bi ${agentIcon(agentKey)}"></i></span>
                    <div>
                        <h3>${esc(title)}</h3>
                        <p>${esc(role)}</p>
                    </div>
                </div>
                <div class="agent-popup-grid">
                    ${rows.map(([label, value]) => `
                        <div class="agent-popup-row">
                            <span>${esc(label)}</span>
                            <strong>${esc(renderValue(value))}</strong>
                        </div>
                    `).join('')}
                </div>
                ${section('Agent Action', output.actions || ['Chưa chạy agent này.'])}
                ${graphContext}
                ${technical}
            `;
        }

        function agentPopupRows(agentKey, data) {
            const screening = data.screening || {};
            const finance = data.finance || {};
            const reasoning = data.openai_reasoning || {};
            const risk = data.risk || {};
            const financing = data.financing || {};
            const partner = data.partner || {};
            const card = data.decision_card || {};
            if (agentKey === 'data_finance_agent') {
                const aiTool = data.agent_outputs?.data_finance_agent?.tool_outputs?.ai_reasoning_tool;
                const fundingGap = finance.funding_gap || {};
                return [
                    ['Data readiness', screening.data_readiness_status || 'Pending'],
                    ['Screening result', screening.preliminary_screening_result || 'Pending'],
                    ['Feasibility', screening.feasibility_status || 'Pending'],
                    ['Funding gap', fundingGap.primary_need_label || finance.funding_need || 'Waiting Finance'],
                    ['Financial needs', financialNeedsLabel(finance.financial_needs) || 'Waiting Finance'],
                    ['Cashflow gap', finance.cashflow_gap_flag === undefined ? 'Waiting Finance' : boolText(finance.cashflow_gap_flag)],
                    ['AI/NLP tool', aiTool ? `${reasoning.provider || 'provider'} / ${reasoning.ai_used ? 'AI used' : 'fallback'}` : 'Pending'],
                    ['Cashflow reasoning', reasoning.cashflow_reasoning || 'Pending'],
                    ['Evidence', (reasoning.evidence_used || []).slice(0, 3).join('; ') || 'Pending']
                ];
            }
            if (agentKey === 'risk_compliance_agent') {
                return [
                    ['Risk level', risk.risk_level || 'Pending'],
                    ['Validated rules', (risk.applicable_risk_flags || []).map(r => r.rule_id).join(', ') || 'Pending'],
                    ['AI mode', risk.agent_reasoning?.ai_used ? `${risk.agent_reasoning.provider} / AI used` : 'Rule/Pending'],
                    ['Guardrail', risk.agent_reasoning?.guardrail_note || 'Pending']
                ];
            }
            return [
                ['Recommendation', card.recommendation || 'Pending'],
                ['Financing type', financing.financing_need_type || 'Pending'],
                ['Credit case', financing.matched_credit_case_id || 'Pending'],
                ['Banking fit', partner.banking_fit_hint || 'Pending'],
                ['External release required', card.human_in_the_loop?.external_release_gate_required ? 'TRUE' : 'FALSE/Pending']
            ];
        }

        function agentTitle(agentKey) {
            return {
                data_finance_agent: 'Data & Finance Agent',
                risk_compliance_agent: 'Risk & Compliance Agent',
                decision_partner_agent: 'Decision & Partner Agent'
            }[agentKey] || 'Agent';
        }

        function agentIcon(agentKey) {
            return {
                data_finance_agent: 'bi-database-check',
                risk_compliance_agent: 'bi-shield-check',
                decision_partner_agent: 'bi-diagram-3'
            }[agentKey] || 'bi-gear';
        }

        function renderInputDataSection(data) {
            const output = data.agent_outputs.data_finance_agent;
            const screening = data.screening;
            const finance = data.finance;
            const profile = data.opportunity_profile || output.outputs.opportunity_profile;
            const contract = profile.contract || {};
            const customer = profile.customer || {};
            const orders = profile.orders || [];
            const firstOrder = orders[0] || {};
            const linked = profile.linked_keys || {};
            const financing = data.financing || {};
            const partner = data.partner || {};
            const fundingGap = finance?.funding_gap || {};
            const humanTrigger = intakeHumanTrigger(data);
            const summaryTitle = `${contract.contract_id || data.contract_id} · ${customer.customer_name || 'Unknown Customer'}`;

            return `
                <div class="input-section">
                    <div class="input-kicker">Input Data</div>
                    <div class="input-grid">
                        ${inputDataCard('Opportunity Summary', 'bi-rocket-takeoff', [
                            ['Opportunity ID', contract.opportunity_id || opportunityCode(contract.contract_id || data.contract_id)],
                            ['Contract ID', contract.contract_id || data.contract_id],
                            ['Customer', customer.customer_name || 'N/A'],
                            ['Current Status', contract.status || 'N/A', true],
                            ['Evaluation Date', data.evaluation_date || 'N/A']
                        ])}
                        ${inputDataCard('Customer Profile', 'bi-person', [
                            ['Customer Name', customer.customer_name || 'N/A'],
                            ['Customer Type', customer.customer_type || 'N/A'],
                            ['Industry', customer.industry || customer.sector || 'N/A'],
                            ['Strategic Value', customer.strategic_value || 'N/A', String(customer.strategic_value || '').toLowerCase() === 'high'],
                            ['Payment Reliability', customer.payment_reliability ?? 'N/A']
                        ])}
                        ${inputDataCard('Contract Summary', 'bi-file-earmark-text', [
                            ['Contract Value', moneyCompact(contract.contract_value)],
                            ['Gross Margin', percent(contract.gross_margin)],
                            ['Payment Terms', contract.payment_terms || 'N/A'],
                            ['Description', contract.description || 'N/A'],
                            ['Status', contract.status || 'N/A']
                        ], 'purple')}
                        ${inputDataCard('Delivery Snapshot', 'bi-truck', [
                            ['Service', (linked.service_ids || []).join(', ') || firstOrder.service_id || 'N/A'],
                            ['Pricing Model', contract.pricing_model || firstOrder.pricing_model || 'N/A'],
                            ['Order Status', firstOrder.status || (orders.length ? `${orders.length} orders` : 'N/A'), String(firstOrder.status || '').toLowerCase().includes('pending')],
                            ['Estimated Cost', moneyCompact(firstOrder.estimated_cost || finance?.total_estimated_cost)],
                            ['Due Date', firstOrder.due_date || firstOrder.planned_end || 'N/A'],
                            ['Province Count', screening.province_count ?? 'N/A']
                        ])}
                        ${inputDataCard('Financial Snapshot', 'bi-wallet2', [
                            ['Open AR', finance ? moneyCompact(finance.total_open_ar) : 'Chưa chạy Finance'],
                            ['Funding Gap', finance ? moneyCompact(fundingGap.funding_gap_amount) : 'Pending finance step'],
                            ['Financial Needs', financialNeedsLabel(finance?.financial_needs) || 'Pending finance step'],
                            ['Projected Cash', finance?.cashflow_gap_months?.[0]?.projected_closing_cash ? moneyCompact(finance.cashflow_gap_months[0].projected_closing_cash) : 'N/A'],
                            ['Cash Reserve Min', finance?.cashflow_gap_months?.[0]?.cash_reserve_minimum ? moneyCompact(finance.cashflow_gap_months[0].cash_reserve_minimum) : 'N/A'],
                            ['Invoice Status', finance ? boolText(finance.cashflow_gap_flag) === 'TRUE' ? 'Cashflow gap' : 'No gap' : 'Pending finance step']
                        ])}
                        ${inputDataCard('Existing Financing', 'bi-credit-card-2-front', [
                            ['Selected Need', financing.financing_need_type || fundingGap.primary_need_label || 'Chờ Decision Agent'],
                            ['Required Precheck', (finance?.required_prechecks || []).join(', ') || 'N/A'],
                            ['Credit Case', financing.matched_credit_case_id || 'N/A'],
                            ['Bank Fit', partner.banking_fit_hint || 'N/A']
                        ], 'purple')}
                    </div>
                    <div class="intake-brief">
                        <h4>${esc(summaryTitle)}</h4>
                        <p>
                            Data readiness: <strong>${esc(screening.data_readiness_status)}</strong>.
                            Screening: <strong>${esc(screening.preliminary_screening_result)}</strong>.
                            Feasibility: <strong>${esc(screening.feasibility_status)}</strong>.
                            ${humanTrigger
                                ? `Cần human-in-the-loop vì ${esc(humanTrigger)}.`
                                : 'Không có trigger human ở intake, workflow có thể chạy xuống phần agent bên dưới.'}
                        </p>
                    </div>
                </div>
            `;
        }

        function renderWizardProgress() {
            const labels = [
                '1-2 · Intake & Screening',
                '3 · Finance + AI/NLP',
                '4 · Risk Rules',
                '5-10 · Decision + HITL'
            ];
            return `<div class="wizard-progress">${labels.map((label, idx) => {
                const cls = idx < workflowStep ? 'done' : idx === workflowStep ? 'active' : '';
                return `<div class="wizard-node ${cls}">${esc(label)}</div>`;
            }).join('')}</div>`;
        }

        function renderWizardScreen(data) {
            if (workflowStep === 0) return renderDataFinanceScreen(data);
            if (workflowStep === 1) return renderOpenAIReasoningScreen(data);
            if (workflowStep === 2) return renderRiskScreen(data);
            return renderDecisionGateScreen(data);
        }

        function agentKeyForStep(step) {
            if (step === 0) return 'data_finance_agent';
            if (step === 1) return 'data_finance_agent';
            if (step === 2) return 'risk_compliance_agent';
            return 'decision_partner_agent';
        }

        function renderAgentRunningScreen(data, step) {
            const key = agentKeyForStep(step);
            const pending = pendingAgentMeta(step);
            const output = data.agent_outputs[key] || pending;
            const reasoning = data.openai_reasoning || data.agent_outputs.data_finance_agent?.tool_outputs?.ai_reasoning_tool?.outputs?.openai_reasoning || {};
            const provider = (reasoning.provider || 'rule').toUpperCase();
            const isAi = step === 1;
            const isDecision = key === 'decision_partner_agent';
            const handoff = output?.handoff_payload || {};
            const summary = isAi
                ? `Provider ${provider} đang phân tích contract text, payment terms và delivery notes.`
                : isDecision
                    ? 'Đang match financing type, credit case và bank product để tạo Decision Card.'
                    : output?.role || 'Agent đang xử lý handoff.';
            const outputSummary = isAi
                ? `AI summary: ${(reasoning.logic_summary || [reasoning.cashflow_reasoning || 'đang chờ phản hồi provider']).slice(0, 2).join(' ')}`
                : key === 'risk_compliance_agent'
                    ? `Risk flags: ${(data.risk?.applicable_risk_flags || []).map(r => r.rule_id).join(', ') || 'None'}`
                    : isDecision
                        ? `Recommendation: ${data.decision_card?.recommendation || 'Pending'}`
                        : `Funding need: ${data.finance?.funding_need || 'Pending'}`;

            return `
                <div class="agent-run-note">
                    Đang chạy lại backend cho bước này. Màn này chỉ hiển thị reasoning summary/evidence, không hiển thị chain-of-thought nội bộ của model.
                </div>
                <div class="agent-running-panel">
                    <div class="agent-running-head">
                        <div>
                            <h4>${esc(output?.agent_name || 'Agent')}</h4>
                            <p>${esc(summary)}</p>
                        </div>
                        <span class="live-pill">${isAi ? provider + ' API CALL' : 'BACKEND RUNNING'}</span>
                    </div>
                    <div class="run-steps">
                        ${runningStepsFor(step).map((item, idx) => `
                            <div class="run-step">
                                <strong>Step ${idx + 1}</strong>
                                ${esc(item)}
                            </div>
                        `).join('')}
                    </div>
                    <div class="run-grid">
                        <div class="run-card active">
                            <span>1. Input</span>
                            <strong>${esc((output?.inputs || []).slice(0, 2).join(' + ') || 'Workflow handoff')}</strong>
                            <p>${esc(isAi ? 'Unstructured contract/payment/delivery text + preliminary finance signals.' : 'Nhận payload từ agent trước và bảng nghiệp vụ liên quan.')}</p>
                        </div>
                        <div class="run-card active">
                            <span>2. Agent Action</span>
                            <strong>${esc((output?.actions || [])[0] || 'Processing')}</strong>
                            <p>${esc((output?.actions || []).slice(1, 3).join(' '))}</p>
                        </div>
                        <div class="run-card active">
                            <span>3. Reasoning Summary</span>
                            <strong>${esc(outputSummary)}</strong>
                            <p>${esc(isAi ? ((reasoning.evidence_used || [reasoning.risk_narrative || 'AI đang tạo risk narrative.']).slice(0, 2).join(' | ')) : 'Rule/evidence được gom lại thành output cho bước tiếp theo.')}</p>
                        </div>
                        <div class="run-card">
                            <span>4. Handoff</span>
                            <strong>${esc(output?.handoff_to || 'Next agent')}</strong>
                            <p>${esc(JSON.stringify(handoff).slice(0, 180))}</p>
                        </div>
                    </div>
                </div>
            `;
        }

        function pendingAgentMeta(step) {
            if (step === 1) {
                return {
                    agent_name: 'Data & Finance Agent · AI/NLP Tool',
                    role: 'Data & Finance Agent is calling its internal AI/NLP tool for contract reasoning.',
                    inputs: ['Data & Finance Agent handoff', 'Contract/payment/delivery text'],
                    actions: [
                        'Call configured AI provider API.',
                        'Parse structured JSON reasoning.',
                        'Write AI reasoning back into finance/screening flags.'
                    ],
                    handoff_to: 'Risk & Compliance Agent',
                    handoff_payload: {status: 'waiting_for_ai_response'}
                };
            }
            if (step === 2) {
                return {
                    agent_name: 'Risk & Compliance Agent',
                    role: 'Mapping AI-enriched flags to compliance risk rules.',
                    inputs: ['AI-enriched Data & Finance handoff', '13_RISK_RULES'],
                    actions: ['Evaluate RR rules.', 'Aggregate risk severity.'],
                    handoff_to: 'Decision & Partner Agent',
                    handoff_payload: {status: 'waiting_for_risk_output'}
                };
            }
            return {
                agent_name: 'Decision & Partner Agent',
                role: 'Mapping financing need, credit case, partner product, Decision Card, and post-decision actions.',
                inputs: ['Risk output', 'Credit profile', 'Bank products'],
                actions: ['Match financing product and credit profile.', 'Generate Decision Card and post-decision action plan.'],
                handoff_to: 'Founder Final Approval',
                handoff_payload: {status: 'waiting_for_decision_card'}
            };
        }

        function renderDataFinanceScreen(data) {
            const output = data.agent_outputs.data_finance_agent;
            const screening = data.screening;
            const humanTrigger = intakeHumanTrigger(data);
            return `
                <div class="wizard-screen">
                    <div class="wizard-layout ${humanTrigger ? '' : 'single'}">
                        <div class="wizard-panel">
                            <h4>Data Intake & Screening Agent</h4>
                            <p>Bước 1-2: agent dựng Opportunity Profile và kiểm tra có đủ điều kiện đưa vào vòng phân tích sâu hay chưa.</p>
                            ${ceoBrief('Founder/CEO Brief', [
                                `Kết luận: ${screening.preliminary_screening_result}. ${screening.feasibility_status}.`,
                                `Dữ liệu chính: contract=${output.outputs.opportunity_profile.linked_keys.contract_id}, customer=${output.outputs.opportunity_profile.linked_keys.customer_id}.`,
                                `Tín hiệu cần chú ý: payment risk=${screening.customer_payment_risk}; segment fit=${screening.service_segment_fit}; province_count=${screening.province_count ?? 'N/A'}.`,
                                humanTrigger
                                    ? `Human trigger: ${humanTrigger}. Founder cần xác nhận trước khi tiếp tục phân tích.`
                                    : 'Không có trigger human: dữ liệu đủ, agent tự chuyển sang Finance + AI/NLP.'
                            ])}
                            <details class="technical-details">
                                <summary>Agent evidence + screening detail</summary>
                                ${section('Agent Action', [
                                    'Filter opportunity contracts by Negotiation/Pending expansion.',
                                    'Join customer, contract, orders, services, invoices and bank transaction references.',
                                    'Build Opportunity Profile, data readiness, customer/contract screening, gateway flags and feasibility check.'
                                ])}
                                ${section('Key Output', [
                                    `Target margin ref: ${percent(screening.target_margin_ref)} (${screening.target_margin_ref_source})`,
                                    `Gateway flags: ${screening.gateway_flags.join('; ') || 'None'}`
                                ])}
                            </details>
                        </div>
                        ${humanTrigger ? `
                            <div class="wizard-gate">
                                <h4>Human-in-the-loop · ${esc(humanTrigger)}</h4>
                                <p>${humanTrigger === 'Need Clarification'
                                    ? 'Agent phát hiện thiếu hoặc chưa chắc dữ liệu. Founder có thể yêu cầu bổ sung dữ liệu trước khi phân tích sâu.'
                                    : 'Agent đề xuất tạm dừng/hold. Founder có quyền override để tiếp tục phân tích nếu vẫn muốn xem Decision Card.'}</p>
                                <textarea id="hitl-note-step0" placeholder="Founder note: dữ liệu cần bổ sung hoặc lý do override/hold..."></textarea>
                                <div class="hitl-actions">
                                    <button class="hitl-btn approve" onclick="continueAutomaticWorkflow(1)">Continue Analysis Anyway</button>
                                    <button class="hitl-btn warn" onclick="holdWorkflow('step0', 'Need clarification: đã ghi nhận yêu cầu bổ sung dữ liệu trước khi phân tích sâu.')">Request Data</button>
                                    <button class="hitl-btn reject" onclick="holdWorkflow('step0', 'Hold: workflow dừng tại intake theo quyết định Founder.')">Hold</button>
                                </div>
                                <div class="wizard-message" id="wizard-message-step0"></div>
                            </div>
                        ` : ''}
                    </div>
                </div>
            `;
        }

        function renderOpenAIReasoningScreen(data) {
            const dataFinanceOutput = data.agent_outputs.data_finance_agent;
            const output = dataFinanceOutput.tool_outputs?.ai_reasoning_tool || {
                actions: dataFinanceOutput.actions || [],
                handoff_payload: dataFinanceOutput.handoff_payload || {},
                outputs: {core_decision_effect: []}
            };
            const reasoning = data.openai_reasoning || output.outputs.openai_reasoning || {};
            const handoff = output.handoff_payload || {};
            const providerName = (reasoning.provider || 'openai').toUpperCase();
            const status = reasoning.ai_used ? `${providerName} active` : `Fallback - kiểm tra ${providerName} API key/network`;
            const focusItems = reasoning.recommended_focus || [];
            const fundingGap = data.finance?.funding_gap || {};
            const primaryNeed = fundingGap.primary_need_label || 'N/A';
            const financialNeeds = financialNeedsLabel(data.finance?.financial_needs) || 'N/A';
            return `
                <div class="wizard-screen">
                    <div class="metric-grid">
                        ${metric('AI Provider Status', status)}
                        ${metric('Funding Gap', primaryNeed)}
                        ${metric('Financial Needs', financialNeeds)}
                        ${metric('Cashflow Gap', boolText(data.finance?.cashflow_gap_flag))}
                    </div>
                    <div class="wizard-layout single">
                        <div class="wizard-panel">
                            <h4>Data & Finance Agent · Finance + AI/NLP Tool</h4>
                            <p>Bước 3: Data & Finance Agent đo công nợ/cashflow và gọi AI/NLP tool đọc payment_terms, delivery_note, mô tả hợp đồng để tạo reasoning có cấu trúc.</p>
                            ${ceoBrief('Founder/CEO Brief', [
                                `Funding gap: ${primaryNeed}; amount=${money(fundingGap.funding_gap_amount || 0)}; confidence=${fundingGap.overall_confidence ?? 'N/A'}.`,
                                `Financial needs: ${financialNeeds}; required prechecks=${(data.finance?.required_prechecks || []).join(', ') || 'N/A'}.`,
                                `AI phân tích: ${reasoning.cashflow_reasoning || 'N/A'}`,
                                `Rủi ro nghiệp vụ: ${reasoning.risk_narrative || 'N/A'}`,
                                `CEO cần xem xét: ${(focusItems || []).slice(0, 3).join('; ') || 'N/A'}`
                            ])}
                            <details class="technical-details">
                                <summary>Agent evidence + AI handoff detail</summary>
                                ${section('Agent Action', output.actions)}
                                ${section('Finance Monitor Output', [
                                    `Estimated cost: ${money(data.finance?.total_estimated_cost || 0)}`,
                                    `Cashflow gap months: ${(data.finance?.cashflow_gap_months || []).map(m => m.month).join(', ') || 'None'}`,
                                    `Bank service required: ${boolText(reasoning.bank_service_required_flag)}`,
                                    `Operational complexity: ${reasoning.operational_complexity || 'N/A'}`,
                                    `Province count: ${reasoning.province_count ?? 'N/A'}`,
                                    `Confidence: ${reasoning.confidence ?? 'N/A'}`,
                                    `Core effect: ${output.outputs.core_decision_effect.join('; ')}`
                                ])}
                                ${section('Logic Summary', reasoning.logic_summary || [])}
                                ${section('Evidence Used', reasoning.evidence_used || [])}
                                ${section('Assumptions / Data Gaps', reasoning.assumptions_or_gaps || [])}
                            </details>
                            <details class="technical-details">
                                <summary>Technical AI JSON + handoff payload</summary>
                                <pre class="handoff">${esc(JSON.stringify(reasoning, null, 2))}</pre>
                                <pre class="handoff">${esc(JSON.stringify(handoff, null, 2))}</pre>
                            </details>
                        </div>
                    </div>
                </div>
            `;
        }

        function renderRiskScreen(data) {
            const output = data.agent_outputs.risk_compliance_agent;
            const risk = data.risk;
            const reasoning = risk.agent_reasoning || {};
            const mitigationRequested = riskGateStatus === 'Mitigation Requested';
            const riskRejected = riskGateStatus === 'Rejected';
            const riskGateClass = riskRejected ? 'block' : mitigationRequested ? '' : riskGateStatus === 'Approved' ? 'ok' : '';
            const mitigationItems = risk.applicable_risk_flags.map(r => `${r.rule_id}: ${r.required_action}`);
            return `
                <div class="wizard-screen">
                    <div class="metric-grid">
                        ${metric('Risk Level', risk.risk_level)}
                        ${metric('Risk Flags', risk.applicable_risk_flags.map(r => r.rule_id).join(', ') || 'None')}
                        ${metric('Owner', risk.applicable_risk_flags.map(r => r.owner_agent).filter(Boolean).join(', ') || 'N/A')}
                        ${metric('AI Risk Mode', `${reasoning.provider || 'rule'} / ${reasoning.ai_used ? 'AI used' : 'fallback'}`)}
                    </div>
                    <div class="wizard-layout single">
                        <div class="wizard-panel">
                            <h4>${esc(output.agent_name)}</h4>
                            <p>Bước 4: AI đề xuất risk rules từ profile đã enrich, sau đó Python guardrail đối chiếu lại với field gốc và sheet 13_RISK_RULES.</p>
                            ${ceoBrief('Founder/CEO Brief', [
                                `Mức rủi ro: ${risk.risk_level}. Flags đã validate: ${risk.applicable_risk_flags.map(r => r.rule_id).join(', ') || 'None'}.`,
                                `AI đọc được: ${(reasoning.summary || []).slice(0, 3).join(' ') || 'N/A'}`,
                                `Điều kiện cần kiểm soát: ${risk.applicable_risk_flags.map(r => `${r.rule_id} - ${r.required_action}`).join('; ') || 'None'}.`,
                                'Không có HITL ở bước này: Risk Agent tự handoff kết quả đã kiểm tra guardrail sang Decision Agent.',
                                reasoning.ai_used
                                    ? `Risk AI provider: ${reasoning.provider}. Prompt size: ${reasoning.prompt_bytes || 'N/A'} bytes.`
                                    : `Risk AI fallback: ${reasoning.friendly_error || reasoning.error || 'Provider unavailable; deterministic guardrails used.'}`
                            ])}
                            <details class="technical-details">
                                <summary>Agent evidence + guardrail detail</summary>
                                ${section('Agent Action', output.actions)}
                                ${section('Knowledge Graph Rules Read', [
                                    'Neo4j Aura Query API: RiskRule, Agent, HumanApproval, APIFunction paths',
                                    'agents/knowledge/rule_catalog.json',
                                    'agents/knowledge/agent_guardrails.json',
                                    '13_RISK_RULES and source observations from MotherDuck'
                                ])}
                                ${section('Rule Interpretation', reasoning.rule_interpretation || [])}
                                ${section('Evidence Used', reasoning.evidence_used || [])}
                                ${section('Guardrail Check', [
                                    `AI proposed: ${(reasoning.ai_proposed_rule_ids || []).join(', ') || 'None'}`,
                                    `Mandatory from source fields: ${(reasoning.guardrail_required_rule_ids || []).join(', ') || 'None'}`,
                                    `Final validated rules: ${(reasoning.final_rule_ids || []).join(', ') || 'None'}`
                                ])}
                            </details>
                            <details class="technical-details">
                                <summary>Technical risk reasoning JSON</summary>
                                <pre class="handoff">${esc(JSON.stringify(reasoning, null, 2))}</pre>
                            </details>
                        </div>
                    </div>
                </div>
            `;
        }

        function runningStepsFor(step) {
            if (step === 1) {
                return [
                    'Đọc rule_catalog, guardrails và payload từ Intake/Screening.',
                    'Gom evidence: payment_terms, delivery_note, AR, cashflow.',
                    'Gọi AI provider để tạo structured reasoning JSON.',
                    'Kiểm tra output rồi handoff sang Risk Agent.'
                ];
            }
            if (step === 2) {
                return [
                    'Đọc AI-enriched profile và sheet 13_RISK_RULES.',
                    'AI đề xuất risk flags kèm evidence.',
                    'Python guardrail đối chiếu lại với field gốc.',
                    'Tổng hợp risk level và điều kiện cần Founder duyệt.'
                ];
            }
            if (step === 3) {
                return [
                    'Đọc finance, risk handoff, credit profile và bank products.',
                    'AI phân tích tradeoff giữa approve, conditional accept, reject.',
                    'Guardrail giữ quyền quyết định cuối ở Founder.',
                    'Tạo Decision Card và external release gate.'
                ];
            }
            return [
                'Đọc hợp đồng/cơ hội từ MotherDuck.',
                'Join customer, contract, order, invoice và bank references.',
                'Kiểm tra data readiness, fit và feasibility.',
                'Chờ Founder shortlist trước khi phân tích sâu.'
            ];
        }

        function renderPostDecisionAutomation(card, financing, partner) {
            const financingType = financing.financing_need_type || 'None';
            const bankProductId = partner.matched_bank_product_id || null;
            const hasFinancingNeed = financingType !== 'None';
            const hasOutboundPayload = hasFinancingNeed && !!bankProductId;
            const externalRequired = card.human_in_the_loop.external_release_gate_required;
            const status = (condition, readyText, skipText) => condition ? readyText : skipText;
            return `
                <div class="post-automation">
                    <h4>Post-decision Automation theo luồng business</h4>
                    <p>Các hành động này chỉ được thực hiện sau khi Founder final approval = Approved. Nếu Founder reject, hệ thống chỉ lưu lý do và kết thúc.</p>
                    ${section('Automation Logic', [
                        '1. Generate document packet: luôn thực hiện nếu Founder approved.',
                        `2. Draft email/API payload: ${status(hasOutboundPayload, 'sẽ tạo vì có financing_need_type và matched_bank_product_id.', 'bỏ qua vì không có nhu cầu tài chính hoặc chưa match được bank product.')}`,
                        `3. Create task: ${hasOutboundPayload ? 'task gửi partner/customer đi kèm payload.' : hasFinancingNeed ? 'ghi chú founder tự liên hệ đối tác nếu không có API/product match.' : 'task nội bộ lưu trữ document, không gửi ra ngoài.'}`,
                        `4. HITL External Release Gate: ${externalRequired ? 'trigger vì có dữ liệu/hồ sơ gửi ra ngoài OPC.' : 'bỏ qua vì không có outbound partner payload.'}`
                    ])}
                </div>
            `;
        }

        function renderDecisionGateScreen(data) {
            const output = data.agent_outputs.decision_partner_agent;
            const card = data.decision_card;
            const financing = data.financing;
            const partner = data.partner;
            const risk = data.risk || {};
            const decisionReasoning = card.agent_reasoning || {};
            const externalRequired = card.human_in_the_loop.external_release_gate_required;
            const isAgentReject = card.recommendation === 'Reject';
            const externalResolved = !externalRequired || releaseDecisionStatus === 'Approved' || releaseDecisionStatus === 'Blocked';
            const isWorkflowDone = finalDecisionStatus === 'Rejected' || (finalDecisionStatus === 'Approved' && externalResolved);
            const finalChip = isAgentReject
                ? `Final approval: ${finalDecisionStatus} (agent recommends Reject)`
                : `Final approval: ${finalDecisionStatus}`;
            const releaseChip = externalRequired ? `External release: ${releaseDecisionStatus}` : 'External release: Not required';
            const finalChipClass = finalDecisionStatus === 'Rejected' ? 'block' : finalDecisionStatus === 'Approved' ? 'ok' : isAgentReject ? 'block' : '';
            const releaseChipClass = releaseDecisionStatus === 'Blocked' ? 'block' : releaseDecisionStatus === 'Approved' ? 'ok' : '';
            const canDecideRelease = externalRequired && finalDecisionStatus === 'Approved' && !isWorkflowDone;
            const approveLabel = isAgentReject ? 'Override & Approve' : 'Final Approve';
            const finalGateMessage = finalDecisionStatus === 'Rejected'
                ? 'Workflow Completed: Founder đã reject hợp đồng.'
                : isWorkflowDone ? 'Workflow Completed: Founder đã chốt hợp đồng và xử lý xong gate gửi dữ liệu ra partner.'
                : isAgentReject && finalDecisionStatus !== 'Approved'
                    ? 'Agent recommends Reject. Founder vẫn có thể override, nhưng phải nhập lý do rõ ràng trước khi approve.'
                    : finalDecisionStatus !== 'Approved' ? 'Bước cuối: Founder cần chốt approve/reject hợp đồng.'
                    : externalRequired && releaseDecisionStatus === 'Pending' ? 'Hợp đồng đã approve. Cần duyệt hoặc chặn External Release để kết thúc workflow.'
                    : externalRequired ? 'Cần duyệt external release trước khi gửi payload cho partner.' : 'Không cần gửi hồ sơ ra partner ở case này.';
            const confidence = Math.round(Number(partner.confidence_score || 0) * 100);
            const confidenceText = Number.isFinite(confidence) && confidence > 0 ? `${confidence}%` : 'N/A';
            return `
                <div class="decision-dashboard">
                    <div class="decision-dashboard-head">
                        <div>
                            <h3>Recommendation <i class="bi bi-stars"></i></h3>
                            <p>Generated by OPC Agentic AI workflow · Founder quyết định cuối</p>
                        </div>
                        <span class="decision-badge ${isAgentReject ? 'reject' : card.recommendation === 'Accept' ? 'accept' : 'conditional'}">${esc(card.recommendation)}</span>
                    </div>

                    <div class="decision-metrics">
                        <div class="decision-metric">
                            <span>Risk Level <i class="bi bi-info-circle"></i></span>
                            <strong class="${risk.risk_level === 'High' ? 'danger' : ''}">${esc(risk.risk_level || 'N/A')}</strong>
                        </div>
                        <div class="decision-metric">
                            <span>Partner Match Confidence</span>
                            <strong class="confidence">${esc(confidenceText)}</strong>
                            <div class="confidence-bar"><span style="width:${Math.min(Math.max(confidence || 0, 0), 100)}%"></span></div>
                        </div>
                        <div class="decision-metric">
                            <span>Recommended Partner</span>
                            <strong>${esc(partner.banking_fit_hint || 'N/A')}</strong>
                            <small>${esc(financing.financing_need_type || 'N/A')}</small>
                        </div>
                    </div>

                    <div class="decision-explain-grid">
                        <div class="decision-list reasons">
                            <h4><i class="bi bi-list-ul"></i> Reasons</h4>
                            <ul>${(card.recommendation_reasons || []).slice(0, 5).map(item => `<li>${esc(item)}</li>`).join('') || '<li>N/A</li>'}</ul>
                        </div>
                        <div class="decision-list conditions">
                            <h4><i class="bi bi-list-check"></i> Conditions</h4>
                            <ul>${(card.conditions || []).slice(0, 5).map(item => `<li>${esc(item)}</li>`).join('') || '<li>N/A</li>'}</ul>
                        </div>
                    </div>

                    <div class="decision-final-gate">
                        <label>Founder Final Approval — ghi chú (tùy chọn)</label>
                        ${isWorkflowDone ? '<div class="agent-run-note">Workflow Completed. Hồ sơ đã được chốt theo các gate của Founder.</div>' : ''}
                        <div class="final-action-row">
                            <textarea id="hitl-note-step3" placeholder="Ví dụ: đồng ý với điều kiện chia giai đoạn..."></textarea>
                            <button class="hitl-btn reject" ${isWorkflowDone ? 'disabled' : ''} onclick="finalizeWorkflow('Rejected')">Reject</button>
                            <button class="hitl-btn approve" ${isWorkflowDone ? 'disabled' : ''} onclick="finalizeWorkflow('Approved')">${approveLabel}</button>
                        </div>
                        ${canDecideRelease ? `<div class="external-action-row">
                            <button class="hitl-btn approve" ${canDecideRelease ? '' : 'disabled'} onclick="setReleaseStatus('Approved')">Approve External Release</button>
                            <button class="hitl-btn reject" ${canDecideRelease ? '' : 'disabled'} onclick="setReleaseStatus('Blocked')">Block External Release</button>
                        </div>` : ''}
                        <div class="wizard-message" id="wizard-message-step3">${finalGateMessage}</div>
                    </div>

                    <details class="technical-details decision-tech">
                        <summary>Agent reasoning + technical handoff</summary>
                        ${section('Recommendation Guardrail', [
                            `Deterministic guardrail: ${decisionReasoning.deterministic_recommendation || 'N/A'}`,
                            `AI proposed: ${decisionReasoning.ai_recommendation || 'N/A'}`,
                            `Final shown to Founder: ${decisionReasoning.final_guarded_recommendation || card.recommendation}`
                        ])}
                        <pre class="handoff">${esc(JSON.stringify(output.handoff_payload, null, 2))}</pre>
                    </details>
                </div>
            `;
        }

        async function advanceWorkflow(nextStep) {
            if (workflowRunning) return false;
            if (!workflowId) {
                alert('Vui lòng bấm Start Workflow trước!');
                return false;
            }

            workflowRunning = true;
            workflowRunningStep = nextStep;
            agentRunBtn.classList.add('loading');
            agentRunBtn.disabled = true;

            try {
                const stepEndpoint = nextStep === 1
                    ? 'ai-reasoning'
                    : nextStep === 2
                        ? 'risk'
                        : 'decision';
                const res = await fetch(`/api/workflow/${encodeURIComponent(workflowId)}/${stepEndpoint}`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({})
                });
                const data = await res.json();
                if (data.error) throw new Error(data.error);
                workflowData = data;
                workflowId = data.workflow_id || workflowId;
                workflowStep = nextStep;
                workflowErrorMessage = '';
            } catch (err) {
                const messageId = 'step' + Math.max(0, nextStep - 1);
                workflowRunning = false;
                workflowRunningStep = null;
                agentRunBtn.classList.remove('loading');
                agentRunBtn.disabled = false;
                workflowErrorMessage = `Không chạy được bước ${nextStep}: ${err.message}. Hãy kiểm tra API key/network hoặc dữ liệu đầu vào rồi thử lại.`;
                renderWorkflow();
                holdWorkflow(messageId, 'Agent run failed: ' + err.message);
                return false;
            }

            workflowRunning = false;
            workflowRunningStep = null;
            agentRunBtn.classList.remove('loading');
            agentRunBtn.disabled = false;
            renderWorkflow();
            return true;
        }

        async function continueAutomaticWorkflow(startStep) {
            for (let stepNo = startStep; stepNo <= 3; stepNo++) {
                const ok = await advanceWorkflow(stepNo);
                if (!ok) break;
            }
        }

        function intakeHumanTrigger(data) {
            const screening = data?.screening || {};
            const readiness = String(screening.data_readiness_status || '').toLowerCase();
            const result = String(screening.preliminary_screening_result || '').toLowerCase();
            const flags = (screening.gateway_flags || []).map(flag => String(flag).toLowerCase());
            if (readiness === 'incomplete') return 'Need Clarification';
            if (flags.some(flag => flag.includes('need clarification'))) return 'Need Clarification';
            if (result.includes('hold') || result.includes('reject') || result.includes('not shortlist')) return 'Hold';
            return null;
        }

        function holdWorkflow(stepId, message) {
            const el = document.getElementById('wizard-message-' + stepId);
            if (el) el.textContent = message;
        }

        function requestRiskMitigation() {
            const note = document.getElementById('hitl-note-step2')?.value || '';
            riskGateStatus = 'Mitigation Requested';
            riskMitigationNote = note.trim() || 'Founder yêu cầu Risk/Finance bổ sung mitigation trước khi Decision Agent match partner.';
            renderWorkflow();
        }

        function approveRiskGate() {
            const note = document.getElementById('hitl-note-step2')?.value || '';
            riskGateStatus = 'Approved';
            riskMitigationNote = note.trim();
            advanceWorkflow(3);
        }

        function rejectRiskGate() {
            const note = document.getElementById('hitl-note-step2')?.value || '';
            riskGateStatus = 'Rejected';
            riskMitigationNote = note.trim() || 'Founder reject tại Risk Gate.';
            renderWorkflow();
        }

        function riskGateMessage() {
            if (riskGateStatus === 'Mitigation Requested') {
                return 'Mitigation requested: workflow đang dừng ở Risk Gate. Founder có thể ghi điều kiện, sau đó Approve risk để chạy Decision Agent.';
            }
            if (riskGateStatus === 'Rejected') {
                return 'Workflow stopped at Risk Gate. Không chạy partner matching/Decision Card cho case này.';
            }
            if (riskGateStatus === 'Approved') {
                return 'Risk approved. Decision Agent đang/đã nhận handoff từ Risk Agent.';
            }
            return 'Chờ Founder quyết định: approve risk, yêu cầu mitigation, hoặc reject tại gate rủi ro.';
        }

        function finalizeWorkflow(message) {
            const note = document.getElementById('hitl-note-step3')?.value || '';
            const el = document.getElementById('wizard-message-step3');
            if (message === 'Approved' && workflowData?.decision_card?.recommendation === 'Reject' && !note.trim()) {
                if (el) el.textContent = 'Agent recommends Reject. Founder muốn override thì cần nhập lý do approve trước.';
                return;
            }
            finalDecisionStatus = message;
            if (message === 'Rejected') {
                releaseDecisionStatus = 'Blocked';
            }
            renderWorkflow();
            const updated = document.getElementById('wizard-message-step3');
            if (updated && note) updated.textContent += ` Note: ${note}`;
        }

        function setReleaseStatus(message) {
            const el = document.getElementById('wizard-message-step3');
            if (finalDecisionStatus !== 'Approved') {
                if (el) el.textContent = 'Please approve final contract before deciding external release.';
                return;
            }
            releaseDecisionStatus = message;
            renderWorkflow();
        }

        function renderHitlPanel(data) {
            const hitl = data.decision_card.human_in_the_loop;
            const externalNeeded = hitl.external_release_gate_required;
            return `
                <div class="hitl-panel">
                    <div class="hitl-header">
                        <h4>Founder Human-in-the-loop</h4>
                        <span class="pill neutral">Agent chỉ khuyến nghị · Founder chốt</span>
                    </div>
                    <div class="hitl-grid">
                        <div class="hitl-step">
                            <label>Gate 1 · Shortlist confirmation</label>
                            <div class="hitl-actions">
                                <button class="hitl-btn approve" onclick="setHitlStatus('shortlist', 'Approved')">Approve</button>
                                <button class="hitl-btn warn" onclick="setHitlStatus('shortlist', 'Need clarification')">Need Clarification</button>
                                <button class="hitl-btn reject" onclick="setHitlStatus('shortlist', 'Hold')">Hold</button>
                            </div>
                            <div class="hitl-status" id="hitl-shortlist">Pending founder confirmation</div>
                        </div>
                        <div class="hitl-step">
                            <label>Gate 2 · Final approval</label>
                            <div class="hitl-actions">
                                <button class="hitl-btn approve" onclick="setHitlStatus('final', 'Approved')">Final Approve</button>
                                <button class="hitl-btn reject" onclick="setHitlStatus('final', 'Rejected')">Reject</button>
                            </div>
                            <div class="hitl-status" id="hitl-final">Pending final approval</div>
                        </div>
                        <div class="hitl-step">
                            <label>Gate 3 · External release</label>
                            <div class="hitl-actions">
                                <button class="hitl-btn approve" ${externalNeeded ? '' : 'disabled'} onclick="setHitlStatus('external', 'Approved for partner release')">Approve Release</button>
                                <button class="hitl-btn reject" ${externalNeeded ? '' : 'disabled'} onclick="setHitlStatus('external', 'Blocked')">Block</button>
                            </div>
                            <div class="hitl-status" id="hitl-external">${externalNeeded ? 'Required before sending partner payload' : 'Not required for this decision'}</div>
                        </div>
                    </div>
                    <textarea class="hitl-note" id="hitl-note" placeholder="Founder note / reason / điều kiện bổ sung..."></textarea>
                </div>
            `;
        }

        function setHitlStatus(kind, value) {
            const el = document.getElementById('hitl-' + kind);
            if (el) el.textContent = value;
        }

        function renderAgentTrace(trace) {
            return (trace || []).map(agent => `
                <div class="agent-box">
                    <h4>${esc(agent.agent_name)}</h4>
                    <p>${esc(agent.role)}</p>
                    <span class="trace-label">Input</span>
                    <ul>${agent.inputs.map(item => `<li>${esc(item)}</li>`).join('')}</ul>
                    <span class="trace-label">Agent Action</span>
                    <ul>${agent.actions.map(item => `<li>${esc(item)}</li>`).join('')}</ul>
                    <span class="trace-label">Handoff → ${esc(agent.handoff_to)}</span>
                    <pre class="handoff">${esc(JSON.stringify(agent.handoff_payload, null, 2))}</pre>
                </div>
            `).join('');
        }

        function inputDataCard(title, icon, rows, tone = 'blue') {
            return `
                <div class="input-card">
                    <div class="input-card-head">
                        <span class="input-icon ${tone === 'purple' ? 'purple' : ''}"><i class="bi ${esc(icon)}"></i></span>
                        <h4>${esc(title)}</h4>
                    </div>
                    ${rows.map(([label, value, accent]) => inputDataRow(label, value, accent)).join('')}
                </div>
            `;
        }

        function inputDataRow(label, value, accent = false) {
            return `
                <div class="input-row">
                    <span>${esc(label)}</span>
                    <strong class="${accent ? 'accent' : ''}">${esc(value ?? 'N/A')}</strong>
                </div>
            `;
        }

        function metric(label, value) {
            return `<div class="metric-card"><span>${esc(label)}</span><strong>${esc(value ?? 'N/A')}</strong></div>`;
        }

        function step(label, value) {
            return `<div class="workflow-step"><span>${esc(label)}</span><strong>${esc(value ?? 'N/A')}</strong></div>`;
        }

        function section(title, items) {
            const rows = (items && items.length ? items : ['N/A'])
                .map(item => `<li>${esc(renderValue(item))}</li>`).join('');
            return `<div class="decision-section"><h4>${esc(title)}</h4><ul>${rows}</ul></div>`;
        }

        function ceoBrief(title, items) {
            const rows = (items && items.length ? items : ['N/A'])
                .map(item => `<li>${esc(renderValue(item))}</li>`).join('');
            return `<div class="ceo-brief"><h4>${esc(title)}</h4><ul class="brief-list">${rows}</ul></div>`;
        }

        function renderValue(value) {
            if (value === null || value === undefined || value === '') return 'N/A';
            if (Array.isArray(value)) return value.map(renderValue).join('; ');
            if (typeof value === 'object') {
                const entries = Object.entries(value);
                if (!entries.length) return 'N/A';
                if (entries.length === 1) {
                    const [key, val] = entries[0];
                    return `${key}: ${renderValue(val)}`;
                }
                return entries.map(([key, val]) => `${key}: ${renderValue(val)}`).join('; ');
            }
            return String(value);
        }

        function financialNeedsLabel(needs) {
            return (needs || [])
                .map(item => {
                    if (typeof item === 'string') return item;
                    return item?.need_type || item?.type || item?.financial_need || '';
                })
                .filter(Boolean)
                .join(', ');
        }

        function money(value) {
            if (value === null || value === undefined || value === '') return 'N/A';
            return Number(value).toLocaleString('vi-VN') + ' VND';
        }

        function opportunityCode(contractId) {
            const raw = String(contractId || '').trim();
            const match = raw.match(/(\d+)$/);
            return match ? `OPP-${match[1].padStart(3, '0')}` : (raw || 'OPP');
        }

        function moneyCompact(value) {
            if (value === null || value === undefined || value === '' || Number.isNaN(Number(value))) return 'N/A';
            const number = Number(value);
            if (Math.abs(number) >= 1_000_000_000) {
                return (number / 1_000_000_000).toLocaleString('vi-VN', { maximumFractionDigits: 2 }) + ' tỷ';
            }
            if (Math.abs(number) >= 1_000_000) {
                return (number / 1_000_000).toLocaleString('vi-VN', { maximumFractionDigits: 0 }) + 'tr';
            }
            return number.toLocaleString('vi-VN') + ' VND';
        }

        function percent(value) {
            if (value === null || value === undefined || value === '') return 'N/A';
            return (Number(value) * 100).toLocaleString('vi-VN', { maximumFractionDigits: 1 }) + '%';
        }

        function boolText(value) {
            return value ? 'TRUE' : 'FALSE';
        }

        // Load table list on page load
        async function loadTables() {
            tableSelect.innerHTML = '<option value="">⏳ Đang tải...</option>';
            try {
                const res = await fetch('/api/tables?_t=' + Date.now());
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                if (data.error) throw new Error(data.error);

                tableSelect.innerHTML = '<option value="">-- Chọn bảng (' + data.tables.length + ') --</option>';
                data.tables.forEach(t => {
                    const opt = document.createElement('option');
                    opt.value = t;
                    opt.textContent = t;
                    tableSelect.appendChild(opt);
                });
            } catch (err) {
                console.error('loadTables error:', err);
                tableSelect.innerHTML = '<option value="">❌ Lỗi: ' + err.message + '</option>';
                // Show error in content area too
                content.innerHTML = '<div class="error-message">❌ Không tải được danh sách bảng: ' + err.message + '<br><br>Hãy kiểm tra:<br>• Server Flask đang chạy?<br>• Truy cập đúng URL http://127.0.0.1:5000 ?<br><br><button onclick="loadTables()" style="padding:8px 16px;background:#3b82f6;border:none;color:#fff;border-radius:6px;cursor:pointer;font-family:Inter,sans-serif;">🔄 Thử lại</button></div>';
            }
        }

        async function loadData() {
            const table = tableSelect.value;
            if (!table) { alert('Vui lòng chọn một bảng!'); return; }

            const limit = limitInput.value || 100;
            const mask = maskToggle.checked;

            loadBtn.classList.add('loading');
            loadBtn.disabled = true;

            try {
                const res = await fetch(`/api/table/${encodeURIComponent(table)}?limit=${limit}&mask=${mask}`);
                const data = await res.json();
                if (data.error) throw new Error(data.error);

                renderTable(data);
            } catch (err) {
                content.innerHTML = `<div class="error-message">❌ ${err.message}</div>`;
            }

            loadBtn.classList.remove('loading');
            loadBtn.disabled = false;
        }

        function renderTable(data) {
            let html = '';

            // Info bar
            html += `
                <div class="info-bar">
                    <span>📋 <strong>${data.table_name}</strong> — ${data.total_rows} dòng (giới hạn: ${data.limit})</span>
                    <span class="badge">${data.columns.length} cột</span>
                </div>
            `;

            // Schema toggle
            html += `
                <div class="schema-toggle">
                    <button class="schema-btn" onclick="toggleSchema()">📐 Xem Schema</button>
                    <div class="schema-panel" id="schemaPanel">
                        <table>
                            <thead><tr><th>Cột</th><th>Kiểu dữ liệu</th><th>Nullable</th></tr></thead>
                            <tbody>
                                ${data.schema.map(s => `
                                    <tr>
                                        <td>${esc(s.column)}</td>
                                        <td>${esc(s.type)}</td>
                                        <td>${esc(s.nullable)}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            `;

            // Data table
            html += '<div class="table-wrapper"><table>';
            html += '<thead><tr>';
            data.columns.forEach(col => {
                html += `<th>${esc(col)}</th>`;
            });
            html += '</tr></thead><tbody>';

            data.rows.forEach(row => {
                html += '<tr>';
                row.forEach(cell => {
                    html += `<td title="${esc(cell)}">${esc(cell)}</td>`;
                });
                html += '</tr>';
            });

            html += '</tbody></table></div>';

            if (data.rows.length === 0) {
                html += `
                    <div class="state-message">
                        <div class="icon">📭</div>
                        <h3>Bảng trống</h3>
                        <p>Bảng "${data.table_name}" không có dữ liệu.</p>
                    </div>
                `;
            }

            content.innerHTML = html;
        }

        function toggleSchema() {
            const panel = document.getElementById('schemaPanel');
            if (panel) panel.classList.toggle('open');
        }

        function esc(str) {
            const div = document.createElement('div');
            div.textContent = str;
            return div.innerHTML;
        }

        // Init
        loadTables();
        loadOpportunities();
