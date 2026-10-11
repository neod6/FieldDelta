const $ = id => document.getElementById(id);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const time = value => value ? new Date(value).toLocaleString(undefined, {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit'}) : 'Not recorded';
const pct = value => typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : 'Not recorded';
const clock = value => value ? new Date(value).toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit'}) : 'Not recorded';
const displayName = value => {
  const name=String(value || 'Unknown object').replaceAll('##','').trim();
  const names={'laptop computer':'Laptop','can drink':'Can','bottle':'Bottle','mouse':'Mouse','earbud case':'Earbud Case','fabric clothing':'Fabric Clothing','book':'Book'};
  return names[name.toLowerCase()] || name[0]?.toUpperCase()+name.slice(1);
};
const tag = value => `<span class="tag ${['UNCERTAIN','UNKNOWN','NOT_OBSERVED','NOT_ASSESSED','POSSIBLY_MISSING'].includes(value) ? 'warn' : value === 'REMOVED' ? 'bad' : ['UNCHANGED','ADDED'].includes(value) ? 'good' : ''}">${escape(value?.replaceAll('_',' ') || 'Not recorded')}</span>`;
let selectedScan = null, selectedSite = null, refreshBusy = false, detailToken = 0, selectionToken = 0;
let enrollmentRegistry = null, enrollmentKey = '';
let lastNewestScan=null;
const expandedSessions=new Set();
const expandedRemovalScans=new Set();
let sessionNumbers={};
let rawView=false, renameId=null, baselineOpened='';
const relevant = o => !o.ignored && (o.user_confirmed_name || o.enrollment_status==='CONFIRMED' || ['ADDED','MOVED','UNCHANGED','REMOVED','POSSIBLY_MISSING'].includes(o.status));
const editButton = (id,name) => `<button type="button" class="rename-button" data-rename="${escape(id)}" data-label="${escape(name)}" aria-label="Rename ${escape(displayName(name))}" title="Rename object"><img src="/dashboard/icons/pencil.svg" width="14" height="14" alt=""></button>`;
function reviewThumbnail(object,baseline) {
  const [x,y,x2,y2]=object.bbox;
  const w=Math.max(x2-x,.001),h=Math.max(y2-y,.001);
  return `<span class="review-thumbnail"><img src="/scans/${encodeURIComponent(baseline)}/image" alt="Baseline candidate ${escape(object.display_name)}" style="width:${100/w}%;height:${100/h}%;left:${-x*100/w}%;top:${-y*100/h}%"></span>`;
}
async function post(path,data) {
  const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  if (!response.ok) throw new Error((await response.json()).detail || 'Request failed');
  return response.json();
}
async function api(path) {
  const response = await fetch(path, {cache:'no-store'});
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json();
}
function failure() { $('error').hidden = false; $('error').textContent = 'Cannot reach FieldDelta server. Check that your iPhone and Mac are on the same network.'; $('connection').textContent = 'Disconnected'; }
function eventsHtml(events) {
  return events.length ? events.map(e => `<div class="evidence-row">${tag(e.type)} <b>${escape(e.label || e.object_id)}</b><small>${escape(e.object_id)} · Local: ${escape(e.local_type || 'Not recorded')} · Cloud: ${escape(e.cloud_type || 'Not recorded')}</small><small>${escape(e.reason || '')}</small></div>`).join('') : '<div class="empty">No recorded change events</div>';
}
function objectResultsHtml(items,memory=[]) {
  const groups=['REMOVED','POSSIBLY_MISSING','MOVED','ADDED','UNCERTAIN','UNCHANGED'];
  const labels={REMOVED:'Removed',POSSIBLY_MISSING:'Possibly Missing',MOVED:'Moved',ADDED:'Added',UNCERTAIN:'Needs Review',UNCHANGED:'Unchanged'};
  return groups.map(status=>{
    const objects=items.filter(o=>o.status===status && !o.ignored && (status!=='UNCERTAIN' || o.enrollment_status==='CONFIRMED' || o.user_confirmed_name));
    if (!objects.length) return '';
    return `<div class="change-group ${status.toLowerCase()}"><div class="change-kind">${labels[status]} <span>${objects.length}</span></div><div class="change-objects">${objects.map(o=>{
      const tracked=memory.find(m=>m.stable_id===o.object_id);
      return `<div><strong>${escape(displayName(o.label))}</strong><span>${status==='POSSIBLY_MISSING' || status==='UNCERTAIN' ? 'Needs review' : status==='REMOVED' ? 'Verified absence' : status==='UNCHANGED' ? 'Matched in both scans' : 'Confirmed change'}${tracked ? ` · Last seen ${escape(clock(tracked.last_seen))}` : ''}</span></div>`;
    }).join('')}</div></div>`;
  }).join('');
}
function removalSummaryHtml(items,expandable=false) {
  const removed=items.filter(o=>o.status==='REMOVED');
  const missing=items.filter(o=>o.status==='POSSIBLY_MISSING');
  const objects=removed.length ? removed : missing;
  if (!objects.length) return '';
  const number=({1:'One',2:'Two',3:'Three'})[objects.length] || objects.length;
  const verified=Boolean(removed.length);
  const title=`${number} ${verified ? 'Removed' : 'Possibly Removed'}`;
  const note=verified ? `${objects.length} objects removed` : `${objects.length} objects possibly removed · Needs review`;
  const names=objects.map(o=>`<div><strong>${escape(displayName(o.label))}</strong><span>${verified ? 'Verified absence' : 'Not observed in this scan. Removal has not been confirmed.'}</span></div>`).join('');
  return expandable ? `<details class="removal-summary"><summary>${note}</summary><div class="removal-names">${names}</div></details>` : `<div class="removal-headline ${verified ? 'verified' : 'review'}"><strong>${title}</strong><span>${verified ? 'Verified absence' : 'Needs review · Not a confirmed removal'}</span></div>`;
}
function stateObjectsHtml(objects) {
  return objects.map(o=>{
    const verified=['UNCHANGED','ADDED','MOVED'].includes(o.status);
    const status=o.status==='POSSIBLY_MISSING' ? 'Possibly Missing' : o.status==='REMOVED' ? 'Removed' : verified ? 'Present' : o.presence==='OBSERVED_CANDIDATE' ? 'Observed' : 'Needs Review';
    const tone=o.status==='REMOVED' ? 'removed' : o.status==='POSSIBLY_MISSING' ? 'possibly_missing' : verified ? 'present' : 'review';
    return `<article class="object-item ${tone}"><div class="object-top"><strong>${escape(displayName(o.label))}</strong><span class="object-status">${status}</span>${o.stable_id && relevant(o) ? editButton(o.stable_id,o.label) : ''}</div><span class="last-seen">Last seen ${escape(clock(o.last_seen))}</span><span class="object-note">${o.user_confirmed_name ? 'User-confirmed identity' : o.enrollment_status==='CONFIRMED' ? 'Tracked object' : verified ? 'Not yet confirmed as tracked' : 'Candidate · Needs review'}</span></article>`;
  }).join('');
}
async function accounts() {
  const items = await api('/accounts');
  $('account').innerHTML = items.map(a => `<option value="${escape(a.id)}">${escape(a.name)}</option>`).join('');
  $('account').value = items.find(a => a.id === 'demo-warehouse')?.id || items[0]?.id || '';
  await sites();
}
async function sites() {
  const token = ++selectionToken;
  const items = await api(`/sites?account_id=${encodeURIComponent($('account').value)}`);
  if (token !== selectionToken) return;
  $('site').innerHTML = items.map(s => `<option value="${escape(s.id)}">${escape(s.name)}</option>`).join('');
  $('site').value = items.find(s => s.has_baseline)?.id || items[0]?.id || '';
  selectedScan = null; lastNewestScan=null; selectedSite = $('site').value;
  await refresh();
}
async function refresh() {
  if (!selectedSite) return;
  const site = selectedSite;
  refreshBusy = true;
  try {
    const state = await api(`/sites/${encodeURIComponent(site)}/state`);
    const history = await api(`/sites/${encodeURIComponent(site)}/scans`);
    if (site !== selectedSite) return;
    $('error').hidden = true; $('connection').textContent = 'Backend Connected'; $('updated').textContent = `Updated ${new Date().toLocaleTimeString()}`;
    $('site-name').textContent = state.site.name;
    $('active-session').textContent=state.active_session ? `Inspection #${state.active_session.number} · Active` : 'No inspection yet';
    const baseline=history.find(s=>s.id===state.active_session?.baseline_scan_id);
    $('reference-info').textContent=baseline ? `Baseline ${clock(baseline.timestamp)}` : 'Awaiting baseline';
    $('registry-status').textContent = state.registry.status.replaceAll('_',' ');
    enrollmentRegistry=state.registry;
    const key=site+JSON.stringify(state.registry);
    if (key!==enrollmentKey) {
      enrollmentKey=key;
      $('enrollment-list').innerHTML=state.registry.objects.map(o => `<div class="enrollment-row ${o.ignored ? 'ignored' : ''}"><input type="checkbox" aria-label="Track ${escape(o.display_name)}" data-enroll="${escape(o.object_id)}" ${o.confirmed ? 'checked disabled' : o.ignored ? 'disabled' : ''}>${reviewThumbnail(o,state.registry.baseline_scan_id)}<span>${escape(displayName(o.display_name))}${o.ignored ? '<small>Ignored proposal</small>' : ''}</span><input aria-label="Display name for ${escape(o.display_name)}" data-name="${escape(o.object_id)}" value="${escape(o.display_name)}" maxlength="100" ${o.confirmed || o.ignored ? 'disabled' : ''}>${editButton(o.object_id,o.display_name)}${o.confirmed ? tag('CONFIRMED') : `<button type="button" data-ignore="${escape(o.object_id)}" data-ignored="${Boolean(o.ignored)}">${o.ignored ? 'Restore' : 'Ignore'}</button>`}</div>`).join('');
    }
    $('enrollment').hidden=!state.registry.baseline_scan_id;
    if (state.latest_scan?.scan_type==='baseline' && baselineOpened!==state.registry.baseline_scan_id) { $('enrollment').open=true; baselineOpened=state.registry.baseline_scan_id; }
    const result = state.latest_scan?.result || {};
    $('assessment').innerHTML = !state.has_baseline ? '<span class="overview-note">Awaiting first baseline</span>' : result.registration?.reliable === false ? '<span class="overview-note review">Review needed · Scene alignment is uncertain</span>' : (result.counts?.uncertain > 0 ? '<span class="overview-note review">Review needed · Experimental assessment</span>' : '<span class="overview-note">Latest scan assessed</span>');
    const missingIds=new Set((state.latest_scan?.object_results || []).filter(o=>o.status==='POSSIBLY_MISSING').map(o=>o.object_id));
    const priority = o => o.status === 'POSSIBLY_MISSING' ? -1 : o.status === 'NOT_OBSERVED' ? 0 : o.status === 'UNCERTAIN' ? 1 : o.status === 'NOT_ASSESSED' ? 2 : 3;
    const decisions=new Map((state.latest_scan?.object_results || []).map(o=>[o.object_id,o]));
    const memory = state.tracked_objects.map(o=>({...o,status:missingIds.has(o.stable_id) ? 'POSSIBLY_MISSING' : decisions.get(o.stable_id)?.status || o.status})).sort((a,b) => priority(a)-priority(b) || a.label.localeCompare(b.label));
    const nameOrder=o=>({Laptop:0,Bottle:1,Can:2,'Earbud Case':3,Mouse:4,Book:5}[displayName(o.label)] ?? 6);
    const canonicalMemory=new Map();
    for (const object of memory.filter(relevant)) {
      const key=object.canonical_id || object.stable_id;
      const previous=canonicalMemory.get(key);
      if (!previous || object.last_seen>previous.last_seen || object.last_seen===previous.last_seen && object.stable_id===key) canonicalMemory.set(key,{...object,stable_id:key});
    }
    const visible=[...canonicalMemory.values()]
      .sort((a,b)=>Number(b.enrollment_status==='CONFIRMED')-Number(a.enrollment_status==='CONFIRMED') || nameOrder(a)-nameOrder(b) || a.label.localeCompare(b.label));
    $('object-count').textContent=`(${visible.length})`;
    $('state-summary').textContent=`${memory.filter(o=>o.enrollment_status==='CONFIRMED').length} confirmed tracked ${memory.filter(o=>o.enrollment_status==='CONFIRMED').length===1 ? 'object' : 'objects'}`;
    $('object-list').innerHTML=stateObjectsHtml(visible.slice(0,6)) || '<div class="empty">No confirmed memory yet. Review and confirm baseline objects below.</div>';
    $('more-objects').hidden=visible.length<=6;
    $('other-object-list').innerHTML=stateObjectsHtml(visible.slice(6));
    $('memory').innerHTML = memory.map(o => `<tr><td>${escape(o.label)}<small>${escape(o.stable_id)}</small><small>${escape(o.enrollment_status.replaceAll('_',' '))}</small></td><td>${tag(o.presence)}</td><td>${tag(o.status)}</td><td>${pct(o.confidence)}</td><td>${escape(time(o.last_seen))}</td></tr>`).join('') || '<tr><td colspan="5" class="empty">No tracked candidates</td></tr>';
    $('counts').innerHTML = ['removed','moved','added','unchanged','uncertain'].map(k => `<div class="metric ${k}"><strong>${result.counts?.[k] ?? '—'}</strong><span>${k === 'uncertain' ? 'Uncertain observations' : k[0].toUpperCase()+k.slice(1)}</span></div>`).join('');
    $('latest-events').innerHTML = eventsHtml(result.events || []);
    $('object-results').innerHTML=objectResultsHtml(state.latest_scan?.object_results || [],memory) || `<div class="change-empty"><strong>${state.latest_scan?.scan_type==='baseline' ? 'Baseline captured · Awaiting confirmation' : state.has_baseline ? result.counts?.uncertain ? 'No confirmed changes · Review needed' : 'No confirmed changes' : 'Ready for your first inspection'}</strong></div>`;
    $('removal-headline').innerHTML=removalSummaryHtml(state.latest_scan?.object_results || []);
    $('history-count').textContent = `${history.length} scans`;
    const newest = history[0]?.id;
    const wasLatest = selectedScan===lastNewestScan;
    if (!selectedScan || !history.some(s => s.id === selectedScan) || wasLatest) selectedScan = newest || null;
    lastNewestScan=newest;
    const scanHtml=(s,index) => {
      const c = s.result?.counts || {}; const changes = (c.added || 0)+(c.removed || 0)+(c.moved || 0);
      const missing=(s.object_results || []).filter(o=>o.status==='POSSIBLY_MISSING');
      const review=(s.object_results || []).filter(o=>o.status==='UNCERTAIN' && o.enrollment_status==='CONFIRMED');
      const changed=(s.object_results || []).filter(o=>['ADDED','MOVED','REMOVED'].includes(o.status));
      const remembered=(s.object_results || []).filter(o=>o.enrollment_status==='CONFIRMED');
      const label=(s.result?.reprocessing ? 'Reprocessed ' : '')+(s.scan_type==='baseline' ? 'Baseline' : s.scan_type==='pending' ? 'Processing scan' : `Scan #${index+1}`);
      const note=s.processing_status!=='complete' ? s.processing_status==='failed' ? 'Needs attention' : 'Processing' : s.scan_type==='baseline' ? 'Reference photo' : missing.length ? `Possibly missing: ${missing.map(o=>displayName(o.label)).join(', ')}` : changed.length ? changed.map(o=>`${o.status.toLowerCase()}: ${displayName(o.label)}`).join(', ') : changes ? `${changes} ${changes===1 ? 'change' : 'changes'}` : review.length ? `Needs review: ${review.map(o=>displayName(o.label)).join(', ')}` : c.uncertain ? 'Needs review' : 'No confirmed changes';
      return `<button class="history-item ${s.id === selectedScan ? 'active' : ''} ${s.scan_type==='baseline' ? 'baseline' : ''}" aria-pressed="${s.id===selectedScan}" data-scan="${escape(s.id)}" data-timestamp="${escape(s.timestamp)}"><span class="timeline-dot"></span><img src="${escape(s.image_url)}" alt="Uploaded ${escape(s.scan_type)}" loading="lazy"><span><strong>${label}${s.id===state.latest_scan?.id ? '<span class="timeline-latest">Latest</span>' : ''}</strong><small class="timeline-time">${escape(clock(s.timestamp))}${s.id===selectedScan ? ' · Selected' : ''}</small><small class="timeline-note ${missing.length ? 'missing' : ''}">${escape(note)}</small>${remembered.length ? `<small class="timeline-memory">${escape(remembered.map(o=>displayName(o.label)).join(' · '))}</small>` : ''}</span></button>`;
    };
    const sessions=state.sessions || [];
    sessionNumbers=Object.fromEntries(sessions.map(s=>[s.id,s.number]));
    const renderSession=session=>{
      const scans=history.filter(s=>s.session_id===session.id).slice().reverse();
      const list=scans.map(scanHtml).join('') || '<div class="empty">Baseline pending</div>';
      return session.active ? `<div class="history-session"><div class="history-label">Active Inspection</div><h3>Inspection #${session.number}</h3><div class="timeline">${list}</div></div>` : `<details class="history-session previous-session" data-session="${escape(session.id)}" ${expandedSessions.has(session.id) ? 'open' : ''}><summary>Inspection #${session.number}<small>${new Date(session.created_at).toLocaleDateString('en-US',{month:'short',day:'numeric'})}</small></summary><div class="timeline">${list}</div></details>`;
    };
    $('history').innerHTML=sessions.filter(s=>s.active).map(renderSession).join('')+(sessions.some(s=>!s.active) ? '<div class="history-label previous-label">Previous Inspections</div>'+sessions.filter(s=>!s.active).map(renderSession).join('') : '') || '<div class="empty">No inspection history</div>';
    await inspect(selectedScan);
  } catch { if (site === selectedSite) failure(); }
  finally { refreshBusy = false; }
}
function photo(scan, title) {
  const boxes = (rawView ? scan.detected_objects : scan.product_objects || []).map(o => { const [x1,y1,x2,y2] = o.bbox; return `<div class="bbox" style="left:${x1*100}%;top:${y1*100}%;width:${(x2-x1)*100}%;height:${(y2-y1)*100}%"><span>${escape(rawView ? o.label : displayName(o.label))}${rawView ? ' '+pct(o.confidence) : ''}</span></div>`; }).join('');
  return `<div><div class="photo-title">${escape(title)} · ${escape(time(scan.timestamp))}</div><div class="photo-frame"><img src="${escape(scan.image_url)}" alt="${escape(title)} uploaded scan">${boxes}</div></div>`;
}
async function inspect(id) {
  const token = ++detailToken;
  if (!id) { $('inspection').hidden = true; return; }
  $('inspection').hidden = false;
  const scan = await api(`/scans/${encodeURIComponent(id)}/detail`);
  const previous = scan.previous_scan_id ? await api(`/scans/${encodeURIComponent(scan.previous_scan_id)}/detail`) : null;
  if (token !== detailToken || id !== selectedScan) return;
  $('scan-heading').textContent = `${sessionNumbers[scan.session_id] ? `Inspection #${sessionNumbers[scan.session_id]} · ` : ''}${clock(scan.timestamp)} · ${scan.scan_type==='baseline' ? 'Baseline' : 'Comparison'}`;
  $('scan-status').textContent = `Processing: ${scan.processing_status} · Cloud: ${scan.result?.cloud_status || 'Not recorded'}${scan.error ? ' · '+scan.error : ''}`;
  $('verify-removal').hidden=scan.scan_type!=='comparison' || !scan.registry.objects.some(o=>o.confirmed);
  $('verify-removal').disabled=scan.removal_review?.status==='queued';
  const checks=scan.removal_review?.checks || scan.result?.controlled_removal || [];
  $('removal-evidence').innerHTML=(scan.removal_review ? `<div class="evidence-row">Removal verification: ${escape(scan.removal_review.status)} ${escape(scan.removal_review.error || '')}</div>` : '')+checks.map(c=>`<details><summary>${escape(c.label)} · ${escape(c.type)}</summary><pre>${escape(JSON.stringify(c,null,2))}</pre></details>`).join('');
  $('photos').className = `photos ${previous ? '' : 'single'} ${$('boxes').checked ? '' : 'boxes-hidden'}`;
  $('photos').innerHTML = (previous ? photo(previous,'Before') : '') + photo(scan,previous ? 'After' : 'Baseline');
  $('detections').innerHTML = scan.detected_objects.map(o => `<div class="evidence-row"><b>${escape(o.label)}</b> · ${pct(o.confidence)}<small>${escape(o.stable_id)} · ${escape(o.verification_status)}</small></div>`).join('') || '<div class="empty">No detections recorded</div>';
  const labels = Object.fromEntries([...(previous?.detected_objects || []),...scan.detected_objects].map(o => [o.stable_id,o.label]));
  $('matches').innerHTML = scan.observations.map(o => {const l = o.evidence.local; return `<div class="evidence-row">${tag(o.status)} · <b>${escape(labels[o.stable_id] || o.stable_id)}</b> · ${o.observed ? 'Detected' : 'Not detected'}<small>${escape(o.stable_id)}</small><small>${l?.evidence ? `DINO similarity: ${pct(l.evidence.visual_similarity)} · ${escape(l.reason || '')}` : escape(l?.reason || o.evidence.limitation || 'Provisional identity')}</small></div>`;}).join('') || '<div class="empty">No observations recorded</div>';
  $('delta').innerHTML = previous ? eventsHtml(scan.result?.events || []) : '<div class="empty">Baseline · No previous scan to compare</div>';
  $('detail-object-results').innerHTML=objectResultsHtml(scan.object_results || []);
  $('removal-summary').innerHTML=removalSummaryHtml(scan.object_results || [],true);
  const removalDetails=$('removal-summary').querySelector('details');
  if (removalDetails) removalDetails.open=expandedRemovalScans.has(id);
  $('diagnostics').textContent = JSON.stringify({registration:scan.result?.registration || 'Not run for baseline',local_counts:scan.result?.local_counts || 'Not run for baseline',raw_detector_output:scan.detected_objects,cloud_status:scan.result?.cloud_status,cloud_evidence:scan.cloud_evidence,registry:scan.registry,registry_scope:scan.registry_scope,warning:scan.result?.warning},null,2);
  document.querySelectorAll('[data-scan]').forEach(b => {
    b.classList.toggle('active',b.dataset.scan === id);
    b.setAttribute('aria-pressed',String(b.dataset.scan===id));
    b.querySelector('.timeline-time').textContent=clock(b.dataset.timestamp)+(b.dataset.scan===id ? ' · Selected' : '');
  });
}
$('account').addEventListener('change', () => sites().catch(failure));
$('site').addEventListener('change', () => { selectedSite = $('site').value; selectedScan = null; lastNewestScan=null; document.querySelector('.workspace').scrollTop=0; refresh().catch(failure); });
$('refresh').addEventListener('click', () => refresh().catch(failure));
$('history').addEventListener('click', event => { const button = event.target.closest('[data-scan]'); if (button) { selectedScan = button.dataset.scan; inspect(selectedScan).then(()=>$('inspection').scrollIntoView({block:'start',behavior:'smooth'})).catch(failure); } });
$('history').addEventListener('toggle',event=>{
  const id=event.target.dataset?.session;
  if (id) { if (event.target.open) expandedSessions.add(id); else expandedSessions.delete(id); }
},true);
$('removal-summary').addEventListener('toggle',event=>{
  if (!selectedScan || event.target.tagName!=='DETAILS') return;
  if (event.target.open) expandedRemovalScans.add(selectedScan); else expandedRemovalScans.delete(selectedScan);
},true);
$('boxes').addEventListener('change', () => $('photos').classList.toggle('boxes-hidden',!$('boxes').checked));
function setView(raw) { rawView=raw; $('raw-view').setAttribute('aria-pressed',String(raw)); $('product-view').setAttribute('aria-pressed',String(!raw)); inspect(selectedScan).catch(failure); }
$('raw-view').addEventListener('click',()=>setView(true));
$('product-view').addEventListener('click',()=>setView(false));
document.addEventListener('click',async event=>{
  const rename=event.target.closest('[data-rename]');
  if (rename) { renameId=rename.dataset.rename; $('rename-name').value=rename.dataset.label; $('rename-error').textContent=''; $('rename-dialog').showModal(); $('rename-name').focus(); return; }
  const ignore=event.target.closest('[data-ignore]');
  if (ignore) { ignore.disabled=true; try { await post(`/sites/${encodeURIComponent(selectedSite)}/objects/${encodeURIComponent(ignore.dataset.ignore)}/identity`,{ignored:ignore.dataset.ignored!=='true'}); await refresh(); } catch(error) { $('enrollment-message').textContent=error.message; ignore.disabled=false; } }
});
$('rename-cancel').addEventListener('click',()=>$('rename-dialog').close());
$('rename-form').addEventListener('submit',async event=>{
  event.preventDefault(); $('rename-save').disabled=true;
  const name=$('rename-name').value.trim();
  try { await post(`/sites/${encodeURIComponent(selectedSite)}/objects/${encodeURIComponent(renameId)}/identity`,{user_confirmed_name:name}); $('rename-dialog').close(); $('memory-notice').textContent=`Site memory updated. This object will be remembered as: ${name}`; $('memory-notice').hidden=false; setTimeout(()=>$('memory-notice').hidden=true,8000); await refresh(); }
  catch(error) { $('rename-error').textContent=error.message; }
  finally { $('rename-save').disabled=false; }
});
$('confirm-baseline').addEventListener('click',async()=>{
  const objects=[...document.querySelectorAll('[data-enroll]:checked:not(:disabled)')].map(input=>({object_id:input.dataset.enroll,display_name:document.querySelector(`[data-name="${input.dataset.enroll}"]`).value}));
  if (!objects.length) { $('enrollment-message').textContent='Select at least one baseline object.'; return; }
  $('confirm-baseline').disabled=true;
  try { await post(`/sites/${encodeURIComponent(selectedSite)}/confirm-baseline`,{baseline_scan_id:enrollmentRegistry.baseline_scan_id,objects}); $('enrollment-message').textContent='Selected objects confirmed.'; await refresh(); }
  catch(error) { $('enrollment-message').textContent=error.message==='Failed to fetch' ? 'Cannot reach FieldDelta server.' : error.message; }
  finally { $('confirm-baseline').disabled=false; }
});
$('verify-removal').addEventListener('click',async()=>{
  $('verify-removal').disabled=true;
  try { await post(`/scans/${encodeURIComponent(selectedScan)}/verify-removal`,{}); await inspect(selectedScan); }
  catch { failure(); }
  finally { $('verify-removal').disabled=false; }
});
accounts().catch(failure);
setInterval(() => { if (!refreshBusy && !document.hidden) refresh().catch(failure); },5000);
