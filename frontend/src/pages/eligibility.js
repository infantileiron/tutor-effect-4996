import{store,loadBatch}from'../stores/business.js';import{esc,num}from'../utils/format.js';import{table}from'../components/common/table.js';import{notice}from'../components/common/notice.js';import{batchBadge,rdBadge}from'../components/common/status.js';import{BATCH_STATUS,SIDE}from'../constants/enums.js';
const canEdit=()=>store.user.role!=='viewer';
const dirText=d=>d==='gte'?'入学分 ≥ 门槛':'入学分 ≤ 门槛';
export function eligibilityPage(){
 const can=canEdit();
 const editing=store.batchDetail&&store.batchDetail.status==='draft'?store.batchDetail:null;
 return `<header class=page-head><div><span class=eyebrow>03 / ELIGIBILITY BATCH</span><h1>资格批次</h1><p>先按入学分门槛划定资格，再锁定名册。实际参辅另记，越线不等于一定参辅。</p></div><a href=#workbench class=text-btn>进入断点检验 →</a></header>
 <div class=split><section>
  <div class=section-title><h2>批次台账</h2><span>${store.batches.length} 批</span></div>
  ${store.batches.map(b=>`<article class=plan-entry><span class=eyebrow>COHORT ${String(b.id).padStart(3,'0')} · ${esc(b.term||'未填学期')}</span><h2>${esc(b.title)} ${batchBadge(b.status)}</h2><div class=meta>门槛 ${num(b.threshold,1)} · ${dirText(b.direction)} · 名册 ${b.roster_count} / 候选 ${b.candidate_count} · 修订 r${b.revision}${b.latest_report_id?` · 最新报告 №${b.latest_report_id} ${rdBadge(b.latest_report_status)}`:''}</div><button class=text-btn data-open-batch=${b.id}>查看资格依据与名册 →</button>${can&&b.status==='draft'?`<button class=text-btn data-lock-batch=${b.id}>锁定资格名册 →</button>`:''}${can&&b.status==='locking'?`<button class=text-btn data-recover-batch=${b.id}>恢复原批 →</button>`:''}</article>`).join('')||notice('还没有资格批次。先在右侧登记期次、门槛和入学分。')}
  <div id=batch-detail>${store.batchDetail?batchDetail(store.batchDetail):''}</div>
 </section><aside class=side-sheet><span class=eyebrow>BATCH BUILDER</span><h2>${editing?'修订草稿批次':'登记资格批次'}</h2>${can?`<form id=batch-form><input type=hidden name=id value="${editing?editing.id:''}"><label>批次名称<input name=title required minlength=2 maxlength=120 value="${esc(editing?.title||'')}" placeholder="2026秋季 · 入学分 60 资格批次"></label><label>期次<input name=term maxlength=80 value="${esc(editing?.term||'2026秋季')}" placeholder="2026秋季"></label><div class=form-two><label>门槛（入学分）<input name=threshold type=number min=0 max=100 step=.1 required value="${editing?.threshold??60}"></label><label>资格方向<select name=direction><option value=gte ${editing?.direction!=='lte'?'selected':''}>入学分 ≥ 门槛</option><option value=lte ${editing?.direction==='lte'?'selected':''}>入学分 ≤ 门槛</option></select></label></div><div class=form-two><label>带宽规则<select name=bandwidth_rule><option value=auto_min_side_n ${editing?.bandwidth_rule!=='manual'?'selected':''}>自动（只看入学分）</option><option value=manual ${editing?.bandwidth_rule==='manual'?'selected':''}>手动固定带宽</option></select></label><label>手动带宽<input name=bandwidth type=number min=0 max=100 step=.1 value="${editing?.bandwidth??''}" placeholder="留空则自动"></label></div><div class=form-two><label>每侧最少人数<input name=min_side_n type=number min=3 max=200 value="${editing?.min_side_n??20}"></label><label>每侧最少不同分数<input name=min_side_distinct type=number min=3 max=100 value="${editing?.min_side_distinct??10}"></label></div><label>最低参辅率跳变<input name=min_participation_jump type=number min=.01 max=.99 step=.01 value="${editing?.min_participation_jump??.2}"></label><label>研究说明<textarea name=description rows=4 maxlength=2000>${esc(editing?.description||'')}</textarea></label><button class=primary>保存草稿</button><button type=reset class=quiet>清空 / 新建</button></form>`:notice('观察员只读。资格与参辅登记由分析员完成。')}
  ${notice('资格由入学分门槛决定；实际参辅单独登记，不改变资格名册。锁定后门槛与入学分只能通过勘误修改，勘误会使既有检验失效。')}
 </aside></div>`;
}

function batchDetail(b){
 const can=canEdit()&&b.status==='draft';
 const locked=b.status==='locked';
 const editing=b.status==='draft';
 const basis=b.basis||{};
 return `<section class=batch-sheet><div class=section-title><h2>资格依据</h2><span>${batchBadge(b.status)} · 修订 r${b.revision}</span></div>
 <div class=stats-strip><div><label>门槛</label><strong>${num(b.threshold,1)}</strong></div><div><label>资格规则</label><strong>${esc(dirText(b.direction))}</strong></div><div><label>越线人数</label><strong>${basis.eligible_count||0} / ${basis.roster_count||0}</strong></div><div><label>断点两侧</label><strong>${basis.left_count||0} / ${basis.right_count||0}</strong></div></div>
 <p class=method>名册校验码 ${esc(b.roster_checksum||'（锁定后生成）')}${b.locked_at?` · 锁定于 ${esc(b.locked_at.slice(0,19).replace('T',' '))} UTC`:''}</p>
 <p class=method>带宽规则 ${esc(b.bandwidth_rule)}，每侧至少 ${b.min_side_n} 人 / ${b.min_side_distinct} 个不同入学分；带宽选择不使用结课成绩。最低参辅率跳变 ${b.min_participation_jump}。</p>
 ${editing?`<form id=candidate-form class=inline-form><label>候选人<select name=student_id>${store.students.map(s=>`<option value=${s.id}>${esc(s.code)} · ${esc(s.name)}</option>`).join('')}</select></label><label>入学分<input name=enrollment_score type=number min=0 max=100 step=.1 required></label><button class=primary>登记候选人</button></form>
 <div class=section-title><h2>候选人（锁定前）</h2><span>${b.candidates.length} 人</span></div>${table(['学号 / 姓名','教学点','入学分','资格侧',''],b.candidates.map(c=>[`<b>${esc(c.code)}</b><small>${esc(c.name)}</small>`,esc(c.campus),num(c.enrollment_score,1),esc(SIDE[c.side]||c.side),`<button class=text-btn data-drop-candidate=${c.student_id}>移除</button>`]))}`:''}
 ${locked?notice('批次已锁定：门槛与入学分只能通过下方“资格勘误”修改，勘误将使既有检验立即失效。'):''}
 ${locked?`<div class=section-title><h2>资格名册（已锁定）</h2><span>${b.roster.length} 人 · ${esc(b.roster_checksum.slice(0,12))}…</span></div><div class=filter-row><label>名册筛选<select id=roster-filter><option value="">全部</option><option value=left>门槛下侧</option><option value=right>越线侧</option><option value=participated>已参辅</option><option value=not-participated>未参辅</option></select></label></div><div id=roster-table>${rosterTable(b)}</div>`:''}
 ${b.corrections.length?`<div class=section-title><h2>资格勘误</h2><span>${b.corrections.length} 条</span></div>${table(['时间 UTC','字段','原值 → 新值','修订','说明','操作人'],b.corrections.map(c=>[esc(c.created_at.slice(0,19).replace('T',' ')),esc(c.field),`${esc(c.old_value)} → ${esc(c.new_value)}`,`r${c.resulting_revision}`,esc(c.note||'—'),esc(c.actor)]))}`:''}
 ${b.reports.length?`<div class=section-title><h2>本批断点报告</h2><span>${b.reports.length} 份</span></div>${table(['报告','状态','修订','发布','失效原因'],b.reports.map(r=>[`<button class=text-btn data-rd-report=${r.id}>№ ${r.id}</button>`,rdBadge(r.status),`r${r.batch_revision}`,r.published?'已签核':'—',esc(r.invalidated_reason||'—')]))}`:''}
 ${locked?`<div class=section-title><h2>资格勘误</h2><span>勘误即失效既有检验</span></div>`+correctionPanel(b):''}
 </section>`;
}

export function rosterTable(b,filter=''){
 let rows=b.roster||[];
 if(filter==='left')rows=rows.filter(r=>r.side==='left');
 if(filter==='right')rows=rows.filter(r=>r.side==='right');
 if(filter==='participated')rows=rows.filter(r=>r.participated);
 if(filter==='not-participated')rows=rows.filter(r=>!r.participated);
 const canRecord=canEdit()&&b.status==='locked';
 return table(['学号 / 姓名','入学分','距门槛','资格','实际参辅','结课成绩','登记'],rows.map(r=>[`<b>${esc(r.code)}</b><small>${esc(r.name)} · ${esc(r.campus)}</small>`,num(r.enrollment_score,1),num(r.distance,1),r.eligible?'<span class=tag-right>越线</span>':'<span class=tag-left>未越线</span>',r.participated?'参辅':'未参辅',r.absent?'<span class=muted>缺考</span>':num(r.final_score,1),canRecord?`<button class=text-btn data-toggle-participation=${r.student_id} data-participated=${r.participated?'1':'0'}>${r.participated?'改为未参辅':'登记参辅'}</button>`:'只读']));
}

export function correctionPanel(b){
 if(!canEdit()||b.status!=='locked')return '';
 return `<form id=correction-form class=correction-form><input type=hidden name=batch_id value=${b.id}><label>勘误字段<select name=field><option value=enrollment_score>某人入学分</option><option value=threshold>门槛</option><option value=direction>资格方向</option><option value=participation>实际参辅</option></select></label><label>学员<select name=student_id><option value="">按字段需要选择</option>${b.roster.map(r=>`<option value=${r.student_id}>${esc(r.code)} · ${esc(r.name)}（${num(r.enrollment_score,1)}）</option>`).join('')}</select></label><label>新值<input name=new_value required placeholder="数字 / gte·lte / true·false"></label><label>勘误说明<input name=note maxlength=500 placeholder="依据与复核人"></label><button class=primary>登记勘误</button></form>${notice('勘误后相关检验立即失效，必须重算才能恢复；并发发布也不会留下未标注的旧结论。')}`;
}
