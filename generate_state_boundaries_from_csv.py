#!/usr/bin/env python3
"""
Generate clean state_boundaries.geojson from 2020 election results in CSV file.
Uses state-level results and creates simple geometries.
"""

import pandas as pd
import geopandas as gpd
import requests
import json
from pathlib import Path

def load_state_geometries():
    """Load state geometries from existing shapefile."""
    print("Loading state geometries from shapefile...")
    
    shapefile_path = 'data/tl_2019_us_state.shp'
    
    try:
        states_gdf = gpd.read_file(shapefile_path)
        print(f"Loaded {len(states_gdf)} state geometries")
        
        # Check available columns
        print(f"Shapefile columns: {list(states_gdf.columns)}")
        
        # The shapefile should have a STATEFP column with FIPS codes
        if 'STATEFP' in states_gdf.columns:
            states_gdf['state_fips'] = states_gdf['STATEFP']
        elif 'GEOID' in states_gdf.columns:
            states_gdf['state_fips'] = states_gdf['GEOID']
        else:
            print("Warning: No FIPS code column found, using index")
            
        return states_gdf
        
    except Exception as e:
        print(f"Error loading shapefile: {e}")
        return None

def create_state_boundaries_from_csv():
    """Create state boundaries using CSV election data and simple geometries."""
    
    # Read the election data
    print("Reading election data...")
    df = pd.read_csv('data/1976-2020-president.csv')
    
    # Filter for 2020 data only
    df_2020 = df[df['year'] == 2020].copy()
    
    print(f"Found {len(df_2020)} records for 2020")
    
    # Aggregate by state and party
    print("Aggregating 2020 results by state...")
    
    # Group by state and party_simplified to get totals
    state_totals = df_2020.groupby(['state_fips', 'party_simplified'])['candidatevotes'].sum().reset_index()
    
    # Pivot to get Dem and Republican columns
    state_pivot = state_totals.pivot(index='state_fips', columns='party_simplified', values='candidatevotes').fillna(0)
    
    # Calculate totals and percentages
    state_results = []
    
    for state_fips in state_pivot.index:
        dem_votes = state_pivot.loc[state_fips, 'DEMOCRAT'] if 'DEMOCRAT' in state_pivot.columns else 0
        rep_votes = state_pivot.loc[state_fips, 'REPUBLICAN'] if 'REPUBLICAN' in state_pivot.columns else 0
        other_votes = sum([state_pivot.loc[state_fips, col] for col in state_pivot.columns 
                          if col not in ['DEMOCRAT', 'REPUBLICAN']])
        
        total_votes = dem_votes + rep_votes + other_votes
        
        if total_votes > 0:
            pct_dem_lead = ((dem_votes - rep_votes) / total_votes) * 100
            
            state_results.append({
                'state_fips': f"{int(state_fips):02d}",  # Ensure 2-digit format
                'votes_dem': int(dem_votes),
                'votes_rep': int(rep_votes),
                'votes_total': int(total_votes),
                'pct_dem_lead': pct_dem_lead
            })
    
    print(f"Processed {len(state_results)} states")
    
    # Load state geometries from shapefile
    states_gdf = load_state_geometries()
    
    if states_gdf is None:
        print("Failed to load state geometries")
        return False
    
    # Convert state results to DataFrame
    results_df = pd.DataFrame(state_results)
    
    # Merge election results with state geometries
    print("Merging election results with state geometries...")
    
    # Ensure both FIPS codes are strings with leading zeros
    results_df['state_fips'] = results_df['state_fips'].astype(str).str.zfill(2)
    states_gdf['state_fips'] = states_gdf['state_fips'].astype(str).str.zfill(2)
    
    # Merge the data
    gdf = states_gdf.merge(results_df, on='state_fips', how='inner')
    
    print(f"Successfully merged {len(gdf)} states")
    
    # Show results
    for _, row in gdf.iterrows():
        print(f"State {row['state_fips']}: {row['votes_dem']:,} Dem, {row['votes_rep']:,} Rep, {row['pct_dem_lead']:+.1f}% lead")
    
    # Keep only essential columns
    keep_columns = ['state_fips', 'votes_dem', 'votes_rep', 'votes_total', 'pct_dem_lead', 'geometry']
    gdf = gdf[keep_columns]
    
    # Save to file
    output_file = 'data/states/state_boundaries.geojson'
    gdf.to_file(output_file, driver='GeoJSON')
    
    print(f"\nSuccessfully created {output_file} with {len(gdf)} states")
    print("File size should be much smaller and properly formatted")
    
    return True

if __name__ == "__main__":
    success = create_state_boundaries_from_csv()
    if success:
        print("\nState boundaries generated successfully from CSV data!")
        print("The visualization should now work with correct 2020 election results.")
    else:
        print("Failed to generate state boundaries.")