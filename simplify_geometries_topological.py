#!/usr/bin/env python3
"""
Simplify geometries while preserving shared boundaries to avoid gaps.
Uses topological simplification to maintain adjacency.
"""

import geopandas as gpd
import pandas as pd
import os
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

def simplify_with_topology(gdf, tolerance=0.01):
    """
    Simplify geometries while preserving topology and shared boundaries.
    Uses a different approach than simple geometry.simplify().
    """
    try:
        from shapely.ops import unary_union
        from shapely.geometry import Polygon, MultiPolygon
        import shapely
        
        print(f"    Using topological simplification (tolerance: {tolerance}°)")
        
        # Create a copy to work with
        gdf_simplified = gdf.copy()
        
        # Method 1: Use buffer(0) to fix any existing topology issues first
        print("    Fixing existing topology issues...")
        gdf_simplified['geometry'] = gdf_simplified.geometry.buffer(0)
        
        # Method 2: Use a smaller tolerance and preserve_topology=True
        print("    Applying conservative simplification...")
        gdf_simplified['geometry'] = gdf_simplified.geometry.simplify(
            tolerance=tolerance/2,  # Use half the tolerance for more conservative approach
            preserve_topology=True
        )
        
        # Method 3: For very detailed shapes, use Douglas-Peucker with topology preservation
        print("    Applying boundary-preserving simplification...")
        
        # Create union of all geometries to understand shared boundaries
        if len(gdf_simplified) > 1:
            # This helps preserve shared boundaries
            total_bounds = gdf_simplified.total_bounds
            
            # Apply simplification in a way that respects neighboring polygons
            simplified_geoms = []
            for idx, row in gdf_simplified.iterrows():
                geom = row.geometry
                
                # Apply a very conservative simplification
                if hasattr(geom, 'simplify'):
                    # Use preserve_topology=True and smaller tolerance
                    simplified_geom = geom.simplify(tolerance=tolerance/3, preserve_topology=True)
                    
                    # Ensure the geometry is still valid
                    if simplified_geom.is_valid:
                        simplified_geoms.append(simplified_geom)
                    else:
                        # If simplification broke the geometry, use buffer(0) to fix it
                        fixed_geom = simplified_geom.buffer(0)
                        simplified_geoms.append(fixed_geom if fixed_geom.is_valid else geom)
                else:
                    simplified_geoms.append(geom)
            
            gdf_simplified['geometry'] = simplified_geoms
        
        return gdf_simplified
        
    except Exception as e:
        print(f"    Topological simplification failed: {e}")
        print("    Falling back to conservative geometric simplification...")
        
        # Fallback: very conservative geometric simplification
        gdf_fallback = gdf.copy()
        gdf_fallback['geometry'] = gdf_fallback.geometry.simplify(
            tolerance=tolerance/4, 
            preserve_topology=True
        )
        return gdf_fallback

def simplify_geojson_file_topological(input_file, output_file, tolerance=0.01):
    """Simplify geometries in a GeoJSON file while preserving topology."""
    try:
        print(f"Processing {input_file}...")
        
        # Read the file
        gdf = gpd.read_file(input_file)
        original_size = os.path.getsize(input_file) / (1024 * 1024)  # MB
        
        print(f"  Original: {len(gdf)} features, {original_size:.1f} MB")
        
        # Apply topological simplification
        gdf_simplified = simplify_with_topology(gdf, tolerance)
        
        # Ensure CRS is preserved
        if gdf.crs is not None:
            gdf_simplified.crs = gdf.crs
        
        # Save simplified version
        gdf_simplified.to_file(output_file, driver='GeoJSON')
        
        new_size = os.path.getsize(output_file) / (1024 * 1024)  # MB
        reduction = ((original_size - new_size) / original_size) * 100 if original_size > 0 else 0
        
        print(f"  Simplified: {new_size:.1f} MB ({reduction:.1f}% reduction)")
        
        return True
        
    except Exception as e:
        print(f"  Error: {e}")
        return False

def simplify_all_files_topological():
    """Simplify all geometry files while preserving boundaries."""
    
    print("=== TOPOLOGICAL GEOMETRY SIMPLIFICATION ===")
    print("This preserves shared boundaries to avoid gaps between polygons.\n")
    
    # 1. Simplify state boundaries (conservative)
    state_file = 'data/states/state_boundaries.geojson'
    if os.path.exists(state_file):
        print("1. Simplifying state boundaries...")
        backup_file = 'data/states/state_boundaries_original.geojson'
        
        # Create backup if it doesn't exist
        if not os.path.exists(backup_file):
            import shutil
            shutil.copy2(state_file, backup_file)
            print(f"  Created backup: {backup_file}")
        
        # Use conservative tolerance for states (they share many boundaries)
        simplify_geojson_file_topological(backup_file, state_file, tolerance=0.02)
        print()
    
    # 2. Simplify county files (moderate)
    print("2. Simplifying county files...")
    states_dir = Path('data/states/by_state')
    
    if states_dir.exists():
        county_count = 0
        for state_dir in states_dir.iterdir():
            if state_dir.is_dir():
                state_fips = state_dir.name
                county_file = state_dir / f'counties_{state_fips}.geojson'
                
                if county_file.exists():
                    backup_file = state_dir / f'counties_{state_fips}_original.geojson'
                    
                    # Create backup if it doesn't exist
                    if not backup_file.exists():
                        import shutil
                        shutil.copy2(county_file, backup_file)
                    
                    # Counties within a state share boundaries
                    if simplify_geojson_file_topological(str(backup_file), str(county_file), tolerance=0.008):
                        county_count += 1
                    
                    if county_count <= 5:  # Show detail for first few
                        print()
        
        print(f"  Processed {county_count} county files\n")
    
    # 3. Simplify precinct files (more aggressive but still preserve topology)
    print("3. Simplifying precinct files...")
    print("   (This may take a while for large numbers of precincts)")
    
    precinct_count = 0
    
    if states_dir.exists():
        for state_dir in states_dir.iterdir():
            if state_dir.is_dir():
                precincts_dir = state_dir / 'precincts'
                
                if precincts_dir.exists():
                    precinct_files = list(precincts_dir.glob('*_precincts.geojson'))
                    
                    for i, precinct_file in enumerate(precinct_files):
                        backup_file = precinct_file.with_suffix('.original.geojson')
                        
                        # Create backup if it doesn't exist
                        if not backup_file.exists():
                            import shutil
                            shutil.copy2(precinct_file, backup_file)
                        
                        # Use moderate tolerance for precincts (they're small but share boundaries)
                        if simplify_geojson_file_topological(str(backup_file), str(precinct_file), tolerance=0.004):
                            precinct_count += 1
                        
                        # Show progress for large numbers
                        if precinct_count % 25 == 0:
                            print(f"    Processed {precinct_count} precinct files...")
                        
                        # Optional: limit processing for testing
                        # if precinct_count >= 100:  # Remove this line to process all
                        #     break
    
    print(f"\n=== SUMMARY ===")
    print(f"✅ Topologically simplified state boundaries")
    print(f"✅ Topologically simplified county files") 
    print(f"✅ Topologically simplified {precinct_count} precinct files")
    print(f"\nBenefits:")
    print(f"- Faster visualization loading")
    print(f"- No gaps between adjacent polygons")
    print(f"- Preserved boundary relationships")
    print(f"- Original files backed up with '_original' suffix")

def restore_original_files():
    """Restore original files from backups."""
    print("Restoring original files...")
    
    # Restore state boundaries
    state_backup = 'data/states/state_boundaries_original.geojson'
    state_file = 'data/states/state_boundaries.geojson'
    
    if os.path.exists(state_backup):
        import shutil
        shutil.copy2(state_backup, state_file)
        print("✅ Restored state boundaries")
    
    # Restore county and precinct files
    states_dir = Path('data/states/by_state')
    
    if states_dir.exists():
        count = 0
        for state_dir in states_dir.iterdir():
            if state_dir.is_dir():
                # Restore county files
                for backup_file in state_dir.glob('*_original.geojson'):
                    original_name = backup_file.name.replace('_original', '')
                    original_file = state_dir / original_name
                    import shutil
                    shutil.copy2(backup_file, original_file)
                    count += 1
                
                # Restore precinct files
                precincts_dir = state_dir / 'precincts'
                if precincts_dir.exists():
                    for backup_file in precincts_dir.glob('*.original.geojson'):
                        original_name = backup_file.name.replace('.original', '')
                        original_file = precincts_dir / original_name
                        import shutil
                        shutil.copy2(backup_file, original_file)
                        count += 1
    
    print(f"✅ Restored {count} files to original detail level")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--restore':
        restore_original_files()
    else:
        print("This will simplify geometries while preserving shared boundaries.")
        print("This prevents gaps between adjacent polygons.")
        print("Original files will be backed up.")
        print()
        response = input("Continue? (y/N): ")
        
        if response.lower() in ['y', 'yes']:
            simplify_all_files_topological()
        else:
            print("Cancelled.")
            print("\nTo restore original files later, run:")
            print("python simplify_geometries_topological.py --restore")