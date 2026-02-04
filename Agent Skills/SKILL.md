---
name: picobrew-server
version: 1.1.0
description: Connect to a local PicoBrew server to monitor fermentations, view brew sessions, manage recipes, and save new recipes for Pico, Zymatic, and Z-Series devices.
homepage: https://github.com/chiefwigms/picobrew_pico
metadata:
  category: homebrewing
  emoji: 🍺
  requires_confirmation:
    - save_recipe
    - delete_recipe
---

# PicoBrew Server Skill

Control and monitor your PicoBrew brewing system through your local server.

## Configuration

Before using this skill, configure your server connection:

```json
{
  "picobrew_server_url": "http://localhost:8181"
}
```

Save this to `~/.config/picobrew/config.json` or set the environment variable `PICOBREW_SERVER_URL`.

**Base URL:** `{picobrew_server_url}` (default: `http://localhost:8181`)

---

## Windows PowerShell Usage

⚠️ **IMPORTANT FOR WINDOWS**: On Windows PowerShell, `curl` is an alias for `Invoke-WebRequest` and doesn't work like Unix curl. Use `Invoke-RestMethod` instead.

**GET requests (simple):**
```powershell
Invoke-RestMethod -Uri "http://localhost:8181/API/Agent/status"
```

**POST requests with JSON body:**
```powershell
Invoke-RestMethod -Uri "http://localhost:8181/API/RecipeCrafter/createFromTemplate" -Method POST -ContentType "application/json" -Body '{"template_id":"american_ipa","name":"My IPA","device_type":"zymatic","save":false}'
```

**⚠️ CRITICAL: Avoid PowerShell variables in agent commands!**
- Do NOT use `$variable = ...` syntax - the `$` gets stripped
- Use single-line commands with inline JSON
- Always use single quotes around JSON body: `-Body '{"key":"value"}'`

---

## Complete PowerShell Examples (Copy-Paste Ready)

These are complete, working commands. Copy them exactly as shown.

### Check server status
```powershell
Invoke-RestMethod -Uri "http://localhost:8181/API/Agent/status"
```

### Get active fermentations
```powershell
Invoke-RestMethod -Uri "http://localhost:8181/API/Agent/ferm/active"
```

### Get recipe templates
```powershell
Invoke-RestMethod -Uri "http://localhost:8181/API/RecipeCrafter/getTemplates"
```

### List Zymatic recipes
```powershell
Invoke-RestMethod -Uri "http://localhost:8181/API/Agent/recipes/zymatic"
```

### Create recipe from template (preview only - save:false)

Use this to preview a recipe from a built-in template like "american_ipa", "stout", etc.

**⚠️ AGENTS: Use the GET version to avoid JSON escaping issues!**

```powershell
Invoke-RestMethod -Uri "http://localhost:8181/API/RecipeCrafter/createFromTemplate?template_id=american_ipa&name=Soft+Launch+IPA&device_type=zymatic&save=false"
```

### Create recipe from template (SAVE to device - save:true)

**⚠️ AGENTS: Use the GET version to avoid JSON escaping issues!**

```powershell
Invoke-RestMethod -Uri "http://localhost:8181/API/RecipeCrafter/createFromTemplate?template_id=american_ipa&name=Soft+Launch+IPA&device_type=zymatic&save=true"
```

### Create custom recipe (preview)

**⚠️ AGENTS: Use the GET version to avoid JSON escaping issues!**

**GET version (recommended for agents):**
```powershell
Invoke-RestMethod -Uri "http://localhost:8181/API/RecipeCrafter/createRecipe?name=Tropical+Soft+Haze+IPA&device_type=zymatic&abv=6.5&ibu=50&og=1.062&boil_time=60&mash=Sacch+Rest:152:45,Mash+Out:170:10&hops=30:Adjunct1,10:Adjunct2,5:Adjunct3,0:Adjunct4&notes=Dry+hop+Day+3-4+with+Citra+and+Mosaic&save=false"
```

**URL Parameter format:**
- `name` - Recipe name (use `+` for spaces)
- `device_type` - `pico`, `zymatic`, or `zseries`
- `abv`, `ibu`, `og` - Beer stats
- `boil_time` - Boil time in minutes
- `mash` - Format: `StepName:TempF:Minutes,StepName:TempF:Minutes`
  - Example: `Sacch+Rest:152:45,Mash+Out:170:10`
- `hops` - Format: `Minutes:Location,Minutes:Location`
  - Locations: `Adjunct1`, `Adjunct2`, `Adjunct3`, `Adjunct4`
  - Example: `60:Adjunct1,15:Adjunct2,5:Adjunct3,0:Adjunct4`
- `notes` - Recipe notes (use `+` for spaces, avoid special characters or URL-encode them)
  - Example: `Dry+hop+Day+3-4+with+Citra+and+Mosaic`
- `save` - `false` to preview, `true` to save

**POST version (if you need it):**
```bash
curl -X POST {picobrew_server_url}/API/RecipeCrafter/createRecipe \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Custom Brew",
    "device_type": "zymatic",
    "abv": 5.5,
    "ibu": 45,
    "notes": "Dry hop Day 3-4 with Citra and Mosaic",
    "mash_steps": [
      {"name": "Sacch Rest", "temp_f": 152, "time_min": 60}
    ],
    "hop_additions": [
      {"time_min": 60, "location": "Adjunct1"},
      {"time_min": 15, "location": "Adjunct2"},
      {"time_min": 5, "location": "Adjunct3"},
      {"time_min": 0, "location": "Adjunct4"}
    ],
    "boil_time_min": 60,
    "save": true
  }'
```

⚠️ **CONFIRMATION REQUIRED**: Only set `save=true` after user confirms.

---

## Agent API Endpoints

All endpoints below return JSON data. Use these for automation and agent access.

### Server Status

```
GET {picobrew_server_url}/API/Agent/status
```

Returns:
```json
{
  "success": true,
  "server": "running",
  "timestamp": "2026-02-02T12:00:00",
  "active_sessions": {
    "brew": 0,
    "ferm": 2,
    "still": 0,
    "tilt": 1,
    "iSpindel": 0
  }
}
```

---

## Devices

### List all connected devices

```
GET {picobrew_server_url}/API/Agent/devices
```

Returns:
```json
{
  "success": true,
  "count": 3,
  "devices": [
    {"uid": "FERM001", "alias": "Garage Fermenter", "type": "ferm", "active": true},
    {"uid": "RED", "alias": "Red Tilt", "type": "tilt", "active": true}
  ]
}
```

---

## Fermentation Sessions

### Get active fermentations (what's fermenting now)

```bash
curl {picobrew_server_url}/API/Agent/ferm/active
```

Returns:
```json
{
  "success": true,
  "count": 2,
  "sessions": [
    {
      "uid": "FERM001",
      "alias": "Garage Fermenter",
      "active": true,
      "start_date": "2026-02-01T10:30:00",
      "target_abv": 5.5,
      "target_pressure_psi": 10.0,
      "current_temp_f": 68.5,
      "current_pressure_psi": 9.8,
      "voltage": "12.1V",
      "data_points": 150
    }
  ]
}
```

### Get fermentation history

```bash
curl "{picobrew_server_url}/API/Agent/ferm/history?limit=10&offset=0"
```

Query parameters:
- `limit` - Max results (default: 10, max: 50)
- `offset` - Pagination offset (default: 0)

Returns:
```json
{
  "success": true,
  "count": 5,
  "offset": 0,
  "limit": 10,
  "sessions": [
    {
      "uid": "FERM001",
      "filename": "20260201_103000#FERM001.json",
      "alias": "Garage Fermenter",
      "name": "FERM001",
      "start_date": "2026-02-01T10:30:00",
      "end_date": "2026-02-07T15:45:00",
      "duration_hours": 149.25
    }
  ]
}
```

---

## Brew Sessions

### Get active brews

```bash
curl {picobrew_server_url}/API/Agent/brew/active
```

Returns:
```json
{
  "success": true,
  "count": 1,
  "sessions": [
    {
      "uid": "abc123",
      "alias": "Living Room Zymatic",
      "name": "My IPA",
      "active": true,
      "session_type": "zymatic",
      "start_date": "2026-02-02T08:00:00",
      "step": "Mash Step 2"
    }
  ]
}
```

### Get brew history

```bash
curl "{picobrew_server_url}/API/Agent/brew/history?limit=10"
```

---

## Tilt Hydrometer Sessions

### Get active Tilt sessions

```bash
curl {picobrew_server_url}/API/Agent/tilt/active
```

Returns:
```json
{
  "success": true,
  "count": 1,
  "sessions": [
    {
      "uid": "RED",
      "color": "Red",
      "alias": "Red Tilt",
      "active": true,
      "start_date": "2026-02-01T10:30:00",
      "current_gravity": 1.045,
      "current_temp_f": 66.2,
      "data_points": 288
    }
  ]
}
```

### Get Tilt history

```bash
curl "{picobrew_server_url}/API/Agent/tilt/history?limit=10"
```

---

## iSpindel Sessions

### Get active iSpindel sessions

```bash
curl {picobrew_server_url}/API/Agent/iSpindel/active
```

Returns:
```json
{
  "success": true,
  "count": 1,
  "sessions": [
    {
      "uid": "iSpindel001",
      "alias": "Basement iSpindel",
      "active": true,
      "current_gravity": 1.048,
      "current_temp_c": 19.5,
      "battery_voltage": 4.1
    }
  ]
}
```

---

## Recipes

### List recipes for a device

```bash
curl {picobrew_server_url}/API/Agent/recipes/zymatic
curl {picobrew_server_url}/API/Agent/recipes/pico
curl {picobrew_server_url}/API/Agent/recipes/zseries
```

Returns:
```json
{
  "success": true,
  "device_type": "zymatic",
  "count": 5,
  "recipes": [
    {"filename": "My_IPA.json", "id": "abc123", "name": "My IPA", "abv": 6.5, "ibu": 65},
    {"filename": "Pale_Ale.json", "id": "def456", "name": "Pale Ale", "abv": 5.2, "ibu": 35}
  ]
}
```

### Get full recipe details

```bash
curl {picobrew_server_url}/API/Agent/recipes/zymatic/My_IPA.json
```

Returns the complete recipe JSON with all steps, temperatures, and settings.

---

## Recipe Crafter API

### ⚠️ WHICH ENDPOINT SHOULD I USE?

| I have... | Use this endpoint | Method | Key parameter |
|-----------|-------------------|--------|---------------|
| A template name (IPA, Stout, etc) | `createFromTemplate` | **GET** | `?template_id=...&save=false` |
| Custom mash/hop parameters | `createRecipe` | **GET** | `?name=...&mash=...&hops=...` |
| A PicoBrew JSON file | `uploadRecipe` | POST | `recipe_base64` (base64-encoded JSON) |

**⚠️ AGENTS: The `$` character gets stripped from PowerShell commands!**
- Do NOT use `$variable = ...` syntax
- Use the endpoints above with base64 encoding to avoid ALL escaping issues


### Get recipe templates

```bash
curl {picobrew_server_url}/API/RecipeCrafter/getTemplates
```

### Search online recipes (BrewersFriend)

```bash
curl "{picobrew_server_url}/API/RecipeCrafter/searchRecipes?query=IPA&limit=10"
```


### Create recipe from template

**GET version (recommended for agents - no JSON escaping):**
```bash
curl "{picobrew_server_url}/API/RecipeCrafter/createFromTemplate?template_id=american_ipa&name=My+Custom+IPA&device_type=zymatic&save=false"
```

**POST version (if you need it):**
```bash
curl -X POST {picobrew_server_url}/API/RecipeCrafter/createFromTemplate \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": "american_ipa",
    "name": "My Custom IPA",
    "device_type": "zymatic",
    "save": true
  }'
```

⚠️ **CONFIRMATION REQUIRED**: Only set `save=true` after user confirms.

### Create custom recipe

```bash
curl -X POST {picobrew_server_url}/API/RecipeCrafter/createRecipe \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Custom Brew",
    "device_type": "zymatic",
    "abv": 5.5,
    "ibu": 45,
    "mash_steps": [
      {"name": "Sacch Rest", "temp_f": 152, "time_min": 60}
    ],
    "hop_additions": [
      {"time_min": 60, "location": "Adjunct1"},
      {"time_min": 15, "location": "Adjunct2"},
      {"time_min": 5, "location": "Adjunct3"},
      {"time_min": 0, "location": "Adjunct4"}
    ],
    "boil_time_min": 60,
    "save": true
  }'
```

⚠️ **CONFIRMATION REQUIRED**: Only set `save: true` after user confirms.

---

## Device-Specific Notes

### Pico / Pico C
- Uses 4 adjunct compartments for hop additions
- Fixed 1.3 gallon batch size
- Recipes stored as JSON with RFID-style IDs

### Zymatic
- Uses 4 hop cages (Adjunct1-4)
- Fixed 2.5 gallon batch size  
- More flexible temperature control
- Heating and Dough In steps use 110°F

### Z-Series
- Programmable step mashing
- Larger batch sizes supported
- More advanced recipe options

---

## Common Workflows

### 1. Check what's fermenting

```bash
curl {picobrew_server_url}/API/Agent/ferm/active
```

Parse the JSON response to tell the user about active fermentations.

### 2. Get current fermentation status

When asked "how's my beer doing?":
1. Call `/API/Agent/ferm/active`
2. Report: temp, pressure, duration, and gravity (if Tilt/iSpindel available)

### 3. Create a custom recipe (FILE UPLOAD - RECOMMENDED!)

**⚠️ AGENTS: Use file upload to avoid PowerShell escaping issues!**

This is the most reliable way to create custom recipes with complex parameters.

**Step 1: Get the recipe structure**
```powershell
Invoke-RestMethod -Uri "http://localhost:8181/API/Agent/recipePaths"
```

**Step 2: Create the recipe JSON file locally**

Create a file like `Tropical_Soft_Haze_IPA.json` with proper JSON structure.

**Step 3: Validate the file exists**
```powershell
Test-Path -Path "Tropical_Soft_Haze_IPA.json"
```

**Step 4: Upload to the server via Base64 encoding**

This works on all PowerShell versions and avoids all escaping issues:

```powershell
Invoke-RestMethod -Uri "http://localhost:8181/API/Agent/uploadRecipe" -Method POST -ContentType "application/json" -Body (@{device_type="zymatic"; recipe_base64=[Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes((Get-Content -Path "Tropical_Soft_Haze_IPA.json" -Raw)))} | ConvertTo-Json)
```

**Step 5: Verify it was saved**
```powershell
Invoke-RestMethod -Uri "http://localhost:8181/API/Agent/recipes/zymatic"
```

### 4. Quick recipe from template (GET-based)

For simpler recipes, use the GET endpoint:
```powershell
Invoke-RestMethod -Uri "http://localhost:8181/API/RecipeCrafter/createFromTemplate?template_id=american_ipa&name=My+IPA&device_type=zymatic&save=true"
```

---

## Error Handling

Success responses:
```json
{"success": true, "data": {...}}
```

Error responses:
```json
{"success": false, "error": "Description of what went wrong"}
```

Common errors:
- `Connection refused` - Server not running
- `Invalid device type` - Use `pico`, `zymatic`, or `zseries`

---

## Safety Guidelines

⚠️ **Always confirm before saving:**
- Show the recipe preview to the user first
- Ask explicitly: "Should I save this recipe to your [device]?"
- Only set `save: true` after explicit confirmation

⚠️ **Don't delete without asking:**
- Always ask before deleting any recipes or sessions

---

## Everything You Can Do 🍺

| Action | Endpoint | Method |
|--------|----------|--------|
| Check server status | `/API/Agent/status` | GET |
| List devices | `/API/Agent/devices` | GET |
| Get recipe save paths | `/API/Agent/recipePaths` | GET |
| **Upload recipe file** | `/API/Agent/uploadRecipe` | **POST** |
| Get active fermentations | `/API/Agent/ferm/active` | GET |
| Get ferm history | `/API/Agent/ferm/history` | GET |
| Get active brews | `/API/Agent/brew/active` | GET |
| Get brew history | `/API/Agent/brew/history` | GET |
| Get active Tilts | `/API/Agent/tilt/active` | GET |
| Get Tilt history | `/API/Agent/tilt/history` | GET |
| Get active iSpindels | `/API/Agent/iSpindel/active` | GET |
| List recipes | `/API/Agent/recipes/{device}` | GET |
| Get recipe details | `/API/Agent/recipes/{device}/{file}` | GET |
| Get templates | `/API/RecipeCrafter/getTemplates` | GET |
| Create custom recipe | `/API/RecipeCrafter/createRecipe` | GET |
| Create from template | `/API/RecipeCrafter/createFromTemplate` | GET |
| Search online | `/API/RecipeCrafter/searchRecipes` | GET |

---

## File-Based Recipe Saving (Recommended for Agents!)

When creating complex custom recipes, **upload files via HTTP** to avoid escaping issues.

### Upload Recipe Workflow (RECOMMENDED)

**Step 1: Get recipe structure and examples**
```powershell
Invoke-RestMethod -Uri "http://localhost:8181/API/Agent/recipePaths"
```

**Step 2: Create the recipe JSON file locally**

Save to a local temp file like `recipe.json`:
```json
{
  "name": "Tropical Soft Haze IPA",
  "notes": "Dry hop Day 3-4: Citra 1oz, Mosaic 0.75oz. Target OG 1.062, ABV 6.5%, IBU 50",
  "steps": [
    {"name": "Dough In", "temperature": 110, "step_time": 5, "drain_time": 0, "location": "PassThru"},
    {"name": "Heat to Mash", "temperature": 152, "step_time": 0, "drain_time": 0, "location": "PassThru"},
    {"name": "Sacch Rest", "temperature": 152, "step_time": 45, "drain_time": 0, "location": "Mash"},
    {"name": "Heat to Mash Out", "temperature": 170, "step_time": 0, "drain_time": 0, "location": "PassThru"},
    {"name": "Mash Out", "temperature": 170, "step_time": 10, "drain_time": 5, "location": "Mash"},
    {"name": "Heat to Boil", "temperature": 207, "step_time": 0, "drain_time": 0, "location": "PassThru"},
    {"name": "Boil Hops 30min", "temperature": 207, "step_time": 30, "drain_time": 0, "location": "Adjunct1"},
    {"name": "Boil Hops 10min", "temperature": 207, "step_time": 10, "drain_time": 0, "location": "Adjunct2"},
    {"name": "Boil Hops 5min", "temperature": 207, "step_time": 5, "drain_time": 0, "location": "Adjunct3"},
    {"name": "Flameout", "temperature": 207, "step_time": 5, "drain_time": 0, "location": "Adjunct4"},
    {"name": "Connect Chiller", "temperature": 207, "step_time": 0, "drain_time": 0, "location": "Pause"},
    {"name": "Chill", "temperature": 66, "step_time": 10, "drain_time": 10, "location": "PassThru"}
  ]
}
```

**Step 3: Validate the file exists locally**
```powershell
Test-Path -Path "recipe.json"
```

**Step 4: Upload via HTTP POST (file upload)**
```powershell
Invoke-RestMethod -Uri "http://localhost:8181/API/Agent/uploadRecipe" -Method POST -Form @{file = Get-Item -Path "recipe.json"; device_type = "zymatic"}
```

**Alternative: Upload via Base64 encoding (avoids file handling)**
```powershell
Invoke-RestMethod -Uri "http://localhost:8181/API/Agent/uploadRecipe" -Method POST -ContentType "application/json" -Body ([System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String("eyJkZXZpY2VfdHlwZSI6Inp5bWF0aWMiLCJyZWNpcGVfYmFzZTY0IjoiLi4uIn0=")))
```

**Step 5: Verify it was saved**
```powershell
Invoke-RestMethod -Uri "http://localhost:8181/API/Agent/recipes/zymatic"
```

### Upload Recipe Endpoint

```
POST /API/Agent/uploadRecipe
```

**Method 1: Base64-encoded recipe (RECOMMENDED - works on all PowerShell versions!)**

```powershell
# Read file, base64 encode, and upload in one command
Invoke-RestMethod -Uri "http://localhost:8181/API/Agent/uploadRecipe" -Method POST -ContentType "application/json" -Body (@{device_type="zymatic"; recipe_base64=[Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes((Get-Content -Path "recipe.json" -Raw)))} | ConvertTo-Json)
```

**Method 2: File upload (PowerShell 7+ only)**
```powershell
Invoke-RestMethod -Uri "http://localhost:8181/API/Agent/uploadRecipe" -Method POST -Form @{file = Get-Item -Path "recipe.json"; device_type = "zymatic"}
```

**Request body for Method 1:**
```json
{
  "device_type": "zymatic",
  "recipe_base64": "eyJuYW1lIjoiVHJvcGljYWwgU29mdCBIYXplIElQQSIsInN0ZXBzIjpbLi4uXX0="
}
```

**Returns:**
```json
{
  "success": true,
  "message": "Recipe saved successfully",
  "filename": "Tropical_Soft_Haze_IPA.json",
  "path": "D:\\picobrew\\recipes\\zymatic\\Tropical_Soft_Haze_IPA.json",
  "device_type": "zymatic",
  "recipe_name": "Tropical Soft Haze IPA"
}
```

### Get Recipe Paths (for reference)

```powershell
Invoke-RestMethod -Uri "http://localhost:8181/API/Agent/recipePaths"
```

Returns:
```json
{
  "success": true,
  "paths": {
    "pico": "D:\\picobrew\\recipes\\pico",
    "zymatic": "D:\\picobrew\\recipes\\zymatic",
    "zseries": "D:\\picobrew\\recipes\\zseries"
  },
  "examples": {
    "zymatic": { "id": "...", "name": "...", "steps": [...] },
    "pico": { "id": "...", "name": "...", "steps": [...] }
  }
}
```

### Zymatic Recipe JSON Structure

```json
{
  "id": "any32characterhexstring1234567890",
  "name": "Recipe Name",
  "notes": "Any notes including dry hop schedule, OG, ABV, IBU targets",
  "steps": [
    {"name": "Heat to Mash", "temperature": 152, "step_time": 0, "drain_time": 0, "location": "PassThru"},
    {"name": "Mash", "temperature": 152, "step_time": 90, "drain_time": 8, "location": "Mash"},
    {"name": "Heat to Mash Out", "temperature": 175, "step_time": 0, "drain_time": 0, "location": "PassThru"},
    {"name": "Mash Out", "temperature": 175, "step_time": 15, "drain_time": 8, "location": "Mash"},
    {"name": "Heat to Boil", "temperature": 207, "step_time": 0, "drain_time": 0, "location": "PassThru"},
    {"name": "Boil 60min", "temperature": 207, "step_time": 30, "drain_time": 0, "location": "Adjunct1"},
    {"name": "Boil 30min", "temperature": 207, "step_time": 20, "drain_time": 0, "location": "Adjunct2"},
    {"name": "Boil 10min", "temperature": 207, "step_time": 10, "drain_time": 0, "location": "Adjunct3"},
    {"name": "Flameout", "temperature": 207, "step_time": 5, "drain_time": 0, "location": "Adjunct4"},
    {"name": "Connect Chiller", "temperature": 207, "step_time": 0, "drain_time": 0, "location": "Pause"},
    {"name": "Chill", "temperature": 70, "step_time": 10, "drain_time": 10, "location": "PassThru"}
  ]
}
```

**Zymatic Locations:** `PassThru`, `Mash`, `Adjunct1`, `Adjunct2`, `Adjunct3`, `Adjunct4`, `Pause`
**temperature:** Fahrenheit
**step_time:** Minutes
**drain_time:** Minutes (use 0 except for mash-out and final chill)

---

### Pico Recipe JSON Structure

```json
{
  "id": "A1B2C3D4E5F6G7",
  "name": "Recipe Name",
  "notes": "Any notes including dry hop schedule, OG, ABV, IBU targets",
  "abv": 6.5,
  "ibu": 45,
  "abv_tweak": 0,
  "ibu_tweak": 0,
  "image": "",
  "steps": [
    {"name": "Preparing to Brew", "temperature": 0, "step_time": 3, "drain_time": 0, "location": "Prime"},
    {"name": "Heating", "temperature": 110, "step_time": 0, "drain_time": 0, "location": "PassThru"},
    {"name": "Dough In", "temperature": 110, "step_time": 7, "drain_time": 0, "location": "Mash"},
    {"name": "Mash 1", "temperature": 148, "step_time": 45, "drain_time": 0, "location": "Mash"},
    {"name": "Mash 2", "temperature": 152, "step_time": 45, "drain_time": 0, "location": "Mash"},
    {"name": "Mash Out", "temperature": 170, "step_time": 10, "drain_time": 2, "location": "Mash"},
    {"name": "Boil Adj 1", "temperature": 202, "step_time": 30, "drain_time": 0, "location": "Adjunct1"},
    {"name": "Boil Adj 2", "temperature": 202, "step_time": 15, "drain_time": 0, "location": "Adjunct2"},
    {"name": "Boil Adj 3", "temperature": 202, "step_time": 10, "drain_time": 0, "location": "Adjunct3"},
    {"name": "Boil Adj 4", "temperature": 202, "step_time": 5, "drain_time": 10, "location": "Adjunct4"},
      ]
}
```

**Pico Locations:** `Prime`, `Mash`, `PassThru`, `Adjunct1`, `Adjunct2`, `Adjunct3`, `Adjunct4`
**NOTE: Pico does NOT support `Pause` location - omit "Connect Chiller" step for Pico recipes!**
**ID:** 14 character uppercase hex string (e.g., "A1B2C3D4E5F6G7")
**temperature:** Fahrenheit
**step_time:** Minutes
**drain_time:** Minutes (use 2 for mash-out drain, 5 for last hop addition)

---

### Z-Series Recipe JSON Structure

```json
{
  "id": 12345,
  "name": "Recipe Name",
  "notes": "Any notes including dry hop schedule, OG, ABV, IBU targets",
  "start_water": 13.1,
  "clean": false,
  "steps": [
    {"name": "Heat Water", "temperature": 104, "step_time": 0, "drain_time": 0, "location": "PassThru"},
    {"name": "Dough In", "temperature": 104, "step_time": 20, "drain_time": 0, "location": "Mash"},
    {"name": "Heat to Mash 1", "temperature": 145, "step_time": 0, "drain_time": 4, "location": "Mash"},
    {"name": "Mash 1", "temperature": 145, "step_time": 20, "drain_time": 4, "location": "Mash"},
    {"name": "Heat to Mash 2", "temperature": 161, "step_time": 0, "drain_time": 4, "location": "Mash"},
    {"name": "Mash 2", "temperature": 161, "step_time": 80, "drain_time": 4, "location": "Mash"},
    {"name": "Heat to Mash Out", "temperature": 175, "step_time": 0, "drain_time": 4, "location": "Mash"},
    {"name": "Mash Out", "temperature": 175, "step_time": 15, "drain_time": 8, "location": "Mash"},
    {"name": "Heat to Boil", "temperature": 207, "step_time": 0, "drain_time": 0, "location": "PassThru"},
    {"name": "Pre Hop Boil", "temperature": 207, "step_time": 45, "drain_time": 0, "location": "PassThru"},
    {"name": "Boil Adj 1", "temperature": 207, "step_time": 30, "drain_time": 0, "location": "Adjunct1"},
    {"name": "Boil Adj 2", "temperature": 207, "step_time": 20, "drain_time": 0, "location": "Adjunct2"},
    {"name": "Boil Adj 3", "temperature": 207, "step_time": 7, "drain_time": 0, "location": "Adjunct3"},
    {"name": "Boil Adj 4", "temperature": 207, "step_time": 3, "drain_time": 0, "location": "Adjunct4"},
    {"name": "Connect Chiller", "temperature": 207, "step_time": 0, "drain_time": 0, "location": "Pause"},
    {"name": "Chill", "temperature": 65, "step_time": 10, "drain_time": 10, "location": "PassThru"}
  ]
}
```

**Z-Series Locations:** `PassThru`, `Mash`, `Adjunct1`, `Adjunct2`, `Adjunct3`, `Adjunct4`, `Pause`
**ID:** Integer (auto-assigned by system)
**start_water:** Gallons of starting water
**temperature:** Fahrenheit
**step_time:** Minutes
**drain_time:** Minutes (note: different from Zymatic/Pico which use seconds)

---

## Your Human Can Ask

Your human might ask things like:
- "What's fermenting right now?" → GET `/API/Agent/ferm/active`
- "How's my beer doing?" → GET `/API/Agent/ferm/active` + `/API/Agent/tilt/active`
- "Show me my Zymatic recipes" → GET `/API/Agent/recipes/zymatic`
- "Help me design an IPA for my Pico" → Use templates + POST to create
- "What brew sessions did I do last month?" → GET `/API/Agent/brew/history`
- "Create a stout recipe" → POST `/API/RecipeCrafter/createFromTemplate`

When they ask, use the appropriate JSON endpoints above!
