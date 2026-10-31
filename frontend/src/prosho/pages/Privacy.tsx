import { Link } from 'react-router-dom'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import DocPage, { H2, List, P, PRIVACY_EMAIL, strong } from '../components/DocPage'

const UPDATED = '31 October 2026'

// Plain-language notice for the closed beta. Every statement here must match
// what the code and the server actually do — change both together.
export default function ProshoPrivacy() {
  useDocumentTitle('Privacy | ProSho')
  const mail = <a href={`mailto:${PRIVACY_EMAIL}`} style={{ color: 'var(--accent)' }}>{PRIVACY_EMAIL}</a>

  return (
    <DocPage>
      <h1 style={{ fontSize: '1.75rem', fontWeight: 700, marginBottom: '0.4rem' }}>How ProSho handles your data</h1>
      <p style={{ fontSize: '0.85rem', color: 'var(--text-3)', marginBottom: '1.5rem' }}>Last updated {UPDATED} · closed beta</p>

      <P>
        ProSho is part of LVAMO. It turns a student project&apos;s GitHub repo into a page that backs up what the
        project claims. This page says what we keep, why, who else is involved, and how to get rid of it.
        Questions or requests: {mail}.
      </P>

      <H2>What we keep</H2>
      <List>
        <li><span style={strong}>Your GitHub profile</span> when you sign in: GitHub user id, username, name, avatar and your primary verified email. We ask GitHub for nothing else, and never post to GitHub for you.</li>
        <li><span style={strong}>What you put into a project</span>: title, page address, university and programme, demo link, claims and targets, milestones, and the evidence your CI sends us.</li>
        <li><span style={strong}>From the repo you connect</span> (through ProSho&apos;s GitHub App, only for repos you choose): its name, whether it&apos;s private, <code>prosho.yaml</code>, and for each commit its id, date, author&apos;s username and the first line of its message. We don&apos;t copy your code.</li>
        <li><span style={strong}>Data-source checks</span>: if your project lists data sources, our server checks those links once a day and keeps the result.</li>
        <li><span style={strong}>Mentor feedback</span>: messages between you and your assigned mentor.</li>
        <li><span style={strong}>A change log</span>: who changed what on a project and when, so mistakes can be traced and undone.</li>
      </List>

      <H2>Visits to project pages</H2>
      <P>
        We count page views per page per day, and keep only the website a visitor came from (for example
        &ldquo;linkedin.com&rdquo;), never the full link. No cookies, no IP addresses and no visitor profiles go into those
        counts. Your browser remembers for the current tab that a page was already counted, so a reload isn&apos;t counted twice.
      </P>
      <P>
        Signing in stores one access token in your browser&apos;s local storage. That&apos;s the only thing ProSho stores in
        your browser besides the view marker above. There are no advertising or analytics trackers.
      </P>

      <H2>Server logs</H2>
      <P>
        Like any website, our server logs each request: IP address, time, the address requested and your browser&apos;s
        user agent. We use these logs to fix problems and stop abuse. They are deleted after about 30 days. To
        limit abuse, the server also holds IP addresses in memory for up to an hour. They are never written to the database.
      </P>

      <H2>Who sees what</H2>
      <List>
        <li><span style={strong}>Private</span> pages: only you, your assigned mentor and LVAMO admins.</li>
        <li><span style={strong}>Unlisted</span> pages: anyone with the link.</li>
        <li><span style={strong}>Public</span> pages: anyone, and they may be listed in a ProSho gallery. You can only make a page public after your supervisor agrees.</li>
        <li>Mentor feedback and visit counts are never on the page. Only you and your mentor see them.</li>
        <li>For a private repo, the page can show commit counts per week but never the commit messages.</li>
      </List>

      <H2>Who else is involved</H2>
      <List>
        <li><span style={strong}>Oracle Cloud</span> runs our server and database in Frankfurt, Germany.</li>
        <li><span style={strong}>Cloudflare</span> serves the website and our domain names.</li>
        <li><span style={strong}>GitHub</span> handles sign-in and gives us access to the repos you connect.</li>
        <li><span style={strong}>Zoho</span> hosts our email, if you write to us.</li>
      </List>
      <P>We don&apos;t sell your data or share it with anyone else, and we don&apos;t use it to train AI models.</P>

      <H2>How long we keep it</H2>
      <P>
        Until you delete it. Before an upgrade we sometimes take a one-off backup of the database. Those
        backups stay on the same server and are deleted within 30 days.
      </P>

      <H2 id="your-rights">Your choices and rights</H2>
      <List>
        <li><span style={strong}>Change</span> anything about a project on its manage page, or in <code>prosho.yaml</code>.</li>
        <li><span style={strong}>Delete a project</span>: on its manage page, under &ldquo;Delete project&rdquo;. If its page was ever shared, the address stays retired so nobody else can take over the link.</li>
        <li><span style={strong}>Delete your account</span>: at the bottom of <Link to="/prosho/dashboard" style={{ color: 'var(--accent)' }}>your projects</Link>. Your projects and everything on them are deleted right away. Notes you left on another student&apos;s project stay in their thread, signed &ldquo;Former member&rdquo;. The change log keeps only a record that a deletion happened.</li>
        <li><span style={strong}>Disconnect GitHub</span>: remove ProSho&apos;s GitHub App in <a href="https://github.com/settings/installations" target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>GitHub settings</a>. Deleting your ProSho account doesn&apos;t do this for you.</li>
        <li><span style={strong}>Get a copy</span> of your data, or ask anything else: email {mail}. We answer within 30 days.</li>
      </List>
      <P>If you think we&apos;ve handled your data wrongly, tell us. You can also complain to your country&apos;s data protection authority.</P>
    </DocPage>
  )
}
