"""Single-workspace reviewed journeys on the existing durable campaign queue."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path

from .journeys import JourneyProposal


class Workflow:
    def __init__(self, campaigns, public_url=None):
        if not campaigns.reset_path:
            raise ValueError('Reviewed workflow requires an operator-configured reset path')
        self.campaigns = campaigns
        self.db = campaigns.db
        self.origin = public_url.removesuffix('/mcp') if public_url else ''
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS journeys (
                id TEXT PRIMARY KEY, digest TEXT NOT NULL, proposal TEXT NOT NULL,
                approved INTEGER NOT NULL DEFAULT 0, parent TEXT,
                created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                approved_at TEXT);
            CREATE TABLE IF NOT EXISTS workflow_runs (
                campaign TEXT PRIMARY KEY, request_id TEXT UNIQUE, provenance TEXT NOT NULL);
        ''')

    def link(self, kind, identifier):
        return f'{self.origin}/workspace#{kind}/{identifier}'

    def submit(self, proposal: dict, revision_of: str | None = None):
        """Save an immutable draft; no execution or automatic approval."""
        if revision_of:
            self.get(revision_of)
        validated = JourneyProposal.model_validate(proposal)
        encoded = validated.model_dump_json()
        if len(encoded.encode()) > 60000:
            raise ValueError('Proposal exceeds 60 KB')
        if self.db.execute('SELECT count(*) FROM journeys').fetchone()[0] >= 200:
            raise ValueError('Workspace proposal limit reached')
        identifier = uuid.uuid4().hex
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        with self.db:
            self.db.execute('INSERT INTO journeys(id,digest,proposal,parent) VALUES(?,?,?,?)',
                            (identifier, digest, encoded, revision_of))
        return self.get(identifier)

    def get(self, identifier):
        row = self.db.execute('SELECT * FROM journeys WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise ValueError('Unknown journey ID')
        return {'journey_id': row['id'], 'version': row['digest'],
                'status': 'approved' if row['approved'] else 'draft',
                'proposal': json.loads(row['proposal']), 'revision_of': row['parent'],
                'approved_at': row['approved_at'], 'review_url': self.link('journey', identifier)}

    def list(self):
        return [{'journey_id': r['id'], 'version': r['digest'],
                 'name': json.loads(r['proposal'])['scenario']['name'],
                 'status': 'approved' if r['approved'] else 'draft',
                 'review_url': self.link('journey', r['id'])}
                for r in self.db.execute('SELECT * FROM journeys ORDER BY created DESC, rowid DESC LIMIT 200')]

    def approve(self, identifier, version, reviewed):
        journey = self.get(identifier)
        if not reviewed or version != journey['version']:
            raise ValueError('Review this exact version, including assumptions and reset setup')
        with self.db:
            self.db.execute('UPDATE journeys SET approved=1, approved_at=COALESCE(approved_at,CURRENT_TIMESTAMP) WHERE id=?', (identifier,))
        return self.get(identifier)

    async def start(self, identifier, version, request_id, rerun_of=None):
        journey = self.get(identifier)
        if journey['status'] != 'approved' or journey['version'] != version:
            raise ValueError('This exact journey version is not approved')
        if not isinstance(request_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}', request_id):
            raise ValueError('Provide a unique request ID (8–80 letters, digits, _ or -)')
        if rerun_of:
            original = self.run(rerun_of)
            if original['status'] in {'queued', 'running', 'cancelling'}:
                raise ValueError('Wait for the original run to finish or cancel it')
            if original['journey_id'] != identifier or original['version'] != version:
                raise ValueError('Rerun must use the original reviewed version')
        scenario = JourneyProposal.model_validate(journey['proposal']).scenario
        provenance = {'journey_id': identifier, 'version': version, 'rerun_of': rerun_of,
                      'setup': journey['proposal']['setup']}
        campaign = await self.campaigns.enqueue([scenario], provenance=provenance, request_id=request_id)
        return self.run(campaign['campaign_id'])

    def run(self, identifier):
        row = self.db.execute('SELECT provenance FROM workflow_runs WHERE campaign=?', (identifier,)).fetchone()
        if row is None:
            raise ValueError('Unknown workflow run ID')
        result = self.campaigns.get(identifier)
        result.update(json.loads(row['provenance']))
        result['results_url'] = self.link('run', identifier)
        result['reset_policy'] = 'Operator reset before every profile; reset failure prevents execution'
        for job in result['jobs']:
            job['evidence'] = self.evidence(identifier, job['id'])
            row = self.db.execute('SELECT snapshot FROM jobs WHERE id=?', (job['id'],)).fetchone()
            job['expected_outcomes'] = json.loads(row['snapshot'])['assertions']
            result_path = self.campaigns.out / job['id'] / 'results.json'
            if (result_path.is_file() and not result_path.is_symlink()
                    and not result_path.parent.is_symlink() and result_path.stat().st_size <= 65536):
                try:
                    worker = json.loads(result_path.read_text())
                    if isinstance(worker, list) and worker and isinstance(worker[0], dict):
                        job['observed_result'] = str(worker[0].get('reason', ''))[:4000]
                except (ValueError, OSError):
                    pass
        return result

    def evidence(self, campaign_id, job_id):
        if not any(j['id'] == job_id for j in self.campaigns.get(campaign_id)['jobs']):
            raise ValueError('Job does not belong to this run')
        folder = self.campaigns.out / job_id / 'evidence'
        if not folder.exists() or folder.is_symlink() or folder.parent.is_symlink():
            return []
        allowed = {'final.png', 'trace.zip', 'actions.json', 'manifest.json'}
        result = []
        for path in sorted(folder.rglob('*')):
            if path.name not in allowed or not path.is_file() or path.is_symlink():
                continue
            if not path.resolve().is_relative_to(folder.resolve()):
                continue
            # Opaque per-run artifact ID: never accept arbitrary filesystem paths from clients.
            artifact_id = hashlib.sha256(str(path.relative_to(folder)).encode()).hexdigest()[:24]
            result.append({'artifact_id': artifact_id, 'name': path.name,
                           'download': f'/workflow-api/runs/{campaign_id}/jobs/{job_id}/artifacts/{artifact_id}'})
        return result

    def artifact(self, campaign_id, job_id, artifact_id):
        if self.db.execute('SELECT 1 FROM workflow_runs WHERE campaign=?', (campaign_id,)).fetchone() is None:
            raise ValueError('Unknown workflow run ID')
        if not any(a['artifact_id'] == artifact_id for a in self.evidence(campaign_id, job_id)):
            raise ValueError('Unknown artifact ID')
        folder = self.campaigns.out / job_id / 'evidence'
        for path in folder.rglob('*'):
            if hashlib.sha256(str(path.relative_to(folder)).encode()).hexdigest()[:24] == artifact_id:
                if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
                    break
                return path
        raise ValueError('Artifact unavailable')

    def export(self, identifier):
        import yaml
        journey = self.get(identifier)
        if journey['status'] != 'approved':
            raise ValueError('Approve the journey before exporting')
        proposal = journey['proposal']
        config = {'target': {'compose': '', 'service': '', 'port': 0},
                  'run': {'agents': []}, 'scenarios': [proposal['scenario']]}
        notes = f"Journey {identifier} version {journey['version']}\nSetup: {proposal['setup']}"
        return ''.join('# ' + line + '\n' for line in notes.splitlines()) + yaml.safe_dump(config, sort_keys=False)

    async def readiness(self):
        import httpx
        from playwright.sync_api import sync_playwright
        # Executable presence is a prerequisite check, not proof Chromium can launch.
        import asyncio
        def browser_check():
            with sync_playwright() as p:
                return Path(p.chromium.executable_path).exists()
        try:
            browser = await asyncio.to_thread(browser_check)
        except Exception:
            browser = False
        targets = []
        async with httpx.AsyncClient(timeout=5, trust_env=False, follow_redirects=False) as client:
            for index, target in enumerate(self.campaigns.targets, 1):
                try:
                    response = await client.get(target + '/')
                    reachable = response.status_code < 500
                except httpx.HTTPError:
                    reachable = False
                targets.append({'slot': index, 'reachable': reachable})
        return {'browser_executable_present': browser, 'browser_launch_verified': False,
                'reset_configured': bool(self.campaigns.reset_path), 'reset_executed': False,
                'targets': targets, 'test_credentials': 'Validated by journey assertions, not this check',
                'ready': browser and all(t['reachable'] for t in targets)}
