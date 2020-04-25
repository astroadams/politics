# -*- coding: utf-8 -*-
"""
Created on Tue Nov 12 07:04:33 2019

@author: Scott

Plan:
    1. Gather state and national presidential election results for the last 
       several cycles, along with electoral votes
    2. Calculate state-by-state trends, with & w/out adjusting for national 
       environment -- e.g., 
            National  Texas  TX Adj  Georgia GA Adj  PA     PA-adj  AZ     AZ-adj  VA    VA-adj
       2016 D+2.1     R+9.0  R+11.1  R+5.2   R+7.3   R+0.7  R+2.8   R+3.6  R+5.7   D+5.4 D+3.3
       2012 D+2.9     R+15.8 R+18.7  R+7.8   R+10.7  D+5.4  D+3.5   R+9.1  R+12.0  D+3.9 D+1.0
       2008 D+7.3     R+11.8 R+19.1  R+5.2   R+12.5  D+10.4 D+3.1   R+8.5  R+15.8  D+6.3 R+1.0
       2004 R+2.5     R+22.9 R+20.4  R+16.6  R+14.1  D+2.5  D+5.0   R+10.5 R+8.0   R+8.2 R+5.5
       2000 D+0.5     R+21.3 R+21.8  R+11.7  R+12.2  D+4.2  D+3.7   R+6.3  R+6.8   R+8.1 R+7.3
    3. Generate line-chart showing margins, state-by-state,
       w/toggle for national environment adjustment
    4. Generate chloropleth showing state-level results,
       with toggle for environment adjustment and slider for
       electoral cycle
    5. Project 2020 results with toggle for different 
       extrapolations (linear, 2nd order poly, etc) and slider
       for different national environments
    6. Show tipping point state for each cycle and, for 2020, different 
       extrapolations
    7. Generate chloropleth color-coded by trendline slope
    
Take-aways:
    1. Electoral college worked to Dem's advantage in 2012, but disadvantage
       in 2000, 201
    2. Sunbelt moving leftward, but gains won't be reflected in electoral 
       college for quite some time (2024?)
    3. Midwest really does have outsized importance.  If its rightward shift in 
       2016 is not reversed the electoral college will put Dems at an even 
       greater disadvantage in 2020 than in 2016.
"""

import pandas as pd

prep = True
plot = True
pvi_plot = True

if prep:
    df = pd.read_csv('1976-2016-president.csv')
    ev_df = pd.read_csv('electoral_vote_apportionment.csv')
    # state, code, %margin D, nD, nR, nT
    
    states = df['state_po'].unique()
    years = df['year'].unique()
    
    f = open('margins.csv','w')
    f.write('year,state,electoral_votes,margin,pvi\n')
    for year in years:
        dfy = df[df['year']==year]
        dtotal = dfy[dfy['party'].str.contains('democrat').ffill(0)]['candidatevotes'].sum()
        rtotal = dfy[dfy['party']=='republican']['candidatevotes'].sum()
        total = dfy['candidatevotes'].sum()
        national_margin = (rtotal/total-dtotal/total) * 100
        # census year = max year <= election year
        census_year = ev_df.columns[1:][ev_df.columns[1:].astype(float)<=year][-1]
        for state in states:
            dem = dfy[(dfy['state_po']==state) & (dfy['party'].str.contains('democrat'))]['candidatevotes'].values[0]
            rep = dfy[(dfy['state_po']==state) & (dfy['party']=='republican')]['candidatevotes'].values[0]
            total = dfy[(dfy['state_po']==state) & (dfy['party']=='republican')]['totalvotes'].values[0]
            margin = (rep/total - dem/total) * 100
            pvi = margin - national_margin
            ev = ev_df[ev_df['State']==state][census_year].values[0]+2 # +2 to convert from # congressional seats to # of electoral votes
            f.write('%d,%s,%d,%f,%f\n' % (year, state, ev, margin, pvi))
    f.close()

if pvi_plot:
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize
    df = pd.read_csv('margins.csv')
    years = df['year'].unique()
    norm = Normalize(vmin=min(years), vmax=max(years))
    cm = plt.cm.get_cmap('RdYlBu')
    for year in years:
        dfy = df[df['year']==year]
        # add end points for CDF
        #dfy = dfy.append({'year':year, 'state':'fake', 'pvi':-100, 'electoral_votes':0}, ignore_index=True)
        #dfy = dfy.append({'year':year, 'state':'fake', 'pvi':100, 'electoral_votes':0}, ignore_index=True)
        sdfy = dfy.sort_values(by='pvi')
        # calculate cumulative distribution function
        color = cm(norm(year))
        print(color)
        plt.hist(sdfy['pvi'], cumulative=True, histtype='step', weights=sdfy['electoral_votes']/269., color=color, range=(-100,100), bins=2201, alpha=0.8)
        plt.plot([-100,100],[1,1], '-', color='black', linewidth=1)
        plt.xlim(-10,10)
        plt.ylim(0.75,1.25)
    
if plot:
    import dash
    import dash_core_components as dcc
    import dash_html_components as html
    import plotly.graph_objs as go
    from dash.dependencies import Input, Output, State

    #external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']    
    #app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
    #app = dash.Dash(__name__, meta_tags=[
    #        {"name": "viewport", "content": "width=device-width, initial-scale=0.9"}
    #])
    app = dash.Dash(__name__)
    server = app.server
    
    df = pd.read_csv('margins.csv')
    years = df['year'].unique()

    year = 2016
    radio = 'margin'
    # Map
    data = [go.Choropleth(
            locations = df[df['year']==year]['state'],
            z = df[df['year']==year][radio],
            locationmode = 'USA-states',
            colorscale = 'RdBu',
            reversescale = True,  
            zmid = 0,
            zmin = -30,
            zmax = 30,
            text = df[df['year']==year][radio].map('{:,.1f}%'.format),
            hoverinfo='location+text',
            colorbar = go.choropleth.ColorBar(
                    title = 'Dem Margin'))]
 
    layout = go.Layout(
        #title = go.layout.Title(
        #    text = '2016 Presidential Election'
        #),
        geo = go.layout.Geo(
            showframe = False,
            showcoastlines = False,
            projection = go.layout.geo.Projection(
                type = 'albers usa'
            )
        ),
        height=900
    )
    
    
    app.layout = html.Div(
        id = "root",
        children = [
            html.Div(
                id="header",
                children=[
                    html.H4(children="Presidential Election Results")
                ]
            ),
            html.Div(
                id="slider-container",
                children=[
                    html.P(
                        id="slider-text",
                        children="Drag the slider to change the year:",
                    ),
                    dcc.Slider(
                        id="years-slider",
                        min=min(years),
                        max=max(years),
                        value=min(years),
                        marks={str(year): str(year) for year in years}, 
                        step=None
                    ),
                    #html.Label('Margin or Lean'),
                    dcc.RadioItems(
                        id="radio",
                        options=[
                            {'label': 'Margin', 'value': 'margin'},
                            {'label': 'Partisan Lean', 'value': 'pvi'}
                        ],
                        value='margin'
                    ),
                ]
            ),
            html.Div(
                id="heatmap-container",
                children=[
                    html.P("Heatmap of election margins in 2016",
                        id="heatmap-title"
                    ),
                    dcc.Graph(
                        id='choropleth',
                        figure={
                            'data': data,
                            'layout': layout
                        }
                    )
                ]
            )
        ]
    )


    @app.callback(Output("heatmap-title", "children"), [Input("years-slider", "value")])
    def update_map_title(year):
        return "Heatmap of election margins in {0}".format(
            year
        )

    @app.callback(Output("choropleth", "figure"), 
        [Input("years-slider", "value"),
        Input("radio", "value")],
        [State("choropleth", "figure")]
    )
    def display_map(year, radio, figure):
        data = [go.Choropleth(
                locations = df[df['year']==year]['state'],
                z = df[df['year']==year][radio],
                locationmode = 'USA-states',
                colorscale = 'RdBu',
                reversescale = True, 
                zmid = 0,
                zmin = -30,
                zmax = 30,
                text = df[df['year']==year][radio].map('{:,.1f}%'.format),
                hoverinfo='location+text',
                colorbar = go.choropleth.ColorBar(
                        title = 'Margin'))]
            
        layout = go.Layout(
            #title = go.layout.Title(
            #    text = '2016 Presidential Election'
            #),
            geo = go.layout.Geo(
                showframe = False,
                showcoastlines = False,
                projection = go.layout.geo.Projection(
                    type = 'albers usa'
                )
            ),
            height=900
        )
        figure={
            'data': data,
            'layout': layout,
            }
        return figure

                
if __name__ == '__main__':
    app.run_server(debug=True)
    