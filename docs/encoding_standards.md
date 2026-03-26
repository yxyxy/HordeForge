# Encoding Standards

## Overview

This document outlines the encoding standards and practices for the HordeForge project. All text files in the project should use UTF-8 encoding to ensure proper internationalization and compatibility across different platforms and systems.

## File Encoding Policy

### UTF-8 as Standard

All text files in the HordeForge project must use UTF-8 encoding without BOM (Byte Order Mark). This includes:

- Python source files (.py)
- Markdown documentation files (.md)
- YAML configuration files (.yaml, .yml)
- JSON files (.json)
- Plain text files (.txt)
- Shell scripts (.sh)
- Docker and Docker Compose files
- Requirements and configuration files

### Why UTF-8

UTF-8 encoding is chosen for the following reasons:

1. **Universal Compatibility**: UTF-8 is supported by all modern operating systems and development tools
2. **Internationalization**: Supports all Unicode characters, allowing for multilingual documentation and code comments
3. **ASCII Compatibility**: UTF-8 is backward compatible with ASCII, ensuring no issues with existing ASCII content
4. **Web Standards**: UTF-8 is the standard encoding for web applications and APIs
5. **Python Standard**: Python 3 uses UTF-8 as the default encoding for source files

## Implementation Guidelines

### Python Files

All Python files should include the proper encoding declaration if needed (though UTF-8 is the default in Python 3):

```python
# -*- coding: utf-8 -*-
"""
This module demonstrates proper UTF-8 encoding.
Пример модуля с правильной кодировкой UTF-8.
"""
```

However, since Python 3 defaults to UTF-8, explicit encoding declarations are generally not needed unless working with Python 2 compatibility.

### Documentation Files

Markdown files should be saved with UTF-8 encoding to support international characters:

```markdown
# Пример документации с UTF-8

Этот документ содержит примеры использования русского языка и других Unicode символов: ✓ ✗ é ñ 中文
```

### Configuration Files

YAML and JSON configuration files should also use UTF-8 encoding:

```yaml
# Configuration with UTF-8 characters
settings:
  description: "Настройки системы HordeForge"
  language: "ru"
  features:
    - "Множественные LLM провайдеры"
    - "Система памяти агентов"
    - "Оптимизация контекста"
```

## File Conversion

### Converting from Other Encodings

If you encounter files with incorrect encoding, use the following methods to convert them:

#### Using Python
```python
# Convert file from one encoding to UTF-8
def convert_to_utf8(input_file, output_file, source_encoding):
    with open(input_file, 'r', encoding=source_encoding) as f:
        content = f.read()
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(content)

# Example usage
convert_to_utf8('old_file.txt', 'new_file.txt', 'cp1251')
```

#### Using iconv (Linux/Mac)
```bash
# Convert from cp1251 to UTF-8
iconv -f cp1251 -t utf-8 input_file.txt > output_file.txt

# Convert multiple files
find . -name "*.md" -exec iconv -f cp1251 -t utf-8 {} -o {}.utf8 \; && find . -name "*.md.utf8" -exec sh -c 'mv "$1" "${1%.utf8}"' _ {} \;
```

#### Using PowerShell (Windows)
```powershell
# Convert from other encoding to UTF-8
Get-Content input_file.txt -Encoding UTF8 | Set-Content output_file.txt -Encoding UTF8
```

## Verification

### Checking File Encoding

Use these commands to verify file encoding:

#### Linux/Mac
```bash
# Check file encoding
file -bi filename.txt

# Check multiple files
find . -name "*.py" -exec file -bi {} \;
find . -name "*.md" -exec file -bi {} \;
```

#### Python Script for Bulk Verification
```python
import os
import chardet

def check_encoding(file_path):
    with open(file_path, 'rb') as f:
        raw_data = f.read()
        result = chardet.detect(raw_data)
        return result['encoding']

def verify_project_encoding(root_dir='.'):
    encodings = {}
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file.endswith(('.py', '.md', '.yaml', '.yml', '.json', '.txt')):
                file_path = os.path.join(root, file)
                encoding = check_encoding(file_path)
                if encoding != 'utf-8':
                    encodings[file_path] = encoding
    
    return encodings

# Check for non-UTF-8 files
non_utf8_files = verify_project_encoding('.')
if non_utf8_files:
    print("Files with non-UTF-8 encoding:")
    for file_path, encoding in non_utf8_files.items():
        print(f"{file_path}: {encoding}")
else:
    print("All files are properly encoded in UTF-8")
```

## Editor Configuration

### VS Code

Configure VS Code to use UTF-8 by default:

```json
{
    "files.encoding": "utf8",
    "files.autoGuessEncoding": true,
    "python.defaultInterpreterPath": "./.venv/bin/python"
}
```

### Vim/Neovim

Add to your .vimrc:
```
set encoding=utf-8
set fileencoding=utf-8
set bomb
```

### PyCharm

In PyCharm settings:
- File -> Settings -> Editor -> File Encodings
- Set Global Encoding to UTF-8
- Set Project Encoding to UTF-8
- Set Default encoding for properties files to UTF-8

## Common Issues and Solutions

### Issue: Garbled Characters

**Symptoms**: Characters like `` or `Ð¿Ñ€Ð¸Ð¼ÐµÑ€` appear in files

**Solution**: Convert the file to UTF-8 encoding using the methods described above

### Issue: Mixed Encoding in Repository

**Symptoms**: Some files display correctly, others show garbled text

**Solution**: 
1. Identify all non-UTF-8 files using the verification script
2. Convert them to UTF-8 systematically
3. Update the encoding standards document

### Issue: Terminal Display Problems

**Symptoms**: Russian or other Unicode text doesn't display properly in terminal

**Solution**: Ensure terminal supports UTF-8:
```bash
# Check locale settings
locale

# Set UTF-8 locale if needed
export LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8
```

## Best Practices

### For Developers

1. **Always use UTF-8**: When creating new files, ensure they are saved in UTF-8
2. **Verify encoding**: Before committing files, verify they use UTF-8 encoding
3. **Use proper editors**: Use editors that support UTF-8 and show encoding information
4. **Handle encoding in code**: When reading external files, specify encoding explicitly:

```python
# Good practice - specify encoding explicitly
with open('file.txt', 'r', encoding='utf-8') as f:
    content = f.read()

# Avoid - relies on system default
with open('file.txt', 'r') as f:  # Don't do this
    content = f.read()
```

### For Documentation

1. **Use Unicode characters properly**: When documenting international features, use proper Unicode characters
2. **Test rendering**: Verify that documentation renders correctly with UTF-8 characters
3. **Provide examples**: Include examples that demonstrate proper UTF-8 usage

### For CI/CD

Add encoding checks to your CI pipeline:

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

## Migration Process

### Automated Migration Script

For migrating existing files to UTF-8:

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
    
    if original_encoding and 'utf' not in original_encoding.lower():
        print(f"Converting {file_path} from {original_encoding} to UTF-8")
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
    extensions = {'.py', '.md', '.yaml', '.yml', '.json', '.txt', '.cfg', '.ini', '.toml'}
    converted_count = 0
    
    for root, dirs, files in os.walk(root_dir):
        # Skip hidden directories and build directories
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'node_modules', '.git']]
        
        for file in files:
            ext = Path(file).suffix.lower()
            if ext in extensions:
                file_path = Path(root) / file
                if convert_file_to_utf8(file_path):
                    converted_count += 1
    
    print(f"Converted {converted_count} files to UTF-8 encoding")

if __name__ == "__main__":
    convert_project_to_utf8(".")
```

## Compliance Checking

### Pre-commit Hook

Add to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: encoding-check
        name: Check file encoding
        entry: python -c "import chardet; import sys; exit(0 if all('utf' in chardet.detect(open(f, 'rb').read())['encoding'].lower() for f in sys.argv[1:] if open(f, 'rb').read()) else 1)"
        language: python
        files: \.(py|md|yaml|yml|json|txt)$
        additional_dependencies: [chardet]
```

## Summary

The UTF-8 encoding standard ensures:
- Consistent character representation across platforms
- Proper internationalization support
- Compatibility with web standards
- Future-proof text handling
- Proper display of documentation in multiple languages

All contributors should ensure that new files are created with UTF-8 encoding and that existing files maintain proper encoding. The project includes tools and scripts to verify and convert file encodings as needed.