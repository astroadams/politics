# Panel + GeoViews Election Visualization

This is an alternative implementation of the hierarchical election visualization using Panel + GeoViews instead of Dash. This approach provides better native support for zoom-based callbacks and geographic data handling.

## Key Advantages over Dash

1. **Native Zoom Callbacks**: Panel + GeoViews has built-in support for viewport change events
2. **Better Geographic Integration**: GeoViews is specifically designed for geographic visualizations
3. **Cleaner Architecture**: Reactive parameters automatically handle state management
4. **No Callback Conflicts**: Eliminates the zoom reset and callback ordering issues from Dash

## Installation

Install the additional dependencies:

```bash
pip install panel>=1.3.0 geoviews>=1.10.0 holoviews>=1.17.0 geopandas>=0.14.0 bokeh>=3.0.0 param>=2.0.0
```

Or install all dependencies including the new Panel ones:

```bash
pip install -r requirements.txt
```

## Usage

Run the Panel version:

```bash
python precinct_visualization_panel.py
```

This will start a Panel server and display the URL to open in your browser (typically `http://localhost:5007`).

## Features

### Automatic Zoom-Based Data Switching
- **State Level**: Continental/multi-state view (geographic span > 30°)
- **County Level**: State/regional view (geographic span 3-30°)  
- **Precinct Level**: Local view (geographic span < 3°, ~50 miles)

### Interactive State Selection
- Click on states to toggle county-level detail view
- Selected states show counties while others show state-level data
- Mixed granularity visualization

### Performance Optimizations
- Efficient data caching
- Only loads necessary geographic levels
- Consistent CRS handling (WGS84/EPSG:4326)

## Key Differences from Dash Version

1. **Parameter-Based Reactivity**: Uses `param.Parameterized` for clean state management
2. **Native Geographic Tools**: Built-in zoom detection and viewport handling
3. **Dynamic Maps**: `hv.DynamicMap` automatically updates when parameters change
4. **Cleaner Event Handling**: Direct tap and range callbacks without complex routing

## Data Requirements

The application expects the same hierarchical data structure created by `split_precinct_data.py`:

```
data/
  states/
    state_boundaries.geojson
    by_state/
      01/  # Alabama
        counties_01.geojson
        precincts/
          01001_precincts.geojson
          01003_precincts.geojson
          ...
      02/  # Alaska
        counties_02.geojson
        precincts/
          ...
```

## Technical Implementation

### Core Classes
- `HierarchicalElectionMap`: Main parameterized class managing the visualization
- Reactive parameters: `zoom_level`, `selected_states`, `current_bounds`
- Automatic data loading based on zoom level and selected states

### Event Handling
- `handle_tap()`: Processes map clicks for state selection
- `handle_range()`: Monitors viewport changes for zoom level detection
- Parameter watchers automatically trigger map updates

### Visualization Pipeline
1. Determine zoom level from viewport bounds
2. Load appropriate data (state/county/precinct)
3. Create GeoViews polygons with styling
4. Apply hover tooltips and interaction tools
5. Update reactive display

This implementation should resolve the callback conflicts and zoom reset issues experienced with the Dash version while providing the same hierarchical visualization capabilities.