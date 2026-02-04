"""
Fermentation Completion Calculator

Estimates fermentation time based on:
- Target ABV
- Temperature (from PicoFerm sensor)
- Pressure (from PicoFerm sensor)

Base times are calibrated for 65°F at 5 PSI (baseline conditions).
Adjustments are made for temperature and pressure deviations.

Temperature has the dominant effect:
- Higher temp = faster fermentation (yeast metabolizes faster)
- Every ~10°F increase roughly doubles fermentation rate

Pressure has a smaller effect:
- Higher pressure slightly inhibits yeast metabolism
- But allows cleaner fermentation at higher temps (suppresses esters)

This calculator uses time-weighted tracking to account for
changing conditions throughout fermentation.
"""

from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict, List
import statistics
import math


# =============================================================================
# BASELINE CONDITIONS
# =============================================================================

# Baseline conditions for fermentation time estimates
BASELINE_TEMP_F = 65.0      # Reference temperature
BASELINE_PRESSURE_PSI = 5.0  # Reference pressure

# Base fermentation times in DAYS at baseline conditions (65°F, 5 PSI)
# Format: (min_days, max_days) for each ABV tier
FERMENTATION_TIMES_AT_BASELINE = {
    'low': (7, 9),       # ABV <= 6.5%
    'medium': (10, 14),  # 6.5% < ABV <= 8.5%
    'high': (14, 21),    # ABV > 8.5%
}


# =============================================================================
# ADJUSTMENT FACTORS
# =============================================================================

# Temperature adjustment: ~7% faster per degree above baseline
# Based on Q10 rule (2x rate per 10°F increase) -> 2^0.1 ≈ 1.072 per degree
TEMP_ADJUSTMENT_PER_DEGREE = 0.07  # 7% per degree F

# Pressure adjustment: ~3% slower per PSI above baseline
# CO2 inhibits yeast metabolism slightly
PRESSURE_ADJUSTMENT_PER_PSI = 0.03  # 3% per PSI

# Weighting factor for recent data (exponential decay)
# Higher = more weight on recent readings
RECENCY_WEIGHT_FACTOR = 0.1  # Weight decay per hour


def _parse_time(time_val) -> Optional[datetime]:
    """
    Parse a time value into a datetime object.
    
    Handles:
    - datetime objects (returned as-is)
    - ISO format strings
    - Unix timestamps (float/int)
    """
    if time_val is None:
        return None
    
    if isinstance(time_val, datetime):
        return time_val
    
    if isinstance(time_val, str):
        try:
            return datetime.fromisoformat(time_val.replace('Z', '+00:00'))
        except:
            return None
    
    if isinstance(time_val, (int, float)):
        try:
            return datetime.fromtimestamp(time_val)
        except:
            return None
    
    return None


def get_abv_category(target_abv: float) -> str:
    """Categorize ABV into low/medium/high tiers."""
    if target_abv <= 6.5:
        return 'low'
    elif target_abv <= 8.5:
        return 'medium'
    else:
        return 'high'


def calculate_condition_factor(temp_f: float, pressure_psi: float) -> float:
    """
    Calculate fermentation rate factor based on current conditions.
    
    Returns a multiplier where:
    - 1.0 = baseline conditions (65°F, 5 PSI)
    - > 1.0 = faster fermentation
    - < 1.0 = slower fermentation
    
    Examples at 5 PSI:
    - 65°F: factor = 1.0 (baseline)
    - 70°F: factor = 1.35 (35% faster)
    - 75°F: factor = 1.70 (70% faster)
    - 60°F: factor = 0.65 (35% slower)
    
    Pressure effect is smaller:
    - 0 PSI at 65°F: factor = 1.15 (15% faster)
    - 10 PSI at 65°F: factor = 0.85 (15% slower)
    - 15 PSI at 65°F: factor = 0.70 (30% slower)
    """
    # Temperature effect (dominant)
    temp_delta = temp_f - BASELINE_TEMP_F
    temp_factor = 1.0 + (temp_delta * TEMP_ADJUSTMENT_PER_DEGREE)
    
    # Pressure effect (smaller, inverse - higher pressure = slower)
    pressure_delta = pressure_psi - BASELINE_PRESSURE_PSI
    pressure_factor = 1.0 - (pressure_delta * PRESSURE_ADJUSTMENT_PER_PSI)
    
    # Combined factor
    combined = temp_factor * pressure_factor
    
    # Clamp to reasonable range (0.3x to 3.0x baseline rate)
    return max(0.3, min(3.0, combined))


def get_base_fermentation_days(target_abv: float) -> Tuple[float, float]:
    """Get base fermentation time at baseline conditions."""
    abv_category = get_abv_category(target_abv)
    return FERMENTATION_TIMES_AT_BASELINE[abv_category]


def estimate_fermentation_days(
    target_abv: float,
    avg_temp_f: float,
    avg_pressure_psi: float = BASELINE_PRESSURE_PSI
) -> Tuple[float, float]:
    """
    Estimate fermentation time in days based on average conditions.
    
    Returns:
        Tuple of (min_days, max_days) for estimated fermentation time
    """
    base_min, base_max = get_base_fermentation_days(target_abv)
    
    # Get condition factor (higher = faster, so we divide)
    condition_factor = calculate_condition_factor(avg_temp_f, avg_pressure_psi)
    
    # Faster conditions = fewer days needed
    adjusted_min = base_min / condition_factor
    adjusted_max = base_max / condition_factor
    
    return (adjusted_min, adjusted_max)


def calculate_weighted_averages(
    data_points: List[Dict],
    start_time: Optional[datetime] = None
) -> Dict:
    """
    Calculate time-weighted averages of temperature and pressure.
    
    More recent readings are weighted more heavily using exponential decay.
    This accounts for the fact that current conditions matter more for
    predicting when fermentation will complete.
    
    Args:
        data_points: List of dicts with 'time', 'temp', 'pres' keys
        start_time: Session start time for reference
    
    Returns:
        Dict with weighted averages and analysis
    """
    if not data_points:
        return {
            'avg_temp': None,
            'avg_pressure': None,
            'weighted_temp': None,
            'weighted_pressure': None,
            'min_temp': None,
            'max_temp': None,
            'min_pressure': None,
            'max_pressure': None,
            'data_points': 0,
            'avg_condition_factor': None,
        }
    
    temps = []
    pressures = []
    weights = []
    condition_factors = []
    
    # Get the most recent timestamp for weight calculation
    latest_time = None
    for p in data_points:
        if 'time' in p:
            t = _parse_time(p['time'])
            if t is not None and (latest_time is None or t > latest_time):
                latest_time = t
    
    if latest_time is None:
        latest_time = datetime.now()
    
    for p in data_points:
        if 'temp' in p and 'pres' in p:
            temp = p['temp']
            pres = p['pres']
            
            # Calculate weight based on recency
            weight = 1.0
            if 'time' in p:
                t = _parse_time(p['time'])
                if t is not None:
                    hours_ago = (latest_time - t).total_seconds() / 3600
                    # Exponential decay: more recent = higher weight
                    weight = math.exp(-RECENCY_WEIGHT_FACTOR * hours_ago)
            
            temps.append(temp)
            pressures.append(pres)
            weights.append(weight)
            condition_factors.append(calculate_condition_factor(temp, pres))
    
    if not temps:
        return {
            'avg_temp': None,
            'avg_pressure': None,
            'weighted_temp': None,
            'weighted_pressure': None,
            'min_temp': None,
            'max_temp': None,
            'min_pressure': None,
            'max_pressure': None,
            'data_points': 0,
            'avg_condition_factor': None,
        }
    
    # Simple averages
    avg_temp = statistics.mean(temps)
    avg_pressure = statistics.mean(pressures)
    
    # Weighted averages (more weight on recent data)
    total_weight = sum(weights)
    weighted_temp = sum(t * w for t, w in zip(temps, weights)) / total_weight
    weighted_pressure = sum(p * w for p, w in zip(pressures, weights)) / total_weight
    
    # Average condition factor (for progress tracking)
    avg_condition_factor = statistics.mean(condition_factors)
    
    return {
        'avg_temp': round(avg_temp, 1),
        'avg_pressure': round(avg_pressure, 1),
        'weighted_temp': round(weighted_temp, 1),
        'weighted_pressure': round(weighted_pressure, 1),
        'min_temp': round(min(temps), 1),
        'max_temp': round(max(temps), 1),
        'min_pressure': round(min(pressures), 1),
        'max_pressure': round(max(pressures), 1),
        'data_points': len(data_points),
        'avg_condition_factor': round(avg_condition_factor, 2),
    }


def calculate_accumulated_progress(
    data_points: List[Dict],
    target_abv: float,
    start_time: datetime
) -> float:
    """
    Calculate fermentation progress based on accumulated "fermentation units".
    
    Instead of just looking at elapsed time, this tracks the actual
    fermentation conditions over time. Warmer periods contribute more
    progress than cooler periods.
    
    Returns:
        Progress percentage (0-100)
    """
    if not data_points or len(data_points) < 2:
        return 0.0
    
    base_min, base_max = get_base_fermentation_days(target_abv)
    target_days = (base_min + base_max) / 2  # Use midpoint
    
    # Total "fermentation units" needed (at baseline conditions)
    # 1 unit = 1 hour at baseline conditions
    target_units = target_days * 24  # Convert days to hours
    
    # Sort data points by time
    sorted_points = []
    for p in data_points:
        if 'time' in p and 'temp' in p and 'pres' in p:
            t = _parse_time(p['time'])
            if t is not None:
                sorted_points.append({
                    'time': t,
                    'temp': p['temp'],
                    'pres': p['pres']
                })
    
    if len(sorted_points) < 2:
        return 0.0
    
    sorted_points.sort(key=lambda x: x['time'])
    
    # Accumulate fermentation units
    accumulated_units = 0.0
    
    for i in range(1, len(sorted_points)):
        prev = sorted_points[i - 1]
        curr = sorted_points[i]
        
        # Time delta in hours
        delta_hours = (curr['time'] - prev['time']).total_seconds() / 3600
        
        # Average conditions during this period
        avg_temp = (prev['temp'] + curr['temp']) / 2
        avg_pres = (prev['pres'] + curr['pres']) / 2
        
        # Condition factor for this period
        factor = calculate_condition_factor(avg_temp, avg_pres)
        
        # Accumulated units = hours * factor
        # Higher factor = more progress per hour
        accumulated_units += delta_hours * factor
    
    progress = (accumulated_units / target_units) * 100
    return min(100.0, max(0.0, progress))


def estimate_completion_time(
    start_time: datetime,
    target_abv: float,
    avg_temp_f: float,
    avg_pressure_psi: float = BASELINE_PRESSURE_PSI,
    use_conservative: bool = True
) -> datetime:
    """
    Calculate estimated completion datetime.
    
    Args:
        start_time: When fermentation started
        target_abv: Target alcohol by volume percentage
        avg_temp_f: Average temperature in Fahrenheit
        avg_pressure_psi: Average pressure in PSI
        use_conservative: If True, use max estimate; if False, use min
    
    Returns:
        Estimated completion datetime
    """
    min_days, max_days = estimate_fermentation_days(target_abv, avg_temp_f, avg_pressure_psi)
    
    days = max_days if use_conservative else min_days
    return start_time + timedelta(days=days)


def calculate_progress_percentage(
    start_time: datetime,
    current_time: datetime,
    target_abv: float,
    avg_temp_f: float,
    avg_pressure_psi: float = BASELINE_PRESSURE_PSI
) -> float:
    """
    Calculate fermentation progress as a percentage (simple time-based).
    
    For more accurate progress tracking with variable conditions,
    use calculate_accumulated_progress() instead.
    """
    min_days, max_days = estimate_fermentation_days(target_abv, avg_temp_f, avg_pressure_psi)
    avg_days = (min_days + max_days) / 2
    
    elapsed = current_time - start_time
    elapsed_days = elapsed.total_seconds() / (24 * 60 * 60)
    
    progress = (elapsed_days / avg_days) * 100
    return min(100.0, max(0.0, progress))


def should_complete_fermentation(
    start_time: datetime,
    current_time: datetime,
    target_abv: float,
    avg_temp_f: float,
    avg_pressure_psi: float = BASELINE_PRESSURE_PSI,
    use_conservative: bool = True
) -> bool:
    """
    Determine if fermentation should be marked as complete.
    
    Args:
        use_conservative: If True, wait for max estimated time before completing
    """
    estimated_completion = estimate_completion_time(
        start_time, target_abv, avg_temp_f, avg_pressure_psi, use_conservative
    )
    return current_time >= estimated_completion


def analyze_session_data(data_points: List[Dict]) -> Dict:
    """
    Analyze fermentation session data to extract averages.
    
    DEPRECATED: Use calculate_weighted_averages() for better accuracy.
    
    Args:
        data_points: List of dicts with 'temp' and 'pres' keys
    
    Returns:
        Dict with 'avg_temp', 'avg_pressure', 'min_temp', 'max_temp', etc.
    """
    return calculate_weighted_averages(data_points)


def get_fermentation_status(
    start_time: Optional[datetime],
    target_abv: Optional[float],
    data_points: List[Dict],
    current_time: Optional[datetime] = None
) -> Dict:
    """
    Get comprehensive fermentation status.
    
    Returns a dict with all relevant status information.
    """
    if current_time is None:
        current_time = datetime.now()
    
    analysis = calculate_weighted_averages(data_points, start_time)
    
    status = {
        'has_target_abv': target_abv is not None,
        'target_abv': target_abv,
        'analysis': analysis,
        'can_estimate': False,
        'progress_percent': 0,
        'accumulated_progress': 0,
        'estimated_min_days': None,
        'estimated_max_days': None,
        'estimated_completion': None,
        'should_complete': False,
        'recommendation': None,
        'baseline_info': {
            'temp_f': BASELINE_TEMP_F,
            'pressure_psi': BASELINE_PRESSURE_PSI,
        },
    }
    
    # Need ABV, start time, and sensor data to make estimates
    if target_abv is None or start_time is None:
        status['recommendation'] = 'Set target ABV to enable fermentation time estimation'
        return status
    
    if analysis['weighted_temp'] is None or analysis['weighted_pressure'] is None:
        status['recommendation'] = 'Waiting for sensor data to estimate completion time'
        return status
    
    status['can_estimate'] = True
    
    # Use weighted averages for estimation (accounts for recent conditions)
    weighted_temp = analysis['weighted_temp']
    weighted_pressure = analysis['weighted_pressure']
    
    # Calculate estimates using weighted conditions
    min_days, max_days = estimate_fermentation_days(
        target_abv, weighted_temp, weighted_pressure
    )
    status['estimated_min_days'] = round(min_days, 1)
    status['estimated_max_days'] = round(max_days, 1)
    
    # Conservative completion estimate
    estimated_completion = estimate_completion_time(
        start_time, target_abv, weighted_temp, weighted_pressure, use_conservative=True
    )
    status['estimated_completion'] = estimated_completion.isoformat() if estimated_completion else None
    
    # Simple time-based progress (for backward compatibility)
    status['progress_percent'] = round(calculate_progress_percentage(
        start_time, current_time, target_abv, weighted_temp, weighted_pressure
    ), 1)
    
    # Accumulated progress (accounts for varying conditions over time)
    status['accumulated_progress'] = round(calculate_accumulated_progress(
        data_points, target_abv, start_time
    ), 1)
    
    # Should complete?
    status['should_complete'] = should_complete_fermentation(
        start_time, current_time, target_abv, weighted_temp, weighted_pressure
    )
    
    # Recommendation based on accumulated progress (more accurate)
    progress = status['accumulated_progress']
    if progress >= 100 or status['should_complete']:
        status['recommendation'] = 'Fermentation time complete! Consider taking a gravity reading to confirm.'
    elif progress >= 75:
        remaining = estimated_completion - current_time
        hours = remaining.total_seconds() / 3600
        if hours < 24:
            status['recommendation'] = f'Almost done! Approximately {int(hours)} hours remaining.'
        else:
            days = hours / 24
            status['recommendation'] = f'Getting close! Approximately {days:.1f} days remaining.'
    else:
        days_remaining = (estimated_completion - current_time).total_seconds() / (24 * 3600)
        if days_remaining > 0:
            status['recommendation'] = f'Fermentation in progress. Estimated {days_remaining:.1f} days remaining.'
        else:
            status['recommendation'] = 'Fermentation may be complete. Consider taking a gravity reading.'
    
    return status
