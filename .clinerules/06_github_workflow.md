# GitHub Integration Rules

HordeForge interacts with GitHub through agents.

Supported actions:

- read issues
- comment on issues
- create branches
- commit code
- create pull requests
- review pull requests
- merge pull requests
- close issues

All GitHub operations must be performed via integration layer.

Agents must not directly call GitHub APIs.