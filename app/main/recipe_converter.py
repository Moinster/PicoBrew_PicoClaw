"""
Recipe Converter

Converts generic BeerRecipe objects (from BeerXML or manual input) into
device-specific formats for Pico, Zymatic, and Z-Series brewers.

Each device has different constraints:
- Pico: 4 hop additions (Adjunct1-4), fixed early steps
- Zymatic: 4 hop additions (Adjunct1-4), more flexible
- Z-Series: 4 hop additions (Adjunct1-4), similar to Zymatic

All devices share the concept of:
- Mash: The grain basket
- PassThru: Recirculation without going through grain/hops
- Adjunct1-4: Hop baskets for timed additions
- Pause: User intervention point
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
import json

from .beerxml_parser import BeerRecipe, Hop, MashStep, HopUse
from .model import PICO_LOCATION, ZYMATIC_LOCATION, ZSERIES_LOCATION, MachineType


class DeviceType(Enum):
    """Target device for recipe conversion"""
    PICO = "pico"
    ZYMATIC = "zymatic"
    ZSERIES = "zseries"


@dataclass
class RecipeStep:
    """A single step in the device recipe"""
    name: str
    location: str  # PassThru, Mash, Adjunct1-4, Pause, Prime
    temperature: int  # Temperature in °F
    step_time: int  # Time in minutes
    drain_time: int  # Drain time in minutes
    
    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'location': self.location,
            'temperature': self.temperature,
            'step_time': self.step_time,
            'drain_time': self.drain_time,
        }


@dataclass
class ConvertedRecipe:
    """A recipe converted for a specific device"""
    name: str
    device_type: DeviceType
    steps: List[RecipeStep] = field(default_factory=list)
    
    # Pico-specific fields
    abv: float = 0.0
    ibu: float = 0.0
    abv_tweak: float = 0.0
    ibu_tweak: float = 0.0
    image: str = ""
    
    # Z-Series specific
    start_water: float = 13.1  # Liters
    
    # Metadata
    notes: str = ""
    original_recipe: Optional[BeerRecipe] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        result = {
            'name': self.name,
            'steps': [s.to_dict() for s in self.steps],
            'notes': self.notes,
        }
        
        if self.device_type == DeviceType.PICO:
            result['abv'] = self.abv
            result['ibu'] = self.ibu
            result['abv_tweak'] = self.abv_tweak
            result['ibu_tweak'] = self.ibu_tweak
            result['image'] = self.image
        elif self.device_type == DeviceType.ZSERIES:
            result['start_water'] = self.start_water
        
        return result


class RecipeConverter:
    """
    Converts BeerRecipe to device-specific formats.
    
    The conversion process:
    1. Generate mash steps from the recipe's mash schedule
    2. Convert boil hop additions to adjunct steps (max 4)
    3. Add appropriate heat/cool transitions
    4. Optimize step timing
    """
    
    # Device-specific constants
    PICO_BOIL_TEMP = 202  # Pico boils at 202°F (altitude adjustment)
    ZYMATIC_BOIL_TEMP = 207
    ZSERIES_BOIL_TEMP = 207
    
    MAX_HOP_ADDITIONS = 4  # All devices support 4 adjunct positions
    
    def __init__(self, device_type: DeviceType):
        self.device_type = device_type
        self.boil_temp = self._get_boil_temp()
    
    def _get_boil_temp(self) -> int:
        """Get the boil temperature for this device"""
        temps = {
            DeviceType.PICO: self.PICO_BOIL_TEMP,
            DeviceType.ZYMATIC: self.ZYMATIC_BOIL_TEMP,
            DeviceType.ZSERIES: self.ZSERIES_BOIL_TEMP,
        }
        return temps.get(self.device_type, 207)
    
    def convert(self, recipe: BeerRecipe) -> ConvertedRecipe:
        """
        Convert a BeerRecipe to a device-specific format.
        
        Args:
            recipe: The source BeerRecipe from BeerXML or manual entry
            
        Returns:
            ConvertedRecipe ready for the target device
        """
        converted = ConvertedRecipe(
            name=recipe.name[:19],  # Most devices limit name length
            device_type=self.device_type,
            abv=recipe.abv,
            ibu=recipe.ibu,
            notes=recipe.notes,
            original_recipe=recipe,
        )
        
        # Set start water for Z-Series
        if self.device_type == DeviceType.ZSERIES:
            converted.start_water = recipe.boil_size_l
        
        # Build the step list based on device type
        if self.device_type == DeviceType.PICO:
            converted.steps = self._build_pico_steps(recipe)
        elif self.device_type == DeviceType.ZYMATIC:
            converted.steps = self._build_zymatic_steps(recipe)
        elif self.device_type == DeviceType.ZSERIES:
            converted.steps = self._build_zseries_steps(recipe)
        
        return converted
    
    def _build_pico_steps(self, recipe: BeerRecipe) -> List[RecipeStep]:
        """Build steps for Pico (C/S/Pro)"""
        steps = []
        
        # Fixed Pico header steps
        steps.append(RecipeStep(
            name="Preparing To Brew",
            location="Prime",
            temperature=0,
            step_time=3,
            drain_time=0
        ))
        
        # Heating and Dough In always use 110°F for Pico
        steps.append(RecipeStep(
            name="Heating",
            location="PassThru",
            temperature=110,
            step_time=0,
            drain_time=0
        ))
        
        steps.append(RecipeStep(
            name="Dough In",
            location="Mash",
            temperature=110,
            step_time=7,
            drain_time=0
        ))
        
        # Add mash steps
        steps.extend(self._build_mash_steps(recipe))
        
        # Add mash out
        steps.append(RecipeStep(
            name="Mash Out",
            location="Mash",
            temperature=178,
            step_time=7,
            drain_time=2
        ))
        
        # Add hop steps
        hop_steps = self._build_hop_steps(recipe, is_pico=True)
        
        # Set drain time on last hop addition
        if hop_steps:
            hop_steps[-1].drain_time = 5
        
        steps.extend(hop_steps)
        
        return steps
    
    def _build_zymatic_steps(self, recipe: BeerRecipe) -> List[RecipeStep]:
        """Build steps for Zymatic"""
        steps = []
        
        # Get first mash temp
        first_mash_temp = 152
        if recipe.mash_steps:
            first_mash_temp = int(recipe.mash_steps[0].step_temp_f)
        
        # Heat to mash
        steps.append(RecipeStep(
            name="Heat Mash",
            location="PassThru",
            temperature=first_mash_temp,
            step_time=0,
            drain_time=0
        ))
        
        # Main mash step(s)
        mash_steps = self._build_mash_steps(recipe)
        if not mash_steps:
            # Default single infusion
            steps.append(RecipeStep(
                name="Mash",
                location="Mash",
                temperature=152,
                step_time=90,
                drain_time=8
            ))
        else:
            steps.extend(mash_steps)
        
        # Heat to mash out
        steps.append(RecipeStep(
            name="Heat to Mash Out",
            location="PassThru",
            temperature=175,
            step_time=0,
            drain_time=0
        ))
        
        # Mash out
        steps.append(RecipeStep(
            name="Mash Out",
            location="Mash",
            temperature=175,
            step_time=15,
            drain_time=8
        ))
        
        # Heat to boil
        steps.append(RecipeStep(
            name="Heat to Boil",
            location="PassThru",
            temperature=self.boil_temp,
            step_time=0,
            drain_time=0
        ))
        
        # Pre-hop boil and hop additions
        hop_steps = self._build_hop_steps(recipe, is_pico=False)
        steps.extend(hop_steps)
        
        # Whirlpool (if applicable)
        whirlpool_hops = recipe.get_whirlpool_hops()
        if whirlpool_hops:
            steps.append(RecipeStep(
                name="Cool to Whirlpool",
                location="PassThru",
                temperature=175,
                step_time=0,
                drain_time=0
            ))
            steps.append(RecipeStep(
                name="Whirlpool",
                location="Adjunct4",
                temperature=175,
                step_time=20,
                drain_time=5
            ))
        
        # Connect chiller
        steps.append(RecipeStep(
            name="Connect Chiller",
            location="Pause",
            temperature=0,
            step_time=0,
            drain_time=0
        ))
        
        # Chill
        steps.append(RecipeStep(
            name="Chill",
            location="PassThru",
            temperature=66,
            step_time=10,
            drain_time=10
        ))
        
        return steps
    
    def _build_zseries_steps(self, recipe: BeerRecipe) -> List[RecipeStep]:
        """Build steps for Z-Series (similar to Zymatic but with some differences)"""
        steps = []
        
        # Get first mash temp
        first_mash_temp = 104  # Z-Series typically starts lower for dough-in
        if recipe.mash_steps:
            first_mash_temp = min(104, int(recipe.mash_steps[0].step_temp_f))
        
        # Heat water
        steps.append(RecipeStep(
            name="Heat Water",
            location="PassThru",
            temperature=first_mash_temp,
            step_time=0,
            drain_time=0
        ))
        
        # Dough in
        steps.append(RecipeStep(
            name="Dough In",
            location="Mash",
            temperature=first_mash_temp,
            step_time=20,
            drain_time=4
        ))
        
        # Multi-step mash
        mash_steps = self._build_mash_steps_zseries(recipe)
        steps.extend(mash_steps)
        
        # Heat to mash out
        steps.append(RecipeStep(
            name="Heat to Mash Out",
            location="Mash",
            temperature=175,
            step_time=0,
            drain_time=4
        ))
        
        # Mash out
        steps.append(RecipeStep(
            name="Mash Out",
            location="Mash",
            temperature=175,
            step_time=15,
            drain_time=8
        ))
        
        # Heat to boil
        steps.append(RecipeStep(
            name="Heat to Boil",
            location="PassThru",
            temperature=self.boil_temp,
            step_time=0,
            drain_time=0
        ))
        
        # Pre-hop boil and hop additions
        hop_steps = self._build_hop_steps(recipe, is_pico=False)
        steps.extend(hop_steps)
        
        # Connect chiller
        steps.append(RecipeStep(
            name="Connect Chiller",
            location="Pause",
            temperature=0,
            step_time=0,
            drain_time=0
        ))
        
        # Chill
        steps.append(RecipeStep(
            name="Chill",
            location="PassThru",
            temperature=66,
            step_time=10,
            drain_time=10
        ))
        
        return steps
    
    def _build_mash_steps(self, recipe: BeerRecipe) -> List[RecipeStep]:
        """Build mash steps from recipe mash schedule"""
        steps = []
        
        for i, mash_step in enumerate(recipe.mash_steps):
            temp_f = int(mash_step.step_temp_f)
            
            # Skip very low temp steps (acid rest, etc.) - not practical for these devices
            if temp_f < 100:
                continue
            
            name = mash_step.name[:19]
            if not name or name.lower() == 'mash':
                name = f"Mash {i + 1}"
            
            steps.append(RecipeStep(
                name=name,
                location="Mash",
                temperature=temp_f,
                step_time=mash_step.step_time_min,
                drain_time=0 if i < len(recipe.mash_steps) - 1 else 8
            ))
        
        return steps
    
    def _build_mash_steps_zseries(self, recipe: BeerRecipe) -> List[RecipeStep]:
        """Build mash steps for Z-Series with heating transitions"""
        steps = []
        
        mash_temps = []
        for mash_step in recipe.mash_steps:
            temp_f = int(mash_step.step_temp_f)
            if temp_f >= 100:  # Skip acid rest temps
                mash_temps.append((mash_step.name, temp_f, mash_step.step_time_min))
        
        if not mash_temps:
            # Default single infusion
            mash_temps = [("Mash 1", 152, 60)]
        
        for i, (name, temp, time) in enumerate(mash_temps):
            # Add heating step if not first
            if i > 0:
                steps.append(RecipeStep(
                    name=f"Heat to Mash {i + 1}",
                    location="Mash",
                    temperature=temp,
                    step_time=0,
                    drain_time=4
                ))
            
            step_name = name[:19] if name else f"Mash {i + 1}"
            steps.append(RecipeStep(
                name=step_name,
                location="Mash",
                temperature=temp,
                step_time=time,
                drain_time=4
            ))
        
        return steps
    
    def _build_hop_steps(self, recipe: BeerRecipe, is_pico: bool = False) -> List[RecipeStep]:
        """
        Build hop addition steps from recipe.
        
        Converts boil hop additions to timed adjunct steps.
        Most devices support 4 hop additions (Adjunct1-4).
        """
        steps = []
        boil_hops = recipe.get_boil_hops()
        boil_time = recipe.boil_time_min
        
        if not boil_hops:
            # No hops - just do a basic boil
            steps.append(RecipeStep(
                name="Boil",
                location="PassThru",
                temperature=self.boil_temp,
                step_time=boil_time,
                drain_time=0
            ))
            return steps
        
        # Group hops by addition time and limit to 4 additions
        hop_schedule = self._create_hop_schedule(boil_hops, boil_time)
        
        # Calculate pre-hop boil time
        first_hop_time = hop_schedule[0][0] if hop_schedule else 60
        pre_hop_boil = boil_time - first_hop_time
        
        if pre_hop_boil > 0:
            steps.append(RecipeStep(
                name="Pre-hop Boil",
                location="PassThru",
                temperature=self.boil_temp,
                step_time=pre_hop_boil,
                drain_time=0
            ))
        
        # Add hop steps
        for i, (hop_time, hop_names) in enumerate(hop_schedule):
            if i >= self.MAX_HOP_ADDITIONS:
                break
            
            adjunct = f"Adjunct{i + 1}"
            
            # Calculate step time (time until next addition or end of boil)
            if i + 1 < len(hop_schedule):
                next_time = hop_schedule[i + 1][0]
                step_time = hop_time - next_time
            else:
                step_time = hop_time  # Last addition runs to end of boil
            
            # Create hop step name
            hop_name = f"Hops {i + 1}"
            if len(hop_names) == 1:
                hop_name = hop_names[0][:19]
            
            steps.append(RecipeStep(
                name=hop_name,
                location=adjunct,
                temperature=self.boil_temp,
                step_time=step_time,
                drain_time=0
            ))
        
        return steps
    
    def _create_hop_schedule(self, hops: List[Hop], boil_time: int) -> List[Tuple[int, List[str]]]:
        """
        Create a hop schedule grouped by addition time.
        
        Returns list of (time_remaining, [hop_names]) sorted by time descending.
        Limits to 4 additions by combining nearby additions.
        """
        # Group by time
        time_groups: Dict[int, List[str]] = {}
        for hop in hops:
            time = min(hop.time_min, boil_time)  # Cap at boil time
            if time not in time_groups:
                time_groups[time] = []
            time_groups[time].append(hop.name)
        
        # Sort by time descending (first addition first)
        schedule = sorted(time_groups.items(), key=lambda x: x[0], reverse=True)
        
        # If more than 4 additions, combine nearby ones
        while len(schedule) > self.MAX_HOP_ADDITIONS:
            # Find the two closest additions and combine
            min_gap = float('inf')
            combine_idx = 0
            
            for i in range(len(schedule) - 1):
                gap = schedule[i][0] - schedule[i + 1][0]
                if gap < min_gap:
                    min_gap = gap
                    combine_idx = i
            
            # Combine into earlier addition
            combined_time = schedule[combine_idx][0]
            combined_names = schedule[combine_idx][1] + schedule[combine_idx + 1][1]
            schedule[combine_idx] = (combined_time, combined_names)
            schedule.pop(combine_idx + 1)
        
        return schedule


def convert_beerxml_to_device(xml_content: str, device_type: str) -> List[dict]:
    """
    High-level function to convert BeerXML to device recipes.
    
    Args:
        xml_content: Raw BeerXML content
        device_type: Target device ('pico', 'zymatic', 'zseries')
        
    Returns:
        List of recipe dictionaries ready for saving
    """
    from .beerxml_parser import parse_beerxml
    
    # Parse BeerXML
    recipes = parse_beerxml(xml_content)
    
    # Determine device type
    device_map = {
        'pico': DeviceType.PICO,
        'zymatic': DeviceType.ZYMATIC,
        'zseries': DeviceType.ZSERIES,
        'z': DeviceType.ZSERIES,
    }
    device = device_map.get(device_type.lower(), DeviceType.PICO)
    
    # Convert each recipe
    converter = RecipeConverter(device)
    converted = []
    
    for recipe in recipes:
        result = converter.convert(recipe)
        converted.append(result.to_dict())
    
    return converted


def create_recipe_from_params(
    name: str,
    device_type: str,
    mash_steps: List[dict],
    hop_additions: List[dict],
    boil_time: int = 60,
    og: float = 1.050,
    ibu: float = 30,
    abv: float = 5.0,
    notes: str = ""
) -> dict:
    """
    Create a device recipe from manual parameters.
    
    Args:
        name: Recipe name
        device_type: Target device ('pico', 'zymatic', 'zseries')
        mash_steps: List of {'name', 'temp_f', 'time_min'}
        hop_additions: List of {'name', 'time_min'} (time = minutes remaining)
        boil_time: Total boil time in minutes
        og: Original gravity
        ibu: Bitterness
        abv: Alcohol by volume
        notes: Recipe notes
        
    Returns:
        Recipe dictionary ready for saving
    """
    from .beerxml_parser import BeerRecipe, MashStep, Hop, HopUse
    
    # Build BeerRecipe from params
    recipe = BeerRecipe(
        name=name,
        boil_time_min=boil_time,
        og=og,
        ibu=ibu,
        abv=abv,
        notes=notes,
    )
    
    # Add mash steps
    for step in mash_steps:
        recipe.mash_steps.append(MashStep(
            name=step.get('name', 'Mash'),
            step_temp_c=(step.get('temp_f', 152) - 32) * 5/9,
            step_time_min=step.get('time_min', 60),
        ))
    
    # Add hops
    for hop in hop_additions:
        recipe.hops.append(Hop(
            name=hop.get('name', 'Hops'),
            amount_kg=hop.get('amount_oz', 1.0) / 35.274,
            time_min=hop.get('time_min', 60),
            use=HopUse.BOIL,
        ))
    
    # Convert to device format
    device_map = {
        'pico': DeviceType.PICO,
        'zymatic': DeviceType.ZYMATIC,
        'zseries': DeviceType.ZSERIES,
    }
    device = device_map.get(device_type.lower(), DeviceType.PICO)
    
    converter = RecipeConverter(device)
    result = converter.convert(recipe)
    
    return result.to_dict()
