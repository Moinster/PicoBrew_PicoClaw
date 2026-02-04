#!/usr/bin/env python
"""Test the recipe converter with a sample BeerXML file."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from app.main.recipe_converter import convert_beerxml_to_device

with open('scripts/test_recipe.xml', 'r') as f:
    xml = f.read()

for device in ['pico', 'zymatic', 'zseries']:
    converted = convert_beerxml_to_device(xml, device)
    print(f'\n=== {device.upper()} ===')
    for step in converted[0]['steps'][:8]:
        print(f"  {step['name']}: {step['location']} @ {step['temperature']}F for {step['step_time']}min")
    if len(converted[0]['steps']) > 8:
        print(f"  ... ({len(converted[0]['steps']) - 8} more steps)")
