#!/usr/bin/env python3
"""
Split large precinct GeoJSON file into hierarchical structure for efficient loading.
"""

import json
import os
from collections import defaultdict
import geopandas as gpd
import pandas as pd
from pathlib import Path

def extract_fips_codes(geoid):
    """Extract state and county FIPS codes from GEOID."""
    # GEOID format appears to be: "05047-1-A (Oz Wd 1)" where 05=state, 047=county
    fips_part = geoid.split('-')[0] if '-' in geoid else geoid[:5]
    
    if len(fips_part) >= 5:
        state_fips = fips_part[:2]
        county_fips = fips_part[2:5]
        return state_fips, county_fips
    elif len(fips_part) >= 2:
        state_fips = fips_part[:2]
        return state_fips, None
    else:
        return None, None

def create_directory_structure(base_path):
    """Create the hierarchical directory structure."""
    os.makedirs(f"{base_path}/states", exist_ok=True)
    os.makedirs(f"{base_path}/states/by_state", exist_ok=True)

def split_precinct_data(input_file, output_base_dir):
    """Split large precinct file into hierarchical structure."""
    print(f"Loading data from {input_file}...")
    
    # Create output directory structure
    create_directory_structure(output_base_dir)
    
    # Read the large file in chunks to manage memory
    print("Processing precincts...")
    
    # Group precincts by state and county
    state_groups = defaultdict(list)
    county_groups = defaultdict(list)
    
    # Read file
    gdf = gpd.read_file(input_file)
    
    # Ensure CRS is set (use WGS84 for web mapping)
    if gdf.crs is None:
        gdf.set_crs('EPSG:4326', inplace=True)
    else:
        # Convert to WGS84 if not already
        gdf = gdf.to_crs('EPSG:4326')
    
    print(f"Loaded {len(gdf)} precincts")
    
    # Process each precinct
    for idx, row in gdf.iterrows():
        geoid = row.get('GEOID', '')
        state_fips, county_fips = extract_fips_codes(geoid)
        
        if state_fips:
            # Add to state group
            state_groups[state_fips].append(row)
            
            if county_fips:
                # Add to county group
                county_key = f"{state_fips}{county_fips}"
                county_groups[county_key].append(row)
    
    print(f"Found {len(state_groups)} states and {len(county_groups)} counties")
    
    # Create state-level files
    print("Creating state-level files...")
    state_boundaries = []
    
    for state_fips, precincts in state_groups.items():
        state_dir = f"{output_base_dir}/states/by_state/{state_fips}"
        os.makedirs(state_dir, exist_ok=True)
        os.makedirs(f"{state_dir}/precincts", exist_ok=True)
        
        # Create state GeoDataFrame from precincts
        state_gdf = gpd.GeoDataFrame(precincts, crs='EPSG:4326')
        
        # Fix invalid geometries before dissolve
        state_gdf['geometry'] = state_gdf.geometry.buffer(0)
        
        # Aggregate election data at state level
        total_votes_dem = state_gdf['votes_dem'].sum()
        total_votes_rep = state_gdf['votes_rep'].sum() 
        total_votes = state_gdf['votes_total'].sum()
        pct_dem_lead = ((total_votes_dem - total_votes_rep) / total_votes * 100) if total_votes > 0 else 0
        
        # Create dissolved state boundary for overview map
        try:
            state_boundary = state_gdf.dissolve().reset_index(drop=True)
        except Exception as e:
            print(f"Warning: Dissolve failed for state {state_fips}, using unary_union instead: {e}")
            from shapely.ops import unary_union
            dissolved_geom = unary_union(state_gdf.geometry.values)
            state_boundary = gpd.GeoDataFrame({'geometry': [dissolved_geom]}, crs='EPSG:4326')
        
        # Add aggregated election data to state boundary
        state_boundary['state_fips'] = state_fips
        state_boundary['votes_dem'] = total_votes_dem
        state_boundary['votes_rep'] = total_votes_rep
        state_boundary['votes_total'] = total_votes
        state_boundary['pct_dem_lead'] = pct_dem_lead
        state_boundaries.append(state_boundary)
        
        # Save state boundary
        state_boundary.to_file(f"{state_dir}/state_{state_fips}.geojson", driver='GeoJSON')
        
        # Create county-level aggregation for this state
        state_counties = []
        state_county_keys = [k for k in county_groups.keys() if k.startswith(state_fips)]
        
        for county_key in state_county_keys:
            county_precincts = county_groups[county_key]
            county_gdf = gpd.GeoDataFrame(county_precincts, crs='EPSG:4326')
            
            # Fix invalid geometries before dissolve
            county_gdf['geometry'] = county_gdf.geometry.buffer(0)
            
            # Aggregate election data at county level
            county_votes_dem = county_gdf['votes_dem'].sum()
            county_votes_rep = county_gdf['votes_rep'].sum() 
            county_votes_total = county_gdf['votes_total'].sum()
            county_pct_dem_lead = ((county_votes_dem - county_votes_rep) / county_votes_total * 100) if county_votes_total > 0 else 0
            
            # Create dissolved county boundary
            try:
                county_boundary = county_gdf.dissolve().reset_index(drop=True)
            except Exception as e:
                print(f"Warning: Dissolve failed for county {county_key}, using unary_union instead: {e}")
                from shapely.ops import unary_union
                dissolved_geom = unary_union(county_gdf.geometry.values)
                county_boundary = gpd.GeoDataFrame({'geometry': [dissolved_geom]}, crs='EPSG:4326')
            
            # Add aggregated election data to county boundary
            county_boundary['county_fips'] = county_key
            county_boundary['votes_dem'] = county_votes_dem
            county_boundary['votes_rep'] = county_votes_rep
            county_boundary['votes_total'] = county_votes_total
            county_boundary['pct_dem_lead'] = county_pct_dem_lead
            state_counties.append(county_boundary)
            
            # Save precinct-level data for this county
            county_gdf.to_file(f"{state_dir}/precincts/{county_key}_precincts.geojson", driver='GeoJSON')
        
        # Save all counties for this state
        if state_counties:
            counties_gdf = gpd.GeoDataFrame(pd.concat(state_counties, ignore_index=True), crs='EPSG:4326')
            counties_gdf.to_file(f"{state_dir}/counties_{state_fips}.geojson", driver='GeoJSON')
    
    # Save national state boundaries
    if state_boundaries:
        national_states = gpd.GeoDataFrame(pd.concat(state_boundaries, ignore_index=True), crs='EPSG:4326')
        national_states.to_file(f"{output_base_dir}/states/state_boundaries.geojson", driver='GeoJSON')
    
    print("Split completed successfully!")
    print(f"Files created in: {output_base_dir}")
    print(f"- National state boundaries: states/state_boundaries.geojson")
    print(f"- State directories: states/by_state/XX/")
    print(f"- County precincts: states/by_state/XX/precincts/XXXXX_precincts.geojson")

if __name__ == "__main__":
    input_file = "data/precincts-with-results.geojson"
    output_dir = "data"
    
    if not os.path.exists(input_file):
        print(f"Error: Input file {input_file} not found")
        exit(1)
    
    split_precinct_data(input_file, output_dir)