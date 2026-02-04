"""
BeerXML Parser

Parses BeerXML 1.0 format files into a standardized recipe structure that can
be converted to PicoBrew device formats (Pico, Zymatic, Z-Series).

BeerXML is an open standard supported by:
- BeerSmith
- Brewfather
- Brewer's Friend
- Many other brewing apps

See: http://www.beerxml.com/beerxml.htm
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class HopUse(Enum):
    """When hops are added during brewing"""
    BOIL = "Boil"
    DRY_HOP = "Dry Hop"
    MASH = "Mash"
    FIRST_WORT = "First Wort"
    AROMA = "Aroma"  # Flameout/whirlpool


class FermentableType(Enum):
    """Type of fermentable ingredient"""
    GRAIN = "Grain"
    SUGAR = "Sugar"
    EXTRACT = "Extract"
    DRY_EXTRACT = "Dry Extract"
    ADJUNCT = "Adjunct"


class MashStepType(Enum):
    """Type of mash step"""
    INFUSION = "Infusion"
    TEMPERATURE = "Temperature"
    DECOCTION = "Decoction"


@dataclass
class Hop:
    """A hop addition in the recipe"""
    name: str
    amount_kg: float  # Amount in kg
    time_min: int  # Time in minutes (boil time remaining, or steep time for whirlpool)
    use: HopUse = HopUse.BOIL
    alpha_acid: float = 0.0  # Alpha acid percentage
    form: str = "Pellet"  # Pellet, Plug, Leaf
    
    @property
    def amount_oz(self) -> float:
        """Amount in ounces"""
        return self.amount_kg * 35.274


@dataclass
class Fermentable:
    """A fermentable ingredient (grain, extract, sugar)"""
    name: str
    amount_kg: float
    type: FermentableType = FermentableType.GRAIN
    color_lovibond: float = 0.0  # Color in Lovibond
    potential_ppg: float = 0.0  # Points per pound per gallon
    
    @property
    def amount_lb(self) -> float:
        """Amount in pounds"""
        return self.amount_kg * 2.20462


@dataclass
class Yeast:
    """Yeast strain"""
    name: str
    type: str = "Ale"  # Ale, Lager, Wheat, Wine, Champagne
    form: str = "Liquid"  # Liquid, Dry, Slant, Culture
    lab: str = ""  # Laboratory name (Wyeast, White Labs, etc.)
    product_id: str = ""  # Product code
    min_temp_c: float = 15.0
    max_temp_c: float = 25.0
    attenuation: float = 75.0  # Percent attenuation
    
    @property
    def min_temp_f(self) -> float:
        return self.min_temp_c * 9/5 + 32
    
    @property
    def max_temp_f(self) -> float:
        return self.max_temp_c * 9/5 + 32


@dataclass
class MashStep:
    """A step in the mash schedule"""
    name: str
    type: MashStepType = MashStepType.INFUSION
    step_temp_c: float = 67.0  # Target temperature in Celsius
    step_time_min: int = 60  # Time at target temp in minutes
    infuse_amount_l: float = 0.0  # Water added (for infusion mash)
    
    @property
    def step_temp_f(self) -> float:
        """Temperature in Fahrenheit"""
        return self.step_temp_c * 9/5 + 32


@dataclass
class Style:
    """Beer style information"""
    name: str
    category: str = ""
    style_guide: str = "BJCP"
    type: str = "Ale"  # Ale, Lager, Mixed, Wheat, etc.
    og_min: float = 1.040
    og_max: float = 1.060
    fg_min: float = 1.008
    fg_max: float = 1.016
    ibu_min: float = 20
    ibu_max: float = 40
    color_min: float = 4.0  # SRM
    color_max: float = 14.0
    abv_min: float = 4.0
    abv_max: float = 6.0


@dataclass 
class BeerRecipe:
    """A complete beer recipe parsed from BeerXML"""
    name: str
    type: str = "All Grain"  # All Grain, Partial Mash, Extract
    brewer: str = ""
    batch_size_l: float = 19.0  # Liters
    boil_size_l: float = 23.0  # Pre-boil volume in liters
    boil_time_min: int = 60
    efficiency: float = 72.0  # Mash efficiency percentage
    
    # Calculated values
    og: float = 1.050
    fg: float = 1.010
    abv: float = 5.0
    ibu: float = 30.0
    color_srm: float = 6.0
    
    # Ingredients
    hops: List[Hop] = field(default_factory=list)
    fermentables: List[Fermentable] = field(default_factory=list)
    yeasts: List[Yeast] = field(default_factory=list)
    mash_steps: List[MashStep] = field(default_factory=list)
    
    # Metadata
    style: Optional[Style] = None
    notes: str = ""
    taste_notes: str = ""
    
    @property
    def batch_size_gal(self) -> float:
        """Batch size in gallons"""
        return self.batch_size_l * 0.264172
    
    @property
    def boil_size_gal(self) -> float:
        """Pre-boil volume in gallons"""
        return self.boil_size_l * 0.264172
    
    def get_boil_hops(self) -> List[Hop]:
        """Get hops used during the boil, sorted by time (longest first)"""
        boil_hops = [h for h in self.hops if h.use in [HopUse.BOIL, HopUse.FIRST_WORT]]
        return sorted(boil_hops, key=lambda h: h.time_min, reverse=True)
    
    def get_whirlpool_hops(self) -> List[Hop]:
        """Get hops used at flameout/whirlpool"""
        return [h for h in self.hops if h.use == HopUse.AROMA]
    
    def get_dry_hops(self) -> List[Hop]:
        """Get dry hop additions"""
        return [h for h in self.hops if h.use == HopUse.DRY_HOP]


def parse_beerxml(xml_content: str) -> List[BeerRecipe]:
    """
    Parse BeerXML content and return a list of recipes.
    
    Args:
        xml_content: Raw XML string in BeerXML format
        
    Returns:
        List of BeerRecipe objects
    """
    recipes = []
    
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        raise ValueError(f"Invalid XML format: {e}")
    
    # Find all recipe elements
    recipe_elements = root.findall('.//RECIPE')
    if not recipe_elements:
        # Try without case sensitivity
        recipe_elements = root.findall('.//recipe')
    
    for recipe_elem in recipe_elements:
        recipe = _parse_recipe_element(recipe_elem)
        if recipe:
            recipes.append(recipe)
    
    return recipes


def _get_text(element, tag: str, default: str = "") -> str:
    """Get text content of a child element, case-insensitive"""
    # Try uppercase (standard BeerXML)
    child = element.find(tag.upper())
    if child is None:
        child = element.find(tag.lower())
    if child is None:
        child = element.find(tag)
    return child.text.strip() if child is not None and child.text else default


def _get_float(element, tag: str, default: float = 0.0) -> float:
    """Get float value from a child element"""
    text = _get_text(element, tag)
    try:
        return float(text) if text else default
    except ValueError:
        return default


def _get_int(element, tag: str, default: int = 0) -> int:
    """Get integer value from a child element"""
    return int(_get_float(element, tag, float(default)))


def _parse_recipe_element(recipe_elem) -> Optional[BeerRecipe]:
    """Parse a single RECIPE element into a BeerRecipe object"""
    
    name = _get_text(recipe_elem, 'NAME', 'Unnamed Recipe')
    
    recipe = BeerRecipe(
        name=name,
        type=_get_text(recipe_elem, 'TYPE', 'All Grain'),
        brewer=_get_text(recipe_elem, 'BREWER'),
        batch_size_l=_get_float(recipe_elem, 'BATCH_SIZE', 19.0),
        boil_size_l=_get_float(recipe_elem, 'BOIL_SIZE', 23.0),
        boil_time_min=_get_int(recipe_elem, 'BOIL_TIME', 60),
        efficiency=_get_float(recipe_elem, 'EFFICIENCY', 72.0),
        og=_get_float(recipe_elem, 'OG', 1.050),
        fg=_get_float(recipe_elem, 'FG', 1.010),
        ibu=_get_float(recipe_elem, 'IBU', 30.0),
        notes=_get_text(recipe_elem, 'NOTES'),
        taste_notes=_get_text(recipe_elem, 'TASTE_NOTES'),
    )
    
    # Calculate ABV if OG and FG are present
    if recipe.og > 1.0 and recipe.fg > 1.0:
        recipe.abv = (recipe.og - recipe.fg) * 131.25
    
    # Parse hops
    hops_elem = recipe_elem.find('HOPS') or recipe_elem.find('hops')
    if hops_elem is not None:
        for hop_elem in hops_elem.findall('HOP') or hops_elem.findall('hop'):
            hop = _parse_hop(hop_elem)
            if hop:
                recipe.hops.append(hop)
    
    # Parse fermentables
    ferms_elem = recipe_elem.find('FERMENTABLES') or recipe_elem.find('fermentables')
    if ferms_elem is not None:
        for ferm_elem in ferms_elem.findall('FERMENTABLE') or ferms_elem.findall('fermentable'):
            ferm = _parse_fermentable(ferm_elem)
            if ferm:
                recipe.fermentables.append(ferm)
    
    # Parse yeasts
    yeasts_elem = recipe_elem.find('YEASTS') or recipe_elem.find('yeasts')
    if yeasts_elem is not None:
        for yeast_elem in yeasts_elem.findall('YEAST') or yeasts_elem.findall('yeast'):
            yeast = _parse_yeast(yeast_elem)
            if yeast:
                recipe.yeasts.append(yeast)
    
    # Parse mash profile
    mash_elem = recipe_elem.find('MASH') or recipe_elem.find('mash')
    if mash_elem is not None:
        steps_elem = mash_elem.find('MASH_STEPS') or mash_elem.find('mash_steps')
        if steps_elem is not None:
            for step_elem in steps_elem.findall('MASH_STEP') or steps_elem.findall('mash_step'):
                step = _parse_mash_step(step_elem)
                if step:
                    recipe.mash_steps.append(step)
    
    # Parse style
    style_elem = recipe_elem.find('STYLE') or recipe_elem.find('style')
    if style_elem is not None:
        recipe.style = _parse_style(style_elem)
    
    # Calculate color if not provided
    if recipe.color_srm == 0 and recipe.fermentables:
        recipe.color_srm = _estimate_color(recipe.fermentables, recipe.batch_size_l)
    
    return recipe


def _parse_hop(hop_elem) -> Optional[Hop]:
    """Parse a HOP element"""
    name = _get_text(hop_elem, 'NAME')
    if not name:
        return None
    
    use_str = _get_text(hop_elem, 'USE', 'Boil').lower()
    use_map = {
        'boil': HopUse.BOIL,
        'dry hop': HopUse.DRY_HOP,
        'mash': HopUse.MASH,
        'first wort': HopUse.FIRST_WORT,
        'aroma': HopUse.AROMA,
    }
    use = use_map.get(use_str, HopUse.BOIL)
    
    return Hop(
        name=name,
        amount_kg=_get_float(hop_elem, 'AMOUNT', 0.0),
        time_min=_get_int(hop_elem, 'TIME', 60),
        use=use,
        alpha_acid=_get_float(hop_elem, 'ALPHA', 0.0),
        form=_get_text(hop_elem, 'FORM', 'Pellet'),
    )


def _parse_fermentable(ferm_elem) -> Optional[Fermentable]:
    """Parse a FERMENTABLE element"""
    name = _get_text(ferm_elem, 'NAME')
    if not name:
        return None
    
    type_str = _get_text(ferm_elem, 'TYPE', 'Grain')
    type_map = {
        'grain': FermentableType.GRAIN,
        'sugar': FermentableType.SUGAR,
        'extract': FermentableType.EXTRACT,
        'dry extract': FermentableType.DRY_EXTRACT,
        'adjunct': FermentableType.ADJUNCT,
    }
    ferm_type = type_map.get(type_str.lower(), FermentableType.GRAIN)
    
    return Fermentable(
        name=name,
        amount_kg=_get_float(ferm_elem, 'AMOUNT', 0.0),
        type=ferm_type,
        color_lovibond=_get_float(ferm_elem, 'COLOR', 0.0),
        potential_ppg=_get_float(ferm_elem, 'YIELD', 0.0) * 0.46,  # Convert yield % to PPG
    )


def _parse_yeast(yeast_elem) -> Optional[Yeast]:
    """Parse a YEAST element"""
    name = _get_text(yeast_elem, 'NAME')
    if not name:
        return None
    
    return Yeast(
        name=name,
        type=_get_text(yeast_elem, 'TYPE', 'Ale'),
        form=_get_text(yeast_elem, 'FORM', 'Liquid'),
        lab=_get_text(yeast_elem, 'LABORATORY'),
        product_id=_get_text(yeast_elem, 'PRODUCT_ID'),
        min_temp_c=_get_float(yeast_elem, 'MIN_TEMPERATURE', 15.0),
        max_temp_c=_get_float(yeast_elem, 'MAX_TEMPERATURE', 25.0),
        attenuation=_get_float(yeast_elem, 'ATTENUATION', 75.0),
    )


def _parse_mash_step(step_elem) -> Optional[MashStep]:
    """Parse a MASH_STEP element"""
    name = _get_text(step_elem, 'NAME')
    if not name:
        return None
    
    type_str = _get_text(step_elem, 'TYPE', 'Infusion')
    type_map = {
        'infusion': MashStepType.INFUSION,
        'temperature': MashStepType.TEMPERATURE,
        'decoction': MashStepType.DECOCTION,
    }
    step_type = type_map.get(type_str.lower(), MashStepType.INFUSION)
    
    return MashStep(
        name=name,
        type=step_type,
        step_temp_c=_get_float(step_elem, 'STEP_TEMP', 67.0),
        step_time_min=_get_int(step_elem, 'STEP_TIME', 60),
        infuse_amount_l=_get_float(step_elem, 'INFUSE_AMOUNT', 0.0),
    )


def _parse_style(style_elem) -> Style:
    """Parse a STYLE element"""
    return Style(
        name=_get_text(style_elem, 'NAME', 'Unknown Style'),
        category=_get_text(style_elem, 'CATEGORY'),
        style_guide=_get_text(style_elem, 'STYLE_GUIDE', 'BJCP'),
        type=_get_text(style_elem, 'TYPE', 'Ale'),
        og_min=_get_float(style_elem, 'OG_MIN', 1.040),
        og_max=_get_float(style_elem, 'OG_MAX', 1.060),
        fg_min=_get_float(style_elem, 'FG_MIN', 1.008),
        fg_max=_get_float(style_elem, 'FG_MAX', 1.016),
        ibu_min=_get_float(style_elem, 'IBU_MIN', 20),
        ibu_max=_get_float(style_elem, 'IBU_MAX', 40),
        color_min=_get_float(style_elem, 'COLOR_MIN', 4.0),
        color_max=_get_float(style_elem, 'COLOR_MAX', 14.0),
        abv_min=_get_float(style_elem, 'ABV_MIN', 4.0),
        abv_max=_get_float(style_elem, 'ABV_MAX', 6.0),
    )


def _estimate_color(fermentables: List[Fermentable], batch_size_l: float) -> float:
    """Estimate beer color in SRM using the Morey equation"""
    if batch_size_l <= 0:
        return 0.0
    
    batch_size_gal = batch_size_l * 0.264172
    mcu = sum(f.color_lovibond * f.amount_lb for f in fermentables) / batch_size_gal
    
    # Morey equation: SRM = 1.4922 * (MCU ^ 0.6859)
    if mcu > 0:
        return 1.4922 * (mcu ** 0.6859)
    return 0.0


def parse_beerxml_file(file_path: str) -> List[BeerRecipe]:
    """
    Parse a BeerXML file and return a list of recipes.
    
    Args:
        file_path: Path to the BeerXML file
        
    Returns:
        List of BeerRecipe objects
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        return parse_beerxml(f.read())
