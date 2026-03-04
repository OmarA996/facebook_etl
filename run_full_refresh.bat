@echo off
:: Full Meta ETL Refresh Script
:: Changes directory to the script's location and runs all pipelines.

echo =======================================================
echo     STARTING FULL META ETL REFRESH
echo =======================================================

:: Change directory to the location of this script
cd /d "%~dp0"

echo [INFO] Step 1: Fetching Account Metadata...
python main.py accounts-info

echo [INFO] Step 2: Fetching Campaign Metadata...
python main.py campaigns-info

echo [INFO] Step 3: Fetching Ad Set Metadata...
python main.py adsets-info

echo [INFO] Step 4: Fetching Ad Metadata...
python main.py ads-info

echo [INFO] Step 5: Fetching Creative Metadata...
python main.py creatives-info

echo [INFO] Step 6: Fetching Insights (Last 7 Days)...
python main.py insights-daily --date-preset last_7d

echo [INFO] Step 7: Fetching Insights (Today)...
python main.py insights-daily --date-preset today

echo [INFO] Step 8: Hydrating Missing Previews (Optional)...
python main.py hydrate-previews --limit 500

echo =======================================================
echo     FULL REFRESH COMPLETED SUCCESSFULLY
echo =======================================================
pause
