#!/usr/bin/env python3
"""
Meta API Credentials Validator

Checks that:
1. ~/.meta_credentials exists and contains META_ACCESS_TOKEN
2. Token is valid (calls /me)
3. Token has required permissions
4. Ad account is accessible
5. Page is accessible

Usage: python3 scripts/meta_auth_check.py brands/[brand-slug].md

Output: JSON to stdout (success) or error message + exit code 1 (failure)
"""

import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

# Parse arguments
if len(sys.argv) < 2:
    print("Usage: python3 scripts/meta_auth_check.py brands/[brand-slug].md", file=sys.stderr)
    sys.exit(1)

brand_file = sys.argv[1]

# ============================================================================
# 1. Load brand context file and extract account/page IDs
# ============================================================================

if not os.path.exists(brand_file):
    print(f"Error: Brand file not found: {brand_file}", file=sys.stderr)
    sys.exit(1)

with open(brand_file, 'r') as f:
    content = f.read()

# Extract YAML frontmatter
if not content.startswith('---'):
    print(f"Error: Brand file must start with YAML frontmatter (---)", file=sys.stderr)
    sys.exit(1)

lines = content.split('\n')
frontmatter_end = None
for i in range(1, len(lines)):
    if lines[i].strip() == '---':
        frontmatter_end = i
        break

if frontmatter_end is None:
    print(f"Error: Brand file frontmatter not properly closed", file=sys.stderr)
    sys.exit(1)

frontmatter = '\n'.join(lines[1:frontmatter_end])

# Parse YAML-like frontmatter (simple key: value)
account_id = None
page_id = None
brand_name = None

for line in frontmatter.split('\n'):
    if ':' in line:
        key, val = line.split(':', 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")

        if key == 'meta_account_id':
            account_id = val
        elif key == 'meta_page_id':
            page_id = val
        elif key == 'brand':
            brand_name = val

if not account_id or not page_id or not brand_name:
    print(f"Error: Brand file missing required fields: meta_account_id, meta_page_id, brand", file=sys.stderr)
    sys.exit(1)

# ============================================================================
# 2. Load credentials from ~/.meta_credentials
# ============================================================================

creds_path = os.path.expanduser('~/.meta_credentials')
if not os.path.exists(creds_path):
    print(json.dumps({
        "valid": False,
        "error": f"Credentials file not found: {creds_path}",
        "help": "See META_SETUP.md Step 6 to create ~/.meta_credentials"
    }))
    sys.exit(1)

token = None
try:
    with open(creds_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('META_ACCESS_TOKEN='):
                token = line.split('=', 1)[1]
                break
except Exception as e:
    print(json.dumps({
        "valid": False,
        "error": f"Could not read credentials file: {e}"
    }))
    sys.exit(1)

if not token:
    print(json.dumps({
        "valid": False,
        "error": "META_ACCESS_TOKEN not found in ~/.meta_credentials"
    }))
    sys.exit(1)

# ============================================================================
# 3. Helper function for Graph API calls
# ============================================================================

def graph_api_call(endpoint, fields=''):
    """
    Call the Meta Graph API. Returns parsed JSON or None on error.
    Sets 'error_message' in result on failure.
    """
    url = f"https://graph.instagram.com/v18.0/{endpoint}?access_token={token}"
    if fields:
        url += f"&fields={fields}"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data
    except urllib.error.HTTPError as e:
        try:
            error_data = json.loads(e.read().decode('utf-8'))
            error_msg = error_data.get('error', {})
            error_code = error_msg.get('code', 'unknown')
            error_message = error_msg.get('message', str(e))
            return {
                'error': True,
                'error_code': error_code,
                'error_message': error_message
            }
        except:
            return {
                'error': True,
                'error_code': e.code,
                'error_message': str(e)
            }
    except Exception as e:
        return {
            'error': True,
            'error_message': str(e)
        }

# ============================================================================
# 4. Validate token
# ============================================================================

result = graph_api_call('me', fields='id,name')
if result.get('error'):
    error_code = result.get('error_code')
    if error_code == 190:
        error = "Token expired (error code 190)"
        help_msg = "See META_SETUP.md Step 8 to refresh your token"
    else:
        error = f"Token invalid (error code {error_code}): {result.get('error_message')}"
        help_msg = "Verify your token in ~/.meta_credentials"

    print(json.dumps({
        "valid": False,
        "error": error,
        "help": help_msg
    }))
    sys.exit(1)

token_user = result.get('name', 'Unknown')
token_user_id = result.get('id', 'unknown')

# ============================================================================
# 5. Check permissions
# ============================================================================

perms_result = graph_api_call('me', fields='permissions')
permissions = []
missing_permissions = []

required_perms = [
    'ads_read',
    'ads_management',
    'read_insights',
    'pages_read_engagement',
    'pages_show_list'
]

if perms_result.get('error'):
    missing_permissions = required_perms
    warnings = [f"Could not verify permissions: {perms_result.get('error_message')}"]
else:
    perm_data = perms_result.get('permissions', [])
    for p in perm_data:
        if p.get('status') == 'granted':
            permissions.append(p.get('permission'))

    for req_perm in required_perms:
        if req_perm not in permissions:
            missing_permissions.append(req_perm)

# ============================================================================
# 6. Validate ad account access
# ============================================================================

ad_account_name = None
ad_account_result = graph_api_call(f'act_{account_id}', fields='id,name')
if ad_account_result.get('error'):
    error_code = ad_account_result.get('error_code')
    error_msg = ad_account_result.get('error_message')
    print(json.dumps({
        "valid": False,
        "error": f"Cannot access ad account {account_id} (error {error_code}): {error_msg}",
        "help": "Verify meta_account_id in your brand file and your user role in Meta Business Manager"
    }))
    sys.exit(1)

ad_account_name = ad_account_result.get('name', account_id)

# ============================================================================
# 7. Validate page access
# ============================================================================

page_name = None
page_result = graph_api_call(page_id, fields='id,name')
if page_result.get('error'):
    error_code = page_result.get('error_code')
    error_msg = page_result.get('error_message')
    print(json.dumps({
        "valid": False,
        "error": f"Cannot access page {page_id} (error {error_code}): {error_msg}",
        "help": "Verify meta_page_id in your brand file and that you have access to this page"
    }))
    sys.exit(1)

page_name = page_result.get('name', page_id)

# ============================================================================
# 8. Output success
# ============================================================================

output = {
    "valid": True,
    "token_user": token_user,
    "ad_account": f"{account_id} — {ad_account_name}",
    "page": f"{page_id} — {page_name}",
    "permissions": sorted(permissions),
    "missing_permissions": sorted(missing_permissions) if missing_permissions else [],
    "warnings": [] if missing_permissions == [] else ["Some permissions may be missing. This may cause analysis failures."]
}

print(json.dumps(output, indent=2))
sys.exit(0)
