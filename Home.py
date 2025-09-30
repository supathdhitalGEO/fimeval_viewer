import streamlit as st

st.set_page_config(page_title="FIM Benchmark Viewer", page_icon="🌊", layout="wide")

# App title and subtitle
st.title("FIM Benchmark Viewer")
st.markdown(
    """
Welcome to the **Flood Inundation Mapping Benchmark Viewer (FIMeval)**. This app is developed under the **Surface Dynamics Modeling Lab (SDML)** at 
**The University of Alabama** to visualize, benchmark, and evaluate flood inundation maps (FIMs).

---
"""
)

# Introduction
st.header("About Flood Inundation Mapping Predictions Evaluation Framework")
st.markdown(
    """
The **accuracy of flood inundation maps** is critical for hydrologic modeling, flood preparedness, and disaster response. However, evaluating different flood maps can be tedious and error-prone.  

**FIMeval** automates this process by:
- Comparing model-predicted FIMs with benchmark datasets
- Computing key evaluation metrics (e.g., CSI, POD, FAR, F1, Accuracy)
- Optionally integrating building footprint impacts
- Supporting permanent waterbody masking and custom AOI boundaries
- Integrated with the extensive benchmark FIM repository developed at SDML which is integrated within the **fimeval**
"""
)

# Cross reference to Map page
st.header("Explore the Benchmark FIMs available with different levels of detail")
st.markdown(
    """
Use the button below to open the **Interactive Map** page,  
where you can view available benchmark FIMs on multiple basemaps, overlay boundaries,  
and explore results interactively.
"""
)
if st.button("Click here to go to **Interactive Viewer**"):
    st.switch_page("pages/1_Interactive Map.py")

# Project info section
st.header("Project GitHub Repository for Contribution and Collaboration")
st.markdown(
    """
This project builds on the open-source **[fimeval](https://github.com/sdmlua/fimeval)**  
Python framework developed at SDML.
For installation, documentation, and usage examples, see the [FIMeval GitHub Repo](https://github.com/sdmlua/fimeval).
"""
)

# Footer / credits
st.divider()
st.caption(
    """
Developed by the **Surface Dynamics Modeling Lab (SDML)**,  
Department of Geography and the Environment, The University of Alabama.  
Contact: [Sagy Cohen](mailto:sagy.cohen@ua.edu), [Supath Dhital](mailto:sdhital@crimson.ua.edu),  [Dipsikha Devi](mailto:ddevi@ua.edu)
"""
)
