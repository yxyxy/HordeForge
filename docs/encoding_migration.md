# Encoding Migration Guide

## Overview

This document describes the migration process from various encodings to UTF-8 for the HordeForge project. The migration ensures all text files use consistent UTF-8 encoding to support internationalization and proper cross-platform compatibility.

## Migration Scope

### Files Affected

The migration affects all text-based files in the project:

- **Source code files**: `.py`, `.js`, `.ts`, `.java`, etc.
- **Documentation files**: `.md`, `.rst`, `.txt`, etc.
- **Configuration files**: `.yaml`, `.yml`, `.json`, `.toml`, `.cfg`, etc.
- **Template files**: `.jinja`, `.html`, `.xml`, etc.
- **Script files**: `.sh`, `.bat`, `.ps1`, etc.
- **Data files**: `.csv`, `.log`, `.env`, etc.

### Directories Included

- `docs/` - All documentation files
- `agents/` - Agent source code and configuration
- `pipelines/` - Pipeline configuration files
- `rules/` - Rule files and policies
- `examples/` - Example files and demonstrations
- `tests/` - Test files and configurations
- `scripts/` - Utility scripts
- `templates/` - Template files
- Root directory files (README.md, etc.)

## Pre-Migration Assessment

### Current Encoding Detection

Before migration, we analyzed the current encoding state of the project:

```bash
# Install chardet for encoding detection
pip install chardet

# Python script to detect encodings
python -c "
import os
import chardet
from pathlib import Path

def detect_encoding(file_path):
    with open(file_path, 'rb') as f:
        raw_data = f.read()
        result = chardet.detect(raw_data)
        return result['encoding'], result['confidence']

# Check all text files in project
encodings = {}
for root, dirs, files in os.walk('.'):
    for file in files:
        if file.endswith(('.py', '.md', '.yaml', '.yml', '.json', '.txt', '.cfg', '.toml', '.env')):
            file_path = os.path.join(root, file)
            encoding, confidence = detect_encoding(file_path)
            if encoding and confidence > 0.7:  # Only if confidence is high
                encodings[file_path] = (encoding, confidence)

# Print results
for file_path, (encoding, confidence) in encodings.items():
    print(f'{file_path}: {encoding} (confidence: {confidence:.2f})')
"
```

### Common Encodings Found

During the assessment, we identified the following encodings that needed conversion:

- **CP1251** (Windows-1251) - Used for Cyrillic text
- **KOI8-R** - Legacy Russian encoding
- **ISO-8859-1** - Latin-1 encoding
- **MacRoman** - Mac OS Roman encoding
- **UTF-16** - Unicode with BOM
- **ASCII** - Basic ASCII (already compatible with UTF-8)

## Migration Process

### Step 1: Backup Current State

Before starting the migration, create a backup of the entire project:

```bash
# Create backup archive
tar -czf hordeforge_backup_$(date +%Y%m%d_%H%M%S).tar.gz --exclude='.git' --exclude='*.pyc' --exclude='__pycache__' .

# Or using zip
zip -r hordeforge_backup_$(date +%Y%m%d_%H%M%S).zip . -x '*.git/*' '*__pycache__/*' '*.pyc'
```

### Step 2: Identify Non-UTF-8 Files

Use the following script to identify all files that are not in UTF-8:

```python
#!/usr/bin/env python3
"""
Script to identify files with non-UTF-8 encoding
"""
import os
import chardet
from pathlib import Path

def find_non_utf8_files(root_dir='.'):
    """Find all files that are not in UTF-8 encoding."""
    non_utf8_files = []
    extensions = {'.py', '.md', '.yaml', '.yml', '.json', '.txt', '.cfg', '.toml', '.env', '.sh', '.bat', '.ps1', '.csv', '.log', '.html', '.xml', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.sql', '.sql', '.ini', '.properties'}
    
    for root, dirs, files in os.walk(root_dir):
        # Skip hidden directories and build directories
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'node_modules', '.git', 'dist', 'build', 'venv', '.venv']]
        
        for file in files:
            ext = Path(file).suffix.lower()
            if ext in extensions:
                file_path = Path(root) / file
                try:
                    # Try to read as UTF-8 first
                    with open(file_path, 'r', encoding='utf-8') as f:
                        f.read()
                except UnicodeDecodeError:
                    # If UTF-8 fails, detect actual encoding
                    with open(file_path, 'rb') as f:
                        raw_data = f.read()
                        result = chardet.detect(raw_data)
                        detected_encoding = result['encoding']
                        confidence = result['confidence']
                        
                        if detected_encoding and confidence > 0.7:
                            non_utf8_files.append((str(file_path), detected_encoding, confidence))
    
    return non_utf8_files

# Find and list non-UTF-8 files
non_utf8_files = find_non_utf8_files('.')
if non_utf8_files:
    print("Files with non-UTF-8 encoding:")
    for file_path, encoding, confidence in non_utf8_files:
        print(f"{file_path}: {encoding} (confidence: {confidence:.2f})")
else:
    print("All files are already in UTF-8 encoding")
```

### Step 3: Convert Files to UTF-8

#### Automated Conversion Script

```python
#!/usr/bin/env python3
"""
Script to convert all project files to UTF-8 encoding
"""
import os
import chardet
from pathlib import Path

def convert_file_to_utf8(file_path):
    """Convert a single file to UTF-8 encoding."""
    with open(file_path, 'rb') as f:
        raw_data = f.read()
        result = chardet.detect(raw_data)
        original_encoding = result['encoding']
        confidence = result['confidence']
    
    if original_encoding and confidence > 0.7 and 'utf' not in original_encoding.lower():
        print(f"Converting {file_path} from {original_encoding} to UTF-8 (confidence: {confidence:.2f})")
        try:
            content = raw_data.decode(original_encoding)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"Error converting {file_path}: {e}")
            return False
    else:
        return False  # Already UTF-8 or couldn't detect

def convert_project_to_utf8(root_dir='.'):
    """Convert all text files in project to UTF-8."""
    extensions = {'.py', '.md', '.yaml', '.yml', '.json', '.txt', '.cfg', '.toml', '.env', '.sh', '.bat', '.ps1', '.csv', '.log', '.html', '.xml', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.sql', '.ini', '.properties'}
    converted_count = 0
    error_count = 0
    
    for root, dirs, files in os.walk(root_dir):
        # Skip hidden directories and build directories
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'node_modules', '.git', 'dist', 'build', 'venv', '.venv']]
        
        for file in files:
            ext = Path(file).suffix.lower()
            if ext in extensions:
                file_path = Path(root) / file
                if convert_file_to_utf8(file_path):
                    converted_count += 1
                elif ext in ['.py', '.md', '.yaml', '.yml', '.json', '.txt']:  # Log errors for important file types
                    try:
                        # Try to read as UTF-8 to confirm it's already UTF-8
                        with open(file_path, 'r', encoding='utf-8') as f:
                            f.read()
                    except UnicodeDecodeError:
                        error_count += 1
                        print(f"Could not convert or confirm UTF-8 for: {file_path}")
    
    print(f"Conversion completed: {converted_count} files converted, {error_count} errors")
    return converted_count, error_count

if __name__ == "__main__":
    convert_project_to_utf8(".")
```

#### Using Command Line Tools

For Linux/Mac systems:

```bash
# Convert all Python files from CP1251 to UTF-8
find . -name "*.py" -exec iconv -f cp1251 -t utf-8 {} -o {}.utf8 \; && find . -name "*.py.utf8" -exec sh -c 'mv "$1" "${1%.utf8}"' _ {} \;

# Convert all Markdown files
find . -name "*.md" -exec iconv -f cp1251 -t utf-8 {} -o {}.utf8 \; && find . -name "*.md.utf8" -exec sh -c 'mv "$1" "${1%.utf8}"' _ {} \;

# Convert all YAML files
find . -name "*.yaml" -exec iconv -f cp1251 -t utf-8 {} -o {}.utf8 \; && find . -name "*.yaml.utf8" -exec sh -c 'mv "$1" "${1%.utf8}"' _ {} \;
```

For Windows systems (PowerShell):

```powershell
# Convert all Python files
Get-ChildItem -Recurse -Filter "*.py" | ForEach-Object {
    $content = Get-Content $_.FullName -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($content -eq $null) {
        # Try different encoding
        $content = Get-Content $_.FullName -Encoding Default
        $content | Set-Content $_.FullName -Encoding UTF8
        Write-Host "Converted $($_.FullName) to UTF-8"
    }
}
```

### Step 4: Verify Conversion

After conversion, verify that all files are properly encoded:

```python
#!/usr/bin/env python3
"""
Script to verify all files are in UTF-8 encoding
"""
import os
from pathlib import Path

def verify_utf8_encoding(root_dir='.'):
    """Verify that all text files are in UTF-8 encoding."""
    extensions = {'.py', '.md', '.yaml', '.yml', '.json', '.txt', '.cfg', '.toml', '.env', '.sh', '.bat', '.ps1', '.csv', '.log', '.html', '.xml', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.sql', '.ini', '.properties'}
    errors = []
    
    for root, dirs, files in os.walk(root_dir):
        # Skip hidden directories and build directories
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'node_modules', '.git', 'dist', 'build', 'venv', '.venv']]
        
        for file in files:
            ext = Path(file).suffix.lower()
            if ext in extensions:
                file_path = Path(root) / file
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        f.read()
                except UnicodeDecodeError as e:
                    errors.append((str(file_path), str(e)))
    
    return errors

# Verify all files are UTF-8
errors = verify_utf8_encoding('.')
if errors:
    print("Files with UTF-8 encoding errors:")
    for file_path, error in errors:
        print(f"{file_path}: {error}")
else:
    print("All files are properly encoded in UTF-8")
```

## Post-Migration Verification

### Automated Testing

Run the following tests to ensure the migration didn't break functionality:

```bash
# Run all tests to ensure no functionality was broken
make test

# Test specific components that might be affected by encoding
pytest tests/unit/test_encoding.py
pytest tests/unit/test_i18n.py
pytest tests/unit/test_agents.py

# Test CLI functionality
horde --help
hordeforge --help

# Test pipeline execution
horde pipeline list
```

### Character Display Verification

Verify that international characters display correctly:

```bash
# Test Russian characters
echo "Проверка русских символов: привет, мир!" > test_encoding.txt
cat test_encoding.txt

# Test other Unicode characters
echo "Unicode test: ✓ ✗ é ñ 中文 العربية" >> test_encoding.txt
cat test_encoding.txt

# Clean up
rm test_encoding.txt
```

## Configuration Updates

### Editor Configuration

Update editor configurations to enforce UTF-8:

#### VS Code (.vscode/settings.json)
```json
{
    "files.encoding": "utf8",
    "files.autoGuessEncoding": true,
    "python.defaultInterpreterPath": "./.venv/bin/python"
}
```

#### Vim (.vimrc)
```
set encoding=utf-8
set fileencoding=utf-8
set bomb
```

### Git Configuration

Ensure Git handles UTF-8 properly:

```bash
# Configure Git for UTF-8
git config core.precomposeunicode true
git config core.quotepath false

# Add to .gitattributes to ensure proper handling
echo "* text=auto eol=lf" >> .gitattributes
echo "*.py text eol=lf charset=utf-8" >> .gitattributes
echo "*.md text eol=lf charset=utf-8" >> .gitattributes
```

## Environment Variables

Set environment variables to ensure UTF-8 support:

```bash
# Add to .env file
PYTHONIOENCODING=utf-8
LC_ALL=en_US.UTF-8
LANG=en_US.UTF-8

# For Windows compatibility
PYTHONUTF8=1
```

## Troubleshooting

### Common Issues During Migration

#### Issue 1: Invalid Characters After Conversion
**Symptoms**: Garbled text or strange characters after conversion
**Solution**: 
1. Identify the original encoding more accurately
2. Use the detection script with higher confidence threshold
3. Manually convert problematic files

#### Issue 2: Build/Run Failures
**Symptoms**: Compilation or runtime errors after migration
**Solution**:
1. Check for BOM (Byte Order Mark) in converted files
2. Verify that all dependencies support UTF-8
3. Update any hardcoded encoding assumptions in code

#### Issue 3: Database Issues
**Symptoms**: Database operations fail with encoding errors
**Solution**:
1. Ensure database connection uses UTF-8
2. Update database collation if needed
3. Check stored procedures and queries for encoding issues

### Recovery Procedures

If the migration causes issues, you can recover using the backup:

```bash
# Restore from backup
tar -xzf hordeforge_backup_YYYYMMDD_HHMMSS.tar.gz

# Or with zip
unzip hordeforge_backup_YYYYMMDD_HHMMSS.zip
```

## Quality Assurance

### Pre-Migration Checklist
- [ ] Backup entire project
- [ ] Document current encoding state
- [ ] Test conversion script on sample files
- [ ] Verify all tests pass before migration

### Post-Migration Checklist
- [ ] Verify all files are in UTF-8
- [ ] Run full test suite
- [ ] Test international character display
- [ ] Verify CLI and API functionality
- [ ] Check documentation rendering
- [ ] Test with different locale settings

### Validation Commands
```bash
# Check encoding of all files
find . -name "*.py" -exec file -bi {} \;
find . -name "*.md" -exec file -bi {} \;

# Run comprehensive tests
make test-all

# Verify token budget system still works
horde llm tokens

# Verify memory system still works
horde memory status

# Verify RAG system still works
horde rag status
```

## Performance Impact

### Expected Changes
- **No Performance Impact**: UTF-8 is the standard encoding and should not affect performance
- **Better Internationalization**: Improved support for non-English characters
- **Cross-Platform Compatibility**: Consistent behavior across different operating systems

### Monitoring
Monitor the system after migration to ensure no performance degradation:

```bash
# Monitor token usage
horde llm tokens --history

# Monitor pipeline performance
horde runs list --limit 10

# Monitor memory performance
horde memory status
```

## Security Considerations

### Positive Impacts
- **Consistent Input Handling**: UTF-8 encoding helps prevent encoding-based security issues
- **Proper Character Validation**: Better handling of international characters in inputs
- **Standard Compliance**: Following UTF-8 standard aligns with security best practices

### Validation
Ensure that the migration doesn't introduce security vulnerabilities:

```bash
# Test input validation with international characters
python -c "
from agents.token_budget_system import TokenBudgetSystem
budget_system = TokenBudgetSystem()
# Test with various Unicode characters
test_inputs = ['hello', 'привет', 'こんにちは', 'مرحبا', '¡Hola!']
for inp in test_inputs:
    print(f'Testing: {inp}')
    # This should not raise any encoding errors
"
```

## Rollback Plan

If critical issues are discovered after migration:

1. **Immediate Action**: Stop all services
2. **Restore Backup**: Use the backup created before migration
3. **Investigate**: Identify the root cause of issues
4. **Fix**: Apply fixes to the migration script
5. **Retry**: Re-run migration with fixes
6. **Verify**: Run comprehensive tests

## Future Maintenance

### Preventing Encoding Issues

Add encoding checks to CI/CD pipeline:

```yaml
# .github/workflows/encoding-check.yml
name: Encoding Check
on: [push, pull_request]
jobs:
  encoding-check:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'
    - name: Install chardet
      run: pip install chardet
    - name: Check file encodings
      run: |
        python -c "
        import os
        import chardet
        
        non_utf8 = []
        for root, dirs, files in os.walk('.'):
            for file in files:
                if file.endswith(('.py', '.md', '.yaml', '.yml', '.json', '.txt')):
                    path = os.path.join(root, file)
                    with open(path, 'rb') as f:
                        raw_data = f.read()
                        result = chardet.detect(raw_data)
                        if result['encoding'] and 'utf' not in result['encoding'].lower():
                            non_utf8.append((path, result['encoding']))
        
        if non_utf8:
            print('Files with non-UTF-8 encoding:')
            for path, encoding in non_utf8:
                print(f'{path}: {encoding}')
            exit(1)
        else:
            print('All files are properly encoded in UTF-8')
        "
```

### Pre-commit Hooks

Add encoding check to pre-commit hooks:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: encoding-check
        name: Check file encoding
        entry: python -c "import chardet; import sys; exit(0 if all('utf' in chardet.detect(open(f, 'rb').read())['encoding'].lower() for f in sys.argv[1:] if open(f, 'rb').read()) else 1)"
        language: python
        files: \.(py|md|yaml|yml|json|txt|cfg|toml|env)$
        additional_dependencies: [chardet]
```

## Summary

The encoding migration to UTF-8 ensures:
- Consistent character representation across platforms
- Proper internationalization support
- Compatibility with modern development tools
- Alignment with web standards
- Future-proof text handling

The migration process is designed to be safe and reversible, with comprehensive backup and verification procedures. All HordeForge components, including the token budget system, memory system, and RAG system, continue to function properly with UTF-8 encoded files.