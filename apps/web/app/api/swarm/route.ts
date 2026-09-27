import {NextResponse} from 'next/server';
import {hasSafeOrigin,isAuthorized,isReviewEnabled,parseReviewInput,REVIEW_MAX_BYTES} from '../../../lib/model-review';
import {MODEL_SWARM_CALL_OUTPUT_TOKENS,runModelSwarm} from '../../../lib/model-swarm';

export const runtime='nodejs';
export const maxDuration=50;
function json(body:unknown,status=200){return NextResponse.json(body,{status,headers:{'Cache-Control':'no-store'}});}
export async function POST(request:Request){
 if(!hasSafeOrigin(request))return json({error:'Request origin is not allowed.'},403);
 if(!isAuthorized(request))return json({error:'Model review access token is missing or invalid.'},401);
 if(!(request.headers.get('content-type')||'').toLowerCase().startsWith('application/json'))return json({error:'Send a JSON request body.'},415);
 if(Number(request.headers.get('content-length')||0)>REVIEW_MAX_BYTES)return json({error:`Request body exceeds ${REVIEW_MAX_BYTES} bytes.`},413);
 let input;
 try{const reader=request.body?.getReader();if(!reader)return json({error:'Request body is empty.'},400);const chunks:Uint8Array[]=[];let total=0;while(true){const {done,value}=await reader.read();if(done)break;total+=value.byteLength;if(total>REVIEW_MAX_BYTES){await reader.cancel();return json({error:`Request body exceeds ${REVIEW_MAX_BYTES} bytes.`},413);}chunks.push(value);}const bytes=new Uint8Array(total);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength;}const body=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));input=parseReviewInput({graph:body.graph,goal:body.goal,maxOutputTokens:MODEL_SWARM_CALL_OUTPUT_TOKENS});}
 catch(error){return json({error:error instanceof SyntaxError?'Request body is not valid JSON.':error instanceof Error?error.message:'Invalid model swarm request.'},400);}
 if(!isReviewEnabled())return json({error:'Model review is disabled. Configure the server model, gateway key, and access token.'},503);
 try{return json(await runModelSwarm(input.graph,input.goal,request.signal));}
 catch(error){if(request.signal.aborted)return json({error:'Model agent team canceled.'},499);return json({error:error instanceof Error&&/45-second deadline/.test(error.message)?'Model agent team timed out after 45 seconds.':'Model agent team failed. Check server configuration and provider status.'},/45-second deadline/.test(error instanceof Error?error.message:'')?504:502);}
}
