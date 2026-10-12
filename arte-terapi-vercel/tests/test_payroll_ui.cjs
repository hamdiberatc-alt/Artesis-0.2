const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const nodes=new Map();
class Element{
 constructor(id){this.id=id;this.value='';this.open=false;this.listeners={};this.style={};this.classList={contains:()=>false,add(){},remove(){}};this.dataset={}}
 set innerHTML(value){this.html=value;for(const m of value.matchAll(/id="([^"]+)"/g))if(!nodes.has(m[1]))nodes.set(m[1],new Element(m[1]));}
 get innerHTML(){return this.html||''}
 addEventListener(type,handler){this.listeners[type]=handler}
 querySelector(){return {focus(){},textContent:''}}
 showModal(){this.open=true}
 close(){this.open=false}
 focus(){this.focused=true}
 scrollIntoView(){}
}
const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
for(const m of html.matchAll(/id="([^"]+)"/g))nodes.set(m[1],new Element(m[1]));
const context=vm.createContext({console,Date,URLSearchParams,setTimeout,clearTimeout,
 document:{getElementById:id=>nodes.get(id),addEventListener(){},querySelector:()=>[...nodes.values()].find(n=>n.open)||null},
 fetch(){throw Error('Unexpected request')}});
let source=html.match(/<script>([\s\S]*?)<\/script>/)[1];
vm.runInContext(source.slice(0,source.lastIndexOf("(async()=>{try{const s=await api('/api/session');")),context);
const run=code=>vm.runInContext(code,context);
function event(key,options={}){return {key,target:{classList:{contains:()=>false},matches:()=>false},preventDefault(){this.prevented=true},...options}}
(async()=>{
 run("state.csrf='test';navigate=async page=>{state.page=page};openProgram=async()=>{state.newProgram=true}");
 await context.handleShortcuts(event('7',{altKey:true}));assert.equal(run('state.page'),'maas');
 await context.handleShortcuts(event('n',{altKey:true}));assert.equal(run('state.newProgram'),true);
 await context.handleShortcuts(event('1',{altKey:true,target:{classList:{contains:()=>false},matches:()=>true}}));assert.equal(run('state.page'),'maas');
 context.showShortcuts();assert(nodes.get('shortcuts').open);assert(nodes.get('shortcut-list').innerHTML.includes('Alt+7'));
 await context.handleShortcuts(event('2',{altKey:true}));assert.equal(run('state.page'),'maas');
 await context.handleShortcuts(event('Escape'));assert(!nodes.get('shortcuts').open);
 run("state.csrf=''");await context.handleShortcuts(event('1',{altKey:true}));assert.equal(run('state.page'),'maas');
 run("state.csrf='test';state.boot={terapistler:[]};state.page='maas'");
 context.fixture={ay:'2026-10',terapistler:[{terapist_id:1,ad:'<img src=x onerror=alert(1)>',aktif:1,
 ayarlanmis:false,grup_sayimi:'ders',ucretler:{bireysel:null,grup2:null,grup3:null},adetler:{bireysel:1,grup2:0,grup3:0},seans:1,tutar:null}],
 seanslar:[],haric:{gelmedi:0,gelecek:0,gecersiz:0},uyarilar:[],eksik_ucretli_seans:1,hesaplanan_toplam:0,tamamlandi:false};
 run('api=async()=>fixture');await context.renderPayroll();
 const result=nodes.get('main').innerHTML;assert(result.includes('Ücret belirleyin'));assert(result.includes('&lt;img'));assert(!result.includes('<img'));
 assert(result.includes('/api/payroll.csv?'));assert(result.includes('Eksik / kontrol gerekli'));
 context.editPayrollRate('1');const editor=nodes.get('payroll-rate-editor').innerHTML;
 assert(editor.includes('name="bireysel"'));assert(editor.includes('name="grup_sayimi"'));assert(editor.includes('value=""'));
 let resolve;context.pending=new Promise(r=>resolve=r);run("api=async()=>pending;state.page='maas'");
 const rendering=context.renderPayroll();run("state.page='danisanlar'");nodes.get('main').innerHTML='New page';
 resolve(context.fixture);await rendering;assert.equal(nodes.get('main').innerHTML,'New page');
 context.pending=new Promise(r=>resolve=r);run("api=async()=>pending");
 const calendar=context.renderProgramCalendar();run('navigationVersion++');
 resolve({week_start:'2026-10-12'});await calendar;
 assert.equal(nodes.get('main').innerHTML,'New page');
 console.log('PASS: payroll screen, missing rates, escaping, stale navigation and keyboard shortcuts.');
})().catch(error=>{console.error(error);process.exitCode=1});
