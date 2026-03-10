# Seed Data

This directory contains sample data to populate the test sandbox.

## Directories

- `issues/` - Sample GitHub issues (JSON format)
- `code/` - Sample source code files
- `tests/` - Sample test files

## Usage

The seed data is also defined in `../config.yaml`. The setup script reads from
the config file and creates issues and files in the GitHub repository.

## Manual Import

To manually import seed data:

1. Create issues manually in the GitHub UI using files in `issues/`
2. Push code files from `code/` and `tests/` to the repository
