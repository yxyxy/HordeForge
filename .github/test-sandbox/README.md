# Test Sandbox Configuration

This directory contains configuration and seed data for the test sandbox repository.

## Setup Instructions

### 1. Create GitHub Organization
1. Go to https://github.com/organizations/plan
2. Create a new organization (e.g., `hordeforge-test`)
3. Choose free tier

### 2. Create Test Repository
1. In the organization, create a new repository: `hordeforge-sandbox`
2. Make it public or private (private requires paid org for Actions)
3. Enable Issues and Pull Requests

### 3. Configure Repository Settings
- Enable GitHub Actions
- Set up branch protection for `main` (optional)
- Add secrets if needed for testing

### 4. Run Setup Script
```bash
python .github/test-sandbox/setup_sandbox.py --token YOUR_GITHUB_TOKEN --org hordeforge-test
```

## Seed Data

The `seed/` directory contains sample data to populate the sandbox:

- `seed/issues/` - Sample GitHub issues
- `seed/code/` - Sample code files
- `seed/tests/` - Sample test files

## Files in This Directory

- `config.yaml` - Sandbox configuration
- `setup_sandbox.py` - Script to populate sandbox
- `seed/` - Sample data directory
