import pandas as pd
import streamlit as st
import xnat
import os
import plotly.express as px
import matplotlib.pyplot as plt
import base64
import numpy as np
import pydicom
import datetime
import plotly.figure_factory as ff
import plotly.express as px
import plotly.graph_objects as go

@st.cache_data
def load_data(url, user, password):
    df = pd.read_csv(url, storage_options={"Authorization": b"Basic " + base64.b64encode(f"{user}:{password}".encode())})
    return df

class App:

    def __init__(self, host=None, user=None, password=None, project_id=None):
        self._host = host or os.environ.get('XNAT_HOST')
        self._user = user or os.environ.get('XNAT_USER')
        self._password = password or os.environ.get('XNAT_PASS')
        self._project_id = project_id or (os.environ.get('XNAT_ITEM_ID') if os.environ.get('XNAT_XSI_TYPE') == 'xnat:projectData' else None)
        self._connection = xnat.connect(self._host, user=self._user, password=self._password)

        if self._project_id:
            try: 
                self._project = self._connection.projects[self._project_id]
            except Exception as e:
                raise Exception(f'Error connecting to project {self._project_id}', e)
        else:
            raise Exception('Must be started from an XNAT project.')
        
        self._init_session_state()
        self._load_data()
        self._init_ui()

    def _load_data(self):
        self._load_caliper_measurements()
        self._load_pdxs()

        # join pdx to caliper measurements
        self._caliper_measurements = self._caliper_measurements.merge(self._pdxs, how='left', left_on='subject', right_on='subject')

    def _load_caliper_measurements(self):
        url = f'{self._host}/data/projects/{self._project_id}/experiments?format=csv&xsiType=pixi:caliperMeasurementData&columns=date,pixi:caliperMeasurementData/weight,pixi:caliperMeasurementData/length,pixi:caliperMeasurementData/width,subject_label,xnat:subjectdata/group'
        df = load_data(url, self._user, self._password)
        df = df.drop(columns=['URI', 'pixi:calipermeasurementdata/id'])

        # add volume column of length * width * width
        df['volume'] = 0.5 * df['pixi:calipermeasurementdata/length'] * df['pixi:calipermeasurementdata/width'] * df['pixi:calipermeasurementdata/width']

        # simplify column names
        df = df.rename(columns={
            'pixi:calipermeasurementdata/subject_id': 'subjectId',
            'pixi:calipermeasurementdata/weight': 'weight',
            'pixi:calipermeasurementdata/length': 'length',
            'pixi:calipermeasurementdata/width': 'width',
            'subject_label': 'subject',
            'xnat:subjectdata/group': 'group'
        })

        # set date column to datetime
        df['date'] = pd.to_datetime(df['date'])

        # sort by date
        df = df.sort_values(by='date')

        self._caliper_measurements = df

        # Update selectors
        st.session_state.subjects.clear()
        st.session_state.subjects.extend(df['subject'].unique().tolist())
        st.session_state.subjects.sort()

        st.session_state.groups.clear()
        st.session_state.groups.extend(df['group'].unique().tolist())
        st.session_state.groups.sort()

    def _load_pdxs(self):
        url = f'{self._host}/data/projects/{self._project_id}/experiments?format=csv&xsiType=pixi:pdxData&columns=date,pixi:pdxData/sourceId,pixi:pdxData/injectionSite,subject_label'
        df = load_data(url, self._user, self._password)
        df = df.drop(columns=['URI', 'pixi:pdxdata/id'])

        # simplify column names
        df = df.rename(columns={
            'pixi:pdxdata/sourceid': 'pdxId',
            'pixi:pdxdata/injectionsite': 'injectionSite',
            'subject_label': 'subject',
            'xnat:subjectdata/group': 'group',
            'date': 'injectionDate'
        })

        # set date column to datetime
        df['injectionDate'] = pd.to_datetime(df['injectionDate'])

        # sort by date
        df = df.sort_values(by='injectionDate')

        self._pdxs = df

        # Update selectors
        st.session_state.pdxs.clear()
        st.session_state.pdxs.extend(df['pdxId'].unique().tolist())
        st.session_state.pdxs.sort()

    def _init_session_state(self):
        # Initialize streamlit session state
        # Values will be populated later
        if 'project' not in st.session_state:
            st.session_state.project = self._project

        if 'project_id' not in st.session_state:
            st.session_state.project_id = self._project_id

        if 'subjects' not in st.session_state:
            st.session_state.subjects = []

        if 'groups' not in st.session_state:
            st.session_state.groups = []

        if 'pdxs' not in st.session_state:
            st.session_state.pdxs = []

    def _init_ui(self):
        # Hide streamlit deploy button
        st.markdown("""
            <style>
                .reportview-container {
                    margin-top: -2em;
                }
                #MainMenu {visibility: hidden;}
                .stDeployButton {display:none;}
                footer {visibility: hidden;}
                #stDecoration {display:none;}
            </style>
        """, unsafe_allow_html=True)

        # Initialize UI
        self._init_sidebar()
        self._init_main()

    def _init_sidebar(self):
        # Streamlit setup
        with st.sidebar:
            st.title("PIXI Caliper Measurement Visualizer")
            st.markdown("*View statistical plots for caliper measurements within a project.*")
            
            with st.expander("Options", expanded=True):
                # Excluded subjects
                self._excluded_subjects = st.multiselect("Excluded Subjects", st.session_state.subjects, default=[], key='excluded_subjects', on_change=self._update_plot)

                # Excluded groups
                self._excluded_groups = st.multiselect("Excluded Groups", st.session_state.groups, default=[], key='excluded_groups', on_change=self._update_plot)
                
                # Start date
                self._start_date = st.date_input("Start Date", self._caliper_measurements['date'].min(), key='start_date', on_change=self._update_plot)

            # with st.expander("Advanced Options"):
            #     # Axis labels and title
            #     self._title = st.text_input("Title", "Tumor Volume vs Time by Group", key='title', on_change=self._update_plot)
            #     self._x_axis_label = st.text_input("X-axis Label", "Time (days)", key='x_axis_label', on_change=self._update_plot)
            #     self._y_axis_label = st.text_input("Y-axis Label", "Tumor Volume (mm^3)", key='y_axis_label', on_change=self._update_plot)
            #     self._legend_title = st.text_input("Legend Title", "Group", key='legend_title', on_change=self._update_plot)
                

    def _init_main(self):
        self._main = st.container()

        with self._main:

            tab1, tab2, tab3 = st.tabs([
                'All Measurements Plot',
                'Box Plot',
                'Data Table',
            ])

            with tab1:
                self._tab1 = st.empty()

            with tab2:
                self._tab2 = st.empty()

            with tab3:
                self._tab3 = st.empty()

        self._update_plot()

    def _update_plot(self):
        self._tab1.empty()
        with self._tab1:
            self._plot_all_measurements()

        self._tab2.empty()
        with self._tab2:
            self._plot_box_plot()

        self._tab3.empty()
        with self._tab3:
            df = self._get_filtered_data()
            st.dataframe(df)

    def _get_filtered_data(self):
        df = self._caliper_measurements

        if len(self._excluded_subjects) > 0:
            df = df[~df['subject'].isin(self._excluded_subjects)]

        if self._start_date is not None:
            df['days'] = (df['date'] - pd.Timestamp(self._start_date)).dt.days
        else:
            df['days'] = (df['date'] - df['date'].min()).dt.days

        if len(self._excluded_groups) > 0:
            df = df[~df['group'].isin(self._excluded_groups)]

        return df
    
    def _plot_all_measurements(self):
        df = self._get_filtered_data()

        fig = go.Figure()

        # Line for each subject colored by group
        colors = px.colors.qualitative.Plotly
        for i, group in enumerate(df['group'].unique()):
            group_df = df[df['group'] == group]
            for subject in group_df['subject'].unique():
                subject_df = group_df[group_df['subject'] == subject]
                fig.add_trace(go.Scatter(x=subject_df['days'], y=subject_df['volume'], mode='lines+markers', name=subject, line=dict(color=colors[i]),
                                         legendgroup=group, legendgrouptitle_text=group.capitalize()))

        fig.update_layout(
            width=800, height=600,
            title='Tumor Volume vs Time for All Subjects',
            xaxis_title='Time (days)',
            yaxis_title='Tumor Volume (mm^3)',
            legend_title='Subjects',
        )

        st.plotly_chart(fig)

    def _plot_box_plot(self):
        df = self._get_filtered_data()

        # box plot of days vs volume by group
        self._fig_2 = px.box(df, x='days', y='volume', color='group', 
                             title='Tumor Volume vs Time by Group', points="all", 
                             width=800, height=600, 
                             range_x=[df['days'].min() - 2, df['days'].max() + 2],
                             range_y=[0, df['volume'].max() + df['volume'].max() * 0.1])

        # update fig size
        self._fig_2.update_layout(
            xaxis_title='Time (days)',
            yaxis_title='Tumor Volume (mm^3)',
            legend_title='Group',
        )

        st.plotly_chart(self._fig_2)

    
app = App()

