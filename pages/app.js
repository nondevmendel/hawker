import Head from 'next/head'

export default function App() {
  return (
    <>
      <Head>
        <meta charSet="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <meta name="robots" content="noindex, nofollow" />
        <title>Hawker</title>
      </Head>
      <div id="__hawker_root" />
    </>
  )
}

// All the UI is injected by the script in _document.js — keeping the same
// single-file structure as the original gallery.
