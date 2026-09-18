import { useEffect, useState } from 'react'
import { api } from './services/api.js'
import { getBackendUrl, setBackendUrl } from './config.js'

function Card(props) {
  return (
    <div className={'card ' + (props.a || '')}>
      <div className="card-title">{props.t}</div>
      <div className="card-value">{props.v}</div>
      {props.s && <div className="card-sub">{props.s}</div>}
    </div>
  )
}

function Overview(props) {
  const h = props.health
  const convs = props.convs
  if (!h) {
    return <div className="empty">Waiting for backend...</div>
  }
  return (
    <section>
      <div className="cards">
        <Card t="Backend" v="online" s={'db: ' + h.db} />
        <Card t="Jev" v={h.jev_configured ? 'configured' : 'not configured'} s="TYPESAFE_API_KEY" />
        <Card t="Conversations" v={convs.length} s="ingested" />
      </div>
      <h3>Recent conversations</h3>
      <table className="tbl">
        <thead>
          <tr><th>ID</th><th>Source</th><th>Bytes</th><th>Captured</th></tr>
        </thead>
        <tbody>
          {convs.map(function (c) {
            return (
              <tr key={c.id}>
                <td className="mono">{c.id}</td>
                <td>{c.source}</td>
                <td>{c.bytes}</td>
                <td className="muted">{c.captured_at}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </section>
  )
}

function Search() {
  const [q, setQ] = useState('')
  const [rows, setRows] = useState([])
  const [err, setErr] = useState('')
  function go() {
    api.search(q)
      .then(function (r) { setRows(r.results || []); setErr('') })
      .catch(function (e) { setErr(String(e.message || e)) })
  }
  return (
    <section>
      <div className="row">
        <h3>Search evidence</h3>
        <input value={q} onChange={function (e) { setQ(e.target.value) }} placeholder="fts5 query" />
        <button onClick={go}>Search</button>
      </div>
      {err ? <div className="empty bad">{err}</div> : null}
      <table className="tbl">
        <thead>
          <tr><th>Conv</th><th>Turn</th><th>Speaker</th><th>Text</th></tr>
        </thead>
        <tbody>
          {rows.map(function (r) {
            const txt = String(r.text || '').slice(0, 200)
            return (
              <tr key={r.id}>
                <td className="mono">{r.conversation_id}</td>
                <td>{r.turn_number}</td>
                <td>{r.speaker}</td>
                <td className="truncate" title={r.text}>{txt}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </section>
  )
}

function JevCalls() {
  const [calls, setCalls] = useState([])
  useEffect(function () {
    api.jevCalls().then(function (r) { setCalls(r.calls || []) }).catch(function () {})
  }, [])
  return (
    <section>
      <h3>Jev calls</h3>
      <table className="tbl">
        <thead>
          <tr><th>ID</th><th>Conv</th><th>NS</th><th>Latency</th><th>When</th></tr>
        </thead>
        <tbody>
          {calls.map(function (c) {
            return (
              <tr key={c.id}>
                <td className="mono">{c.id}</td>
                <td className="mono">{c.conversation_id}</td>
                <td>{c.ns}</td>
                <td className="mono">{c.latency_ms}ms</td>
                <td className="muted">{c.created_at}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </section>
  )
}

function Audit() {
  const [report, setReport] = useState('')
  const [err, setErr] = useState('')
  useEffect(function () {
    api.auditLatest()
      .then(function (r) { setReport(r) })
      .catch(function (e) { setErr(String(e.message || e)) })
  }, [])
  return (
    <section>
      <h3>Latest audit report</h3>
      {err ? <div className="empty bad">{err}</div> : null}
      {report ? <pre className="report">{report}</pre> : null}
    </section>
  )
}

export default function App() {
  const [tab, setTab] = useState('overview')
  const [health, setHealth] = useState(null)
  const [convs, setConvs] = useState([])
  const [url, setUrl] = useState(getBackendUrl())
  const [draft, setDraft] = useState(getBackendUrl())

  useEffect(function () {
    let cancel = false
    function tick() {
      api.health()
        .then(function (h) {
          if (cancel) return
          setHealth(h)
          return api.conversations()
        })
        .then(function (c) {
          if (cancel || !c) return
          setConvs(c.conversations || [])
        })
        .catch(function () {
          if (!cancel) setHealth(null)
        })
    }
    tick()
    const i = setInterval(tick, 5000)
    return function () { cancel = true; clearInterval(i) }
  }, [url])

  function apply() {
    setBackendUrl(draft)
    setUrl(getBackendUrl())
  }

  const tabs = [
    ['overview', 'Overview'],
    ['search', 'Search'],
    ['jev', 'Jev Calls'],
    ['audit', 'Audit'],
  ]

  const pillClass = 'pill ' + (health ? 'ok' : 'bad')
  const pillText = health ? 'online' : 'offline'

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand"><h1>Jev Workspace</h1></div>
        <div className="status">
          <span className={pillClass}>{pillText}</span>
          <input value={draft} onChange={function (e) { setDraft(e.target.value) }} />
          <button onClick={apply}>Apply</button>
        </div>
      </header>
      <nav className="tabs">
        {tabs.map(function (pair) {
          const id = pair[0]
          const label = pair[1]
          const cls = 'tab' + (tab === id ? ' active' : '')
          return (
            <button key={id} className={cls} onClick={function () { setTab(id) }}>
              {label}
            </button>
          )
        })}
      </nav>
      <main>
        {tab === 'overview' && <Overview health={health} convs={convs} />}
        {tab === 'search' && <Search />}
        {tab === 'jev' && <JevCalls />}
        {tab === 'audit' && <Audit />}
      </main>
      <footer><span>Backend: {url}</span></footer>
    </div>
  )
}
