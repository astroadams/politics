#!/usr/bin/env python3
"""
Panel + GeoViews implementation of hierarchical election visualization.
Automatically adjusts data granularity based on zoom level with native support.
"""

import panel as pn
import geoviews as gv
import holoviews as hv
import geopandas as gpd
import pandas as pd
import param
import os
from pathlib import Path
from bokeh.models import HoverTool
from holoviews.streams import RangeXY, Tap

# Initialize Panel
pn.extension('bokeh', 'tabulator')
gv.extension('bokeh')

# Set default renderer and backend
hv.renderer('bokeh')

class HierarchicalElectionMap(param.Parameterized):
    """Interactive hierarchical election map with zoom-based data switching."""
    
    # Reactive parameters
    zoom_level = param.String(default='state', doc="Current zoom level")
    selected_states = param.List(default=[], doc="Selected states for county detail")
    current_bounds = param.Dict(default={}, doc="Current map bounds")
    
    def __init__(self, **params):
        super().__init__(**params)
        self.data_cache = {}
        self.load_initial_data()
    
    def load_cached_data(self, file_path):
        """Load and cache GeoJSON data with consistent CRS."""
        if file_path not in self.data_cache:
            if os.path.exists(file_path):
                try:
                    gdf = gpd.read_file(file_path)
                    
                    # Ensure consistent CRS (WGS84)
                    if gdf.crs is not None and gdf.crs != 'EPSG:4326':
                        gdf = gdf.to_crs('EPSG:4326')
                    elif gdf.crs is None:
                        gdf = gdf.set_crs('EPSG:4326')
                    
                    self.data_cache[file_path] = gdf
                    print(f"Loaded: {file_path}")
                except Exception as e:
                    print(f"Error loading {file_path}: {e}")
                    self.data_cache[file_path] = None
                    return None
            else:
                print(f"File not found: {file_path}")
                return None
        return self.data_cache[file_path]
    
    def load_initial_data(self):
        """Pre-load state boundaries for faster initial display."""
        self.state_boundaries = self.load_cached_data('data/states/state_boundaries.geojson')
        print(f"Loaded {len(self.state_boundaries) if self.state_boundaries is not None else 0} state boundaries")
    
    def determine_zoom_level(self, x_range, y_range):
        """Determine appropriate data granularity from viewport bounds."""
        if not x_range or not y_range:
            return 'state'
        
        # Calculate the span of the current view
        x_span = abs(x_range[1] - x_range[0])
        y_span = abs(y_range[1] - y_range[0])
        
        # Use the larger span to determine zoom level
        max_span = max(x_span, y_span)
        
        # Define thresholds based on geographic span
        # Rough conversion: 1 degree ≈ 69 miles at latitude 40°N
        if max_span > 30:  # Continental/multi-state view
            return 'state'
        elif max_span > 2:  # State/regional view
            return 'county'
        elif max_span > 0.3:  # ~20 miles or closer - show precincts
            return 'precinct'
        else:  # Very close zoom - show precincts with extra detail
            return 'precinct'
    
    def load_data_for_level(self, zoom_level, bounds=None):
        """Load appropriate data based on zoom level and bounds."""
        print(f"Loading data for zoom level: {zoom_level}")
        
        if zoom_level == 'state':
            return self.state_boundaries
        
        elif zoom_level == 'county':
            # Mixed granularity: counties for selected states, states for others
            if not self.selected_states:
                return self.state_boundaries
            
            combined_data = []
            
            # Add unselected states
            if self.state_boundaries is not None:
                unselected = self.state_boundaries[
                    ~self.state_boundaries['state_fips'].isin(self.selected_states)
                ].copy()
                if len(unselected) > 0:
                    unselected['granularity'] = 'state'
                    combined_data.append(unselected)
            
            # Add counties for selected states
            for state_fips in self.selected_states:
                county_file = f'data/states/by_state/{state_fips}/counties_{state_fips}.geojson'
                counties_gdf = self.load_cached_data(county_file)
                if counties_gdf is not None:
                    counties_gdf = counties_gdf.copy()
                    counties_gdf['granularity'] = 'county'
                    combined_data.append(counties_gdf)
            
            if combined_data:
                return gpd.GeoDataFrame(pd.concat(combined_data, ignore_index=True), crs='EPSG:4326')
            else:
                return self.state_boundaries
        
        elif zoom_level == 'precinct':
            # Load precincts based on current viewport and selected states
            combined_data = []
            
            # If we have bounds, determine which states/counties are in view
            if bounds and 'x_range' in bounds and 'y_range' in bounds:
                x_range = bounds['x_range']
                y_range = bounds['y_range']
                
                # Get states that intersect with current bounds
                states_in_view = []
                if self.state_boundaries is not None:
                    for idx, state_row in self.state_boundaries.iterrows():
                        geom = state_row.geometry
                        # Check if state geometry intersects with bounding box
                        if (geom.bounds[0] <= x_range[1] and geom.bounds[2] >= x_range[0] and
                            geom.bounds[1] <= y_range[1] and geom.bounds[3] >= y_range[0]):
                            states_in_view.append(state_row['state_fips'])
                
                # Load precincts for states in view (limit to first 2 states to avoid overload)
                for state_fips in states_in_view[:2]:
                    precincts_dir = Path(f'data/states/by_state/{state_fips}/precincts')
                    if precincts_dir.exists():
                        # Load first few precinct files for this state to avoid overload
                        precinct_files = list(precincts_dir.glob('*_precincts.geojson'))[:3]
                        for precinct_file in precinct_files:
                            precincts_gdf = self.load_cached_data(str(precinct_file))
                            if precincts_gdf is not None and len(precincts_gdf) > 0:
                                # Filter precincts to only those in viewport
                                filtered_precincts = []
                                for idx, precinct_row in precincts_gdf.iterrows():
                                    geom = precinct_row.geometry
                                    if (geom.bounds[0] <= x_range[1] and geom.bounds[2] >= x_range[0] and
                                        geom.bounds[1] <= y_range[1] and geom.bounds[3] >= y_range[0]):
                                        filtered_precincts.append(precinct_row)
                                
                                if filtered_precincts:
                                    filtered_gdf = gpd.GeoDataFrame(filtered_precincts, crs='EPSG:4326')
                                    filtered_gdf['granularity'] = 'precinct'
                                    combined_data.append(filtered_gdf)
                
                if combined_data:
                    result = gpd.GeoDataFrame(pd.concat(combined_data, ignore_index=True), crs='EPSG:4326')
                    print(f"Loaded {len(result)} precincts for current viewport")
                    return result
            
            # Fallback: load precincts for selected states if no bounds
            elif self.selected_states:
                for state_fips in self.selected_states[:1]:  # Limit to first selected state
                    precincts_dir = Path(f'data/states/by_state/{state_fips}/precincts')
                    if precincts_dir.exists():
                        precinct_files = list(precincts_dir.glob('*_precincts.geojson'))[:2]
                        for precinct_file in precinct_files:
                            precincts_gdf = self.load_cached_data(str(precinct_file))
                            if precincts_gdf is not None:
                                precincts_gdf = precincts_gdf.copy()
                                precincts_gdf['granularity'] = 'precinct'
                                combined_data.append(precincts_gdf)
                
                if combined_data:
                    result = gpd.GeoDataFrame(pd.concat(combined_data, ignore_index=True), crs='EPSG:4326')
                    print(f"Loaded {len(result)} precincts for selected states")
                    return result
            
            # Final fallback to county level
            print("No precinct data available - showing county level")
            return self.load_data_for_level('county', bounds)
        
        return self.state_boundaries
    
    def create_map_element(self, data, zoom_level):
        """Create GeoViews map element from data."""
        if data is None or len(data) == 0:
            # Create an empty but valid polygons element
            empty_polygons = gv.Polygons([]).opts(
                width=900, height=600, 
                title=f"No {zoom_level} data available for this area - try zooming out or selecting a state first",
                tools=['hover', 'wheel_zoom', 'pan', 'reset']
            )
            return empty_polygons
        
        # Prepare data for visualization
        data = data.reset_index(drop=True)
        
        # Determine color column and create hover tooltip
        if 'pct_dem_lead' in data.columns:
            color_col = 'pct_dem_lead'
            tooltips = [
                ('State', '@state_name' if 'state_name' in data.columns else '@state_fips'),
                ('Dem Lead', '@pct_dem_lead{0.1f}%'),
                ('Dem Votes', '@votes_dem{0,0}'),
                ('Rep Votes', '@votes_rep{0,0}')
            ]
            if 'county_name' in data.columns:
                tooltips.insert(1, ('County', '@county_name'))
            if 'precinct_name' in data.columns:
                tooltips.insert(-3, ('Precinct', '@precinct_name'))
            elif 'GEOID' in data.columns:
                tooltips.insert(-3, ('Precinct ID', '@GEOID'))
            if 'granularity' in data.columns:
                tooltips.append(('Level', '@granularity'))
        else:
            color_col = 'state_fips'
            tooltips = [('State FIPS', '@state_fips')]
        
        # Create the polygons element with data
        polygons = gv.Polygons(data, vdims=[color_col] + [col for col in data.columns if col != 'geometry'])
        
        # Style the map with proper aspect ratio
        if color_col == 'pct_dem_lead':
            opts = dict(
                color=color_col,
                cmap='RdBu',
                symmetric=True,
                colorbar=True,
                colorbar_opts={'title': 'Dem Lead %'},
                line_color='white',
                line_width=0.5,
                tools=['hover', 'tap', 'wheel_zoom', 'pan', 'reset'],
                width=900,
                height=600,
                aspect='equal',
                title=f"Election Results - {zoom_level.title()} Level"
            )
        else:
            opts = dict(
                color=color_col,
                cmap='Category20',
                colorbar=True,
                line_color='white',
                line_width=0.5,
                tools=['hover', 'tap', 'wheel_zoom', 'pan', 'reset'],
                width=900,
                height=600,
                aspect='equal',
                title=f"Geographic View - {zoom_level.title()} Level"
            )
        
        # Add hover tool
        hover = HoverTool(tooltips=tooltips)
        opts['tools'] = ['hover', 'tap', 'wheel_zoom', 'pan', 'reset']
        
        return polygons.opts(**opts)
    
    @param.depends('zoom_level', 'selected_states', 'current_bounds', watch=True)
    def update_map(self, x_range=None, y_range=None, x=None, y=None, **kwargs):
        """Update map when parameters change."""
        try:
            # Handle range changes from streams
            if x_range is not None and y_range is not None:
                self.handle_range(x_range, y_range)
            
            # Handle tap events from streams
            if x is not None and y is not None:
                self.handle_tap(x, y)
            
            data = self.load_data_for_level(self.zoom_level, self.current_bounds)
            result = self.create_map_element(data, self.zoom_level)
            
            # Ensure we never return None
            if result is None:
                return gv.Polygons([]).opts(
                    width=900, height=600, 
                    title="Map data temporarily unavailable",
                    tools=['hover', 'wheel_zoom', 'pan', 'reset']
                )
            return result
        except Exception as e:
            print(f"Error in update_map: {e}")
            return gv.Polygons([]).opts(
                width=900, height=600, 
                title="Error loading map data - please try again",
                tools=['hover', 'wheel_zoom', 'pan', 'reset']
            )
    
    def handle_tap(self, x, y):
        """Handle tap events on the map for state selection."""
        if self.state_boundaries is None:
            return
        
        # Find which state was clicked
        from shapely.geometry import Point
        point = Point(x, y)
        
        current_data = self.load_data_for_level(self.zoom_level)
        if current_data is not None:
            for idx, row in current_data.iterrows():
                if row.geometry.contains(point):
                    state_fips = row.get('state_fips')
                    if state_fips:
                        # Toggle state selection
                        if state_fips in self.selected_states:
                            new_selected = [s for s in self.selected_states if s != state_fips]
                        else:
                            new_selected = self.selected_states + [state_fips]
                        
                        self.selected_states = new_selected
                        
                        # Switch to county level if state was added
                        if state_fips in self.selected_states:
                            self.zoom_level = 'county'
                        
                        print(f"State {state_fips} {'selected' if state_fips in self.selected_states else 'deselected'}")
                        break
    
    def handle_range(self, x_range, y_range):
        """Handle viewport changes to update zoom level."""
        new_zoom_level = self.determine_zoom_level(x_range, y_range)
        if new_zoom_level != self.zoom_level:
            self.zoom_level = new_zoom_level
            print(f"Zoom level changed to: {new_zoom_level}")
        
        self.current_bounds = {'x_range': x_range, 'y_range': y_range}
    
    def create_info_panel(self):
        """Create information panel showing current state."""
        info_html = f"""
        <div style="padding: 15px; background-color: #f0f8ff; border-radius: 5px; margin-bottom: 10px;">
            <h4>🗺️ Zoom-Based Election Visualization</h4>
            <p><strong>Current Level:</strong> {self.zoom_level.title()}</p>
            <p><strong>Selected States:</strong> {len(self.selected_states)} states showing county detail</p>
            <hr>
            <p>💡 <strong>Instructions:</strong></p>
            <ul>
                <li>🔍 Zoom in/out to automatically switch between state/county/precinct levels</li>
                <li>🖱️ Click on states to show their county-level data</li>
                <li>🎯 Selected states show counties while others show state-level data</li>
                <li>🔬 Zoom in close (< 50 miles) to see precinct-level results</li>
                <li>📊 Color shows Democratic lead percentage (blue = Dem, red = Rep)</li>
            </ul>
            <p><strong>Zoom Level Guidelines:</strong></p>
            <ul>
                <li>🌎 Continental view: State-level data</li>
                <li>🗺️ Regional view: County-level data</li>
                <li>🔍 Close zoom (&lt; 20 miles): Precinct-level data (where available)</li>
            </ul>
            <p><em>Note: Precinct data is available for select states/counties. If no precinct data exists for your zoom area, county-level data will be shown instead.</em></p>
        </div>
        """
        return pn.pane.HTML(info_html, width=400)
    
    def create_dashboard(self):
        """Create the complete dashboard."""
        # Create streams for interactivity
        range_stream = RangeXY()
        tap_stream = Tap()
        
        # Create a dynamic map that updates with parameters and responds to streams
        dmap = hv.DynamicMap(self.update_map, streams=[range_stream, tap_stream])
        
        # Create info panel as a regular Panel HTML pane that updates with parameters
        info_panel = pn.pane.HTML(self.create_info_panel().object, width=400)
        
        # Function to update info panel when parameters change
        def update_info_panel(event):
            info_panel.object = self.create_info_panel().object
        
        # Watch for parameter changes to update info panel
        self.param.watch(update_info_panel, ['zoom_level', 'selected_states'])
        
        # Create the map plot with callbacks
        map_plot = pn.pane.HoloViews(dmap, width=900, height=700)
        
        # Layout
        dashboard = pn.Column(
            pn.pane.HTML("<h1 style='text-align: center;'>Panel + GeoViews Election Visualization</h1>"),
            pn.Row(
                info_panel,
                map_plot,
                sizing_mode='stretch_width'
            ),
            sizing_mode='stretch_width'
        )
        
        return dashboard

def main():
    """Main function to run the Panel application."""
    # Check if data exists
    if not os.path.exists('data/states/state_boundaries.geojson'):
        print("Hierarchical data not found. Please run split_precinct_data.py first.")
        return
    
    # Create the application
    app = HierarchicalElectionMap()
    dashboard = app.create_dashboard()
    
    # Serve the application
    print("Starting Panel + GeoViews election visualization...")
    print("🔍 Zoom in/out to automatically switch data granularity")
    print("🖱️ Click on states to show county-level detail")
    print("Open the URL that appears below in your browser")
    
    return dashboard.servable()

if __name__ == "__main__":
    # For development, serve directly
    app = HierarchicalElectionMap()
    dashboard = app.create_dashboard()
    dashboard.show(port=5008)