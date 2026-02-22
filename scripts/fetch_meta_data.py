#!/usr/bin/env python3
"""
Meta Data Fetcher

Pulls campaign, ad set, ad, and organic data from Meta Graph API.
Stores raw JSON files in social-reviews/[brand-slug]/.cache/raw/

Usage:
  python3 scripts/fetch_meta_data.py brands/[brand-slug].md [--days 30]

Output:
  JSON manifest to stdout with file paths
  Raw data JSON files to .cache/raw/[YYYY-MM-DD]-[type].json
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta
import time
import argparse
from pathlib import Path

# ============================================================================
# Parse arguments
# ============================================================================

parser = argparse.ArgumentParser(description='Fetch Meta social data for a brand')
parser.add_argument('brand_file', help='Path to brand context file (brands/[slug].md)')
parser.add_argument('--days', type=int, default=30, help='Days of data to fetch (default: 30)')
parser.add_argument('--since', help='Start date (YYYY-MM-DD), overrides --days')
parser.add_argument('--until', help='End date (YYYY-MM-DD), defaults to today')

args = parser.parse_args()

# ============================================================================
# Load brand context
# ============================================================================

if not os.path.exists(args.brand_file):
    print(json.dumps({"error": f"Brand file not found: {args.brand_file}"}))
    sys.exit(1)

with open(args.brand_file, 'r') as f:
    content = f.read()

if not content.startswith('---'):
    print(json.dumps({"error": "Brand file must start with YAML frontmatter"}))
    sys.exit(1)

lines = content.split('\n')
frontmatter_end = None
for i in range(1, len(lines)):
    if lines[i].strip() == '---':
        frontmatter_end = i
        break

frontmatter = '\n'.join(lines[1:frontmatter_end])

account_id = None
page_id = None
brand_name = None
slug = None

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
        elif key == 'slug':
            slug = val

if not all([account_id, page_id, brand_name, slug]):
    print(json.dumps({"error": "Brand file missing required fields"}))
    sys.exit(1)

# ============================================================================
# Load credentials
# ============================================================================

creds_path = os.path.expanduser('~/.meta_credentials')
if not os.path.exists(creds_path):
    print(json.dumps({"error": f"Credentials file not found: {creds_path}"}))
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
    print(json.dumps({"error": f"Could not read credentials: {e}"}))
    sys.exit(1)

if not token:
    print(json.dumps({"error": "META_ACCESS_TOKEN not found in credentials"}))
    sys.exit(1)

# ============================================================================
# Calculate date range
# ============================================================================

if args.until:
    until = datetime.strptime(args.until, '%Y-%m-%d').date()
else:
    until = datetime.now().date()

if args.since:
    since = datetime.strptime(args.since, '%Y-%m-%d').date()
else:
    since = until - timedelta(days=args.days)

date_range = {"since": since.isoformat(), "until": until.isoformat()}

# ============================================================================
# Create output directory
# ============================================================================

output_dir = f"social-reviews/{slug}/.cache/raw"
os.makedirs(output_dir, exist_ok=True)

today = datetime.now().strftime('%Y-%m-%d')
cache_base = f"{output_dir}/{today}"

# ============================================================================
# Graph API helper
# ============================================================================

def graph_api_call(endpoint, fields='', params=None, paginate=False):
    """
    Call Graph API. Returns dict (single result) or list (paginated).
    Handles pagination automatically if paginate=True.
    """
    base_url = f"https://graph.instagram.com/v18.0/{endpoint}"

    url = base_url + f"?access_token={token}"
    if fields:
        url += f"&fields={fields}"
    if params:
        for k, v in params.items():
            url += f"&{k}={v}"

    all_data = []
    page_count = 0

    while url:
        try:
            time.sleep(0.5)  # Rate limiting
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))

            if data.get('error'):
                error_msg = data['error'].get('message', 'Unknown error')
                return {"error": True, "error_message": error_msg}

            if paginate:
                all_data.extend(data.get('data', []))
                page_count += 1
                url = data.get('paging', {}).get('cursors', {}).get('after')
                if url:
                    url = f"{base_url}?access_token={token}&after={url}"
                    if fields:
                        url += f"&fields={fields}"
                    if params:
                        for k, v in params.items():
                            url += f"&{k}={v}"
            else:
                return data

        except urllib.error.HTTPError as e:
            try:
                error_data = json.loads(e.read().decode('utf-8'))
                return {"error": True, "error_message": error_data.get('error', {}).get('message', str(e))}
            except:
                return {"error": True, "error_message": str(e)}
        except Exception as e:
            return {"error": True, "error_message": str(e)}

    if paginate:
        return {"data": all_data, "page_count": page_count}
    return {}

# ============================================================================
# 1. Fetch account overview
# ============================================================================

account_data = graph_api_call(f'act_{account_id}', fields='id,name,account_status,currency,timezone_name,balance,spend_cap,amount_spent')
if account_data.get('error'):
    print(json.dumps({"error": f"Failed to fetch account data: {account_data.get('error_message')}"}))
    sys.exit(1)

account_file = f"{cache_base}-account.json"
with open(account_file, 'w') as f:
    json.dump({
        "fetched_at": datetime.now().isoformat(),
        "account_id": account_id,
        "brand_slug": slug,
        "data": account_data
    }, f, indent=2)

# ============================================================================
# 2. Fetch campaigns
# ============================================================================

campaign_fields = 'id,name,status,objective,daily_budget,lifetime_budget,created_time,updated_time,insights.date_preset(last_30d){spend,impressions,reach,clicks,cpc,cpm,ctr,actions,cost_per_action_type,purchase_roas,video_p25_watched_actions,video_p50_watched_actions,video_p75_watched_actions,video_p100_watched_actions}'

campaigns_data = graph_api_call(f'act_{account_id}/campaigns', fields=campaign_fields, paginate=True)
if campaigns_data.get('error'):
    print(json.dumps({"error": f"Failed to fetch campaigns: {campaigns_data.get('error_message')}"}))
    sys.exit(1)

campaigns_file = f"{cache_base}-campaigns.json"
with open(campaigns_file, 'w') as f:
    json.dump({
        "fetched_at": datetime.now().isoformat(),
        "date_range": date_range,
        "account_id": account_id,
        "brand_slug": slug,
        "data": campaigns_data.get('data', [])
    }, f, indent=2)

# ============================================================================
# 3. Fetch ad sets with breakdown
# ============================================================================

adset_fields = 'id,name,campaign_id,status,targeting,optimization_goal,billing_event,daily_budget,insights.date_preset(last_30d){spend,impressions,reach,clicks,cpc,ctr,frequency,actions,cost_per_action_type}'

adsets_data = graph_api_call(f'act_{account_id}/adsets', fields=adset_fields, paginate=True)
if adsets_data.get('error'):
    print(json.dumps({"error": f"Failed to fetch ad sets: {adsets_data.get('error_message')}"}))
    sys.exit(1)

adsets_file = f"{cache_base}-adsets.json"
with open(adsets_file, 'w') as f:
    json.dump({
        "fetched_at": datetime.now().isoformat(),
        "date_range": date_range,
        "account_id": account_id,
        "brand_slug": slug,
        "data": adsets_data.get('data', [])
    }, f, indent=2)

# ============================================================================
# 4. Fetch ads with creative details
# ============================================================================

ads_fields = 'id,name,adset_id,campaign_id,status,created_time,creative{id,name,title,body,image_url,image_hash,video_id,call_to_action_type,object_story_spec},insights.date_preset(last_30d){spend,impressions,clicks,ctr,cpc,frequency,actions,cost_per_action_type,video_play_actions,video_p25_watched_actions,video_p50_watched_actions,video_p75_watched_actions,video_p100_watched_actions,video_avg_time_watched_actions}'

ads_data = graph_api_call(f'act_{account_id}/ads', fields=ads_fields, paginate=True)
if ads_data.get('error'):
    print(json.dumps({"error": f"Failed to fetch ads: {ads_data.get('error_message')}"}))
    sys.exit(1)

ads_file = f"{cache_base}-ads.json"
with open(ads_file, 'w') as f:
    json.dump({
        "fetched_at": datetime.now().isoformat(),
        "date_range": date_range,
        "account_id": account_id,
        "brand_slug": slug,
        "data": ads_data.get('data', [])
    }, f, indent=2)

# ============================================================================
# 5. Fetch organic page posts and insights
# ============================================================================

# Page-level insights
page_insights = graph_api_call(page_id, fields='id,name,insights.metric(page_impressions,page_reach,page_engaged_users,page_fan_adds,page_post_engagements,page_views_total).period(day).date_preset(last_30d){value,title}')
if page_insights.get('error'):
    page_insights = {}

# Get recent posts
posts_fields = 'id,message,story,type,created_time,full_picture,permalink_url,insights.metric(post_impressions,post_reach,post_engaged_users,post_clicks,post_reactions_by_type_total,post_video_views,post_video_avg_time_watched,post_video_view_time_by_cropped_content_data).period(lifetime){value,title}'

posts_data = graph_api_call(f'{page_id}/posts', fields=posts_fields, paginate=True)
if posts_data.get('error'):
    posts_data = {"data": []}

organic_file = f"{cache_base}-organic.json"
with open(organic_file, 'w') as f:
    json.dump({
        "fetched_at": datetime.now().isoformat(),
        "page_id": page_id,
        "brand_slug": slug,
        "page_insights": page_insights,
        "posts": posts_data.get('data', [])
    }, f, indent=2)

# ============================================================================
# Output manifest
# ============================================================================

manifest = {
    "brand_slug": slug,
    "brand_name": brand_name,
    "date_range": date_range,
    "account_id": account_id,
    "page_id": page_id,
    "fetched_at": datetime.now().isoformat(),
    "files": {
        "account": account_file,
        "campaigns": campaigns_file,
        "adsets": adsets_file,
        "ads": ads_file,
        "organic": organic_file
    }
}

print(json.dumps(manifest, indent=2))
sys.exit(0)
