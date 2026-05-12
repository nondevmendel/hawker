import { getServerSession } from 'next-auth'
import { authOptions } from './api/auth/[...nextauth]'

export default function Install({ apiKey, apiUrl }) {
  const hawkerEnv = `HAWKER_API_URL=${apiUrl}\nHAWKER_API_KEY=${apiKey}`

  return (
    <div style={{
      background:'#0f0f0f', color:'#e0e0e0', minHeight:'100vh',
      fontFamily:'-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
      padding:'40px 28px', maxWidth:'700px', margin:'0 auto',
    }}>
      <a href="/app.html" style={{ color:'#4a9eff', fontSize:'12px', textDecoration:'none' }}>← Back to dashboard</a>
      <h1 style={{ marginTop:'20px', marginBottom:'6px', fontSize:'22px' }}>
        <span style={{ color:'#4a9eff' }}>Hawk</span>er — Install the Menu Bar App
      </h1>
      <p style={{ color:'#666', fontSize:'13px', marginBottom:'32px' }}>
        The menu bar app runs on your Mac and captures social media screenshots automatically.
      </p>

      <Step n="1" title="Requirements">
        <p>macOS 12+, Python 3.9+, and the following Python packages:</p>
        <Code>{`pip3 install rumps pillow pyobjc-framework-Cocoa pyobjc-framework-Quartz`}</Code>
      </Step>

      <Step n="2" title="Download the files">
        <p>Download both files into a folder (e.g. <code style={codeStyle}>~/.hawker/</code>):</p>
        <div style={{ display:'flex', gap:'10px', marginTop:'10px' }}>
          <DlBtn href="/api/download/menubar.py" label="menubar.py" />
          <DlBtn href="/api/download/daemon.py"  label="daemon.py"  />
        </div>
      </Step>

      <Step n="3" title="Configure your API key">
        <p>Create a file called <code style={codeStyle}>hawker.env</code> in the same folder with this content:</p>
        <Code selectable>{hawkerEnv}</Code>
      </Step>

      <Step n="4" title="Grant Screen Recording permission">
        <p>Open <strong>System Settings → Privacy &amp; Security → Screen Recording</strong> and enable the Python executable you&apos;ll use to run the app.</p>
      </Step>

      <Step n="5" title="Run it">
        <Code>{`python3 ~/.hawker/menubar.py`}</Code>
        <p style={{ marginTop:'8px' }}>A <code style={codeStyle}>(o,o)</code> icon appears in your menu bar. Click it and choose <strong>Launch at Login</strong> to auto-start.</p>
      </Step>
    </div>
  )
}

function Step({ n, title, children }) {
  return (
    <div style={{ marginBottom:'28px' }}>
      <div style={{ display:'flex', alignItems:'center', gap:'10px', marginBottom:'10px' }}>
        <span style={{
          background:'#4a9eff', color:'#000', borderRadius:'50%',
          width:'22px', height:'22px', display:'flex', alignItems:'center',
          justifyContent:'center', fontSize:'11px', fontWeight:'700', flexShrink:0,
        }}>{n}</span>
        <h3 style={{ fontSize:'15px', fontWeight:'600' }}>{title}</h3>
      </div>
      <div style={{ paddingLeft:'32px', fontSize:'13px', color:'#ccc', lineHeight:'1.6' }}>
        {children}
      </div>
    </div>
  )
}

function Code({ children, selectable }) {
  return (
    <pre style={{
      background:'#111', border:'1px solid #252525', borderRadius:'7px',
      padding:'12px 14px', fontSize:'12px', fontFamily:'Menlo,monospace',
      color:'#a8d8a8', overflowX:'auto', marginTop:'8px',
      userSelect: selectable ? 'all' : 'auto',
    }}>{children}</pre>
  )
}

function DlBtn({ href, label }) {
  return (
    <a href={href} style={{
      background:'#1a1a1a', border:'1px solid #252525', color:'#e0e0e0',
      padding:'8px 16px', borderRadius:'7px', textDecoration:'none',
      fontSize:'13px', fontWeight:'500',
    }}>⬇ {label}</a>
  )
}

const codeStyle = {
  background:'#111', padding:'1px 6px', borderRadius:'4px',
  fontFamily:'Menlo,monospace', fontSize:'12px', color:'#4a9eff',
}

export async function getServerSideProps({ req, res }) {
  const session = await getServerSession(req, res, authOptions)
  if (!session) return { redirect: { destination: '/api/auth/signin', permanent: false } }

  return {
    props: {
      apiKey: process.env.HAWKER_API_KEY || '',
      apiUrl: process.env.NEXTAUTH_URL || 'https://hawker.vercel.app',
    },
  }
}
