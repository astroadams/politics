#!/usr/bin/env python3
"""
Create proper state boundaries with correctly aggregated election data from precinct files.
"""

import geopandas as gpd
import pandas as pd
import os
from pathlib import Path

def create_proper_state_boundaries():
    """Create state boundaries with properly aggregated election data from precincts."""
    
    states_dir = Path('data/states/by_state')
    if not states_dir.exists():
        print("Error: No state data found.")
        return False
    
    state_boundaries = []
    
    print("Creating proper state boundaries from precinct data...")
    
    # Find all state directories
    state_dirs = [d for d in states_dir.iterdir() if d.is_dir()]
    
    for state_dir in state_dirs:
        state_fips = state_dir.name
        precincts_dir = state_dir / "precincts"
        
        if not precincts_dir.exists():
            print(f"Warning: No precincts directory for state {state_fips}")
            continue
            
        print(f"Processing state {state_fips}...")
        
        # Collect all precinct files for this state
        precinct_files = list(precincts_dir.glob("*_precincts.geojson"))
        
        if not precinct_files:
            print(f"Warning: No precinct files found for state {state_fips}")
            continue
        
        # Load and combine all precincts for this state
        state_precincts = []
        for precinct_file in precinct_files:
            try:
                precinct_gdf = gpd.read_file(precinct_file)
                state_precincts.append(precinct_gdf)
            except Exception as e:
                print(f"Warning: Could not read {precinct_file}: {e}")
        
        if not state_precincts:
            print(f"Warning: No valid precinct data for state {state_fips}")
            continue
        
        # Combine all precincts for this state
        state_gdf = gpd.GeoDataFrame(pd.concat(state_precincts, ignore_index=True), crs='EPSG:4326')
        
        # Fix invalid geometries
        state_gdf['geometry'] = state_gdf.geometry.buffer(0)
        
        # Aggregate election data at state level
        total_votes_dem = state_gdf['votes_dem'].sum()
        total_votes_rep = state_gdf['votes_rep'].sum() 
        total_votes = state_gdf['votes_total'].sum()
        pct_dem_lead = ((total_votes_dem - total_votes_rep) / total_votes * 100) if total_votes > 0 else 0
        
        print(f"  State {state_fips}: {total_votes:,} total votes, {pct_dem_lead:.1f}% Dem lead")
        
        # Create dissolved state boundary
        try:
            state_boundary = state_gdf.dissolve().reset_index(drop=True)
        except Exception as e:
            print(f"  Warning: Dissolve failed for state {state_fips}, using unary_union: {e}")
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
    
    # Save updated national state boundaries
    if state_boundaries:
        print("Combining all states for national boundaries...")
        national_states = gpd.GeoDataFrame(pd.concat(state_boundaries, ignore_index=True), crs='EPSG:4326')
        
        # Remove any unwanted columns that might have carried over
        keep_columns = ['state_fips', 'votes_dem', 'votes_rep', 'votes_total', 'pct_dem_lead', 'geometry']
        for col in national_states.columns:
            if col not in keep_columns:
                national_states = national_states.drop(columns=[col])
        
        output_file = 'data/states/state_boundaries.geojson'
        national_states.to_file(output_file, driver='GeoJSON')
        print(f"Successfully created {output_file} with {len(national_states)} states")
        
        # Show summary
        print("\nState-level summary (first 5 states):")
        print("State | Dem Votes | Rep Votes | Dem Lead %")
        print("------|-----------|-----------|----------")
        for i in range(min(5, len(national_states))):
            row = national_states.iloc[i]
            print(f"{row['state_fips']:5s} | {row['votes_dem']:9.0f} | {row['votes_rep']:9.0f} | {row['pct_dem_lead']:8.1f}%")
        
        return True
    else:
        print("Error: No valid state data found")
        return False

if __name__ == "__main__":
    success = create_proper_state_boundaries()
    if success:
        print("\nProper state boundaries created successfully!")
        print("The visualization should now show correct state-level data.")
    else:
        print("Failed to create proper state boundaries.")