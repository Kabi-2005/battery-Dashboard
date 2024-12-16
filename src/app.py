import os
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from dash import Dash, html, dcc, Input, Output

# Load and parse metadata
metadata = pd.read_csv('cleaned_dataset/metadata.csv')


def parse_matlab_time(str_time):
    str_time = str_time.strip().strip('[]')
    parts = str_time.split()
    if len(parts) != 6:
        return pd.NaT
    arr = [float(x) for x in parts]
    year, month, day, hour, minute, sec = arr
    sec_int = int(sec)
    microseconds = int(round((sec - sec_int) * 1_000_000))
    return pd.Timestamp(year=int(year), month=int(month), day=int(day),
                        hour=int(hour), minute=int(minute), second=sec_int, microsecond=microseconds)


metadata['start_time'] = metadata['start_time'].apply(parse_matlab_time)
metadata = metadata.sort_values('start_time').reset_index(drop=True)

metadata['Re'] = pd.to_numeric(metadata['Re'], errors='coerce')
metadata['Rct'] = pd.to_numeric(metadata['Rct'], errors='coerce')
metadata['Capacity'] = pd.to_numeric(metadata['Capacity'], errors='coerce')

# Separate operations by type
impedance_data = metadata[metadata['type'] == 'impedance'].copy()
discharge_data = metadata[metadata['type'] == 'discharge'].copy()

discharge_data = discharge_data.sort_values(
    'start_time').reset_index(drop=True)
discharge_data['cycle_number'] = discharge_data.index + 1

impedance_data = impedance_data.sort_values(
    'start_time').reset_index(drop=True)
impedance_data['impedance_cycle_number'] = impedance_data.index + 1


def to_complex_or_float(x):
    if pd.isnull(x):
        return np.nan
    if isinstance(x, (float, int)):
        return complex(x)
    if isinstance(x, str):
        x = x.strip().strip('()')
        if not x:
            return np.nan
        try:
            return complex(x)
        except ValueError:
            return np.nan
    return np.nan


def get_rectified_impedance(file_path):
    if not os.path.exists(file_path):
        return np.nan
    try:
        df = pd.read_csv(file_path)
        if 'Rectified_Impedance' in df.columns:
            df['Rectified_Impedance'] = df['Rectified_Impedance'].apply(
                to_complex_or_float)
            real_values = df['Rectified_Impedance'].apply(
                lambda c: c.real if isinstance(c, complex) else c)
            return real_values.median()
        else:
            return np.nan
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return np.nan


data_base_path = 'cleaned_dataset/data/'
rectified_values = []
for idx, row in impedance_data.iterrows():
    fname = row['filename']
    file_path = os.path.join(data_base_path, fname)
    rect_val = get_rectified_impedance(file_path)
    rectified_values.append(rect_val)

impedance_data['Rectified_Impedance'] = rectified_values

impedance_data_clean = impedance_data.dropna(
    subset=['Re', 'Rct', 'Rectified_Impedance'])
impedance_data_clean = impedance_data_clean[
    (impedance_data_clean['Re'] > 0) & (impedance_data_clean['Re'] < 10) &
    (impedance_data_clean['Rct'] > 0) & (impedance_data_clean['Rct'] < 10) &
    (impedance_data_clean['Rectified_Impedance'] > 0) & (
        impedance_data_clean['Rectified_Impedance'] < 10)
]
impedance_data = impedance_data_clean

# Dash app initialization
app = Dash(__name__)

server = app.server

# Layout
app.layout = html.Div([
    html.H1("Battery Analysis Dashboard", style={'textAlign': 'center'}),
    html.Hr(),

    html.Div([
        html.Label("Select Battery ID:"),
        dcc.Dropdown(
            options=[{'label': b, 'value': b}
                     for b in metadata['battery_id'].unique()],
            value=metadata['battery_id'].iloc[0],
            id='battery-dropdown'
        ),
    ], style={'marginBottom': '20px'}),

    dcc.Tabs([
        dcc.Tab(label="Re and Rct Over Time", children=[
            dcc.Graph(id='re-rct-plot')
        ]),
        dcc.Tab(label="Rectified Impedance", children=[
            dcc.Graph(id='rectified-impedance-plot')
        ]),
        dcc.Tab(label="Capacity Fade", children=[
            dcc.Graph(id='capacity-fade-plot')
        ]),
    ]),
])

# Callbacks


@app.callback(
    [
        Output('re-rct-plot', 'figure'),
        Output('rectified-impedance-plot', 'figure'),
        Output('capacity-fade-plot', 'figure')
    ],
    Input('battery-dropdown', 'value')
)
def update_plots(battery_id):
    selected_impedance = impedance_data[impedance_data['battery_id'] == battery_id]
    selected_discharge = discharge_data[discharge_data['battery_id'] == battery_id]

    # Re and Rct Plot
    fig_re_rct = go.Figure()
    fig_re_rct.add_trace(go.Scatter(
        x=selected_impedance['impedance_cycle_number'],
        y=selected_impedance['Re'],
        mode='lines+markers',
        name='Electrolyte Resistance (Re)'
    ))
    fig_re_rct.add_trace(go.Scatter(
        x=selected_impedance['impedance_cycle_number'],
        y=selected_impedance['Rct'],
        mode='lines+markers',
        name='Charge Transfer Resistance (Rct)',
        yaxis='y2'
    ))
    fig_re_rct.update_layout(
        title='Re and Rct Over Time',
        xaxis_title='Impedance Measurement Number',
        yaxis_title='Re (Ohms)',
        yaxis2=dict(
            title='Rct (Ohms)',
            overlaying='y',
            side='right'
        ),
        template='plotly_white'
    )

    # Rectified Impedance Plot
    fig_rectified = go.Figure()
    fig_rectified.add_trace(go.Scatter(
        x=selected_impedance['impedance_cycle_number'],
        y=selected_impedance['Rectified_Impedance'],
        mode='lines+markers',
        name='Rectified Impedance'
    ))
    fig_rectified.update_layout(
        title='Rectified Impedance Over Time',
        xaxis_title='Impedance Measurement Number',
        yaxis_title='Rectified Impedance (Ohms)',
        template='plotly_white'
    )

    # Capacity Fade Plot
    fig_capacity = go.Figure()
    fig_capacity.add_trace(go.Scatter(
        x=selected_discharge['cycle_number'],
        y=selected_discharge['Capacity'],
        mode='lines+markers',
        name='Capacity'
    ))
    fig_capacity.update_layout(
        title='Capacity Fade Over Discharge Cycles',
        xaxis_title='Cycle Number',
        yaxis_title='Capacity (Ahr)',
        template='plotly_white'
    )

    return fig_re_rct, fig_rectified, fig_capacity


# Run the app
if __name__ == '__main__':
    app.run_server(debug=True)
