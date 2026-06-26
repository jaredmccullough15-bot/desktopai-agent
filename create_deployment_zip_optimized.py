#!/usr/bin/env python3
"""Create optimized Beanstalk deployment package (under 500MB)."""

import zipfile
import os
import sys

def should_include(filepath):
    """Check if file should be included in deployment."""
    # Skip directories and common build artifacts
    skip_patterns = [
        '__pycache__', '.pyc', '.pyo', '.pyd',
        '.git', '.gitignore', '.gitattributes',
        'node_modules', '.npm', 'dist', 'build',
        '__MACOSX', '.DS_Store',
        '.pytest_cache', '.tox', 'htmlcov',
        '*.egg-info', 'eggs',
        'logs/', '.log',
        'test_', 'tests/', '*test*.py',
        '.env', '.venv', 'venv',
    ]
    
    for pattern in skip_patterns:
        if pattern in filepath:
            return False
    
    # Only include Python, JSON, TXT, yaml files and key config
    valid_extensions = {
        '.py', '.json', '.txt', '.yml', '.yaml',
        '.md', '.sh', '.bat', '.ps1',
        '.ini', '.cfg', '.conf',
    }
    
    _, ext = os.path.splitext(filepath)
    return ext in valid_extensions or filepath.endswith(('.gitkeep', 'Procfile'))

def create_deployment_zip(src_dir, output_path):
    """Create optimized ZIP for deployment."""
    
    if os.path.exists(output_path):
        os.remove(output_path)
    
    total_size = 0
    file_count = 0
    
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(src_dir):
            # Skip unnecessary directories
            dirs[:] = [d for d in dirs if d not in {
                '__pycache__', '.git', 'dist', 'build', 'node_modules',
                'logs', '.pytest_cache', '.tox', '.venv', 'venv',
                'htmlcov', 'eggs', '__MACOSX'
            }]
            
            for file in files:
                file_path = os.path.join(root, file)
                
                # Skip test files except test_navigation_mode.py
                if ('test_' in file or '/tests/' in file_path) and 'navigation' not in file:
                    continue
                
                if should_include(file_path):
                    arcname = os.path.relpath(file_path, os.path.dirname(src_dir))
                    try:
                        zf.write(file_path, arcname)
                        file_count += 1
                        total_size += os.path.getsize(file_path)
                    except Exception as e:
                        print(f'⚠ Skipped {file_path}: {e}')
    
    final_size = os.path.getsize(output_path)
    final_size_mb = final_size / 1024 / 1024
    
    return final_size, final_size_mb, file_count, total_size / 1024 / 1024

# Create optimized deployment
src_path = 'jarvis-platform/apps/bill-core'
zip_path = 'bill-core-deployment.zip'

print('Creating optimized Beanstalk deployment package...')
print()

file_size, file_size_mb, file_count, uncompressed_mb = create_deployment_zip(src_path, zip_path)

print(f'✓ Created {zip_path}')
print(f'  Files included: {file_count}')
print(f'  Compressed size: {file_size_mb:.2f} MB')
print(f'  Uncompressed size: {uncompressed_mb:.2f} MB')
print(f'  Compression ratio: {(1 - file_size_mb/uncompressed_mb)*100:.1f}%')
print()

if file_size_mb > 500:
    print(f'❌ ERROR: {file_size_mb:.2f} MB exceeds 500 MB Beanstalk limit!')
    sys.exit(1)
else:
    print(f'✓ Size {file_size_mb:.2f} MB is within 500 MB Beanstalk limit')
    print()
    print('Ready to upload to AWS Beanstalk!')
    print('Upload steps:')
    print('  1. Go to AWS Elastic Beanstalk Console')
    print('  2. Select your Bill Core environment')
    print('  3. Click "Upload and Deploy"')
    print('  4. Select bill-core-deployment.zip')
    print('  5. Click "Deploy"')
    print()
    print(f'Location: {os.path.abspath(zip_path)}')
