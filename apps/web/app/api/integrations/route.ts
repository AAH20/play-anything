import {NextResponse} from 'next/server';
import {hasIntegrationSafeOrigin,isIntegrationAuthorized,INTEGRATION_LIMITS} from '@/lib/integration-runtime';
import {integrationRuntime} from '@/lib/integration-runtime-instance';

export const runtime='nodejs';
export const dynamic='force-dynamic';

const noStore={'Cache-Control':'no-store, max-age=0'};
function authorized(request:Request){return isIntegrationAuthorized(request)&&hasIntegrationSafeOrigin(request);}
async function readJson(request:Request){const declared=Number(request.headers.get('content-length')||0);if(declared>INTEGRATION_LIMITS.requestBytes)throw new Error('Integration request exceeds the 2 MB limit.');if(!request.body)throw new Error('Request body is required.');const reader=request.body.getReader(),chunks:Uint8Array[]=[];let total=0;while(true){const {done,value}=await reader.read();if(done)break;total+=value.byteLength;if(total>INTEGRATION_LIMITS.requestBytes){await reader.cancel();throw new Error('Integration request exceeds the 2 MB limit.');}chunks.push(value);}const bytes=new Uint8Array(total);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}try{return JSON.parse(new TextDecoder().decode(bytes));}catch{throw new Error('Request body must be valid JSON.');}}

export async function GET(_request:Request){return NextResponse.json({integrations:integrationRuntime.catalog(),limits:{requestBytes:INTEGRATION_LIMITS.requestBytes,concurrency:INTEGRATION_LIMITS.concurrency,queue:INTEGRATION_LIMITS.queued,timeoutMs:INTEGRATION_LIMITS.timeoutMs,kernelNodes:INTEGRATION_LIMITS.kernelNodes,kernelEdges:INTEGRATION_LIMITS.kernelEdges,modelNodes:INTEGRATION_LIMITS.modelInputNodes,modelEdges:INTEGRATION_LIMITS.modelInputEdges}},{headers:noStore});}

export async function POST(request:Request){if(!authorized(request))return NextResponse.json({error:'Unauthorized integration request.'},{status:401,headers:noStore});if(!request.headers.get('content-type')?.toLowerCase().startsWith('application/json'))return NextResponse.json({error:'Content-Type must be application/json.'},{status:415,headers:noStore});try{return NextResponse.json({job:integrationRuntime.start(await readJson(request))},{status:202,headers:noStore});}catch(error){const message=error instanceof Error?error.message:'Invalid integration request.';return NextResponse.json({error:message},{status:/unknown integration|not configured|not allowlisted|is not supported|is required|must |exceeds|limited|invalid|expected|snapshot|not an allowed|not supported|must contain|must be/i.test(message)?400:503,headers:noStore});}}
