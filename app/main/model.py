from flask import current_app
from pathlib import Path
import requests
import shutil
import json

from .config import (MachineType, brew_archive_sessions_path, ferm_archive_sessions_path,
                     still_archive_sessions_path, iSpindel_archive_sessions_path, tilt_archive_sessions_path)

ZYMATIC_LOCATION = {
    'PassThru': '0',
    'Mash': '1',
    'Adjunct1': '2',
    'Adjunct2': '3',
    'Adjunct3': '4',
    'Adjunct4': '5',
    'Pause': '6',
}

ZSERIES_LOCATION = {
    'PassThru': '0',
    'Mash': '1',
    'Adjunct1': '2',
    'Adjunct2': '3',
    'Adjunct3': '4',
    'Adjunct4': '5',
    'Pause': '6',
}

PICO_LOCATION = {
    'Prime': '0',
    'Mash': '1',
    'PassThru': '2',
    'Adjunct1': '3',
    'Adjunct2': '4',
    'Adjunct3': '6',
    'Adjunct4': '5',
}

PICO_SESSION = {
    0: 'Brewing',
    1: 'Deep Clean',
    2: 'Sous Vide',
    4: 'Cold Brew',
    5: 'Manual Brew',
}


class PicoBrewSession:
    def __init__(self, machineType=None):
        self.file = None
        self.filepath = None
        self.alias = ''
        self.machine_type = machineType
        self.created_at = None
        self.name = 'Waiting To Brew'
        self.type = 0
        self.step = ''
        self.session = ''   # session guid
        self.id = -1        # session id (integer)
        self.recovery = ''
        self.remaining_time = None
        self.is_pico = True if machineType in [MachineType.PICOBREW, MachineType.PICOBREW_C, MachineType.PICOBREW_C_ALT] else False
        self.has_alt_firmware = True if machineType in [MachineType.PICOBREW_C_ALT] else False
        self.needs_firmware = False
        self.boiler_type = None   # Z machines have 2 different configurations: 1 (big) or 2 (small)
        self.data = []

    def cleanup(self):
        if self.file and self.filepath:
            self.file.close()
            shutil.move(str(self.filepath), str(brew_archive_sessions_path()))
        self.file = None
        self.filepath = None
        self.created_at = None
        self.name = 'Waiting To Brew'
        self.type = 0
        self.step = ''
        self.session = ''
        self.id = -1
        self.recovery = ''
        self.remaining_time = None
        self.data = []


class PicoStillSession:
    def __init__(self, uid=None):
        self.file = None
        self.filepath = None
        self.alias = ''
        self.ip_address = None
        self.device_id = uid
        self.uninit = True
        self.created_at = None
        self.name = 'Waiting To Distill'
        self.active = False
        self.session = ''   # session guid
        self.polling_thread = None
        self.data = []

    def cleanup(self):
        if self.file and self.filepath:
            self.file.close()
            shutil.move(str(self.filepath), str(still_archive_sessions_path()))
        self.file = None
        self.filepath = None
        self.uninit = True
        self.created_at = None
        self.name = 'Waiting To Distill'
        self.active = False
        self.polling_thread = None
        self.session = ''
        self.data = []

    def start_still_polling(self):
        connect_failure = False
        failure_message = None
        still_data_uri = 'http://{}/data'.format(self.ip_address)
        try:
            current_app.logger.debug('DEBUG: Retrieve PicoStill Data - {}'.format(still_data_uri))
            r = requests.get(still_data_uri)
            datastring = r.text.strip()
        except Exception as e:
            current_app.logger.error(f'exception occured communicating to picostill {still_data_uri} : {e}')
            failure_message = f'unable to estaablish successful connection to {still_data_uri}'
            datastring = None
            connect_failure = True

        if not datastring or datastring[0] != '#':
            connect_failure = True
            failure_message = f'received unexpected response string from {still_data_uri}'
            current_app.logger.error(f'{failure_message} : {datastring}')

        if connect_failure:
            raise Exception(f'Failed to Start PicoStill Monitoring: {failure_message}')

        from .still_polling import new_still_session
        from .still_polling import FlaskThread

        thread = FlaskThread(target=new_still_session,
                             args=(self.ip_address, self.device_id),
                             daemon=True)
        thread.start()
        self.polling_thread = thread


class PicoFermSession:
    # Maximum data points to keep in memory. Older points are downsampled.
    # At 1-min intervals this is ~2.8 days of full-resolution data.
    # Older data is summarized (averaged per hour) to keep memory bounded.
    MAX_DATA_POINTS = 4000
    # When trimming, keep this many of the most recent full-resolution points
    RECENT_POINTS_TO_KEEP = 2000

    def __init__(self):
        self.file = None
        self.filepath = None
        self.alias = ''
        self.active = False
        self.uninit = True
        self.voltage = '-'
        self.start_time = None
        self.data = []
        self._summary_data = []  # Downsampled older data points
        # Fermentation completion tracking
        self.target_abv = None          # User-specified target ABV (%)
        self.target_pressure_psi = 5.0  # Target fermentation pressure (PSI)
        self.auto_complete = True       # Auto-complete when estimated time reached
        self.use_conservative = True    # Use conservative (longer) time estimate
        # Cached fermentation status to avoid redundant computation
        self._cached_status = None
        self._cache_data_len = 0

    def cleanup(self):
        # Clean up metadata file first (before filepath is cleared)
        self.cleanup_metadata()
        if self.file and self.filepath:
            self.file.close()
            shutil.move(str(self.filepath), str(ferm_archive_sessions_path()))
        self.file = None
        self.filepath = None
        self.uninit = True
        self.voltage = '-'
        self.start_time = None
        self.data = []
        self._summary_data = []
        self.target_abv = None
        self.target_pressure_psi = 5.0
        self.auto_complete = True
        self.use_conservative = True
        self._cached_status = None
        self._cache_data_len = 0

    def trim_data_if_needed(self):
        """Downsample older data points to keep memory usage bounded.
        
        When data exceeds MAX_DATA_POINTS, older points are averaged
        into hourly summaries and moved to _summary_data. Only the
        most recent RECENT_POINTS_TO_KEEP are kept at full resolution.
        """
        if len(self.data) <= self.MAX_DATA_POINTS:
            return

        # Split: keep recent points at full resolution, summarize the rest
        cutoff = len(self.data) - self.RECENT_POINTS_TO_KEEP
        old_points = self.data[:cutoff]
        self.data = self.data[cutoff:]

        # Group old points by hour and average them
        hourly_buckets = {}
        for p in old_points:
            # Use hour-level granularity for bucketing
            t = p.get('time', 0)
            hour_key = int(t // 3600000) * 3600000  # Round to hour in millis
            if hour_key not in hourly_buckets:
                hourly_buckets[hour_key] = []
            hourly_buckets[hour_key].append(p)

        for hour_key in sorted(hourly_buckets.keys()):
            bucket = hourly_buckets[hour_key]
            avg_point = {
                'time': sum(p.get('time', 0) for p in bucket) / len(bucket),
                'temp': sum(p.get('temp', 0) for p in bucket) / len(bucket),
                'pres': sum(p.get('pres', 0) for p in bucket) / len(bucket),
            }
            self._summary_data.append(avg_point)

    def get_all_data_for_analysis(self):
        """Return summary + recent data combined for fermentation analysis."""
        return self._summary_data + self.data

    def get_fermentation_status(self):
        """Get current fermentation status and estimates.
        
        Uses a simple cache: recalculates only when new data has arrived.
        """
        current_len = len(self.data) + len(self._summary_data)
        if self._cached_status is not None and self._cache_data_len == current_len:
            return self._cached_status

        from .fermentation_calculator import get_fermentation_status
        self._cached_status = get_fermentation_status(
            self.start_time,
            self.target_abv,
            self.get_all_data_for_analysis()
        )
        self._cache_data_len = current_len
        return self._cached_status

    def should_auto_complete(self):
        """Check if fermentation should auto-complete based on time estimates.
        
        Reuses cached status from get_fermentation_status() to avoid
        redundant computation.
        """
        if not self.auto_complete or self.target_abv is None:
            return False
        status = self.get_fermentation_status()
        return status.get('should_complete', False)

    def get_metadata_path(self):
        """Get the path for the metadata sidecar file."""
        if self.filepath:
            return Path(str(self.filepath) + '.meta')
        return None

    def save_metadata(self):
        """Save session metadata to a sidecar file for persistence across restarts."""
        meta_path = self.get_metadata_path()
        if meta_path:
            metadata = {
                'target_abv': self.target_abv,
                'target_pressure_psi': self.target_pressure_psi,
                'auto_complete': self.auto_complete,
                'use_conservative': self.use_conservative,
                'start_time': self.start_time.isoformat() if self.start_time else None,
                'alias': self.alias,
            }
            try:
                with open(meta_path, 'w') as f:
                    json.dump(metadata, f, indent=2)
            except Exception as e:
                print(f"Error saving fermentation metadata: {e}")

    def load_metadata(self):
        """Load session metadata from a sidecar file."""
        meta_path = self.get_metadata_path()
        if meta_path and meta_path.exists():
            try:
                with open(meta_path, 'r') as f:
                    metadata = json.load(f)
                self.target_abv = metadata.get('target_abv')
                self.target_pressure_psi = metadata.get('target_pressure_psi', 5.0)
                self.auto_complete = metadata.get('auto_complete', True)
                self.use_conservative = metadata.get('use_conservative', True)
                if metadata.get('start_time'):
                    from datetime import datetime
                    self.start_time = datetime.fromisoformat(metadata['start_time'])
                self.alias = metadata.get('alias', '')
                return True
            except Exception as e:
                print(f"Error loading fermentation metadata: {e}")
        return False

    def cleanup_metadata(self):
        """Remove the metadata sidecar file."""
        meta_path = self.get_metadata_path()
        if meta_path and meta_path.exists():
            try:
                meta_path.unlink()
            except Exception:
                pass


class iSpindelSession:
    def __init__(self):
        self.file = None
        self.filepath = None
        self.alias = ''
        self.active = False
        self.uninit = True
        self.voltage = '-'
        self.start_time = None
        self.data = []

    def cleanup(self):
        if self.file and self.filepath:
            self.file.close()
            shutil.move(str(self.filepath), str(
                iSpindel_archive_sessions_path()))
        self.file = None
        self.filepath = None
        self.uninit = True
        self.voltage = '-'
        self.start_time = None
        self.data = []


class TiltSession:
    def __init__(self):
        self.file = None
        self.filepath = None
        self.alias = ''
        self.color = None
        self.active = False
        self.uninit = True
        self.rssi = None
        self.start_time = None
        self.data = []

    def cleanup(self):
        if self.file and self.filepath:
            self.file.close()
            shutil.move(str(self.filepath), str(
                tilt_archive_sessions_path()))
        self.file = None
        self.filepath = None
        self.uninit = True
        self.rssi = None
        self.start_time = None
        self.data = []


class SupportObject:
    def __init__(self):
        self.name = None
        self.logo = None
        self.manual = None
        self.faq = None
        self.instructional_videos = None
        self.misc_media = None

    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__, indent=4)


class SupportMedia:
    def __init__(self, path, owner="Picobrew"):
        self.path = path
        self.owner = owner
