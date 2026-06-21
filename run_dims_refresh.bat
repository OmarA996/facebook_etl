@echo off
cd /d C:\Users\ASUS\Desktop\facebook_etl_new_big
echo [%date% %time%] Starting dims-refresh >> logs\scheduler.log 2>&1
"C:\Users\ASUS\AppData\Local\Python\bin\python.exe" main.py dims-refresh --to-bigquery >> logs\scheduler.log 2>&1
echo [%date% %time%] Finished dims-refresh (exit %errorlevel%) >> logs\scheduler.log 2>&1
