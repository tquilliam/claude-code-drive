# Meta API Setup Guide

This guide walks you through setting up Meta API access for the social media agent. You'll need this to analyze paid campaign performance and organic post metrics.

## What You Need

- Meta Business Manager account (you have this)
- A Facebook Page for your brand (you have this)
- A Facebook Ad Account (you have this)
- A web browser for authentication

---

## Step 1: Create a Meta App

1. Go to [developers.facebook.com/apps](https://developers.facebook.com/apps/)
2. Click **"Create App"** or **"My Apps"** → **"Create App"**
3. Choose **Business** as the app type
4. Fill in the form:
   - **App Name**: e.g., "Victory Blinds Analytics" or "[YourBrand] Social Agent"
   - **Contact Email**: Your business email
   - **App Purpose**: Select "Manage business"
   - **Business Account**: Select your Business Manager account
5. Click **"Create App"**

You now have an **App ID**. Make note of it.

---

## Step 2: Add the Marketing API

1. In your new app dashboard, click **"Add Product"**
2. Find **"Marketing API"** and click **"Set Up"**
3. Navigate to **Settings** → **Basic** in the left sidebar
4. Note your **App ID** and **App Secret** (you'll need these to generate tokens)

---

## Step 3: Generate a Long-Lived Page Access Token

This token gives the agent permission to read ad campaign and page data.

### Option A: Using the Graph API Explorer (Recommended)

1. Go to [developers.facebook.com/tools/explorer](https://developers.facebook.com/tools/explorer)
2. In the top dropdown, select your app (the one you just created)
3. In the "Get Token" dropdown, select **"Get Page Access Token"**
   - A dialog will appear asking you to log in and authorize your app
   - Select your Page and click **"Generate"**
4. You now have a **short-lived token** (valid for 1 hour)

### Exchange for a Long-Lived Token

Short-lived tokens aren't useful for scheduled analysis. You need a long-lived token (valid ~60 days).

1. Go to [developers.facebook.com/tools/accesstoken](https://developers.facebook.com/tools/accesstoken)
2. Paste your short-lived token into the box and click **"Debug"**
3. Scroll down to find the **"Exchange for long-lived token"** section
4. Click the blue button
5. Copy the new token (this is your **long-lived token**)

**Important:** Long-lived tokens last ~60 days. Set a calendar reminder to refresh it before it expires (see "Token Refresh" below).

---

## Step 4: Grant Required Permissions

The token above needs additional permissions to read campaign and organic data. These are configured in your app settings.

In your app dashboard on [developers.facebook.com/apps](https://developers.facebook.com/apps/), navigate to **Settings** → **Roles** → **Ad Accounts**:

Ensure your ad account has the following user roles (ask your Meta Business Manager admin if needed):
- **Admin** or **Analyst** (to read campaign insights)

Required API permissions (auto-granted when you generate the token with the right scope):
- `ads_read` — read campaign and ad set data
- `ads_management` — read creative details
- `read_insights` — read performance metrics
- `pages_read_engagement` — read organic page post data
- `pages_show_list` — list pages

If you encounter permission errors later (error code 200), return here and verify these scopes were included when you generated the token.

---

## Step 5: Find Your Account IDs

The agent needs two pieces of information from your Meta Business setup:

### Ad Account ID

1. Go to [facebook.com/ads/manager](https://facebook.com/ads/manager)
2. Look at the URL: `https://facebook.com/ads/manager?act=XXXXXXXXX`
3. The number after `act=` is your **Ad Account ID** (format: `act_123456789`)

### Page ID

1. Go to [facebook.com/settings](https://facebook.com/settings) (your profile settings) or your Page settings
2. Open [business.facebook.com](https://business.facebook.com)
3. In the left sidebar, go to **Pages**
4. Select your brand's Page
5. In the page URL or in the page settings, find the **Page ID** (a long number like `987654321`)

Make note of both IDs.

---

## Step 6: Store Credentials Locally

Create a credentials file **outside this repository** to keep tokens safe:

### macOS / Linux

```bash
cat > ~/.meta_credentials << 'EOF'
META_ACCESS_TOKEN=your_long_lived_token_here
META_APP_ID=your_app_id_here
META_APP_SECRET=your_app_secret_here
EOF

chmod 600 ~/.meta_credentials
```

**Replace:**
- `your_long_lived_token_here` with the long-lived token from Step 3
- `your_app_id_here` with your App ID from Step 2
- `your_app_secret_here` with your App Secret from Step 2

### Windows (PowerShell)

```powershell
@"
META_ACCESS_TOKEN=your_long_lived_token_here
META_APP_ID=your_app_id_here
META_APP_SECRET=your_app_secret_here
"@ | Set-Content -Path "$env:USERPROFILE\.meta_credentials" -Force
```

**Important:** This file is **not** in the git repo. It will never be committed. Do not share it with anyone or paste it into Slack.

---

## Step 7: Verify Your Setup

Run the auth check script:

```bash
python3 scripts/meta_auth_check.py brands/victory-blinds.md
```

**Success output:**
```json
{
  "valid": true,
  "token_user": "Your Name",
  "ad_account": "ACT_123456789 — Victory Blinds",
  "page": "987654321 — Victory Blinds",
  "permissions": ["ads_read", "ads_management", "read_insights", "pages_read_engagement"],
  "missing_permissions": [],
  "warnings": []
}
```

**If you see an error:**
- **"Token expired (code 190)"** → See "Token Refresh" below
- **"Missing permission: ads_read"** → Return to Step 4 and verify your token has the right scopes
- **"Cannot access ad account"** → Verify your Ad Account ID in Step 5 and your user role in Step 4

---

## Step 8: Add Brand Information

The social agent reads brand context from `brands/[brand-slug].md` files. Each brand needs:
- `meta_account_id` — from Step 5
- `meta_page_id` — from Step 5
- Brand narrative (target audience, tone, emotional drivers, etc.)

See `brands/victory-blinds.md` for the template.

---

## Token Refresh

Long-lived tokens expire after ~60 days. When your token expires:

### 1. Generate a New Token

Follow **Step 3** (above) to generate a new long-lived token from your app.

### 2. Update Credentials

Edit `~/.meta_credentials`:

```bash
nano ~/.meta_credentials
# or
vim ~/.meta_credentials
```

Replace the old `META_ACCESS_TOKEN` value with your new token.

### 3. Verify

```bash
python3 scripts/meta_auth_check.py brands/victory-blinds.md
```

---

## Troubleshooting

### Error Code 190 (Token Expired)

Your token is no longer valid. Generate a new one (Step 3 → Exchange for long-lived token).

### Error Code 200 (Missing Permission)

The token doesn't have the required scope. Go back to Step 3 and ensure you selected the right permissions when generating the token. You may need to revoke the old token and generate a new one with the full scope.

### Error Code 4 (Rate Limit)

You've hit Meta's API rate limit. The social agent will pause and retry automatically. If you see this repeatedly, you may be running too many concurrent analyses. Wait 1 hour and try again.

### Error: "Cannot read [page_id]"

Verify:
1. The Page ID is correct (Step 5)
2. Your token is a **Page access token** (not a User token)
3. You have admin or editor access to the Page in Meta Business Manager

### Error: "No campaigns found"

Verify:
1. Your Ad Account ID is correct (Step 5)
2. You have active campaigns in your ad account
3. The date range you're analyzing has data (default is last 30 days)

---

## Security Notes

- **Never commit** `~/.meta_credentials` to git
- **Never paste** your token into code, Slack, or anywhere public
- **Never share** your `APP_SECRET` with anyone
- If you ever accidentally expose a token, regenerate it immediately in Meta's app settings
- Tokens stored in `~/.meta_credentials` are readable only by you (chmod 600)

---

## Next Steps

Once you've verified your setup:

1. Fill in `brands/victory-blinds.md` with your brand information
2. Run `/social-review victory-blinds` to start analyzing your campaigns
3. Add more brands by creating additional `brands/[brand-slug].md` files
