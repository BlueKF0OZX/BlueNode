'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
const source = html.slice(html.indexOf('    // Browser-local preferences'),html.indexOf('    let statusLoading'));
let shared = {ok:true,local_node:'12345',revision:0,favorites:[]};
let failure = 0;
const writes = [], commands = [];
function device() {
  const elements = {}, storage = new Map();
  const element = id => elements[id] ||= {textContent:'',innerHTML:'',value:'',dataset:{},hidden:false};
  const context = vm.createContext({Date,AbortController,setTimeout,clearTimeout,document:{getElementById:element},
    localStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value)},
    runNodeControl:(...args)=>commands.push(args), adminHeaders:x=>x, showControlLogin:()=>{},
    fetch:async (url, options={})=>{
      let status = failure || 200, data = structuredClone(shared);
      if (options.method === 'POST') {
        const change = JSON.parse(options.body); writes.push(change);
        if (!failure && change.revision !== shared.revision) status = 409;
        if (status === 200) {
          if (change.operation === 'save') {
            const existing = shared.favorites.find(item=>item.node === change.item.node);
            if (existing) existing.label = change.item.label;
            else shared.favorites.push(change.item);
          } else if (change.operation === 'remove') shared.favorites = shared.favorites.filter(item=>item.node !== change.node);
          else for (const item of change.items) if (!shared.favorites.some(old=>old.node===item.node)) shared.favorites.push(item);
          shared.revision++; data = structuredClone(shared);
        }
      }
      return {ok:status===200,status,json:async()=>status===200?data:{error:'Request rejected; refresh and retry.'}};
    },
    escapeHtml:value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))});
  vm.runInContext(source,context);
  return {context,element,storage};
}
(async()=>{
  const pc=device(), phone=device();
  pc.storage.set('bluenode:nodes:v1:12345',JSON.stringify({favorites:[{node:'23456',label:'Old browser favorite'}],recent:[]}));
  await pc.context.configureSavedNodes('12345',{});
  await phone.context.configureSavedNodes('12345',{});
  assert.equal(shared.favorites.length,0,'loading never silently imports legacy preferences');
  assert.equal(pc.element('import-browser-favorites').hidden,false);
  await pc.context.importBrowserFavorites();
  await phone.context.loadSharedFavorites();
  assert.match(phone.element('saved-node-favorites').innerHTML,/Old browser favorite/);
  phone.context.prompt=()=>'<img src=x onerror=alert(1)>';
  await phone.context.editFavoriteNode('23456');
  await pc.context.loadSharedFavorites();
  assert.match(pc.element('saved-node-favorites').innerHTML,/&lt;img/);
  assert.doesNotMatch(pc.element('saved-node-favorites').innerHTML,/<img/);
  pc.context.prompt=()=>null;
  const before=shared.revision;
  await pc.context.editFavoriteNode('23456');
  assert.equal(shared.revision,before,'cancel does not save');
  pc.context.prompt=()=>'x'.repeat(80);
  await pc.context.editFavoriteNode('23456');
  assert.equal(shared.favorites[0].label.length,48);
  await phone.context.removeFavoriteNode('23456');
  assert.equal(shared.favorites.length,1,'stale device cannot clobber a newer edit');
  assert.match(phone.element('saved-nodes-message').textContent,/rejected/);
  await phone.context.removeFavoriteNode('23456');
  await pc.context.loadSharedFavorites();
  assert.equal(shared.favorites.length,0);
  assert.doesNotMatch(pc.element('saved-node-favorites').innerHTML,/Edit name/);
  pc.element('manual-node-number').value='34567';pc.element('favorite-node-label').value='Shared';
  pc.context.localStorage.setItem=()=>{throw Error('blocked');};
  await pc.context.saveFavoriteNode();
  assert.equal(shared.favorites[0].node,'34567','shared storage works with browser storage blocked');
  assert.match(pc.element('saved-nodes-message').textContent,/saved on this node/);
  failure=503;
  await phone.context.loadSharedFavorites();
  const writeCount=writes.length;
  phone.element('manual-node-number').value='45678';await phone.context.saveFavoriteNode();
  assert.equal(writes.length,writeCount,'outage cannot create an unsynced local favorite');
  failure=0;await phone.context.loadSharedFavorites();
  assert.equal(commands.length,0,'favorite edits never send radio commands');
  phone.context.connectSavedNode('34567',{});
  assert.equal(commands[0][0],'node-connect');assert.equal(commands[0][2],'34567');
  for(const value of ['12345','evil','99999']) phone.context.connectSavedNode(value,{});
  assert.equal(commands.length,1);
  phone.context.rememberNodeControl('node-connect',{ok:false,outcome:'unverified',node:'34567'});
  phone.context.rememberNodeControl('node-connect',{ok:true,outcome:'verified',node:'34567'},'54321');
  assert.equal(JSON.parse(phone.storage.get('bluenode:nodes:v1:12345')).recent.length,0);
  phone.context.rememberNodeControl('node-connect',{ok:true,outcome:'verified',node:'34567'});
  assert.equal(JSON.parse(phone.storage.get('bluenode:nodes:v1:12345')).recent[0].node,'34567');
  const clean=phone.context.cleanSavedNodes({favorites:[null,{node:'12345'}, {node:'23456',label:'x'.repeat(80)},{node:'23456'}, {node:'<script>'}],
    recent:Array.from({length:20},(_,i)=>({node:String(60000+i),used_at:i}))},'12345',100);
  assert.equal(clean.favorites.length,1);assert.equal(clean.favorites[0].label.length,48);
  assert.equal(clean.recent.length,8);assert.equal(clean.recent[0].used_at,19);
  let release;
  phone.context.fetch=()=>new Promise(resolve=>{release=()=>resolve({ok:true,status:200,json:async()=>structuredClone(shared)});});
  const delayed=phone.context.loadSharedFavorites();
  phone.context.fetch=async()=>({ok:true,status:200,json:async()=>({ok:true,local_node:'54321',revision:0,favorites:[]})});
  await phone.context.configureSavedNodes('54321',{});
  release();await delayed;
  assert.doesNotMatch(phone.element('saved-node-favorites').innerHTML,/Shared/,'late response must stay in its own node scope');
  console.log('PASS shared favorites: two devices, migration, conflicts, escaping, outage, storage denial, recents and scope');
})().catch(error=>{console.error(error);process.exitCode=1;});
