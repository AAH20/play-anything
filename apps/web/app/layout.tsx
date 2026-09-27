import type {Metadata} from 'next';
import './globals.css';
export const metadata:Metadata={title:'Graph Studio · Play Anything',description:'Explore repository relationships, coordinate evidence-based analysis and build your next project.'};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>;}
