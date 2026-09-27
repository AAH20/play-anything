import {NextResponse} from 'next/server';
import {integrationRuntime} from '@/lib/integration-runtime-instance';
import {hasIntegrationSafeOrigin,isIntegrationAuthorized} from '@/lib/integration-runtime';

export const runtime='nodejs';
export const dynamic='force-dynamic';
type RouteContext={params:Promise<{id:string}>};
const noStore={'Cache-Control':'no-store, max-age=0'};
function authorized(request:Request){return isIntegrationAuthorized(request)&&hasIntegrationSafeOrigin(request);}

export async function GET(request:Request,context:RouteContext){if(!authorized(request))return NextResponse.json({error:'Unauthorized integration request.'},{status:401,headers:noStore});const {id}=await context.params;const job=integrationRuntime.get(id);return job?NextResponse.json({job},{headers:noStore}):NextResponse.json({error:'Integration job not found.'},{status:404,headers:noStore});}

export async function DELETE(request:Request,context:RouteContext){if(!authorized(request))return NextResponse.json({error:'Unauthorized integration request.'},{status:401,headers:noStore});const {id}=await context.params;const job=await integrationRuntime.cancel(id);return job?NextResponse.json({job},{headers:noStore}):NextResponse.json({error:'Integration job not found.'},{status:404,headers:noStore});}
