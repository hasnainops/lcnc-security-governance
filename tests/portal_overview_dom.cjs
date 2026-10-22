/* DOM integration checks. Install jsdom in a temporary test environment; see runbook. */
const {JSDOM}=require('jsdom');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {catalog}=require('../governance-portal/platform-overview.js');
const root=path.join(__dirname,'../governance-portal');
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const until=async predicate=>{
  for(let i=0;i<200;i++){if(predicate())return;await sleep(10);}
  throw Error('Timed out waiting for DOM condition');
};
(async()=>{
  const dom=new JSDOM(fs.readFileSync(path.join(root,'index.html'),'utf8'),{
    url:'http://localhost:3000',runScripts:'outside-only',pretendToBeVisual:true
  });
  const w=dom.window, doc=w.document, get=id=>doc.getElementById(id);
  let mode='current',inventoryFails=false,delayA=false,posts=0,mutationResolve;
  let functionalMode='passed';
  const functionalServices=[
    'governance-api-a','governance-api-b','governance-api','governance-portal','opa'
  ];
  const functionalCells=()=>[...get('platformRows').children]
    .filter(row=>functionalServices.includes(row.querySelector('strong').textContent))
    .map(row=>row.children[5]);
  const functionalShows=status=>functionalCells().length===5 &&
    functionalCells().every(cell=>cell.querySelector('strong')?.textContent===status);
  const errors=[];w.addEventListener('error',e=>errors.push(e.message));
  const apps=['a','b'].map(id=>({id,name:`Application ${id.toUpperCase()}`,platform:'Appsmith',risk_score:null}));
  w.fetch=async(url,options={})=>{
    let data;
    if(url==='/api/exam/platform-status') {
      if(mode==='network')throw Error('Connection failed');
      if(mode==='http')return {ok:false,status:502};
      data={schema_version:1,source:'docker_compose',observation_status:mode,
        reason:mode==='unavailable'?'snapshot_missing':null,
        observed_at:new Date().toISOString(),age_seconds:mode==='stale'?40:0,stale_after_seconds:30,
        services:catalog.map(([service],i)=>({service,container_count:1,container_state:'running',docker_health:i<14?'healthy':'not_configured',observation_status:mode}))};
    } else if(url==='/api/exam/functional-status') {
      if(functionalMode==='network')throw Error('Functional connection failed');
      if(functionalMode==='http')return {ok:false,status:502};
      const stamp=new Date().toISOString();
      data={schema_version:1,source:'internal_http_probes',
        served_at:stamp,stale_after_seconds:30,
        checks:functionalServices.map(service=>({
          service,check:service==='opa'?'policy_decisions':'inventory_read',
          status:functionalMode,
          ...(service==='opa'?{
            cases_passed:functionalMode==='passed'?6:0,cases_total:6
          }:{}),
          observed_at:stamp,duration_ms:5,
          http_status:functionalMode==='passed'?200:500,
          application_count:service!=='opa'&&functionalMode==='passed'?14:null,
          reason:functionalMode==='passed'?null:'http_error'
        }))};
    } else if(url==='/api/applications') {
      if(inventoryFails)return {ok:false,status:503}; data=apps;
    } else if(url.endsWith('/history')) {
      const id=url.split('/')[3]; if(id==='a'&&delayA)await sleep(120);
      data={application:apps.find(a=>a.id===id),risk_assessments:[],policy_decisions:[],governance_decisions:[]};
    } else if(url.endsWith('/compliance-evidence'))data={controls:[]};
    else if(url.endsWith('/compliance/dynamic'))data={controls:[],summary:{},overall_status:'not_assessed'};
    else if(url.endsWith('/citizen-guidance'))data=null;
    else if(url.endsWith('/governance-evaluate')) {
      assert.equal(options.method,'POST');assert.match(url,/\/a\/governance-evaluate$/);
      posts++;await new Promise(resolve=>mutationResolve=resolve);
      data={application_name:'Application A',governance:{outcome:'REVIEW'}};
    } else throw Error('Unexpected endpoint '+url);
    return {ok:true,json:async()=>data};
  };
  try {
    w.eval(fs.readFileSync(path.join(root,'functional-overview.js'),'utf8'));
    w.eval(fs.readFileSync(path.join(root,'platform-overview.js'),'utf8'));
    w.eval(fs.readFileSync(path.join(root,'app.js'),'utf8'));
    await until(()=>get('platformSummary').textContent.includes('14'));
    assert.equal(get('platformRows').children.length,20);
    assert.equal([...get('platformRows').children]
      .filter(row=>row.children[3].textContent==='Not configured').length,6);
    assert.equal([...get('platformRows').children]
      .filter(row=>row.children[5].textContent==='Not configured').length,15);
    await until(()=>functionalShows('Passed'));
    const opaCell=()=>[...get('platformRows').children]
      .find(row=>row.querySelector('strong').textContent==='opa').children[5];
    assert.match(opaCell().textContent,/Policy decisions/);
    assert.match(opaCell().textContent,/6\/6 cases matched/);
    assert.ok(!opaCell().textContent.includes('applications'));
    console.log('PASS: 20 service rows; health distinctions; initial inventory');
    for(const state of ['stale','unavailable','http','network','current']) {
      mode=state;get('platformRefresh').click();
      await until(()=>!get('platformRefresh').disabled);
      assert.equal(get('platformObservation').className,['http','network'].includes(state)?'unavailable':state);
      const counts=[...get('platformSummary').querySelectorAll('span')].map(el=>el.textContent);
      assert.deepEqual(counts,state==='current'?['20','14','6','0']:['—','—','—','—']);
    }
    console.log('PASS: stale, missing snapshot, HTTP/network failure and recovery');
    for(const state of ['failed','http','network','passed']) {
      functionalMode=state;
      get('platformRefresh').click();
      const expected=state==='passed'?'Passed':state==='failed'?'Failed':'Unavailable';
      await until(()=>functionalShows(expected) && !get('platformRefresh').disabled);
      assert.equal(get('platformObservation').className,'current');
      for(const cell of functionalCells()) {
        assert.equal(cell.parentElement.children[3].textContent,'healthy');
        if(state!=='passed') {
          assert.ok(!cell.textContent.includes('14 applications'));
          assert.ok(!cell.textContent.includes('6/6 cases matched'));
        }
      }
    }
    console.log('PASS: functional failure, unavailable report and recovery remain independent of Docker health');

    const originalNow=w.Date.now;
    w.Date.now=()=>originalNow()+31000;
    await until(()=>get('platformObservation').className==='stale');
    await until(()=>functionalShows('Stale'));
    assert.ok(!opaCell().textContent.includes('6/6 cases matched'));
    assert.ok(functionalCells().every(cell=>!cell.textContent.includes('14 applications')));
    assert.equal(get('platformSummary').querySelector('span').textContent,'—');
    w.Date.now=originalNow;
    get('platformRefresh').click();await until(()=>!get('platformRefresh').disabled);
    console.log('PASS: displayed status ages locally without a new API response');
    // An older response must not render under a newer selection.
    delayA=true;
    const first=w.loadHistory('a');const second=w.loadHistory('b');
    await Promise.all([first,second]);
    assert.equal(get('detailName').textContent,'Application B');
    assert.match(get('detailPlatform').textContent,/UUID: b/);
    console.log('PASS: delayed A response cannot overwrite B');
    delayA=false;await w.loadHistory('a');
    const pending=w.runGovernanceEvaluation();
    await until(()=>posts===1);
    await w.runGovernanceEvaluation(); // Duplicate submission must be suppressed.
    await w.loadHistory('b');
    mutationResolve();await pending;
    assert.equal(posts,1);assert.equal(get('applicationSelector').value,'b');
    assert.equal(get('detailName').textContent,'Application B');
    console.log('PASS: mutation bound to A; duplicate prevented; selection B retained');
    // Text from application records must remain text in selector and detail view.
    apps[1].name='<img src=x onerror="alert(1)">';
    await w.loadApplications();await w.loadHistory('b');
    assert.equal(get('detailName').textContent,apps[1].name);
    assert.equal(doc.querySelectorAll('img').length,0);
    inventoryFails=true;await w.loadApplications();
    assert.equal(get('applicationCount').textContent,'—');
    assert.equal(get('detailPanel').classList.contains('hidden'),true);
    assert.match(get('inventoryStatus').textContent,/unavailable/);
    assert.deepEqual(errors,[]);
    console.log('PASS: text escaping; inventory failure clears counts and evidence');
  } finally {w.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
