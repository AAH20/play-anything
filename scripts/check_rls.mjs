// Optional development-only PostgreSQL WASM check. No project runtime dependency.
import {readFileSync,readdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
if(!process.argv[2])throw Error('Pass the absolute path to a temporary PGlite dist/index.js installation.');
const {PGlite}=await import(pathToFileURL(resolve(process.argv[2])));
const root=fileURLToPath(new URL('../',import.meta.url)),db=new PGlite();
try {
 await db.exec(readFileSync(root+'tests/fixtures/creator_rls_bootstrap.sql','utf8'));
 for(const name of readdirSync(root+'supabase/migrations').filter(n=>n.endsWith('.sql')).sort())await db.exec(readFileSync(root+'supabase/migrations/'+name,'utf8'));
 await db.exec(readFileSync(root+'tests/creator_rls.sql','utf8'));
 console.log('PASS: owner CRUD, cross-user isolation, spoofing and anonymous denial.');
} finally {await db.close();}
