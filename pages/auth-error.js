export default function AuthError({ error }) {
  return (
    <div style={{
      background:'#0f0f0f', color:'#e0e0e0', minHeight:'100vh',
      display:'flex', alignItems:'center', justifyContent:'center',
      fontFamily:'-apple-system,sans-serif',
    }}>
      <div style={{ textAlign:'center', padding:'40px' }}>
        <div style={{ fontFamily:'monospace', fontSize:'40px', marginBottom:'20px' }}>🦅</div>
        <h2 style={{ marginBottom:'10px' }}>Access Denied</h2>
        <p style={{ color:'#666', fontSize:'13px', marginBottom:'24px' }}>
          {error === 'AccessDenied'
            ? 'That Google account is not authorized to access Hawker.'
            : 'Authentication error. Please try again.'}
        </p>
        <a href="/api/auth/signin" style={{
          background:'#4a9eff', color:'#000', padding:'10px 20px',
          borderRadius:'7px', textDecoration:'none', fontSize:'13px', fontWeight:'700',
        }}>Try again</a>
      </div>
    </div>
  )
}

export async function getServerSideProps({ query }) {
  return { props: { error: query.error || null } }
}
