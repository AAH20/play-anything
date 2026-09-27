import GraphWorkspace from '@/components/GraphWorkspace';
export default async function Page({searchParams}:{searchParams:Promise<{embed?:string}>}){const {embed}=await searchParams;return <GraphWorkspace embedded={embed==='1'}/>;}
