"""
Recipe Crafter API Routes

Provides endpoints for:
- Importing BeerXML recipes
- Creating recipes from manual input
- Converting recipes to device formats
- Searching/importing from online recipe sources
"""

import json
import os
import uuid
from flask import request, jsonify, current_app, render_template
from pathlib import Path

from . import main
from .config import recipe_path, MachineType
from .beerxml_parser import parse_beerxml, BeerRecipe
from .recipe_converter import (
    RecipeConverter, 
    DeviceType, 
    convert_beerxml_to_device,
    create_recipe_from_params
)
from .frontend_common import render_template_with_defaults


# =============================================================================
# Recipe Crafter Page
# =============================================================================

@main.route('/recipe_crafter')
def recipe_crafter():
    """Render the Recipe Crafter page."""
    return render_template_with_defaults('recipe_crafter.html')


# =============================================================================
# BeerXML Import
# =============================================================================

@main.route('/API/RecipeCrafter/importBeerXML', methods=['POST'])
def import_beerxml():
    """
    Import a BeerXML file and convert to device format.
    
    Request body:
        - xml_content: Raw BeerXML string (required if no file or xml_base64)
        - xml_base64: Base64-encoded BeerXML (alternative to xml_content, avoids escaping issues)
        - device_type: 'pico', 'zymatic', or 'zseries' (default: 'pico')
        - save: Whether to save the recipe (default: false, just preview)
        
    Or multipart form with:
        - file: The BeerXML file
        - device_type: Target device
        - save: Whether to save
        
    Returns:
        {
            'success': true,
            'recipes': [...],  // Converted recipes
            'saved_count': 0   // Number saved (if save=true)
        }
    """
    try:
        import base64
        
        # Get XML content from file upload or JSON body
        xml_content = None
        device_type = 'pico'
        save_recipe = False
        
        if request.content_type and 'multipart/form-data' in request.content_type:
            # File upload
            if 'file' not in request.files:
                return jsonify({'success': False, 'error': 'No file uploaded'}), 400
            
            file = request.files['file']
            if file.filename == '':
                return jsonify({'success': False, 'error': 'No file selected'}), 400
            
            xml_content = file.read().decode('utf-8')
            device_type = request.form.get('device_type', 'pico')
            save_recipe = request.form.get('save', 'false').lower() == 'true'
        else:
            # JSON body
            data = request.get_json() or {}
            device_type = data.get('device_type', 'pico')
            save_recipe = data.get('save', False)
            
            # Check for base64-encoded XML first (avoids escaping issues for agents)
            if 'xml_base64' in data:
                try:
                    xml_content = base64.b64decode(data['xml_base64']).decode('utf-8')
                except Exception as e:
                    return jsonify({'success': False, 'error': f'Failed to decode base64 XML: {e}'}), 400
            else:
                xml_content = data.get('xml_content')
        
        if not xml_content:
            return jsonify({'success': False, 'error': 'No BeerXML content provided. Use xml_content, xml_base64, or file upload'}), 400
        
        # Parse and convert
        converted = convert_beerxml_to_device(xml_content, device_type)
        
        saved_count = 0
        if save_recipe:
            for recipe in converted:
                if _save_recipe(recipe, device_type):
                    saved_count += 1
        
        return jsonify({
            'success': True,
            'recipes': converted,
            'saved_count': saved_count,
            'device_type': device_type,
        })
        
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"BeerXML import error: {e}")
        return jsonify({'success': False, 'error': f'Import failed: {str(e)}'}), 500


@main.route('/API/RecipeCrafter/previewBeerXML', methods=['POST'])
def preview_beerxml():
    """
    Parse BeerXML and return the raw recipe data (before conversion).
    Useful for showing what's in the file before converting.
    """
    try:
        xml_content = None
        
        if request.content_type and 'multipart/form-data' in request.content_type:
            if 'file' not in request.files:
                return jsonify({'success': False, 'error': 'No file uploaded'}), 400
            xml_content = request.files['file'].read().decode('utf-8')
        else:
            data = request.get_json() or {}
            xml_content = data.get('xml_content')
        
        if not xml_content:
            return jsonify({'success': False, 'error': 'No BeerXML content provided'}), 400
        
        # Parse only - don't convert
        recipes = parse_beerxml(xml_content)
        
        # Convert to serializable format
        result = []
        for r in recipes:
            recipe_data = {
                'name': r.name,
                'type': r.type,
                'brewer': r.brewer,
                'batch_size_gal': round(r.batch_size_gal, 2),
                'boil_time_min': r.boil_time_min,
                'og': r.og,
                'fg': r.fg,
                'abv': round(r.abv, 1),
                'ibu': round(r.ibu, 1),
                'color_srm': round(r.color_srm, 1),
                'style': r.style.name if r.style else None,
                'notes': r.notes,
                'fermentables': [
                    {'name': f.name, 'amount_lb': round(f.amount_lb, 2), 'type': f.type.value}
                    for f in r.fermentables
                ],
                'hops': [
                    {'name': h.name, 'amount_oz': round(h.amount_oz, 2), 
                     'time_min': h.time_min, 'use': h.use.value, 'alpha': h.alpha_acid}
                    for h in r.hops
                ],
                'yeasts': [
                    {'name': y.name, 'lab': y.lab, 'attenuation': y.attenuation}
                    for y in r.yeasts
                ],
                'mash_steps': [
                    {'name': m.name, 'temp_f': round(m.step_temp_f), 'time_min': m.step_time_min}
                    for m in r.mash_steps
                ],
            }
            result.append(recipe_data)
        
        return jsonify({
            'success': True,
            'recipes': result,
            'count': len(result),
        })
        
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"BeerXML preview error: {e}")
        return jsonify({'success': False, 'error': f'Preview failed: {str(e)}'}), 500


# =============================================================================
# Manual Recipe Creation
# =============================================================================

@main.route('/API/RecipeCrafter/createRecipe', methods=['GET', 'POST'])
def create_recipe():
    """
    Create a recipe from manual input.
    
    GET (agent-friendly, no JSON escaping needed):
        /API/RecipeCrafter/createRecipe?name=My+IPA&device_type=zymatic&save=false
            &mash=Sacch+Rest:152:60,Mash+Out:170:10
            &hops=60:Adjunct1,15:Adjunct2,5:Adjunct3,0:Adjunct4
            &boil_time=60&og=1.065&ibu=65&abv=6.5
        
        mash format: "StepName:TempF:Minutes,StepName:TempF:Minutes,..."
        hops format: "Minutes:Location,Minutes:Location,..." (Locations: Adjunct1-4)
    
    POST Request body:
        {
            'name': 'My IPA',
            'device_type': 'pico',
            'mash_steps': [
                {'name': 'Sacch Rest', 'temp_f': 152, 'time_min': 60}
            ],
            'hop_additions': [
                {'name': 'Cascade', 'time_min': 60},
                {'name': 'Centennial', 'time_min': 15},
                {'name': 'Citra', 'time_min': 5}
            ],
            'boil_time': 60,
            'og': 1.065,
            'ibu': 65,
            'abv': 6.5,
            'notes': 'My favorite IPA',
            'save': true
        }
    """
    try:
        # Support both GET (query params) and POST (JSON body)
        if request.method == 'GET':
            name = request.args.get('name', 'New Recipe')
            device_type = request.args.get('device_type', 'pico')
            boil_time = int(request.args.get('boil_time', 60))
            og = float(request.args.get('og', 1.050))
            ibu = int(request.args.get('ibu', 30))
            abv = float(request.args.get('abv', 5.0))
            notes = request.args.get('notes', '')
            save = request.args.get('save', 'false').lower() == 'true'
            
            # Parse mash steps from "Name:TempF:Minutes,Name:TempF:Minutes" format
            mash_param = request.args.get('mash', '')
            if mash_param:
                mash_steps = []
                for step in mash_param.split(','):
                    parts = step.strip().split(':')
                    if len(parts) >= 3:
                        mash_steps.append({
                            'name': parts[0].replace('+', ' '),
                            'temp_f': int(parts[1]),
                            'time_min': int(parts[2])
                        })
                    elif len(parts) == 2:
                        # TempF:Minutes format (auto-name)
                        mash_steps.append({
                            'name': f'Step at {parts[0]}F',
                            'temp_f': int(parts[0]),
                            'time_min': int(parts[1])
                        })
            else:
                mash_steps = [{'name': 'Mash', 'temp_f': 152, 'time_min': 60}]
            
            # Parse hops from "Minutes:Location,Minutes:Location" format
            hops_param = request.args.get('hops', '')
            if hops_param:
                hop_additions = []
                for hop in hops_param.split(','):
                    parts = hop.strip().split(':')
                    if len(parts) >= 2:
                        hop_additions.append({
                            'time_min': int(parts[0]),
                            'location': parts[1]
                        })
            else:
                hop_additions = []
        else:
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'error': 'No data provided'}), 400
            
            name = data.get('name', 'New Recipe')
            device_type = data.get('device_type', 'pico')
            mash_steps = data.get('mash_steps', [{'name': 'Mash', 'temp_f': 152, 'time_min': 60}])
            hop_additions = data.get('hop_additions', [])
            boil_time = data.get('boil_time', 60)
            og = data.get('og', 1.050)
            ibu = data.get('ibu', 30)
            abv = data.get('abv', 5.0)
            notes = data.get('notes', '')
            save = data.get('save', False)
        
        # Create the recipe
        recipe = create_recipe_from_params(
            name=name,
            device_type=device_type,
            mash_steps=mash_steps,
            hop_additions=hop_additions,
            boil_time=boil_time,
            og=og,
            ibu=ibu,
            abv=abv,
            notes=notes,
        )
        
        saved = False
        if save:
            saved = _save_recipe(recipe, device_type)
        
        return jsonify({
            'success': True,
            'recipe': recipe,
            'saved': saved,
            'device_type': device_type,
        })
        
    except Exception as e:
        current_app.logger.error(f"Recipe creation error: {e}")
        return jsonify({'success': False, 'error': f'Creation failed: {str(e)}'}), 500


@main.route('/API/RecipeCrafter/convertRecipe', methods=['POST'])
def convert_recipe():
    """
    Convert an existing recipe to a different device format.
    
    Request body:
        {
            'recipe': {...},  // Existing recipe dict
            'from_device': 'zymatic',
            'to_device': 'pico',
            'save': false
        }
    """
    try:
        data = request.get_json()
        if not data or 'recipe' not in data:
            return jsonify({'success': False, 'error': 'No recipe provided'}), 400
        
        source_recipe = data['recipe']
        to_device = data.get('to_device', 'pico')
        save = data.get('save', False)
        
        # Build a BeerRecipe from the source
        from .beerxml_parser import BeerRecipe, MashStep, Hop, HopUse
        
        beer_recipe = BeerRecipe(
            name=source_recipe.get('name', 'Converted Recipe'),
            abv=source_recipe.get('abv', 5.0),
            ibu=source_recipe.get('ibu', 30.0),
            notes=source_recipe.get('notes', ''),
        )
        
        # Extract mash and hop info from steps
        for step in source_recipe.get('steps', []):
            location = step.get('location', '')
            
            if location == 'Mash':
                beer_recipe.mash_steps.append(MashStep(
                    name=step.get('name', 'Mash'),
                    step_temp_c=(step.get('temperature', 152) - 32) * 5/9,
                    step_time_min=step.get('step_time', 60),
                ))
            elif location.startswith('Adjunct'):
                beer_recipe.hops.append(Hop(
                    name=step.get('name', 'Hops'),
                    amount_kg=0.028,  # ~1 oz default
                    time_min=step.get('step_time', 10),
                    use=HopUse.BOIL,
                ))
        
        # Convert to target device
        device_map = {
            'pico': DeviceType.PICO,
            'zymatic': DeviceType.ZYMATIC,
            'zseries': DeviceType.ZSERIES,
        }
        device = device_map.get(to_device.lower(), DeviceType.PICO)
        
        converter = RecipeConverter(device)
        converted = converter.convert(beer_recipe)
        result = converted.to_dict()
        
        saved = False
        if save:
            saved = _save_recipe(result, to_device)
        
        return jsonify({
            'success': True,
            'recipe': result,
            'saved': saved,
            'device_type': to_device,
        })
        
    except Exception as e:
        current_app.logger.error(f"Recipe conversion error: {e}")
        return jsonify({'success': False, 'error': f'Conversion failed: {str(e)}'}), 500


# =============================================================================
# Recipe Templates (Common styles)
# =============================================================================

RECIPE_TEMPLATES = {
    'american_ipa': {
        'name': 'American IPA',
        'mash_steps': [
            {'name': 'Sacch Rest', 'temp_f': 152, 'time_min': 60},
        ],
        'hop_additions': [
            {'name': 'Bittering', 'time_min': 60},
            {'name': 'Flavor', 'time_min': 15},
            {'name': 'Aroma', 'time_min': 5},
            {'name': 'Whirlpool', 'time_min': 0},
        ],
        'boil_time': 60,
        'og': 1.065,
        'ibu': 65,
        'abv': 6.5,
    },
    'pale_ale': {
        'name': 'American Pale Ale',
        'mash_steps': [
            {'name': 'Sacch Rest', 'temp_f': 152, 'time_min': 60},
        ],
        'hop_additions': [
            {'name': 'Bittering', 'time_min': 60},
            {'name': 'Flavor', 'time_min': 15},
            {'name': 'Aroma', 'time_min': 5},
        ],
        'boil_time': 60,
        'og': 1.050,
        'ibu': 40,
        'abv': 5.0,
    },
    'stout': {
        'name': 'Dry Stout',
        'mash_steps': [
            {'name': 'Sacch Rest', 'temp_f': 154, 'time_min': 60},
        ],
        'hop_additions': [
            {'name': 'Bittering', 'time_min': 60},
        ],
        'boil_time': 60,
        'og': 1.042,
        'ibu': 35,
        'abv': 4.2,
    },
    'hefeweizen': {
        'name': 'Hefeweizen',
        'mash_steps': [
            {'name': 'Protein Rest', 'temp_f': 122, 'time_min': 15},
            {'name': 'Sacch Rest', 'temp_f': 152, 'time_min': 45},
        ],
        'hop_additions': [
            {'name': 'Hallertau', 'time_min': 60},
        ],
        'boil_time': 60,
        'og': 1.048,
        'ibu': 12,
        'abv': 4.9,
    },
    'neipa': {
        'name': 'New England IPA',
        'mash_steps': [
            {'name': 'Sacch Rest', 'temp_f': 156, 'time_min': 60},
        ],
        'hop_additions': [
            {'name': 'Bittering', 'time_min': 30},
            {'name': 'Whirlpool 1', 'time_min': 10},
            {'name': 'Whirlpool 2', 'time_min': 5},
            {'name': 'Whirlpool 3', 'time_min': 0},
        ],
        'boil_time': 60,
        'og': 1.068,
        'ibu': 45,
        'abv': 6.8,
    },
    'pilsner': {
        'name': 'German Pilsner',
        'mash_steps': [
            {'name': 'Protein Rest', 'temp_f': 122, 'time_min': 10},
            {'name': 'Sacch Rest', 'temp_f': 148, 'time_min': 60},
            {'name': 'Mash Out', 'temp_f': 168, 'time_min': 10},
        ],
        'hop_additions': [
            {'name': 'Saaz', 'time_min': 60},
            {'name': 'Saaz', 'time_min': 30},
            {'name': 'Saaz', 'time_min': 5},
        ],
        'boil_time': 90,
        'og': 1.048,
        'ibu': 35,
        'abv': 4.8,
    },
}


@main.route('/API/RecipeCrafter/getTemplates', methods=['GET'])
def get_templates():
    """Get list of available recipe templates."""
    templates = []
    for key, template in RECIPE_TEMPLATES.items():
        templates.append({
            'id': key,
            'name': template['name'],
            'og': template['og'],
            'ibu': template['ibu'],
            'abv': template['abv'],
        })
    return jsonify({
        'success': True,
        'templates': templates,
    })


@main.route('/API/RecipeCrafter/getTemplate/<template_id>', methods=['GET'])
def get_template(template_id):
    """Get a specific recipe template."""
    template = RECIPE_TEMPLATES.get(template_id)
    if not template:
        return jsonify({'success': False, 'error': 'Template not found'}), 404
    
    # Include the ID in the template object
    template_with_id = {**template, 'id': template_id}
    
    return jsonify({
        'success': True,
        'template': template_with_id,
    })


@main.route('/API/RecipeCrafter/createFromTemplate', methods=['GET', 'POST'])
def create_from_template():
    """
    Create a recipe from a template.
    
    GET (agent-friendly, no JSON escaping needed):
        /API/RecipeCrafter/createFromTemplate?template_id=american_ipa&name=My+IPA&device_type=zymatic&save=false
    
    POST Request body:
        {
            'template_id': 'american_ipa',
            'name': 'My Custom IPA',  // Optional override
            'device_type': 'pico',
            'save': true
        }
    """
    try:
        # Support both GET (query params) and POST (JSON body)
        if request.method == 'GET':
            template_id = request.args.get('template_id')
            name_override = request.args.get('name')
            device_type = request.args.get('device_type', 'pico')
            save = request.args.get('save', 'false').lower() == 'true'
        else:
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'error': 'No data provided'}), 400
            template_id = data.get('template_id')
            name_override = data.get('name')
            device_type = data.get('device_type', 'pico')
            save = data.get('save', False)
        
        if not template_id or template_id not in RECIPE_TEMPLATES:
            return jsonify({'success': False, 'error': 'Invalid template ID'}), 400
        
        template = RECIPE_TEMPLATES[template_id].copy()
        
        # Allow name override
        if name_override:
            template['name'] = name_override
        
        # Create the recipe
        recipe = create_recipe_from_params(
            name=template['name'],
            device_type=device_type,
            mash_steps=template['mash_steps'],
            hop_additions=template['hop_additions'],
            boil_time=template['boil_time'],
            og=template['og'],
            ibu=template['ibu'],
            abv=template['abv'],
        )
        
        saved = False
        if save:
            saved = _save_recipe(recipe, device_type)
        
        return jsonify({
            'success': True,
            'recipe': recipe,
            'saved': saved,
            'device_type': device_type,
        })
        
    except Exception as e:
        current_app.logger.error(f"Template creation error: {e}")
        return jsonify({'success': False, 'error': f'Creation failed: {str(e)}'}), 500


# =============================================================================
# Helper Functions
# =============================================================================

def _save_recipe(recipe: dict, device_type: str) -> bool:
    """Save a converted recipe to the appropriate directory."""
    try:
        device_map = {
            'pico': MachineType.PICOBREW,
            'zymatic': MachineType.ZYMATIC,
            'zseries': MachineType.ZSERIES,
        }
        machine_type = device_map.get(device_type.lower(), MachineType.PICOBREW)
        
        # Get recipe path
        path = recipe_path(machine_type)
        
        # Generate filename from recipe name
        name = recipe.get('name', 'recipe')
        filename = name.replace(' ', '_').replace("'", "")
        filepath = path / f"{filename}.json"
        
        # Don't overwrite existing recipes
        counter = 1
        while filepath.exists():
            filepath = path / f"{filename}_{counter}.json"
            counter += 1
        
        # Add ID if needed (Pico uses RFID-style ID)
        if machine_type in [MachineType.PICOBREW, MachineType.PICOBREW_C]:
            if 'id' not in recipe:
                recipe['id'] = uuid.uuid4().hex[:14]
        elif machine_type == MachineType.ZYMATIC:
            if 'id' not in recipe:
                recipe['id'] = uuid.uuid4().hex[:32]
        elif machine_type == MachineType.ZSERIES:
            if 'id' not in recipe:
                recipe['id'] = 1  # Will be incremented by the system
        
        # Save
        with open(filepath, 'w') as f:
            json.dump(recipe, f, indent=4)
        
        current_app.logger.info(f"Saved recipe to {filepath}")
        return True
        
    except Exception as e:
        current_app.logger.error(f"Failed to save recipe: {e}")
        return False


# =============================================================================
# Online Recipe Sources
# =============================================================================

@main.route('/API/RecipeCrafter/searchRecipes', methods=['GET'])
def search_recipes():
    """
    Search for recipes from online sources.
    
    Query params:
        - q: Search query
        - style: Beer style filter
        - source: 'brewersfriend' (more sources can be added)
        
    Note: This is a placeholder for future integration with recipe APIs.
    """
    query = request.args.get('q', '')
    style = request.args.get('style', '')
    source = request.args.get('source', 'brewersfriend')
    
    # TODO: Implement actual API calls to recipe sources
    # For now, return a helpful message
    return jsonify({
        'success': True,
        'message': 'Online recipe search is not yet implemented',
        'suggestion': 'You can export recipes from Brewer\'s Friend, Brewfather, or BeerSmith in BeerXML format and import them using the importBeerXML endpoint.',
        'supported_sources': [
            {
                'name': "Brewer's Friend",
                'url': 'https://www.brewersfriend.com/search/',
                'export_format': 'BeerXML',
            },
            {
                'name': 'Brewfather',
                'url': 'https://web.brewfather.app/',
                'export_format': 'BeerXML',
            },
            {
                'name': 'BeerSmith',
                'url': 'https://beersmithrecipes.com/',
                'export_format': 'BeerXML',
            },
            {
                'name': 'BrewDog DIY Dog',
                'url': 'https://brewdogmedia.s3.eu-west-2.amazonaws.com/docs/2019+DIY+DOG+-+V8.pdf',
                'export_format': 'PDF (manual entry required)',
            },
        ],
        'query': query,
        'style': style,
    })
