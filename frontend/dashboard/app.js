const titles={quality:"质量总览",runs:"会话观测",regression:"回归中心",issues:"问题中心",feedback:"用户反馈",handoffs:"人工接管",rag:"Policy RAG",system:"系统管理"};
const state={view:"quality",runs:[],cases:[],issues:[],feedback:[],handoffs:[],selectedCases:new Set()};
const $=(selector)=>document.querySelector(selector);
const $$=(selector)=>[...document.querySelectorAll(selector)];

async function api(path,options={}){
  const response=await fetch(path,{credentials:"same-origin",headers:{"Content-Type":"application/json",...(options.headers||{})},...options});
  if(response.status===401){location.href="/login/";throw new Error("登录已失效");}
  if(response.status===409&&path.includes("auth")){location.href="/change-password/";throw new Error("需要修改密码");}
  const body=response.status===204?null:await response.json().catch(()=>null);
  if(!response.ok)throw new Error(body?.detail?.message||body?.detail||`服务请求失败（${response.status}）`);
  return body;
}
const esc=(value)=>String(value??"").replace(/[&<>"']/g,(char)=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[char]);
const pct=(value)=>value==null?"暂无":`${(value*100).toFixed(1)}%`;
const duration=(value)=>value==null?"暂无":value<1000?`${value} ms`:`${(value/1000).toFixed(2)} s`;
const date=(value)=>value?new Date(value).toLocaleString("zh-CN",{hour12:false}):"-";
const statusLabel=(value)=>({succeeded:"成功",failed:"失败",running:"运行中",waiting_confirmation:"等待确认",cancelled:"已取消",passed:"通过",blocked:"阻塞",active:"已激活",draft:"草稿",retired:"已停用",open:"待接入",in_progress:"处理中",investigating:"排查中",resolved:"已解决",resolved_verified:"已验证解决",ignored:"已忽略",new:"新反馈",reviewing:"处理中",dismissed:"已忽略"}[value]||value||"未知");
const badge=(value)=>`<span class="status ${esc(value)}">${esc(statusLabel(value))}</span>`;

function notice(message){const node=$("#global-notice");node.textContent=message;node.hidden=!message;}
function selectDashboardView(view,{history=true}={}){
  if(!titles[view])view="quality";state.view=view;
  $$('[data-dashboard-view]').forEach(node=>node.hidden=node.dataset.dashboardView!==view);
  $$('[data-view]').forEach(link=>link.setAttribute("aria-current",link.dataset.view===view?"page":"false"));
  $("#page-title").textContent=titles[view];
  if(history){const url=new URL(location.href);url.searchParams.set("view",view);window.history.pushState({},"",url);}
  closeNavigation();loadView(view).catch(error=>notice(error.message));
}
function syncViewFromUrl(){selectDashboardView(new URL(location.href).searchParams.get("view")||"quality",{history:false});}
function closeNavigation(){$("#sidebar").classList.remove("open");$("#nav-scrim").hidden=true;}

async function loadQuality(){
  const range=$("#quality-range").value;
  const [overview,trends,operations]=await Promise.all([api(`/api/v1/quality/overview?range=${range}`),api(`/api/v1/quality/trends?range=${range}`),api(`/api/v1/quality/operations?range=${range}`)]);
  const metrics=[
    ["运行总数",overview.total_runs,"全部来源",""],["成功率",pct(overview.success_rate),`${overview.successful_runs} 次成功`,"good"],
    ["失败率",pct(overview.error_rate),`${overview.failed_runs} 次失败`,overview.failed_runs?"bad":""],["等待确认",overview.waiting_confirmation_runs,"不计入失败率",""],
    ["P95 延迟",duration(overview.p95_duration_ms),`平均 ${duration(overview.average_duration_ms)}`,""],["工具调用",overview.tool_call_count,`失败率 ${pct(overview.tool_failure_rate)}`,overview.tool_failure_count?"bad":""],
    ["总 Token",overview.token_usage_available?overview.total_tokens.toLocaleString():"暂无",`${overview.prompt_tokens} 输入 / ${overview.completion_tokens} 输出`,""],
    ["估算成本",overview.cost_available?`¥${overview.total_estimated_cost_cny.toFixed(4)}`:"暂无目录价","仅完整计价时汇总",""],
    ["业务成功率",pct(overview.business_success_rate),"仅含可验证运行",""],
  ];
  $("#quality-metrics").innerHTML=metrics.map(([label,value,hint,tone])=>`<article class="metric ${tone}"><span>${label}</span><strong>${value}</strong><small>${hint}</small></article>`).join("");
  renderTrends(trends.items||[]);renderTools(overview.tools||[]);renderOperations(operations);
}
function renderOperations(data){
  const rag=data.rag||{},latency=data.latency||{};
  const metrics=[
    ["RAG 命中率",pct(rag.hit_rate),`${rag.hit_count||0} / ${rag.request_count||0} 次检索`,rag.degraded_count?"bad":"good"],
    ["RAG 降级",rag.degraded_count||0,`降级率 ${pct(rag.degraded_rate)}`,rag.degraded_count?"bad":""],
    ["政策引用率",pct(rag.policy_citation_rate),`${rag.policy_citation_count||0} 次回答获得政策证据`,""],
    ["检索耗时",duration(rag.average_latency_ms),"平均政策检索时间",""],
    ["首次响应",duration(latency.average_first_response_ms),"运行开始到首个回答",""],
    ["完整响应",duration(latency.average_complete_response_ms),"平均端到端耗时",""],
    ["工具耗时",duration(latency.average_tool_ms),"平均单次工具执行",""],
    ["人工闭环",duration(latency.average_handoff_resolution_ms),"创建到解决/取消",""],
  ];
  $("#operations-metrics").innerHTML=metrics.map(([label,value,hint,tone])=>`<article class="metric ${tone}"><span>${label}</span><strong>${value}</strong><small>${hint}</small></article>`).join("");
  $("#active-alerts").innerHTML=data.alerts?.length?`<div class="alert-list">${data.alerts.map(item=>`<article class="operation-alert ${esc(item.level)}"><div><strong>${esc(item.message)}</strong><small>${esc(item.code)}</small></div><b>${item.count}</b></article>`).join("")}</div>`:'<p class="empty">当前范围没有活动告警。</p>';
  $("#version-comparison").innerHTML=data.versions?.length?`<table><thead><tr><th>版本</th><th>样本</th><th>成功率</th><th>平均耗时</th><th>Token</th><th>成本</th></tr></thead><tbody>${data.versions.map(item=>`<tr><td><strong>${esc(item.model)}</strong><small>政策 ${esc(item.policy_version)} · 数据 ${esc(item.data_version)}</small></td><td>${item.run_count}</td><td>${pct(item.success_rate)}</td><td>${duration(item.average_duration_ms)}</td><td>${item.average_tokens==null?"暂无":Math.round(item.average_tokens).toLocaleString()}</td><td>${item.average_cost_cny==null?"暂无":`¥${item.average_cost_cny.toFixed(4)}`}</td></tr>`).join("")}</tbody></table>`:'<p class="empty">当前范围没有可比较的版本。</p>';
}
function renderTrends(items){
  if(!items.length){$("#quality-trends").innerHTML='<p class="empty">当前范围还没有运行数据。</p>';return;}
  const max=Math.max(...items.map(item=>item.total_runs),1);
  $("#quality-trends").innerHTML=items.map(item=>`<div class="trend-column" title="${item.date}：${item.total_runs} 次，成功率 ${pct(item.success_rate)}"><div class="trend-bar" style="--height:${Math.max(4,item.total_runs/max*190)}px"></div><strong>${item.total_runs}</strong><small>${item.date.slice(5)}</small></div>`).join("");
}
function renderTools(items){
  $("#tool-quality").innerHTML=items.length?`<table><thead><tr><th>工具</th><th>调用</th><th>失败</th><th>失败率</th></tr></thead><tbody>${items.map(item=>`<tr><td>${esc(item.name)}</td><td>${item.call_count}</td><td>${item.failure_count}</td><td>${pct(item.failure_rate)}</td></tr>`).join("")}</tbody></table>`:'<p class="empty">暂无工具调用。</p>';
}

async function loadRuns(){
  const status=$("#run-status-filter").value;const payload=await api(`/api/v1/runs?limit=100${status?`&status=${status}`:""}`);state.runs=payload.items;
  $("#runs-count").textContent=`${payload.total} 条`;$("#runs-list").innerHTML=payload.items.length?payload.items.map(run=>`<button class="list-item" data-run-id="${esc(run.run_id)}"><strong>${esc(run.conversation_id||run.run_id)}</strong>${badge(run.status)}<small>${esc(run.source)} · ${esc(run.planner_type)} · ${date(run.started_at)} · ${duration(run.duration_ms)}</small></button>`).join(""):'<p class="empty">暂无运行记录。</p>';
  $$('[data-run-id]').forEach(button=>button.addEventListener("click",()=>loadRunDetail(button.dataset.runId)));
}
async function loadRunDetail(id){
  const payload=await api(`/api/v1/runs/${encodeURIComponent(id)}`);const run=payload.run;
  const policies=payload.policy_evidence?.length?payload.policy_evidence.map(item=>`<li><a href="${esc(item.source_url)}" target="_blank" rel="noopener">${esc(item.title||item.policy_id)}</a></li>`).join(""):"<li>本次运行没有政策证据。</li>";
  $("#run-detail").innerHTML=`<div class="detail-grid"><div><span>状态</span>${badge(run.status)}</div><div><span>来源 / Planner</span><b>${esc(run.source)} / ${esc(run.planner_type)}</b></div><div><span>耗时</span><b>${duration(run.duration_ms)}</b></div><div><span>步骤</span><b>${run.step_count}</b></div><div><span>Token</span><b>${run.total_tokens??"暂无"}</b></div><div><span>估算成本</span><b>${run.estimated_cost_cny==null?"暂无目录价":`¥${run.estimated_cost_cny.toFixed(6)}`}</b></div><div><span>业务结果</span><b>${statusLabel(payload.business_outcome)}</b></div><div><span>版本</span><b>${esc(run.model||run.planner_type)} / ${esc(run.policy_version||"未记录")}</b></div></div><section class="evidence"><h4>政策证据</h4><ul>${policies}</ul></section><div class="timeline">${payload.steps.length?payload.steps.map(step=>`<article><strong>${step.sequence}. ${esc(step.name)}</strong>${badge(step.status)}<small>${esc(step.kind)} · ${duration(step.duration_ms)}</small></article>`).join(""):'<p class="empty">这条运行没有步骤记录。</p>'}</div><div class="action-row"><button type="button" data-convert-run="${esc(run.run_id)}">添加为回归用例</button></div>`;
  $('[data-convert-run]').addEventListener("click",()=>convertSource("run",run.run_id));
}

async function loadCases(){
  const payload=await api("/api/v1/regression/cases");state.cases=payload.items;$("#cases-count").textContent=`${payload.total} 个用例`;
  $("#case-list").innerHTML=payload.items.length?payload.items.map(item=>`<article class="case-row"><input type="checkbox" data-case-check="${esc(item.case_id)}" ${item.status!=="active"?"disabled":""} ${state.selectedCases.has(item.case_id)?"checked":""}/><div><p><strong>${esc(item.name)}</strong></p><small>${esc(item.origin_type)} · ${esc(item.fixture_type)} · ${date(item.updated_at)}</small></div>${badge(item.status)}<button class="secondary" type="button" data-case-status="${esc(item.case_id)}">${item.status==="active"?"停用":"激活"}</button></article>`).join(""):'<p class="empty">还没有回归用例，可从问题、反馈、运行详情或右上角创建。</p>';
  $$('[data-case-check]').forEach(node=>node.addEventListener("change",()=>{node.checked?state.selectedCases.add(node.dataset.caseCheck):state.selectedCases.delete(node.dataset.caseCheck);updateSelectedCount();}));
  $$('[data-case-status]').forEach(node=>node.addEventListener("click",()=>toggleCase(node.dataset.caseStatus)));updateSelectedCount();
}
function updateSelectedCount(){$("#selected-case-count").textContent=`已选 ${state.selectedCases.size} 项`;}
async function toggleCase(id){const item=state.cases.find(entry=>entry.case_id===id);await api(`/api/v1/regression/cases/${id}`,{method:"PATCH",body:JSON.stringify({status:item.status==="active"?"retired":"active"})});await loadCases();}
async function runBatch(){
  if(!state.selectedCases.size){notice("请先选择至少一个已激活用例。");return;}notice("回归批次正在运行，请稍候。");
  const payload=await api("/api/v1/regression/batches",{method:"POST",body:JSON.stringify({case_ids:[...state.selectedCases],planner_type:$("#batch-planner").value,max_steps:Number($("#batch-max-steps").value),verify_outcome_execution:true})});
  notice("");$("#batch-result-panel").hidden=false;$("#batch-status").innerHTML=badge(payload.status);$("#batch-results").innerHTML=`<div class="detail-grid"><div><span>总数</span><b>${payload.total_count}</b></div><div><span>通过</span><b>${payload.passed_count}</b></div><div><span>失败</span><b>${payload.failed_count}</b></div><div><span>阻塞</span><b>${payload.blocked_count}</b></div></div><div class="timeline">${payload.results.map(item=>`<article><strong>${esc(item.case_id)}</strong>${badge(item.status)}<small>${esc(item.failure_reason||"执行完成")}</small></article>`).join("")}</div>`;
}

async function loadIssues(){const payload=await api("/api/v1/observability/issues?limit=100");state.issues=payload.items;$("#issues-count").textContent=`${payload.total} 条`;$("#issues-list").innerHTML=payload.items.length?payload.items.map(item=>`<button class="list-item" data-issue-id="${esc(item.issue_id)}"><strong>${esc(item.summary)}</strong>${badge(item.status)}<small>${esc(item.source)} · ${esc(item.error_code)} · ${item.occurrence_count} 次 · ${date(item.last_seen_at)}</small></button>`).join(""):'<p class="empty">当前没有运行问题。</p>';$$('[data-issue-id]').forEach(node=>node.addEventListener("click",()=>renderIssue(node.dataset.issueId)));}
function renderIssue(id){const item=state.issues.find(entry=>entry.issue_id===id);$("#issue-detail").innerHTML=`<div class="detail-grid"><div><span>错误码</span><b>${esc(item.error_code)}</b></div><div><span>严重度</span><b>${esc(item.severity)}</b></div><div><span>首次出现</span><b>${date(item.first_seen_at)}</b></div><div><span>最近出现</span><b>${date(item.last_seen_at)}</b></div></div><p>${esc(item.sanitized_detail||item.summary)}</p><div class="action-row"><button type="button" data-issue-convert>添加为回归用例</button><button class="secondary" type="button" data-issue-review="investigating">标记排查中</button><button class="secondary" type="button" data-issue-review="resolved_verified">验证并解决</button><button class="secondary" type="button" data-issue-review="ignored">忽略</button></div>`;$('[data-issue-convert]').addEventListener("click",()=>convertSource("issue",id));$$('[data-issue-review]').forEach(node=>node.addEventListener("click",()=>reviewIssue(id,node.dataset.issueReview)));}
async function reviewIssue(id,status){await api(`/api/v1/observability/issues/${id}`,{method:"PATCH",body:JSON.stringify({status,developer_note:null})});await loadIssues();$("#issue-detail").innerHTML='<p class="empty">处理状态已更新。</p>';}

async function loadFeedback(){const payload=await api("/api/v1/observability/feedback?limit=100");state.feedback=payload.items;$("#feedback-count").textContent=`${payload.total} 条`;$("#feedback-list").innerHTML=payload.items.length?payload.items.map(item=>`<button class="list-item" data-feedback-id="${esc(item.feedback_id)}"><strong>${item.rating==="helpful"?"有帮助":"没帮助"} · ${esc(item.category||"未分类")}</strong>${badge(item.status)}<small>${esc(item.comment||"未填写补充意见")} · ${date(item.created_at)}</small></button>`).join(""):'<p class="empty">暂无用户反馈。</p>';$$('[data-feedback-id]').forEach(node=>node.addEventListener("click",()=>renderFeedback(node.dataset.feedbackId)));}
function renderFeedback(id){const item=state.feedback.find(entry=>entry.feedback_id===id);$("#feedback-detail").innerHTML=`<div class="detail-grid"><div><span>评价</span><b>${item.rating==="helpful"?"有帮助":"没帮助"}</b></div><div><span>分类</span><b>${esc(item.category||"未分类")}</b></div><div><span>会话</span><b>${esc(item.conversation_id)}</b></div><div><span>状态</span>${badge(item.status)}</div></div><p>${esc(item.comment||"用户未填写补充意见。")}</p><div class="action-row"><button type="button" data-feedback-convert>添加为回归用例</button><button class="secondary" type="button" data-feedback-review="reviewing">开始处理</button><button class="secondary" type="button" data-feedback-review="resolved">标记解决</button></div>`;$('[data-feedback-convert]').addEventListener("click",()=>convertSource("feedback",id));$$('[data-feedback-review]').forEach(node=>node.addEventListener("click",()=>reviewFeedback(id,node.dataset.feedbackReview)));}
async function reviewFeedback(id,status){await api(`/api/v1/observability/feedback/${id}`,{method:"PATCH",body:JSON.stringify({status,developer_note:null})});await loadFeedback();$("#feedback-detail").innerHTML='<p class="empty">处理状态已更新。</p>';}
async function convertSource(type,id){const item=await api(`/api/v1/regression/cases/from-${type}/${encodeURIComponent(id)}`,{method:"POST",body:"{}"});notice(`已创建回归草稿：${item.name}`);}

async function loadHandoffs(){
  const payload=await api("/api/v1/admin/handoffs");
  const filter=$("#handoff-status-filter").value;
  state.handoffs=(payload.handoffs||[]).filter(item=>!filter||item.status===filter);
  $("#handoffs-count").textContent=`${state.handoffs.length} 条`;
  $("#handoffs-list").innerHTML=state.handoffs.length?state.handoffs.map(item=>`<button class="list-item" data-handoff-id="${esc(item.ticket_id)}"><strong>${esc(item.customer_message||item.reason)}</strong>${badge(item.status)}<small>${esc(item.conversation_id)} · ${date(item.updated_at)}</small></button>`).join(""):'<p class="empty">当前筛选条件下没有人工工单。</p>';
  $$('[data-handoff-id]').forEach(node=>node.addEventListener("click",()=>loadHandoffDetail(node.dataset.handoffId)));
}
async function loadHandoffDetail(id){
  const payload=await api(`/api/v1/admin/handoffs/${encodeURIComponent(id)}`);const item=payload.handoff;
  const actions=item.status==="open"?'<button type="button" data-handoff-action="claim">接入处理</button><button class="secondary" type="button" data-handoff-action="cancel">取消工单</button>':item.status==="in_progress"?'<button type="button" data-handoff-action="resolve">标记已解决</button><button class="secondary" type="button" data-handoff-action="cancel">取消工单</button>':"";
  const messages=payload.messages.length?payload.messages.map(message=>`<article><strong>${message.role==="user"?"客户":"客服"}</strong><p>${esc(message.text||`[${message.kind}]`)}</p><small>${date(message.created_at)}</small></article>`).join(""):'<p class="empty">暂无可显示的会话消息。</p>';
  $("#handoff-detail").innerHTML=`<div class="detail-grid"><div><span>状态</span>${badge(item.status)}</div><div><span>原因</span><b>${esc(item.reason)}</b></div><div><span>会话</span><b>${esc(item.conversation_id)}</b></div><div><span>负责人</span><b>${esc(item.assigned_developer_user_id||"尚未分配")}</b></div></div><p>${esc(item.customer_message||item.context_summary||"未提供补充说明。")}</p><div class="timeline handoff-messages">${messages}</div><div class="action-row">${actions}</div>`;
  $$('[data-handoff-action]').forEach(node=>node.addEventListener("click",()=>transitionHandoff(id,node.dataset.handoffAction)));
}
async function transitionHandoff(id,action){await api(`/api/v1/admin/handoffs/${encodeURIComponent(id)}/${action}`,{method:"POST",body:"{}"});await loadHandoffs();await loadHandoffDetail(id);}

async function loadSystem(){
  const [system,developers]=await Promise.all([api("/api/v1/system/status"),api("/api/v1/admin/developers")]);
  const cards=[["Agent",`${system.agent.planner_type}${system.agent.model?` / ${system.agent.model}`:""}`,`策略版本 ${system.agent.policy_version||"未加载"}`],["工具后端",system.tools.backend_name,`${system.tools.managed_by_mcp?"MCP 托管":"本地适配"} · ${system.tools.tool_count} 个工具`],["数据库",`SQLite / v${system.database.migration_version}`,system.database.status],["数据规模",`${system.data.run_count} 次运行`,`${system.data.regression_case_count} 个用例 · ${system.data.issue_count} 个问题`]];
  $("#system-components").innerHTML=cards.map(([title,value,hint])=>`<article class="component"><h3>${esc(title)}</h3><p><b>${esc(value)}</b></p><p>${esc(hint)}</p></article>`).join("");
  $("#developers-count").textContent=`${developers.developers.length} 个账户`;$("#developers-list").innerHTML=developers.developers.map(item=>`<article class="developer-row"><div><p><strong>${esc(item.display_name)}</strong></p><small>${esc(item.email)} · ${statusLabel(item.status)}</small></div><button type="button" data-developer-id="${esc(item.user_id)}" data-developer-status="${item.status}">${item.status==="active"?"停用":"启用"}</button></article>`).join("");
  $$('[data-developer-id]').forEach(node=>node.addEventListener("click",()=>setDeveloperStatus(node.dataset.developerId,node.dataset.developerStatus==="active"?"disabled":"active")));
}
async function setDeveloperStatus(id,status){await api(`/api/v1/admin/developers/${id}/status`,{method:"PATCH",body:JSON.stringify({status})});await loadSystem();}

async function loadRag(){const status=await api("/api/v1/rag/status");const cards=[["检索架构",status.retrieval,`${status.document_count} 篇政策 · ${status.chunk_count} 个片段`],["向量模型",status.model,status.dense_available?"BGE 可用":"已降级为 BM25"],["语料分类",status.categories.length,status.categories.map(item=>`${item.name} ${item.count}`).join(" · ")]];$("#rag-status").innerHTML=cards.map(([title,value,hint])=>`<article class="component"><h3>${esc(title)}</h3><p><b>${esc(value)}</b></p><p>${esc(hint)}</p></article>`).join("");}
async function debugRag(){const payload=await api(`/api/v1/rag/debug?q=${encodeURIComponent($("#rag-query").value)}`);$("#rag-result-status").textContent=payload.dense_available?"BGE + BM25 融合":"BM25 降级模式";$("#rag-results").innerHTML=payload.hits.length?`<table><thead><tr><th>政策</th><th>分类</th><th>Dense</th><th>BM25</th><th>RRF</th><th>片段</th></tr></thead><tbody>${payload.hits.map(hit=>`<tr><td><a href="${esc(hit.source_url)}" target="_blank" rel="noopener">${esc(hit.title)}</a></td><td>${esc(hit.category)}</td><td>${hit.dense_rank??"-"}</td><td>${hit.bm25_rank??"-"}</td><td>${Number(hit.rrf_score).toFixed(5)}</td><td>${esc(hit.content)}</td></tr>`).join("")}</tbody></table>`:'<p class="empty">没有召回政策片段。</p>';}

async function loadView(view){notice("");return ({quality:loadQuality,runs:loadRuns,regression:loadCases,issues:loadIssues,feedback:loadFeedback,handoffs:loadHandoffs,rag:loadRag,system:loadSystem}[view]||loadQuality)();}
async function initialize(){
  const me=await api("/api/v1/auth/me");$("#developer-identity").textContent=me.display_name||me.email;
  $$('[data-view]').forEach(link=>link.addEventListener("click",event=>{event.preventDefault();selectDashboardView(link.dataset.view);}));
  $("#refresh-button").addEventListener("click",()=>loadView(state.view).catch(error=>notice(error.message)));$("#quality-range").addEventListener("change",loadQuality);$("#run-status-filter").addEventListener("change",loadRuns);
  $("#handoff-status-filter").addEventListener("change",loadHandoffs);
  $("#rag-debug-form").addEventListener("submit",event=>{event.preventDefault();debugRag().catch(error=>notice(error.message));});
  $("#new-case-button").addEventListener("click",()=>$("#case-form").hidden=false);$("#close-case-form").addEventListener("click",()=>$("#case-form").hidden=true);$("#run-batch-button").addEventListener("click",()=>runBatch().catch(error=>notice(error.message)));
  $("#case-form").addEventListener("submit",async event=>{event.preventDefault();const data=new FormData(event.currentTarget);await api("/api/v1/regression/cases",{method:"POST",body:JSON.stringify({name:data.get("name"),description:data.get("description"),origin_type:"tau2",origin_id:String(data.get("task_id")),fixture_type:"tau2_task",fixture:{task_id:String(data.get("task_id")),split:"base"},expected:{business_success:true},status:"active"})});event.currentTarget.reset();event.currentTarget.hidden=true;await loadCases();});
  $("#developer-form").addEventListener("submit",async event=>{event.preventDefault();const data=Object.fromEntries(new FormData(event.currentTarget));await api("/api/v1/admin/developers",{method:"POST",body:JSON.stringify(data)});event.currentTarget.reset();await loadSystem();});
  $("#logout-button").addEventListener("click",async()=>{await api("/api/v1/auth/logout",{method:"POST",body:"{}"});location.href="/login/";});
  $("#nav-toggle").addEventListener("click",()=>{$("#sidebar").classList.add("open");$("#nav-scrim").hidden=false;});$("#nav-scrim").addEventListener("click",closeNavigation);window.addEventListener("popstate",syncViewFromUrl);window.addEventListener("keydown",event=>{if(event.key==="Escape")closeNavigation();});syncViewFromUrl();
}
initialize().catch(error=>notice(error.message));
