# Truck Parking Safety Analysis

## Overview

This project investigates crash activity near truck parking facilities using geospatial analytics, transportation safety data, and statistical modeling.

The objective was to determine whether truck parking facilities experience significantly different crash rates compared to comparable roadway segments and control locations.

## Business Problem

Truck parking shortages are a growing transportation safety concern. This project analyzes crash patterns surrounding truck parking facilities to identify potential safety impacts and support data-driven infrastructure decisions.

## Data Sources

- Maryland State Police Crash Data
- Truck Parking Facility Data
- Traffic Message Channel (TMC) Network Data
- Vehicle Miles Traveled (VMT) Data
- Roadway Geometry and Directional Data

## Methodology

### Data Preparation
- Cleaned and standardized crash records
- Removed duplicate observations
- Validated spatial coordinates
- Integrated multiple transportation datasets

### Geospatial Analysis
- Crash-to-parking-zone conflation
- Buffer-based spatial matching
- Directional validation
- TMC network integration

### Statistical Analysis
- Hypothesis testing
- Poisson models
- Negative Binomial regression
- Crash rate comparisons using VMT normalization

## Technologies

- Python
- Pandas
- GeoPandas
- NumPy
- SciPy
- SQL
- Tableau

## Key Results

- Analyzed over 1 million crash records
- Identified statistically significant safety differences across parking facility zones
- Developed repeatable crash-to-zone conflation methodology
- Produced executive-level dashboards supporting transportation safety analysis

## Skills Demonstrated

- Geospatial Analytics
- Statistical Modeling
- Data Engineering
- Transportation Analytics
- Data Visualization
- Python Development
