# 🏗️ PlanningScout Engine v2.0
### *Advanced Lead Generation for UK Planning & Residential Land*

---

## 🎯 The USP
PlanningScout is a **Proximity-Logic Engine** that reads deep into Planning Decision Notices (PDFs). It identifies "High-Probability" appeal leads by finding specific legal triggers like **Grey Belt**, **Tilted Balance**, and **Housing Supply** failures that manual searchers miss.

---

## 🚀 Onboarding a New Client

Follow these **5 steps** to set up a new client in under 10 minutes:

### 1. Google Sheets Setup
* Create a sheet from the template.
* Rename the tab to `Leads`.
* Share as **Editor** with the Service Account email.
* Copy the **Sheet ID** from the URL.

### 2. Configure Client DNA
* Create `clients/clientname.json`.
* Paste the Sheet ID and tailor the `search_keywords`.

### 3. GitHub Secrets
* Add `GMAIL_TO_CLIENTNAME` to GitHub Secrets.

### 4. Create Automation
* Copy `run_maplanning.yml` to a new `.yml` file.
* Update the name and the path to the new `.json`.

### 5. Initial Run
* Go to **Actions** -> Select Client -> **Run workflow**.
* Set weeks to `12` for a full 3-month history.

---

## 📋 Weekly Maintenance

* **Monday:** Check "Actions" to ensure all automated runs finished (Green checkmarks).
* **Tuesday:** Audit the "Leads" sheet for any "False Positives" (Approved apps that slipped through).
* **Wednesday:** Send the "Weekly Digest" email to clients using the report template.

---

## 🛡️ Technical Safety
* **Rate Limiting:** Engine includes `time.sleep()` to avoid portal blocks.
* **Auth:** Uses Google OAuth2 Service Accounts.
