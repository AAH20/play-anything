import test from 'node:test';
import assert from 'node:assert/strict';
import {getHermesIntegrations,executeHermes} from '../lib/hermes-adapter';

test('Hermes capability requires its own credentials and does not expose them',()=>{
 assert.equal(getHermesIntegrations({})[0].configured,false);
 const rows=getHermesIntegrations({HERMES_BASE_URL:'http://localhost:8642',HERMES_API_KEY:'private-test-key',HERMES_MODEL:'hermes'});
 assert.equal(rows[0].configured,true);assert.ok(!JSON.stringify(rows).includes('private-test-key'));
});
test('Hermes uses the verified endpoint, bounds context and preserves token usage',async()=>{
 const prior=globalThis.fetch;let sent:any;
 globalThis.fetch=async(url,init)=>{assert.equal(String(url),'http://localhost:8642/v1/chat/completions');sent=JSON.parse(String(init?.body));assert.equal(init?.redirect,'error');return Response.json({choices:[{message:{content:'Review private-test-key'}}],usage:{prompt_tokens:100,completion_tokens:20}});};
 try{const result=await executeHermes('hermes','review',{goal:'Review evidence',parameters:{}},{HERMES_BASE_URL:'http://localhost:8642',HERMES_API_KEY:'private-test-key',HERMES_MODEL:'hermes'},new AbortController().signal);assert.equal(sent.stream,false);assert.equal(sent.max_tokens,1200);assert.equal(result.result.output,'Review [redacted]');assert.deepEqual(result.usage,{inputTokens:100,outputTokens:20});}
 finally{globalThis.fetch=prior;}
});
test('Hermes rejects remote plaintext endpoints and unsupported operations',async()=>{
 const input={goal:'Review',parameters:{}};const env={HERMES_BASE_URL:'http://remote.example',HERMES_API_KEY:'secret',HERMES_MODEL:'hermes'};
 await assert.rejects(()=>executeHermes('hermes','review',input,env,new AbortController().signal),/HTTPS/);
 await assert.rejects(()=>executeHermes('hermes','other',input,env,new AbortController().signal),/Unsupported/);
});
