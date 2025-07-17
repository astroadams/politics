#!/usr/bin/env python3
"""
Hierarchical precinct-level visualization with efficient data loading.
Loads state -> county -> precinct data based on zoom level.
"""

import dash
from dash import dcc, html, callback_context
from dash.dependencies import Input, Output, State
import plotly.express as px
import plotly.graph_objects as go
import geopandas as gpd
import pandas as pd
import os
from pathlib import Path

app = dash.Dash(__name__)

# Data cache to avoid reloading
data_cache = {}

def load_cached_data(file_path):
    """Load and cache GeoJSON data."""
    if file_path not in data_cache:
        if os.path.exists(file_path):
            try:
                data_cache[file_path] = gpd.read_file(file_path)
                print(f"Successfully loaded: {file_path}")
            except Exception as e:
                print(f"Error loading {file_path}: {e}")
                data_cache[file_path] = None
                return None
        else:
            print(f"File not found: {file_path}")
            return None
    return data_cache[file_path]

def get_state_boundaries():
    """Load national state boundaries."""
    data = load_cached_data('data/states/state_boundaries.geojson')
    if data is not None:
        print(f"DEBUG: Loaded state boundaries - {len(data)} features")
        print(f"DEBUG: Sample state data - State {data.iloc[0].get('state_fips')}: Dem={data.iloc[0].get('votes_dem')}, Rep={data.iloc[0].get('votes_rep')}")
    return data

def get_state_counties(state_fips):
    """Load counties for a specific state."""
    file_path = f'data/states/by_state/{state_fips}/counties_{state_fips}.geojson'
    return load_cached_data(file_path)

def get_county_precincts(state_fips, county_fips):
    """Load precincts for a specific county."""
    file_path = f'data/states/by_state/{state_fips}/precincts/{state_fips}{county_fips}_precincts.geojson'
    return load_cached_data(file_path)

def get_adjacent_states(target_state_fips):
    """Get state boundaries for visualization context."""
    states = get_state_boundaries()
    if states is not None:
        return states
    return None

def create_figure(geojson_data, zoom_level='national', center_lat=39.8, center_lon=-98.6, zoom=4):
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
    
    # Determine color column based on available data
    color_col = None
    hover_data = []
    
    if 'pct_dem_lead' in geojson_data.columns:
        color_col = 'pct_dem_lead'
        hover_data = ['votes_dem', 'votes_rep'] if 'votes_dem' in geojson_data.columns else []
    elif 'state_fips' in geojson_data.columns:
        color_col = 'state_fips'
    elif 'county_fips' in geojson_data.columns:
        color_col = 'county_fips'
    
    # Reset index to ensure proper alignment
    geojson_data = geojson_data.reset_index(drop=True)
    
    # Create choropleth map
    fig = px.choropleth(
        geojson_data,
        geojson=geojson_data.geometry,
        locations=geojson_data.index,
        color=color_col,
        hover_data=hover_data + (['state_fips'] if 'state_fips' in geojson_data.columns else []),
        color_continuous_scale='RdBu' if color_col == 'pct_dem_lead' else 'Viridis',
        color_continuous_midpoint=0 if color_col == 'pct_dem_lead' else None,
        labels={'pct_dem_lead': 'Dem Lead %', 'state_fips': 'State FIPS', 'votes_dem': 'Dem Votes', 'votes_rep': 'Rep Votes'},
        title=f"Election Results - {zoom_level.title()} Level"
    )
    
    # Update layout for better interactivity
    fig.update_geos(
        fitbounds="locations",
        visible=False,
        projection_type="mercator"
    )
    
    fig.update_layout(
        height=600,
        margin={"r":0,"t":30,"l":0,"b":0}
    )
    
    return fig

# App layout
app.layout = html.Div([
    html.H1("Hierarchical Precinct-Level Election Visualization", 
            style={'textAlign': 'center', 'marginBottom': 30}),
    
    html.Div([
        html.Div([
            html.Label("Zoom Level:"),
            dcc.Dropdown(
                id='zoom-level',
                options=[
                    {'label': 'National (States)', 'value': 'national'},
                    {'label': 'State (Counties)', 'value': 'state'},
                    {'label': 'County (Precincts)', 'value': 'county'}
                ],
                value='national',
                style={'width': '200px'}
            )
        ], style={'display': 'inline-block', 'marginRight': 20}),
        
        html.Div([
            html.Label("State:"),
            dcc.Dropdown(
                id='state-selector',
                options=[],
                value=None,
                style={'width': '200px'},
                disabled=True
            )
        ], style={'display': 'inline-block', 'marginRight': 20}),
        
        html.Div([
            html.Label("County:"),
            dcc.Dropdown(
                id='county-selector',
                options=[],
                value=None,
                style={'width': '200px'},
                disabled=True
            )
        ], style={'display': 'inline-block'})
    ], style={'textAlign': 'center', 'marginBottom': 20}),
    
    dcc.Graph(id='election-map'),
    
    html.Div([
        html.P("Instructions:", style={'fontWeight': 'bold'}),
        html.Ul([
            html.Li("Start with National view to see all states"),
            html.Li("Select 'State' zoom level and choose a state to see counties"),
            html.Li("Select 'County' zoom level and choose a county to see precincts"),
            html.Li("Data loads efficiently - only the needed geographic level is loaded")
        ])
    ], style={'margin': 20, 'padding': 20, 'backgroundColor': '#f0f0f0', 'borderRadius': 5})
])

@app.callback(
    [Output('state-selector', 'disabled'),
     Output('state-selector', 'options'),
     Output('county-selector', 'disabled'),
     Output('county-selector', 'options')],
    [Input('zoom-level', 'value')]
)
def update_selectors(zoom_level):
    """Update dropdown options based on zoom level."""
    # State selector
    if zoom_level in ['state', 'county']:
        # Enable state selector and populate with available states
        state_dirs = []
        states_path = Path('data/states/by_state')
        if states_path.exists():
            state_dirs = [d.name for d in states_path.iterdir() if d.is_dir()]
        
        state_options = [{'label': f'State {s}', 'value': s} for s in sorted(state_dirs)]
        state_disabled = False
    else:
        state_options = []
        state_disabled = True
    
    # County selector
    if zoom_level == 'county':
        county_disabled = False
        county_options = []  # Will be populated when state is selected
    else:
        county_disabled = True
        county_options = []
    
    return state_disabled, state_options, county_disabled, county_options

@app.callback(
    Output('county-selector', 'options', allow_duplicate=True),
    [Input('state-selector', 'value')],
    [State('zoom-level', 'value')],
    prevent_initial_call=True
)
def update_county_options(selected_state, zoom_level):
    """Update county options when state is selected."""
    if zoom_level == 'county' and selected_state:
        # Get available counties for the selected state
        precincts_path = Path(f'data/states/by_state/{selected_state}/precincts')
        if precincts_path.exists():
            county_files = list(precincts_path.glob('*_precincts.geojson'))
            counties = [f.stem.replace('_precincts', '') for f in county_files]
            county_options = [{'label': f'County {c[2:]}', 'value': c[2:]} for c in sorted(counties)]
            return county_options
    
    return []

@app.callback(
    Output('election-map', 'figure'),
    [Input('zoom-level', 'value'),
     Input('state-selector', 'value'),
     Input('county-selector', 'value')]
)
def update_map(zoom_level, selected_state, selected_county):
    """Update map based on zoom level and selections."""
    
    if zoom_level == 'national':
        # Load national state boundaries
        data = get_state_boundaries()
        return create_figure(data, 'national')
    
    elif zoom_level == 'state' and selected_state:
        # Load counties for selected state + adjacent state boundaries
        counties = get_state_counties(selected_state)
        adjacent_states = get_adjacent_states(selected_state)
        
        if counties is not None:
            return create_figure(counties, 'state')
        else:
            # Fallback to state boundaries if counties not available
            return create_figure(adjacent_states, 'state fallback')
    
    elif zoom_level == 'county' and selected_state and selected_county:
        # Load precincts for selected county
        precincts = get_county_precincts(selected_state, selected_county)
        return create_figure(precincts, 'county')
    
    else:
        # Default to national view
        data = get_state_boundaries()
        return create_figure(data, 'national')

if __name__ == '__main__':
    # Clear any cached data
    data_cache.clear()
    
    # Check if hierarchical data exists
    if not os.path.exists('data/states/state_boundaries.geojson'):
        print("Hierarchical data not found. Please run split_precinct_data.py first.")
        print("Usage: python split_precinct_data.py")
        exit(1)
    
    # Validate the state_boundaries.geojson file
    try:
        test_data = gpd.read_file('data/states/state_boundaries.geojson')
        print(f"Successfully validated state_boundaries.geojson with {len(test_data)} features")
        print(f"Sample: State {test_data.iloc[0].get('state_fips')}: {test_data.iloc[0].get('pct_dem_lead'):.1f}% Dem lead")
    except Exception as e:
        print(f"Error with state_boundaries.geojson: {e}")
        print("The file may be corrupted. Please re-run split_precinct_data.py")
        exit(1)
    
    print("Starting hierarchical precinct visualization...")
    print("Open http://127.0.0.1:8050 in your browser")
    app.run_server(debug=True)