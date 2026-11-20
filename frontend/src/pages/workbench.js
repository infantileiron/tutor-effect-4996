import{store}from'../stores/business.js';import{esc,num}from'../utils/format.js';import{resultPanel,rdPanel}from'../components/common/report.js';import{badge,rdBadge,batchBadge}from'../components/common/status.js';import{notice}from'../components/common/notice.js';
export function workbenchPage(){
 const locked=store.batches.filter(b=>b.status==='locked');
 const selected=window.__rdReport?store.rdReports.find(r=>r.id===window.__rdReport):store.rdReports[0];
 return `<header class=page-head><div><span class=eyebrow>04 / RD WORKBENCH</span><h1>断点检验</h1><p>以入学分门槛为断点，估计实际参辅的局部效果。带宽选择不看结课成绩。</p></div></header>
 <div class=run-bar><form id=rd-run-form><label>已锁定资格批次<select name=batch_id>${locked.map(b=>`<option value=${b.id}>${esc(b.title)} · 门槛 ${num(b.threshold,1)} · ${dirText(b.direction)} · 名册 ${b.roster_count}</option>`).join('')}</select></label><button class=primary ${store.user.role==='viewer'||!locked.length?'disabled':''}>提交断点检验 →</button></form><div><span class=eyebrow>识别约定</span><p>模糊断点 · 局部线性 2SLS<br>仅报告带宽内合规者 LATE</p></div></div>
 ${!locked.length?notice('还没有已锁定的资格批次。先到“资格批次”登记门槛与入学分并锁定名册。'):''}
 <section id=latest-rd class=result-sheet>${rdPanel(selected)}</section>
 ${selected?rdActions(selected):''}
 <div class=section-title><h2>断点检验记录</h2><span>勘误会使旧结果失效</span></div>
 <div class=run-history>${store.rdReports.map(r=>`<button class=history-entry data-rd-report=${r.id}>№ ${r.id}　${esc(store.batches.find(b=>b.id===r.batch_id)?.title||'批次')} ${rdBadge(r.status)}${r.valid?'':' · 已失效'}<small>r${r.batch_revision} · ${esc((r.created_at||'').slice(0,19).replace('T',' '))} UTC</small></button>`).join('')||'<div class=empty>还没有断点检验记录。</div>'}</div>
 ${notice('实际参辅必须单独登记。若分数离散、参辅率跳变过弱或越线参辅样本不足，系统会拒绝给出因果结论。')}
 <details class=assumptions><summary>附：两组直接比较（观察性，不能作因果解读）</summary>
 <div class=run-bar><form id=run-form><label>研究方案<select name=plan_id>${store.plans.map(p=>`<option value=${p.id}>${esc(p.title)} · ${esc(p.campus)}</option>`).join('')}</select></label><button class=primary ${store.user.role==='viewer'?'disabled':''}>提交后台检验 →</button></form><div><span class=eyebrow>分析约定</span><p>Welch 双侧检验 · 95% 置信区间<br>有效样本每组至少 2 条</p></div></div>
 <section id=latest-result class=result-sheet>${resultPanel(store.reports[0])}</section>
 <div class=section-title><h2>比较记录</h2><span>结果不会随成绩修订而改变</span></div>
 <div class=run-history>${store.reports.map(r=>`<button class=history-entry data-report=${r.id}>№ ${r.id}　${esc(store.plans.find(p=>p.id===r.plan_id)?.title||'方案')} ${badge(r.status)}<small>${esc((r.created_at||'').slice(0,19).replace('T',' '))} UTC</small></button>`).join('')||'<div class=empty>还没有两组比较记录。</div>'}</div>
 </details>`;
}
const dirText=d=>d==='gte'?'入学分 ≥ 门槛':'入学分 ≤ 门槛';
function rdActions(r){
 if(!r.valid)return `<div class=action-row>${store.user.role!=='viewer'?`<button class=primary data-recompute=${r.id}>按当前名册重算 →</button>`:''}<a class=text-btn href=#eligibility>回到资格批次登记勘误 →</a></div>`;
 if(r.status==='completed'||r.status==='inconclusive')return `<div class=action-row><button class=quiet data-export-rd=${r.id}>下载断点报告 JSON ↓</button>${store.user.role!=='viewer'?`<button class=primary data-rd-conclusion=${r.id}>起草研究结论 →</button>`:''}<a class=text-btn href=#eligibility>登记资格勘误 →</a></div>`;
 return '';
}
