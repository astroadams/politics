#!/usr/bin/env python3
"""
High-performance election data visualization app using vector tiles.
Serves both the web interface and static data files.
"""

import os
import json
from pathlib import Path
from flask import Flask, render_template, send_from_directory, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Configuration
DATA_DIR = Path("data")
TEMPLATES_DIR = Path("templates")

@app.route('/')
def index():
    """Serve the main election visualization interface."""
    return render_template('mapbox_election_viewer.html')

@app.route('/data/<path:filename>')
def serve_data(filename):
    """Serve data files (GeoJSON, etc.) for fallback scenarios."""
    try:
        return send_from_directory(DATA_DIR, filename)
    except FileNotFoundError:
        return jsonify({"error": "Data file not found"}), 404

@app.route('/api/status')
def api_status():
    """API endpoint to check data availability."""
    status = {
        "status": "healthy",
        "data_available": {
            "states": (DATA_DIR / "states" / "state_boundaries.geojson").exists(),
            "counties": len(list((DATA_DIR / "states" / "by_state").glob("*/counties_*.geojson"))),
            "precincts": len(list((DATA_DIR / "states" / "by_state").glob("*/precincts/*.geojson")))
        },
        "tiles_available": (Path("tiles") / "tiles.mbtiles").exists()
    }
    return jsonify(status)

@app.route('/api/states')
def api_states():
    """Get list of available states with basic info."""
    states_file = DATA_DIR / "states" / "state_boundaries.geojson"
    
    if not states_file.exists():
        return jsonify({"error": "State data not available"}), 404
    
    try:
        import geopandas as gpd
        gdf = gpd.read_file(states_file)
        
        states = []
        for _, row in gdf.iterrows():
            states.append({
                "fips": row.get("state_fips", ""),
                "name": row.get("state_name", ""),
                "bounds": list(row.geometry.bounds) if row.geometry else None,
                "dem_lead": row.get("pct_dem_lead", 0),
                "votes_total": int(row.get("votes_total", 0))
            })
        
        return jsonify({"states": states})
    except Exception as e:
        return jsonify({"error": f"Failed to load state data: {str(e)}"}), 500

@app.route('/health')
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "Election Data Visualization App"
    })

def main():
    """Main execution function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='High-performance election visualization app')
    parser.add_argument('--host', default='localhost', help='Host to bind to')
    parser.add_argument('--port', type=int, default=5000, help='Port to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    # Check if data exists
    if not DATA_DIR.exists():
        print(f"Warning: Data directory not found: {DATA_DIR}")
    
    # Check if templates exist
    if not TEMPLATES_DIR.exists():
        print(f"Warning: Templates directory not found: {TEMPLATES_DIR}")
    
    print(f"Starting election visualization app on http://{args.host}:{args.port}")
    print("Available endpoints:")
    print(f"  Main app: http://{args.host}:{args.port}/")
    print(f"  API status: http://{args.host}:{args.port}/api/status")
    print(f"  Health check: http://{args.host}:{args.port}/health")
    
    # Check tile server status
    tiles_available = (Path("tiles") / "tiles.mbtiles").exists()
    if tiles_available:
        print("✅ Vector tiles are available for high-performance rendering")
        print("  Start tile server: python tile_server.py")
    else:
        print("⚠️  Vector tiles not found. Run generate_vector_tiles.py first for best performance")
        print("  Generate tiles: python generate_vector_tiles.py")
    
    app.run(host=args.host, port=args.port, debug=args.debug)

if __name__ == "__main__":
    main()