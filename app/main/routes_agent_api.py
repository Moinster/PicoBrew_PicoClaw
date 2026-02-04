"""
Agent-friendly JSON API endpoints for PicoBrew Server.

These endpoints return structured JSON data instead of HTML,
making them suitable for AI agents and automation tools.
"""
from datetime import datetime
from flask import current_app, jsonify, request
from pathlib import Path

from . import main
from .config import (MachineType, recipe_path)
from .session_parser import (
    active_brew_sessions, active_ferm_sessions, active_still_sessions,
    active_iSpindel_sessions, active_tilt_sessions,
    list_session_files, load_brew_sessions,
)
from .config import (
    brew_archive_sessions_path, ferm_archive_sessions_path,
    still_archive_sessions_path, iSpindel_archive_sessions_path,
    tilt_archive_sessions_path
)
from .routes_frontend import (
    load_active_ferm_sessions, load_active_still_sessions,
    load_active_brew_sessions, load_active_iSpindel_sessions,
    load_active_tilt_sessions, load_ferm_sessions, load_still_sessions,
    load_iSpindel_sessions, load_tilt_sessions
)
from .recipe_parser import PicoBrewRecipe, ZymaticRecipe, ZSeriesRecipe

import json


# =============================================================================
# Server Status
# =============================================================================

@main.route('/API/Agent/status', methods=['GET'])
def agent_status():
    """
    Check server status and get summary of active sessions.
    
    Returns:
        {
            "success": true,
            "server": "running",
            "active_sessions": {
                "brew": 0,
                "ferm": 2,
                "still": 0,
                "tilt": 1,
                "iSpindel": 0
            }
        }
    """
    return jsonify({
        'success': True,
        'server': 'running',
        'timestamp': datetime.now().isoformat(),
        'active_sessions': {
            'brew': len(active_brew_sessions),
            'ferm': len(active_ferm_sessions),
            'still': len(active_still_sessions),
            'tilt': len(active_tilt_sessions),
            'iSpindel': len(active_iSpindel_sessions),
        }
    })


# =============================================================================
# Fermentation Sessions
# =============================================================================

@main.route('/API/Agent/ferm/active', methods=['GET'])
def agent_ferm_active():
    """
    Get all active fermentation sessions with current data.
    
    Returns:
        {
            "success": true,
            "sessions": [
                {
                    "uid": "FERM001",
                    "alias": "My Fermenter",
                    "active": true,
                    "start_date": "2026-02-01T10:30:00",
                    "target_abv": 5.5,
                    "current_temp_f": 68.5,
                    "current_pressure_psi": 10.2,
                    "fermentation_status": {...}
                }
            ]
        }
    """
    try:
        sessions = []
        for uid, session in active_ferm_sessions.items():
            # Get latest data point if available
            latest_temp = None
            latest_pressure = None
            if session.data and len(session.data) > 0:
                latest = session.data[-1]
                latest_temp = latest.get('temp')
                latest_pressure = latest.get('pres')
            
            sessions.append({
                'uid': uid,
                'alias': session.alias or uid,
                'active': session.active,
                'start_date': session.start_time.isoformat() if session.start_time else None,
                'target_abv': session.target_abv,
                'target_pressure_psi': session.target_pressure_psi,
                'current_temp_f': latest_temp,
                'current_pressure_psi': latest_pressure,
                'voltage': session.voltage,
                'data_points': len(session.data) if session.data else 0,
                'fermentation_status': session.get_fermentation_status() if hasattr(session, 'get_fermentation_status') else None,
            })
        
        return jsonify({
            'success': True,
            'count': len(sessions),
            'sessions': sessions,
        })
    except Exception as e:
        current_app.logger.error(f"Agent API error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@main.route('/API/Agent/ferm/history', methods=['GET'])
def agent_ferm_history():
    """
    Get fermentation session history (archived sessions).
    
    Query params:
        - limit: Max number of sessions (default: 10, max: 50)
        - offset: Pagination offset (default: 0)
    
    Returns:
        {
            "success": true,
            "sessions": [
                {
                    "uid": "FERM001",
                    "filename": "20260201_103000#FERM001.json",
                    "alias": "My Fermenter",
                    "start_date": "2026-02-01T10:30:00",
                    "end_date": "2026-02-07T15:45:00",
                    "duration_hours": 149.25
                }
            ]
        }
    """
    try:
        limit = min(request.args.get('limit', 10, type=int), 50)
        offset = request.args.get('offset', 0, type=int)
        
        sessions = []
        try:
            raw_sessions = load_ferm_sessions(None, offset, limit)
            for s in raw_sessions:
                duration = None
                if s.get('date') and s.get('end_date'):
                    try:
                        delta = s['end_date'] - s['date']
                        duration = round(delta.total_seconds() / 3600, 2)
                    except:
                        pass
                
                sessions.append({
                    'uid': s.get('uid'),
                    'filename': s.get('filename'),
                    'alias': s.get('alias'),
                    'name': s.get('name'),
                    'start_date': s['date'].isoformat() if s.get('date') else None,
                    'end_date': s['end_date'].isoformat() if s.get('end_date') else None,
                    'duration_hours': duration,
                })
        except Exception as e:
            # End of pagination or error
            current_app.logger.debug(f"Ferm history pagination: {e}")
        
        return jsonify({
            'success': True,
            'count': len(sessions),
            'offset': offset,
            'limit': limit,
            'sessions': sessions,
        })
    except Exception as e:
        current_app.logger.error(f"Agent API error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# Brew Sessions
# =============================================================================

@main.route('/API/Agent/brew/active', methods=['GET'])
def agent_brew_active():
    """
    Get all active brew sessions.
    """
    try:
        sessions = []
        for uid, session in active_brew_sessions.items():
            sessions.append({
                'uid': uid,
                'alias': session.alias or uid,
                'name': session.name,
                'active': session.active,
                'session_type': session.session_type.value if session.session_type else None,
                'start_date': session.created_at.isoformat() if session.created_at else None,
                'step': session.step,
                'recovery': session.recovery,
            })
        
        return jsonify({
            'success': True,
            'count': len(sessions),
            'sessions': sessions,
        })
    except Exception as e:
        current_app.logger.error(f"Agent API error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@main.route('/API/Agent/brew/history', methods=['GET'])
def agent_brew_history():
    """
    Get brew session history (archived sessions).
    """
    try:
        limit = min(request.args.get('limit', 10, type=int), 50)
        offset = request.args.get('offset', 0, type=int)
        
        sessions = []
        try:
            raw_sessions = load_brew_sessions(None, offset, limit)
            for s in raw_sessions:
                sessions.append({
                    'uid': s.get('uid'),
                    'filename': s.get('filename'),
                    'alias': s.get('alias'),
                    'name': s.get('name'),
                    'date': s['date'].isoformat() if s.get('date') else None,
                    'type': s.get('type'),
                    'machine': s.get('machine'),
                })
        except Exception as e:
            current_app.logger.debug(f"Brew history pagination: {e}")
        
        return jsonify({
            'success': True,
            'count': len(sessions),
            'offset': offset,
            'limit': limit,
            'sessions': sessions,
        })
    except Exception as e:
        current_app.logger.error(f"Agent API error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# Tilt Sessions
# =============================================================================

@main.route('/API/Agent/tilt/active', methods=['GET'])
def agent_tilt_active():
    """
    Get all active Tilt hydrometer sessions.
    """
    try:
        sessions = []
        for uid, session in active_tilt_sessions.items():
            latest_gravity = None
            latest_temp = None
            if session.data and len(session.data) > 0:
                latest = session.data[-1]
                latest_gravity = latest.get('gravity')
                latest_temp = latest.get('temp')
            
            sessions.append({
                'uid': uid,
                'color': session.color if hasattr(session, 'color') else uid,
                'alias': session.alias or uid,
                'active': session.active,
                'start_date': session.created_at.isoformat() if session.created_at else None,
                'current_gravity': latest_gravity,
                'current_temp_f': latest_temp,
                'data_points': len(session.data) if session.data else 0,
            })
        
        return jsonify({
            'success': True,
            'count': len(sessions),
            'sessions': sessions,
        })
    except Exception as e:
        current_app.logger.error(f"Agent API error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@main.route('/API/Agent/tilt/history', methods=['GET'])
def agent_tilt_history():
    """
    Get Tilt session history.
    """
    try:
        limit = min(request.args.get('limit', 10, type=int), 50)
        offset = request.args.get('offset', 0, type=int)
        
        sessions = []
        try:
            raw_sessions = load_tilt_sessions(None, offset, limit)
            for s in raw_sessions:
                sessions.append({
                    'uid': s.get('uid'),
                    'filename': s.get('filename'),
                    'alias': s.get('alias'),
                    'name': s.get('name'),
                    'start_date': s['date'].isoformat() if s.get('date') else None,
                    'end_date': s['end_date'].isoformat() if s.get('end_date') else None,
                })
        except Exception as e:
            current_app.logger.debug(f"Tilt history pagination: {e}")
        
        return jsonify({
            'success': True,
            'count': len(sessions),
            'sessions': sessions,
        })
    except Exception as e:
        current_app.logger.error(f"Agent API error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# iSpindel Sessions
# =============================================================================

@main.route('/API/Agent/iSpindel/active', methods=['GET'])
def agent_ispindel_active():
    """
    Get all active iSpindel sessions.
    """
    try:
        sessions = []
        for uid, session in active_iSpindel_sessions.items():
            latest_gravity = None
            latest_temp = None
            latest_battery = None
            if session.data and len(session.data) > 0:
                latest = session.data[-1]
                latest_gravity = latest.get('gravity')
                latest_temp = latest.get('temp')
                latest_battery = latest.get('battery')
            
            sessions.append({
                'uid': uid,
                'alias': session.alias or uid,
                'active': session.active,
                'start_date': session.created_at.isoformat() if session.created_at else None,
                'current_gravity': latest_gravity,
                'current_temp_c': latest_temp,
                'battery_voltage': latest_battery,
                'data_points': len(session.data) if session.data else 0,
            })
        
        return jsonify({
            'success': True,
            'count': len(sessions),
            'sessions': sessions,
        })
    except Exception as e:
        current_app.logger.error(f"Agent API error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# Recipes
# =============================================================================

@main.route('/API/Agent/recipes/<device_type>', methods=['GET'])
def agent_list_recipes(device_type):
    """
    List all recipes for a device type.
    
    Args:
        device_type: 'pico', 'zymatic', or 'zseries'
    
    Returns:
        {
            "success": true,
            "device_type": "zymatic",
            "recipes": [
                {"id": "abc123", "name": "My IPA", "filename": "My_IPA.json"}
            ]
        }
    """
    try:
        device_map = {
            'pico': MachineType.PICOBREW,
            'zymatic': MachineType.ZYMATIC,
            'zseries': MachineType.ZSERIES,
        }
        
        if device_type.lower() not in device_map:
            return jsonify({
                'success': False,
                'error': f"Invalid device type: {device_type}. Use 'pico', 'zymatic', or 'zseries'"
            }), 400
        
        machine_type = device_map[device_type.lower()]
        path = recipe_path(machine_type)
        
        recipes = []
        recipe_files = list(path.glob("*.json"))
        
        for filepath in sorted(recipe_files):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                
                # Handle different recipe formats
                if isinstance(data, list):
                    # Some formats store recipe as array
                    recipe_data = data[0] if len(data) > 0 else {}
                else:
                    recipe_data = data
                
                recipes.append({
                    'filename': filepath.name,
                    'id': recipe_data.get('id', filepath.stem),
                    'name': recipe_data.get('name', filepath.stem),
                    'abv': recipe_data.get('abv') or recipe_data.get('ABV'),
                    'ibu': recipe_data.get('ibu') or recipe_data.get('IBU'),
                })
            except Exception as e:
                current_app.logger.warning(f"Could not parse recipe {filepath}: {e}")
                recipes.append({
                    'filename': filepath.name,
                    'name': filepath.stem,
                    'parse_error': True,
                })
        
        return jsonify({
            'success': True,
            'device_type': device_type.lower(),
            'count': len(recipes),
            'recipes': recipes,
        })
    except Exception as e:
        current_app.logger.error(f"Agent API error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@main.route('/API/Agent/recipes/<device_type>/<filename>', methods=['GET'])
def agent_get_recipe(device_type, filename):
    """
    Get full details of a specific recipe.
    """
    try:
        device_map = {
            'pico': MachineType.PICOBREW,
            'zymatic': MachineType.ZYMATIC,
            'zseries': MachineType.ZSERIES,
        }
        
        if device_type.lower() not in device_map:
            return jsonify({
                'success': False,
                'error': f"Invalid device type: {device_type}"
            }), 400
        
        machine_type = device_map[device_type.lower()]
        path = recipe_path(machine_type)
        
        # Ensure filename ends with .json
        if not filename.endswith('.json'):
            filename = f"{filename}.json"
        
        filepath = path / filename
        
        if not filepath.exists():
            return jsonify({
                'success': False,
                'error': f"Recipe not found: {filename}"
            }), 404
        
        with open(filepath, 'r') as f:
            recipe_data = json.load(f)
        
        return jsonify({
            'success': True,
            'device_type': device_type.lower(),
            'filename': filename,
            'recipe': recipe_data,
        })
    except Exception as e:
        current_app.logger.error(f"Agent API error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# Devices
# =============================================================================

@main.route('/API/Agent/devices', methods=['GET'])
def agent_list_devices():
    """
    List all registered devices and their current status.
    """
    try:
        devices = []
        
        # Brew machines (from active sessions)
        for uid, session in active_brew_sessions.items():
            devices.append({
                'uid': uid,
                'alias': session.alias or uid,
                'type': 'brew',
                'machine_type': session.session_type.value if session.session_type else 'unknown',
                'active': session.active,
            })
        
        # PicoFerm devices
        for uid, session in active_ferm_sessions.items():
            devices.append({
                'uid': uid,
                'alias': session.alias or uid,
                'type': 'ferm',
                'active': session.active,
                'voltage': session.voltage,
            })
        
        # PicoStill devices
        for uid, session in active_still_sessions.items():
            devices.append({
                'uid': uid,
                'alias': session.alias or uid,
                'type': 'still',
                'active': session.active,
                'ip_address': session.ip_address if hasattr(session, 'ip_address') else None,
            })
        
        # Tilt devices
        for uid, session in active_tilt_sessions.items():
            devices.append({
                'uid': uid,
                'alias': session.alias or uid,
                'type': 'tilt',
                'color': session.color if hasattr(session, 'color') else None,
                'active': session.active,
            })
        
        # iSpindel devices
        for uid, session in active_iSpindel_sessions.items():
            devices.append({
                'uid': uid,
                'alias': session.alias or uid,
                'type': 'iSpindel',
                'active': session.active,
            })
        
        return jsonify({
            'success': True,
            'count': len(devices),
            'devices': devices,
        })
    except Exception as e:
        current_app.logger.error(f"Agent API error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# Recipe Save Paths (for file-based recipe saving)
# =============================================================================

@main.route('/API/Agent/recipePaths', methods=['GET'])
def agent_recipe_paths():
    """
    Get the file system paths where recipes should be saved for each device type.
    
    This allows agents to write recipe files directly to the file system,
    avoiding HTTP POST escaping issues with complex JSON/XML payloads.
    
    Returns:
        {
            "success": true,
            "paths": {
                "pico": "/path/to/recipes/pico",
                "zymatic": "/path/to/recipes/zymatic",
                "zseries": "/path/to/recipes/zseries"
            },
            "examples": {
                "zymatic": { ... sample recipe structure ... }
            }
        }
    """
    try:
        import uuid
        
        paths = {
            'pico': str(recipe_path(MachineType.PICOBREW)),
            'zymatic': str(recipe_path(MachineType.ZYMATIC)),
            'zseries': str(recipe_path(MachineType.ZSERIES)),
        }
        
        # Sample Zymatic recipe structure
        zymatic_example = {
            "id": uuid.uuid4().hex[:32],
            "name": "Example IPA",
            "notes": "Dry hop Day 3-4: Citra 1oz, Mosaic 0.75oz",
            "steps": [
                {"name": "Dough In", "temp": 110, "time": 5, "drain": 0, "location": "PassThru"},
                {"name": "Heating", "temp": 110, "time": 0, "drain": 0, "location": "PassThru"},
                {"name": "Sacch Rest", "temp": 152, "time": 45, "drain": 0, "location": "Mash"},
                {"name": "Mash Out", "temp": 170, "time": 10, "drain": 5, "location": "Mash"},
                {"name": "Heat to Boil", "temp": 207, "time": 0, "drain": 0, "location": "PassThru"},
                {"name": "Boil Adjunct 1", "temp": 207, "time": 30, "drain": 0, "location": "Adjunct1"},
                {"name": "Boil Adjunct 2", "temp": 207, "time": 10, "drain": 0, "location": "Adjunct2"},
                {"name": "Boil Adjunct 3", "temp": 207, "time": 5, "drain": 0, "location": "Adjunct3"},
                {"name": "Boil Adjunct 4", "temp": 207, "time": 5, "drain": 0, "location": "Adjunct4"},
                {"name": "Connect Chiller", "temp": 207, "time": 5, "drain": 0, "location": "Pause"},
                {"name": "Chill", "temp": 66, "time": 10, "drain": 10, "location": "PassThru"}
            ]
        }
        
        # Sample Pico recipe structure
        pico_example = {
            "id": uuid.uuid4().hex[:14].upper(),
            "name": "Example IPA",
            "notes": "Dry hop Day 3-4: Citra 1oz, Mosaic 0.75oz",
            "abv_tweak": 0,
            "ibu_tweak": 0,
            "steps": [
                {"name": "Mash", "temp": 152, "time": 45, "location": 0, "step_type": 0, "drain_time": 0},
                {"name": "Mash Out", "temp": 170, "time": 10, "location": 0, "step_type": 0, "drain_time": 300},
                {"name": "Boil Adj 1", "temp": 207, "time": 30, "location": 1, "step_type": 1, "drain_time": 0},
                {"name": "Boil Adj 2", "temp": 207, "time": 10, "location": 2, "step_type": 1, "drain_time": 0},
                {"name": "Boil Adj 3", "temp": 207, "time": 5, "location": 3, "step_type": 1, "drain_time": 0},
                {"name": "Boil Adj 4", "temp": 207, "time": 5, "location": 4, "step_type": 1, "drain_time": 0}
            ]
        }
        
        return jsonify({
            'success': True,
            'paths': paths,
            'file_naming': 'Use recipe name with spaces replaced by underscores: My_Recipe_Name.json',
            'examples': {
                'zymatic': zymatic_example,
                'pico': pico_example,
            },
            'instructions': [
                '1. Get the path for your device type from the paths object',
                '2. Create a JSON file with the recipe structure (see examples)',
                '3. Save it to: {path}/{Recipe_Name}.json',
                '4. The recipe will appear in the server immediately',
            ]
        })
    except Exception as e:
        current_app.logger.error(f"Agent API error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@main.route('/API/Agent/uploadRecipe', methods=['POST'])
def agent_upload_recipe():
    """
    Upload a recipe JSON file to the server.
    
    This endpoint accepts recipe files via:
    1. File upload (multipart/form-data with 'file' field)
    2. Raw JSON body with 'recipe' and 'device_type' fields
    3. Base64-encoded JSON in 'recipe_base64' field (for agents with escaping issues)
    
    Required fields:
        - device_type: 'pico', 'zymatic', or 'zseries'
        - recipe content via one of the methods above
    
    Returns:
        {
            "success": true,
            "message": "Recipe saved successfully",
            "filename": "Recipe_Name.json",
            "path": "/path/to/recipes/zymatic/Recipe_Name.json"
        }
    """
    try:
        import uuid
        import base64
        
        recipe_data = None
        device_type = None
        
        # Method 1: File upload
        if request.content_type and 'multipart/form-data' in request.content_type:
            if 'file' not in request.files:
                return jsonify({'success': False, 'error': 'No file uploaded'}), 400
            
            file = request.files['file']
            device_type = request.form.get('device_type', 'zymatic')
            
            try:
                recipe_data = json.loads(file.read().decode('utf-8'))
            except json.JSONDecodeError as e:
                return jsonify({'success': False, 'error': f'Invalid JSON in file: {e}'}), 400
        
        # Method 2 & 3: JSON body
        else:
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'error': 'No data provided'}), 400
            
            device_type = data.get('device_type', 'zymatic')
            
            # Check for base64-encoded recipe (Method 3)
            if 'recipe_base64' in data:
                try:
                    decoded = base64.b64decode(data['recipe_base64']).decode('utf-8')
                    recipe_data = json.loads(decoded)
                except Exception as e:
                    return jsonify({'success': False, 'error': f'Failed to decode base64 recipe: {e}'}), 400
            
            # Direct JSON recipe (Method 2)
            elif 'recipe' in data:
                recipe_data = data['recipe']
            
            else:
                return jsonify({'success': False, 'error': 'No recipe provided. Use "recipe", "recipe_base64", or file upload'}), 400
        
        # Validate recipe has required fields
        if not recipe_data:
            return jsonify({'success': False, 'error': 'Empty recipe data'}), 400
        
        if 'name' not in recipe_data:
            return jsonify({'success': False, 'error': 'Recipe must have a "name" field'}), 400
        
        if 'steps' not in recipe_data:
            return jsonify({'success': False, 'error': 'Recipe must have a "steps" array'}), 400
        
        # Generate ID if not provided
        if 'id' not in recipe_data:
            if device_type.lower() == 'pico':
                recipe_data['id'] = uuid.uuid4().hex[:14].upper()
            else:
                recipe_data['id'] = uuid.uuid4().hex[:32]
        
        # Validate step locations against device type
        from .model import PICO_LOCATION, ZYMATIC_LOCATION, ZSERIES_LOCATION
        
        location_map = {
            'pico': PICO_LOCATION,
            'zymatic': ZYMATIC_LOCATION,
            'zseries': ZSERIES_LOCATION,
        }
        
        valid_locations = location_map.get(device_type.lower(), ZYMATIC_LOCATION)
        invalid_steps = []
        
        for i, step in enumerate(recipe_data.get('steps', [])):
            location = step.get('location', '')
            if location and location not in valid_locations:
                invalid_steps.append({
                    'step_index': i,
                    'step_name': step.get('name', f'Step {i}'),
                    'invalid_location': location,
                    'valid_locations': list(valid_locations.keys())
                })
        
        if invalid_steps:
            return jsonify({
                'success': False,
                'error': f'Recipe contains {len(invalid_steps)} step(s) with invalid locations for {device_type}',
                'invalid_steps': invalid_steps,
                'hint': f'Valid locations for {device_type}: {list(valid_locations.keys())}'
            }), 400
        
        # Get the appropriate path
        device_map = {
            'pico': MachineType.PICOBREW,
            'zymatic': MachineType.ZYMATIC,
            'zseries': MachineType.ZSERIES,
        }
        
        if device_type.lower() not in device_map:
            return jsonify({'success': False, 'error': f'Invalid device_type: {device_type}. Use pico, zymatic, or zseries'}), 400
        
        machine_type = device_map[device_type.lower()]
        path = recipe_path(machine_type)
        
        # Generate filename
        name = recipe_data['name']
        filename = name.replace(' ', '_').replace("'", "").replace('"', '') + '.json'
        filepath = path / filename
        
        # Don't overwrite existing recipes without explicit flag
        if filepath.exists():
            overwrite = False
            if request.content_type and 'multipart/form-data' in request.content_type:
                overwrite = request.form.get('overwrite', 'false').lower() == 'true'
            elif request.get_json():
                overwrite = request.get_json().get('overwrite', False)
            
            if not overwrite:
                return jsonify({
                    'success': False, 
                    'error': f'Recipe "{filename}" already exists. Set overwrite=true to replace it.'
                }), 409
        
        # Save the recipe
        with open(filepath, 'w') as f:
            json.dump(recipe_data, f, indent=4)
        
        current_app.logger.info(f"Agent uploaded recipe: {filepath}")
        
        return jsonify({
            'success': True,
            'message': 'Recipe saved successfully',
            'filename': filename,
            'path': str(filepath),
            'device_type': device_type,
            'recipe_name': name,
        })
        
    except Exception as e:
        current_app.logger.error(f"Agent upload recipe error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
