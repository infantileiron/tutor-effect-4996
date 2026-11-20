import{store}from'../stores/business.js';import{esc,num}from'../utils/format.js';import{table}from'../components/common/table.js';import{rdPanel}from'../components/common/report.js';import{notice}from'../components/common/notice.js';import{rdBadge}from'../components/common/status.js';
export function conclusionsPage(){
 const reports=store.rdReports.filter(r=>r.status!=='queued'&&r.status!=='running');
 const selected=window.__rdConclusion?reports.find(r=>r.id===window.__rdConclusion):reports[0];
 return `<header class=page-head><div><span class=eyebrow>05 / REVIEW & DECISION</span><h1>教研结论</h1><p>把断点证据、识别假设和采纳意见一并归档。</p></div><button id=audit-button class=quiet ${store.user.role!=='admin'?'hidden':''}>查看审计</button></header>
 <label class=report-selector>选择断点报告<select id=rd-conclusion-report>${reports.map(r=>`<option value=${r.id} ${selected&&selected.id===r.id?'selected':''}>№ ${r.id} · ${esc(store.batches.find(b=>b.id===r.batch_id)?.title||'')} · r${r.batch_revision} · ${r.published?'已签核':'待签核'}${r.valid?'':' · 已失效'}</option>`).join('')}</select></label>
 <div id=rd-conclusion-detail>${rdConclusionDetail(selected)}</div><div id=audit-panel></div>`;
}
export function rdConclusionDetail(r){
 if(!r)return notice('没有可用的断点报告。先锁定资格名册并执行断点检验。');
 const editable=store.user.role!=='viewer'&&r.valid&&(!r.published||store.user.role==='admin');
 const canPublish=store.user.role==='admin'&&r.valid&&r.status==='completed';
 return `<section class=result-sheet>${rdPanel(r)}</section><div class=decision-grid><section><span class=eyebrow>教研解释与采纳建议</span><h2>${r.published?'负责人已签核':r.valid?'待负责人签核':'勘误后失效'}</h2><form id=rd-conclusion-form data-id=${r.id}><label>结论与后续行动<textarea name=conclusion rows=4 minlength=4 maxlength=3000 required ${editable?'':'disabled'}>${esc(r.conclusion)}</textarea></label>${editable?`<label class=check><input name=published type=checkbox ${r.published?'checked':''} ${canPublish?'':'disabled'}> 负责人签核发布（仅管理员，且须为可报告结果）</label><button class=primary>保存教研结论</button>`:''}</form>${r.status==='inconclusive'&&r.valid?notice('当前结果为“拒绝因果结论”，可归档解释，但不能签核为有效因果结论。'):''}</section><aside>${notice('报告导出包含断点估计、95% 区间、参辅率跳变、识别假设、带宽依据、两侧样本与名册修订号。')}<button class=quiet data-export-rd=${r.id} ${r.valid?'':'disabled'}>下载断点报告 JSON ↓</button></aside></div>`;
}
