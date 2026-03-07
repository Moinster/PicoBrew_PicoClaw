# Brewfather Integration Skill

Connect to Brewfather API to pull recipes and sync with your PicoBrew server.

## Configuration

Before using this skill, configure your Brewfather API key:

```json
{
  "brewfather_api_key": "your_brewfather_api_key_here"
}
```

Save this to `~/.config/brewfather/config.json` or set the environment variable `BREWFAHTER_API_KEY`.

**Base URL:** `https://api.brewfather.app/v1/`

---

## API Endpoints

### Authentication
All endpoints require your API key in the Authorization header:
```
Authorization: Bearer {brewfather_api_key}
```

### Get Recipes
```
GET /recipes
```

Parameters:
- `limit`: Number of recipes to return (default: 10)
- `skip`: Number of recipes to skip (for pagination)
- `sort`: Sort field (default: createdAt)

Returns:
```json
[
  {
    "_id": "recipe_id",
    "name": "Recipe Name",
    "batchSize": 5.0,
    "boilTime": 60,
    "efficiency": 75,
    "style": "IPA",
    "fermentationDays": 14,
    "grains": [
      {
        "name": "Grain Name",
        "amount": 10.0,
        "potential": 1.036,
        "color": 10.0
      }
    ],
    "hops": [
      {
        "name": "Hop Name",
        "form": "Pellet",
        "alpha": 12.0,
        "time": 60,
        "amount": 1.0,
        "use": "Boil"
      }
    ],
    "yeast": {
      "name": "Yeast Name",
      "attenuation": 75.0
    }
  }
]
```

### Get Specific Recipe
```
GET /recipes/{recipe_id}
```

### Get Batches
```
GET /batches
```

### Get Specific Batch
```
GET /batches/{batch_id}
```

### Create Batch from Recipe
```
POST /recipes/{recipe_id}/batch
```

Body:
```json
{
  "name": "Batch Name",
  "brewDate": "2026-02-11T15:00:00.000Z",
  "batchSize": 5.0
}
```

---

## PowerShell Examples

### Get all recipes
```powershell
$headers = @{
    "Authorization" = "Bearer $env:BF_API_KEY"
}
Invoke-RestMethod -Uri "https://api.brewfather.app/v1/recipes" -Headers $headers -Method GET
```

### Get specific recipe
```powershell
$recipeId = "your_recipe_id"
$headers = @{
    "Authorization" = "Bearer $env:BF_API_KEY"
}
Invoke-RestMethod -Uri "https://api.brewfather.app/v1/recipes/$recipeId" -Headers $headers -Method GET
```

---

## Integration with PicoBrew Server

This skill can be combined with the picobrew-server skill to:

1. Pull recipe from Brewfather
2. Convert recipe format to PicoBrew compatible format
3. Upload to PicoBrew server

### Recipe Conversion Process

When converting from Brewfather to PicoBrew format:

1. Parse grain bill and convert amounts to PicoBrew format
2. Map hop additions to appropriate PicoBrew adjunct locations based on timing
3. Calculate appropriate mash schedule for Zymatic/Pico
4. Generate appropriate JSON structure for PicoBrew server

---

## Common Tasks

### 1. List all recipes
```powershell
$headers = @{
    "Authorization" = "Bearer $env:BF_API_KEY"
}
(Invoke-RestMethod -Uri "https://api.brewfather.app/v1/recipes" -Headers $headers -Method GET) | ForEach-Object { Write-Host $_.name -ForegroundColor Green; Write-Host "ID: $($_._id)" -ForegroundColor Yellow }
```

### 2. Get specific recipe details
```powershell
$recipeId = "recipe_id_here"
$headers = @{
    "Authorization" = "Bearer $env:BF_API_KEY"
}
$recipe = Invoke-RestMethod -Uri "https://api.brewfather.app/v1/recipes/$recipeId" -Headers $headers -Method GET
Write-Host "Recipe: $($recipe.name)"
Write-Host "Style: $($recipe.style)"
Write-Host "OG: $($recipe.recipeCalculations?.og)"
Write-Host "FG: $($recipe.recipeCalculations?.fg)"
Write-Host "IBU: $($recipe.recipeCalculations?.ibu)"
Write-Host "Color: $($recipe.recipeCalculations?.color)"
```

### 3. Convert Brewfather recipe to PicoBrew format (conceptual)
```powershell
function Convert-BFRecipeToPicoBrew {
    param(
        $bfRecipe
    )
    
    # Determine device type based on batch size or user preference
    $deviceType = if ($bfRecipe.batchSize -gt 2.5) { "zymatic" } else { "pico" }
    
    # Basic conversion logic would go here
    # This would map grains, hops, and create appropriate step sequences
    # based on the original Brewfather recipe
    
    $picoBrewRecipe = @{
        name = $bfRecipe.name
        notes = "Converted from Brewfather recipe. Original style: $($bfRecipe.style)"
        deviceType = $deviceType
        # Additional mapping logic would be implemented here
    }
    
    return $picoBrewRecipe
}
```

---

## Error Handling

Common error responses:
- `401 Unauthorized`: Invalid or missing API key
- `404 Not Found`: Requested resource doesn't exist
- `429 Too Many Requests`: Rate limit exceeded (Brewfather has rate limits)

Rate limits:
- Standard requests: 1000 per hour
- Streaming requests: 100 per hour

---

## Safety Guidelines

⚠️ Always validate recipe data before sending to PicoBrew server
⚠️ Confirm with user before creating batches or uploading recipes
⚠️ Respect API rate limits to avoid being throttled

---

## Everything You Can Do

| Action | Endpoint | Method |
|--------|----------|--------|
| List recipes | `/recipes` | GET |
| Get recipe | `/recipes/{id}` | GET |
| List batches | `/batches` | GET |
| Get batch | `/batches/{id}` | GET |
| Create batch | `/recipes/{id}/batch` | POST |
| Create recipe | `/recipes` | POST |

---

## Integration Example: Pull Recipe and Send to PicoBrew

```powershell
# 1. Get recipe from Brewfather
$headers = @{
    "Authorization" = "Bearer $env:BF_API_KEY"
}
$bfRecipe = Invoke-RestMethod -Uri "https://api.brewfather.app/v1/recipes/recipe_id" -Headers $headers -Method GET

# 2. Extract relevant data from Brewfather recipe
$recipeName = $bfRecipe.name
$style = $bfRecipe.style
$batchSize = $bfRecipe.batchSize
$boilTime = $bfRecipe.boilTime
$grains = $bfRecipe.grains
$hops = $bfRecipe.hops
$yeast = $bfRecipe.yeast

# 3. Prepare recipe parameters for PicoBrew RecipeCrafter
# Using the picobrew-server skill's createRecipe endpoint
# Convert hop schedule to PicoBrew format (Adjunct1-4 based on timing)

# Group hops by timing for PicoBrew adjunct locations
$hopSchedule = @()
foreach ($hop in ($hops | Sort-Object -Property time -Descending)) {
    $hopSchedule += "$($hop.time):Adjunct1"  # Simplified - would need more sophisticated mapping
}

# 4. Create recipe using picobrew-server skill
# Use the GET version to avoid JSON escaping issues:
$recipeParams = @{
    name = [uri]::EscapeDataString($recipeName)
    device_type = if ($batchSize -gt 2.5) { "zymatic" } else { "pico" }
    abv = [uri]::EscapeDataString("$($bfRecipe.recipeCalculations.abv)")
    ibu = [uri]::EscapeDataString("$($bfRecipe.recipeCalculations.ibu)")
    og = [uri]::EscapeDataString("$($bfRecipe.recipeCalculations.og)")
    boil_time = $boilTime
    notes = [uri]::EscapeDataString("Converted from Brewfather recipe. Style: $style")
    save = $false  # Set to $true after confirming with user
}

$paramString = ($recipeParams.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join "&"
$createUrl = "http://192.168.68.52:80/API/RecipeCrafter/createRecipe?$paramString"

# Preview the recipe (save=false)
$picoBrewRecipe = Invoke-RestMethod -Uri $createUrl -Method GET

# Show user the converted recipe before saving
Write-Host "Converted Recipe Preview:" -ForegroundColor Green
Write-Host "Name: $($picoBrewRecipe.name)"
Write-Host "Device Type: $($picoBrewRecipe.device_type)"
Write-Host "Estimated ABV: $($picoBrewRecipe.abv)%"
Write-Host "Estimated IBU: $($picoBrewRecipe.ibu)"

# 5. After user confirms, save the recipe to PicoBrew server
# Change save parameter to $true and execute again
```

## Recommended Workflow

1. Use this skill to pull recipe data from Brewfather
2. Extract the necessary ingredients and timing information
3. Format the recipe appropriately using the picobrew-server skill's RecipeCrafter API
4. Preview the converted recipe before saving
5. Confirm with user before saving to PicoBrew device
6. Upload the final recipe to your PicoBrew server at 192.168.68.52:80