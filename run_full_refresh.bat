@echo off
:: Focused Meta ETL Refresh Script
:: Runs account metadata + delivery insights + creative dimensions.

echo =======================================================
echo     STARTING FULL META ETL REFRESH
echo =======================================================

:: Change directory to the location of this script
cd /d "%~dp0"

echo [INFO] Step 1: Fetching Account Metadata...
python main.py accounts-info
if errorlevel 1 goto :error

echo [INFO] Step 2: Fetching Campaigns...
python main.py campaigns-info
if errorlevel 1 goto :error

echo [INFO] Step 3: Fetching Adsets...
python main.py adsets-info
if errorlevel 1 goto :error

echo [INFO] Step 4: Fetching Ads...
python main.py ads-info
if errorlevel 1 goto :error

echo [INFO] Step 5: Fetching Creatives (refreshes image_url / thumbnail_url)...
python main.py creatives-info
if errorlevel 1 goto :error

echo [INFO] Step 6: Fetching Insights (Last 7 Days)...
python main.py insights-daily --date-preset last_7d
if errorlevel 1 goto :error

echo [INFO] Step 7: Fetching Insights (Today)...
python main.py insights-daily --date-preset today
if errorlevel 1 goto :error

echo =======================================================
echo     FULL REFRESH COMPLETED SUCCESSFULLY
echo =======================================================
goto :end

:error
echo =======================================================
echo     REFRESH FAILED - check errors above
echo =======================================================
exit /b 1

:end
pause
