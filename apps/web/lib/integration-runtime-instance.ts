import {IntegrationRuntime} from './integration-runtime';

const globalRuntime=globalThis as typeof globalThis&{__playAnythingIntegrationRuntime?:IntegrationRuntime;__playAnythingIntegrationRuntimeVersion?:number};
const runtimeVersion=2;
if(globalRuntime.__playAnythingIntegrationRuntimeVersion!==runtimeVersion){globalRuntime.__playAnythingIntegrationRuntime=new IntegrationRuntime();globalRuntime.__playAnythingIntegrationRuntimeVersion=runtimeVersion;}
export const integrationRuntime=globalRuntime.__playAnythingIntegrationRuntime!;
