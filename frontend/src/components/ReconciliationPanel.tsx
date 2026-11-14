import {useEffect, useMemo, useState} from 'react';
import {useReconciliations} from '../stores/reconciliations';
import {createReconciliation} from '../api/reconciliations';
import {canWrite} from '../stores/auth';
import {useTask} from '../hooks/useTask';
import Notice from './common/Notice';
import EmptyState from './common/EmptyState';
import {exclusionLabels} from '../constants/enums';
import {fixed, hour} from '../utils/format';
import type {Entity, Reconciliation, ReconciliationLedger, ReconciliationSideRow} from '../types/domain';

const runLabel=(r:Entity)=>r.id==='demo-run'?'十月基线':r.id==='demo-run-corrected'?'十月更正稿':r.id.slice(0,8);

function SingleSideTable({rows,title}:{rows:ReconciliationSideRow[];title:string}){
 return <section className="recon-single">
  <h3>{title}（{rows.length} 个小时，不参与归因）</h3>
  {rows.length===0?<p className="recon-empty">无单边小时。</p>:<div className="table-wrap"><table>
   <thead><tr><th>时刻 UTC</th><th>状态</th><th>隔离原因</th><th>电量 kWh</th><th>产量 kg</th></tr></thead>
   <tbody>{rows.map(r=><tr key={r.side+r.timestamp}>
    <td>{hour(r.timestamp)}</td>
    <td>{r.state==='valid'?'仅本侧有效':'本侧隔离'}</td>
    <td>{r.state==='excluded'?(exclusionLabels[r.reason]||r.reason):'—'}</td>
    <td>{r.kwh===null?'—':fixed(r.kwh,2)}</td>
    <td>{r.output_kg===null?'—':fixed(r.output_kg,2)}</td>
   </tr>)}</tbody>
  </table></div>}
 </section>;
}

function LedgerView({ledger}:{ledger:ReconciliationLedger}){
 const t=ledger.totals;
 if(!ledger.has_common_hours)return <div className="notice" role="alert">
  两次运行没有共同有效小时，无法进行电量差归因；全部观测已列入单边清单。请核对时间窗口、时区口径与隔离原因。
  <small>共同有效小时 {ledger.common_count} 个 · A侧单边 {ledger.only_a_count} · B侧单边 {ledger.only_b_count}</small>
 </div>;
 return <>
  <div className="recon-summary">
   <div><small>共同有效小时</small><strong>{ledger.common_count}</strong></div>
   <div><small>A 总电量 / B 总电量（kWh）</small><strong>{fixed(t.kwh_a,1)} / {fixed(t.kwh_b,1)}</strong></div>
   <div><small>总电量差 B−A（kWh）</small><strong>{fixed(t.kwh_delta,1)}</strong></div>
   <div><small>产量贡献（kWh）</small><strong className="recon-output">{fixed(t.output_effect,1)}</strong></div>
   <div><small>单位能耗贡献（kWh）</small><strong className="recon-intensity">{fixed(t.intensity_effect,1)}</strong></div>
   <div><small>未归因残差（kWh）</small><strong>{fixed(t.unattributed_kwh,6)}</strong></div>
  </div>
  <p className="note-rule">口径：按统一 UTC 时刻配对共同有效小时；每小时把 B−A 电量差按两种替换顺序（先换产量／先换单位能耗）分解后取平均，两项之和恒等于该小时电量差。逐时合计与总差额相等，单边及隔离观测单列且不参与归因。</p>
  <h3>逐时归因底稿</h3>
  <div className="table-wrap"><table>
   <thead><tr><th>时刻 UTC</th><th>A电量</th><th>B电量</th><th>电量差</th><th>A产量</th><th>B产量</th><th>A单耗</th><th>B单耗</th><th>产量贡献</th><th>能耗贡献</th><th>残差</th></tr></thead>
   <tbody>{ledger.hourly.map(r=><tr key={r.timestamp}>
    <td>{hour(r.timestamp)}</td><td>{fixed(r.kwh_a,2)}</td><td>{fixed(r.kwh_b,2)}</td>
    <td><b>{fixed(r.kwh_delta,2)}</b></td>
    <td>{fixed(r.output_a_kg,2)}</td><td>{fixed(r.output_b_kg,2)}</td>
    <td>{fixed(r.intensity_a,4)}</td><td>{fixed(r.intensity_b,4)}</td>
    <td className="recon-output">{fixed(r.output_effect,2)}</td>
    <td className="recon-intensity">{fixed(r.intensity_effect,2)}</td>
    <td>{fixed(r.residual,6)}</td>
   </tr>)}</tbody>
   <tfoot><tr>
    <td>合计</td><td>{fixed(t.kwh_a,2)}</td><td>{fixed(t.kwh_b,2)}</td>
    <td><b>{fixed(t.kwh_delta,2)}</b></td>
    <td>{fixed(t.output_a_kg,1)}</td><td>{fixed(t.output_b_kg,1)}</td>
    <td>—</td><td>—</td>
    <td className="recon-output">{fixed(t.output_effect,2)}</td>
    <td className="recon-intensity">{fixed(t.intensity_effect,2)}</td>
    <td>{fixed(t.unattributed_kwh,6)}</td>
   </tr></tfoot>
  </table></div>
  <div className="recon-single-grid">
   <SingleSideTable rows={ledger.only_a} title="A 侧单边 / 隔离观测"/>
   <SingleSideTable rows={ledger.only_b} title="B 侧单边 / 隔离观测"/>
  </div>
 </>;
}

export default function ReconciliationPanel({runs}:{runs:Entity[]}){
 const store=useReconciliations();
 const completed=useMemo(()=>runs.filter(r=>r.status==='completed'&&r.result?.observations),[runs]);
 const [runA,setRunA]=useState('demo-run');
 const [runB,setRunB]=useState('demo-run-corrected');
 const [activeId,setActiveId]=useState('');
 const {error,busy,act}=useTask();
 useEffect(()=>{
  const ids=completed.map(r=>r.id);
  if(ids.length&&!ids.includes(runA))setRunA(ids[0]);
  if(ids.length&&!ids.includes(runB))setRunB(ids.find(id=>id!==runA)||ids[0]);
 },[completed]);
 const items=store.items as Reconciliation[];
 const active:Reconciliation|undefined=items.find(x=>x.id===activeId)||items[0];
 const submit=()=>act(async()=>{
  if(runA===runB)throw new Error('请选择两条不同的运行');
  const created=await createReconciliation({run_a_id:runA,run_b_id:runB});
  await store.load();setActiveId(created.id);
 });
 const swap=()=>{setRunA(runB);setRunB(runA);};
 return <section className="recon-panel">
  <div className="section-heading"><h2>运行对账 · 电量差归因</h2></div>
  <p className="note-rule">青屿陶窑更正小时观测后，总电量差会混入样本增减。对账只在两次运行的共同有效小时上分解电量差：产量贡献与单位能耗（kWh/kg）贡献，取两种替换顺序的平均值。</p>
  <Notice message={error||store.error}/>
  {completed.length<2?<EmptyState text="至少需要两条已完成且含有效观测的运行才能对账。"/>:<div className="recon-form">
   <label>基准运行 A<select value={runA} onChange={e=>setRunA(e.target.value)}>{completed.map(r=><option key={r.id} value={r.id}>{runLabel(r)}</option>)}</select></label>
   <button type="button" className="secondary recon-swap" onClick={swap} disabled={busy}>互换 A / B ↔</button>
   <label>对比运行 B<select value={runB} onChange={e=>setRunB(e.target.value)}>{completed.map(r=><option key={r.id} value={r.id}>{runLabel(r)}</option>)}</select></label>
   {canWrite()&&<button type="button" onClick={()=>void submit()} disabled={busy||runA===runB}>发起对账并保存底稿快照</button>}
  </div>}
  {items.length>0&&<div className="recon-archives">
   <h3>历史对账底稿（创建时冻结，源数据重算不改旧底稿）</h3>
   <div className="recon-archive-list">{items.map((x:Reconciliation)=><button key={x.id} type="button" className={'secondary'+(active?.id===x.id?' active':'')} onClick={()=>setActiveId(x.id)}>
    {hour(x.created_at)} · {runLabel({id:x.snapshot.run_a_id} as Entity)} → {runLabel({id:x.snapshot.run_b_id} as Entity)} · 共同{x.snapshot.ledger.common_count}h
   </button>)}</div>
  </div>}
  {active&&<article className="recon-snapshot">
   <p className="eyebrow">FROZEN LEDGER · {hour(active.created_at)}</p>
   <h3>{active.snapshot.run_a_label||active.snapshot.run_a_id} → {active.snapshot.run_b_label||active.snapshot.run_b_id}</h3>
   <p className="note-rule">A 有效/隔离 {active.snapshot.frozen_run_a.valid_count}/{active.snapshot.frozen_run_a.excluded_count} · B 有效/隔离 {active.snapshot.frozen_run_b.valid_count}/{active.snapshot.frozen_run_b.excluded_count} · 底稿版本 v{active.snapshot.ledger.schema_version}（旧运行可兼容读取）</p>
   <LedgerView ledger={active.snapshot.ledger}/>
  </article>}
 </section>;
}
