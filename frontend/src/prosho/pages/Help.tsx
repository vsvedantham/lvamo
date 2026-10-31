import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import DocPage, { H2, List, P, PRIVACY_EMAIL, strong } from '../components/DocPage'

const pre: React.CSSProperties = {
  margin: '0 0 0.9rem', padding: '0.85rem', background: 'var(--bg-elevated)', border: '1px solid var(--border)',
  borderRadius: 'var(--radius-xs)', fontSize: '0.78rem', overflowX: 'auto', lineHeight: 1.55,
}

const MANIFEST = `version: 1
title: HeatRisk EU
type: data-science            # or: frontend
summary: Who is most at risk from summer heat in five European countries
problem: >
  Each country counts heat deaths differently; no open view links
  how hot it gets to who is exposed.
demo:
  kind: streamlit             # streamlit | url | video
  url: https://heatrisk.streamlit.app
claims:
  - id: predict-2026
    text: Predict 2026 heat deaths within ±25% of official estimates
    metric: prediction_error_pct
    target: { op: abs_lte, value: 25 }
  - id: city-maps
    text: Heat vulnerability maps for five capitals
    # no metric: you set the status yourself, shown as "self-reported"
data:
  sources:
    - name: Eurostat weekly deaths
      url: https://ec.europa.eu/eurostat/
      licence: CC BY 4.0`

const EVIDENCE = `[
  {"key": "prediction_error_pct", "kind": "metric", "value_num": 18.4, "unit": "%"},
  {"key": "pipeline", "kind": "run", "value_text": "success",
   "payload": {"tests_passed": 48, "tests_total": 48}}
]`

// The "Set up ProSho in 15 minutes" guide for pilot students. Keep it in
// step with the manage page: same names for the same buttons.
export default function ProshoHelp() {
  useDocumentTitle('Set up ProSho in 15 minutes | ProSho')
  return (
    <DocPage>
      <h1 style={{ fontSize: '1.75rem', fontWeight: 700, marginBottom: '0.6rem' }}>Set up ProSho in 15 minutes</h1>
      <P>
        You need a GitHub account with your project&apos;s repo on it, and an invite to the beta. At the end you&apos;ll
        have a page that shows what your project promises and the evidence that backs it up — updated on every push.
      </P>

      <Step n={1} title="Sign in" minutes={1}>
        <P>
          Go to <Link to="/prosho/login" style={{ color: 'var(--accent)' }}>Sign in</Link> and continue with GitHub.
          ProSho reads only your name, username, avatar and email. If it says you&apos;re not on the invite list,
          send your GitHub username to whoever invited you.
        </P>
      </Step>

      <Step n={2} title="Create the project" minutes={1}>
        <P>
          Press <span style={strong}>New project</span>. Pick a title, the page address (for example{' '}
          <code>heatrisk-eu</code>) and the type: data science or frontend. Choose the address carefully. Once
          you&apos;ve shared the page it can&apos;t change, so links on your CV keep working.
        </P>
      </Step>

      <Step n={3} title="Connect the repo" minutes={3}>
        <P>
          On the project page, under <span style={strong}>GitHub repository</span>, press <span style={strong}>Install on GitHub</span>.
          Install ProSho&apos;s GitHub App on your <em>personal</em> account (organisations aren&apos;t supported yet), let it
          see only the project&apos;s repo, then pick the repo and press <span style={strong}>Connect</span>.
        </P>
        <P>The app can only read. It never writes to your repo. Private repos work, and their commit messages stay off the page.</P>
      </Step>

      <Step n={4} title="Add prosho.yaml" minutes={5}>
        <P>
          ProSho shows you a starter file once the repo is connected. Save it as <code>prosho.yaml</code> at the root of the repo,
          fill it in, push, and press <span style={strong}>Sync now</span>. After that, every push to the default branch updates the page.
        </P>
        <pre style={pre}>{MANIFEST}</pre>
        <List>
          <li><span style={strong}>Claims</span> are what the project promises, up to 30. Give each one a short <code>id</code> (lowercase letters, digits, <code>-</code> or <code>_</code>).</li>
          <li>A claim with a <code>metric</code> and <code>target</code> is decided by evidence: <code>gte</code>, <code>lte</code>, <code>abs_lte</code>, <code>eq</code>, or <code>between</code> (with <code>value_hi</code>). Nobody types in &ldquo;met&rdquo;.</li>
          <li>A claim without them is <em>self-reported</em>: you set its status on the project page, and the public page says so.</li>
          <li>Mistakes are shown with their line number. Until you fix them, the page keeps the last version that worked.</li>
        </List>
      </Step>

      <Step n={5} title="Send evidence from CI" minutes={5} optional>
        <P>
          Under <span style={strong}>Evidence from CI</span>, create a token. Copy it right away — it&apos;s shown once. Then, in your repo
          on GitHub: <em>Settings → Secrets and variables → Actions → New repository secret</em>, named <code>PROSHO_TOKEN</code>.
        </P>
        <P>Have your pipeline write its results to <code>prosho-evidence.json</code>, using your claims&apos; metric names as keys:</P>
        <pre style={pre}>{EVIDENCE}</pre>
        <P>
          Then add the step ProSho shows you, with <span style={strong}>Copy step</span>, at the end of your workflow job. It
          posts the file once per run. More than 30 posts a minute from one token are refused, so don&apos;t put it in a loop.
        </P>
      </Step>

      <Step n={6} title="Plan milestones and share" minutes={2}>
        <List>
          <li><span style={strong}>Milestones</span>: add the steps of your project with dates and tick them off. If you have a mentor, they can mark completed steps as reviewed.</li>
          <li><span style={strong}>Who can see the page</span>: <em>Private</em> while you set up. <em>Unlisted</em> for anyone with the link (supervisor, examiners, recruiters). <em>Public</em> only after your supervisor agrees.</li>
          <li>Press <span style={strong}>View page ↗</span> to see exactly what visitors see.</li>
        </List>
      </Step>

      <H2>If something&apos;s off</H2>
      <List>
        <li><span style={strong}>&ldquo;prosho.yaml not found&rdquo;</span>: the file must be at the root of the default branch, named exactly <code>prosho.yaml</code>.</li>
        <li><span style={strong}>&ldquo;ProSho lost access&rdquo;</span>: the app was uninstalled or the repo was removed from it. Pick the repo again on the project page.</li>
        <li><span style={strong}>CI step fails with 401</span>: the <code>PROSHO_TOKEN</code> secret is missing, mistyped or revoked. Create a new token.</li>
        <li><span style={strong}>A claim stays &ldquo;no evidence yet&rdquo;</span>: the <code>key</code> in your evidence must match the claim&apos;s <code>metric</code> exactly.</li>
        <li><span style={strong}>Done with ProSho?</span> Delete a project at the bottom of its page, or your whole account at the bottom of <Link to="/prosho/dashboard" style={{ color: 'var(--accent)' }}>your projects</Link>. See <Link to="/prosho/privacy" style={{ color: 'var(--accent)' }}>how we handle your data</Link>.</li>
      </List>
      <P>Stuck? Ask your mentor, or write to <a href={`mailto:${PRIVACY_EMAIL}`} style={{ color: 'var(--accent)' }}>{PRIVACY_EMAIL}</a>.</P>
    </DocPage>
  )
}

function Step({ n, title, minutes, optional, children }: { n: number; title: string; minutes: number; optional?: boolean; children: ReactNode }) {
  return (
    <section style={{ marginTop: '2rem' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.6rem', flexWrap: 'wrap', marginBottom: '0.6rem' }}>
        <span aria-hidden="true" style={{ width: '1.6rem', height: '1.6rem', flex: 'none', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', borderRadius: '50%', background: 'var(--accent)', color: '#fff', fontSize: '0.8rem', fontWeight: 700, alignSelf: 'center' }}>{n}</span>
        <h2 style={{ fontSize: '1.15rem', fontWeight: 700 }}>{title}</h2>
        <span style={{ fontSize: '0.78rem', color: 'var(--text-3)' }}>{minutes} min{optional ? ' · optional' : ''}</span>
      </div>
      {children}
    </section>
  )
}
