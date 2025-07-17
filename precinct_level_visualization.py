# conda activate mapping

import dash
#import dash_core_components as dcc
from dash import dcc
#import dash_html_components as html
from dash import html
from dash.dependencies import Input, Output
import plotly.express as px
import geopandas as gpd

app = dash.Dash(__name__)

# Load your GeoJSON data
print('loading data')
precinct_geojson = gpd.read_file('data/fips24.geojson')
state_geojson =  precinct_geojson #gpd.read_file('data/precincts-with-results.geojson')
county_geojson = precinct_geojson #gpd.read_file('path/to/county_geojson_file.geojson')
print('finished loading data')

# Sample data columns: ['geometry', 'state', 'county', 'precinct', 'votes_party1', 'votes_party2']
# You will need to merge your election results with the geojson dataframes.

def create_figure(geojson, level='state', use_mapbox=False):
    if use_mapbox:
        fig = px.choropleth_mapbox(
            geojson,
            geojson=geojson.geometry,
            locations=geojson.index,
            color='pct_dem_lead',
            hover_data=['votes_dem', 'votes_rep'],
            mapbox_style="carto-positron",
            opacity=0.4,
            center={"lat": 38.99927700381166, "lon": -77.03461273617128},
            color_continuous_scale='RdBu',
            zoom=8,
        )
        fig.update_geos(fitbounds="locations", visible=False)
    else:
        fig = px.choropleth(
            geojson,
            geojson=geojson.geometry,
            locations=geojson.index,
            color='pct_dem_lead',
            hover_data=['votes_dem', 'votes_rep'],
            projection="mercator",
            color_continuous_scale='RdBu',
        )
        fig.update_geos(fitbounds="locations", visible=True)
    
    fig.update_layout(title=f"Election Results at {level} level", margin={"r":0,"t":0,"l":0,"b":0})
    return fig

app.layout = html.Div([
    dcc.Graph(id='election-map', figure=create_figure(precinct_geojson)),
    dcc.Store(id='zoom-level', data='precinct')
])

@app.callback(
    Output('election-map', 'figure'),
    Output('zoom-level', 'data'),
    Input('election-map', 'relayoutData'),
    Input('zoom-level', 'data')
)
def update_map(relayoutData, zoom_level):
    if relayoutData and 'mapbox.zoom' in relayoutData:
        zoom = relayoutData['mapbox.zoom']
        
        if zoom_level == 'state' and zoom > 5:
            return create_figure(county_geojson, level='county'), 'county'
        elif zoom_level == 'county' and zoom > 10:
            return create_figure(precinct_geojson, level='precinct'), 'precinct'
        elif zoom_level == 'precinct' and zoom <= 10:
            return create_figure(county_geojson, level='county'), 'county'
        elif zoom_level == 'county' and zoom <= 5:
            return create_figure(state_geojson, level='state'), 'state'
    
    return dash.no_update, dash.no_update

if __name__ == '__main__':
    app.run_server(debug=True)