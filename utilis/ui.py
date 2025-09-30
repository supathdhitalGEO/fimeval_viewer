
import streamlit as st
def inject_sidebar_nav_css(font_size_px=28, width_px=320):
    st.markdown(
        f"""
        <style>
        /* Make the sidebar wider (optional) */
        section[data-testid="stSidebar"] {{
            min-width: {width_px}px !important;
            max-width: {width_px}px !important;
        }}

        /* Make sidebar nav labels bigger & bolder.
           Cover a, and any child (p/span/div) — works across Streamlit versions. */
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] li a,
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] li a * ,
        section[data-testid="stSidebar"] nav li a,
        section[data-testid="stSidebar"] nav li a * {{
            font-size: {font_size_px}px !important;
            font-weight: 800 !important;
            line-height: 1.2 !important;
            color: #1f2937 !important;
        }}

        /* Hover & active colors */
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] li a:hover *,
        section[data-testid="stSidebar"] nav li a:hover * {{
            color: #2563eb !important;
        }}
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] li a[aria-current="page"] *,
        section[data-testid="stSidebar"] nav li a[aria-current="page"] * {{
            color: #1d4ed8 !important;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )