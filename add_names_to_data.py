#!/usr/bin/env python3
"""
Add state and county names to the data files for better user interface.
"""

import pandas as pd
import geopandas as gpd
import os
from pathlib import Path

# State FIPS to name mapping
STATE_NAMES = {
    '01': 'Alabama', '02': 'Alaska', '04': 'Arizona', '05': 'Arkansas',
    '06': 'California', '08': 'Colorado', '09': 'Connecticut', '10': 'Delaware',
    '11': 'Washington DC', '12': 'Florida', '13': 'Georgia', '15': 'Hawaii',
    '16': 'Idaho', '17': 'Illinois', '18': 'Indiana', '19': 'Iowa',
    '20': 'Kansas', '21': 'Kentucky', '22': 'Louisiana', '23': 'Maine',
    '24': 'Maryland', '25': 'Massachusetts', '26': 'Michigan', '27': 'Minnesota',
    '28': 'Mississippi', '29': 'Missouri', '30': 'Montana', '31': 'Nebraska',
    '32': 'Nevada', '33': 'New Hampshire', '34': 'New Jersey', '35': 'New Mexico',
    '36': 'New York', '37': 'North Carolina', '38': 'North Dakota', '39': 'Ohio',
    '40': 'Oklahoma', '41': 'Oregon', '42': 'Pennsylvania', '44': 'Rhode Island',
    '45': 'South Carolina', '46': 'South Dakota', '47': 'Tennessee', '48': 'Texas',
    '49': 'Utah', '50': 'Vermont', '51': 'Virginia', '53': 'Washington',
    '54': 'West Virginia', '55': 'Wisconsin', '56': 'Wyoming'
}

def load_county_names():
    """Load county names from the county presidential data."""
    print("Loading county names from county CSV data...")
    
    try:
        # Read the county presidential CSV file which has county names
        df = pd.read_csv('data/countypres_2000-2016.csv')
        
        # Get unique state/county combinations  
        county_data = df[['state_po', 'county', 'FIPS']].drop_duplicates()
        
        # Create county lookup dictionary using FIPS codes
        county_names = {}
        for _, row in county_data.iterrows():
            if pd.notna(row['FIPS']) and pd.notna(row['county']):
                # FIPS is already the full state+county code
                fips_key = f"{int(row['FIPS']):05d}"  # Ensure 5-digit format
                county_names[fips_key] = row['county']
        
        print(f"Loaded {len(county_names)} county names")
        
        # Show some examples
        sample_counties = list(county_names.items())[:5]
        for fips, name in sample_counties:
            print(f"  {fips}: {name}")
        
        return county_names
        
    except Exception as e:
        print(f"Error loading county names: {e}")
        print("Will use FIPS codes as fallback")
        return {}

def add_names_to_state_boundaries():
    """Add state names to state boundaries file."""
    state_file = 'data/states/state_boundaries.geojson'
    
    if not os.path.exists(state_file):
        print(f"State boundaries file not found: {state_file}")
        return False
    
    print("Adding state names to state boundaries...")
    
    try:
        gdf = gpd.read_file(state_file)
        
        # Add state names
        gdf['state_name'] = gdf['state_fips'].map(STATE_NAMES)
        
        # Fill any missing names with FIPS codes
        gdf['state_name'] = gdf['state_name'].fillna('State ' + gdf['state_fips'])
        
        # Save updated file
        gdf.to_file(state_file, driver='GeoJSON')
        
        print(f"✅ Added state names to {len(gdf)} states")
        
        # Show sample
        for _, row in gdf.head(3).iterrows():
            print(f"   {row['state_fips']}: {row['state_name']}")
        
        return True
        
    except Exception as e:
        print(f"Error updating state boundaries: {e}")
        return False

def add_names_to_county_files():
    """Add state and county names to county files."""
    print("Adding names to county files...")
    
    county_names = load_county_names()
    states_dir = Path('data/states/by_state')
    
    if not states_dir.exists():
        print("States directory not found")
        return False
    
    updated_count = 0
    
    for state_dir in states_dir.iterdir():
        if state_dir.is_dir():
            state_fips = state_dir.name
            state_name = STATE_NAMES.get(state_fips, f'State {state_fips}')
            
            county_file = state_dir / f'counties_{state_fips}.geojson'
            
            if county_file.exists():
                try:
                    gdf = gpd.read_file(county_file)
                    
                    # Add state name
                    gdf['state_name'] = state_name
                    
                    # Add county names
                    gdf['county_name'] = gdf['county_fips'].map(county_names)
                    
                    # For missing county names, extract from county_fips
                    mask = gdf['county_name'].isna()
                    if mask.any():
                        gdf.loc[mask, 'county_name'] = 'County ' + gdf.loc[mask, 'county_fips'].str[-3:]
                    
                    # Save updated file
                    gdf.to_file(county_file, driver='GeoJSON')
                    
                    updated_count += 1
                    
                    if updated_count <= 3:  # Show sample
                        print(f"   {state_name}: {len(gdf)} counties")
                    
                except Exception as e:
                    print(f"   Error updating {county_file}: {e}")
    
    print(f"✅ Updated {updated_count} county files")
    return True

def add_names_to_precinct_files():
    """Add state and county names to precinct files."""
    print("Adding names to precinct files...")
    print("(This may take a while for large numbers of files)")
    
    county_names = load_county_names()
    states_dir = Path('data/states/by_state')
    
    if not states_dir.exists():
        print("States directory not found")
        return False
    
    updated_count = 0
    
    for state_dir in states_dir.iterdir():
        if state_dir.is_dir():
            state_fips = state_dir.name
            state_name = STATE_NAMES.get(state_fips, f'State {state_fips}')
            
            precincts_dir = state_dir / 'precincts'
            
            if precincts_dir.exists():
                precinct_files = list(precincts_dir.glob('*_precincts.geojson'))
                
                for precinct_file in precinct_files:
                    try:
                        # Extract county FIPS from filename
                        filename = precinct_file.stem
                        county_fips_full = filename.replace('_precincts', '')
                        county_name = county_names.get(county_fips_full, f'County {county_fips_full[-3:]}')
                        
                        gdf = gpd.read_file(precinct_file)
                        
                        # Add state and county names
                        gdf['state_name'] = state_name
                        gdf['county_name'] = county_name
                        
                        # Save updated file
                        gdf.to_file(precinct_file, driver='GeoJSON')
                        
                        updated_count += 1
                        
                        if updated_count % 50 == 0:
                            print(f"   Updated {updated_count} precinct files...")
                        
                    except Exception as e:
                        print(f"   Error updating {precinct_file}: {e}")
    
    print(f"✅ Updated {updated_count} precinct files")
    return True

def add_all_names():
    """Add names to all data files."""
    print("=== ADDING STATE AND COUNTY NAMES ===")
    print("This will make the interface more user-friendly.\n")
    
    success = True
    
    # 1. Add names to state boundaries
    if not add_names_to_state_boundaries():
        success = False
    print()
    
    # 2. Add names to county files
    if not add_names_to_county_files():
        success = False
    print()
    
    # 3. Add names to precinct files
    if not add_names_to_precinct_files():
        success = False
    print()
    
    if success:
        print("=== SUMMARY ===")
        print("✅ Added state names to all files")
        print("✅ Added county names to county and precinct files") 
        print("✅ Interface will now show readable names instead of FIPS codes")
    else:
        print("⚠️  Some errors occurred while adding names")
    
    return success

if __name__ == "__main__":
    print("This will add state and county names to all data files.")
    print("This makes the interface more user-friendly.")
    print()
    response = input("Continue? (y/N): ")
    
    if response.lower() in ['y', 'yes']:
        add_all_names()
    else:
        print("Cancelled.")