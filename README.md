# Facebook Insights ETL Pipeline

A robust, type-safe, and modular ETL (Extract, Transform, Load) pipeline for fetching marketing data from the Meta Graph API and storing it in PostgreSQL.

## Features

- **Robust Data Extraction**: Fetches insights, creatives, campaigns, ad sets, and ads with automatic pagination and rate limit handling.
- **Efficient Updates**: Uses `ON CONFLICT DO UPDATE` (upsert) strategies to prevent duplicates and ensure data consistency.
- **Modular CLI**: Easy-to-use command-line interface for running specific pipelines and maintenance tasks.
- **Dynamic Configuration**: Supports multiple environments (e.g., freelance, agency) via `.env` profiles.
- **Structured Logging**: JSON-formatted logs for better observability.
- **Optimized Previews**: Decoupled "hydration" pipeline to fetch ad previews on demand, saving API calls.

## Quick Start

### 1. Prerequisites

- Python 3.9+
- PostgreSQL
- Meta Developer Account (App ID, App Secret, Access Token)

### 2. Installation

1.  Clone the repository.
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3.  Set up environment variables in `.env` (see `.env.example` or below).

### 3. Configuration

Create a `.env` file in the root directory:

```ini
# Meta API
META_ACCESS_TOKEN=your_access_token
META_APP_ID=your_app_id
META_APP_SECRET=your_app_secret
META_API_VERSION=v21.0

# Database (Default)
DB_CONN_STRING=postgresql://user:pass@localhost:5432/dbname

# Ad Accounts (Default)
META_AD_ACCOUNT_IDS=["act_123456789", "act_987654321"]

# Optional Profiles (e.g., for different clients)
DB_CONN_STRING_AGENCY=postgresql://user:pass@localhost:5432/agency_db
META_AD_ACCOUNT_IDS_AGENCY=["act_111111", "act_222222"]
```

## Usage

Run the pipeline using `main.py`.

### Daily Insights (The Core Pipeline)

Fetches yesterday's data for all configured ad accounts.

```bash
python main.py insights-daily
```

**Options:**
- `--date-preset`: `today`, `yesterday`, `last_7d`, etc. (default: `yesterday`)
- `--level`: `ad`, `adset`, `campaign`, `account` (default: `ad`)
- `--breakdowns`: Comma-separated list e.g. `age,gender`
- `--db-profile`: Use a specific profile from `.env` (e.g., `agency`)

### Dimension Pipelines

Fetch metadata for different entities.

```bash
python main.py creatives-info   # Fetch ad creatives (images, titles)
python main.py campaigns-info   # Fetch campaign details
python main.py adsets-info      # Fetch ad set details
python main.py ads-info         # Fetch ad details
python main.py accounts-info    # Fetch ad account details
```

### On-Demand Previews (Hydration)

Fetch visual previews (HTML/URLs) only for creatives that are missing them.
**Prerequisite**: Run `creatives-info` first.

```bash
python main.py hydrate-previews --limit 100
```

### Cleaning & Maintenance

```bash
# Clean raw data into fact tables (if you need to re-process)
python main.py insights-clean --from-date 2023-01-01

# Truncate tables (WARNING: Deletes data)
python main.py db-truncate --tables fact_meta_insight_daily
```

## Automation

For convenience, you can run all metadata pipelines and fetch the last 8 days of insights (Last 7 Days + Today) using the provided batch script:

```bash
run_full_refresh.bat
```

This script is ideal for scheduled tasks or manual full refreshes.


## Project Structure

- `src/cli/`: Command-line interface handlers.
- `src/clients/`: Meta Graph API client with retry logic.
- `src/config/`: Configuration loading using Pydantic.
- `src/etl/extract/`: Logic for making API calls.
- `src/etl/transform/`: Data cleaning and normalization.
- `src/etl/load/`: Database loading (Upsert) logic.
- `src/etl/pipelines/`: Orchestrates Extract -> Transform -> Load flows.
- `src/schema/`: Defines unique keys for upsert logic.
- `tests/`: Unit tests.

## Development

Run tests with pytest:

```bash
pytest tests/
```
