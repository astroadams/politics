#!/usr/bin/env python3
"""
Simple tile server for serving MVT tiles from MBTiles database.
Provides endpoints for Mapbox GL JS consumption.
"""

import sqlite3
import os
from pathlib import Path
from flask import Flask, Response, jsonify, send_file
from flask_cors import CORS
import json

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

class TileServer:
    """Simple tile server for MVT tiles."""
    
    def __init__(self, mbtiles_path: str):
        self.mbtiles_path = Path(mbtiles_path)
        if not self.mbtiles_path.exists():
            raise FileNotFoundError(f"MBTiles file not found: {mbtiles_path}")
        
        # Test database connection
        self._get_metadata()
    
    def _get_connection(self):
        """Get database connection."""
        return sqlite3.connect(str(self.mbtiles_path))
    
    def _get_metadata(self):
        """Get tile metadata from MBTiles database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT name, value FROM metadata")
            metadata = dict(cursor.fetchall())
            conn.close()
            return metadata
        except sqlite3.Error as e:
            conn.close()
            print(f"Database error: {e}")
            return {}
    
    def get_tile(self, z: int, x: int, y: int) -> bytes:
        """Get a specific tile from the database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Note: MBTiles uses TMS tiling scheme, convert from XYZ
            tms_y = (2 ** z - 1) - y
            
            cursor.execute(
                "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                (z, x, tms_y)
            )
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return result[0]
            else:
                return None
        except sqlite3.Error as e:
            conn.close()
            print(f"Database error getting tile {z}/{x}/{y}: {e}")
            return None
    
    def get_tilejson(self, base_url: str) -> dict:
        """Generate TileJSON specification."""
        metadata = self._get_metadata()
        
        return {
            "tilejson": "3.0.0",
            "name": metadata.get("name", "Election Data Tiles"),
            "description": metadata.get("description", ""),
            "version": metadata.get("version", "1.0.0"),
            "scheme": "xyz",
            "tiles": [f"{base_url}/tiles/{{z}}/{{x}}/{{y}}.pbf"],
            "minzoom": int(metadata.get("minzoom", 0)),
            "maxzoom": int(metadata.get("maxzoom", 14)),
            "bounds": [float(x) for x in metadata.get("bounds", "-180,-85,180,85").split(",")],
            "center": [float(x) for x in metadata.get("center", "-98,39,4").split(",")],
            "format": "pbf",
            "vector_layers": [
                {
                    "id": "election_data",
                    "description": "Hierarchical election data by zoom level",
                    "fields": {
                        "level": "Level of data (state/county/precinct)",
                        "state_fips": "State FIPS code",
                        "state_name": "State name",
                        "county_fips": "County FIPS code (county/precinct levels)",
                        "county_name": "County name (county/precinct levels)",
                        "precinct_id": "Precinct ID (precinct level only)",
                        "pct_dem_lead": "Democratic lead percentage",
                        "votes_dem": "Democratic votes",
                        "votes_rep": "Republican votes",
                        "votes_total": "Total votes"
                    }
                }
            ]
        }

# Global tile server instance
tile_server = None

@app.route('/health')
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "tiles_available": tile_server is not None})

@app.route('/tilejson')
def get_tilejson():
    """Get TileJSON specification."""
    if not tile_server:
        return jsonify({"error": "Tile server not initialized"}), 500
    
    base_url = f"http://{app.config.get('HOST', 'localhost')}:{app.config.get('PORT', 5000)}"
    tilejson = tile_server.get_tilejson(base_url)
    return jsonify(tilejson)

@app.route('/tiles/<int:z>/<int:x>/<int:y>.pbf')
def get_tile(z: int, x: int, y: int):
    """Get a specific tile."""
    if not tile_server:
        return "Tile server not initialized", 500
    
    # Validate zoom level
    if z < 0 or z > 20:
        return "Invalid zoom level", 400
    
    tile_data = tile_server.get_tile(z, x, y)
    
    if tile_data is None:
        return "Tile not found", 404
    
    response = Response(
        tile_data,
        mimetype='application/x-protobuf',
        headers={
            'Content-Encoding': 'gzip' if len(tile_data) > 1000 else '',
            'Cache-Control': 'public, max-age=3600'  # Cache for 1 hour
        }
    )
    
    return response

@app.route('/')
def index():
    """Serve a simple test page."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Election Data Tile Server</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .endpoint { background: #f5f5f5; padding: 10px; margin: 10px 0; border-radius: 4px; }
        </style>
    </head>
    <body>
        <h1>Election Data Vector Tile Server</h1>
        <p>This server provides MVT tiles for election data visualization.</p>
        
        <h2>Available Endpoints:</h2>
        <div class="endpoint">
            <strong>GET /health</strong><br>
            Health check and server status
        </div>
        <div class="endpoint">
            <strong>GET /tilejson</strong><br>
            TileJSON specification for Mapbox GL JS
        </div>
        <div class="endpoint">
            <strong>GET /tiles/{z}/{x}/{y}.pbf</strong><br>
            Vector tile endpoint (MVT format)
        </div>
        
        <h2>Integration:</h2>
        <p>Use the TileJSON endpoint with Mapbox GL JS:</p>
        <pre>
map.addSource('election-data', {
    'type': 'vector',
    'url': '/tilejson'
});
        </pre>
    </body>
    </html>
    """

def create_app(mbtiles_path: str, host: str = 'localhost', port: int = 5001):
    """Create and configure the Flask app."""
    global tile_server
    
    # Initialize tile server
    try:
        tile_server = TileServer(mbtiles_path)
        print(f"Tile server initialized with database: {mbtiles_path}")
    except Exception as e:
        print(f"Failed to initialize tile server: {e}")
        return None
    
    # Configure app
    app.config['HOST'] = host
    app.config['PORT'] = port
    
    return app

def main():
    """Main execution function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Serve vector tiles from MBTiles database')
    parser.add_argument('--mbtiles', default='tiles/tiles.mbtiles', help='Path to MBTiles database')
    parser.add_argument('--host', default='localhost', help='Host to bind to')
    parser.add_argument('--port', type=int, default=5001, help='Port to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.mbtiles):
        print(f"Error: MBTiles file not found: {args.mbtiles}")
        print("Run generate_vector_tiles.py first to create the tile database.")
        return 1
    
    flask_app = create_app(args.mbtiles, args.host, args.port)
    if flask_app is None:
        return 1
    
    print(f"Starting tile server on http://{args.host}:{args.port}")
    print("Available endpoints:")
    print(f"  Health check: http://{args.host}:{args.port}/health")
    print(f"  TileJSON: http://{args.host}:{args.port}/tilejson")
    print(f"  Tiles: http://{args.host}:{args.port}/tiles/{{z}}/{{x}}/{{y}}.pbf")
    
    flask_app.run(host=args.host, port=args.port, debug=args.debug)

if __name__ == "__main__":
    exit(main())