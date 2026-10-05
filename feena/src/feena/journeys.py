"""Reviewable journey proposals; generation and approval never execute browser actions."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import Field, model_validator

from .simulation_config import BrowserScenario, StrictModel


class JourneyProposal(StrictModel):
    version: int = 1
    scenario: BrowserScenario
    setup: str = Field(min_length=1, max_length=4000)
    assumptions: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def require_outcomes(self):
        if self.version != 1:
            raise ValueError('Unsupported proposal version')
        kinds = {assertion.kind for assertion in self.scenario.assertions}
        if 'json' not in kinds or not kinds.intersection({'visible', 'text', 'count'}):
            raise ValueError('Include both a visible UI assertion and a backend JSON invariant')
        return self


def save_proposal(proposal: JourneyProposal, path: Path) -> str:
    data = (proposal.model_dump_json(indent=2) + '\n').encode()
    # Never replace an earlier review or its evidence.
    with path.open('xb') as stream:
        stream.write(data)
    return hashlib.sha256(data).hexdigest()


def approve_proposal(source: Path, digest: str, destination: Path) -> None:
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('Proposal changed; review it and approve its current SHA-256')
    proposal = JourneyProposal.model_validate_json(data)
    # A separate config can only be run by an explicit simulate/ci invocation.
    config = {'target': {'compose': '', 'service': '', 'port': 0},
              'run': {'agents': []}, 'scenarios': [proposal.scenario.model_dump()]}
    import yaml
    with destination.open('x') as stream:
        notes = 'Reviewed proposal SHA-256: ' + digest + '\nSetup: ' + proposal.setup
        notes += '\nAssumptions: ' + '; '.join(proposal.assumptions)
        stream.write(''.join('# ' + line + '\n' for line in notes.splitlines()))
        yaml.safe_dump(config, stream, sort_keys=False)
