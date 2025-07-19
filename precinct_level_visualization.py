#!/usr/bin/env python3
"""
Zoom-based hierarchical visualization with click-to-drill-down functionality.
Automatically adjusts data granularity based on zoom level and user interactions.
"""

import dash
from dash import dcc, html, callback_context
from dash.dependencies import Input, Output, State
import plotly.express as px
import plotly.graph_objects as go
import geopandas as gpd
import pandas as pd
import os
import json
from pathlib import Path

app = dash.Dash(__name__)

# Data cache to avoid reloading
data_cache = {}

# Track selected states for mixed granularity view
selected_states = set()

def load_cached_data(file_path):
    """Load and cache GeoJSON data, ensuring consistent CRS."""
    if file_path not in data_cache:
        if os.path.exists(file_path):
            try:
                gdf = gpd.read_file(file_path)
                
                # Ensure all data is in WGS84 (EPSG:4326) for consistency
                if gdf.crs is not None and gdf.crs != 'EPSG:4326':
                    print(f"Converting {file_path} from {gdf.crs} to EPSG:4326")
                    gdf = gdf.to_crs('EPSG:4326')
                elif gdf.crs is None:
                    print(f"Setting CRS for {file_path} to EPSG:4326")
                    gdf = gdf.set_crs('EPSG:4326')
                
                data_cache[file_path] = gdf
                print(f"Loaded: {file_path}")
            except Exception as e:
                print(f"Error loading {file_path}: {e}")
                data_cache[file_path] = None
                return None
        else:
            print(f"File not found: {file_path}")
            return None
    return data_cache[file_path]

def get_zoom_level_from_relayout(relayout_data):
    """Determine appropriate data granularity from map zoom level."""
    if not relayout_data:
        return 'state'
    
    # Extract zoom level from relayout data
    zoom = None
    if 'mapbox.zoom' in relayout_data:
        zoom = relayout_data['mapbox.zoom']
    elif 'geo.projection.scale' in relayout_data:
        # Use projection scale directly (ranges from ~1 to 20+)
        zoom = relayout_data['geo.projection.scale']
    
    if zoom is None:
        return 'state'
    
    # Define zoom thresholds for different granularities
    # Higher scales = more zoomed in (projection.scale ranges from ~1 to 20+)
    if zoom < 3:
        return 'state'      # Continental US view (scale 1-3)
    elif zoom < 12:
        return 'county'     # State/regional view (scale 3-12)
    else:
        return 'precinct'   # Local view (~50 miles or closer, scale 12+)

def get_viewport_bounds(relayout_data):
    """Extract viewport bounds from relayout data."""
    if not relayout_data:
        return None
    
    bounds = {}
    if 'mapbox.center' in relayout_data and 'mapbox.zoom' in relayout_data:
        # Mapbox bounds
        center = relayout_data['mapbox.center']
        zoom = relayout_data['mapbox.zoom']
        bounds = {
            'center_lat': center.get('lat', 39.5),
            'center_lon': center.get('lon', -98.5),
            'zoom': zoom
        }
    elif 'geo.center' in relayout_data:
        # Geo projection bounds
        center = relayout_data['geo.center']
        bounds = {
            'center_lat': center.get('lat', 39.5),
            'center_lon': center.get('lon', -98.5),
            'zoom': 4
        }
    
    return bounds

def load_data_for_zoom_and_viewport(zoom_level, viewport_bounds=None, clicked_states=None, recent_state=None):
    """Load appropriate data based on zoom level and viewport."""
    print(f"Loading data for zoom level: {zoom_level}")
    
    if clicked_states is None:
        clicked_states = set()
    
    if zoom_level == 'state':
        # Load state boundaries
        return load_cached_data('data/states/state_boundaries.geojson')
    
    elif zoom_level == 'county':
        # Mixed granularity: counties for selected states, states for others
        if not clicked_states:
            # No states selected, show all states
            return load_cached_data('data/states/state_boundaries.geojson')
        
        # Combine state and county data
        combined_data = []
        
        # Load state boundaries first
        states_gdf = load_cached_data('data/states/state_boundaries.geojson')
        if states_gdf is not None:
            # Ensure state data is in WGS84
            if states_gdf.crs != 'EPSG:4326':
                states_gdf = states_gdf.to_crs('EPSG:4326')
            
            # Add states that are NOT selected (show as state-level)
            unselected_states = states_gdf[~states_gdf['state_fips'].isin(clicked_states)]
            if len(unselected_states) > 0:
                unselected_states = unselected_states.copy()
                unselected_states['granularity'] = 'state'
                combined_data.append(unselected_states)
        
        # Load counties for selected states
        for state_fips in clicked_states:
            county_file = f'data/states/by_state/{state_fips}/counties_{state_fips}.geojson'
            counties_gdf = load_cached_data(county_file)
            if counties_gdf is not None:
                # Ensure county data is in WGS84
                if counties_gdf.crs != 'EPSG:4326':
                    counties_gdf = counties_gdf.to_crs('EPSG:4326')
                
                counties_gdf = counties_gdf.copy()
                counties_gdf['granularity'] = 'county'
                combined_data.append(counties_gdf)
        
        if combined_data:
            return gpd.GeoDataFrame(pd.concat(combined_data, ignore_index=True), crs='EPSG:4326')
        else:
            return load_cached_data('data/states/state_boundaries.geojson')
    
    elif zoom_level == 'precinct':
        # Load precincts for the most recently clicked state
        if recent_state:
            print(f"Loading precincts for state {recent_state}")
            precincts_dir = Path(f'data/states/by_state/{recent_state}/precincts')
            if precincts_dir.exists():
                precinct_files = list(precincts_dir.glob('*_precincts.geojson'))
                if precinct_files:
                    # Load first available precinct file for the state
                    return load_cached_data(str(precinct_files[0]))
        
        # Fallback: try to load any available precinct file
        states_dir = Path('data/states/by_state')
        for state_dir in states_dir.iterdir():
            if state_dir.is_dir():
                precincts_dir = state_dir / 'precincts'
                if precincts_dir.exists():
                    precinct_files = list(precincts_dir.glob('*_precincts.geojson'))
                    if precinct_files:
                        return load_cached_data(str(precinct_files[0]))
        
        # Final fallback to county data
        return load_data_for_zoom_and_viewport('county', viewport_bounds, clicked_states, recent_state)
    
    return load_cached_data('data/states/state_boundaries.geojson')

def create_figure(geojson_data, zoom_level='state', preserve_bounds=None):
    """Create choropleth figure based on data and zoom level."""
    if geojson_data is None or len(geojson_data) == 0:
        # Return empty figure
        fig = go.Figure()
        fig.update_layout(
            title="No data available",
            xaxis={'visible': False},
            yaxis={'visible': False}
        )
        return fig
    
    # Determine color column and hover data
    color_col = 'pct_dem_lead' if 'pct_dem_lead' in geojson_data.columns else 'state_fips'
    hover_data = []
    
    if 'pct_dem_lead' in geojson_data.columns:
        hover_data = ['votes_dem', 'votes_rep']
        
        # Add names to hover data if available
        if 'state_name' in geojson_data.columns:
            hover_data.append('state_name')
        if 'county_name' in geojson_data.columns:
            hover_data.append('county_name')
        if 'granularity' in geojson_data.columns:
            hover_data.append('granularity')
    
    # Reset index to ensure proper alignment
    geojson_data = geojson_data.reset_index(drop=True)
    
    # Ensure state_fips is in hover data for click detection
    if 'state_fips' in geojson_data.columns and 'state_fips' not in hover_data:
        hover_data.append('state_fips')
    
    # Create choropleth map
    fig = px.choropleth(
        geojson_data,
        geojson=geojson_data.geometry,
        locations=geojson_data.index,
        color=color_col,
        hover_data=hover_data,
        color_continuous_scale='RdBu' if color_col == 'pct_dem_lead' else 'Viridis',
        color_continuous_midpoint=0 if color_col == 'pct_dem_lead' else None,
        labels={
            'pct_dem_lead': 'Dem Lead %',
            'votes_dem': 'Dem Votes',
            'votes_rep': 'Rep Votes',
            'state_name': 'State',
            'county_name': 'County',
            'granularity': 'Level',
            'state_fips': 'State Code'
        },
        title=f"Election Results - Zoom Level: {zoom_level.title()}"
    )
    
    # Set initial bounds to continental US or use preserved bounds
    if preserve_bounds:
        fig.update_geos(
            visible=False,
            projection_type="mercator",
            **preserve_bounds
        )
    else:
        # Default to continental US bounds (excludes Alaska and Hawaii)
        fig.update_geos(
            visible=False,
            projection_type="mercator",
            lonaxis_range=[-130, -65],  # Continental US longitude range
            lataxis_range=[20, 50]      # Continental US latitude range
        )
    
    fig.update_layout(
        height=700,
        margin={"r":0,"t":50,"l":0,"b":0},
        title_x=0.5
    )
    
    return fig

# App layout
app.layout = html.Div([
    html.H1("Zoom-Based Election Visualization", 
            style={'textAlign': 'center', 'marginBottom': 20}),
    
    html.Div([
        html.P("🔍 Zoom in/out to see different levels of detail", style={'margin': 5}),
        html.P("🖱️ Click on states to see county-level data", style={'margin': 5}),
        html.P("📊 Mixed granularity: counties for selected states, states for others", style={'margin': 5})
    ], style={
        'textAlign': 'center', 
        'backgroundColor': '#f0f8ff', 
        'padding': 15, 
        'borderRadius': 5,
        'marginBottom': 20
    }),
    
    # Store for tracking zoom level and selected states
    dcc.Store(id='zoom-level-store', data='state'),
    dcc.Store(id='selected-states-store', data=[]),
    dcc.Store(id='most-recent-state-store', data=None),
    
    dcc.Graph(
        id='election-map',
        config={
            'scrollZoom': True,
            'doubleClick': 'autosize',
            'showTips': False,
            'displayModeBar': True,
            'displaylogo': False
        }
    ),
    
    html.Div([
        html.H4("Zoom Level Information:", style={'color': '#333'}),
        html.Div(id='zoom-info', style={'fontSize': 14}),
        html.H4("Selected States:", style={'color': '#333', 'marginTop': 20}),
        html.Div(id='selected-states-info', style={'fontSize': 14})
    ], style={
        'margin': 20, 
        'padding': 20, 
        'backgroundColor': '#f9f9f9', 
        'borderRadius': 5
    })
])

def calculate_state_bounds(state_fips):
    """Calculate bounding box for a single state with padding."""
    if not state_fips:
        return None
    
    try:
        # Load state boundaries to get geometries
        states_gdf = load_cached_data('data/states/state_boundaries.geojson')
        if states_gdf is None:
            return None
        
        # Filter to the single selected state
        selected_states_gdf = states_gdf[states_gdf['state_fips'] == state_fips]
        
        if len(selected_states_gdf) == 0:
            return None
        
        # Get the bounds of the selected states
        bounds = selected_states_gdf.total_bounds  # [minx, miny, maxx, maxy]
        
        # Add padding (about 10% on each side)
        padding_x = (bounds[2] - bounds[0]) * 0.1
        padding_y = (bounds[3] - bounds[1]) * 0.1
        
        return {
            'lonaxis': {
                'range': [bounds[0] - padding_x, bounds[2] + padding_x]
            },
            'lataxis': {
                'range': [bounds[1] - padding_y, bounds[3] + padding_y]
            }
        }
    except Exception as e:
        print(f"Error calculating state bounds: {e}")
        return None

@app.callback(
    [Output('election-map', 'figure'),
     Output('zoom-level-store', 'data'),
     Output('zoom-info', 'children')],
    [Input('selected-states-store', 'data'),
     Input('most-recent-state-store', 'data')],
    [State('zoom-level-store', 'data'),
     State('election-map', 'relayoutData')]
)
def update_map_on_state_selection(selected_states_list, most_recent_state, current_zoom_level, relayout_data):
    """Update map when states are selected/deselected."""
    
    # Determine zoom level from relayout data or use current
    natural_zoom_level = get_zoom_level_from_relayout(relayout_data) if relayout_data else (current_zoom_level or 'state')
    
    # Check if we should force county level due to state selection
    clicked_states = set(selected_states_list) if selected_states_list else set()
    ctx = callback_context
    should_zoom_to_state = False
    
    if ctx.triggered:
        for trigger in ctx.triggered:
            trigger_id = trigger['prop_id']
            if trigger_id == 'most-recent-state-store.data' and most_recent_state:
                should_zoom_to_state = True
                break
    
    # Determine final zoom level with precedence rules
    if natural_zoom_level == 'precinct' and most_recent_state:
        # High zoom + recent state = show precincts for that state
        zoom_level = 'precinct'
    elif should_zoom_to_state and most_recent_state:
        # Fresh state click = force county level
        zoom_level = 'county'
    elif clicked_states and natural_zoom_level == 'state':
        # States selected but low zoom = force county level
        zoom_level = 'county'
    else:
        # Use natural zoom level (state/county/precinct based on scale)
        zoom_level = natural_zoom_level
    
    # Load appropriate data
    data = load_data_for_zoom_and_viewport(zoom_level, relayout_data, clicked_states, most_recent_state)
    
    # Determine bounds for the figure
    preserve_bounds = None
    
    if should_zoom_to_state and most_recent_state:
        # Calculate bounds for the most recent state and zoom to it
        preserve_bounds = calculate_state_bounds(most_recent_state)
    elif relayout_data:
        # Preserve the current view from relayout data
        preserve_bounds = {}
        if 'geo.center.lat' in relayout_data and 'geo.center.lon' in relayout_data:
            preserve_bounds['center'] = dict(
                lat=relayout_data['geo.center.lat'],
                lon=relayout_data['geo.center.lon']
            )
        if 'geo.projection.scale' in relayout_data:
            preserve_bounds['projection_scale'] = relayout_data['geo.projection.scale']
        if 'geo.lonaxis.range' in relayout_data:
            preserve_bounds['lonaxis_range'] = relayout_data['geo.lonaxis.range']
        if 'geo.lataxis.range' in relayout_data:
            preserve_bounds['lataxis_range'] = relayout_data['geo.lataxis.range']
    
    # Create figure with preserved bounds
    fig = create_figure(data, zoom_level, preserve_bounds)
    
    # Create zoom info
    zoom_info = [
        html.P(f"Current Level: {zoom_level.title()}", style={'fontWeight': 'bold'}),
        html.P(f"Data Points: {len(data) if data is not None else 0}"),
        html.P("Click on states to zoom and show detail" if not most_recent_state else f"Focus: {most_recent_state} | Level: {zoom_level}")
    ]
    
    return fig, zoom_level, zoom_info

@app.callback(
    [Output('selected-states-store', 'data'),
     Output('most-recent-state-store', 'data'),
     Output('selected-states-info', 'children')],
    [Input('election-map', 'clickData')],
    [State('selected-states-store', 'data'),
     State('zoom-level-store', 'data')]
)
def handle_state_clicks(click_data, selected_states_list, zoom_level):
    """Handle clicks on states to toggle county view."""
    
    print(f"Click data received: {click_data}")  # Debug print
    
    if not click_data:
        selected_states_info = html.P("Click on states to show their counties")
        return selected_states_list or [], None, selected_states_info
    
    # Extract clicked location info
    point_data = click_data['points'][0]
    print(f"Point data: {point_data}")  # Debug print
    
    # Try to extract state FIPS directly from hover data if available
    state_fips = None
    most_recent_state = None
    
    # Check if state_fips is in the hover data (more reliable)
    if 'customdata' in point_data and point_data['customdata']:
        # customdata contains the hover_data values
        customdata = point_data['customdata']
        print(f"Custom data: {customdata}")  # Debug
        
        # Get current data to understand the hover_data structure
        clicked_states = set(selected_states_list) if selected_states_list else set()
        current_data = load_data_for_zoom_and_viewport(zoom_level, None, clicked_states)
        
        if current_data is not None:
            # Determine which column contains state_fips in hover_data
            hover_columns = ['votes_dem', 'votes_rep']
            if 'state_name' in current_data.columns:
                hover_columns.append('state_name')
            if 'county_name' in current_data.columns:
                hover_columns.append('county_name')
            if 'granularity' in current_data.columns:
                hover_columns.append('granularity')
            hover_columns.append('state_fips')  # This should be last
            
            # Extract state_fips from customdata (it should be the last element)
            if len(customdata) >= len(hover_columns):
                state_fips_idx = hover_columns.index('state_fips')
                if state_fips_idx < len(customdata):
                    state_fips = str(customdata[state_fips_idx])
                    print(f"Extracted state FIPS from hover data: {state_fips}")
    
    # Fallback to location index method if hover data doesn't work
    if not state_fips:
        print("Falling back to location index method...")
        clicked_states = set(selected_states_list) if selected_states_list else set()
        current_data = load_data_for_zoom_and_viewport(zoom_level, None, clicked_states)
        
        if current_data is not None:
            # Get the location index from the click
            location_idx = point_data.get('location', 0)
            print(f"Location index: {location_idx}, Total features: {len(current_data)}")  # Debug
            
            if location_idx < len(current_data):
                clicked_feature = current_data.iloc[location_idx]
                
                # Try to get state FIPS from the clicked feature
                if 'state_fips' in clicked_feature:
                    state_fips = clicked_feature['state_fips']
                elif 'county_fips' in clicked_feature:
                    # If it's a county, extract state FIPS from county FIPS
                    county_fips = str(clicked_feature['county_fips'])
                    if len(county_fips) >= 5:
                        state_fips = county_fips[:2]
                        
                print(f"Fallback identified state FIPS: {state_fips}")  # Debug
    
    # Set the most recent state
    if state_fips:
        most_recent_state = state_fips
    
    if state_fips:
        selected_states_set = set(selected_states_list) if selected_states_list else set()
        
        # Toggle state selection
        if state_fips in selected_states_set:
            selected_states_set.remove(state_fips)
            print(f"Removed state {state_fips} from selection")
            # If we removed the current state, clear most recent
            if state_fips == most_recent_state:
                most_recent_state = list(selected_states_set)[0] if selected_states_set else None
        else:
            selected_states_set.add(state_fips)
            print(f"Added state {state_fips} to selection")
            # Set as most recent state
            most_recent_state = state_fips
        
        selected_states_list = list(selected_states_set)
        
        # Create info display
        if selected_states_list:
            try:
                states_gdf = load_cached_data('data/states/state_boundaries.geojson')
                state_names = []
                for fips in selected_states_list:
                    state_row = states_gdf[states_gdf['state_fips'] == fips]
                    if len(state_row) > 0 and 'state_name' in state_row.columns:
                        state_names.append(state_row.iloc[0]['state_name'])
                    else:
                        state_names.append(f"State {fips}")
                
                selected_states_info = [
                    html.P("States showing county detail:", style={'fontWeight': 'bold', 'color': 'green'}),
                    html.Ul([html.Li(name) for name in state_names])
                ]
            except Exception as e:
                print(f"Error creating state info: {e}")
                selected_states_info = [
                    html.P("Selected states:", style={'fontWeight': 'bold'}),
                    html.P(", ".join(selected_states_list))
                ]
        else:
            selected_states_info = html.P("Click on states to show their counties")
    else:
        selected_states_info = html.P("Click on states to show their counties (no state detected)")
        selected_states_list = selected_states_list or []
    
    return selected_states_list, most_recent_state, selected_states_info

if __name__ == '__main__':
    # Clear any cached data
    data_cache.clear()
    
    # Check if hierarchical data exists
    if not os.path.exists('data/states/state_boundaries.geojson'):
        print("Hierarchical data not found. Please run split_precinct_data.py first.")
        print("Usage: python split_precinct_data.py")
        exit(1)
    
    print("Starting zoom-based hierarchical visualization...")
    print("🔍 Zoom in/out to change data granularity")
    print("🖱️ Click on states to drill down to county level")
    print("Open http://127.0.0.1:8050 in your browser")
    app.run_server(debug=True)