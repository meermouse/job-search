# Jie’s Job Search

## 📌 Overview

Jie’s Job Search is an application designed to help individuals in the UK who require visa sponsorship find suitable employment opportunities.

The system focuses on automating job discovery by combining CV analysis, job search aggregation, and visa sponsor filtering.

---

## 🎯 Objectives

* Analyse a candidate’s CV to determine suitable job roles
* Search for relevant job listings across multiple platforms
* Filter results to include only employers licensed to sponsor visas
* Enable filtering by location and salary above a certain threshold (£60k by default)
* Present results in a clear, structured format

---

## ⚙️ Core Features

### 1. CV Analysis

* Accept a CV as input (e.g. PDF, DOCX, or text)
* Extract key information such as:

  * Skills
  * Experience
  * Job titles
* Use this data to generate relevant job search queries

---

### 2. Job Search Integration

The application will search for jobs across the following platforms:

* LinkedIn
* Indeed
* Reed
* NHS - https://www.nhsjobs.com/

---

### 3. Visa Sponsor Filtering

* Filter job results based on whether the employer is listed in the official UK government sponsor register:

  * **Register of Worker and Temporary Worker Licensed Sponsors**
* Data source:

  * https://www.gov.uk/csv-preview/69f47183ab602a88957eefa6/2026-05-01_-_Worker_and_Temporary_Worker.csv
* The dataset may be:

  * Retrieved dynamically from the URL, or
  * Stored locally as a CSV file

---

### 4. Job Results Display

Search results will be displayed in a table with the following columns:

| Column            | Required | Description                       |
| ----------------- | -------- | --------------------------------- |
| Job Title         | ✅ Yes    | Title of the job listing          |
| Location          | ❌ No     | Job location                      |
| Brief Description | ❌ No     | Short summary of the role         |
| Salary            | ❌ No     | Salary information (if available) |
| Link              | ✅ Yes    | URL to the job posting            |

* The **Link** column must provide a direct link to the job listing
* At minimum, each result must include:

  * Job Title
  * Link

---

## 🔄 Workflow

1. User uploads CV
2. System analyses CV and extracts relevant data
3. System generates job search queries
4. Queries are sent to supported job platforms
5. Results are collected and aggregated
6. Employers are cross-referenced with the sponsor list
7. Filtered results are displayed in a table

---

## 🧩 Future Enhancements (Optional)

* Save and track job applications
* Ranking/scoring jobs based on relevance
* Alerts for new matching jobs
* Integration with application autofill tools

---

## 🛠️ Notes

* Not all employers listed as sponsors will actively offer sponsorship for every role
* Job listings may not always explicitly state visa sponsorship availability
* Additional heuristics or keyword filtering may improve accuracy

---
