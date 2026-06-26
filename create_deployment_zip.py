#!/usr/bin/env python3
"""Create deployment ZIP file for Beanstalk."""

import zipfile
import os

def zipdir(path, ziph):
    """Recursively add files from path to zip archive."""
    for root, dirs, files in os.walk(path):
        for file in files:
            file_path = os.path.join(root, file)
            arcname = os.path.relpath(file_path, os.path.dirname(path))
            ziph.write(file_path, arcname)

# Remove old file if it exists
zip_path = 'bill-core-deployment.zip'
if os.path.exists(zip_path):
    os.remove(zip_path)
    print(f'Removed old {zip_path}')

# Create the ZIP file
src_path = 'jarvis-platform/apps/bill-core'
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    zipdir(src_path, zf)

file_size = os.path.getsize(zip_path)
file_size_mb = file_size / 1024 / 1024

print(f'✓ Created {zip_path}')
print(f'✓ File size: {file_size_mb:.2f} MB')
print(f'✓ Location: {os.path.abspath(zip_path)}')
print()
print('Ready to upload to AWS Beanstalk!')
print('Upload steps:')
print('  1. Go to AWS Elastic Beanstalk console')
print('  2. Select your Bill Core environment')
print('  3. Click "Upload and Deploy"')
print('  4. Select bill-core-deployment.zip')
print('  5. Click "Deploy"')
