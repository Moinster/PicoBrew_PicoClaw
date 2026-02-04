#!/usr/bin/env python
"""
PicoFerm Device Simulator

Simulates a PicoFerm device connecting to the server and sending fermentation data.
Useful for testing the fermentation completion logic without a real device.

Usage:
    python picoferm_simulator.py [options]

Examples:
    # Basic simulation with default settings (waits for UI start)
    python picoferm_simulator.py

    # Simulate a 6% ABV beer at 72°F and 5 PSI
    python picoferm_simulator.py --abv 6.0 --temp 72 --pressure 5

    # Accelerated test (1 simulated hour per second)
    python picoferm_simulator.py --speed 3600 --abv 5.0

    # Skip waiting for UI - start immediately
    python picoferm_simulator.py --no-wait --speed 7200 --duration 5
    
    # Use a custom device UID
    python picoferm_simulator.py --uid MYCUSTOMDEV
"""

import argparse
import json
import random
import requests
import time
from datetime import datetime, timedelta

# Default persistent device UID for testing
DEFAULT_DEVICE_UID = "TESTFERM001"


class PicoFermSimulator:
    """Simulates a PicoFerm device sending data to the server."""
    
    def __init__(self, server_url: str, device_uid: str = None):
        self.server_url = server_url.rstrip('/')
        self.device_uid = device_uid or DEFAULT_DEVICE_UID
        self.token = self._generate_token()
        self.session_active = False
        self.voltage = 3.7  # Typical battery voltage
        
        # Simulation parameters
        self.base_temp = 70.0  # Base temperature in °F
        self.base_pressure = 5.0  # Base pressure in PSI
        self.temp_variance = 0.5  # Random variance in temperature
        self.pressure_variance = 0.2  # Random variance in pressure
        
    def _generate_uid(self) -> str:
        """Generate a random 12-character device UID."""
        import string
        chars = string.ascii_uppercase + string.digits
        return 'SIM' + ''.join(random.choices(chars, k=9))
    
    def _generate_token(self) -> str:
        """Generate a random 8-character token."""
        import string
        chars = string.ascii_uppercase + string.digits
        return ''.join(random.choices(chars, k=8))
    
    def register(self) -> bool:
        """Register the device with the server."""
        url = f"{self.server_url}/API/PicoFerm/isRegistered"
        params = {'uid': self.device_uid, 'token': self.token}
        
        try:
            response = requests.get(url, params=params)
            print(f"[REGISTER] {url}")
            print(f"  Response: {response.text}")
            return '#1#' in response.text
        except Exception as e:
            print(f"[ERROR] Registration failed: {e}")
            return False
    
    def check_firmware(self, version: str = "0.1.11") -> bool:
        """Check if firmware update is available."""
        url = f"{self.server_url}/API/PicoFerm/checkFirmware"
        params = {'uid': self.device_uid, 'version': version}
        
        try:
            response = requests.get(url, params=params)
            print(f"[FIRMWARE] {url}")
            print(f"  Response: {response.text}")
            return '#1#' in response.text
        except Exception as e:
            print(f"[ERROR] Firmware check failed: {e}")
            return False
    
    def get_state(self) -> str:
        """Get the current state from the server."""
        url = f"{self.server_url}/API/PicoFerm/getState"
        params = {'uid': self.device_uid}
        
        try:
            response = requests.get(url, params=params)
            return response.text
        except Exception as e:
            print(f"[ERROR] Get state failed: {e}")
            return ""
    
    def is_session_started(self) -> bool:
        """Check if the fermentation session has been started via the UI."""
        state = self.get_state()
        # '#10,0#' means session is active and should send data
        return '#10,0#' in state
    
    def wait_for_ui_start(self, timeout: int = 300) -> bool:
        """
        Wait for user to click 'Start Fermentation' in the UI.
        
        Args:
            timeout: Maximum seconds to wait (default: 5 minutes)
            
        Returns:
            True if session was started, False if timeout
        """
        print("\n" + "=" * 60)
        print("⏳ WAITING FOR UI START")
        print("=" * 60)
        print(f"Device '{self.device_uid}' is registered and waiting.")
        print(f"\nPlease go to the web UI at: {self.server_url}")
        print("Find the device and click 'Start Fermentation' button.")
        print("Enter your ABV and fermentation settings in the modal.")
        print(f"\n(Timeout in {timeout} seconds, press Ctrl+C to cancel)")
        print("-" * 60)
        
        start_time = datetime.now()
        check_interval = 1  # Check every second
        
        while (datetime.now() - start_time).total_seconds() < timeout:
            if self.is_session_started():
                print("\n✅ Fermentation started via UI!")
                return True
            
            elapsed = int((datetime.now() - start_time).total_seconds())
            remaining = timeout - elapsed
            print(f"\r  Waiting... ({remaining}s remaining)", end="", flush=True)
            time.sleep(check_interval)
        
        print("\n\n⚠️ Timeout waiting for UI start.")
        return False
    
    def set_fermentation_params(self, target_abv: float, target_pressure: float = 5.0,
                                 auto_complete: bool = True, use_conservative: bool = True) -> dict:
        """Set fermentation parameters on the server."""
        url = f"{self.server_url}/API/PicoFerm/setFermentationParams"
        data = {
            'uid': self.device_uid,
            'target_abv': target_abv,
            'target_pressure_psi': target_pressure,
            'auto_complete': auto_complete,
            'use_conservative': use_conservative
        }
        
        try:
            response = requests.post(url, json=data)
            print(f"[PARAMS] Set ABV={target_abv}%, Pressure={target_pressure} PSI")
            result = response.json()
            print(f"  Response: {json.dumps(result, indent=2)}")
            return result
        except Exception as e:
            print(f"[ERROR] Set params failed: {e}")
            return {}
    
    def get_fermentation_status(self) -> dict:
        """Get current fermentation status from server."""
        url = f"{self.server_url}/API/PicoFerm/getFermentationStatus"
        params = {'uid': self.device_uid}
        
        try:
            response = requests.get(url, params=params)
            return response.json()
        except Exception as e:
            print(f"[ERROR] Get status failed: {e}")
            return {}
    
    def generate_data_point(self) -> dict:
        """Generate a simulated sensor data point."""
        temp = self.base_temp + random.uniform(-self.temp_variance, self.temp_variance)
        pressure = self.base_pressure + random.uniform(-self.pressure_variance, self.pressure_variance)
        
        # Simulate slight pressure increase during active fermentation
        if self.session_active:
            pressure += random.uniform(0, 0.5)
        
        return {'s1': round(temp, 2), 's2': round(pressure, 2)}
    
    def log_dataset(self, data_points: list, rate: float = 1.0) -> str:
        """Send a dataset to the server."""
        url = f"{self.server_url}/API/PicoFerm/logDataSet"
        
        # Simulate slight voltage decrease over time
        self.voltage = max(3.0, self.voltage - 0.001)
        
        params = {
            'uid': self.device_uid,
            'rate': rate,
            'voltage': round(self.voltage, 2),
            'data': json.dumps(data_points)
        }
        
        try:
            response = requests.get(url, params=params)
            return response.text
        except Exception as e:
            print(f"[ERROR] Log dataset failed: {e}")
            return ""
    
    def run_simulation(self, target_abv: float = 5.0, temp: float = 70.0, 
                       pressure: float = 5.0, speed: float = 1.0,
                       duration_days: float = None, data_interval: float = 5.0,
                       wait_for_start: bool = True):
        """
        Run a full fermentation simulation.
        
        Args:
            target_abv: Target ABV for the beer
            temp: Simulated temperature in °F
            pressure: Simulated pressure in PSI
            speed: Time acceleration factor (e.g., 3600 = 1 hour per second)
            duration_days: How many simulated days to run (None = until complete)
            data_interval: How often the device sends data (in simulated minutes)
            wait_for_start: Wait for user to click Start Fermentation in UI
        """
        print("=" * 60)
        print("PicoFerm Simulator")
        print("=" * 60)
        print(f"Device UID: {self.device_uid}")
        print(f"Server: {self.server_url}")
        print(f"Target ABV: {target_abv}%")
        print(f"Temperature: {temp}°F")
        print(f"Pressure: {pressure} PSI")
        print(f"Speed: {speed}x (1 real second = {speed} simulated seconds)")
        print(f"Wait for UI: {'Yes' if wait_for_start else 'No'}")
        print("=" * 60)
        
        # Set simulation parameters
        self.base_temp = temp
        self.base_pressure = pressure
        
        # Step 1: Register device
        print("\n[1/4] Registering device...")
        if not self.register():
            print("Failed to register device!")
            return
        
        # Step 2: Check firmware
        print("\n[2/4] Checking firmware...")
        self.check_firmware()
        
        # Step 3: Wait for UI start OR set params directly
        if wait_for_start:
            print("\n[3/4] Waiting for user to start fermentation via UI...")
            if not self.wait_for_ui_start(timeout=300):
                print("Exiting - no fermentation started.")
                return
            
            # Get the parameters that were set via the UI
            status = self.get_fermentation_status()
            if status.get('success'):
                target_abv = status.get('target_abv') or target_abv
                print(f"  Using ABV from UI: {target_abv}%")
                
            if status.get('fermentation_status', {}).get('estimated_max_days'):
                est_days = status['fermentation_status']['estimated_max_days']
                print(f"  Estimated fermentation time: {est_days} days")
                if duration_days is None:
                    duration_days = est_days + 0.5
        else:
            # Set fermentation parameters directly (skip UI)
            print("\n[3/4] Setting fermentation parameters...")
            result = self.set_fermentation_params(target_abv, pressure)
            
            if result.get('fermentation_status', {}).get('estimated_max_days'):
                est_days = result['fermentation_status']['estimated_max_days']
                print(f"\n  Estimated fermentation time: {est_days} days")
                if duration_days is None:
                    duration_days = est_days + 0.5
        
        duration_days = duration_days or 7  # Default to 7 days
        
        # Step 4: Start sending data
        print(f"\n[4/4] Starting fermentation simulation...")
        print(f"  Will simulate {duration_days} days of fermentation")
        
        self.session_active = True
        simulated_start = datetime.now()
        simulated_elapsed = timedelta()
        target_duration = timedelta(days=duration_days)
        
        # Calculate real-time interval between data sends
        # data_interval is in simulated minutes
        real_interval = (data_interval * 60) / speed  # Convert to real seconds
        
        print(f"  Data interval: {data_interval} simulated minutes ({real_interval:.2f} real seconds)")
        print("\n" + "-" * 60)
        
        data_count = 0
        last_status_check = datetime.now()
        
        try:
            while simulated_elapsed < target_duration:
                # Generate data points (simulate batch of readings)
                batch_size = random.randint(1, 3)
                data_points = [self.generate_data_point() for _ in range(batch_size)]
                
                # Send data to server
                response = self.log_dataset(data_points, rate=data_interval)
                data_count += batch_size
                
                # Calculate simulated time
                simulated_elapsed = timedelta(seconds=(datetime.now() - simulated_start).total_seconds() * speed)
                simulated_days = simulated_elapsed.total_seconds() / (24 * 3600)
                
                # Print status
                avg_temp = sum(p['s1'] for p in data_points) / len(data_points)
                avg_pres = sum(p['s2'] for p in data_points) / len(data_points)
                
                print(f"[Day {simulated_days:.2f}] Sent {batch_size} points | "
                      f"Temp: {avg_temp:.1f}°F | Pres: {avg_pres:.1f} PSI | "
                      f"Response: {response.strip()}")
                
                # Check fermentation status periodically
                if (datetime.now() - last_status_check).total_seconds() > 5:
                    status = self.get_fermentation_status()
                    if status.get('success'):
                        ferm_status = status.get('fermentation_status', {})
                        progress = ferm_status.get('progress_percent', 0)
                        recommendation = ferm_status.get('recommendation', '')
                        print(f"  └─ Progress: {progress:.1f}% | {recommendation}")
                        
                        if ferm_status.get('should_complete'):
                            print("\n" + "=" * 60)
                            print("🎉 FERMENTATION COMPLETE!")
                            print("=" * 60)
                            break
                    last_status_check = datetime.now()
                
                # Check if server told us to stop
                if '#2,4#' in response:
                    print("\n" + "=" * 60)
                    print("🎉 Server signaled fermentation complete!")
                    print("=" * 60)
                    break
                
                # Wait for next interval
                time.sleep(max(0.1, real_interval))
                
        except KeyboardInterrupt:
            print("\n\nSimulation interrupted by user.")
        
        # Final status
        print("\n" + "-" * 60)
        print("Simulation Summary:")
        print(f"  Total data points sent: {data_count}")
        print(f"  Simulated duration: {simulated_elapsed}")
        print(f"  Real duration: {datetime.now() - simulated_start}")
        
        # Get final status
        final_status = self.get_fermentation_status()
        if final_status.get('success'):
            print(f"\nFinal Fermentation Status:")
            print(json.dumps(final_status.get('fermentation_status', {}), indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(
        description='PicoFerm Device Simulator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Register and wait for UI start
  %(prog)s --abv 6.0 --temp 72          # 6%% ABV at 72°F (waits for UI)
  %(prog)s --no-wait --speed 3600       # Skip UI, 1 hour per second
  %(prog)s --no-wait --speed 7200 -d 5  # Fast test, 5 days in ~1 min
  %(prog)s --uid MYDEVICE               # Use custom device name
        """
    )
    
    parser.add_argument('--server', '-s', default='http://localhost:8181',
                        help='Server URL (default: http://localhost:8181)')
    parser.add_argument('--uid', '-u', default=DEFAULT_DEVICE_UID,
                        help=f'Device UID (default: {DEFAULT_DEVICE_UID})')
    parser.add_argument('--abv', '-a', type=float, default=5.0,
                        help='Target ABV %% (default: 5.0)')
    parser.add_argument('--temp', '-t', type=float, default=70.0,
                        help='Fermentation temperature in °F (default: 70.0)')
    parser.add_argument('--pressure', '-p', type=float, default=5.0,
                        help='Fermentation pressure in PSI (default: 5.0)')
    parser.add_argument('--speed', type=float, default=1.0,
                        help='Time acceleration factor (default: 1.0, try 3600 for 1hr/sec)')
    parser.add_argument('--duration', '-d', type=float, default=None,
                        help='Simulation duration in days (default: auto based on ABV)')
    parser.add_argument('--interval', '-i', type=float, default=5.0,
                        help='Data interval in simulated minutes (default: 5.0)')
    parser.add_argument('--no-wait', action='store_true',
                        help='Skip waiting for UI start, begin immediately')
    
    args = parser.parse_args()
    
    # Create and run simulator
    simulator = PicoFermSimulator(args.server, args.uid)
    simulator.run_simulation(
        target_abv=args.abv,
        temp=args.temp,
        pressure=args.pressure,
        speed=args.speed,
        duration_days=args.duration,
        data_interval=args.interval,
        wait_for_start=not args.no_wait
    )


if __name__ == '__main__':
    main()
