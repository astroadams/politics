#!/usr/bin/env python3
"""
Generate hierarchical vector tiles from precinct election data.
Creates MVT tiles for efficient web mapping at multiple zoom levels.
"""

import os
import json
import math
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import geopandas as gpd
import pandas as pd
import mercantile
import mapbox_vector_tile
from shapely.geometry import mapping, shape
from shapely.ops import transform
import pyproj
from functools import partial

class VectorTileGenerator:
    """Generate vector tiles from hierarchical election data."""
    
    def __init__(self, data_dir: str, output_dir: str):
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Tile configuration
        self.min_zoom = 0   # Continental view
        self.max_zoom = 14  # Detailed precinct view
        self.tile_size = 512  # Higher resolution tiles
        
        # Data caches
        self.state_data = None
        self.county_data_cache = {}
        self.precinct_data_cache = {}
        
        # Create tile database
        self.db_path = self.output_dir / "tiles.mbtiles"
        self.init_tile_db()
    
    def init_tile_db(self):
        """Initialize MBTiles database for storing tiles."""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS tiles (
                zoom_level INTEGER,
                tile_column INTEGER,
                tile_row INTEGER,
                tile_data BLOB,
                PRIMARY KEY (zoom_level, tile_column, tile_row)
            )
        """)
        
        # Create metadata table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                name TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        # Insert metadata
        metadata = {
            'name': 'US Election Precinct Data',
            'description': 'Hierarchical election data tiles',
            'version': '1.0',
            'type': 'overlay',
            'format': 'pbf',
            'minzoom': str(self.min_zoom),
            'maxzoom': str(self.max_zoom),
            'bounds': '-180,-85,180,85',
            'center': '-98,39,4'
        }
        
        for key, value in metadata.items():
            self.conn.execute(
                "INSERT OR REPLACE INTO metadata (name, value) VALUES (?, ?)",
                (key, value)
            )
        
        self.conn.commit()
    
    def load_state_data(self) -> gpd.GeoDataFrame:
        """Load state-level data."""
        if self.state_data is None:
            state_file = self.data_dir / "states" / "state_boundaries.geojson"
            if state_file.exists():
                self.state_data = gpd.read_file(state_file)
                # Ensure WGS84
                if self.state_data.crs != 'EPSG:4326':
                    self.state_data = self.state_data.to_crs('EPSG:4326')
                print(f"Loaded {len(self.state_data)} states")
            else:
                print(f"State data not found at {state_file}")
                return gpd.GeoDataFrame()
        return self.state_data
    
    def load_county_data(self, state_fips: str) -> Optional[gpd.GeoDataFrame]:
        """Load county data for a specific state."""
        if state_fips not in self.county_data_cache:
            county_file = self.data_dir / "states" / "by_state" / state_fips / f"counties_{state_fips}.geojson"
            if county_file.exists():
                try:
                    gdf = gpd.read_file(county_file)
                    if gdf.crs != 'EPSG:4326':
                        gdf = gdf.to_crs('EPSG:4326')
                    self.county_data_cache[state_fips] = gdf
                    print(f"Loaded {len(gdf)} counties for state {state_fips}")
                except Exception as e:
                    print(f"Error loading counties for state {state_fips}: {e}")
                    self.county_data_cache[state_fips] = None
            else:
                self.county_data_cache[state_fips] = None
        return self.county_data_cache[state_fips]
    
    def load_precinct_data(self, state_fips: str, county_fips: str) -> Optional[gpd.GeoDataFrame]:
        """Load precinct data for a specific county."""
        key = f"{state_fips}_{county_fips}"
        if key not in self.precinct_data_cache:
            precinct_file = self.data_dir / "states" / "by_state" / state_fips / "precincts" / f"{county_fips}_precincts.geojson"
            if precinct_file.exists():
                try:
                    gdf = gpd.read_file(precinct_file)
                    if gdf.crs != 'EPSG:4326':
                        gdf = gdf.to_crs('EPSG:4326')
                    # Simplify geometries for tiles
                    gdf.geometry = gdf.geometry.simplify(0.0001)
                    self.precinct_data_cache[key] = gdf
                    print(f"Loaded {len(gdf)} precincts for {county_fips}")
                except Exception as e:
                    print(f"Error loading precincts for {county_fips}: {e}")
                    self.precinct_data_cache[key] = None
            else:
                self.precinct_data_cache[key] = None
        return self.precinct_data_cache[key]
    
    def tile_intersects_bounds(self, tile: mercantile.Tile, bounds: Tuple[float, float, float, float]) -> bool:
        """Check if a tile intersects with given bounds."""
        tile_bounds = mercantile.bounds(tile)
        return not (
            tile_bounds.east < bounds[0] or tile_bounds.west > bounds[2] or
            tile_bounds.north < bounds[1] or tile_bounds.south > bounds[3]
        )
    
    def get_features_for_tile(self, tile: mercantile.Tile, zoom: int) -> List[Dict]:
        """Get features that intersect with a specific tile."""
        tile_bounds = mercantile.bounds(tile)
        tile_bbox = (tile_bounds.west, tile_bounds.south, tile_bounds.east, tile_bounds.north)
        
        features = []
        
        if zoom <= 6:  # State level
            state_data = self.load_state_data()
            if state_data is not None and len(state_data) > 0:
                # Filter to features that intersect the tile
                intersecting = state_data.cx[tile_bounds.west:tile_bounds.east, tile_bounds.south:tile_bounds.north]
                for _, row in intersecting.iterrows():
                    # Simplify geometry for the zoom level
                    geom = row.geometry
                    if zoom < 4:
                        geom = geom.simplify(0.01)  # Heavy simplification for low zoom
                    elif zoom < 6:
                        geom = geom.simplify(0.001)
                    
                    features.append({
                        'geometry': mapping(geom),
                        'properties': {
                            'level': 'state',
                            'state_fips': row.get('state_fips', ''),
                            'state_name': row.get('state_name', ''),
                            'pct_dem_lead': float(row.get('pct_dem_lead', 0)) if pd.notna(row.get('pct_dem_lead', 0)) else 0.0,
                            'votes_dem': int(row.get('votes_dem', 0)) if pd.notna(row.get('votes_dem', 0)) else 0,
                            'votes_rep': int(row.get('votes_rep', 0)) if pd.notna(row.get('votes_rep', 0)) else 0,
                            'votes_total': int(row.get('votes_total', 0)) if pd.notna(row.get('votes_total', 0)) else 0
                        }
                    })
        
        elif zoom <= 10:  # County level
            state_data = self.load_state_data()
            if state_data is not None:
                # Find states that intersect this tile
                intersecting_states = state_data.cx[tile_bounds.west:tile_bounds.east, tile_bounds.south:tile_bounds.north]
                for _, state_row in intersecting_states.iterrows():
                    state_fips = state_row.get('state_fips', '')
                    county_data = self.load_county_data(state_fips)
                    if county_data is not None:
                        intersecting_counties = county_data.cx[tile_bounds.west:tile_bounds.east, tile_bounds.south:tile_bounds.north]
                        for _, county_row in intersecting_counties.iterrows():
                            geom = county_row.geometry
                            if zoom < 8:
                                geom = geom.simplify(0.001)
                            elif zoom < 10:
                                geom = geom.simplify(0.0005)
                            
                            features.append({
                                'geometry': mapping(geom),
                                'properties': {
                                    'level': 'county',
                                    'state_fips': state_fips,
                                    'county_fips': county_row.get('county_fips', ''),
                                    'county_name': county_row.get('county_name', ''),
                                    'state_name': county_row.get('state_name', ''),
                                    'pct_dem_lead': float(county_row.get('pct_dem_lead', 0)) if pd.notna(county_row.get('pct_dem_lead', 0)) else 0.0,
                                    'votes_dem': int(county_row.get('votes_dem', 0)) if pd.notna(county_row.get('votes_dem', 0)) else 0,
                                    'votes_rep': int(county_row.get('votes_rep', 0)) if pd.notna(county_row.get('votes_rep', 0)) else 0,
                                    'votes_total': int(county_row.get('votes_total', 0)) if pd.notna(county_row.get('votes_total', 0)) else 0
                                }
                            })
        
        else:  # Precinct level (zoom 11+)
            state_data = self.load_state_data()
            if state_data is not None:
                intersecting_states = state_data.cx[tile_bounds.west:tile_bounds.east, tile_bounds.south:tile_bounds.north]
                for _, state_row in intersecting_states.iterrows():
                    state_fips = state_row.get('state_fips', '')
                    county_data = self.load_county_data(state_fips)
                    if county_data is not None:
                        intersecting_counties = county_data.cx[tile_bounds.west:tile_bounds.east, tile_bounds.south:tile_bounds.north]
                        for _, county_row in intersecting_counties.iterrows():
                            county_fips = county_row.get('county_fips', '')
                            precinct_data = self.load_precinct_data(state_fips, county_fips)
                            if precinct_data is not None:
                                intersecting_precincts = precinct_data.cx[tile_bounds.west:tile_bounds.east, tile_bounds.south:tile_bounds.north]
                                for _, precinct_row in intersecting_precincts.iterrows():
                                    geom = precinct_row.geometry
                                    if zoom < 13:
                                        geom = geom.simplify(0.0001)
                                    
                                    features.append({
                                        'geometry': mapping(geom),
                                        'properties': {
                                            'level': 'precinct',
                                            'state_fips': state_fips,
                                            'county_fips': county_fips,
                                            'precinct_id': precinct_row.get('GEOID', ''),
                                            'county_name': precinct_row.get('county_name', ''),
                                            'state_name': precinct_row.get('state_name', ''),
                                            'pct_dem_lead': float(precinct_row.get('pct_dem_lead', 0)) if pd.notna(precinct_row.get('pct_dem_lead', 0)) else 0.0,
                                            'votes_dem': int(precinct_row.get('votes_dem', 0)) if pd.notna(precinct_row.get('votes_dem', 0)) else 0,
                                            'votes_rep': int(precinct_row.get('votes_rep', 0)) if pd.notna(precinct_row.get('votes_rep', 0)) else 0,
                                            'votes_total': int(precinct_row.get('votes_total', 0)) if pd.notna(precinct_row.get('votes_total', 0)) else 0
                                        }
                                    })
        
        return features
    
    def generate_tile(self, tile: mercantile.Tile) -> Optional[bytes]:
        """Generate a single vector tile."""
        features = self.get_features_for_tile(tile, tile.z)
        
        if not features:
            return None
        
        # Create layer data in the format expected by mapbox_vector_tile
        layer_data = {
            'name': 'election_data',
            'features': features
        }
        
        # Generate MVT tile
        try:
            tile_data = mapbox_vector_tile.encode(layer_data)
            return tile_data
        except Exception as e:
            print(f"Error generating tile {tile.z}/{tile.x}/{tile.y}: {e}")
            print(f"  Sample feature: {features[0] if features else 'No features'}")
            return None
    
    def generate_tiles_for_zoom(self, zoom: int):
        """Generate all tiles for a specific zoom level."""
        print(f"Generating tiles for zoom level {zoom}...")
        
        # Get overall bounds from state data
        state_data = self.load_state_data()
        if state_data is None or len(state_data) == 0:
            print("No state data available")
            return
        
        bounds = state_data.total_bounds
        
        # Get all tiles for this zoom level that intersect our bounds
        tiles = list(mercantile.tiles(bounds[0], bounds[1], bounds[2], bounds[3], [zoom]))
        
        tile_count = 0
        for tile in tiles:
            tile_data = self.generate_tile(tile)
            if tile_data:
                # Store tile in database
                self.conn.execute(
                    "INSERT OR REPLACE INTO tiles (zoom_level, tile_column, tile_row, tile_data) VALUES (?, ?, ?, ?)",
                    (tile.z, tile.x, tile.y, tile_data)
                )
                tile_count += 1
                
                if tile_count % 100 == 0:
                    print(f"  Generated {tile_count} tiles...")
                    self.conn.commit()
        
        self.conn.commit()
        print(f"Completed zoom level {zoom}: {tile_count} tiles generated")
    
    def generate_all_tiles(self):
        """Generate tiles for all zoom levels."""
        print(f"Starting tile generation from zoom {self.min_zoom} to {self.max_zoom}")
        
        for zoom in range(self.min_zoom, self.max_zoom + 1):
            self.generate_tiles_for_zoom(zoom)
            
            # Clear caches periodically to manage memory
            if zoom % 3 == 0:
                self.county_data_cache.clear()
                self.precinct_data_cache.clear()
                print(f"Cleared data caches after zoom {zoom}")
        
        print(f"Tile generation complete. Database saved to: {self.db_path}")
        self.conn.close()

def main():
    """Main execution function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate vector tiles from election data')
    parser.add_argument('--data-dir', default='data', help='Directory containing election data')
    parser.add_argument('--output-dir', default='tiles', help='Directory to store generated tiles')
    parser.add_argument('--max-zoom', type=int, default=14, help='Maximum zoom level')
    
    args = parser.parse_args()
    
    generator = VectorTileGenerator(args.data_dir, args.output_dir)
    generator.max_zoom = args.max_zoom
    generator.generate_all_tiles()

if __name__ == "__main__":
    main()