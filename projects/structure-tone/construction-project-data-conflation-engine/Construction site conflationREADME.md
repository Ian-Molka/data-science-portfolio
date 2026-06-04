# Construction Project Data Conflation Engine

## Overview

This project is an automated data integration and workflow management system developed to synchronize construction project tracking data between centralized project databases and field-maintained Excel workbooks.

The system eliminates manual data entry by automatically identifying updates, reconciling records, preserving project tracking workflows, and applying changes across project management documents used by on-site teams.

## Business Problem

Construction teams maintain project information across multiple systems, including centralized databases and field-updated spreadsheets.

Manual transfer of information between these systems is time-consuming, prone to errors, and creates inconsistencies that can impact project schedules, procurement tracking, and stakeholder reporting.

This solution automates the synchronization process, ensuring that project data remains accurate and up to date while reducing administrative workload.

## Objectives

- Eliminate manual data entry
- Synchronize database records with field-maintained spreadsheets
- Preserve existing workbook formulas and formatting
- Automatically insert and update project records
- Protect critical project information from unauthorized modification
- Improve data accuracy and consistency

## Key Features

### Automated Data Conflation

- Reads centralized project database exports
- Compares records against on-site tracking workbooks
- Matches records using project identifiers and business rules
- Updates only the fields that require modification

### Record Management

- Detects new project records
- Automatically inserts missing entries
- Updates existing project information
- Prevents duplicate records

### Data Validation

- Validates project identifiers
- Standardizes date formats
- Handles missing or incomplete information
- Preserves data integrity throughout the process

### Workbook Protection

- Locks protected project fields
- Restricts unauthorized editing
- Maintains worksheet permissions
- Preserves formulas and workbook structure

### Workflow Automation

- Updates project tracking statuses
- Maintains calculated fields
- Refreshes schedule-related metrics
- Supports daily field updates from construction teams

## Technologies

- Python
- Pandas
- OpenPyXL
- Excel Automation
- Data Validation
- ETL Processing

## Technical Highlights

- Automated record matching and reconciliation
- Dynamic row insertion and updating
- Formula generation and preservation
- Workbook protection and access control
- Date standardization and validation
- Large-scale spreadsheet processing

## Results

- Eliminated manual data entry workflows
- Reduced risk of human error
- Improved consistency between project databases and field reports
- Streamlined daily project update processes
- Increased efficiency for project management teams

## Skills Demonstrated

- Data Engineering
- ETL Development
- Process Automation
- Excel Automation
- Python Development
- Data Validation
- Workflow Optimization
- Business Process Improvement
