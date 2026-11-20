import{num,esc}from'../../utils/format.js';import{badge,rdBadge}from'./status.js';
export function resultPanel(report){if(!report)return '<div class=empty>先在检验工作台执行辅导方案，结果会在这里留存。</div>';if(report.status!=='completed')return `<div class=empty>${badge(report.status)} ${esc(report.error||'后台任务执行中，请稍候…')}</div>`;const r=report.result;return `<div class=result-heading><div><span class=eyebrow>WELCH · 双侧检验</span><h2>两组均分相差 <em>${num(r.difference)} 分</em></h2><p>${r.significant?'差异达到预设显著性水平':'尚无足够证据拒绝均值相等假设'}。观察性分组需结合教学点背景解读。</p></div><span class=report-no>研究报告<br>№ ${String(report.id).padStart(3,'0')}</span></div><div class=effect><div><span>常规自习组</span><b>${num(r.control_mean)}</b><small>n = ${r.control_n}</small></div><div class=effect-line><span style="width:${Math.min(100,Math.max(0,r.control_mean))}%"></span><span class=treatment style="width:${Math.min(100,Math.max(0,r.intervention_mean))}%"></span></div><div><span>小组辅导组</span><b>${num(r.intervention_mean)}</b><small>n = ${r.intervention_n}</small></div></div><div class=stats-strip><div><label>p 值</label><strong>${r.p_value<.0001?'< 0.0001':num(r.p_value,4)}</strong></div><div><label>95% 差值区间</label><strong>[${num(r.ci_low)}, ${num(r.ci_high)}]</strong></div><div><label>Cohen d</label><strong>${num(r.cohen_d)}</strong></div><div><label>排除样本</label><strong>${r.excluded} / ${r.total_selected}</strong></div></div><p class=method>t = ${num(r.t,3)} · 自由度 ${num(r.df,2)} · α = 0.05 · 方向：干预 − 对照</p>`;}

const fmtCi=ci=>ci?`[${num(ci[0],2)}, ${num(ci[1],2)}]`:'—';

export function rdPanel(report){
 if(!report)return '<div class=empty>锁定资格名册并提交断点检验后，结果会在这里展示。</div>';
 if(!report.valid)return `<div class=invalid-banner>${rdBadge(report.status)} 该报告已因资格勘误失效。<p>${esc(report.invalidated_reason||'资格名册已修订')}</p><p>相关区间与检验不再成立，需重新计算后才能恢复。</p></div>`;
 if(report.status==='queued'||report.status==='running')return `<div class=empty>${rdBadge(report.status)} 后台任务执行中，请稍候…</div>`;
 if(report.status==='failed')return `<div class=empty>${rdBadge(report.status)} ${esc(report.error||'计算失败')}</div>`;
 const r=report.result||{};
 const ok=report.status==='completed';
 return `<div class=result-heading><div><span class=eyebrow>FUZZY RD · 局部线性 2SLS</span><h2>${ok?`实际参辅局部效应约 <em>${num(r.late,2)} 分</em>`:'<em>拒绝因果结论</em>'}</h2><p>${ok?'断点处合规者的局部平均效应；仅适用于带宽内的越线学员。':esc(r.reason||'识别条件不足，不能把差异解释为参辅效果。')}</p></div><span class=report-no>断点报告<br>№ ${String(report.id).padStart(3,'0')}</span></div>
 <div class=stats-strip><div><label>实际参辅 LATE</label><strong>${num(r.late,2)}</strong></div><div><label>95% 区间</label><strong>${fmtCi(r.late_ci)}</strong></div><div><label>参辅率跳变</label><strong>${num(r.first_stage_jump,2)}</strong></div><div><label>参辅率跳变 95% 区间</label><strong>${fmtCi(r.first_stage_ci)}</strong></div></div>
 <div class=stats-strip><div><label>结课成绩跳变</label><strong>${num(r.reduced_form_jump,2)}</strong></div><div><label>第一阶段 F</label><strong>${r.checks?.perfect_compliance?'完全合规':num(r.first_stage_F,1)}</strong></div><div><label>带宽</label><strong>${r.bandwidth==null?'未选定':num(r.bandwidth,2)}</strong></div><div><label>带宽内样本</label><strong>${r.window_n||0}（左 ${r.left_n||0} / 右 ${r.right_n||0}）</strong></div></div>
 ${r.checks?`<div class=check-grid><div><label>越线但未参辅</label><strong>${r.checks.above_cutoff_nonparticipants}</strong><small>资格侧未实际参辅</small></div><div><label>未越线却参辅</label><strong>${r.checks.below_cutoff_participants}</strong><small>门槛下侧实际参辅</small></div><div><label>入学分不同取值</label><strong>${r.discreteness?.left_distinct||0} / ${r.discreteness?.right_distinct||0}</strong><small>左侧 / 右侧</small></div><div><label>门槛质量点</label><strong>${num((r.discreteness?.mass_at_cutoff||0)*100,0)}%</strong><small>恰好等于门槛</small></div></div>`:''}
 ${r.refusals&&r.refusals.length?`<div class=notice danger><b>拒绝因果结论的原因</b><ul>${r.refusals.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`:''}
 ${r.assumptions?`<details class=assumptions><summary>识别假设（报告与导出同步保留）</summary><ol>${r.assumptions.map(a=>`<li>${esc(a)}</li>`).join('')}</ol><p class=method>${esc(r.method||'')}</p></details>`:''}
 ${r.bandwidth_basis?`<details class=assumptions open><summary>带宽选择依据（未使用结课成绩）</summary><p class=method>${esc(r.bandwidth_basis.rule||'')}：${esc(r.bandwidth_basis.reason||'')}</p><p class=method>结课成绩参与带宽选择：<b>${r.bandwidth_basis.uses_outcome?'是':'否'}</b>；两侧人数 ${r.bandwidth_basis.left_n||0} / ${r.bandwidth_basis.right_n||0}，不同入学分 ${r.bandwidth_basis.left_distinct||0} / ${r.bandwidth_basis.right_distinct||0}。</p></details>`:''}
 ${r.cutoff_sample?cutoffSample(r.cutoff_sample):''}`;
}

export function cutoffSample(rows,expanded=false){
 const sorted=[...rows].sort((a,b)=>Math.abs(a.u)-Math.abs(b.u));
 const shown=expanded?sorted:sorted.slice(0,20);
 return `<details class=assumptions ${expanded?'open':''}><summary>断点两侧样本（按距门槛远近排序，共 ${rows.length} 条${expanded?'':'，默认显示最近 20 条'}）</summary><div class=table-wrap><table><thead><tr><th>学号</th><th>入学分</th><th>距门槛</th><th>资格</th><th>实际参辅</th><th>结课成绩</th><th>类型</th></tr></thead><tbody>${shown.map(r=>`<tr><td>${esc(r.code)}</td><td>${num(r.enrollment_score,1)}</td><td>${num(r.u,1)}</td><td>${r.eligible?'越线':'未越线'}</td><td>${r.participated?'是':'否'}</td><td>${num(r.final_score,1)}</td><td>${r.eligible&&r.participated?'合规参辅':r.eligible&&!r.participated?'越线未参辅':!r.eligible&&r.participated?'未越线却参辅':'未越线未参辅'}</td></tr>`).join('')}</tbody></table></div></details>`;
}
