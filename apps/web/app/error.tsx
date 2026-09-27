'use client';
export default function ErrorView({reset}:{reset:()=>void}){return <main className="error-page"><h1>The workspace could not load.</h1><p>Try again. Your exported snapshots and original Python application remain available.</p><button onClick={reset}>Retry workspace</button><a href="/legacy/creator.html">Open Creator Studio</a></main>;}
