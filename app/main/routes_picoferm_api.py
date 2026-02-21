import json
from datetime import datetime
from flask import current_app, send_from_directory, request
from webargs import fields
from webargs.flaskparser import use_args, FlaskParser

from . import main
from .. import socketio
from .config import ferm_active_sessions_path, firmware_path, MachineType
from .firmware import firmware_filename, minimum_firmware, firmware_upgrade_required
from .model import PicoFermSession
from .session_parser import active_ferm_sessions
from .fermentation_calculator import get_fermentation_status, analyze_session_data

arg_parser = FlaskParser()


# Custom JSON encoder to handle datetime objects
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def json_dumps(obj):
    """JSON dumps with datetime support."""
    return json.dumps(obj, cls=DateTimeEncoder)


# Register: /API/PicoFerm/isRegistered?uid={uid}&token={token}
# Response: '#{0}#' where {0} : 1 = Registered, 0 = Not Registered
ferm_registered_args = {
    'uid': fields.Str(required=True),       # 12 character alpha-numeric serial number
    'token': fields.Str(required=True),    # 8 character alpha-numberic number
}


@main.route('/API/PicoFerm/isRegistered')
@use_args(ferm_registered_args, location='querystring')
def process_ferm_registered(args):
    uid = args['uid']
    if uid not in active_ferm_sessions:
        active_ferm_sessions[uid] = PicoFermSession()
    return '#1#'


# Check Firmware: /API/PicoFerm/checkFirmware?uid={UID}&version={VERSION}
#           Response: '#{0}#' where {0} : 1 = Update Available, 0 = No Updates
check_ferm_firmware_args = {
    'uid': fields.Str(required=True),       # 12 character alpha-numeric serial number
    'version': fields.Str(required=True),   # Current firmware version - i.e. 0.1.11
}


@main.route('/API/PicoFerm/checkFirmware')
@use_args(check_ferm_firmware_args, location='querystring')
def process_check_ferm_firmware(args):
    if firmware_upgrade_required(MachineType.PICOFERM, args['version']):
        return '#1#'
    return '#0#'


# Get Firmware: /API/pico/getFirmware?uid={UID}
#     Response: RAW Bin File Contents
get_firmware_args = {
    'uid': fields.Str(required=True),       # 12 character alpha-numeric serial number
}


@main.route('/API/PicoFerm/getFirmwareAddress')
@use_args(get_firmware_args, location='querystring')
def process_get_firmware_address(args):
    filename = firmware_filename(MachineType.PICOFERM, minimum_firmware(MachineType.PICOFERM))
    return '#http://picobrew.com/firmware/picoferm/{}#'.format(filename)


# Get Firmware: /firmware/picoferm/<version>
#     Response: RAW Bin File
@main.route('/firmware/picoferm/<file>', methods=['GET'])
def process_picoferm_firmware(file):
    current_app.logger.debug('DEBUG: PicoFerm fetch firmware file={}'.format(file))
    return send_from_directory(firmware_path(MachineType.PICOFERM), file)


# Get State: /API/PicoFerm/getState?uid={UID}
#  Response: '#{0}#' where {0} : 2,4 = nothing to do, 10,0 = in progress/send data, 10,16 = in progress/error, 2,16 = complete/stop sending data
get_ferm_state_args = {
    'uid': fields.Str(required=True),   # 12 character alpha-numeric serial number
}


@main.route('/API/PicoFerm/getState')
@use_args(get_ferm_state_args, location='querystring')
def process_get_ferm_state(args):
    uid = args['uid']
    if uid not in active_ferm_sessions:
        active_ferm_sessions[uid] = PicoFermSession()

    session = active_ferm_sessions[uid]

    if session.active == True:
        return '#10,0#'
    elif session.uninit or session.file == None:
        return '#2,4'


# LogDataSet: /API/PicoFerm/logDataSet?uid={UID}&rate={RATE}&voltage={VOLTAGE}&data={DATA}
#   Response: '#{0}#' where {0} : 10,0 = in progress/send data, ?????
log_ferm_dataset_args = {
    'uid': fields.Str(required=True),        # 12 character alpha-numeric serial number
    'rate': fields.Float(required=True),     # Rate between samples (minutes)
    'voltage': fields.Float(required=True),  # %0.2f Voltage
    'data': fields.Str(required=True),       # List of dictionary (Temperature (S1), Pressure (S2)): [{"s1":%0.2f,"s2":%0.2f},]
}


@main.route('/API/PicoFerm/logDataSet')
@use_args(log_ferm_dataset_args, location='querystring')
def process_log_ferm_dataset(args):
    uid = args['uid']

    if uid not in active_ferm_sessions or active_ferm_sessions[uid].uninit:
        create_new_session(uid)

    data = json.loads(args['data'])
    time_delta = args['rate'] * 60 * 1000
    time = ((datetime.utcnow() - datetime(1970, 1, 1)).total_seconds() * 1000) - (time_delta * (len(data) - 1))

    session_data = []
    log_data = ''
    for d in data:
        point = {'time': time,
                 'temp': d['s1'],
                 'pres': d['s2'],
                 }
        session_data.append(point)
        time = time + time_delta
        log_data += '\n\t{},'.format(json.dumps(point))

    active_ferm_sessions[uid].data.extend(session_data)
    active_ferm_sessions[uid].voltage = str(args['voltage']) + 'V'
    
    # Trim in-memory data to prevent unbounded memory growth on long fermentations
    active_ferm_sessions[uid].trim_data_if_needed()
    
    # Get fermentation status for the update (result is cached for should_auto_complete below)
    ferm_status = active_ferm_sessions[uid].get_fermentation_status()
    
    graph_update = json_dumps({
        'voltage': args['voltage'], 
        'data': session_data,
        'fermentation_status': ferm_status
    })
    socketio.emit('ferm_session_update|{}'.format(args['uid']), graph_update)
    
    # Also emit a dedicated status update for UI components
    if ferm_status['can_estimate']:
        socketio.emit('ferm_status_update|{}'.format(args['uid']), json_dumps(ferm_status))

    # Check for auto-completion based on fermentation time estimates
    session = active_ferm_sessions[uid]
    should_auto_complete = session.should_auto_complete()
    
    # end fermentation when: user specifies complete OR auto-complete triggers
    if session.uninit == False and (session.active == False or should_auto_complete):
        if should_auto_complete:
            current_app.logger.info(f'PicoFerm {uid}: Auto-completing fermentation based on time estimate')
            socketio.emit('ferm_auto_complete|{}'.format(uid), json_dumps({
                'uid': uid,
                'reason': 'Estimated fermentation time reached',
                'status': ferm_status
            }))
        session.file.write('{}\n\n]'.format(log_data[:-2]))
        session.cleanup()
        # The server makes a determination when fermenting is done based on the datalog after it sends '2,4'
        return '#2,4#'
    else:
        session.active = True
        session.file.write(log_data)
        session.file.flush()
        # Errors like '10,16' send data but mark data error.
        # '10,0' tells the PicoFerm to continue to send data.
        return '#10,0#'


# -------- Fermentation Settings API --------

# Set Fermentation Parameters: POST /API/PicoFerm/setFermentationParams
# Allows user to set ABV target and other fermentation parameters
set_ferm_params_args = {
    'uid': fields.Str(required=True),              # Device UID
    'target_abv': fields.Float(required=False),    # Target ABV percentage (e.g., 5.5 for 5.5%)
    'target_pressure_psi': fields.Float(required=False, load_default=5.0),  # Target pressure in PSI
    'auto_complete': fields.Bool(required=False, load_default=True),        # Auto-complete when done
    'use_conservative': fields.Bool(required=False, load_default=True),     # Use conservative estimate
}


@main.route('/API/PicoFerm/setFermentationParams', methods=['POST'])
@use_args(set_ferm_params_args, location='json')
def set_fermentation_params(args):
    """Set fermentation parameters for a PicoFerm session."""
    uid = args['uid']
    
    if uid not in active_ferm_sessions:
        active_ferm_sessions[uid] = PicoFermSession()
    
    session = active_ferm_sessions[uid]
    
    if 'target_abv' in args and args['target_abv'] is not None:
        session.target_abv = args['target_abv']
        current_app.logger.info(f'PicoFerm {uid}: Set target ABV to {session.target_abv}%')
    
    if 'target_pressure_psi' in args:
        session.target_pressure_psi = args['target_pressure_psi']
    
    if 'auto_complete' in args:
        session.auto_complete = args['auto_complete']
    
    if 'use_conservative' in args:
        session.use_conservative = args['use_conservative']
    
    # Persist metadata to disk so it survives restarts
    session.save_metadata()
    
    # Return current status
    status = session.get_fermentation_status()
    return json_dumps({
        'success': True,
        'uid': uid,
        'target_abv': session.target_abv,
        'target_pressure_psi': session.target_pressure_psi,
        'auto_complete': session.auto_complete,
        'use_conservative': session.use_conservative,
        'fermentation_status': status
    }), 200, {'Content-Type': 'application/json'}


# Get Fermentation Status: GET /API/PicoFerm/getFermentationStatus
# Returns current fermentation status and time estimates
get_ferm_status_args = {
    'uid': fields.Str(required=True),
}


@main.route('/API/PicoFerm/getFermentationStatus')
@use_args(get_ferm_status_args, location='querystring')
def get_ferm_status(args):
    """Get current fermentation status including time estimates."""
    uid = args['uid']
    
    if uid not in active_ferm_sessions:
        return json_dumps({
            'success': False,
            'error': 'No active session for this device'
        }), 404, {'Content-Type': 'application/json'}
    
    session = active_ferm_sessions[uid]
    status = session.get_fermentation_status()
    
    return json_dumps({
        'success': True,
        'uid': uid,
        'active': session.active,
        'target_abv': session.target_abv,
        'target_pressure_psi': session.target_pressure_psi,
        'auto_complete': session.auto_complete,
        'start_time': session.start_time.isoformat() if session.start_time else None,
        'voltage': session.voltage,
        'data_points': len(session.data),
        'fermentation_status': status
    }), 200, {'Content-Type': 'application/json'}


# -------- Utility --------
def create_new_session(uid):
    if uid not in active_ferm_sessions:
        active_ferm_sessions[uid] = PicoFermSession()
    active_ferm_sessions[uid].uninit = False
    active_ferm_sessions[uid].start_time = datetime.now()  # Not now, but X interval seconds ago
    active_ferm_sessions[uid].filepath = ferm_active_sessions_path().joinpath('{0}#{1}.json'.format(active_ferm_sessions[uid].start_time.strftime('%Y%m%d_%H%M%S'), uid))
    active_ferm_sessions[uid].file = open(active_ferm_sessions[uid].filepath, 'w')
    active_ferm_sessions[uid].file.write('[')
    # Save initial metadata (start_time) so it persists across restarts
    active_ferm_sessions[uid].save_metadata()
