@echo off
cd /d C:\Users\ASUS\Desktop\facebook_etl_new_big
echo [%date% %time%] Starting accounts-insights >> logs\scheduler.log 2>&1
"C:\Users\ASUS\AppData\Local\Python\bin\python.exe" main.py accounts-insights --days-back 7 --to-bigquery >> logs\scheduler.log 2>&1
echo [%date% %time%] Finished accounts-insights (exit %errorlevel%) >> logs\scheduler.log 2>&1
