import type { NextConfig } from 'next';
const config: NextConfig = {poweredByHeader:false,reactStrictMode:true,async headers(){return [{source:'/:path*',headers:[{key:'X-Content-Type-Options',value:'nosniff'},{key:'Referrer-Policy',value:'strict-origin-when-cross-origin'}]}];}};
export default config;
